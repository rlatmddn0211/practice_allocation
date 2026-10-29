"""Independent read-only completion audit; no training or policy evaluation."""
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timezone
import csv, hashlib, json, math

OUTPUT = Path(__file__).resolve().parent
ROOT = OUTPUT.parents[1]
RUN = ROOT / "results/20261007T091127Z_allocation_branches_cuda_64ec1ea7/run"
TASKS = ("DO", "DC", "WO", "WC")
QUOTAS = {"U": (2,2,2,2), "F_DO": (5,1,1,1), "F_DC": (1,5,1,1), "F_WO": (1,1,5,1), "F_WC": (1,1,1,5)}
checks = []
input_hashes = {}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read_json(path):
    input_hashes[str(path.relative_to(ROOT.parent))] = sha(path)
    return json.loads(path.read_text(encoding="utf-8"))

def rows(path):
    input_hashes[str(path.relative_to(ROOT.parent))] = sha(path)
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))

def check(name, condition):
    checks.append({"name": name, "passed": bool(condition)})
    if not condition:
        raise AssertionError(name)

def near(a, b):
    return math.isclose(float(a), float(b), rel_tol=0, abs_tol=1e-9)

def main():
    summary = read_json(RUN / "run_summary.json")
    manifest = read_json(RUN / "run_manifest.json")
    receipt = read_json(RUN / "parent_provenance.json")
    check("ten_branches_completed", summary["status"] == "completed" and summary["branches_completed"] == 10 and summary["error"] is None)
    check("original_and_continuation_seeds", summary["original_seed"] == 901 and summary["parent_step"] == 200000 and summary["continuation_seeds"] == [1901,1902])
    for name, expected in manifest["source_hashes"].items():
        check("frozen_source:" + name, sha(ROOT / name) == expected and sha(RUN / "source_snapshot" / name) == expected)
    parent = Path(receipt["parent_run"])
    for name, expected in receipt["pinned_inputs"].items():
        check("parent_input:" + name, sha(parent / name) == expected)
    for name, expected in receipt["checkpoint_files"].items():
        check("parent_checkpoint:" + name, sha(Path(receipt["checkpoint"]) / name) == expected)
    saved_parent = read_json(Path(receipt["checkpoint"]) / "checkpoint_manifest.json")
    for name, expected in saved_parent["source_hashes"].items():
        check("parent_source:" + name, sha(parent.parents[2] / name) == expected and sha(parent / "source_snapshot" / name) == expected)
    for checkpoint in [RUN / "initial_checkpoint", *sorted((RUN / "branches").glob("*/checkpoints/*"))]:
        cm = read_json(checkpoint / "checkpoint_manifest.json")
        restore = read_json(checkpoint / "restore_verification.json")
        check("checkpoint_restore:" + str(checkpoint.relative_to(RUN)), restore["restored_state_matches"] and cm["source_hashes"] == manifest["source_hashes"])
        for name, expected in cm["files"].items():
            check("checkpoint_bytes:" + str((checkpoint / name).relative_to(RUN)), sha(checkpoint / name) == expected)
    evaluations = rows(RUN / "evaluation_episodes.csv")
    groups = defaultdict(list)
    for row in evaluations:
        groups[row["evaluation_id"]].append(row)
    check("evaluation_grain", len(evaluations) == 4200 and len(groups) == 21 and len({r["initial_state_hash"] for r in evaluations}) == 200)
    banks = read_json(RUN / "evaluation_banks.json")
    expected_cases = {(r["task"], str(r["episode_index"]), str(r["seed"]), r["initial_state_hash"]) for r in banks["outcome"]}
    computed = {}
    for evaluation_id, group in groups.items():
        check("evaluation_cases:" + evaluation_id, len(group) == 200 and all(r["bank"] == "outcome" for r in group) and
              {(r["task"], r["episode_index"], r["seed"], r["initial_state_hash"]) for r in group} == expected_cases)
        computed[evaluation_id] = {task: sum(int(r["success"]) for r in group if r["task"] == task) / 50 for task in TASKS}
    baseline = read_json(RUN / "baseline/evaluation.json")
    check("baseline_recalculation", computed["baseline"] == baseline["success_by_task"] and near(sum(computed["baseline"].values())/4, .485))
    all_training = []
    final_learning_states = []
    for repeat in (1901,1902):
        for candidate, quota in QUOTAS.items():
            branch_id = f"repeat_{repeat}_{candidate}"
            directory = RUN / "branches" / branch_id
            branch = read_json(directory / "branch_summary.json")
            started = read_json(directory / "branch_started.json")
            check("branch_start:" + branch_id, started["before_fingerprints"] == receipt["parent_state_fingerprints"] and
                  started["before_fingerprints"]["learning"] == started["after_fingerprints"]["learning"])
            check("branch_budget:" + branch_id, branch["status"] == "completed" and branch["additional_training_steps"] == branch["additional_sac_iterations"] == 40000)
            episodes = rows(directory / "train_episodes.csv")
            all_training.extend(episodes)
            check("training_episodes:" + branch_id, len(episodes) == 80 and all(int(r["length"]) == 500 for r in episodes))
            for block in range(10):
                counts = Counter(r["task"] for r in episodes[block*8:(block+1)*8])
                check(f"block_quota:{branch_id}:{block}", [counts[t] for t in TASKS] == list(quota))
            check("collected_exposure:" + branch_id, branch["collected_new_by_task"] == {t: q*5000 for t,q in zip(TASKS,quota)})
            check("sampled_exposure:" + branch_id, sum(branch["sampled_during_branch_by_task"].values()) == 40000*256 and 0 <= branch["sampled_new_experience_fraction"] <= 1 and near(branch["new_experience_fraction_in_final_replay"], .4))
            check("reset_audit:" + branch_id, read_json(directory / "training_reset_audit.json")["passed"])
            for horizon in (20000,40000):
                result = branch["outcomes"][str(horizon)]
                check(f"result_recalculation:{branch_id}:{horizon}", computed[result["evaluation_id"]] == result["success_by_task"] and result["state_unchanged"])
            final_learning_states.append(branch["final_state_fingerprints"]["learning"])
    check("distinct_final_models", len(set(final_learning_states)) == 10)
    check("total_training_transitions", sum(int(r["length"]) for r in all_training) == 400000)
    ledger = rows(RUN / "cost_ledger.csv")
    for key, expected in summary["costs"].items():
        check("cost_ledger:" + key, sum(int(r[key]) for r in ledger) == expected)
    check("evaluation_transitions", sum(int(r["length"]) for r in evaluations) == summary["evaluation_transitions"])
    check("total_environment_transitions", summary["costs"]["environment_steps"] == 400000 + summary["evaluation_transitions"])
    check("training_seconds", near(sum(float(r["seconds"]) for r in ledger if r["stage"].startswith("train_")), summary["training_seconds"]))
    comparisons = rows(RUN / "allocation_comparison.csv")
    check("comparison_cardinality", len(comparisons) == 20)
    primary = defaultdict(list)
    for row in comparisons:
        repeat, candidate, horizon = int(row["repeat_seed"]), row["candidate"], int(row["additional_steps"])
        rates = computed[f"repeat_{repeat}_{candidate}_h{horizon:06d}"]
        uniform = computed[f"repeat_{repeat}_U_h{horizon:06d}"]
        macro = sum(rates.values()) / 4
        check(f"comparison_recalculation:{repeat}:{candidate}:{horizon}",
              near(row["macro_success"], macro) and near(row["gain_pp"], 100*(macro-.485)) and
              near(row["extra_gain_vs_uniform_pp"], 25*(sum(rates.values())-sum(uniform.values()))) and
              near(row["max_drop_pp"], 100*max(0,max(computed["baseline"][t]-rates[t] for t in TASKS))))
        if horizon == 40000:
            primary[candidate].append({"repeat_seed": repeat, "macro_success": macro, "extra_gain_pp": float(row["extra_gain_vs_uniform_pp"])})
    selected = read_json(RUN / "frozen_selection_rules.json")
    check("selectors_unchanged", selected == read_json(parent / "selected_checkpoint.json") and not selected["outcome_scores_used"])
    mean_results = {candidate: {"macro_success": sum(r["macro_success"] for r in group)/2,
                               "extra_gain_pp": sum(r["extra_gain_pp"] for r in group)/2}
                    for candidate, group in primary.items()}
    return {"baseline_macro": .485, "primary_by_candidate": dict(primary), "mean_primary": mean_results,
            "completed_at": summary["completed_at"], "elapsed_seconds": summary["elapsed_seconds"],
            "additional_training_steps": 400000, "evaluation_episodes": 4200, "unique_evaluation_states": 200}

if __name__ == "__main__":
    record = {"created_at": datetime.now(timezone.utc).isoformat(), "source_run": str(RUN),
              "audit_script_sha256": sha(Path(__file__)), "additional_training_steps_executed": 0,
              "additional_evaluation_episodes_executed": 0, "status": "running"}
    try:
        record["results"] = main()
        record["status"] = "passed"
    except BaseException as error:
        record["status"] = "failed"
        record["error"] = repr(error)
        raise
    finally:
        record["checks"] = checks
        record["checks_passed"] = sum(c["passed"] for c in checks)
        record["input_hashes"] = input_hashes
        with (OUTPUT / "verification.json").open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(record, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write("\n")
        print(json.dumps({"status": record["status"], "checks_passed": record["checks_passed"],
                          "results": record.get("results"), "output": str(OUTPUT)}, ensure_ascii=False))

