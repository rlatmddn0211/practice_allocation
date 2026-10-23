"""Independent exact-fraction audit via isotonic min-max characterization.

Does not import audit.py or the version-57 model. No new labels or RL.
"""
import itertools
import sys
from fractions import Fraction as F
from record import HERE, ROOT, Run, dump, read, rows, sha


def isotonic_minmax(successes, totals):
    return [max(min(F(sum(successes[a:b + 1]), sum(totals[a:b + 1])) for b in range(i, len(successes))) for a in range(i + 1)) for i in range(len(successes))]


def main():
    run = Run("verify")
    try:
        audited = __import__("pathlib").Path(sys.argv[1]).resolve()
        cfg = read(HERE / "audit_config.json")
        protocol = read(HERE / "protocol.json")
        run.input(HERE / "protocol.json", "438d2b23889c1242319f1592b86e0ff3ca2fa462992db6a3c9d41e669e8ffc7c")
        for name, digest in [("frozen_reference_predictions.csv", cfg["prediction_sha256"]), ("paired_outcomes.csv", protocol["reference_csv_sha256"]), ("proposed_jobs.csv", cfg["jobs_sha256"])]:
            run.input(HERE / "inputs" / name, digest)
        for name in ["summary.json", "parent_g_bounds.csv", "g_bounds.csv", "parent_task_support.csv", "observation_g_bounds.csv"]:
            run.input(audited / name)
        for name, digest in read(audited / "source_hashes.json").items():
            run.check(sha(audited / "source_snapshot" / name) == digest, "audit_source_snapshot:" + name)
        key = lambda r: (int(r["parent"]), int(r["prefix"]), r["task"], int(r["case"]))
        ref = {key(r): r for r in rows(HERE / "inputs" / "paired_outcomes.csv")}
        saved = {key(r): r for r in rows(HERE / "inputs" / "frozen_reference_predictions.csv")}
        obs = {key(r): r for r in rows(audited / "observation_g_bounds.csv")}
        exact, eligible_counts = {}, {}
        for parent, task in itertools.product(protocol["parents"], protocol["tasks"]):
            cases = [i for i in range(100) if all(ref[parent, s, task, i]["J8"] == "0" for s in protocol["prefixes"])]
            eligible_counts[parent, task] = len(cases)
            k = {s: {i: int(ref[parent, s, task, i]["old_J40"]) + int(ref[parent, s, task, i]["new_J40"]) for i in cases} for s in protocol["prefixes"]}
            c = {i: k[4201][i] + k[4202][i] for i in cases}
            groups = {g: [i for i in cases if c[i] == g] for g in sorted(set(c.values()))}
            baseline = {}
            for state in protocol["prefixes"]:
                successes = [sum(k[state][i] for i in members) + 1 for members in groups.values()]
                totals = [2 * len(members) + 2 for members in groups.values()]
                baseline[state] = dict(zip(groups, isotonic_minmax(successes, totals)))
            for grade, members in groups.items():
                center = F(sum(k[4201][i] for i in members), 2 * len(members))
                h = {i: F(k[4201][i], 2) - center for i in members}
                constraints = [F(1, 4)]
                for state, sign in [(4201, 1), (4202, -1)]:
                    p = baseline[state][grade]
                    for i in members:
                        direction = sign * h[i]
                        if direction > 0:
                            constraints.append((1 - p) / direction)
                        if direction < 0:
                            constraints.append(p / -direction)
                shrinkage = min(constraints)
                for state, sign in [(4201, 1), (4202, -1)]:
                    fitted = []
                    for i in members:
                        p = baseline[state][grade]
                        q = p + shrinkage * sign * h[i]
                        ident = parent, state, task, i
                        z = saved[ident]
                        run.near(z["M0"], p, "isotonic_minmax_M0:" + str(ident))
                        run.near(z["M1"], q, "exact_M1:" + str(ident))
                        run.check(int(z["common_difficulty_count"]) == grade and int(z["state_reference_successes"]) == k[state][i], "reference_features:" + str(ident))
                        run.check(0 <= q <= 1, "exact_probability:" + str(ident))
                        exact[ident] = (p, q)
                        fitted.append(q)
                        if task in protocol["focus_tasks"]:
                            values = [F(y - p) ** 2 - F(y - q) ** 2 for y in [0, 1]]
                            run.near(obs[ident]["G_upper"], max(values), "exact_row_upper:" + str(ident))
                            run.near(obs[ident]["G_lower"], min(values), "exact_row_lower:" + str(ident))
                    run.check(sum(fitted) == len(members) * baseline[state][grade], "exact_state_grade_mean:" + str((parent, task, state, grade)))
                for i in members:
                    run.check(sum(exact[parent, state, task, i][1] for state in protocol["prefixes"]) == sum(exact[parent, state, task, i][0] for state in protocol["prefixes"]), "exact_case_mean:" + str((parent, task, i)))
        run.check(set(exact) == set(saved), "all_2494_forecasts_reconstructed")
        exact_bounds = {}
        parent_rows = {int(r["parent"]): r for r in rows(audited / "parent_g_bounds.csv")}
        for parent in protocol["parents"]:
            values = [(p, q) for (pp, state, task, case), (p, q) in exact.items() if pp == parent and task in protocol["focus_tasks"]]
            N = sum(eligible_counts[parent, t] for t in protocol["focus_tasks"])
            run.check(len(values) == 2 * N == 2 * int(parent_rows[parent]["N_focus"]), "exact_parent_N:" + str(parent))
            lower = sum(min(p * p - q * q, (1 - p) ** 2 - (1 - q) ** 2) for p, q in values) / (2 * N)
            upper = sum(max(p * p - q * q, (1 - p) ** 2 - (1 - q) ** 2) for p, q in values) / (2 * N)
            exact_bounds[parent] = lower, upper
            run.near(parent_rows[parent]["G_lower"], lower, "exact_parent_lower:" + str(parent))
            run.near(parent_rows[parent]["G_upper"], upper, "exact_parent_upper:" + str(parent))
            run.check(sum(p != q for p, q in values) // 2 == int(parent_rows[parent]["changed_cases"]), "exact_changed_cases:" + str(parent))
        for r in rows(audited / "g_bounds.csv"):
            excluded = int(r["excluded_parent"]) if r["excluded_parent"] else None
            selected = [value for p, value in exact_bounds.items() if p != excluded]
            for j, field in enumerate(["G_lower", "G_upper"]):
                run.near(r[field], sum(value[j] for value in selected) / len(selected), "exact_aggregate:" + r["scope"] + "/" + field)
            expected_threshold = F(1, 1000) if excluded is None else F(0)
            run.near(r["applicable_threshold"], expected_threshold, "gate_threshold:" + r["scope"])
        for r in rows(audited / "parent_task_support.csv"):
            parent, task = int(r["parent"]), r["task"]
            run.check(int(r["eligible_cases"]) == eligible_counts[parent, task], "task_support:" + str((parent, task)))
            if task in protocol["focus_tasks"]:
                run.near(r["G_task_weight_within_parent"], F(eligible_counts[parent, task], sum(eligible_counts[parent, t] for t in protocol["focus_tasks"])), "task_weight:" + str((parent, task)))
        summary = read(audited / "summary.json")
        focus = [(ident, p, q) for ident, (p, q) in exact.items() if ident[2] in protocol["focus_tasks"]]
        differing = [(ident, p, q) for ident, p, q in focus if p != q]
        run.check(len(focus) == 1096 and len(differing) == 98, "exact_total_changed_support")
        run.check({ident[2] for ident, p, q in differing} == {"PU"}, "no_DC_forecast_difference")
        exact_mean_abs = sum(abs(q - p) for ident, p, q in focus) / len(focus)
        run.near(summary["correction"]["mean_abs_delta_all_state_rows"], exact_mean_abs, "correction_magnitude")
        run.check(exact_bounds[41012] == (0, 0) and exact_bounds[41014] == (0, 0), "identical_parent_models_not_empirical_null")
        old = read(ROOT / cfg["previous_version"] / "protocol.json")
        run.check(sha(ROOT / cfg["previous_version"] / "protocol.json") == cfg["previous_protocol_sha256"], "57_protocol_preserved")
        for field in ["models", "uncertainty", "learning_proposal", "budget_proposal", "primary_D", "second_bundle"]:
            run.check(protocol[field] == old[field], "frozen_design_preserved:" + field)
        for field, value in old["proposed_investment_gate"].items():
            run.check(protocol["proposed_investment_gate"][field] == value, "original_gate_preserved:" + field)
        jobs = rows(HERE / "inputs" / "proposed_jobs.csv")
        run.check(len(jobs) == 20 and sum(int(r["training_steps"]) for r in jobs) == 640000 and sum(int(r["evaluation_cap"]) for r in jobs) == 4000000, "unchanged_budget_and_jobs")
        run.check(not protocol["execution_authorized"] and not protocol["scheduled"], "no_new_execution")
        dump(run.out / "exact_bounds.json", {str(parent): {"lower_fraction": str(value[0]), "upper_fraction": str(value[1])} for parent, value in exact_bounds.items()})
        return run.finish({"status": "independent_exact_audit_passed_no_confirmation", "audited": str(audited), "all_prediction_rows": len(exact), "primary_cases": len(focus) // 2, "changed_primary_cases": len(differing) // 2, "method": "exact Fraction isotonic minmax, direct squared-error bounds and independent weights", "launch_or_queue_created": False})
    except BaseException as exc:
        return run.finish(exc=exc)


if __name__ == "__main__":
    raise SystemExit(main())
