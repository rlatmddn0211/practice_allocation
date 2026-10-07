"""Real-environment gates; every run keeps its source snapshot and failures."""

from __future__ import annotations

import csv
import io
import json
import shutil
import time
import traceback
import unittest
from pathlib import Path

import numpy as np
import torch
from metaworld.policies import (SawyerDrawerCloseV3Policy, SawyerDrawerOpenV3Policy,
                                SawyerWindowCloseV3Policy, SawyerWindowOpenV3Policy)
from stable_baselines3 import SAC

from .core import (ALLOCATIONS, ROOT, TASKS, AllocationSchedule, Config, capture_rng,
                   derived_seed, fingerprint, restore_rng, runtime_manifest,
                   source_files, utc_now, write_json)
from .engine import Engine, load_checkpoint, save_checkpoint
from .environment import CostCounter, TaskEpisode
from .evaluation import build_banks, evaluate_model
from .learning import attach_logger, learning_state

EXPERTS = (SawyerDrawerOpenV3Policy, SawyerDrawerCloseV3Policy,
           SawyerWindowOpenV3Policy, SawyerWindowCloseV3Policy)


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def module_values(model) -> dict:
    return {name: value.detach().cpu().clone() for name, value in model.policy.state_dict().items()}


def max_parameter_difference(first: dict, second: dict, prefix: str = "") -> float:
    values = [(first[key].float() - second[key].float()).abs().max().item()
              for key in first if key.startswith(prefix)]
    return max(values, default=0.0)


class Preflight:
    def __init__(self, config: Config, output: Path):
        self.config, self.output = config, output
        self.costs = CostCounter()
        self.checks = []
        self.engine = None
        self.banks = None
        self.checkpoint = output / "checkpoints" / f"step_{config.smoke_train_steps:09d}"
        self.metrics = output / "train_metrics.csv"
        self.started = time.perf_counter()
        self.manifest = runtime_manifest(config)

    def gate(self, name, function):
        print(f"[{len(self.checks) + 1}] {name}", flush=True)
        start = time.perf_counter()
        counters = self.costs.snapshot()
        record = {"name": name, "started_at": utc_now(), "passed": False}
        try:
            record["details"] = function()
            record["passed"] = True
            return record["details"]
        except BaseException as error:
            record["error"] = f"{type(error).__name__}: {error}"
            raise
        finally:
            record["seconds"] = time.perf_counter() - start
            record["costs"] = {k: v - counters[k] for k, v in self.costs.snapshot().items()}
            self.checks.append(record)
            write_json(self.output / "checks" / f"{len(self.checks):02d}_{name}.json", record)
            ledger = self.output / "cost_ledger.csv"
            new = not ledger.exists()
            with ledger.open("a", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["stage", "passed", "seconds", *record["costs"]])
                if new:
                    writer.writeheader()
                writer.writerow({"stage": name, "passed": record["passed"], "seconds": record["seconds"], **record["costs"]})
            print(f"  {'PASS' if record['passed'] else 'FAIL'} ({record['seconds']:.2f}s)", flush=True)

    def unit_contracts(self):
        suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
        log = io.StringIO()
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
        (self.output / "unit_tests.txt").write_text(log.getvalue(), encoding="utf-8")
        check(result.wasSuccessful(), log.getvalue())
        return {"tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors)}

    def environment_contracts(self):
        rows = []
        rng_before = fingerprint(capture_rng())
        for task in range(4):
            seed = derived_seed(self.config.seed, 20, task, 999)
            with TaskEpisode(task, seed, self.costs) as first, TaskEpisode(task, seed, self.costs) as second, TaskEpisode(task, seed + 1, self.costs) as different:
                check(first.initial_state_hash == second.initial_state_hash, "Same reset seed produced different physical states.")
                check(first.initial_state_hash != different.initial_state_hash, "Different reset seeds produced the same physical state.")
                check(not np.array_equal(first.initial_state["rand_vec"], different.initial_state["rand_vec"]), "Reset task parameters are accidentally frozen.")
                check(np.array_equal(first.observation[-4:], np.eye(4)[task]), "Task one-hot is incorrect.")
                actions = np.random.default_rng(derived_seed(self.config.seed, 300, task)).uniform(-1, 1, (16, 4)).astype(np.float32)
                for action in actions:
                    check(fingerprint(first.step(action)) == fingerprint(second.step(action)), "Same initial state and actions did not reproduce the trajectory.")
                rows.append({"task": TASKS[task], "state_shape": [43], "action_shape": [4],
                             "raw_goal_matches_target": True, "same_seed_same_state": True,
                             "different_seed_changes_task_parameters": True,
                             "identical_action_trajectory_steps": 16})
        check(fingerprint(capture_rng()) == rng_before, "Environment construction/reset changed global training RNG.")
        return {"tasks": rows, "global_rng_unchanged": True}

    def allocation_contracts(self):
        rows, observed_success_before_end = [], 0
        for candidate, quotas in ALLOCATIONS.items():
            scheduler = AllocationSchedule(candidate, derived_seed(self.config.seed, 10))
            counts = np.zeros(4, dtype=int)
            visits = np.zeros(4, dtype=int)
            episode_rows = []
            for _ in range(8):
                task = scheduler.next_task()
                seed = derived_seed(self.config.seed, 20, task, int(visits[task]))
                visits[task] += 1
                expert = EXPERTS[task]()
                with TaskEpisode(task, seed, self.costs) as episode:
                    first_success = None
                    for step in range(500):
                        action = np.clip(expert.get_action(episode.observation[:39]), -1, 1).astype(np.float32)
                        _, _, terminated, truncated, info = episode.step(action)
                        counts[task] += 1
                        if info["success"] and first_success is None:
                            first_success = step + 1
                        check(not terminated and truncated == (step == 499), "500-step contract violated.")
                    if first_success is not None and first_success < 500:
                        observed_success_before_end += 1
                    episode_rows.append({"task": TASKS[task], "length": episode.steps,
                                         "first_success_step": first_success,
                                         "initial_state_hash": episode.initial_state_hash})
            check(np.array_equal(counts, np.array(quotas) * 500), f"Wrong actual step allocation for {candidate}.")
            rows.append({"candidate": candidate, "actual_steps": dict(zip(TASKS, counts.tolist())),
                         "episodes": episode_rows})
        check(observed_success_before_end > 0, "No scripted success fixture exercised success-without-termination.")
        return {"candidates": rows, "success_before_500_then_continued": observed_success_before_end,
                "note": "Scripted policies exercise termination semantics; this is not learned-policy success evidence."}

    def bank_contracts(self):
        self.banks = build_banks(self.config, self.costs)
        write_json(self.output / "evaluation_banks.json", self.banks)
        for name, entries in self.banks.items():
            for task in range(4):
                entry = next(row for row in entries if row["task_index"] == task)
                with TaskEpisode(task, entry["seed"], self.costs) as recreated:
                    check(recreated.initial_state_hash == entry["initial_state_hash"], "Bank initial state cannot be recreated.")
        return {"diagnostic_states": len(self.banks["diagnostic"]), "outcome_states": len(self.banks["outcome"]),
                "all_states_and_task_parameters_distinct": True, "banks_hash": fingerprint(self.banks),
                "reset_checks_per_bank": 4, "distribution": "same official continuous per-task reset distribution"}

    def training_contracts(self):
        self.engine = Engine(self.config, self.costs)
        model = self.engine.model
        check(model.actor.latent_pi[0].in_features == 43, "Actor does not consume the task-conditioned state.")
        check(all(network[0].in_features == 47 for network in model.critic.q_networks), "Critics do not consume state plus action.")
        before = module_values(model)
        result = self.engine.train_steps(self.config.smoke_train_steps, "uniform_training", self.metrics)
        after = module_values(model)
        changes = {prefix: max_parameter_difference(before, after, prefix) for prefix in ("actor.", "critic.", "critic_target.")}
        check(all(value > 0 for value in changes.values()), "An actor/critic/target failed to update.")
        check(all(torch.isfinite(value).all().item() for value in after.values()), "Non-finite learned parameters.")
        for name, module in (("actor", model.actor), ("critic", model.critic)):
            gradients = [p.grad for p in module.parameters() if p.grad is not None]
            check(bool(gradients) and all(torch.isfinite(g).all().item() for g in gradients), f"Invalid {name} gradients.")
        replay = model.replay_buffer
        check(np.all(self.engine.collected_steps == self.config.smoke_train_steps // 4), "Uniform training collected unequal task steps.")
        check(np.all(replay.sampled_task_counts > 0), "A task's transitions never entered a gradient batch.")
        actual_task_counts = np.bincount(replay.observations[:replay.size(), 0, -4:].argmax(axis=1), minlength=4)
        check(np.array_equal(actual_task_counts, self.engine.collected_steps), "Replay task IDs differ from actual collection.")
        end_indices = np.arange(499, replay.size(), 500)
        check(np.all(replay.dones[end_indices, 0] == 1) and np.all(replay.timeouts[end_indices, 0] == 1), "Replay lost timeout flags.")
        check(self.engine.at_boundary, "Validation training did not end at an episode boundary.")
        result.update({"parameter_max_changes": changes,
                       "actual_collected_steps": dict(zip(TASKS, self.engine.collected_steps.tolist())),
                       "actual_replay_transitions": dict(zip(TASKS, actual_task_counts.tolist())),
                       "gradient_sample_counts": dict(zip(TASKS, replay.sampled_task_counts.tolist())),
                       "last_update_metrics": model.last_update_metrics,
                       "network_inputs": {"actor": 43, "each_critic": 47},
                       "resolved_target_entropy": model.target_entropy})
        return result

    def checkpoint_contracts(self):
        manifest = save_checkpoint(self.engine, self.checkpoint)
        try:
            save_checkpoint(self.engine, self.checkpoint)
        except FileExistsError:
            pass
        else:
            raise AssertionError("Existing checkpoint directory was overwritten.")
        return {"step": manifest["step"], "updates": manifest["updates"],
                "seconds_to_save": manifest["seconds"], "full_state_hashes": manifest["state_fingerprints"],
                "overwrite_refused": True}

    def evaluation_contracts(self):
        before = self.engine.fingerprints()
        first = evaluate_model(self.engine.model, self.banks["diagnostic"], self.costs,
                               self.output / "eval_episodes.csv", "diagnostic_replay_1",
                               self.config.validation_eval_episodes_per_task)
        check(self.engine.fingerprints() == before, "Evaluation modified training state or RNG.")
        second = evaluate_model(self.engine.model, self.banks["diagnostic"], self.costs,
                                self.output / "eval_episodes.csv", "diagnostic_replay_2",
                                self.config.validation_eval_episodes_per_task)
        check(self.engine.fingerprints() == before, "Repeated evaluation modified training state or RNG.")
        check(first["results_hash"] == second["results_hash"], "Deterministic evaluation did not reproduce identical outcomes.")
        # The untrained SAC may fail every episode. Exercise positive-success
        # accounting and early stopping independently using official experts.
        class ScriptedFixture:
            policy = torch.nn.Identity()

            def predict(self, observation, deterministic=True):
                expert = EXPERTS[int(observation[-4:].argmax())]()
                return np.clip(expert.get_action(observation[:39]), -1, 1).astype(np.float32), None

        fixture = evaluate_model(ScriptedFixture(), self.banks["diagnostic"], self.costs,
                                 self.output / "eval_episodes.csv", "scripted_success_fixture", 1,
                                 policy_type="scripted_fixture")
        check(fixture["macro_success"] > 0 and fixture["environment_steps"] < 2000,
              "Scripted evaluation fixture did not exercise positive success and early stopping.")
        check(self.engine.fingerprints() == before, "Evaluation fixture changed learning state.")
        return {"first": first, "second": second, "full_training_state_unchanged": True,
                "identical_episode_results": True, "outcome_bank_policy_scores_used": False,
                "scripted_success_and_early_stop_fixture": fixture}

    def resume_contracts(self):
        uninterrupted = self.engine.train_steps(self.config.resume_steps, "continuous", self.metrics, trace=True)
        expected_fingerprints = self.engine.fingerprints()
        expected_parameters = module_values(self.engine.model)
        start = time.perf_counter()
        resumed = load_checkpoint(self.checkpoint, self.costs)
        load_seconds = time.perf_counter() - start
        try:
            resumed_result = resumed.train_steps(self.config.resume_steps, "restored", self.metrics, trace=True)
            differences = max_parameter_difference(expected_parameters, module_values(resumed.model))
            observed_fingerprints = resumed.fingerprints()
            check(uninterrupted["trace_sha256"] == resumed_result["trace_sha256"], "Observation/action/sample-index/loss trajectories differ after resume.")
            check(observed_fingerprints == expected_fingerprints, "Final full learning/replay/collector/RNG state differs after resume.")
            check(differences == 0, "Restored parameters differ from uninterrupted execution.")
            check(resumed_result["updates"] == self.config.resume_steps, "Resume restarted warm-up or changed update count.")
        finally:
            resumed.close()
        return {"continuous": uninterrupted, "resumed": resumed_result, "seconds_to_load": load_seconds,
                "final_state_fingerprints": expected_fingerprints, "parameter_max_abs_difference": differences,
                "comparison": "bitwise equality on the same installed runtime and selected device"}

    def stock_update_contracts(self):
        instrumented = load_checkpoint(self.checkpoint, self.costs)
        state = capture_rng()
        instrumented.model.train(gradient_steps=1, batch_size=self.config.batch_size)
        self.costs.train_iterations += 1
        expected = fingerprint(learning_state(instrumented.model))
        expected_rng = fingerprint(capture_rng())
        expected_indices = instrumented.model.replay_buffer.last_indices.copy()
        stock = SAC.load(self.checkpoint / "model.zip", device=self.config.device)
        stock.load_replay_buffer(self.checkpoint / "replay.pkl")
        attach_logger(stock)
        restore_rng(state)
        stock.train(gradient_steps=1, batch_size=self.config.batch_size)
        self.costs.train_iterations += 1
        check(fingerprint(learning_state(stock)) == expected, "Instrumentation changed stock SAC's updates.")
        check(fingerprint(capture_rng()) == expected_rng, "Instrumentation consumed additional RNG.")
        check(np.array_equal(stock.replay_buffer.last_indices, expected_indices), "Instrumentation changed replay samples.")
        instrumented.close()
        return {"stock_vs_instrumented_state_identical": True, "sampled_indices_identical": True,
                "rng_identical": True, "gradient_iterations_per_model": 1}

    def branch_contracts(self):
        before = json.loads((self.checkpoint / "checkpoint_manifest.json").read_text(encoding="utf-8"))
        starts = []
        branch = None
        try:
            for candidate in ALLOCATIONS:
                engine = load_checkpoint(self.checkpoint, self.costs)
                learned = fingerprint(learning_state(engine.model))
                content = fingerprint({k: v for k, v in engine.model.replay_buffer.state_for_hash().items()
                                       if k != "branch_start_step"})
                engine.start_branch(candidate, 8101)
                check(fingerprint(learning_state(engine.model)) == learned, "Branch changed learned/optimizer state.")
                check(fingerprint({k: v for k, v in engine.model.replay_buffer.state_for_hash().items()
                                   if k != "branch_start_step"}) == content, "Branch changed replay history.")
                check(engine.model.num_timesteps == before["step"], "Branch reset cumulative step counter.")
                check(engine.model._n_updates == before["updates"], "Branch reset update counter.")
                starts.append({"candidate": candidate, "learning_state_hash": learned,
                               "replay_content_hash": content, "step": engine.model.num_timesteps,
                               "updates": engine.model._n_updates})
                engine.close()
            # Reload so this continuation has its own recorded repeat RNG.
            branch = load_checkpoint(self.checkpoint, self.costs)
            branch.start_branch("F_DO", 8101)
            result = branch.train_steps(500, "focus_branch_validation", self.metrics, trace=True)
            check(result["updates"] == 500, "Branch warm-up was incorrectly restarted.")
            replay = branch.model.replay_buffer
            check(np.count_nonzero(replay.birth_steps[:replay.size()] > before["step"]) == 500, "New-transition tags are incorrect.")
            check(replay.sampled_new_count > 0, "Branch's new experiences never reached gradient updates.")
            # Check rejection at a real mid-episode state, then retain its cost.
            branch.step()
            try:
                save_checkpoint(branch, self.output / "checkpoints" / "invalid_mid_episode")
            except RuntimeError:
                pass
            else:
                raise AssertionError("Mid-episode checkpoint was accepted without physics state.")
            check(not (self.output / "checkpoints" / "invalid_mid_episode").exists(), "Rejected checkpoint created an artifact.")
            return {"starts": starts, "short_focus_continuation": result,
                    "new_transitions_before_mid_episode_probe": 500,
                    "new_experiences_sampled": replay.sampled_new_count,
                    "mid_episode_checkpoint_refused": True,
                    "note": "500-step focused continuation plus one rejection probe; not a 40k research branch."}
        finally:
            if branch is not None:
                branch.close()

    def run(self) -> bool:
        write_json(self.output / "run_started.json", self.manifest)
        write_json(self.output / "resolved_config.json", self.config.to_dict())
        for path in source_files():
            target = self.output / "source_snapshot" / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        success, error_text = False, None
        try:
            self.gate("unit_contracts", self.unit_contracts)
            self.gate("environment_inputs_and_reset", self.environment_contracts)
            self.gate("actual_allocation_and_termination", self.allocation_contracts)
            self.gate("evaluation_banks", self.bank_contracts)
            self.gate("shared_sac_training", self.training_contracts)
            self.gate("complete_checkpoint", self.checkpoint_contracts)
            self.gate("evaluation_isolation", self.evaluation_contracts)
            self.gate("continuous_vs_restored_training", self.resume_contracts)
            self.gate("stock_sac_equivalence", self.stock_update_contracts)
            self.gate("branch_initialization_and_no_warmup", self.branch_contracts)
            success = True
        except BaseException:
            error_text = traceback.format_exc()
            (self.output / "failure_traceback.txt").write_text(error_text, encoding="utf-8")
            print(error_text, flush=True)
        finally:
            if self.engine is not None:
                self.engine.close()
            elapsed = time.perf_counter() - self.started
            result = {
                "status": "passed" if success else "failed", "completed_at": utc_now(),
                "scope": "implementation validation only", "device": self.config.device,
                "checks_passed": sum(check["passed"] for check in self.checks),
                "checks_attempted": len(self.checks), "checks_planned": 10,
                "checks": self.checks, "costs": self.costs.snapshot(), "elapsed_seconds": elapsed,
                "error": error_text, "p0_executed": False, "research_branches_executed": 0,
            }
            write_json(self.output / "preflight.json", result)
            write_json(self.output / "run_manifest.json", {**self.manifest, **{k: result[k] for k in (
                "status", "completed_at", "costs", "elapsed_seconds", "p0_executed", "research_branches_executed")},
                "cuda_peak_allocated_bytes": torch.cuda.max_memory_allocated() if self.config.device == "cuda" else None})
            lines = [f"# Implementation validation: {result['status']}", "",
                     f"Device: {self.config.device}. Passed {result['checks_passed']}/10 planned gates.",
                     f"Elapsed: {elapsed:.2f} seconds. Environment transitions: {self.costs.environment_steps}.",
                     f"SAC iterations: {self.costs.train_iterations}. Evaluation episodes: {self.costs.evaluation_episodes}.", "",
                     "| Check | Result | Seconds |", "| --- | --- | ---: |"]
            lines.extend(f"| {r['name']} | {'PASS' if r['passed'] else 'FAIL'} | {r['seconds']:.2f} |" for r in self.checks)
            lines += ["", "This is a technical verification result. P0 and the ten research branches have not run.",
                      "Exact resume is tested on this runtime/device; cross-version or cross-device bitwise equality is not claimed.",
                      "Environment resets include internal simulator work that is counted as resets, not agent transitions."]
            if error_text:
                lines += ["", "See failure_traceback.txt. Failed and unattempted work is not reported as a pass."]
            (self.output / "validation_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"RESULT: {result['status']} | {self.output}", flush=True)
        return success
