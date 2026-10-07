"""Fixed P0 protocol, separate technical smoke run, and auditable run artifacts."""

from __future__ import annotations

import csv
import json
import os
import shutil
import time
import traceback
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import torch

from .core import (ROOT, TASKS, Config, file_sha256, fingerprint, isolated_rng,
                   package_versions, runtime_manifest, source_files, source_hashes,
                   utc_now, write_json)
from .engine import Engine, load_checkpoint, save_checkpoint
from .environment import CostCounter
from .evaluation import build_banks, evaluate_model


@dataclass(frozen=True)
class Plan:
    stage: str = "p0_pretraining"
    total_steps: int = 400000
    diagnostic_steps: tuple[int, ...] = (0, 100000, 200000, 400000)
    checkpoint_steps: tuple[int, ...] = (200000, 400000)
    diagnostic_episodes_per_task: int = 20
    block_steps: int = 4000

    @classmethod
    def smoke(cls) -> "Plan":
        return cls("p0_runner_validation", 8000, (0, 4000, 8000), (4000, 8000), 2)

    def validate(self) -> None:
        if self not in (Plan(), Plan.smoke()):
            raise ValueError("Use the fixed P0 protocol or its explicitly labelled technical smoke plan.")


def selection_rules(previous: dict, current: dict) -> dict:
    """Use integer success counts so rate-rounding cannot break exact ties."""
    previous_counts, current_counts = previous["success_counts"], current["success_counts"]
    counts = [current_counts[t] for t in TASKS]
    sample_sizes = [current["episodes_by_task"][t] for t in TASKS]
    if sample_sizes != [20] * 4 or [previous["episodes_by_task"][t] for t in TASKS] != [20] * 4:
        raise ValueError("Research selectors require all twenty public episodes per task.")
    if any(not isinstance(n, int) or not 0 <= n <= 20 for n in counts + [previous_counts[t] for t in TASKS]):
        raise ValueError("Invalid success counts.")
    gap = current["step"] - previous["step"]
    if gap <= 0:
        raise ValueError("Progress requires an earlier diagnostic.")
    deltas = [current_counts[t] - previous_counts[t] for t in TASKS]
    lowest, largest = min(counts), max(deltas)
    failure = "F_" + TASKS[counts.index(lowest)] if counts.count(lowest) == 1 else "U"
    progress = "F_" + TASKS[deltas.index(largest)] if largest > 0 and deltas.count(largest) == 1 else "U"
    inputs = [{key: diagnostic[key] for key in (
        "step", "success_counts", "episodes_by_task", "results_hash")} for diagnostic in (previous, current)]
    mixed = [task for task in TASKS if 0 < current_counts[task] < 20]
    return {
        "step": current["step"], "previous_step": previous["step"],
        "mixed_success_tasks": mixed, "eligible": len(mixed) >= 2,
        "recommendations": {"Uniform": "U", "Failure": failure, "Progress": progress},
        "progress_per_training_step": {task: deltas[i] / 20 / gap for i, task in enumerate(TASKS)},
        "input_hash": fingerprint(inputs), "inputs": inputs,
        "information_source": "public diagnostic bank only", "outcome_scores_used": False,
    }


def verify_validation(path: Path, config: Config, *, runner: bool = False) -> dict:
    """A previous pass applies only to this exact source, configuration and runtime."""
    path = path.resolve()
    if not path.is_relative_to((ROOT / "results").resolve()):
        raise ValueError("Validation evidence must be inside this version's results directory.")
    result_name = "run_summary.json" if runner else "preflight.json"
    result = json.loads((path / result_name).read_text(encoding="utf-8"))
    manifest = json.loads((path / "run_manifest.json").read_text(encoding="utf-8"))
    if runner:
        passed = (result["status"] == "completed" and result["stage"] == "p0_runner_validation"
                  and result["training_steps"] == 8000 and result["restored_checkpoints_verified"] == 2)
    else:
        passed = (result["status"] == "passed" and result["checks_passed"] == 10
                  and result["checks_planned"] == 10)
    if not passed or manifest["source_hashes"] != source_hashes():
        raise RuntimeError("Missing successful validation for the current source.")
    if manifest["packages"] != package_versions() or manifest["config_hash"] != fingerprint(config.to_dict()):
        raise RuntimeError("Validation used a different package version, device or configuration.")
    return {"path": path.relative_to(ROOT).as_posix(), "result_hash": file_sha256(path / result_name),
            "manifest_hash": file_sha256(path / "run_manifest.json")}


class Pretraining:
    def __init__(self, config: Config, plan: Plan, output: Path, evidence: dict):
        plan.validate()
        if config.seed != 901 or config.version != "02_p0_uniform_pretraining_v1":
            raise ValueError("This P0 version fixes original seed 901.")
        self.config, self.plan, self.output, self.evidence = config, plan, output, evidence
        self.costs = CostCounter()
        self.engine = None
        self.banks = None
        self.manifest = None
        self.diagnostics = {}
        self.checkpoints = []
        self.stages = []
        self.training_seconds = 0.0
        self.selected_step = None
        self.started = time.perf_counter()
        self.initial_parameters = None

    def event(self, stage: str, **extra) -> None:
        step = self.engine.model.num_timesteps if self.engine else 0
        throughput = step / self.training_seconds if self.training_seconds else None
        row = {"time": utc_now(), "pid": os.getpid(), "stage": stage,
               "training_steps": step, "total_training_steps": self.plan.total_steps,
               "updates": self.engine.model._n_updates if self.engine else 0,
               "train_steps_per_second": throughput,
               "remaining_training_seconds": (self.plan.total_steps - step) / throughput if throughput else None,
               "elapsed_seconds": time.perf_counter() - self.started,
               "costs": self.costs.snapshot(), **extra}
        with (self.output / "progress.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
        print(f"{row['time']} | {stage} | step {step:,}/{self.plan.total_steps:,} | updates {row['updates']:,}", flush=True)

    def measured(self, name: str, function):
        self.event(name + "_started")
        before, started = self.costs.snapshot(), time.perf_counter()
        record = {"stage": name, "started_at": utc_now(), "passed": False}
        try:
            result = function()
            record["passed"] = True
            return result
        except BaseException as error:
            record["error"] = f"{type(error).__name__}: {error}"
            raise
        finally:
            record["seconds"] = time.perf_counter() - started
            record["costs"] = {k: v - before[k] for k, v in self.costs.snapshot().items()}
            if name.startswith("train_"):
                self.training_seconds += record["seconds"]
            self.stages.append(record)
            write_json(self.output / "stages" / f"{len(self.stages):03d}_{name}.json", record)
            ledger = self.output / "cost_ledger.csv"
            new = not ledger.exists()
            with ledger.open("a", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["stage", "passed", "seconds", *before])
                if new:
                    writer.writeheader()
                writer.writerow({key: record[key] for key in ("stage", "passed", "seconds")} | record["costs"])
            self.event(name + ("_completed" if record["passed"] else "_failed"))

    def diagnostic(self, step: int) -> dict:
        before = self.engine.fingerprints()
        result = evaluate_model(
            self.engine.model, self.banks["diagnostic"], self.costs,
            self.output / "diagnostic_episodes.csv", f"step_{step:09d}",
            limit_per_task=self.plan.diagnostic_episodes_per_task, context=self.plan.stage)
        if self.engine.fingerprints() != before:
            raise RuntimeError("Diagnostic evaluation changed learning, replay, collector or RNG state.")
        if result["episodes_by_task"] != dict.fromkeys(TASKS, self.plan.diagnostic_episodes_per_task):
            raise RuntimeError("Incomplete public diagnostic.")
        result.update({"step": step, "state_unchanged": True})
        write_json(self.output / "diagnostics" / f"step_{step:09d}.json", result)
        self.diagnostics[step] = result
        self.event("diagnostic_result", success_by_task=result["success_by_task"])
        return result

    def checkpoint(self, step: int) -> dict:
        directory = self.output / "checkpoints" / f"step_{step:09d}"
        before = self.engine.fingerprints()
        manifest = save_checkpoint(self.engine, directory)
        started = time.perf_counter()
        with isolated_rng():
            restored = load_checkpoint(directory, self.costs)
            try:
                if restored.fingerprints() != before:
                    raise RuntimeError("Full checkpoint restore does not match the live state.")
            finally:
                restored.close()
                del restored
        restore_seconds = time.perf_counter() - started
        if self.engine.fingerprints() != before:
            raise RuntimeError("Checkpoint verification changed live training state.")
        record = {"step": step, "path": directory.relative_to(self.output).as_posix(),
                  "save_seconds": manifest["seconds"], "restore_seconds": restore_seconds,
                  "restored_state_matches": True, "manifest_hash": file_sha256(directory / "checkpoint_manifest.json")}
        write_json(directory / "restore_verification.json", record)
        self.checkpoints.append(record)
        return record

    def train_block(self) -> dict:
        result = self.engine.train_steps(
            self.plan.block_steps, "p0_uniform" if self.plan.stage == "p0_pretraining" else "runner_smoke",
            self.output / "train_metrics.csv", episodes_path=self.output / "train_episodes.csv")
        step = self.engine.model.num_timesteps
        replay = self.engine.model.replay_buffer
        if (not self.engine.at_boundary or self.engine.collected_steps.tolist() != [step // 4] * 4
                or self.engine.task_visits.tolist() != [step // 2000] * 4
                or replay.size() != min(step, self.config.buffer_size)
                or replay.pos != step % self.config.buffer_size
                or replay.sampled_total != self.engine.model._n_updates * self.config.batch_size
                or not np.all(replay.sampled_task_counts > 0)):
            raise RuntimeError("Uniform collection, replay exposure, or buffer counters failed a block audit.")
        self.event("uniform_block_audited", collected_by_task=dict(zip(TASKS, self.engine.collected_steps.tolist())),
                   sampled_by_task=dict(zip(TASKS, replay.sampled_task_counts.tolist())),
                   replay_size=replay.size(), replay_pos=replay.pos, losses=self.engine.model.last_update_metrics)
        return result

    def freeze_selection(self, step: int) -> None:
        previous_step = 100000 if step == 200000 else 200000
        result = selection_rules(self.diagnostics[previous_step], self.diagnostics[step])
        write_json(self.output / "selectors" / f"step_{step:09d}.json", result)
        if self.selected_step is None and result["eligible"]:
            self.selected_step = step
            write_json(self.output / "selected_checkpoint.json", {
                **result, "checkpoint": f"checkpoints/step_{step:09d}",
                "selection_rule": "first eligible among 200k then 400k; no branch results used"})

    def parameter_changes(self) -> dict:
        if self.engine is None or self.initial_parameters is None:
            return {}
        current = self.engine.model.policy.state_dict()
        changes = {}
        for prefix in ("actor.", "critic.", "critic_target."):
            values = [float((value.detach().cpu() - self.initial_parameters[name]).abs().max())
                      for name, value in current.items() if name.startswith(prefix)]
            changes[prefix] = max(values, default=0.0) if all(np.isfinite(v) for v in values) else None
        return changes

    def run(self) -> bool:
        success, error_text = False, None
        self.event("initializing")
        try:
            self.manifest = runtime_manifest(self.config, self.plan.stage)
            self.manifest.update({"plan": asdict(self.plan), "validation_evidence": self.evidence,
                                  "initialization": "fresh random initialization; no checkpoint loaded",
                                  "pid": os.getpid()})
            write_json(self.output / "run_started.json", self.manifest)
            write_json(self.output / "resolved_config.json", self.config.to_dict())
            write_json(self.output / "execution_plan.json", asdict(self.plan))
            for path in source_files():
                target = self.output / "source_snapshot" / path.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
            self.banks = self.measured("build_evaluation_banks", lambda: build_banks(self.config, self.costs))
            write_json(self.output / "evaluation_banks.json", self.banks)
            self.engine = self.measured("initialize_fresh_sac", lambda: Engine(self.config, self.costs))
            self.initial_parameters = {k: v.detach().cpu().clone() for k, v in self.engine.model.policy.state_dict().items()}
            write_json(self.output / "initial_state.json", self.engine.fingerprints())
            self.measured("diagnostic_000000000", lambda: self.diagnostic(0))
            while self.engine.model.num_timesteps < self.plan.total_steps:
                end = self.engine.model.num_timesteps + self.plan.block_steps
                self.measured(f"train_{end:09d}", self.train_block)
                if end in self.plan.checkpoint_steps:
                    self.measured(f"checkpoint_{end:09d}", lambda: self.checkpoint(end))
                if end in self.plan.diagnostic_steps:
                    self.measured(f"diagnostic_{end:09d}", lambda: self.diagnostic(end))
                if self.plan.stage == "p0_pretraining" and end in self.plan.checkpoint_steps:
                    self.freeze_selection(end)
            changes = self.parameter_changes()
            if not all(value is not None and value > 0 for value in changes.values()):
                raise RuntimeError("One or more learned modules did not change with finite parameters.")
            if source_hashes() != self.manifest["source_hashes"]:
                raise RuntimeError("Source or configuration files changed during the run.")
            if any(sum(stage["costs"][key] for stage in self.stages) != value
                   for key, value in self.costs.snapshot().items()):
                raise RuntimeError("Stage cost ledger does not reconcile with actual counters.")
            if self.plan.stage == "p0_pretraining":
                write_json(self.output / "branchpoint_decision.json", {
                    "selected_step": self.selected_step,
                    "status": "eligible_checkpoint_available" if self.selected_step else "defer_research_branches",
                    "research_branches_executed": 0,
                    "rule": "200k if at least two tasks have 1..19 successes; otherwise 400k; otherwise defer"})
            success = True
        except BaseException:
            error_text = traceback.format_exc()
            (self.output / "failure_traceback.txt").write_text(error_text, encoding="utf-8")
            print(error_text, flush=True)
        finally:
            if self.engine is not None:
                self.engine.close()
            summary = {
                "stage": self.plan.stage, "status": "completed" if success else "failed", "completed_at": utc_now(),
                "training_steps": self.engine.model.num_timesteps if self.engine else 0,
                "sac_iterations": self.engine.model._n_updates if self.engine else 0,
                "collected_by_task": dict(zip(TASKS, self.engine.collected_steps.tolist())) if self.engine else {},
                "sampled_by_task": dict(zip(TASKS, self.engine.model.replay_buffer.sampled_task_counts.tolist())) if self.engine else {},
                "training_seconds": self.training_seconds,
                "elapsed_seconds": time.perf_counter() - self.started, "costs": self.costs.snapshot(),
                "diagnostics": self.diagnostics, "checkpoints": self.checkpoints,
                "restored_checkpoints_verified": len(self.checkpoints), "selected_checkpoint_step": self.selected_step,
                "parameter_max_abs_change": self.parameter_changes(), "outcome_bank_episodes_evaluated": 0,
                "research_branches_executed": 0, "error": error_text,
                "cuda_peak_allocated_bytes": torch.cuda.max_memory_allocated() if self.config.device == "cuda" else None,
            }
            write_json(self.output / "run_summary.json", summary)
            write_json(self.output / "run_manifest.json", {**(self.manifest or {}), **summary})
            self.event(summary["status"])
        print(f"RESULT: {summary['status']} | {self.output}", flush=True)
        return success
