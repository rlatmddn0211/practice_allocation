"""Separate new replication evidence, old discovery evidence, and pooled description."""

from .branch_analysis import comparison_rows, write_table
from .core import write_json


def cohort_summaries(baseline, discovery, replication, candidates):
    rows = []
    for cohort, branches in (("replication", replication), ("discovery", discovery),
                             ("combined_descriptive", discovery + replication)):
        comparisons, _ = comparison_rows(baseline, branches)
        for candidate in candidates:
            values = [r for r in comparisons if r["candidate"] == candidate and r["additional_steps"] == 40000]
            if not values or len({r["repeat_seed"] for r in values}) != len(values):
                raise RuntimeError("Missing or duplicated primary repeat in cohort summary.")
            deltas = [round(r["extra_gain_vs_uniform_pp"], 10) for r in values]
            rows.append({"cohort": cohort, "candidate": candidate, "repeat_count": len(values),
                         "repeat_seeds": ";".join(str(r["repeat_seed"]) for r in values),
                         "mean_macro_success": sum(r["macro_success"] for r in values) / len(values),
                         "mean_gain_pp": sum(r["gain_pp"] for r in values) / len(values),
                         "mean_extra_gain_vs_uniform_pp": sum(deltas) / len(deltas),
                         "minimum_extra_gain_pp": min(deltas), "maximum_extra_gain_pp": max(deltas),
                         "positive_repeats": sum(v > 0 for v in deltas),
                         "zero_repeats": sum(v == 0 for v in deltas),
                         "negative_repeats": sum(v < 0 for v in deltas)})
    return rows


def secondary_contrasts(baseline, branches, cohort):
    indexed = {(b["repeat_seed"], b["candidate"]): b for b in branches}
    rows = []
    initial_wc = baseline["success_by_task"]["WC"]
    for repeat in sorted({b["repeat_seed"] for b in branches}):
        close = indexed[repeat, "F_DC"]["outcomes"]["40000"]["success_by_task"]
        focused = indexed[repeat, "F_DO"]["outcomes"]
        early, late = focused["20000"]["success_by_task"], focused["40000"]["success_by_task"]
        delta = round(100 * (close["DO"] - late["DO"]), 10)
        rows.append({"cohort": cohort, "repeat_seed": repeat,
                     "do_at_40k_under_f_dc": close["DO"], "do_at_40k_under_f_do": late["DO"],
                     "do_f_dc_minus_f_do_pp": delta, "do_discovery_direction_repeated": delta > 0,
                     "f_do_wc_baseline": initial_wc, "f_do_wc_20k": early["WC"], "f_do_wc_40k": late["WC"],
                     "wc_20k_minus_baseline_pp": 100 * (early["WC"] - initial_wc),
                     "wc_40k_minus_20k_pp": 100 * (late["WC"] - early["WC"]),
                     "wc_40k_minus_baseline_pp": 100 * (late["WC"] - initial_wc),
                     "wc_dip_then_return_to_baseline": early["WC"] < initial_wc and late["WC"] >= initial_wc})
    return rows


def write_replication_analysis(output, baseline, discovery, replication, plan, frozen_plan):
    if ({b["repeat_seed"] for b in discovery} != {1901, 1902}
            or {b["repeat_seed"] for b in replication} != {1903, 1904, 1905}
            or len(discovery) != 10 or len(replication) != 15):
        raise RuntimeError("Incomplete discovery or replication cohort; no pooled analysis allowed.")
    summaries = cohort_summaries(baseline, discovery, replication, plan.candidates)
    contrasts = secondary_contrasts(baseline, replication, "replication")
    contrasts += secondary_contrasts(baseline, discovery, "discovery")
    write_table(output / "cohort_summary.csv", summaries)
    write_table(output / "prespecified_secondary_contrasts.csv", contrasts)
    result = {"status": "completed", "primary_horizon": 40000,
              "replication": [r for r in summaries if r["cohort"] == "replication"],
              "discovery": [r for r in summaries if r["cohort"] == "discovery"],
              "combined_descriptive": [r for r in summaries if r["cohort"] == "combined_descriptive"],
              "prespecified_secondary_contrasts": contrasts,
              "frozen_analysis_plan": frozen_plan,
              "limits": ["One original pretrained policy; no original-seed generalization.",
                         "Ranges and repeat signs describe observed variability; they are not confidence intervals.",
                         "Secondary contrasts were identified in discovery and fixed before these new repeats.",
                         "Evaluation states are reused across candidates, checkpoints and repeats.",
                         "No automatic significance claim or outcome-dependent experiment extension."]}
    write_json(output / "replication_summary.json", result)
    return {"replication_repeats": 3, "discovery_repeats": 2, "original_pretraining_seeds": 1,
            "cohort_summary_rows": len(summaries), "secondary_contrast_rows": len(contrasts)}
