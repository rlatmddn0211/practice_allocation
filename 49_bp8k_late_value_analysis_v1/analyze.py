"""B measurement analysis: three fixed times, no selector fitting or simulation."""
import csv
import hashlib
import io
import itertools
import json
import math
import os
import platform
import shutil
import sys
import time
import traceback
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PARENTS = (41011, 41012, 41013, 41014, 41015)
REPEATS = (4201, 4202)
TASKS = ("DO", "DC", "PU", "BP")
KINDS = ("early", "late", "total")
PATTERNS = tuple(f"{i:03b}" for i in range(8))
POLICIES = ("J0", "J8_4201", "J40_4201", "J8_4202", "J40_4202")


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Run:
    def __init__(self):
        self.start, self.cpu = time.perf_counter(), time.process_time()
        self.path = HERE/"results"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                                    +"_B_analysis_"+uuid.uuid4().hex[:8])
        (self.path/"source_snapshot").mkdir(parents=True, exist_ok=False)
        for p in list(HERE.glob("*.py"))+[HERE/"analysis_config.json"]:
            shutil.copy2(p, self.path/"source_snapshot"/p.name)
        self.inputs, self.checks = {}, []
        self.write("source_hashes.json", {p.name: sha(p.read_bytes()) for p in (self.path/"source_snapshot").iterdir()})

    def check(self, name, condition):
        self.checks.append(dict(check=name, passed=bool(condition)))
        if not condition:
            raise AssertionError(name)

    def data(self, path, expected=None):
        path = Path(path).resolve()
        b = path.read_bytes()
        h = sha(b)
        self.inputs[str(path)] = h
        if expected:
            self.check("hash:"+str(path), h == expected)
        return b

    def js(self, path, expected=None):
        return json.loads(self.data(path, expected).decode("utf-8-sig"))

    def rows(self, path, expected=None):
        return list(csv.DictReader(io.StringIO(self.data(path, expected).decode("utf-8-sig"))))

    def write(self, name, value):
        with (self.path/name).open("x", encoding="utf-8") as f:
            json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)
            f.write("\n")

    def table(self, name, rows):
        with (self.path/name).open("x", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)


def read_inputs(run):
    cfg = run.js(HERE/"analysis_config.json")
    cam = Path(run.js(ROOT/"48_bp8k_checkpoint_evaluation_v1/ACTIVE_CAMPAIGN.json")["campaign"])
    marker = run.js(cam/"COMPLETE.json")
    completion = run.js(marker["summary"]["path"], marker["summary"]["sha256"])
    plan_ref = run.js(cam/"plan_integrity.json")
    plan = run.js(cam/"plan.json", plan_ref["sha256"])
    protocol = plan["protocol"]
    run.check("completed_B_scope", completion["execution_status"] == "completed"
              and completion["policies"] == 10 and completion["new_SAC_updates"] == 0)
    run.check("frozen_analysis", cfg["bootstrap"]["replicates"] == protocol["analysis"]["case_uncertainty"]["replicates"]
              == 20000 and cfg["bootstrap"]["seed"] == protocol["analysis"]["case_uncertainty"]["rng_seed"] == 480202)
    run.check("budget", completion["research_evaluation_steps"] <= 2000000
              and completion["technical_evaluation_steps"] <= 4000)
    inputrefs, costrows, sources = [], [], []
    for b in plan["baselines"]:
        inputrefs.append({**b, "kind": "existing"})
    for job in plan["jobs"]:
        m = run.js(cam/"completed"/(job["id"]+".json"))
        r = run.js(m["result_ref"]["path"], m["result_ref"]["sha256"])
        c = run.js(m["cost_ref"]["path"], m["cost_ref"]["sha256"])
        runtime = run.js(Path(m["attempt"])/"runtime.json")
        request = run.js(Path(m["attempt"])/"request.json")
        before = run.js(Path(m["attempt"])/"restored_fingerprints.json")
        after = run.js(Path(m["attempt"])/"post_evaluation_fingerprints.json")
        run.check("exact_restore_and_no_mutation:"+job["id"],
                  r["full_restore_verified"] and r["evaluation_state_unchanged"] and before == after
                  and r["original_checkpoint_files_unchanged"] and r["absolute_step"] == 208000
                  and c["costs"]["train_iterations"] == 0 and c["status"] == "completed")
        run.check("pinned_source:"+job["id"], request["source_hashes"] == plan["source_hashes"] == runtime["source_hashes"])
        inputrefs.append(dict(original_seed=r["original_seed"], continuation=r["continuation"], horizon=8000,
                              outcome={"path": r["episodes_path"], "sha256": r["episodes_sha256"]}, kind="new_B",
                              actual_steps=c["costs"]["environment_steps"]))
        costrows.append({"id": job["id"], **c})
        sources.append(dict(original_seed=r["original_seed"], continuation=r["continuation"],
                            continuation_rng_seed=r["continuation_rng_seed"], checkpoint=r["checkpoint"],
                            bank=r["bank"], packages=runtime["packages"]))
    bank = {}
    for b in plan["banks"]:
        value = run.js(b["bank"]["path"], b["bank"]["sha256"])
        bank[b["original_seed"]] = {(e["task"], e["episode_index"]): (str(e["seed"]), e["initial_state_hash"])
                                   for e in value["outcome"]}
    y = np.zeros((5, 5, 4, 100), dtype=np.int8)
    coverage, raw, asset_rows = set(), [], []
    for ref in inputrefs:
        p, r, h = ref["original_seed"], ref["continuation"], ref["horizon"]
        policy = "J0" if h == 0 else f"J{h//1000}_{r}"
        pi, qi = PARENTS.index(p), POLICIES.index(policy)
        data = run.rows(ref["outcome"]["path"], ref["outcome"]["sha256"])
        keys = {(d["task"], int(d["episode_index"])) for d in data}
        run.check("O100_coverage:"+str((p, r, h)), len(data) == 400
                  and keys == set(itertools.product(TASKS, range(100))) and (pi, qi) not in coverage)
        coverage.add((pi, qi))
        for d in data:
            t, i = d["task"], int(d["episode_index"])
            run.check("same_case:"+str((p, r, h, t, i)), (d["seed"], d["initial_state_hash"]) == bank[p][t, i])
            run.check("binary_success:"+str((p, r, h, t, i)), d["success"] in ("0", "1"))
            y[pi, qi, TASKS.index(t), i] = int(d["success"])
            raw.append(dict(original_seed=p, continuation=r, horizon=h, policy=policy, **d))
        steps = sum(int(d["length"]) for d in data)
        if ref["kind"] == "new_B":
            run.check("new_cost:"+str((p, r)), steps == ref["actual_steps"])
        asset_rows.append(dict(original_seed=p, continuation=r, horizon=h, policy=policy,
                               path=ref["outcome"]["path"], sha256=ref["outcome"]["sha256"],
                               rows=len(data), kind=ref["kind"], environment_steps_recorded=steps))
    run.check("25_unique_policies", len(coverage) == 25 and len(raw) == 10000)
    prior_ref = run.js(ROOT/"47_existing_data_path_loss_analysis_v1/LATEST_ANALYSIS.json")
    prior = run.js(Path(prior_ref["run"])/"summary.json", prior_ref["summary_sha256"])
    run.check("original_and_final_means_reproduce_A", abs(y[:, 0].mean()*100-33.7) < 1e-10
              and abs(y[:, [2, 4]].mean()*100-34.075) < 1e-10)
    run.table("outcomes_25_policies.csv", raw)
    run.table("input_assets.csv", asset_rows)
    run.write("checkpoint_provenance.json", sources)
    run.write("costs.json", dict(B_campaign=str(cam), B_completion=completion, evaluation_cost_records=costrows,
                                analysis_new_environment_steps=0, analysis_new_SAC_updates=0))
    run.write("frozen_protocol.json", protocol)
    np.savez_compressed(run.path/"binary_outcomes.npz", successes=y)
    return y, bank, completion, prior


def scores_and_patterns(run, y, bank):
    scores = y.mean(axis=(2, 3))*100
    policies = [dict(original_seed=p, policy=q, macro_pp=float(scores[pi, qi]),
                     **{t: float(y[pi, qi, ti].mean()*100) for ti, t in enumerate(TASKS)})
                for pi, p in enumerate(PARENTS) for qi, q in enumerate(POLICIES)]
    paths, patterns, cases, tasks = [], [], [], []
    for pi, p in enumerate(PARENTS):
        for ri, r in enumerate(REPEATS):
            b, f = 1+ri*2, 2+ri*2
            j0, j8, j40 = [float(scores[pi, q]) for q in (0, b, f)]
            paths.append(dict(original_seed=p, continuation=r, J0=j0, J8=j8, J40=j40,
                              early_pp=j8-j0, late_pp=j40-j8, total_pp=j40-j0, stop8_advantage_pp=j8-j40))
            for ti, t in enumerate(TASKS):
                counts = Counter()
                for i in range(100):
                    triple = "".join(str(int(y[pi, q, ti, i])) for q in (0, b, f))
                    counts[triple] += 1
                    seed, state = bank[p][t, i]
                    cases.append(dict(original_seed=p, continuation=r, task=t, episode_index=i,
                                      seed=seed, initial_state_hash=state,
                                      success0=int(triple[0]), success8=int(triple[1]), success40=int(triple[2]), pattern=triple))
                for pattern in PATTERNS:
                    patterns.append(dict(original_seed=p, continuation=r, task=t, pattern=pattern,
                                         count=counts[pattern], fraction=counts[pattern]/100))
                eg, el = counts["010"]+counts["011"], counts["100"]+counts["101"]
                lg, ll = counts["001"]+counts["101"], counts["010"]+counts["110"]
                tg, tl = counts["001"]+counts["011"], counts["100"]+counts["110"]
                n0 = int(y[pi, 0, ti].sum())
                n8 = int(y[pi, b, ti].sum())
                n40 = int(y[pi, f, ti].sum())
                run.check("three_time_identity:"+str((p, r, t)), sum(counts.values()) == 100
                          and eg-el == n8-n0 and lg-ll == n40-n8 and tg-tl == n40-n0
                          and (eg-el)+(lg-ll) == tg-tl
                          and eg+lg-tg == el+ll-tl == counts["010"]+counts["101"])
                tasks.append(dict(original_seed=p, continuation=r, task=t, J0=n0, J8=n8, J40=n40,
                                  early_gain_pp=eg, early_loss_pp=el, early_net_pp=eg-el,
                                  late_gain_pp=lg, late_loss_pp=ll, late_net_pp=lg-ll,
                                  total_gain_pp=tg, total_loss_pp=tl, total_net_pp=tg-tl,
                                  old_success_lost_after8_pp=counts["110"], early_gain_lost_after8_pp=counts["010"],
                                  old_success_recovered_after8_pp=counts["101"], new_success_after8_pp=counts["001"],
                                  old_success_absent_at8_and40_pp=counts["100"], early_gain_retained_pp=counts["011"],
                                  late_loss_given_success8=None if n8 == 0 else ll/n8,
                                  late_acquisition_given_failure8=None if n8 == 100 else lg/(100-n8),
                                  old_retention_at40=None if n0 == 0 else (counts["101"]+counts["111"])/n0))
    parents = []
    for p in PARENTS:
        data = [d for d in paths if d["original_seed"] == p]
        parents.append(dict(original_seed=p, **{k: float(np.mean([d[k] for d in data])) for k in
                                               ("J0", "J8", "J40", "early_pp", "late_pp", "total_pp", "stop8_advantage_pp")}))
    path_changes = []
    for p, r in itertools.product(PARENTS, REPEATS):
        block = [d for d in tasks if d["original_seed"] == p and d["continuation"] == r]
        path_changes.append(dict(original_seed=p, continuation=r, **{
            k: float(np.mean([d[k] for d in block])) for k in (
                "early_gain_pp", "early_loss_pp", "early_net_pp", "late_gain_pp", "late_loss_pp", "late_net_pp",
                "total_gain_pp", "total_loss_pp", "total_net_pp", "old_success_lost_after8_pp",
                "early_gain_lost_after8_pp", "old_success_recovered_after8_pp", "new_success_after8_pp",
                "old_success_absent_at8_and40_pp", "early_gain_retained_pp")}))
    pattern_means = []
    for task in TASKS+("macro",):
        block = [d for d in patterns if task == "macro" or d["task"] == task]
        for pattern in PATTERNS:
            vals = [d["fraction"]*100 for d in block if d["pattern"] == pattern]
            pattern_means.append(dict(task=task, pattern=pattern, mean_fraction_pp=float(np.mean(vals))))
    sensitivity = []
    for excluded in PARENTS:
        subset = [d for d in parents if d["original_seed"] != excluded]
        sensitivity.append(dict(excluded_parent=excluded, **{k: float(np.mean([d[k] for d in subset])) for k in
                                                            ("J0", "J8", "J40", "early_pp", "late_pp", "total_pp", "stop8_advantage_pp")}))
    run.table("policy_scores.csv", policies)
    run.table("path_scores.csv", paths)
    run.table("parent_scores.csv", parents)
    run.table("case_trajectories.csv", cases)
    run.table("three_time_patterns.csv", patterns)
    run.table("task_gains_losses.csv", tasks)
    run.table("path_gains_losses.csv", path_changes)
    run.table("pattern_means.csv", pattern_means)
    run.table("parent_removal.csv", sensitivity)
    return paths, parents, tasks, path_changes, pattern_means, sensitivity


def uncertainty(run, y, paths, parents):
    rng = np.random.default_rng(480202)
    n = 20000
    bt = np.zeros((n, 5, 5, 4), dtype=float)
    indices = {}
    for pi, p in enumerate(PARENTS):
        for ti, t in enumerate(TASKS):
            ix = rng.integers(0, 100, size=(n, 100), dtype=np.int64)
            indices[str(p)+"_"+t] = ix.astype(np.uint8)
            task_policies = y[pi, :, ti, :]
            bt[:, pi, :, ti] = task_policies[:, ix].mean(axis=2).T*100
    bm = bt.mean(axis=3)
    # Independently check saved case-index weighted results before using them.
    for b in (0, 123, 19999):
        for pi, p in enumerate(PARENTS):
            for qi in range(5):
                for ti, t in enumerate(TASKS):
                    w = Counter(indices[str(p)+"_"+t][b].tolist())
                    direct = sum(wi*int(y[pi, qi, ti, i]) for i, wi in w.items())
                    run.check("bootstrap_weighted:"+str((b, p, qi, t)), abs(direct-bt[b, pi, qi, ti]) < 1e-9)
    labels, cols, observed, analytic = [], [], [], []
    taskrows, parentrows, globalrows = [], [], []
    marginal = lambda a: [float(v) for v in np.quantile(a, [.025, .975], method="linear")]
    path_draws = {}
    for pi, p in enumerate(PARENTS):
        for ri, r in enumerate(REPEATS):
            b, f = 1+ri*2, 2+ri*2
            for kind, lo, hi in (("early", 0, b), ("late", b, f), ("total", 0, f)):
                d = bm[:, pi, hi]-bm[:, pi, lo]
                point = float((y[pi, hi].astype(float)-y[pi, lo]).mean()*100)
                cd = y[pi, hi].astype(float)-y[pi, lo]
                labels.append(dict(original_seed=p, continuation=r, contrast=kind))
                cols.append(d)
                observed.append(point)
                analytic.append(float(np.sqrt(np.var(cd, axis=1, ddof=0).sum()/100)*25))
                path_draws[p, r, kind] = d
                for ti, t in enumerate(TASKS):
                    v = bt[:, pi, hi, ti]-bt[:, pi, lo, ti]
                    ci = marginal(v)
                    taskrows.append(dict(original_seed=p, continuation=r, task=t, contrast=kind,
                                         difference_pp=float(cd[ti].mean()*100),
                                         marginal_low_pp=ci[0], marginal_high_pp=ci[1],
                                         empirical_degenerate=bool(np.std(v, ddof=1) < 1e-12)))
    draws = np.column_stack(cols)
    obs = np.array(observed)
    sd = np.std(draws, axis=0, ddof=1)
    good = sd > 1e-12
    maxz = np.max(np.abs((draws[:, good]-obs[good])/sd[good]), axis=1) if np.any(good) else np.zeros(n)
    q = float(np.quantile(maxz, .95, method="linear"))
    ci = np.quantile(draws, [.025, .975], axis=0, method="linear")
    contrastrows = [dict(**lab, difference_pp=float(obs[i]), bootstrap_SD_pp=float(sd[i]),
                         empirical_exact_SD_pp=analytic[i],
                         marginal_low_pp=float(ci[0, i]), marginal_high_pp=float(ci[1, i]),
                         simultaneous_low_pp=float(obs[i]-q*sd[i]), simultaneous_high_pp=float(obs[i]+q*sd[i]),
                         empirical_degenerate=bool(not good[i])) for i, lab in enumerate(labels)]
    run.check("thirty_macro_contrasts", draws.shape == (20000, 30))
    run.check("bootstrap_SD_vs_exact", np.all(np.abs(sd[good]/np.array(analytic)[good]-1) < .04))
    exact_parent_indices = np.array(list(itertools.product(range(5), repeat=5)))
    for kind in KINDS:
        by_parent = np.column_stack([(path_draws[p, 4201, kind]+path_draws[p, 4202, kind])/2 for p in PARENTS])
        vals = np.array([d[kind+"_pp"] for d in parents])
        case_global = by_parent.mean(axis=1)
        parent_boot = vals[exact_parent_indices].mean(axis=1)
        case_ci, parent_ci = marginal(case_global), marginal(parent_boot)
        globalrows.append(dict(contrast=kind, difference_pp=float(vals.mean()),
                               case_marginal_low_pp=case_ci[0], case_marginal_high_pp=case_ci[1],
                               parent_percentile_low_pp=parent_ci[0], parent_percentile_high_pp=parent_ci[1],
                               parent_resamples=3125, independent_parents=5))
        for pi, p in enumerate(PARENTS):
            c = marginal(by_parent[:, pi])
            parentrows.append(dict(original_seed=p, contrast=kind, difference_pp=float(vals[pi]),
                                   case_marginal_low_pp=c[0], case_marginal_high_pp=c[1]))
    late = next(d for d in globalrows if d["contrast"] == "late")
    stop = dict(contrast="stop8_advantage", difference_pp=-late["difference_pp"],
                case_marginal_low_pp=-late["case_marginal_high_pp"], case_marginal_high_pp=-late["case_marginal_low_pp"],
                parent_percentile_low_pp=-late["parent_percentile_high_pp"],
                parent_percentile_high_pp=-late["parent_percentile_low_pp"], parent_resamples=3125, independent_parents=5)
    globalrows.append(stop)
    run.table("path_contrasts_uncertainty.csv", contrastrows)
    run.table("task_contrasts_marginal.csv", taskrows)
    run.table("parent_contrasts_marginal.csv", parentrows)
    run.table("global_contrasts_uncertainty.csv", globalrows)
    np.savez_compressed(run.path/"case_resample_indices.npz", **indices)
    np.savez_compressed(run.path/"bootstrap_draws.npz", task_policy_means_pp=bt, macro_contrasts_pp=draws,
                        observed_macro_contrasts_pp=obs, max_standardized_deviation=maxz,
                        exact_parent_indices=exact_parent_indices)
    run.write("bootstrap_definition.json", dict(replicates=n, seed=480202, SD_ddof=1, quantile_method="linear",
                                               policy_order=POLICIES, parent_order=PARENTS, task_order=TASKS,
                                               contrast_order=labels, simultaneous_critical_value=q,
                                               zero_SE_contrasts=int((~good).sum()),
                                               scope="30 path macro contrasts simultaneous; task/parent/global case intervals marginal"))
    return contrastrows, globalrows, q


def describe_flags(paths, contrasts):
    rows = []
    for d in paths:
        c = next(c for c in contrasts if c["original_seed"] == d["original_seed"]
                 and c["continuation"] == d["continuation"] and c["contrast"] == "late")
        rows.append(dict(original_seed=d["original_seed"], continuation=d["continuation"],
                         early_loss_then_recovery=d["early_pp"] <= -2 and d["late_pp"] >= 2,
                         early_loss_still_below_parent=d["early_pp"] <= -2 and d["total_pp"] <= -2,
                         continue_ge2=d["late_pp"] >= 2, stop8_ge2=d["late_pp"] <= -2,
                         abs_late_lt2=abs(d["late_pp"]) < 2,
                         late_simultaneous_positive=c["simultaneous_low_pp"] > 0 and not c["empirical_degenerate"],
                         late_simultaneous_negative=c["simultaneous_high_pp"] < 0 and not c["empirical_degenerate"]))
    positive, negative, sure_pos, sure_neg = [], [], [], []
    for p in PARENTS:
        block = [r for r in rows if r["original_seed"] == p]
        if all(r["continue_ge2"] for r in block):
            positive.append(p)
            if all(r["late_simultaneous_positive"] for r in block):
                sure_pos.append(p)
        if all(r["stop8_ge2"] for r in block):
            negative.append(p)
            if all(r["late_simultaneous_negative"] for r in block):
                sure_neg.append(p)
    return rows, dict(continue_both_ge2_parents=positive, stop8_both_ge2_parents=negative,
                      case_supported_continue_parents=sure_pos, case_supported_stop8_parents=sure_neg,
                      opposite_repeatable_point_preferences=bool(positive and negative),
                      case_supported_opposite_preferences=bool(sure_pos and sure_neg),
                      broad_stop8_pattern=sum(r["stop8_ge2"] for r in rows) >= 8 and len(negative) >= 4,
                      mostly_small_realized_difference=sum(r["abs_late_lt2"] for r in rows) >= 8,
                      early_loss_then_recovery_paths=sum(r["early_loss_then_recovery"] for r in rows),
                      early_loss_still_below_parent_paths=sum(r["early_loss_still_below_parent"] for r in rows),
                      continue_ge2_paths=sum(r["continue_ge2"] for r in rows),
                      stop8_ge2_paths=sum(r["stop8_ge2"] for r in rows),
                      abs_late_lt2_paths=sum(r["abs_late_lt2"] for r in rows),
                      interpretation="Descriptive development flags only; no automatic C gate")


def plots(run, paths, parents, contrasts, changes, pattern_means):
    os.environ["MPLCONFIGDIR"] = str(run.path/"matplotlib_cache")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                         "figure.constrained_layout.use": True, "savefig.dpi": 160})
    out = run.path/"figures"
    out.mkdir()

    def save(fig, name):
        fig.savefig(out/(name+".png"))
        fig.savefig(out/(name+".svg"))
        plt.close(fig)

    fig, axes = plt.subplots(1, 5, figsize=(15, 4), sharey=True)
    for ax, p in zip(axes, PARENTS):
        for d in paths:
            if d["original_seed"] == p:
                ax.plot([0, 8, 40], [d["J0"], d["J8"], d["J40"]], "o-", label=str(d["continuation"]))
        ax.set_title(str(p))
        ax.set_xticks([0, 8, 40])
        ax.set_xlabel("Additional training (k)")
        upper = max(60., 10*np.ceil(max(d[k] for d in paths for k in ("J0", "J8", "J40"))/10))
        ax.set_ylim(0, upper)
    axes[0].set_ylabel("Macro success (%)")
    axes[0].legend()
    fig.suptitle("B: fixed checkpoint outcomes, same per-parent O100 cases")
    save(fig, "three_time_success")

    fig, ax = plt.subplots(figsize=(9, 6))
    labels, values, low, high = [], [], [], []
    for d in contrasts:
        if d["contrast"] == "late":
            labels.append(f'{d["original_seed"]} / {d["continuation"]}')
            values.append(d["difference_pp"])
            low.append(d["simultaneous_low_pp"])
            high.append(d["simultaneous_high_pp"])
    values = np.array(values)
    ax.errorbar(values, np.arange(10), xerr=[values-np.array(low), np.array(high)-values], fmt="o", capsize=3)
    ax.set_yticks(range(10), labels)
    ax.axvline(0, color="black", lw=.9)
    ax.axvline(2, color="gray", ls=":", lw=.7)
    ax.axvline(-2, color="gray", ls=":", lw=.7)
    ax.invert_yaxis()
    ax.set_xlabel("J40 - J8 (pp): positive favors continuing")
    ax.set_title("B: late value; simultaneous 95% intervals over 30 macro contrasts")
    save(fig, "late_value_intervals")

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5), sharey=True)
    for ax, stage in zip(axes, ("early", "late")):
        for ri, r in enumerate(REPEATS):
            block = [d for d in changes if d["continuation"] == r]
            pos = np.arange(5)+(ri-.5)*.35
            ax.bar(pos, [d[stage+"_gain_pp"] for d in block], .32, color="#218565", alpha=1 if ri == 0 else .5)
            ax.bar(pos, [-d[stage+"_loss_pp"] for d in block], .32, color="#B53B44", alpha=1 if ri == 0 else .5)
            ax.plot(pos, [d[stage+"_net_pp"] for d in block], "ko", ms=4)
        ax.axhline(0, color="black", lw=.8)
        ax.set_xticks(range(5), [str(p) for p in PARENTS], rotation=20)
        ax.set_title("Parent to 8k" if stage == "early" else "8k to 40k")
    axes[0].set_ylabel("Macro contributions (pp)")
    fig.suptitle("Gains (green), losses (red), net (black); 4201 left / 4202 right")
    save(fig, "early_late_gains_losses")

    fig, ax = plt.subplots(figsize=(10, 4.5))
    block = [d for d in pattern_means if d["task"] == "macro"]
    ax.bar([d["pattern"] for d in block], [d["mean_fraction_pp"] for d in block], color="#1763A6")
    ax.set_xlabel("Success pattern: parent / 8k / 40k")
    ax.set_ylabel("Mean fraction of cases (%)")
    ax.set_title("All eight three-timepoint patterns; equal weights across parents/tasks")
    save(fig, "three_time_patterns")
    return matplotlib.__version__


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    run = Run()
    try:
        y, bank, completion, prior = read_inputs(run)
        paths, parents, tasks, changes, pattern_means, sensitivity = scores_and_patterns(run, y, bank)
        contrasts, global_ci, critical = uncertainty(run, y, paths, parents)
        flagrows, flags = describe_flags(paths, contrasts)
        run.table("path_development_flags.csv", flagrows)
        mpl = plots(run, paths, parents, contrasts, changes, pattern_means)
        means = {k: float(np.mean([d[k] for d in parents])) for k in
                 ("J0", "J8", "J40", "early_pp", "late_pp", "total_pp", "stop8_advantage_pp")}
        mean_changes = {k: float(np.mean([d[k] for d in changes])) for k in changes[0]
                        if k not in ("original_seed", "continuation")}
        task_scores = []
        for t in TASKS:
            block = [d for d in tasks if d["task"] == t]
            task_scores.append(dict(task=t, **{k: float(np.mean([d[k] for d in block]))
                                               for k in ("J0", "J8", "J40", "early_gain_pp", "early_loss_pp",
                                                         "late_gain_pp", "late_loss_pp", "early_net_pp", "late_net_pp")}))
        run.table("task_mean_scores.csv", task_scores)
        summary = dict(execution_status="completed_B_measurement_analysis", scientific_scope="development_only_no_rule_fit",
                       parents=PARENTS, continuations=REPEATS, tasks=TASKS, independent_parents=5,
                       counts=dict(unique_policies=25, source_outcome_rows=10000, joined_path_cases=4000,
                                   new_evaluation_policies=10, new_evaluation_episodes=4000),
                       means=means, path_scores=paths, parent_scores=parents, parent_removal=sensitivity,
                       task_scores=task_scores, mean_gain_loss=mean_changes, pattern_means=pattern_means,
                       global_contrasts_uncertainty=global_ci,
                       case_bootstrap=dict(replicates=20000, seed=480202, SD_ddof=1, simultaneous_family=30,
                                           critical_value=critical,
                                           degenerate_contrasts=sum(d["empirical_degenerate"] for d in contrasts)),
                       development_flags=flags,
                       limits=["one realized future per 8k state", "known parents and existing evaluation bank",
                               "shared J8 change-score association is not used as a predictor",
                               "O100 only research measurement; no free online diagnostic",
                               "8k stop and 40k continue share budget cap, not identical actual training expenditure",
                               "all rule fitting and C/original-stage2/3 execution held"],
                       status_of_prior_findings=dict(stage1_gate="not_passed_unchanged", TD_rules="all_numeric_rules_keep_unchanged"),
                       costs=dict(research_evaluation_steps=completion["research_evaluation_steps"],
                                  technical_evaluation_steps=completion["technical_evaluation_steps"],
                                  total_new_environment_steps=completion["total_new_environment_steps"],
                                  new_training_steps=0, new_SAC_updates=0, analysis_new_environment_steps=0,
                                  analysis_wall_seconds=time.perf_counter()-run.start,
                                  analysis_CPU_seconds=time.process_time()-run.cpu),
                       runtime=dict(python=sys.version, numpy=np.__version__, matplotlib=mpl, platform=platform.platform()))
        run.write("summary.json", summary)
        run.write("checks.json", {"passed": len(run.checks), "failed": 0, "checks": run.checks})
        run.write("input_hashes.json", run.inputs)
        run.write("output_hashes.json", {str(p.relative_to(run.path)): sha(p.read_bytes()) for p in run.path.rglob("*")
                                        if p.is_file() and "matplotlib_cache" not in p.parts})
        (HERE/"LATEST_ANALYSIS.json").write_text(json.dumps(
            {"run": str(run.path), "summary_sha256": sha((run.path/"summary.json").read_bytes())}, indent=2), encoding="utf-8")
        print(json.dumps({"run": str(run.path), "means": means, "flags": flags,
                          "checks": len(run.checks), "new_environment_steps_of_analysis": 0}, indent=2))
    except BaseException:
        run.write("failure.json", dict(traceback=traceback.format_exc(), checks=run.checks, input_hashes=run.inputs,
                                      new_environment_steps=0, new_SAC_updates=0,
                                      wall_seconds=time.perf_counter()-run.start))
        raise


if __name__ == "__main__":
    main()
