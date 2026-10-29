"""Check the first completed retry against its pre-power-loss trajectory."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
JOB = "E3_C_s11_pre160"


def main():
    started = time.perf_counter()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_verify_" + uuid.uuid4().hex[:8]
    output = ROOT / "results" / stamp
    output.mkdir(parents=True, exist_ok=False)
    hashes, checks = {}, []
    for filename in ("recover.py", "verify_resumption.py", "VERSION.json"):
        shutil.copyfile(ROOT / filename, output / filename)

    def sha(path):
        path = Path(path)
        with path.open("rb") as stream:
            value = hashlib.file_digest(stream, "sha256").hexdigest()
        hashes[str(path)] = value
        return value

    def read(path):
        sha(path)
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))

    def rows(path):
        sha(path)
        with Path(path).open(encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))

    def check(name, passed, **evidence):
        checks.append({"name": name, "passed": bool(passed), **evidence})

    try:
        campaign = Path(read(REPO / "13_e0_e3_autonomous_queue_v1/ACTIVE_CAMPAIGN.json")["campaign"])
        first = Path(read(campaign / "attempts" / JOB / "01.json")["output"])
        retry = Path(read(campaign / "attempts" / JOB / "02.json")["output"])
        marker = read(campaign / "completed" / (JOB + ".json"))
        result = read(retry / "result.json")
        check("retry_is_distinct_and_first_attempt_retained", retry != first and (first / "train_metrics.csv").is_file())
        check("completed_marker_identifies_retry", Path(marker["result_ref"]["path"]) == retry / "result.json"
              and marker["result_ref"]["sha256"] == sha(retry / "result.json"))
        first_request, retry_request = read(first / "request.json"), read(retry / "request.json")
        first_request.pop("output")
        retry_request.pop("output")
        check("request_identical_except_new_output_directory", first_request == retry_request)
        check("same_runtime_configuration",
              read(first / "runtime.json")["config"] == read(retry / "runtime.json")["config"])

        compared = {}
        for filename in ("train_metrics.csv", "train_episodes.csv", "training_reset_audit.csv"):
            before, after = rows(first / filename), rows(retry / filename)
            excluded = {"segment_seconds"} if filename == "train_metrics.csv" else set()
            clean = lambda values: [{key: value for key, value in row.items() if key not in excluded} for row in values]
            old = clean(before)
            new = clean(after[:len(before)])
            differences = [{"row": index, "columns": [key for key in left if left.get(key) != right.get(key)]}
                           for index, (left, right) in enumerate(zip(old, new), 1) if left != right]
            check("identical_interrupted_prefix_" + filename, bool(before) and len(after) >= len(before) and old == new,
                  compared_rows=len(before), excluded_columns=sorted(excluded), differences=differences[:10])
            compared[filename] = {"old_rows": len(before), "retry_rows": len(after)}

        costs = read(retry / "costs.json")
        manifest_path = Path(result["checkpoint"]["path"]) / "checkpoint_manifest.json"
        manifest = read(manifest_path)
        check("successful_exact_20k_training_budget", costs["success"] and costs["costs"]["environment_steps"] == 20000
              and costs["costs"]["train_iterations"] == 20000 and costs["costs"]["evaluation_episodes"] == 0)
        check("checkpoint_at_160k_with_no_repeated_warmup", result["step"] == manifest["step"] == 160000 and manifest["updates"] == 159000)
        check("checkpoint_manifest_hash", sha(manifest_path) == result["checkpoint"]["manifest_sha256"])
        for filename, expected in manifest["files"].items():
            check("checkpoint_payload_" + filename, sha(manifest_path.parent / filename) == expected)
        parent_manifest = read(Path(first_request["parent"]["path"]) / "checkpoint_manifest.json")
        check("dependency_versions_unchanged", parent_manifest["packages"] == manifest["packages"])
        check("source_hashes_unchanged", parent_manifest["source_hashes"] == manifest["source_hashes"] == first_request["source_hashes"])
        check("uniform_collection_5k_per_task", result["collected_this_job"] == {name: 5000 for name in ("DO", "PP", "PU", "BP")})
        metrics = rows(retry / "train_metrics.csv")
        numeric = ["reward", "actor_loss", "critic_loss", "entropy_loss", "entropy_coefficient",
                   "critic_0_abs_td_error", "critic_1_abs_td_error"]
        check("finite_recorded_training_values", all(math.isfinite(float(row[column])) for row in metrics for column in numeric))
        check("original_attempt_has_no_fabricated_success", not (first / "result.json").exists())
        interruption = read(first / "interruption.json")
        check("power_loss_cost_bounds_preserved", interruption["observed_training_steps_lower_bound"] == 9000
              and interruption["unobserved_training_steps_upper_bound"] == 11000)
        for filename in ("recover.py", "verify_resumption.py", "VERSION.json"):
            sha(output / filename)
        summary = {"observed_at": datetime.now(timezone.utc).isoformat(), "passed": all(item["passed"] for item in checks),
                   "job": JOB, "attempt": 2, "output": str(output), "retry_output": str(retry),
                   "compared_rows": compared, "checks": checks, "checkpoint": result["checkpoint"],
                   "resumed_job_wall_seconds": costs["wall_seconds"], "resumed_job_costs": costs["costs"],
                   "queue_status_observed": read(campaign / "STATUS.json"),
                   "verification_wall_seconds": time.perf_counter() - started,
                   "verification_training_steps": 0, "verification_evaluation_episodes": 0,
                   "python": sys.version, "dependencies": "Python standard library only",
                   "scope": "Technical resumption and deterministic logged-prefix comparison, not evidence of a scientific effect."}
        (output / "verification.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        (output / "input_hashes.json").write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2), flush=True)
        if not summary["passed"]:
            raise RuntimeError("Recovery verification failed; review individual checks.")
    except BaseException as exc:
        (output / "error.json").write_text(json.dumps({"error": str(exc), "traceback": traceback.format_exc(),
                                                      "checks_completed": checks}, indent=2) + "\n", encoding="utf-8")
        raise


if __name__ == "__main__":
    main()
