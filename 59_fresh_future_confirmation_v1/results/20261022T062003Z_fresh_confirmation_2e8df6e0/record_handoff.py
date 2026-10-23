"""Read-only launch validation, retaining a timestamped status/source receipt."""
import hashlib
import json
import shutil
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

CAMPAIGN = Path(__file__).resolve().parent
IMPLEMENTATION = CAMPAIGN.parent.parent
REPO = IMPLEMENTATION.parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, value):
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def main():
    out = CAMPAIGN / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_handoff_" + uuid.uuid4().hex[:8])
    out.mkdir(exist_ok=False)
    (out / "source_snapshot").mkdir()
    (out / "input_snapshot").mkdir()
    shutil.copy2(__file__, out / "source_snapshot" / "record_handoff.py")
    write(out / "source_hashes.json", {"record_handoff.py": sha(__file__)})
    checks, inputs, start = [], [], time.perf_counter()

    def check(label, condition):
        checks.append({"name": label, "passed": bool(condition)})
        if not condition:
            raise AssertionError(label)

    def capture(path):
        path = Path(path)
        content = path.read_bytes()
        target = out / "input_snapshot" / (str(len(inputs)).zfill(2) + "_" + path.name)
        with target.open("xb") as handle:
            handle.write(content)
        inputs.append({"source": str(path), "snapshot": target.name, "sha256": hashlib.sha256(content).hexdigest()})
        return json.loads(content.decode("utf-8-sig")) if path.suffix == ".json" else content

    success = False
    try:
        plan = capture(CAMPAIGN / "plan.json")
        status = capture(CAMPAIGN / "STATUS.json")
        check("campaign_running", status["status"] == "running" and status["total"] == 20)
        for key, expected in plan["source_hashes"].items():
            check("frozen_live_source:" + key, sha(IMPLEMENTATION / key) == expected)
            check("frozen_campaign_snapshot:" + key, sha(CAMPAIGN / "source_snapshot" / key) == expected)
        technical_path = Path(plan["verification"]["path"])
        check("technical_receipt_hash", sha(technical_path) == plan["verification"]["sha256"])
        technical = capture(technical_path.parent / "summary.json")
        costs = capture(technical_path.parent / "costs.json")
        check("technical68_passed", technical["status"] == "passed" and technical["checks"] == 68 and not technical["failed_checks"])
        check("actual_technical_cost", costs["costs"]["environment_steps"] == plan["technical_steps"] == 6516)
        check("total_upper_with_actual_technical", plan["research_training_cap"] + plan["research_evaluation_cap"] + plan["technical_steps"] == 4646516 <= 4650000)
        attempt = Path(status["running"]["attempt"])
        started = capture(attempt / "research_start_integrity.json")
        fork = capture(attempt / "fork_integrity.json")
        progress_bytes = capture(attempt / "progress.jsonl")
        latest = json.loads(progress_bytes.decode("utf-8").splitlines()[-1])
        check("fresh_original208k_zero_cost_start", started["absolute_step"] == 208000 and started["environment_steps_before_fork"] == 0 and started["independent_of_technical_rollouts"])
        check("only_future_rng_changed", fork["preserved_before"] == fork["preserved_after"] and all(fork["global_streams_changed"].values()) and fork["schedule_rng_changed"])
        check("actual_training_begun", latest["costs"]["train_iterations"] > 0 and latest["absolute_step"] > 208000)
        check("no_worker_error", not (attempt / "error.json").exists())
        capture(CAMPAIGN / "execution_start_ko.md")
        capture(REPO / "README.md")
        capture(REPO / "AGENTS.md")
        receipt = {"status": "running_launch_validated", "campaign": str(CAMPAIGN), "scientific_conclusion": "not_yet_measured", "technical_checks": 68, "technical_environment_steps": 6516, "completed_jobs_at_read": status["completed"], "running_job": status["running"]["job"], "latest_worker_progress": latest, "operational_policy_block": "First PS launch blocked before script execution; approved process-scoped launch succeeded; zero research retries", "new_environment_steps_for_this_check": 0}
        write(out / "COMPLETE.json", receipt)
        success = True
        print(json.dumps({"handoff": str(out), "job": status["running"]["job"], "observed_training_steps": latest["costs"]["train_iterations"], "checks": len(checks), "new_environment_steps": 0}), flush=True)
    except BaseException as exc:
        write(out / "FAILED.json", {"error": repr(exc), "traceback": traceback.format_exc(), "new_environment_steps": 0})
        traceback.print_exc()
    finally:
        write(out / "inputs.json", inputs)
        write(out / "checks.json", checks)
        write(out / "runtime.json", {"success": success, "wall_seconds": time.perf_counter() - start, "python": sys.version, "new_environment_steps": 0})
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
