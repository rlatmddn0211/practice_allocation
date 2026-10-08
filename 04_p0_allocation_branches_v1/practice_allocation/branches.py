"""Sequential complete-state branches with immutable evidence and exact costs."""

from __future__ import annotations

import csv
import gc
import json
import os
import shutil
import time
import traceback

import numpy as np
import torch

from .branch_analysis import make_analysis
from .branch_protocol import import_parent, reset_plan, verify_parent
from .core import (ALLOCATIONS, ROOT, TASKS, derived_seed, file_sha256, fingerprint,
                   isolated_rng, runtime_manifest, source_files, source_hashes,
                   utc_now, write_json)
from .engine import load_checkpoint, save_checkpoint
from .environment import CostCounter
from .evaluation import evaluate_model


class BranchExperiment:
    def __init__(self, config, plan, output, evidence):
        plan.validate()
        self.config, self.plan, self.output, self.evidence = config, plan, output, evidence
        self.costs = CostCounter()
        self.engine = self.manifest = self.parent_receipt = self.banks = None
        self.current = None
        self.stages, self.completed = [], []
        self.training_seconds = 0.0
        self.started = time.perf_counter()
        self.imported_checkpoint = output / "initial_checkpoint"
        self.baseline = None
        self.reset_hashes = {}
        self.observed_hash_owners = {}
        self.evaluation_transitions = 0
        self.outcome_episodes = 0

    def event(self, stage, **extra):
        additional = self.costs.train_iterations
        speed = additional / self.training_seconds if self.training_seconds else None
        row = {"time": utc_now(), "pid": os.getpid(), "stage": stage,
               "current_branch": self.current, "branches_completed": len(self.completed),
               "branches_planned": self.plan.branch_count, "additional_training_steps": additional,
               "total_additional_training_steps": self.plan.total_steps,
               "current_model_step": self.engine.model.num_timesteps if self.engine else None,
               "training_seconds": self.training_seconds, "train_steps_per_second": speed,
               "remaining_training_seconds_excluding_evaluation": (self.plan.total_steps - additional) / speed if speed else None,
               "elapsed_seconds": time.perf_counter() - self.started, "costs": self.costs.snapshot(), **extra}
        with (self.output / "progress.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
        print(f"{row['time']} | {stage} | {self.current or 'shared'} | "
              f"additional {additional:,}/{self.plan.total_steps:,} | branches {len(self.completed)}/{self.plan.branch_count}", flush=True)

    def measured(self, name, function):
        self.event(name + "_started")
        before, started = self.costs.snapshot(), time.perf_counter()
        record = {"stage": name, "started_at": utc_now(), "passed": False}
        try:
            value = function()
            record["passed"] = True
            return value
        except BaseException as error:
            record["error"] = f"{type(error).__name__}: {error}"
            raise
        finally:
            record["seconds"] = time.perf_counter() - started
            record["costs"] = {key: value - before[key] for key, value in self.costs.snapshot().items()}
            if name.startswith("train_"):
                self.training_seconds += record["seconds"]
            self.stages.append(record)
            write_json(self.output / "stages" / f"{len(self.stages):03d}_{name}.json", record)
            ledger = self.output / "cost_ledger.csv"
            fresh = not ledger.exists()
            with ledger.open("a", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["stage", "passed", "seconds", *before])
                if fresh:
                    writer.writeheader()
                writer.writerow({key: record[key] for key in ("stage", "passed", "seconds")} | record["costs"])
            # Time is accounted before reporting speed, unlike the original P0 audit event.
            self.event(name + ("_completed" if record["passed"] else "_failed"))

    def evaluate(self, evaluation_id, destination):
        before = self.engine.fingerprints()
        result = evaluate_model(self.engine.model, self.banks[self.plan.bank], self.costs,
                                self.output / "evaluation_episodes.csv", evaluation_id,
                                limit_per_task=self.plan.episodes_per_task, context=self.plan.stage)
        if self.engine.fingerprints() != before:
            raise RuntimeError("Evaluation changed learning, replay, collector, or RNG state.")
        if result["episodes_by_task"] != dict.fromkeys(TASKS, self.plan.episodes_per_task):
            raise RuntimeError("An evaluation is incomplete.")
        expected_macro = sum(result["success_counts"].values()) / (4 * self.plan.episodes_per_task)
        if not np.isclose(result["macro_success"], expected_macro, atol=1e-15, rtol=0):
            raise RuntimeError("Evaluation macro and episode counts disagree.")
        self.evaluation_transitions += result["environment_steps"]
        if self.plan.bank == "outcome":
            self.outcome_episodes += result["episodes"]
        result.update({"evaluation_id": evaluation_id, "bank": self.plan.bank,
                       "state_unchanged": True, "parent_step": self.plan.parent_step,
                       "purpose": "Research outcome; never selector input" if self.plan.bank == "outcome"
                       else "Technical runner verification on public diagnostic states; not research results"})
        write_json(destination, result)
        self.event("evaluation_result", evaluation_id=evaluation_id, success_by_task=result["success_by_task"])
        return result

    def verified_checkpoint(self, directory):
        before = self.engine.fingerprints()
        manifest = save_checkpoint(self.engine, directory)
        started = time.perf_counter()
        with isolated_rng():
            restored = load_checkpoint(directory, self.costs)
            try:
                if restored.fingerprints() != before:
                    raise RuntimeError("A branch checkpoint cannot reproduce its complete state.")
            finally:
                restored.close()
                del restored
        if self.engine.fingerprints() != before:
            raise RuntimeError("Checkpoint verification changed the active branch.")
        record = {"step": self.engine.model.num_timesteps,
                  "path": directory.relative_to(self.output).as_posix(),
                  "save_seconds": manifest["seconds"], "restore_seconds": time.perf_counter() - started,
                  "restored_state_matches": True, "manifest_hash": file_sha256(directory / "checkpoint_manifest.json")}
        write_json(directory / "restore_verification.json", record)
        return record

    def release_engine(self):
        if self.engine is not None:
            self.engine.close()
            self.engine = None
        gc.collect()

    def initialize_branch(self, candidate, repeat, directory):
        self.engine = load_checkpoint(self.imported_checkpoint, self.costs)
        before = self.engine.fingerprints()
        if before != self.parent_receipt["parent_state_fingerprints"]:
            raise RuntimeError("A branch did not start from the original complete state.")
        replay = self.engine.model.replay_buffer
        history = fingerprint({k: v for k, v in replay.state_for_hash().items() if k != "branch_start_step"})
        self.branch_initial = {"collected": self.engine.collected_steps.copy(),
                               "sampled": replay.sampled_task_counts.copy(), "sampled_total": replay.sampled_total,
                               "sampled_new": replay.sampled_new_count,
                               "learning_hash": before["learning"], "replay_pos": replay.pos}
        self.engine.start_branch(candidate, repeat)
        after = self.engine.fingerprints()
        if (before["learning"] != after["learning"]
                or history != fingerprint({k: v for k, v in replay.state_for_hash().items() if k != "branch_start_step"})
                or replay.branch_start_step != self.plan.parent_step
                or self.engine.model._n_updates != 199000
                or self.engine.model.num_timesteps != self.plan.parent_step):
            raise RuntimeError("Branch initialization altered learned state, history, or warm-up counters.")
        write_json(directory / "branch_started.json", {
            "created_at": utc_now(), "candidate": candidate, "repeat_seed": repeat,
            "original_seed": 901, "parent_step": self.plan.parent_step,
            "before_fingerprints": before, "after_fingerprints": after,
            "learned_state_and_replay_history_preserved": True,
            "changed": ["continuation learning RNG", "task schedule/reset streams", "replay branch-age marker"],
            "baseline_reference": "../../baseline/evaluation.json",
            "config_hash": fingerprint(self.config.to_dict()),
            "collected_baseline": self.branch_initial["collected"].tolist(),
            "sampled_baseline": self.branch_initial["sampled"].tolist()})

    def train_block(self, candidate, directory):
        result = self.engine.train_steps(self.plan.block_steps, self.current,
                                        directory / "train_metrics.csv", episodes_path=directory / "train_episodes.csv")
        elapsed = self.engine.model.num_timesteps - self.plan.parent_step
        replay = self.engine.model.replay_buffer
        quotas = np.array(ALLOCATIONS[candidate]) * (elapsed // self.plan.block_steps)
        sampled = replay.sampled_task_counts - self.branch_initial["sampled"]
        if (not self.engine.at_boundary or result["updates"] != self.plan.block_steps
                or not np.array_equal(self.engine.task_visits, quotas)
                or not np.array_equal(self.engine.collected_steps - self.branch_initial["collected"], quotas * 500)
                or replay.size() != self.config.buffer_size
                or replay.pos != (self.branch_initial["replay_pos"] + elapsed) % self.config.buffer_size
                or self.engine.model._n_updates != 199000 + elapsed
                or replay.sampled_total - self.branch_initial["sampled_total"] != elapsed * self.config.batch_size
                or sampled.sum() != elapsed * self.config.batch_size or not np.all(sampled > 0)
                or int(np.count_nonzero(replay.birth_steps > self.plan.parent_step)) != elapsed):
            raise RuntimeError("A branch violated its exact allocation, update, or replay contract.")
        return result

    def audit_episode_pairs(self, directory, repeat):
        with (directory / "train_episodes.csv").open(encoding="utf-8", newline="") as handle:
            episodes = list(csv.DictReader(handle))
        if len(episodes) != self.plan.steps_per_branch // 500:
            raise RuntimeError("Missing training episode records.")
        evaluation_hashes = {e["initial_state_hash"] for entries in self.banks.values() for e in entries}
        visits = dict.fromkeys(TASKS, 0)
        audited = []
        for episode in episodes:
            task, state_hash = episode["task"], episode["initial_state_hash"]
            key = (repeat, task, visits[task])
            if int(episode["length"]) != 500 or state_hash in evaluation_hashes:
                raise RuntimeError("Training termination or evaluation-bank separation failed.")
            if key in self.reset_hashes and self.reset_hashes[key] != state_hash:
                raise RuntimeError("Common per-task reset inputs differ between allocation candidates.")
            if state_hash in self.observed_hash_owners and self.observed_hash_owners[state_hash] != key:
                raise RuntimeError("Distinct training reset cases unexpectedly share a physical state.")
            self.reset_hashes[key] = state_hash
            self.observed_hash_owners[state_hash] = key
            audited.append({**episode, "repeat_seed": repeat, "task_visit": visits[task],
                            "reset_seed": derived_seed(repeat, 20, TASKS.index(task), visits[task])})
            visits[task] += 1
        write_json(directory / "training_reset_audit.json", {
            "passed": True, "common_reset_cases_match": True,
            "no_evaluation_states_used_for_training": True, "episodes": audited})

    def run_branch(self, candidate, repeat):
        self.current = f"repeat_{repeat}_{candidate}"
        directory = self.output / "branches" / self.current
        directory.mkdir(parents=True, exist_ok=False)
        started, initial_costs = time.perf_counter(), self.costs.snapshot()
        branch = {"branch_id": self.current, "candidate": candidate, "repeat_seed": repeat,
                  "status": "running", "outcomes": {}, "checkpoints": []}
        try:
            self.measured(f"initialize_{self.current}", lambda: self.initialize_branch(candidate, repeat, directory))
            while self.engine.model.num_timesteps < self.plan.parent_step + self.plan.steps_per_branch:
                horizon = self.engine.model.num_timesteps - self.plan.parent_step + self.plan.block_steps
                self.measured(f"train_{self.current}_{horizon:06d}", lambda: self.train_block(candidate, directory))
                self.event("allocation_block_audited", additional_branch_steps=horizon,
                           collected_new_by_task=dict(zip(TASKS, (self.engine.collected_steps - self.branch_initial["collected"]).tolist())),
                           losses=self.engine.model.last_update_metrics)
                if horizon in self.plan.evaluation_steps:
                    checkpoint = self.measured(f"checkpoint_{self.current}_{horizon:06d}",
                        lambda: self.verified_checkpoint(directory / "checkpoints" / f"extra_{horizon:06d}"))
                    branch["checkpoints"].append(checkpoint)
                    branch["outcomes"][str(horizon)] = self.measured(f"evaluation_{self.current}_{horizon:06d}",
                        lambda: self.evaluate(f"{self.current}_h{horizon:06d}", directory / "evaluations" / f"extra_{horizon:06d}.json"))
            self.audit_episode_pairs(directory, repeat)
            replay = self.engine.model.replay_buffer
            sampled_total = replay.sampled_total - self.branch_initial["sampled_total"]
            if self.engine.fingerprints()["learning"] == self.branch_initial["learning_hash"]:
                raise RuntimeError("The branch completed without changing the learned state.")
            branch.update({"status": "completed", "additional_training_steps": self.plan.steps_per_branch,
                           "additional_sac_iterations": self.plan.steps_per_branch,
                           "collected_new_by_task": dict(zip(TASKS, (self.engine.collected_steps - self.branch_initial["collected"]).tolist())),
                           "sampled_during_branch_by_task": dict(zip(TASKS, (replay.sampled_task_counts - self.branch_initial["sampled"]).tolist())),
                           "sampled_new_experience_fraction": (replay.sampled_new_count - self.branch_initial["sampled_new"]) / sampled_total,
                           "new_experience_fraction_in_final_replay": self.plan.steps_per_branch / self.config.buffer_size,
                           "final_state_fingerprints": self.engine.fingerprints()})
        except BaseException:
            branch.update({"status": "failed", "error": traceback.format_exc(),
                           "additional_training_steps": self.costs.train_iterations - initial_costs["train_iterations"]})
            raise
        finally:
            branch.update({"completed_at": utc_now(), "elapsed_seconds": time.perf_counter() - started,
                           "costs": {k: v - initial_costs[k] for k, v in self.costs.snapshot().items()}})
            write_json(directory / "branch_summary.json", branch)
            self.release_engine()
        self.completed.append(branch)
        self.event("branch_completed", candidate=candidate, repeat_seed=repeat)

    def run(self):
        succeeded, error = False, None
        comparison = None
        try:
            self.manifest = runtime_manifest(self.config, self.plan.stage)
            self.manifest.update({"pid": os.getpid(), "plan": self.plan.to_dict(),
                                  "validation_evidence": self.evidence,
                                  "initialization": "Same complete P0 seed-901 checkpoint at 200k for every branch"})
            write_json(self.output / "run_started.json", self.manifest)
            write_json(self.output / "resolved_config.json", self.config.to_dict())
            write_json(self.output / "execution_plan.json", self.plan.to_dict())
            for path in source_files():
                target = self.output / "source_snapshot" / path.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
            parent, checkpoint, saved, selected, self.banks, self.parent_receipt = self.measured(
                "verify_p0_provenance", lambda: verify_parent(self.config))
            write_json(self.output / "parent_provenance.json", self.parent_receipt)
            write_json(self.output / "frozen_selection_rules.json", selected)
            write_json(self.output / "evaluation_banks.json", self.banks)
            write_json(self.output / "continuation_reset_plan.json", reset_plan(self.plan, self.banks))
            self.engine = self.measured("import_complete_parent_state",
                                       lambda: import_parent(self.config, self.costs, checkpoint, saved))
            self.measured("save_and_verify_initial_checkpoint", lambda: self.verified_checkpoint(self.imported_checkpoint))
            self.baseline = self.measured("evaluate_shared_baseline",
                lambda: self.evaluate("baseline", self.output / "baseline/evaluation.json"))
            self.release_engine()
            for repeat in self.plan.repeat_seeds:
                for candidate in self.plan.candidates:
                    self.run_branch(candidate, repeat)
            self.current = None
            comparison = self.measured("final_comparison", lambda: make_analysis(
                self.output, self.baseline, self.completed, self.plan, selected["recommendations"]))
            self.measured("verify_parent_unchanged_at_end", lambda: verify_parent(self.config))
            if source_hashes() != self.manifest["source_hashes"]:
                raise RuntimeError("Source or configuration changed during the experiment.")
            if (self.costs.train_iterations != self.plan.total_steps
                    or self.costs.environment_steps != self.plan.total_steps + self.evaluation_transitions
                    or self.costs.evaluation_episodes != (1 + self.plan.branch_count * len(self.plan.evaluation_steps)) * 4 * self.plan.episodes_per_task):
                raise RuntimeError("The final experiment budget or evaluation count is inconsistent.")
            if any(sum(stage["costs"][key] for stage in self.stages) != value
                   for key, value in self.costs.snapshot().items()):
                raise RuntimeError("The stage cost ledger does not reconcile.")
            succeeded = True
        except BaseException:
            error = traceback.format_exc()
            (self.output / "failure_traceback.txt").write_text(error, encoding="utf-8")
            print(error, flush=True)
        finally:
            self.release_engine()
            summary = {"stage": self.plan.stage, "status": "completed" if succeeded else "failed",
                       "completed_at": utc_now(), "parent_step": self.plan.parent_step, "original_seed": 901,
                       "continuation_seeds": list(self.plan.repeat_seeds),
                       "branches_completed": len(self.completed), "branches_planned": self.plan.branch_count,
                       "additional_training_steps": self.costs.train_iterations,
                       "training_seconds": self.training_seconds, "elapsed_seconds": time.perf_counter() - self.started,
                       "costs": self.costs.snapshot(), "evaluation_transitions": self.evaluation_transitions,
                       "outcome_bank_episodes_evaluated": self.outcome_episodes,
                       "baseline": self.baseline, "branches": self.completed, "comparison": comparison,
                       "error": error, "cuda_peak_allocated_bytes": torch.cuda.max_memory_allocated()}
            write_json(self.output / "run_summary.json", summary)
            write_json(self.output / "run_manifest.json", {**(self.manifest or {}), **summary})
            self.event(summary["status"])
        return succeeded
