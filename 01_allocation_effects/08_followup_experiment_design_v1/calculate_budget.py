"""Review planned budgets from frozen local evidence; never imports or runs RL."""
from __future__ import annotations

import csv
import hashlib
import json
import platform
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    started = time.perf_counter()
    output = ROOT / "results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_budget_review_" + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    snapshot = output / "source_snapshot"
    snapshot.mkdir()
    checks = []
    record = {"status": "running", "created_at": datetime.now(timezone.utc).isoformat(),
              "python": platform.python_version(), "dependencies": "Python standard library only",
              "actual_training_steps": 0, "actual_policy_evaluation_episodes": 0,
              "checks": checks, "source_hashes": {}, "input_hashes": {}}

    def check(name, condition):
        checks.append({"name": name, "passed": bool(condition)})
        if not condition:
            raise AssertionError(name)

    def read(relative):
        path = REPO / relative
        record["input_hashes"][relative] = sha(path)
        return json.loads(path.read_text(encoding="utf-8"))

    try:
        for name in ("protocol.json", "README.md", "calculate_budget.py"):
            shutil.copy2(ROOT / name, snapshot / name)
            record["source_hashes"][name] = sha(ROOT / name)
        record["git_head"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
        record["root_pilot_design_sha256"] = sha(REPO / "LOCAL_PRACTICE_ALLOCATION_PILOT_DESIGN_20261007.md")
        protocol = json.loads((ROOT / "protocol.json").read_text(encoding="utf-8"))
        check("proposal_is_not_execution", protocol["status"] == "proposed_not_executed")
        pretraining = read(protocol["cost_reference"]["pretraining_summary"])
        replication = read(protocol["cost_reference"]["replication_summary"])
        check("references_completed", pretraining["status"] == replication["status"] == "completed")
        factors = {"pretrain_seconds_per_step": pretraining["training_seconds"] / pretraining["training_steps"],
                   "branch_seconds_per_step": replication["training_seconds"] / replication["additional_training_steps"],
                   "residual_seconds_per_episode_proxy": (replication["elapsed_seconds"] - replication["training_seconds"]) / replication["costs"]["evaluation_episodes"]}
        record["timing_factors"] = factors
        common = protocol["common"]
        for group in ("standard_allocations", "donor_swap_allocations"):
            for name, counts in protocol[group].items():
                check(group + ":" + name, len(counts) == 4 and all(isinstance(x, int) and x > 0 for x in counts) and sum(counts) == 8)
        check("donor_swap_holds_DO_WC", all(row[0] == row[3] == 2 for row in protocol["donor_swap_allocations"].values()))
        check("branch_is_complete_blocks", common["branch_steps"] % (common["training_episode_steps"] * common["episodes_per_allocation_block"]) == 0)
        known_ids = (REPO / "06_p0_branch_replication_v1/.venv/Lib/site-packages/metaworld/env_dict.py").read_text(encoding="utf-8")
        for name, tasks in protocol["task_suites"].items():
            check("suite:" + name, len(tasks) == len(set(tasks)) == 4 and all('"' + task + '"' in known_ids for task in tasks))
        budgets = []
        for item in protocol["experiments"]:
            count = item["contexts"] * item["candidates"] * item["repeats"]
            pretrain_steps = item["pretrain_runs"] * item["steps_per_pretrain"]
            branch_steps = count * item["extra_steps_per_branch"]
            episodes = 4 * (item["outcome_policy_evaluations"] * common["outcome_cases_per_task"] + item["public_policy_evaluations"] * common["public_diagnostic_cases_per_task"])
            check(item["id"] + ":training_budget", pretrain_steps + branch_steps == item["expected_training_steps"])
            check(item["id"] + ":evaluation_budget", episodes == item["expected_evaluation_episodes"])
            if item["id"] != "E0":
                check(item["id"] + ":outcome_count", item["outcome_policy_evaluations"] == item["contexts"] + 2 * count)
                check(item["id"] + ":seed_context_count", item["contexts"] == len(item["suites"]) * len(item["original_seeds"]) * len(item["checkpoints"]))
                check(item["id"] + ":continuation_count", item["repeats"] == len(item["continuation_seeds"]))
            if item["pretrain_runs"]:
                check(item["id"] + ":public_count", item["public_policy_evaluations"] == item["pretrain_runs"] * len(item["public_diagnostic_steps"]))
            hours = (pretrain_steps * factors["pretrain_seconds_per_step"] + branch_steps * factors["branch_seconds_per_step"] + episodes * factors["residual_seconds_per_episode_proxy"]) / 3600
            budgets.append({"experiment": item["id"], "pretraining_steps": pretrain_steps, "branches": count,
                            "branch_training_steps": branch_steps, "total_training_steps": pretrain_steps + branch_steps,
                            "evaluation_episodes": episodes, "evaluation_transition_upper_bound": episodes * 500,
                            "reference_hours": hours, "status": "planned_not_run"})
        record["budgets"] = budgets
        check("first_package_total", sum(x["total_training_steps"] for x in budgets if x["experiment"] in ("E0", "E1")) == 4800000 and sum(x["evaluation_episodes"] for x in budgets if x["experiment"] in ("E0", "E1")) == 90000)
        check("core_package_total", sum(x["total_training_steps"] for x in budgets if x["experiment"] in ("E0", "E1", "E2", "E3")) == 10680000)
        check("source_bytes_unchanged", all(sha(ROOT / name) == expected for name, expected in record["source_hashes"].items()))
        check("evidence_bytes_unchanged", all(sha(REPO / name) == expected for name, expected in record["input_hashes"].items()))
        with (output / "budget.csv").open("x", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(budgets[0]))
            writer.writeheader()
            writer.writerows(budgets)
        record["status"] = "passed"
    except Exception as error:
        record["status"] = "failed"
        record["error"] = repr(error)
        raise
    finally:
        record["actual_elapsed_seconds"] = time.perf_counter() - started
        with (output / "verification.json").open("x", encoding="utf-8") as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        print(json.dumps({"status": record["status"], "checks": len(checks), "output": str(output), "budgets": record.get("budgets", [])}))


if __name__ == "__main__":
    main()
