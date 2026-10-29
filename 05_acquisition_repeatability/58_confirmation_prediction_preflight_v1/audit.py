"""Audit frozen forecasts and weighted binary-label bounds; no fitting or RL."""
import math
from collections import defaultdict
from statistics import fmean
from record import HERE, ROOT, Run, csvout, dump, read, rows, sha


def main():
    run = Run("audit")
    try:
        cfg = read(HERE / "audit_config.json")
        protocol = read(HERE / "protocol.json")
        run.input(HERE / "protocol.json")
        for name, digest in [
            ("frozen_reference_predictions.csv", cfg["prediction_sha256"]),
            ("proposed_jobs.csv", cfg["jobs_sha256"]),
            ("paired_outcomes.csv", protocol["reference_csv_sha256"]),
            ("state_manifest.json", protocol["state_manifest_sha256"]),
        ]:
            run.input(HERE / "inputs" / name, digest)
        raw = rows(HERE / "inputs" / "frozen_reference_predictions.csv")
        data = rows(HERE / "inputs" / "paired_outcomes.csv")
        reference = {(int(r["parent"]), int(r["prefix"]), r["task"], int(r["case"])): r for r in data}
        parsed = []
        for r in raw:
            z = {**r}
            for field in ["parent", "prefix", "case", "common_difficulty_count", "state_reference_successes"]:
                z[field] = int(z[field])
            z["focus"] = z["focus"] == "True"
            z["M0"], z["M1"] = float(z["M0"]), float(z["M1"])
            z["delta"] = z["M1"] - z["M0"]
            z["changed"] = abs(z["delta"]) > cfg["tolerance"]
            key = (z["parent"], z["prefix"], z["task"], z["case"])
            source = reference[key]
            run.check(all(reference[z["parent"], s, z["task"], z["case"]]["J8"] == "0" for s in protocol["prefixes"]), "common_failure:" + str(key))
            run.check((z["seed"], z["initial_state_hash"]) == (source["seed"], source["initial_state_hash"]), "identity:" + str(key))
            run.check(z["focus"] == (z["task"] in protocol["focus_tasks"]), "focus:" + str(key))
            run.check(0 <= z["M0"] <= 1 and 0 <= z["M1"] <= 1, "probability:" + str(key))
            run.check(math.isfinite(z["M0"]) and math.isfinite(z["M1"]), "finite:" + str(key))
            for y in [0, 1]:
                linear = 2 * z["delta"] * (y - z["M0"]) - z["delta"] ** 2
                squared = (y - z["M0"]) ** 2 - (y - z["M1"]) ** 2
                run.near(linear, squared, "gain_identity:" + str((key, y)))
            z["gain_if_y0"] = -2 * z["delta"] * z["M0"] - z["delta"] ** 2
            z["gain_if_y1"] = 2 * z["delta"] * (1 - z["M0"]) - z["delta"] ** 2
            z["G_upper"] = max(z["gain_if_y0"], z["gain_if_y1"])
            z["G_lower"] = min(z["gain_if_y0"], z["gain_if_y1"])
            z["upper_bound_label_not_forecast"] = 1 if z["delta"] > 0 else 0
            parsed.append(z)
        keys = [(r["parent"], r["prefix"], r["task"], r["case"]) for r in parsed]
        run.check(len(keys) == len(set(keys)) == 2494, "unique_2494_predictions")
        cases, bins = defaultdict(list), defaultdict(list)
        for r in parsed:
            cases[r["parent"], r["task"], r["case"]].append(r)
            bins[r["parent"], r["task"], r["prefix"], r["common_difficulty_count"]].append(r)
        case_rows, grade_rows = [], []
        max_case_error = max_bin_error = 0.0
        for key, group in sorted(cases.items()):
            group.sort(key=lambda r: r["prefix"])
            run.check([r["prefix"] for r in group] == protocol["prefixes"], "both_states:" + str(key))
            err = abs(fmean(r["M1"] for r in group) - fmean(r["M0"] for r in group))
            run.check(err < cfg["tolerance"], "case_mean:" + str(key))
            max_case_error = max(max_case_error, err)
            case_rows.append({"parent": key[0], "task": key[1], "case": key[2], "grade": group[0]["common_difficulty_count"], "focus": group[0]["focus"], "changed": any(r["changed"] for r in group), "M0_state1": group[0]["M0"], "M1_state1": group[0]["M1"], "M0_state2": group[1]["M0"], "M1_state2": group[1]["M1"], "delta_state1": group[0]["delta"], "delta_state2": group[1]["delta"], "case_mean_absolute_error": err})
        for key, group in sorted(bins.items()):
            err = abs(fmean(r["M1"] for r in group) - fmean(r["M0"] for r in group))
            run.check(err < cfg["tolerance"], "state_grade_mean:" + str(key))
            max_bin_error = max(max_bin_error, err)
            grade_rows.append({"parent": key[0], "task": key[1], "prefix": key[2], "grade": key[3], "N_cases": len(group), "changed_predictions": sum(r["changed"] for r in group), "mean_M0": fmean(r["M0"] for r in group), "mean_M1": fmean(r["M1"] for r in group), "mean_absolute_error": err})
        support, parents, observations = [], [], []
        primary = [r for r in parsed if r["focus"]]
        primary_cases = [r for r in case_rows if r["focus"]]
        for p in protocol["parents"]:
            pp = [r for r in primary if r["parent"] == p]
            Np = len(pp) // 2
            run.check(Np > 0 and len(pp) == 2 * Np, "parent_denominator:" + str(p))
            for t in protocol["tasks"]:
                group = [r for r in parsed if r["parent"] == p and r["task"] == t]
                N = len(group) // 2
                changes = sum(r["changed"] for r in group)
                support.append({"parent": p, "task": t, "focus": t in protocol["focus_tasks"], "eligible_cases": N, "changed_cases": changes // 2, "changed_predictions": changes, "parent_primary_cases": Np, "G_task_weight_within_parent": N / Np if t in protocol["focus_tasks"] else None, "G_task_lower_conditional": fmean(r["G_lower"] for r in group) if N else None, "G_task_upper_conditional": fmean(r["G_upper"] for r in group) if N else None})
            parent = {"parent": p, "N_focus": Np, "changed_cases": sum(r["changed"] for r in pp) // 2, "changed_predictions": sum(r["changed"] for r in pp), "G_lower": fmean(r["G_lower"] for r in pp), "G_upper": fmean(r["G_upper"] for r in pp), "mean_abs_delta_all": fmean(abs(r["delta"]) for r in pp), "max_abs_delta": max(abs(r["delta"]) for r in pp)}
            parents.append(parent)
            for r in pp:
                observations.append({"parent": p, "prefix": r["prefix"], "task": r["task"], "case": r["case"], "grade": r["common_difficulty_count"], "M0": r["M0"], "M1": r["M1"], "delta": r["delta"], "G_lower": r["G_lower"], "G_upper": r["G_upper"], "upper_bound_label_not_forecast": r["upper_bound_label_not_forecast"], "overall_weight_after_averaging_two_futures": 1 / (5 * 2 * Np)})
        run.near(sum(r["overall_weight_after_averaging_two_futures"] for r in observations), 1, "G_weights_sum_one")
        bounds = []
        for excluded in [None, *protocol["parents"]]:
            retained = [r for r in parents if r["parent"] != excluded]
            lower, upper = fmean(r["G_lower"] for r in retained), fmean(r["G_upper"] for r in retained)
            required = 0.001 if excluded is None else 0.0
            bounds.append({"scope": "overall" if excluded is None else "without_" + str(excluded), "excluded_parent": excluded, "parent_count": len(retained), "G_lower": lower, "G_upper": upper, "applicable_threshold": required, "strict_greater_required": excluded is not None, "threshold_algebraically_possible": upper >= required if excluded is None else upper > required, "upper_above_0_001_descriptive_only_for_LOPO": upper >= 0.001})
        changed = [r for r in primary if r["changed"]]
        correction = {
            "focus_cases": len(primary_cases), "changed_cases": len(changed) // 2,
            "changed_case_fraction": len(changed) / len(primary),
            "changed_parent_ids": sorted({r["parent"] for r in changed}),
            "changed_tasks": sorted({r["task"] for r in changed}),
            "mean_abs_delta_all_state_rows": fmean(abs(r["delta"]) for r in primary),
            "mean_abs_delta_changed_state_rows": fmean(abs(r["delta"]) for r in changed),
            "rms_delta_all_state_rows": math.sqrt(fmean(r["delta"] ** 2 for r in primary)),
            "min_abs_delta_changed": min(abs(r["delta"]) for r in changed),
            "max_abs_delta_changed": max(abs(r["delta"]) for r in changed),
            "parent_equal_mean_abs_delta_all": fmean(r["mean_abs_delta_all"] for r in parents),
        }
        for name, values in [("case_corrections.csv", case_rows), ("grade_constraints.csv", grade_rows), ("parent_task_support.csv", support), ("parent_g_bounds.csv", parents), ("observation_g_bounds.csv", observations), ("g_bounds.csv", bounds)]:
            csvout(run.out / name, values)
        weighted_upper = sum(r["G_upper"] * r["overall_weight_after_averaging_two_futures"] for r in observations)
        run.near(weighted_upper, bounds[0]["G_upper"], "row_weights_equal_parent_aggregation")
        run.check(len(primary_cases) == 548 and len(changed) == 98, "primary_support_matches_locked_file")
        run.check(correction["changed_tasks"] == ["PU"], "all_primary_corrections_are_PU")
        run.check(all(r["threshold_algebraically_possible"] for r in bounds), "overall_and_LOPO_G_not_structurally_impossible")
        run.check(not protocol["execution_authorized"] and not protocol["scheduled"], "no_launch_or_queue_authorization")
        run.check(sha(ROOT / cfg["previous_version"] / "protocol.json") == cfg["previous_protocol_sha256"], "57_protocol_unchanged")
        summary = {"status": "locked_prediction_audit_complete_no_confirmation_outcomes", "prediction_sha256": cfg["prediction_sha256"], "correction": correction, "overall_G_lower": bounds[0]["G_lower"], "overall_G_upper": bounds[0]["G_upper"], "minimum_LOPO_G_upper": min(r["G_upper"] for r in bounds[1:]), "overall_G_upper_share_parent41011": next(r["G_upper"] for r in parents if r["parent"] == 41011) / sum(r["G_upper"] for r in parents), "max_case_mean_error": max_case_error, "max_state_grade_mean_error": max_bin_error, "probability_min": min(min(r["M0"], r["M1"]) for r in parsed), "probability_max": max(max(r["M0"], r["M1"]) for r in parsed), "bounds_are_not_power_or_real_policy_reachability": True, "D_or_G_measured_on_F3_F4": False}
        dump(run.out / "summary.json", summary)
        return run.finish(summary)
    except BaseException as exc:
        return run.finish(exc=exc)


if __name__ == "__main__":
    raise SystemExit(main())
