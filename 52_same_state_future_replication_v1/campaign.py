"""Run exactly ten frozen futures, sequentially, without automatic retry."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

from common import (
    ROOT, REPOSITORY, unique, atomic, reference, checked, frozen_inputs,
    config_for, verify_input_files)
from practice_allocation.core import source_hashes, write_json, utc_now
from practice_allocation.study_io import IntegrityError, source_snapshot, read_json


def prepare(verification):
    out = unique(ROOT/"results", "future_replication")
    source_snapshot(out)
    start = time.perf_counter()
    try:
        protocol, states = frozen_inputs()
        verified_path = Path(verification).resolve()
        verified = read_json(verified_path/"VERIFIED.json")
        summary = read_json(checked(verified["summary"]))
        if (verified["source_hashes"] != source_hashes()
                or summary["source_hashes"] != source_hashes()
                or summary["status"] != "passed" or summary["failed_checks"]):
            raise IntegrityError("Technical verification does not certify this source state")
        technical_costs = []
        for path in sorted((ROOT/"results").glob("*_technical_*/costs.json")):
            technical_costs.append({"reference": reference(path), **read_json(path)})
        technical_steps = sum(c["costs"]["environment_steps"] for c in technical_costs)
        if technical_steps > 10000:
            raise IntegrityError("Technical budget exceeded")
        # Reserve room for 40 full checkpoints, using actual input sizes.
        sizes = [read_json(Path(s["checkpoint"]["path"])/"checkpoint_manifest.json")["bytes"] for s in states]
        storage_reserve = max(10*1024**3, sum(sizes)*6)
        if shutil.disk_usage(out).free < storage_reserve:
            raise IntegrityError("Insufficient checkpoint disk space")
        jobs = []
        for s in states:
            config_for(s)
            verify_input_files(s)
            jobs.append({"id": f"B_s{s['parent']}_r{s['prefix_continuation']}_new_future",
                         "state": s})
        plan = {
            "created_at": utc_now(), "version": "52_same_state_future_replication_v1",
            "source_hashes": source_hashes(), "protocol": protocol,
            "verification": reference(verified_path/"VERIFIED.json"),
            "technical_costs": technical_costs, "technical_steps": technical_steps,
            "storage_reserved_bytes": storage_reserve, "jobs": jobs,
            "research_training_cap": 320000, "research_evaluation_cap": 2000000,
            "fixed_choice_table": reference(ROOT/"inputs/fixed_choices.csv"),
            "no_adaptive_scheduling": True}
        write_json(out/"plan.json", plan)
        write_json(out/"plan_integrity.json", reference(out/"plan.json"))
        for name in ("completed", "jobs", "launches"):
            (out/name).mkdir()
        atomic(out/"STATUS.json", {
            "status": "prepared", "completed": 0, "total": 10, "updated_at": utc_now(),
            "training_step_cap": 320000, "evaluation_step_cap": 2000000,
            "technical_steps": technical_steps})
        atomic(ROOT/"ACTIVE_CAMPAIGN.json", {"campaign": str(out), "created_at": utc_now()})
        write_json(out/"preparation_costs.json", {"new_environment_steps": 0,
                                                 "wall_seconds": time.perf_counter()-start})
        print(json.dumps({"campaign": str(out), "jobs": 10,
                          "technical_steps": technical_steps, "source_frozen": True}), flush=True)
    except BaseException as exc:
        write_json(out/"preparation_error.json", {"error": str(exc), "traceback": traceback.format_exc(),
                                                 "new_environment_steps": 0})
        raise


def last_progress(attempt):
    path = attempt/"progress.jsonl"
    if not path.exists():
        return None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        return json.loads(lines[-1]) if lines else None
    except (OSError, json.JSONDecodeError):
        return None


def run_campaign(cam):
    import msvcrt
    cam = Path(cam).resolve()
    lock = (cam/"controller.lock").open("a+b")
    if lock.tell() == 0:
        lock.write(b"0")
        lock.flush()
    lock.seek(0)
    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    child = None
    try:
        plan = read_json(checked(read_json(cam/"plan_integrity.json")))
        if source_hashes() != plan["source_hashes"]:
            raise IntegrityError("Frozen controller source changed")
        if (cam/"COMPLETE.json").exists():
            print("Completed campaign; nothing to run.", flush=True)
            return 0
        for job in plan["jobs"]:
            if list((cam/"jobs"/job["id"]).glob("*")) and not (cam/"completed"/(job["id"]+".json")).exists():
                raise IntegrityError("Incomplete attempt preserved; automatic retry forbidden: "+job["id"])
        start = time.perf_counter()
        completed = []
        for job in plan["jobs"]:
            marker_path = cam/"completed"/(job["id"]+".json")
            if marker_path.exists():
                marker = read_json(marker_path)
                completed.append({"job": job["id"], "result": read_json(checked(marker["result"])),
                                  "costs": read_json(checked(marker["costs"]))})
                continue
            attempt = unique(cam/"jobs"/job["id"], "attempt")
            q = {**job, "output": str(attempt), "source_hashes": plan["source_hashes"]}
            write_json(attempt/"request.json", q)
            env = dict(os.environ)
            env.update(PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", OMP_NUM_THREADS="1",
                       MKL_NUM_THREADS="1", PRACTICE_SUITE="B", CUBLAS_WORKSPACE_CONFIG=":4096:8")
            with (attempt/"stdout.log").open("x", encoding="utf-8") as stdout, \
                    (attempt/"stderr.log").open("x", encoding="utf-8") as stderr:
                child = subprocess.Popen(
                    [sys.executable, "-u", "-B", str(cam/"source_snapshot/worker.py"),
                     "--request", str(attempt/"request.json")],
                    cwd=REPOSITORY, env=env, stdout=stdout, stderr=stderr,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                write_json(attempt/"process.json", {"pid": child.pid, "started_at": utc_now()})
                while child.poll() is None:
                    progress = last_progress(attempt)
                    atomic(cam/"STATUS.json", {
                        "status": "running", "updated_at": utc_now(), "completed": len(completed), "total": 10,
                        "running": {"job": job["id"], "pid": child.pid, "attempt": str(attempt),
                                    "latest": progress},
                        "research_training_steps_completed": sum(e["costs"]["training_steps"] for e in completed),
                        "research_evaluation_steps_completed": sum(e["costs"]["evaluation_steps"] for e in completed),
                        "technical_steps": plan["technical_steps"],
                        "elapsed_seconds": time.perf_counter()-start,
                        "pending": [j["id"] for j in plan["jobs"][len(completed)+1:]]})
                    time.sleep(3)
                if child.returncode != 0 or not (attempt/"result.json").exists():
                    raise IntegrityError("Worker failed; preserved attempt: "+str(attempt))
            cost, result = read_json(attempt/"costs.json"), read_json(attempt/"result.json")
            if cost["status"] != "completed" or cost["training_steps"] != 32000 or cost["evaluation_steps"] > 200000:
                raise IntegrityError("Worker cost or completion integrity failed")
            if not result["fork_verified"] or not result["evaluation_state_unchanged"]:
                raise IntegrityError("Full-state integrity failed")
            checked(result["episodes"])
            write_json(marker_path, {"completed_at": utc_now(), "attempt": str(attempt),
                                     "result": reference(attempt/"result.json"),
                                     "costs": reference(attempt/"costs.json")})
            completed.append({"job": job["id"], "result": result, "costs": cost})
            child = None
        train = sum(e["costs"]["training_steps"] for e in completed)
        evaluation = sum(e["costs"]["evaluation_steps"] for e in completed)
        if len(completed) != 10 or train != 320000 or evaluation > 2000000:
            raise IntegrityError("Campaign total budget mismatch")
        summary = {
            "execution_status": "completed", "completed_at": utc_now(),
            "states": 10, "parents": 5, "new_futures_per_state": 1,
            "research_training_steps": train, "research_evaluation_steps": evaluation,
            "technical_environment_steps_all_attempts": plan["technical_steps"],
            "total_environment_steps": train+evaluation+plan["technical_steps"],
            "source_hashes": plan["source_hashes"], "verification": plan["verification"],
            "results": completed, "scientific_conclusion": "pending frozen-protocol analysis",
            "C_original_stages_2_3": "held_not_scheduled"}
        write_json(cam/"completion_summary.json", summary)
        write_json(cam/"COMPLETE.json", {"summary": reference(cam/"completion_summary.json")})
        atomic(cam/"STATUS.json", {"status": "completed", "completed": 10, "total": 10,
                                   "updated_at": utc_now(), "training_steps": train,
                                   "evaluation_steps": evaluation, "technical_steps": plan["technical_steps"]})
        print(json.dumps({k: v for k, v in summary.items() if k not in ("results", "source_hashes")}), flush=True)
        return 0
    except BaseException as exc:
        # There is one worker only. Preserve a still-running worker's identity if
        # controller failure occurs; never silently spawn a replacement.
        failure = {"status": "failed", "time": utc_now(), "error": str(exc),
                   "traceback": traceback.format_exc(),
                   "worker_pid": child.pid if child and child.poll() is None else None}
        failure_path = cam/("failure_"+str(time.time_ns())+".json")
        write_json(failure_path, failure)
        atomic(cam/"STATUS.json", failure)
        traceback.print_exc()
        return 1
    finally:
        lock.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=("prepare", "run"))
    ap.add_argument("--verification")
    ap.add_argument("--campaign")
    args = ap.parse_args()
    if args.command == "prepare":
        if not args.verification:
            ap.error("prepare requires --verification")
        prepare(args.verification)
        return 0
    if not args.campaign:
        ap.error("run requires --campaign")
    return run_campaign(args.campaign)


if __name__ == "__main__":
    raise SystemExit(main())
