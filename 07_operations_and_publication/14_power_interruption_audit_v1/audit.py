"""Read-only interruption audit; never starts or repairs an experiment."""
from __future__ import annotations

import csv
import hashlib
import json
import platform
import shutil
import sys
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
STAGES = {
    "E0": "09_fresh_evaluation_audit_v1",
    "E1": "10_independent_seed_checkpoint_study_v1",
    "E2": "11_fixed_target_donor_swap_v1",
    "E3": "12_task_composition_study_v1",
}


def main():
    started = time.perf_counter()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "results" / (stamp + "_" + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(__file__, output / "audit_source.py")
    files, failures, json_cache = {}, [], {}

    def digest(path):
        path = Path(path)
        stat = path.stat()
        with path.open("rb") as stream:
            value = hashlib.file_digest(stream, "sha256").hexdigest()
        files[str(path)] = {"sha256": value, "bytes": stat.st_size,
                            "mtime_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()}
        return value

    def read(path):
        path = Path(path)
        if str(path) in json_cache:
            return json_cache[str(path)]
        digest(path)
        try:
            value = json.loads(path.read_text(encoding="utf-8-sig"))
        except (ValueError, UnicodeError) as exc:
            failures.append({"check": "json_parse", "path": str(path), "error": str(exc)})
            value = None
        json_cache[str(path)] = value
        return value

    def check_hash(path, expected, label):
        try:
            actual = digest(path)
            if actual != expected:
                failures.append({"check": label, "path": str(path), "expected": expected, "actual": actual})
        except OSError as exc:
            failures.append({"check": label, "path": str(path), "error": str(exc)})

    campaign = Path(read(REPO / "13_e0_e3_autonomous_queue_v1" / "ACTIVE_CAMPAIGN.json")["campaign"])
    plan = read(campaign / "plan.json")
    check_hash(campaign / "plan.json", read(campaign / "plan_integrity.json")["sha256"], "frozen_plan")
    status_before = read(campaign / "STATUS.json")
    for stage, mapping in plan["sources"].items():
        for relative, expected in mapping.items():
            check_hash(REPO / STAGES[stage] / relative, expected, "frozen_stage_source")
    for relative, expected in plan["controller_sources"].items():
        check_hash(REPO / "13_e0_e3_autonomous_queue_v1" / relative, expected, "frozen_controller_source")

    stats = {stage: {"completed_jobs": 0, "training_steps": 0, "evaluation_episodes": 0,
                     "completed_40k_branch_training": 0, "worker_wall_seconds": 0.0,
                     "planned": plan["counts"][stage]} for stage in STAGES}
    completed, checkpoint_count, checkpoint_file_count = {}, 0, 0
    pretraining = {}
    for marker_path in sorted((campaign / "completed").glob("*.json")):
        marker = read(marker_path)
        if marker is None:
            continue
        result_path = Path(marker["result_ref"]["path"])
        check_hash(result_path, marker["result_ref"]["sha256"], "completed_result")
        result = read(result_path)
        if result is None:
            continue
        completed[marker["id"]] = {"marker": marker, "result": result}
        stage = stats[result["stage"]]
        stage["completed_jobs"] += 1
        costs = read(result_path.parent / "costs.json")
        if costs:
            stage["evaluation_episodes"] += costs["costs"]["evaluation_episodes"]
            stage["worker_wall_seconds"] += costs["wall_seconds"]
            if result["kind"] == "train":
                stage["training_steps"] += costs["costs"]["environment_steps"]
        if result["kind"] == "train" and result.get("horizon") == 40000:
            stage["completed_40k_branch_training"] += 1
        if "_pre" in marker["id"]:
            key = f'{result["stage"]}_{result["suite"]}_seed{result["original_seed"]}'
            pretraining[key] = max(pretraining.get(key, 0), result["step"])
        if "episodes_path" in result:
            check_hash(result["episodes_path"], result["episodes_sha256"], "evaluation_csv")
        if "checkpoint" in result:
            checkpoint = Path(result["checkpoint"]["path"])
            manifest_path = checkpoint / "checkpoint_manifest.json"
            check_hash(manifest_path, result["checkpoint"]["manifest_sha256"], "checkpoint_manifest")
            manifest = read(manifest_path)
            if manifest:
                checkpoint_count += 1
                for filename, expected in manifest["files"].items():
                    check_hash(checkpoint / filename, expected, "checkpoint_payload")
                    checkpoint_file_count += 1
        if len(completed) % 100 == 0:
            print(f"Audited {len(completed)} completed jobs", flush=True)

    events_path = campaign / "events.jsonl"
    digest(events_path)
    events = []
    for line_number, line in enumerate(events_path.read_text(encoding="utf-8-sig").splitlines(), 1):
        try:
            events.append(json.loads(line))
        except ValueError as exc:
            failures.append({"check": "event_parse", "line": line_number, "error": str(exc)})
    attempts = list((campaign / "attempts").glob("*/*.json"))
    intents = list((campaign / "attempts").glob("*/*.launch_intent"))
    output_paths = {Path(event["output"]) for event in events if event.get("output")}
    for path in attempts + intents:
        data = read(path)
        if data and data.get("output"):
            output_paths.add(Path(data["output"]))
    for directory in sorted(output_paths):
        for path in directory.glob("*.json"):
            read(path)

    remaining = [job for job in plan["jobs"] if job["id"] not in completed]
    first_pending = remaining[0] if remaining else None
    prefix_ok = [job["id"] for job in plan["jobs"][:len(completed)]] == [job["id"] for job in plan["jobs"] if job["id"] in completed]
    incomplete = []
    for event in events:
        if event.get("event") != "job_started" or event["id"] in completed:
            continue
        directory = Path(event["output"])
        record = dict(event)
        record["has_result"] = (directory / "result.json").exists()
        record["has_checkpoint"] = (directory / "checkpoint" / "checkpoint_manifest.json").exists()
        metrics = directory / "train_metrics.csv"
        if metrics.exists():
            digest(metrics)
            with metrics.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            record["last_metric_step"] = max(int(row["step"]) for row in rows)
        progress = directory / "progress.jsonl"
        if progress.exists():
            digest(progress)
            record["progress"] = [json.loads(line) for line in progress.read_text(encoding="utf-8-sig").splitlines()]
        incomplete.append(record)

    report = {
        "observed_at_utc": datetime.now(timezone.utc).isoformat(), "campaign": str(campaign),
        "read_only": True, "status": status_before,
        "completed_jobs": len(completed), "total_jobs": len(plan["jobs"]), "remaining_jobs": len(remaining),
        "completed_jobs_form_prefix": prefix_ok, "stage_progress": stats,
        "pretraining_checkpoint_steps": pretraining,
        "last_completed": max((v["marker"] for v in completed.values()), key=lambda item: item["completed_at"]),
        "first_pending": first_pending, "interrupted_attempts": incomplete,
        "events_by_type": dict(Counter(event.get("event") for event in events)),
        "attempt_records": len(attempts), "checkpoint_manifests_checked": checkpoint_count,
        "checkpoint_payload_files_checked": checkpoint_file_count,
        "json_documents_checked": len(json_cache), "files_hashed": len(files),
        "failures": failures, "audit_wall_seconds": time.perf_counter() - started,
        "runtime": {"python": sys.version, "executable": sys.executable, "platform": platform.platform(),
                    "dependencies": "Python standard library only", "training_steps": 0, "evaluation_episodes": 0},
        "limitations": ["Hashes establish persisted byte integrity, not scientific validity or a live restore test.",
                        "The original STATUS.json overwritten by the controller is not available in this audit.",
                        "Metrics from the interrupted job are a lower bound; volatile buffers may have been lost."],
    }
    report["audit_source_sha256"] = digest(output / "audit_source.py")
    (output / "audit.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output / "input_hashes.json").write_text(json.dumps(files, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"audit_output": str(output), **report}, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
