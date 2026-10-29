"""One-time, explicitly authorized recovery of the 2026-10-10 interruption.

Only mutable queue status is replaced. Completed results, source, checkpoints,
plan, and failed-attempt data are preserved. The frozen v13 CLI runs the work.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import sys
import time
import traceback
import uuid
from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
BASELINE = REPO / "14_power_interruption_audit_v1/results/20261012T052748Z_4be8fe6c"
EXPECTED_JOB = "E3_C_s11_pre160"
EXPECTED_PARENT = "E3_C_s11_pre140"
EXPECTED_PLAN = "ac6cf6ab551622af196f6ac3ceda7da0cf1dbb8571d4b87346653bdf4e3aa720"


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, data):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


@contextmanager
def queue_lock(path):
    import msvcrt
    # Existing one-byte lock only: no creation, truncation, or stale PID removal.
    with Path(path).open("r+b") as stream:
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def validate(campaign, output):
    baseline = read(BASELINE / "audit.json")
    observed = read(BASELINE / "input_hashes.json")
    require(not baseline["failures"] and baseline["completed_jobs_form_prefix"], "Baseline audit did not pass.")
    require(Path(baseline["campaign"]).resolve() == campaign, "Campaign differs from the inspected campaign.")
    require(sha(campaign / "plan.json") == EXPECTED_PLAN, "Frozen plan changed.")
    require(read(campaign / "plan_integrity.json")["sha256"] == EXPECTED_PLAN, "Frozen plan integrity record changed.")
    state = read(campaign / "STATUS.json")
    require(state == baseline["status"], "Queue status changed; inspect it instead of resetting it.")
    require(state["state"] == "integrity_failed" and state.get("error") == "JSONDecodeError",
            "This recovery is only for the audited JSON-read failure.")
    require(not (campaign / "STOP_AFTER_JOB").exists(), "A user stop marker exists.")

    mismatches = []
    for index, (path, metadata) in enumerate(observed.items(), 1):
        try:
            if sha(path) != metadata["sha256"]:
                mismatches.append({"path": path, "reason": "sha256 changed"})
        except OSError as exc:
            mismatches.append({"path": path, "reason": str(exc)})
        if index % 2000 == 0:
            print(f"Verified {index}/{len(observed)} persisted files", flush=True)
    write(output / "hash_verification.json", {"at": now(), "files_checked": len(observed), "mismatches": mismatches})
    require(not mismatches, "Persisted evidence differs from the completed audit; recovery refused.")

    plan = read(campaign / "plan.json")
    markers = {path.stem: read(path) for path in (campaign / "completed").glob("*.json")}
    require(len(markers) == 646 and len(plan["jobs"]) == 1051, "Unexpected completion or plan count.")
    require(set(markers) == {job["id"] for job in plan["jobs"][:646]}, "Completed jobs are not the frozen plan prefix.")
    job = plan["jobs"][646]
    require(job["id"] == EXPECTED_JOB and job["parent"]["from_job"] == EXPECTED_PARENT, "Wrong pending job or parent.")
    require((job["suite"], job["original_seed"], job["start_step"], job["steps"]) == ("C", 11, 140000, 20000),
            "Unexpected task composition, seed, or training budget.")
    identity = read(campaign / "attempts" / EXPECTED_JOB / "01.json")
    failed_output = Path(identity["output"])
    require(len(list((campaign / "attempts" / EXPECTED_JOB).glob("*.json"))) == 1, "Retry state has changed.")
    require(not (failed_output / "result.json").exists(), "Interrupted attempt now has a result.")
    require(not (failed_output / "checkpoint").exists(), "Interrupted attempt has an unexpected checkpoint.")
    parent = read(markers[EXPECTED_PARENT]["result_ref"]["path"])
    manifest = read(Path(parent["checkpoint"]["path"]) / "checkpoint_manifest.json")
    require(parent["step"] == manifest["step"] == 140000, "Parent step mismatch.")
    with (failed_output / "train_metrics.csv").open(encoding="utf-8", newline="") as stream:
        last_logged_step = max(int(row["step"]) for row in csv.DictReader(stream))
    require(last_logged_step == 149000, "Interrupted prefix changed.")
    disk = {name: shutil.disk_usage(path)._asdict() for name, path in {"workspace": ROOT, "results": plan["storage_root"]}.items()}
    require(disk["results"]["free"] >= plan["minimum_free_bytes"], "Results drive is below the frozen free-space threshold.")
    require(disk["workspace"]["free"] >= 500_000_000, "Insufficient space to preserve recovery records.")
    import psutil
    try:
        old_process = psutil.Process(identity["pid"])
        same_worker = old_process.is_running() and abs(old_process.create_time() - identity["process_created"]) < .01
    except psutil.Error:
        same_worker = False
    require(not same_worker, "Original worker is still alive.")

    record = {"validated_at": now(), "ready": True, "campaign": str(campaign),
              "baseline_audit": {"path": str(BASELINE / "audit.json"), "sha256": sha(BASELINE / "audit.json")},
              "baseline_input_manifest": {"path": str(BASELINE / "input_hashes.json"), "sha256": sha(BASELINE / "input_hashes.json")},
              "files_reverified": len(observed), "completed_jobs_preserved": len(markers),
              "remaining_jobs": 405, "next_job": job, "parent_checkpoint": parent["checkpoint"],
              "parent_packages": manifest["packages"], "interrupted_attempt": identity,
              "interrupted_logged_step": last_logged_step, "disk": disk,
              "reason": "User explicitly requested resumption on 2026-10-12 after a complete integrity audit.",
              "root_cause_limit": "The original JSON-read failure had no file path or retained original status; no data corruption is inferred.",
              "source_sha256": sha(__file__)}
    write(output / "validation.json", record)
    return record, state, failed_output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["check", "resume"])
    parser.add_argument("--check-report", type=Path)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + args.command + "_" + uuid.uuid4().hex[:8]
    output = ROOT / "results" / stamp
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(__file__, output / "recovery_source.py")
    started = time.perf_counter()
    write(output / "runtime.json", {"started_at": now(), "command": args.command,
          "python": sys.version, "executable": sys.executable, "platform": platform.platform(),
          "dependencies": {"psutil": importlib.metadata.version("psutil")},
          "source_sha256": sha(__file__), "training_steps": 0, "evaluation_episodes": 0})
    campaign = Path(read(REPO / "13_e0_e3_autonomous_queue_v1/ACTIVE_CAMPAIGN.json")["campaign"]).resolve()
    try:
        with ExitStack() as locks:
            if args.command == "resume":
                require(args.check_report is not None, "A successful check report is required before activation.")
                previous_check = read(args.check_report)
                require(previous_check["ready"] and previous_check["source_sha256"] == sha(__file__), "Check does not cover this recovery source.")
                require(Path(previous_check["campaign"]).resolve() == campaign, "Check belongs to another campaign.")
                locks.enter_context(queue_lock(campaign / "controller.lock"))
                locks.enter_context(queue_lock(campaign / "worker.lock"))
            record, old_status, failed_output = validate(campaign, output)
            if args.command == "resume":
                # Retain the exact prior status before replacing the mutable status file.
                shutil.copyfile(campaign / "STATUS.json", output / "previous_STATUS.json")
                interruption = failed_output / "interruption.json"
                require(not interruption.exists(), "An interruption record appeared; inspect it before activation.")
                write(interruption, {
                    "detected_at": now(), "error": {"type": "InterruptedProcess", "retryable": True,
                    "message": "Unexpected PC shutdown; the 140k-to-160k attempt was not checkpointed."},
                    "observed_training_steps_lower_bound": 9000,
                    "unobserved_training_steps_upper_bound": 11000,
                    "evaluation_cost_may_be_incomplete": False,
                    "bound_reason": "Power loss can discard buffered CSV records; upper bound is the remainder of this 20k atomic job, not one logging interval.",
                    "recovery_validation": str(output / "validation.json")})
                fresh_status = {"state": "recovery_prepared", "time": now(), "completed_jobs": 646,
                                "total_jobs": 1051, "next_job": EXPECTED_JOB,
                                "recovery_validation": str(output / "validation.json"),
                                "previous_status": {"path": str(output / "previous_STATUS.json"), "sha256": sha(output / "previous_STATUS.json")}}
                write(output / "activation_intent.json", fresh_status)
                with (campaign / "events.jsonl").open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps({"time": now(), "event": "manual_recovery_authorized",
                                             "job": EXPECTED_JOB, "validation": str(output / "validation.json"),
                                             "status_backup": str(output / "previous_STATUS.json")}) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                temporary_status = campaign / ("STATUS.recovery_" + uuid.uuid4().hex + ".tmp")
                write(temporary_status, fresh_status)
                os.replace(temporary_status, campaign / "STATUS.json")
            summary = {"completed_at": now(), "passed": True, "command": args.command,
                       "activated": args.command == "resume", "output": str(output),
                       "validation": str(output / "validation.json"), "next_job": EXPECTED_JOB,
                       "parent_step": 140000, "files_checked": record["files_reverified"],
                       "wall_seconds": time.perf_counter() - started,
                       "training_steps": 0, "evaluation_episodes": 0}
            write(output / "result.json", summary)
            print(json.dumps(summary, indent=2), flush=True)
    except BaseException as exc:
        write(output / "error.json", {"at": now(), "type": type(exc).__name__, "message": str(exc),
                                      "traceback": traceback.format_exc(), "wall_seconds": time.perf_counter() - started})
        raise


if __name__ == "__main__":
    main()
