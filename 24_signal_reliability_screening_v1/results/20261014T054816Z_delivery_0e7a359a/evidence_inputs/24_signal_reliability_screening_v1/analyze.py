"""F07 retrospective analysis. Reads frozen episodes; never imports an RL learner."""
from __future__ import annotations

import csv
import hashlib
import itertools
import json
import platform
import shutil
import sys
import time
import traceback
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import scipy
from scipy.special import ndtr

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def digest(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def save(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def table(path, rows):
    if not rows:
        return
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("x", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def grouped_mean(rows, keys, fields):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[k] for k in keys)].append(row)
    return [dict(zip(keys, key), **{f: float(np.mean([r[f] for r in values])) for f in fields})
            for key, values in sorted(groups.items())]


def paired_gate(differences, per_repeat_gaps, rule):
    """differences: draws x task x case, after averaging diagnostic continuations."""
    n = differences.shape[-1]
    k = per_repeat_gaps.shape[1]
    support = np.linspace(-1, 1, 2 * k + 1)
    prior = rule["symmetric_dirichlet_prior_total"]
    mean_t = differences.sum(-1) / (n + prior)
    second_t = ((differences ** 2).sum(-1) + prior * np.mean(support ** 2)) / (n + prior)
    var_t = np.maximum(0, second_t - mean_t ** 2) / (n + prior + 1)
    post_mean = mean_t.mean(1)
    post_sd = np.sqrt(var_t.sum(1)) / differences.shape[1]
    raw_gap = differences.mean((1, 2))
    lower = post_mean - rule["lower_score_z"] * post_sd
    passed = ((raw_gap >= rule["raw_gap_min_pp"] / 100 - 1e-12)
              & (lower > 0) & (per_repeat_gaps > 1e-12).all(1))
    return passed, ndtr(post_mean / post_sd), lower


def main():
    started, cpu_started = time.perf_counter(), time.process_time()
    output = HERE / "results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    shutil.copy2(__file__, output / "analysis_source.py")
    shutil.copy2(HERE / "protocol.json", output / "protocol.json")
    inputs, checks = {}, []
    summary = {"status": "running", "new_environment_steps": 0, "new_learner_updates": 0}

    def check(name, passed, details=None):
        checks.append({"name": name, "passed": bool(passed), "details": details})
        if not passed:
            raise AssertionError(name)

    def hashed(path):
        path = Path(path)
        value = digest(path)
        if str(path) in inputs:
            check("input stable: " + str(path), inputs[str(path)] == value)
        inputs[str(path)] = value
        return value

    def read(path):
        hashed(path)
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))

    def rows(path):
        hashed(path)
        with Path(path).open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))

    try:
        p = read(HERE / "protocol.json")
        hashed(Path(__file__))
        active = read(ROOT / "13_e0_e3_autonomous_queue_v1/ACTIVE_CAMPAIGN.json")
        campaign = Path(active["campaign"])
        plan = read(campaign / "plan.json")
        check("frozen campaign plan", inputs[str(campaign / "plan.json")] == read(campaign / "plan_integrity.json")["sha256"])
        planned = {j["id"]: j for j in plan["jobs"]}
        tasks = p["suites"]
        contexts = [(suite, seed, cp) for suite in tasks for seed in p["original_seeds"] for cp in p["checkpoints"][suite]]
        arrays = {c: np.full((2, 3, 5, 4, 100), np.nan) for c in contexts}
        lengths = {c: np.zeros((2, 3, 5, 4, 100), dtype=np.int16) for c in contexts}
        bases, records, splits, banks = {}, [], {}, {}
        raw_episode_count = 0

        def record(job_id):
            marker = read(campaign / "completed" / (job_id + ".json"))
            path = Path(marker["result_ref"]["path"])
            rec = read(path)
            check("result hash: " + job_id, inputs[str(path)] == marker["result_ref"]["sha256"])
            check("planned result: " + job_id, rec["id"] == job_id and rec["stage"] == planned[job_id]["stage"])
            return rec, path

        for suite in tasks:
            stage = "E1" if suite == "A" else "E3"
            rec, _ = record(f"{stage}_{suite}_bank")
            bank = read(rec["bank"]["path"])
            check("bank hash: " + suite, inputs[rec["bank"]["path"]] == rec["bank"]["sha256"])
            entries = {(e["task"], e["episode_index"]): e for e in bank["outcome"]}
            check("outcome bank size: " + suite, len(entries) == 400)
            banks[suite] = entries
            dindices, oindices = [], []
            for task in tasks[suite]:
                ordered = sorted(range(100), key=lambda i: hashlib.sha256(
                    ("F07-v1|" + suite + "|" + task + "|" + entries[task, i]["initial_state_hash"]).encode()).hexdigest())
                dindices.append(ordered[:50])
                oindices.append(ordered[50:])
                check("disjoint D/O: " + suite + ":" + task, not set(ordered[:50]) & set(ordered[50:]) and len(set(ordered)) == 100)
            splits[suite] = (np.array(dindices), np.array(oindices))
        save(output / "case_splits.json", {s: {"D": d.tolist(), "O": o.tolist(), "tasks": tasks[s]} for s, (d, o) in splits.items()})

        def load_evaluation(job_id):
            nonlocal raw_episode_count
            rec, path = record(job_id)
            req = read(path.parent / "request.json")
            check("outcome nonmutating evaluation: " + job_id,
                  rec["kind"] == "evaluate" and rec["evaluation_state_unchanged"]
                  and req["bank_kind"] == "outcome" and req["technical_smoke"] is False)
            episode = rows(rec["episodes_path"])
            check("episode hash: " + job_id, inputs[rec["episodes_path"]] == rec["episodes_sha256"])
            success = np.full((4, 100), np.nan)
            duration = np.zeros((4, 100), dtype=np.int16)
            for e in episode:
                t, i = tasks[rec["suite"]].index(e["task"]), int(e["episode_index"])
                bankcase = banks[rec["suite"]][e["task"], i]
                if not (int(e["seed"]) == bankcase["seed"] and e["initial_state_hash"] == bankcase["initial_state_hash"]
                        and np.isnan(success[t, i]) and e["bank"] == "outcome"):
                    raise AssertionError("episode identity or duplicate: " + job_id)
                success[t, i], duration[t, i] = int(e["success"]), int(e["length"])
            check("complete binary cases and valid lengths: " + job_id,
                  len(episode) == 400 and np.isin(success, [0, 1]).all()
                  and ((duration >= 1) & (duration <= 500)).all() and (duration[success == 0] == 500).all())
            check("reconciled outcome and cost: " + job_id,
                  abs(success.mean() - rec["evaluation"]["macro_success"]) < 1e-12
                  and int(duration.sum()) == rec["evaluation"]["environment_steps"])
            for ti, task in enumerate(tasks[rec["suite"]]):
                check("task count: " + job_id + ":" + task, int(success[ti].sum()) == rec["evaluation"]["success_counts"][task])
            raw_episode_count += len(episode)
            records.append({"id": job_id, "suite": rec["suite"], "original_seed": rec["original_seed"],
                            "checkpoint_step": rec["checkpoint_step"], "role": rec["role"],
                            "horizon": rec.get("horizon", 0), "continuation_label": rec.get("continuation_label", 0),
                            "allocation": rec.get("allocation", "parent"), "macro_pct": float(success.mean() * 100),
                            "evaluation_environment_steps": int(duration.sum()), "episodes_path": rec["episodes_path"],
                            "episode_sha256": rec["episodes_sha256"]})
            return success, duration

        for ctx in contexts:
            suite, seed, cp = ctx
            stage = "E1" if suite == "A" else "E3"
            prefix = f"{stage}_{suite}_s{seed}_c{cp // 1000}"
            bases[ctx], _ = load_evaluation(prefix + "_base")
            names = ["U"] + ["F_" + t for t in tasks[suite]]
            for hi, h in enumerate(p["horizons"]):
                for ri, repeat in enumerate(p["continuations"][suite]):
                    for ai, allocation in enumerate(names):
                        arrays[ctx][hi, ri, ai], lengths[ctx][hi, ri, ai] = load_evaluation(
                            prefix + f"_r{repeat}_{allocation}_e{h // 1000}")
            print("loaded " + str(ctx), flush=True)
        check("12 contexts and 148800 raw episodes", len(arrays) == 12 and raw_episode_count == 148800)
        table(output / "evaluations.csv", records)

        # Independent reconciliation against earlier scalar calculations.
        old_a = rows(ROOT / "16_e0_e2_results_analysis_v1/results/20261012T065024Z_70db8b08/branch_recomputed.csv")
        old_bc = rows(ROOT / "21_e3_completed_results_analysis_v1/results/20261014T024817Z_ca372238/branch_recomputed.csv")
        for old in [r for r in old_a if r["stage"] == "E1"] + old_bc:
            suite = old.get("suite", "A")
            ctx = (suite, int(old["original_seed"]), int(old["checkpoint_step"]))
            hi = p["horizons"].index(int(old["horizon"]))
            ri = p["continuations"][suite].index(int(old["continuation_label"]))
            ai = (["U"] + ["F_" + t for t in tasks[suite]]).index(old["allocation"])
            check("prior macro: " + str((ctx, hi, ri, ai)), abs(arrays[ctx][hi, ri, ai].mean() * 100 - float(old["macro_pct"])) < 1e-9)

        # Boundary tests for the gate's intended behavior; all have positive uncertainty.
        for k in [1, 2]:
            zero = np.zeros((1, 4, 2))
            yes, prob, lower = paired_gate(zero, np.zeros((1, k)), p["reliability_rule"])
            check(f"zero paired gap does not pass; k={k}", not yes[0] and prob[0] == 0.5 and lower[0] < 0)
            yes, _, _ = paired_gate(np.ones((1, 4, 20)), np.ones((1, k)), p["reliability_rule"])
            check(f"consistent very large advantage passes; k={k}", yes[0])

        rng_boot = np.random.default_rng(p["bootstrap_seed"])
        pair_rows, context_rows = [], []
        for ctx, y in arrays.items():
            suite, seed, cp = ctx
            names = ["U"] + ["F_" + t for t in tasks[suite]]
            weights = rng_boot.multinomial(100, np.full(100, .01), size=(p["bootstrap_draws"], 4))
            boot = np.einsum("hrati,bti->bhra", y, weights, optimize=True).mean(2) / 400 * 100
            means = y.mean((1, 3, 4)) * 100
            pairs = list(itertools.combinations(range(5), 2))
            point = np.array([means[:, a] - means[:, b] for a, b in pairs]).T
            draws = np.stack([boot[:, :, a] - boot[:, :, b] for a, b in pairs], axis=-1)
            ses = np.array([[100 * np.sqrt(np.var((y[h, :, a] - y[h, :, b]).mean(0), axis=1, ddof=1).sum() / 1600)
                             for a, b in pairs] for h in range(2)])
            z = np.where(ses[None] > 1e-12, np.abs(draws - point) / np.maximum(ses[None], 1e-12), 0)
            critical = float(np.quantile(z.max((1, 2)), .95))
            cis = np.quantile(draws, [.025, .975], axis=0)
            for pi, (a, b) in enumerate(pairs):
                ds = y[:, :, a] - y[:, :, b]
                repeat_values = ds.mean((2, 3)) * 100
                single_se = 100 * np.sqrt(np.var(ds[1], axis=2, ddof=1).sum(1) / 1600)
                reverse = point[0, pi] * point[1, pi] < -1e-12
                lo, hi = point[:, pi] - critical * ses[:, pi], point[:, pi] + critical * ses[:, pi]
                pointwise_reverse = ((cis[0, 0, pi] > 0 and cis[1, 1, pi] < 0)
                                     or (cis[1, 0, pi] < 0 and cis[0, 1, pi] > 0))
                simultaneous_reverse = ((lo[0] > 0 and hi[1] < 0) or (hi[0] < 0 and lo[1] > 0)) and (ses[:, pi] > 1e-12).all()
                pair_rows.append({"suite": suite, "original_seed": seed, "checkpoint_step": cp,
                                  "allocation_a": names[a], "allocation_b": names[b],
                                  "difference_20k_pp": float(point[0, pi]), "difference_40k_pp": float(point[1, pi]),
                                  "reversed": bool(reverse), "material_reversed_2pp": bool(reverse and (np.abs(point[:, pi]) >= 2).all()),
                                  "pointwise_case_robust_reversal": bool(pointwise_reverse),
                                  "simultaneous_case_robust_reversal": bool(simultaneous_reverse),
                                  "case_ci20_low": float(cis[0, 0, pi]), "case_ci20_high": float(cis[1, 0, pi]),
                                  "case_ci40_low": float(cis[0, 1, pi]), "case_ci40_high": float(cis[1, 1, pi]),
                                  "simultaneous_ci20_low": float(lo[0]), "simultaneous_ci20_high": float(hi[0]),
                                  "simultaneous_ci40_low": float(lo[1]), "simultaneous_ci40_high": float(hi[1]),
                                  "observed_continuation_sd_40_pp": float(repeat_values[1].std(ddof=1)),
                                  "rms_single_continuation_case_se_40_pp": float(np.sqrt(np.mean(single_se ** 2))),
                                  "mean_three_continuations_case_se_40_pp": float(ses[1, pi]),
                                  "individual_continuations_reversed": int((repeat_values[0] * repeat_values[1] < -1e-12).sum())})
            context_rows.append({"suite": suite, "original_seed": seed, "checkpoint_step": cp,
                                 "winner20": names[int(means[0].argmax())], "winner40": names[int(means[1].argmax())],
                                 "winner_same": bool(means[0].argmax() == means[1].argmax()),
                                 "boundary_task_policy_cells": int(((y.sum(-1) == 0) | (y.sum(-1) == 100)).sum()),
                                 "total_task_policy_cells": int(np.prod(y.shape[:-1]))})
        table(output / "horizon_pairs.csv", pair_rows)
        table(output / "contexts.csv", context_rows)
        print("conditional horizon and variation analysis completed", flush=True)

        # Fixed splits and random subsets are shared by policies and by seed/checkpoint.
        drng = np.random.default_rng(p["subset_seed"])
        permutations = {s: np.argsort(drng.random((p["subset_draws"], 4, 50)), axis=-1) for s in tasks}
        ddata, odata, dlength = {}, {}, {}
        for ctx, y in arrays.items():
            di, oi = splits[ctx[0]]
            ddata[ctx] = np.take_along_axis(y, di[None, None, None, :, :], axis=-1)
            odata[ctx] = np.take_along_axis(y, oi[None, None, None, :, :], axis=-1)
            dlength[ctx] = np.take_along_axis(lengths[ctx], di[None, None, None, :, :], axis=-1)
        decisions, calibration, defaults = [], [], []
        draws_count = p["subset_draws"]
        draw_ids = np.arange(draws_count)
        for ctx in contexts:
            suite, seed, cp = ctx
            names = ["U"] + ["F_" + t for t in tasks[suite]]
            others = [c for c in contexts if c[0] == suite and c[2] == cp and c[1] != seed]
            check("fixed fallback excludes original seed: " + str(ctx), len(others) == 2 and all(c[1] != seed for c in others))
            fixed_scores = np.mean([ddata[c][1].mean((0, 2, 3)) for c in others], axis=0)
            fixed = int(fixed_scores.argmax())
            defaults.append({"suite": suite, "original_seed": seed, "checkpoint_step": cp, "allocation": names[fixed], "training_original_seeds": [c[1] for c in others]})
            base_o = np.take_along_axis(bases[ctx], splits[suite][1], axis=-1).mean(1)
            for held in range(3):
                donors = [r for r in range(3) if r != held]
                for mode in p["modes"]:
                    source_h = 1 if mode == "cross_repeat_40" else 0
                    donor_ids = [held] if mode == "same_trajectory_20_to_40" else donors
                    target_h = 0 if mode in ("measurement_only_20", "cross_repeat_20") else 1
                    target_ids = donors if mode == "measurement_only_20" else [held]
                    source = ddata[ctx][source_h, donor_ids]
                    source_len = dlength[ctx][source_h, donor_ids]
                    target_task = odata[ctx][target_h, target_ids].mean((0, 3))
                    target = target_task.mean(1)
                    drops = np.maximum(0, base_o[None] - target_task).max(1)
                    full_choice = int(source.mean((0, 2, 3)).argmax())
                    for n in p["small_bank_cases_per_task"]:
                        idx = permutations[suite][:, :, :n]
                        # Explicit broadcasting retains R, draw, allocation, task, case axes.
                        sample = np.take_along_axis(source[:, None, :, :, :], idx[None, :, None, :, :], axis=-1)
                        costs = np.take_along_axis(source_len[:, None, :, :, :], idx[None, :, None, :, :], axis=-1).sum((0, 2, 3, 4))
                        check("diagnostic sample shape: " + str((ctx, held, mode, n)), sample.shape == (len(donor_ids), draws_count, 5, 4, n))
                        avg = sample.mean(0)
                        scores = avg.mean((2, 3))
                        chosen = scores.argmax(1)
                        tie = np.isclose(scores, scores.max(1)[:, None], atol=1e-12, rtol=0).sum(1) > 1
                        selected = {"Uniform": np.zeros(draws_count, dtype=int), "Development_fixed": np.full(draws_count, fixed), "Greedy": chosen}
                        gate_info = {}
                        for label, fallback in [("Uniform", 0), ("Development_fixed", fixed)]:
                            diff = avg[draw_ids, chosen] - avg[:, fallback]
                            repeat_scores = sample.mean((3, 4))
                            repeat_gap = (repeat_scores[:, draw_ids, chosen] - repeat_scores[:, :, fallback]).T
                            passed, confidence, lower = paired_gate(diff, repeat_gap, p["reliability_rule"])
                            gap_pass = scores[draw_ids, chosen] - scores[:, fallback] >= .02 - 1e-12
                            selected["Gap2_" + label] = np.where(gap_pass, chosen, fallback)
                            selected["Reliability_" + label] = np.where(passed, chosen, fallback)
                            gate_info[label] = (passed, confidence, lower)
                        for method in p["methods"]:
                            choice = selected[method]
                            value = target[choice]
                            fallback = 0 if method.endswith("Uniform") or method == "Uniform" else fixed
                            counts = np.bincount(choice, minlength=5)
                            greedy_value = target[chosen]
                            paid = method not in ("Uniform", "Development_fixed")
                            row = {"suite": suite, "original_seed": seed, "checkpoint_step": cp,
                                   "held_continuation": p["continuations"][suite][held], "mode": mode,
                                   "cases_per_task": n, "method": method, "fallback": names[fallback],
                                   "score_pp": float(value.mean() * 100),
                                   "vs_uniform_pp": float((value - target[0]).mean() * 100),
                                   "vs_development_fixed_pp": float((value - target[fixed]).mean() * 100),
                                   "vs_greedy_pp": float((value - greedy_value).mean() * 100),
                                   "vs_gap_only_pp": float((value - target[selected["Gap2_" + ("Uniform" if fallback == 0 and method.endswith("Uniform") else "Development_fixed")]]).mean() * 100),
                                   "absolute_gain_pp": float((value - base_o.mean()).mean() * 100),
                                   "hindsight_regret_pp": float((target.max() - value).mean() * 100),
                                   "within_2pp_of_hindsight_pct": float((value >= target.max() - .02 - 1e-12).mean() * 100),
                                   "switch_from_fallback_pct": float((choice != fallback).mean() * 100),
                                   "future_positive_vs_fallback_pct": float((value > target[fallback] + 1e-12).mean() * 100),
                                   "maximum_task_drop_mean_pp": float(drops[choice].mean() * 100),
                                   "match_full_D_greedy_pct": float((chosen == full_choice).mean() * 100),
                                   "greedy_tie_pct": float(tie.mean() * 100),
                                   "simulated_diagnostic_eval_steps_mean": float(costs.mean()) if paid else 0.,
                                   "simulated_diagnostic_training_steps": float(len(donor_ids) * 5 * p["horizons"][source_h]) if paid else 0.,
                                   **{"choose_" + names[i] + "_pct": float(counts[i] / draws_count * 100) for i in range(5)}}
                            decisions.append(row)
                        if mode == "cross_repeat_20_to_40":
                            _, confidence, _ = gate_info["Development_fixed"]
                            for low, high in [(0, .5), (.5, .8), (.8, .95), (.95, 1.000001)]:
                                mask = (confidence >= low) & (confidence < high) & (chosen != fixed)
                                if mask.any():
                                    calibration.append({"suite": suite, "original_seed": seed, "checkpoint_step": cp,
                                                        "held_continuation": p["continuations"][suite][held], "cases_per_task": n,
                                                        "confidence_low": low, "confidence_high": min(high, 1.),
                                                        "resampling_draws": int(mask.sum()),
                                                        "mean_diagnostic_confidence": float(confidence[mask].mean()),
                                                        "future_positive_pct": float((target[chosen[mask]] > target[fixed] + 1e-12).mean() * 100),
                                                        "future_gain_pp": float((target[chosen[mask]] - target[fixed]).mean() * 100)})
            print("selectors completed " + str(ctx), flush=True)
        table(output / "selection_by_context_repeat.csv", decisions)
        table(output / "development_fixed_choices.csv", defaults)
        table(output / "confidence_to_future_gain.csv", calibration)
        metric_fields = [k for k in decisions[0] if k.endswith(("_pp", "_pct", "_mean", "_steps")) and not k.startswith("choose_")]
        cell_keys = ["mode", "cases_per_task", "method", "suite", "original_seed", "checkpoint_step"]
        cells = grouped_mean(decisions, cell_keys, metric_fields)
        table(output / "selection_by_context.csv", cells)
        by_suite_seed = grouped_mean(cells, ["mode", "cases_per_task", "method", "suite", "original_seed"], metric_fields)
        by_seed = grouped_mean(by_suite_seed, ["mode", "cases_per_task", "method", "original_seed"], metric_fields)
        table(output / "selection_by_original_seed.csv", by_seed)
        pooled = grouped_mean(by_seed, ["mode", "cases_per_task", "method"], metric_fields)
        by_group = grouped_mean(cells, ["mode", "cases_per_task", "method", "suite", "checkpoint_step"], metric_fields)
        table(output / "selection_summary.csv", pooled)
        table(output / "selection_by_group.csv", by_group)
        summary.update({
            "status": "completed", "raw_episode_rows": raw_episode_count, "contexts": len(contexts),
            "original_seed_blocks": p["original_seeds"], "pretrained_policy_histories": 9,
            "branch_evaluations": 360, "baseline_evaluations": 12,
            "observed_horizon_reversals": sum(r["reversed"] for r in pair_rows),
            "allocation_pairs": len(pair_rows),
            "material_2pp_horizon_reversals": sum(r["material_reversed_2pp"] for r in pair_rows),
            "pointwise_case_robust_reversals": sum(r["pointwise_case_robust_reversal"] for r in pair_rows),
            "simultaneous_case_robust_reversals": sum(r["simultaneous_case_robust_reversal"] for r in pair_rows),
            "same_horizon_winner_contexts": sum(r["winner_same"] for r in context_rows),
            "rms_observed_continuation_sd_pp": float(np.sqrt(np.mean([r["observed_continuation_sd_40_pp"] ** 2 for r in pair_rows]))),
            "rms_conditional_single_policy_case_se_pp": float(np.sqrt(np.mean([r["rms_single_continuation_case_se_40_pp"] ** 2 for r in pair_rows]))),
            "pairs_with_continuation_sd_above_case_se": sum(r["observed_continuation_sd_40_pp"] > r["rms_single_continuation_case_se_40_pp"] for r in pair_rows),
            "primary_results": [r for r in pooled if r["mode"] == p["primary"]["mode"] and r["cases_per_task"] == p["primary"]["cases_per_task"]],
            "secondary_results_n20": [r for r in pooled if r["mode"] == p["primary"]["mode"] and r["cases_per_task"] == 20],
            "no_equal_budget_online_claim": True,
        })
        check("all planned selector cells", len(decisions) == 12 * 3 * 5 * 5 * 7)
        check("all numerical selector outputs finite", all(np.isfinite(r[f]) for r in decisions for f in metric_fields))
        check("Uniform self contrast zero", all(abs(r["vs_uniform_pp"]) < 1e-9 for r in decisions if r["method"] == "Uniform"))
        check("preserved source and protocol", digest(Path(__file__)) == inputs[str(Path(__file__))] and digest(HERE / "protocol.json") == inputs[str(HERE / "protocol.json")])
    except Exception:
        summary.update(status="failed", error=traceback.format_exc())
        print(summary["error"], flush=True)
    finally:
        summary.update(wall_seconds=time.perf_counter() - started, cpu_seconds=time.process_time() - cpu_started,
                       python=sys.version, numpy=np.__version__, scipy=scipy.__version__, platform=platform.platform(),
                       checks_total=len(checks), checks_failed=sum(not c["passed"] for c in checks),
                       source_sha256=digest(Path(__file__)), protocol_sha256=digest(HERE / "protocol.json"))
        save(output / "summary.json", summary)
        save(output / "checks.json", checks)
        save(output / "input_hashes.json", inputs)
    print(json.dumps({"output": str(output), "status": summary["status"], "wall_seconds": summary["wall_seconds"]}))
    return 0 if summary["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
