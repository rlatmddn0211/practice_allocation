"""Frozen branch protocol, explicit parent import, and validation evidence."""

from __future__ import annotations

import json
import pickle
from dataclasses import asdict, dataclass
from pathlib import Path

from .core import (ROOT, TASKS, Config, derived_seed, file_sha256, fingerprint,
                   package_versions, restore_rng, source_hashes)
from .engine import Engine
from .learning import AuditedSAC, attach_logger


@dataclass(frozen=True)
class BranchPlan:
    stage: str = "p0_allocation_branches"
    candidates: tuple[str, ...] = ("U", "F_DO", "F_DC", "F_WO", "F_WC")
    repeat_seeds: tuple[int, ...] = (1901, 1902)
    parent_step: int = 200000
    steps_per_branch: int = 40000
    evaluation_steps: tuple[int, ...] = (20000, 40000)
    bank: str = "outcome"
    episodes_per_task: int = 50
    block_steps: int = 4000

    @classmethod
    def smoke(cls):
        return cls(stage="branch_runner_validation", repeat_seeds=(1901,),
                   steps_per_branch=4000, evaluation_steps=(4000,),
                   bank="diagnostic", episodes_per_task=2)

    def validate(self):
        if self not in (BranchPlan(), BranchPlan.smoke()):
            raise ValueError("Only the authorized ten branches or the separate five-block technical smoke are supported.")

    @property
    def branch_count(self):
        return len(self.candidates) * len(self.repeat_seeds)

    @property
    def total_steps(self):
        return self.branch_count * self.steps_per_branch

    def to_dict(self):
        return {**asdict(self), "branch_count": self.branch_count,
                "total_additional_training_steps": self.total_steps,
                "baseline_evaluated_once_and_shared": True,
                "primary_horizon": self.steps_per_branch,
                "candidate_order": "repeat first, then U/F_DO/F_DC/F_WO/F_WC"}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def verify_parent(config: Config):
    specification = read_json(ROOT / "configs/parent.json")
    parent = (ROOT / specification["run_relative_to_version"]).resolve()
    if not parent.is_relative_to(ROOT.parent.resolve()) or parent.is_relative_to(ROOT):
        raise ValueError("The parent must be the pinned earlier local run.")
    for name, expected in specification["file_hashes"].items():
        if file_sha256(parent / name) != expected:
            raise RuntimeError(f"Pinned P0 input changed: {name}")
    manifest = read_json(parent / "run_manifest.json")
    selected = read_json(parent / "selected_checkpoint.json")
    banks = read_json(parent / "evaluation_banks.json")
    if (manifest["status"] != "completed" or manifest["stage"] != "p0_pretraining"
            or manifest["config"]["seed"] != 901 or selected["step"] != 200000
            or not selected["eligible"] or selected["outcome_scores_used"]
            or selected["recommendations"] != {"Uniform": "U", "Failure": "F_DO", "Progress": "F_WC"}
            or selected["input_hash"] != fingerprint(selected["inputs"])):
        raise RuntimeError("The completed P0 or its frozen selection is inconsistent.")
    if manifest["packages"] != package_versions():
        raise RuntimeError("The parent and current dependency versions differ.")
    expected_config = dict(manifest["config"], version=config.version)
    if expected_config != config.to_dict():
        raise RuntimeError("A branch changed a parent learner setting beyond version metadata.")
    for name, expected in manifest["source_hashes"].items():
        if file_sha256(parent.parents[2] / name) != expected or file_sha256(parent / "source_snapshot" / name) != expected:
            raise RuntimeError(f"Frozen P0 source mismatch: {name}")
    # These local copies execute every action, update, reset and evaluation.
    # Cross-version import is permitted only because their bytes are identical.
    copied = {}
    for module in ("core.py", "engine.py", "environment.py", "learning.py", "evaluation.py"):
        name = "practice_allocation/" + module
        actual = file_sha256(ROOT / name)
        if actual != manifest["source_hashes"][name]:
            raise RuntimeError(f"The frozen learner changed: {name}")
        copied[name] = actual
    checkpoint = parent / "checkpoints/step_000200000"
    checkpoint_manifest = read_json(checkpoint / "checkpoint_manifest.json")
    if (checkpoint_manifest["schema_version"] != 1
            or checkpoint_manifest["source_hashes"] != manifest["source_hashes"]
            or checkpoint_manifest["packages"] != manifest["packages"]
            or checkpoint_manifest["step"] != 200000 or checkpoint_manifest["updates"] != 199000
            or not read_json(checkpoint / "restore_verification.json")["restored_state_matches"]):
        raise RuntimeError("The selected complete checkpoint is invalid.")
    for name, expected in checkpoint_manifest["files"].items():
        if Path(name).name != name or file_sha256(checkpoint / name) != expected:
            raise RuntimeError(f"Parent checkpoint bytes changed: {name}")
    entries = banks["diagnostic"] + banks["outcome"]
    if any(len({entry[key] for entry in entries}) != 280 for key in
           ("seed", "initial_state_hash", "task_parameter_hash")):
        raise RuntimeError("The original evaluation banks overlap or contain duplicates.")
    for bank, count in (("diagnostic", 20), ("outcome", 50)):
        for index, task in enumerate(TASKS):
            rows = [e for e in banks[bank] if e["task"] == task]
            if (len(rows) != count or {e["episode_index"] for e in rows} != set(range(count))
                    or any(e["task_index"] != index or e["bank"] != bank for e in rows)):
                raise RuntimeError("Incorrect evaluation-bank cardinality or task identity.")
    receipt = {"parent_run": str(parent), "checkpoint": str(checkpoint),
               "pinned_inputs": specification["file_hashes"],
               "checkpoint_files": checkpoint_manifest["files"],
               "byte_identical_learner_modules": copied,
               "original_config_hash": manifest["config_hash"],
               "current_config_hash": fingerprint(config.to_dict()),
               "metadata_only_config_change": ["version"],
               "selection_input_hash": selected["input_hash"],
               "parent_state_fingerprints": checkpoint_manifest["state_fingerprints"]}
    return parent, checkpoint, checkpoint_manifest, selected, banks, receipt


def import_parent(config, costs, checkpoint, manifest):
    # Locally generated, hash-verified trusted artifacts; never arbitrary pickle input.
    with (checkpoint / "collector_and_rng.pkl").open("rb") as handle:
        state = pickle.load(handle)
    original_config = Config(**state["config"])
    original_config.validate()
    if (fingerprint(original_config.to_dict()) != manifest["config_hash"]
            or dict(original_config.to_dict(), version=config.version) != config.to_dict()):
        raise RuntimeError("Parent collector configuration mismatch.")
    model = AuditedSAC.load(checkpoint / "model.zip", device=config.device)
    model.load_replay_buffer(checkpoint / "replay.pkl")
    attach_logger(model)
    engine = Engine(config, costs, model=model)
    engine.restore_boundary_state(state["collector"])
    restore_rng(state["rng"])
    if engine.fingerprints() != manifest["state_fingerprints"]:
        engine.close()
        raise RuntimeError("Cross-version import changed the complete parent learning state.")
    return engine


def reset_plan(plan, banks):
    evaluation_seeds = {e["seed"] for entries in banks.values() for e in entries}
    seen = set()
    rows = []
    max_visits = 5 * (plan.steps_per_branch // plan.block_steps)
    for repeat in plan.repeat_seeds:
        for task_index, task in enumerate(TASKS):
            for visit in range(max_visits):
                seed = derived_seed(repeat, 20, task_index, visit)
                if seed in seen or seed in evaluation_seeds:
                    raise RuntimeError("Continuation reset streams overlap each other or evaluation.")
                seen.add(seed)
                rows.append({"repeat_seed": repeat, "task": task, "task_visit": visit,
                             "reset_seed": seed})
    return rows


def verify_evidence(path, config, runner=False):
    path = path.resolve()
    if not path.is_relative_to((ROOT / "results").resolve()):
        raise ValueError("Validation evidence must belong to this independent version.")
    result_file = "run_summary.json" if runner else "preflight.json"
    result = read_json(path / result_file)
    manifest = read_json(path / "run_manifest.json")
    if runner:
        passed = (result["status"] == "completed" and result["stage"] == "branch_runner_validation"
                  and result["branches_completed"] == 5 and result["additional_training_steps"] == 20000
                  and result["outcome_bank_episodes_evaluated"] == 0)
    else:
        passed = result["status"] == "passed" and result["checks_passed"] == result["checks_planned"] == 10
    if (not passed or manifest["source_hashes"] != source_hashes()
            or manifest["packages"] != package_versions()
            or manifest["config_hash"] != fingerprint(config.to_dict())):
        raise RuntimeError("Successful validation for the exact current code/config/runtime is required.")
    return {"path": path.relative_to(ROOT).as_posix(),
            "result_hash": file_sha256(path / result_file),
            "manifest_hash": file_sha256(path / "run_manifest.json")}
