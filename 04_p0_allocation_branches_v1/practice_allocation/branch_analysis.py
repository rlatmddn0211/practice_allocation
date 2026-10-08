"""Prespecified descriptive contrasts; never feed outcome scores to selectors."""

import csv
from collections import defaultdict

from .core import TASKS, write_json


def write_table(path, rows):
    if not rows:
        return
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def comparison_rows(baseline, branches):
    baseline_rates = baseline["success_by_task"]
    baseline_macro = sum(baseline_rates.values()) / 4
    uniform = {b["repeat_seed"]: b for b in branches if b["candidate"] == "U"}
    rows, task_rows = [], []
    for branch in branches:
        for horizon, result in branch["outcomes"].items():
            rates = result["success_by_task"]
            reference = uniform[branch["repeat_seed"]]["outcomes"][horizon]["success_by_task"]
            macro, uniform_macro = sum(rates.values()) / 4, sum(reference.values()) / 4
            rows.append({"original_seed": 901, "parent_step": 200000,
                         "repeat_seed": branch["repeat_seed"], "candidate": branch["candidate"],
                         "additional_steps": int(horizon), "macro_success": macro,
                         "gain_pp": 100 * (macro - baseline_macro),
                         "extra_gain_vs_uniform_pp": 100 * (macro - uniform_macro),
                         "max_drop_pp": 100 * max(0, max(baseline_rates[t] - rates[t] for t in TASKS)),
                         "worst_task_success": min(rates.values()),
                         **{f"success_{t}": rates[t] for t in TASKS}})
            for task in TASKS:
                task_rows.append({"repeat_seed": branch["repeat_seed"], "candidate": branch["candidate"],
                                  "additional_steps": int(horizon), "task": task,
                                  "base_success": baseline_rates[task], "success": rates[task],
                                  "uniform_success": reference[task],
                                  "gain_pp": 100 * (rates[task] - baseline_rates[task]),
                                  "difference_vs_uniform_pp": 100 * (rates[task] - reference[task])})
    return rows, task_rows


def make_analysis(output, baseline, branches, plan, recommendations):
    rows, task_rows = comparison_rows(baseline, branches)
    write_table(output / "allocation_comparison.csv", rows)
    write_table(output / "task_changes.csv", task_rows)
    primary = [row for row in rows if row["additional_steps"] == plan.steps_per_branch]
    by_key = {(r["repeat_seed"], r["candidate"], r["additional_steps"]): r for r in rows}
    rule_rows = []
    for repeat in plan.repeat_seeds:
        for horizon in plan.evaluation_steps:
            for rule, candidate in recommendations.items():
                rule_rows.append({"rule": rule, **by_key[(repeat, candidate, horizon)]})
    write_table(output / "frozen_rule_scores.csv", rule_rows)
    grouped = defaultdict(list)
    with (output / "evaluation_episodes.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            grouped[(row["evaluation_id"], row["task"])].append(row)
    paired_rows = []
    for branch in branches:
        for horizon, result in branch["outcomes"].items():
            for task in TASKS:
                current = {r["initial_state_hash"]: int(r["success"])
                           for r in grouped[(result["evaluation_id"], task)]}
                for reference_name, reference_id in (("baseline", baseline["evaluation_id"]),
                    ("uniform", f"repeat_{branch['repeat_seed']}_U_h{int(horizon):06d}")):
                    reference = {r["initial_state_hash"]: int(r["success"])
                                 for r in grouped[(reference_id, task)]}
                    if set(current) != set(reference) or len(current) != plan.episodes_per_task:
                        raise RuntimeError("Paired analysis has missing or inconsistent evaluation initial states.")
                    pairs = [(reference[k], current[k]) for k in current]
                    paired_rows.append({"repeat_seed": branch["repeat_seed"], "candidate": branch["candidate"],
                                        "additional_steps": int(horizon), "task": task, "reference": reference_name,
                                        "episodes": len(pairs),
                                        "new_successes": pairs.count((0, 1)), "lost_successes": pairs.count((1, 0)),
                                        "persistent_successes": pairs.count((1, 1)),
                                        "persistent_failures": pairs.count((0, 0))})
    write_table(output / "paired_success_changes.csv", paired_rows)
    cross_repeat = []
    if len(plan.repeat_seeds) == 2:
        for train_repeat, test_repeat in (plan.repeat_seeds, plan.repeat_seeds[::-1]):
            # Integer success counts prevent floating-point tie breaking.
            counts = {b["candidate"]: sum(b["outcomes"][str(plan.steps_per_branch)]["success_counts"].values())
                      for b in branches if b["repeat_seed"] == train_repeat}
            selected = max(plan.candidates, key=lambda candidate: counts[candidate])
            test = by_key[(test_repeat, selected, plan.steps_per_branch)]
            cross_repeat.append({"selection_repeat": train_repeat, "evaluation_repeat": test_repeat,
                                 "selected_candidate": selected, "evaluation_macro_success": test["macro_success"],
                                 "evaluation_extra_gain_vs_uniform_pp": test["extra_gain_vs_uniform_pp"]})
    write_json(output / "comparison_summary.json", {
        "stage": plan.stage, "primary_horizon": plan.steps_per_branch, "primary_results": primary,
        "frozen_recommendations": recommendations, "cross_repeat_selection_diagnostic": cross_repeat,
        "tie_order": list(plan.candidates),
        "limits": ["One original training seed; two continuations are not independent pretrained policies.",
                   "Descriptive pilot results; no automated significance or generalization claim.",
                   "Emphasizing one task also reduces practice on other tasks.",
                   "Cross-repeat candidate selection is a diagnostic, not an operational selector."]})
    return {"primary_horizon": plan.steps_per_branch, "primary_rows": len(primary),
            "comparison_rows": len(rows), "paired_rows": len(paired_rows),
            "cross_repeat_directions": len(cross_repeat)}
