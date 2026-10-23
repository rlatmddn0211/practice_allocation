"""Zero-environment contract checks with immutable source snapshots."""
import ast
import hashlib
import importlib.metadata
import json
import shutil
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def dump(path, value):
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    out = HERE / "results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_static_" + uuid.uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    snapshots = [p for p in HERE.iterdir() if p.is_file() and p.suffix in {".py", ".ps1", ".md", ".json", ".txt"}]
    for directory in ("practice_allocation", "configs", "inputs"):
        snapshots.extend(p for p in (HERE / directory).rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    source_hashes = {}
    for path in snapshots:
        relative = path.relative_to(HERE)
        target = out / "source_snapshot" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        source_hashes[relative.as_posix()] = digest(path)
    dump(out / "source_hashes.json", source_hashes)
    checks, started, success = [], time.perf_counter(), False

    def check(name, passed):
        checks.append({"name": name, "passed": bool(passed)})
        if not passed:
            raise AssertionError(name)

    try:
        for path in snapshots:
            if path.suffix == ".py":
                ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
                check("syntax:" + str(path.relative_to(HERE)), True)
        # Import only after all current code and inputs have a retained snapshot.
        from common import frozen_inputs
        from practice_allocation.core import package_versions
        protocol, states = frozen_inputs()
        scientific = json.loads((HERE / "inputs/protocol58.json").read_text(encoding="utf-8"))
        check("20_jobs_and_10_original_states", len(states) == 20 and len({(s["parent"], s["prefix_continuation"]) for s in states}) == 10)
        check("2_futures_per_state", all(sum(s["parent"] == p and s["prefix_continuation"] == r for s in states) == 2 for p in range(41011, 41016) for r in (4201, 4202)))
        for field, scientific_key in [("training_steps_total", "training_steps"), ("evaluation_cap_total", "evaluation_step_cap"), ("total_environment_cap", "including_technical_cap")]:
            check("frozen_budget:" + field, protocol[field] == scientific["budget_proposal"][scientific_key])
        check("checkpoints_unchanged", protocol["full_checkpoint_absolute_steps"] == scientific["learning_proposal"]["full_save_absolute_steps"])
        check("technical_reserve_within_cap", protocol["technical_plan"]["maximum_first_technical_run_steps"] == 7000 <= protocol["technical_environment_cap_all_attempts"] == 10000)
        check("single_worker_and_no_retry", protocol["automatic_retry_reserve"] == 0 and protocol["max_parallel_workers"] == 1)
        old = HERE.parent / "52_same_state_future_replication_v1"
        for path in (HERE / "practice_allocation").glob("*.py"):
            check("learner_code_byte_identical:" + path.name, digest(path) == digest(old / "practice_allocation" / path.name))
        for path in (HERE / "configs").glob("*.json"):
            check("copied_config_unchanged:" + path.name, digest(path) == digest(old / "configs" / path.name))
        check("models_and_thresholds_not_refitted", "fixed_predictions_sha256" in protocol and scientific["models"]["M1_shrinkage"] == 0.25 and scientific["proposed_investment_gate"]["G_Brier_minimum"] == 0.001)
        import numpy as np
        canonical = [(p, r, f) for p in range(41011, 41016) for r in (4201, 4202) for f in (3, 4)]
        expected_order = [canonical[int(i)] for i in np.random.default_rng(570101).permutation(20)]
        check("independent_frozen_job_order", [(s["parent"], s["prefix_continuation"], s["future_id"]) for s in states] == expected_order)
        reserve_bytes = max(10 * 1024 ** 3, sum(json.loads((Path(s["checkpoint"]["path"]) / "checkpoint_manifest.json").read_text(encoding="utf-8"))["bytes"] for s in states) * 6)
        free = shutil.disk_usage(HERE).free
        check("storage_for_80_checkpoints_plus_margin", free >= reserve_bytes)
        dump(out / "COMPLETE.json", {"status": "passed_zero_environment_contract_check", "checks": len(checks), "new_environment_steps": 0, "source_hashes": source_hashes, "packages": package_versions(), "python": sys.version, "free_disk_bytes": free, "storage_reserved_bytes": reserve_bytes, "first_job": {k: states[0][k] for k in ("parent", "prefix_continuation", "future_id", "proposed_new_future_root_seed")}})
        success = True
        print(json.dumps({"run": str(out), "checks": len(checks), "free_disk_GiB": free / 1024 ** 3, "reserved_GiB": reserve_bytes / 1024 ** 3, "new_environment_steps": 0}), flush=True)
    except BaseException as exc:
        dump(out / "FAILED.json", {"error": repr(exc), "traceback": traceback.format_exc(), "new_environment_steps": 0})
        traceback.print_exc()
    finally:
        dump(out / "checks.json", checks)
        dump(out / "runtime.json", {"wall_seconds": time.perf_counter() - started, "python": sys.version, "new_environment_steps": 0, "success": success})
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
