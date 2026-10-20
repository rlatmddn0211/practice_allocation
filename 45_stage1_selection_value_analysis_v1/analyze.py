"""Read-only reanalysis of stage 1; never trains, evaluates, or changes v44."""
import csv
import hashlib
import io
import itertools
import json
import math
import platform
import shutil
import statistics
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
CONDITIONS = ("dose625", "alternate4k", "mixture")
TASKS = ("DO", "DC", "PU", "BP")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    started = time.perf_counter()
    run = HERE / "results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_review_" + uuid.uuid4().hex[:8])
    run.mkdir(parents=True, exist_ok=False)
    (run / "source_snapshot").mkdir()
    shutil.copy2(__file__, run / "source_snapshot" / "analyze.py")
    source_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    inputs, checks = {}, []

    def write(name, value):
        with (run / name).open("x", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write("\n")

    def check(label, passed):
        checks.append({"check": label, "passed": bool(passed)})
        if not passed:
            raise AssertionError(label)

    def read_bytes(path, expected=None):
        path = Path(path).resolve()
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        inputs[str(path)] = digest
        if expected:
            check("sha256:" + str(path), digest == expected)
        return data

    def js(path, expected=None):
        return json.loads(read_bytes(path, expected).decode("utf-8-sig"))

    def csv_rows(path, expected=None):
        return list(csv.DictReader(io.StringIO(read_bytes(path, expected).decode("utf-8-sig"))))

    def table(name, rows):
        with (run / name).open("x", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    try:
        active = js(REPO / "44_selection_value_stage1_checkpoint36_v2" / "ACTIVE_CAMPAIGN.json")
        cam = Path(active["campaign"])
        complete = js(cam / "COMPLETE.json")
        completion = js(complete["summary"]["path"], complete["summary"]["sha256"])
        integrity = js(cam / "plan_integrity.json")
        plan = js(cam / "plan.json", integrity["sha256"])
        protocol = js(REPO / "43_feedback_revised_selection_protocol_v1" / "protocol.json")
        official = js(completion["analysis"]["path"], completion["analysis"]["sha256"])
        official_dir = Path(completion["analysis"]["path"]).parent
        readiness = js(cam / "readiness_evidence.json")
        read_bytes(REPO / "25_candidate_factor_evidence_register_v1" / "record_template_ko.md")
        read_bytes(REPO / "37_f08_integrated_candidate_review_v1" / "report_ko.md")
        parents = protocol["stage1"]["original_seeds"]
        repeats = protocol["stage1"]["continuation_labels"]
        check("scientific_complete_245", not plan["technical_smoke"] and completion["jobs_completed"] == len(plan["jobs"]) == 245)
        check("no_recorded_failed_attempts", all(x["status"] == "completed" for x in completion["costs"]))
        policies, halves, parent_scores, branch_scores, bank_cases = [], {}, {}, {}, {}
        last_metrics, packages, parameter_sets, branch_seeds = [], {}, set(), []
        training_steps = 0
        evaluation_steps = 0
        checkpoint36 = 0
        for job in plan["jobs"]:
            marker = js(cam / "completed" / (job["id"] + ".json"))
            result = js(marker["result_ref"]["path"], marker["result_ref"]["sha256"])
            attempt = Path(marker["attempt"])
            request = js(attempt / "request.json")
            cost = js(attempt / "costs.json")
            runtime = js(attempt / "runtime.json")
            packages[json.dumps(runtime["packages"], sort_keys=True)] = runtime["packages"]
            params = {k: v for k, v in runtime["config"].items() if k not in ("version", "seed", "bank_seed")}
            parameter_sets.add(json.dumps(params, sort_keys=True))
            check("complete:" + job["id"], cost["status"] == "completed" and result["id"] == job["id"])
            if job["kind"] == "train":
                training_steps += job["steps"]
                check("training_budget:" + job["id"], cost["costs"]["environment_steps"] == job["steps"])
                checkpoint36 += int(job.get("horizon") == 36000)
                if request.get("start_branch"):
                    branch_seeds.append({k: request[k] for k in ("id", "original_seed", "continuation", "continuation_rng_seed", "condition")})
                if result["step"] == 200000 and "condition" not in result:
                    metrics = csv_rows(attempt / "train_metrics.csv")
                    row = metrics[-1]
                    selected = {k: float(row[k]) for k in ("actor_loss", "critic_loss", "entropy_coefficient", "critic_0_abs_td_error", "critic_1_abs_td_error")}
                    check("finite_parent_final_metrics:" + job["id"], all(math.isfinite(v) for v in selected.values()))
                    last_metrics.append({"original_seed": job["original_seed"], **selected, "interpretation": "One logged update; not a causal diagnosis of low success"})
            if job["kind"] != "evaluate":
                continue
            rows = csv_rows(result["episodes_path"], result["episodes_sha256"])
            keys = {(x["task"], int(x["episode_index"])) for x in rows}
            check("O100_coverage:" + job["id"], len(rows) == 400 and keys == set(itertools.product(TASKS, range(100))))
            check("binary_success:" + job["id"], all(int(x["success"]) in (0, 1) for x in rows))
            check("evaluation_preserved_state:" + job["id"], result["evaluation_state_unchanged"])
            p = job["original_seed"]
            signatures = {(x["task"], int(x["episode_index"]), int(x["seed"]), x["initial_state_hash"]) for x in rows}
            if p in bank_cases:
                check("paired_cases_within_parent:" + job["id"], signatures == bank_cases[p])
            else:
                bank_cases[p] = signatures
            tasks = {t: sum(int(x["success"]) for x in rows if x["task"] == t) for t in TASKS}
            score = sum(tasks.values()) / 4
            check("reported_macro:" + job["id"], abs(score - 100 * result["evaluation"]["macro_success"]) < 1e-10)
            step_count = sum(int(x["length"]) for x in rows)
            check("evaluation_step_count:" + job["id"], step_count == cost["costs"]["environment_steps"] == result["evaluation"]["environment_steps"])
            evaluation_steps += step_count
            condition = job.get("condition", "parent")
            rep = job.get("continuation", "")
            policies.append({"original_seed": p, "continuation": rep, "condition": condition, "macro_pp": score, **tasks})
            if condition == "parent":
                parent_scores[p] = score
            else:
                branch_scores[p, rep, condition] = score
                for h in (0, 1):
                    halves[p, rep, condition, h] = sum(int(x["success"]) for x in rows if int(x["episode_index"]) // 50 == h) / 2
        check("identical_learner_parameters", len(parameter_sets) == 1)
        check("same_dependency_versions", len(packages) == 1)
        check("cell_counts", len(policies) == 35 and len(branch_scores) == 30 and len(parent_scores) == 5)
        check("all_36k_checkpoints_recorded", checkpoint36 == 30)
        check("exact_training_and_total_cost", training_steps == 2200000 and training_steps + evaluation_steps == completion["actual_environment_steps_recorded"])

        def best(values):
            return max(CONDITIONS, key=lambda c: values[c])

        def crossfit(selected_parents):
            rows = []
            for p, target_r, h in itertools.product(selected_parents, repeats, (0, 1)):
                source_r = next(r for r in repeats if r != target_r)
                choice = best({c: halves[p, source_r, c, h] for c in CONDITIONS})
                fixed = best({c: statistics.mean(halves[q, r, c, h] for q in selected_parents if q != p for r in repeats) for c in CONDITIONS})
                chosen = halves[p, target_r, choice, 1 - h]
                rows.append({"original_seed": p, "heldout_continuation": target_r, "selection_half": h, "score_half": 1-h, "selected": choice, "leave_parent_out_fixed": fixed, "selected_pp": chosen, "vs_BP_pp": chosen - halves[p, target_r, "dose625", 1-h], "vs_fixed_pp": chosen - halves[p, target_r, fixed, 1-h]})
            return rows

        choices = crossfit(parents)
        old_choices = csv_rows(official_dir / "choice_crossfit.csv")
        for new, old in zip(choices, old_choices):
            check("crossfit_replication:" + str((new["original_seed"], new["heldout_continuation"], new["selection_half"])), all(str(new[k]) == old[k] if isinstance(new[k], str) else abs(new[k] - float(old[k])) < 1e-10 for k in new))
        check("crossfit_count", len(old_choices) == len(choices) == 20)
        parent_table = []
        for p in parents:
            means = {c: statistics.mean(branch_scores[p, r, c] for r in repeats) for c in CONDITIONS}
            parent_table.append({"original_seed": p, "parent_macro_pp": parent_scores[p], **means, **{c + "_minus_parent_pp": means[c] - parent_scores[p] for c in CONDITIONS}, "both_repeat_mean_best": best(means), "crossfit_minus_BP_pp": statistics.mean(x["vs_BP_pp"] for x in choices if x["original_seed"] == p), "crossfit_minus_fixed_pp": statistics.mean(x["vs_fixed_pp"] for x in choices if x["original_seed"] == p)})
        aggregates = []
        for c in ("parent",) + CONDITIONS:
            rows = [x for x in policies if x["condition"] == c]
            aggregates.append({"condition": c, "policies": len(rows), **{k: statistics.mean(x[k] for x in rows) for k in ("macro_pp",) + TASKS}, "gain_vs_parent_pp": statistics.mean(x["macro_pp"] for x in rows) - statistics.mean(parent_scores.values())})
        mean_score = {x["condition"]: x["macro_pp"] for x in aggregates}
        repeat_pairs = []
        preference_sets = []
        for a, b in itertools.combinations(CONDITIONS, 2):
            plus, minus = [], []
            for p in parents:
                diffs = [branch_scores[p, r, a] - branch_scores[p, r, b] for r in repeats]
                repeat_pairs.append({"original_seed": p, "a": a, "b": b, "r4201_a_minus_b_pp": diffs[0], "r4202_a_minus_b_pp": diffs[1], "mean_difference_pp": statistics.mean(diffs), "sign_reversed": diffs[0] * diffs[1] < 0, "a_better_by_2pp_both": all(x >= 2 for x in diffs), "b_better_by_2pp_both": all(x <= -2 for x in diffs)})
                if all(x >= 2 for x in diffs): plus.append(p)
                if all(x <= -2 for x in diffs): minus.append(p)
            preference_sets.append({"a": a, "b": b, "a_preferred_parents": plus, "b_preferred_parents": minus, "opposite_repeatable_preferences": bool(plus and minus)})
        check("repeatable_preferences_match", preference_sets == official["pairwise_preferences"])
        refits = []
        for excluded in parents:
            rows = crossfit([p for p in parents if p != excluded])
            refits.append({"excluded_original_seed": excluded, "vs_BP_pp": statistics.mean(x["vs_BP_pp"] for x in rows), "vs_fixed_pp": statistics.mean(x["vs_fixed_pp"] for x in rows)})
        for k in ("vs_BP_pp", "vs_fixed_pp"):
            check("full_parent_refit_matches:" + k, all(abs(x[k] - y) < 1e-10 for x, y in zip(refits, official["full_parent_removal_refitted_means"][k])))
        cross_mean = {k: statistics.mean(x[k] for x in choices) for k in ("selected_pp", "vs_BP_pp", "vs_fixed_pp")}
        gate_parts = {"opposite_repeatable_parent_preferences": any(x["opposite_repeatable_preferences"] for x in preference_sets), "positive_crossfit_vs_both_controls": cross_mean["vs_BP_pp"] > 0 and cross_mean["vs_fixed_pp"] > 0, "positive_after_every_parent_removal": all(x[k] > 0 for x in refits for k in ("vs_BP_pp", "vs_fixed_pp"))}
        check("investment_gate_recomputed", all(gate_parts.values()) == official["stage2_investment_gate_pass"])
        comparisons = csv_rows(official_dir / "comparisons.csv")
        for row in comparisons:
            a, b = row["method"], row["baseline"]
            vals = [statistics.mean(branch_scores[p, r, a] - branch_scores[p, r, b] for r in repeats) for p in parents]
            check("comparison_values:" + a + "_" + b, vals == json.loads(row["parent_values_pp"]) and abs(statistics.mean(vals) - float(row["mean_pp"])) < 1e-10)
        parent_oracle = statistics.mean(max(x[c] for c in CONDITIONS) for x in parent_table)
        branch_oracle = statistics.mean(max(branch_scores[p, r, c] for c in CONDITIONS) for p in parents for r in repeats)
        summary = {
            "execution_status": "completed",
            "scientific_status": "stage1_investment_gate_not_passed; adaptive allocation remains unvalidated",
            "campaign": str(cam), "campaign_completed_at": complete["completed_at"],
            "original_seeds": parents, "continuation_labels": repeats,
            "independent_unit": "parent; two repeats and four crossfit scores are dependent",
            "evaluation": {"policies": 35, "episodes": 14000, "same_cases_within_parent": True, "outcome_cases_per_task": 100},
            "aggregates": aggregates, "parent_scores": parent_table,
            "crossfit": {**cross_mean, "heldout_fixed_mean_pp": cross_mean["selected_pp"] - cross_mean["vs_fixed_pp"], "information_scope": "retrospective final outcomes in another continuation and disjoint episode half; not an 8k diagnostic"},
            "gate_parts": gate_parts, "stage2_investment_gate_pass": all(gate_parts.values()),
            "full_parent_removal_refits": refits,
            "parents_all_three_method_means_below_parent": [x["original_seed"] for x in parent_table if all(x[c] < x["parent_macro_pp"] for c in CONDITIONS)],
            "posthoc_optimistic_reuse": {"parent_mean_best_score_pp": parent_oracle, "parent_mean_best_minus_BP_pp": parent_oracle - mean_score["dose625"], "each_branch_best_score_pp": branch_oracle, "each_branch_best_minus_BP_pp": branch_oracle - mean_score["dose625"], "scope": "Select and score on the same final observations. Not a validated selector, population upper bound, or net-cost result."},
            "costs": {"research_training_steps": training_steps, "research_evaluation_steps": evaluation_steps, "research_total_environment_steps": completion["actual_environment_steps_recorded"], "research_SAC_updates": completion["actual_update_iterations_recorded"], "research_attempt_wall_seconds_sum": sum(x["wall_seconds"] for x in completion["costs"]), "research_attempt_CPU_seconds_sum": sum(x["cpu_seconds"] for x in completion["costs"]), "research_GPU_busy_seconds": None, "v44_technical_environment_steps_separate": readiness["new_technical_environment_steps"], "analysis_new_environment_steps": 0, "analysis_new_SAC_updates": 0, "analysis_wall_seconds": time.perf_counter() - started},
            "dependencies_of_training": list(packages.values()),
            "analysis_runtime": {"python": sys.version, "platform": platform.platform()},
            "uncertainty": "Original descriptive bootstrap resamples five parents after averaging repeats. Small exploratory sample, no independent significance or absence claim. Learning variation and finite evaluation noise are not separately identified.",
            "preparation_note": "An initial console-only read failed under cp949; repeated with UTF-8. No experiment or analysis-run data were changed.",
        }
        table("policy_scores.csv", policies)
        table("method_scores.csv", aggregates)
        table("parent_scores.csv", parent_table)
        table("repeat_pair_differences.csv", repeat_pairs)
        table("crossfit.csv", choices)
        table("parent_removal_refits.csv", refits)
        table("parent_final_training_metrics.csv", last_metrics)
        table("continuation_rng_seeds.csv", branch_seeds)
        table("predeclared_comparisons.csv", comparisons)
        write("summary.json", summary)
        write("checks.json", {"checks": checks, "passed": len(checks), "failed": 0, "scope": "Technical provenance and arithmetic validation, not scientific-effect evidence"})
        write("input_hashes.json", inputs)
        write("source_hashes.json", {"analyze.py": source_hash})
        # Only this navigation pointer is mutable; every run and source snapshot is new.
        with (HERE / "LATEST_REVIEW.json").open("w", encoding="utf-8") as f:
            json.dump({"run": str(run), "summary_sha256": hashlib.sha256((run / "summary.json").read_bytes()).hexdigest()}, f, indent=2)
        print(json.dumps({"run": str(run), "checks_passed": len(checks), "means": mean_score, "crossfit": cross_mean, "gate": gate_parts, "new_environment_steps": 0}, ensure_ascii=False, indent=2))
    except BaseException:
        write("failure.json", {"traceback": traceback.format_exc(), "checks": checks, "input_hashes": inputs, "source_hash": source_hash, "new_environment_steps": 0})
        raise


if __name__ == "__main__":
    main()
