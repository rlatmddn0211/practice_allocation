"""Inventory existing assets and check proposed budgets; no scientific reanalysis."""
import csv
import hashlib
import io
import json
import re
import shutil
import sys
import time
import traceback
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    start = time.perf_counter()
    out = HERE / "results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_design_audit_" + uuid.uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    snap = out / "source_snapshot"
    snap.mkdir()
    for name in ("audit_design.py", "protocol.json", "README.md", "research_plan_ko.md", "feedback_alignment_ko.md", "external_sources.json"):
        shutil.copy2(HERE / name, snap / name)
    checks, inputs, assets = [], {}, []

    def write(name, obj):
        with (out / name).open("x", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)

    def check(name, condition):
        checks.append({"check": name, "passed": bool(condition)})
        if not condition:
            raise AssertionError(name)

    def blob(path, expected=None):
        path = Path(path).resolve()
        data = path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        inputs[str(path)] = sha
        if expected:
            check("hash:" + str(path), sha == expected)
        return data

    def js(path, expected=None):
        return json.loads(blob(path, expected).decode("utf-8-sig"))

    def rows(path, expected=None):
        return list(csv.DictReader(io.StringIO(blob(path, expected).decode("utf-8-sig"))))

    try:
        proposal = js(HERE / "protocol.json")
        js(HERE / "external_sources.json")
        for name in ("README.md", "research_plan_ko.md", "feedback_alignment_ko.md"):
            doc = blob(HERE / name).decode("utf-8-sig")
            for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", doc):
                if target.startswith(("http://", "https://", "#")):
                    continue
                check("local_link:" + name + ":" + target, (HERE / target.split("#", 1)[0]).exists())
        active = js(REPO / "44_selection_value_stage1_checkpoint36_v2" / "ACTIVE_CAMPAIGN.json")
        cam = Path(active["campaign"])
        completion_marker = js(cam / "COMPLETE.json")
        completion = js(completion_marker["summary"]["path"], completion_marker["summary"]["sha256"])
        plan = js(cam / "plan.json", js(cam / "plan_integrity.json")["sha256"])
        check("stage1_complete", completion["execution_status"] == "completed" and len(plan["jobs"]) == 245)
        totals = Counter()
        metric_headers, episode_headers, outcome_headers = set(), set(), set()
        bp8, bp36, future_source = [], [], []
        for job in plan["jobs"]:
            marker = js(cam / "completed" / (job["id"] + ".json"))
            result = js(marker["result_ref"]["path"], marker["result_ref"]["sha256"])
            attempt = Path(marker["attempt"])
            if job["kind"] == "evaluate":
                data = rows(result["episodes_path"], result["episodes_sha256"])
                totals["outcome_files"] += 1
                totals["outcome_rows"] += len(data)
                outcome_headers.add(tuple(data[0]))
                check("400_outcome_rows:" + job["id"], len(data) == 400)
                assets.append({"id": job["id"], "kind": "outcome_csv", "path": result["episodes_path"], "rows": len(data)})
            if job["kind"] != "train":
                continue
            for filename, key, headers in (("train_metrics.csv", "metric", metric_headers), ("train_episodes.csv", "episode", episode_headers)):
                path = attempt / filename
                data = rows(path)
                totals[key + "_files"] += 1
                totals[key + "_rows"] += len(data)
                headers.add(tuple(data[0]))
                assets.append({"id": job["id"], "kind": key + "_csv", "path": str(path), "rows": len(data)})
            if job.get("condition") == "dose625" and job.get("horizon") in (8000, 36000):
                ref = result["checkpoint"]
                cp = Path(ref["path"])
                manifest = js(cp / "checkpoint_manifest.json", ref["manifest_sha256"])
                check("checkpoint_files_exist:" + job["id"], all((cp / name).is_file() for name in manifest["files"]))
                info = {"id": job["id"], "original_seed": job["original_seed"], "continuation": job["continuation"], "checkpoint_ref": ref}
                if job["horizon"] == 8000:
                    bp8.append(info)
                    if job["continuation"] == 4201:
                        future_source.append(info)
                else:
                    bp36.append(info)
        check("expected_asset_counts", totals["outcome_files"] == 35 and totals["outcome_rows"] == 14000 and totals["metric_files"] == totals["episode_files"] == 200)
        check("expected_log_rows", totals["metric_rows"] == 8800 and totals["episode_rows"] == 4400)
        check("B_and_C_source_states", len(bp8) == len(bp36) == 10 and len(future_source) == 5)
        b = proposal["B_checkpoint_evaluation"]
        c = proposal["C_fresh_future_replication"]
        eval_one = b["tasks"] * b["cases_per_task"] * b["max_episode_steps"]
        check("B_budget", b["policies_to_evaluate"] * eval_one == b["evaluation_upper_steps"] == 2000000)
        future_n = c["parents"] * len(c["future_labels"])
        for name in ("C_keep", "C_switch_optional"):
            arm = c[name]
            check(name + "_budget", future_n == arm["new_training_branches"] == arm["new_evaluation_policies"] and future_n * c["future_training_steps"] == arm["new_training_steps"] and future_n * eval_one == arm["evaluation_upper_steps"] and arm["new_training_steps"] + arm["evaluation_upper_steps"] == arm["combined_upper_steps"])
        budget = proposal["budget_ladder"]
        check("budget_ladder", budget["A_plus_B_upper_steps"] == b["evaluation_upper_steps"] and budget["A_plus_B_plus_C_keep_upper_steps"] == b["evaluation_upper_steps"] + c["C_keep"]["combined_upper_steps"] and budget["A_plus_B_plus_C_keep_and_switch_upper_steps"] == b["evaluation_upper_steps"] + c["C_keep"]["combined_upper_steps"] + c["C_switch_optional"]["combined_upper_steps"])
        check("maximum_new_training", budget["max_new_training_steps"] == 640000 and budget["max_new_training_branches"] == 20)
        summary = {"status": "design_inventory_and_arithmetic_checked", "scientific_analyses_executed": [], "experiment_execution": "not_started_or_scheduled", "new_environment_steps": 0, "new_SAC_updates": 0, "campaign": str(cam), "asset_counts": dict(totals), "metric_headers": [list(x) for x in metric_headers], "episode_headers": [list(x) for x in episode_headers], "outcome_headers": [list(x) for x in outcome_headers], "B_8k_checkpoints": bp8, "existing_36k_checkpoints": bp36, "C_origin_4201_states": future_source, "budget_ladder": budget, "checks_passed": len(checks), "wall_seconds": time.perf_counter() - start, "checkpoint_verification_scope": "Manifest hash and existence only; full binary hashes and exact restoration required before any future evaluation or training."}
        write("summary.json", summary)
        write("asset_manifest.json", assets)
        write("input_hashes.json", inputs)
        write("checks.json", checks)
        write("source_hashes.json", {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in snap.iterdir()})
        with (HERE / "LATEST_DESIGN_AUDIT.json").open("w", encoding="utf-8") as f:
            json.dump({"run": str(out), "summary_sha256": hashlib.sha256((out / "summary.json").read_bytes()).hexdigest()}, f, indent=2)
        print(json.dumps({"run": str(out), "counts": dict(totals), "checks_passed": len(checks), "new_environment_steps": 0, "scientific_analyses_executed": [], "budget_ladder": budget}, ensure_ascii=False, indent=2))
    except BaseException:
        write("failure.json", {"traceback": traceback.format_exc(), "checks": checks, "input_hashes": inputs, "new_environment_steps": 0})
        raise


if __name__ == "__main__":
    main()
