"""Pinned discovery evidence and frozen hypotheses for new continuation seeds."""

import csv
from pathlib import Path

from .branch_protocol import read_json, reset_plan
from .core import ROOT, TASKS, file_sha256, fingerprint, package_versions


def verify_discovery(config, plan, banks):
    specification = read_json(ROOT / "configs/replication.json")
    directory = (ROOT / specification["run_relative_to_version"]).resolve()
    if not directory.is_relative_to(ROOT.parent.resolve()) or directory.is_relative_to(ROOT):
        raise ValueError("Discovery evidence must come from the frozen earlier version.")
    for name, expected in specification["file_hashes"].items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or file_sha256(directory / relative) != expected:
            raise RuntimeError(f"Pinned discovery artifact changed: {name}")
    result = read_json(directory / "run_summary.json")
    manifest = read_json(directory / "run_manifest.json")
    old_plan = read_json(directory / "execution_plan.json")
    expected_keys = {(seed, candidate) for seed in specification["discovery_seeds"] for candidate in plan.candidates}
    actual_keys = {(b["repeat_seed"], b["candidate"]) for b in result["branches"]}
    if (result["status"] != "completed" or result["stage"] != "p0_allocation_branches"
            or result["original_seed"] != 901 or result["parent_step"] != plan.parent_step
            or result["continuation_seeds"] != [1901, 1902] or len(result["branches"]) != 10
            or result["branches_completed"] != 10 or actual_keys != expected_keys
            or result["additional_training_steps"] != 400000
            or result["costs"]["evaluation_episodes"] != 4200
            or any(b["status"] != "completed" or b["additional_training_steps"] != 40000 for b in result["branches"])):
        raise RuntimeError("Incomplete or inconsistent discovery cohort.")
    if (dict(manifest["config"], version=config.version) != config.to_dict()
            or manifest["packages"] != package_versions()
            or fingerprint(read_json(directory / "evaluation_banks.json")) != fingerprint(banks)):
        raise RuntimeError("Discovery and replication learner/runtime/evaluation conditions differ.")
    if (old_plan["candidates"] != list(plan.candidates) or old_plan["steps_per_branch"] != 40000
            or old_plan["evaluation_steps"] != [20000, 40000]
            or tuple(specification["replication_seeds"]) != plan.repeat_seeds
            or set(plan.repeat_seeds) & set(specification["discovery_seeds"])):
        raise RuntimeError("The prespecified replication allocation or seed plan changed.")
    for name, expected in manifest["source_hashes"].items():
        if (file_sha256(directory.parents[2] / name) != expected
                or file_sha256(directory / "source_snapshot" / name) != expected):
            raise RuntimeError(f"Frozen discovery source changed: {name}")
    old_resets = {row["reset_seed"] for row in read_json(directory / "continuation_reset_plan.json")}
    new_resets = {row["reset_seed"] for row in reset_plan(plan, banks)}
    if old_resets & new_resets:
        raise RuntimeError("Replication reset seeds overlap the discovery cohort.")
    historical_states = set()
    for name in specification["file_hashes"]:
        if name.endswith("training_reset_audit.json"):
            audit = read_json(directory / name)
            if not audit["passed"] or len(audit["episodes"]) != 80:
                raise RuntimeError("Incomplete discovery reset audit.")
            historical_states.update(e["initial_state_hash"] for e in audit["episodes"])
    if len(historical_states) != 400:
        raise RuntimeError("Unexpected number of discovery physical reset states.")
    receipt = {
        "discovery_run": str(directory), "file_hashes": specification["file_hashes"],
        "discovery_seeds": specification["discovery_seeds"], "replication_seeds": list(plan.repeat_seeds),
        "same_learner_config_except_version": True, "same_packages": True, "same_evaluation_bank": True,
        "disjoint_reset_seeds": True, "discovery_reset_cases": len(old_resets),
        "replication_reset_cases": len(new_resets), "discovery_physical_reset_states": len(historical_states),
        "analysis_plan_hash": file_sha256(ROOT / "configs/replication.json"),
    }
    return directory, result, historical_states, receipt, specification


def verify_baseline(replication_output, baseline, discovery_directory, discovery):
    fields = ("success_by_task", "success_counts", "episodes_by_task", "environment_steps")
    if any(baseline[key] != discovery["baseline"][key] for key in fields):
        raise RuntimeError("Same frozen policy/bank failed to reproduce the discovery baseline.")

    def baseline_cases(path):
        with path.open(encoding="utf-8", newline="") as handle:
            rows = [r for r in csv.DictReader(handle) if r["evaluation_id"] == "baseline"]
        cases = {(r["task"], r["initial_state_hash"]): {
            "success": int(r["success"]), "length": int(r["length"]), "return": float(r["return"]),
            "seed": int(r["seed"]), "episode_index": int(r["episode_index"]),
            "bank": r["bank"], "policy_type": r["policy_type"],
        } for r in rows}
        if len(rows) != 200 or len(cases) != 200 or {r["task"] for r in rows} != set(TASKS):
            raise RuntimeError("Baseline has missing or duplicate cases.")
        return cases

    current = baseline_cases(replication_output / "evaluation_episodes.csv")
    historical = baseline_cases(discovery_directory / "evaluation_episodes.csv")
    if current != historical:
        raise RuntimeError("Baseline case-level outcomes differ from discovery.")
    return {"passed": True, "shared_initial_cases": 200, "identical_case_successes": True,
            "identical_functional_result_hash": fingerprint(current), "same_complete_200k_parent": True,
            "comparison_excludes_only_metadata": ["evaluation_id", "context"],
            "note": "The original evaluator hash includes context, which deliberately names the new replication stage."}
