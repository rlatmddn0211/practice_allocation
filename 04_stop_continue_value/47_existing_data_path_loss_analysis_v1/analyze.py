"""A1-A3 only: immutable CSV/JSON inputs; no simulator, learner, or policy loading."""
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
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PARENTS = (41011, 41012, 41013, 41014, 41015)
REPEATS = (4201, 4202)
METHODS = ("dose625", "alternate4k", "mixture")
TASKS = ("DO", "DC", "PU", "BP")
PAIRS = tuple(itertools.combinations(METHODS, 2))
METRICS = ("actor_loss", "critic_loss", "entropy_loss", "entropy_coefficient",
           "critic_0_abs_td_error", "critic_1_abs_td_error", "batch_new_fraction")


def digest(data):
    return hashlib.sha256(data).hexdigest()


class Run:
    def __init__(self):
        self.started = time.perf_counter()
        self.cpu = time.process_time()
        self.path = HERE / "results" / (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_analysis_" + uuid.uuid4().hex[:8])
        self.path.mkdir(parents=True, exist_ok=False)
        snap = self.path / "source_snapshot"
        snap.mkdir()
        for name in ("analyze.py", "analysis_config.json", "verify.py"):
            if (HERE / name).exists():
                shutil.copy2(HERE / name, snap / name)
        self.inputs, self.checks = {}, []
        self.write("source_hashes.json", {p.name: digest(p.read_bytes()) for p in snap.iterdir()})

    def check(self, label, passed):
        self.checks.append({"check": label, "passed": bool(passed)})
        if not passed:
            raise AssertionError(label)

    def data(self, path, sha=None):
        path = Path(path).resolve()
        data = path.read_bytes()
        actual = digest(data)
        self.inputs[str(path)] = actual
        if sha is not None:
            self.check("hash:" + str(path), actual == sha)
        return data

    def js(self, path, sha=None):
        return json.loads(self.data(path, sha).decode("utf-8-sig"))

    def rows(self, path, sha=None):
        return list(csv.DictReader(io.StringIO(self.data(path, sha).decode("utf-8-sig"))))

    def write(self, name, value):
        with (self.path / name).open("x", encoding="utf-8") as f:
            json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)
            f.write("\n")

    def table(self, name, rows):
        with (self.path / name).open("x", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def num(value):
    return None if value == "" else float(value)


def truth(value):
    if value in ("1", "True", "true"):
        return 1
    if value in ("0", "False", "false"):
        return 0
    raise ValueError("Invalid binary value: " + str(value))


def statistics(values):
    a = np.array([x for x in values if x is not None], dtype=float)
    if not len(a):
        return {"n": 0, "median": None, "q25": None, "q75": None, "mean": None, "min": None, "max": None}
    return dict(n=len(a), median=float(np.median(a)), q25=float(np.quantile(a, .25)),
                q75=float(np.quantile(a, .75)), mean=float(a.mean()), min=float(a.min()), max=float(a.max()))


def load_inputs(run):
    cfg = run.js(HERE / "analysis_config.json")
    protocol = run.js(ROOT / "46_post_stage1_path_loss_design_v1/protocol.json")
    run.check("A_only_protocol", cfg["scope"] == ["A1", "A2", "A3"]
              and protocol["A_existing_data"]["A2"]["analysis_rng_seed"] == 460202)
    run.data(ROOT / "25_candidate_factor_evidence_register_v1/record_template_ko.md")
    # Read interpretation sources, never import historical experiment code.
    for name in ("engine.py", "learning.py", "schedules.py", "evaluation.py"):
        run.data(ROOT / "44_selection_value_stage1_checkpoint36_v2/practice_allocation" / name)
    cam = Path(run.js(ROOT / "44_selection_value_stage1_checkpoint36_v2/ACTIVE_CAMPAIGN.json")["campaign"])
    marker = run.js(cam / "COMPLETE.json")
    completion = run.js(marker["summary"]["path"], marker["summary"]["sha256"])
    plan = run.js(cam / "plan.json", run.js(cam / "plan_integrity.json")["sha256"])
    oldref = run.js(ROOT / "45_stage1_selection_value_analysis_v1/LATEST_REVIEW.json")
    olddir = Path(oldref["run"])
    prior = run.js(olddir / "summary.json", oldref["summary_sha256"])
    oldcross = run.rows(olddir / "crossfit.csv")
    run.check("245_completed_scientific_jobs", len(plan["jobs"]) == 245
              and completion["execution_status"] == "completed" and not plan["technical_smoke"])
    outcomes, logs, episodes = {}, defaultdict(list), defaultdict(list)
    raw_outcomes, raw_logs, raw_episodes, asset_rows, seed_rows = [], [], [], [], []
    cases, packages, versions = {}, {}, {}
    for job in plan["jobs"]:
        marker = run.js(cam / "completed" / (job["id"] + ".json"))
        result = run.js(marker["result_ref"]["path"], marker["result_ref"]["sha256"])
        attempt = Path(marker["attempt"])
        if job["kind"] not in ("train", "evaluate"):
            continue
        request = run.js(attempt / "request.json")
        runtime = run.js(attempt / "runtime.json")
        cost = run.js(attempt / "costs.json")
        packages[json.dumps(runtime["packages"], sort_keys=True)] = runtime["packages"]
        versions[runtime["implementation"]] = runtime["source_hashes"]
        run.check("job_complete:" + job["id"], cost["status"] == "completed"
                  and result["id"] == job["id"])
        p, c, r = job["original_seed"], job.get("condition", "parent"), job.get("continuation", 0)
        ident = {"original_seed": p, "condition": c, "continuation": r}
        if job["kind"] == "evaluate":
            data = run.rows(result["episodes_path"], result["episodes_sha256"])
            run.check("outcome_coverage:" + job["id"], len(data) == 400 and
                      {(d["task"], int(d["episode_index"])) for d in data}
                      == set(itertools.product(TASKS, range(100))))
            signature = {(d["task"], int(d["episode_index"])): (int(d["seed"]), d["initial_state_hash"]) for d in data}
            if p in cases:
                run.check("case_pairing:" + job["id"], signature == cases[p])
            else:
                cases[p] = signature
            array = np.zeros((4, 100), dtype=np.int8)
            for d in data:
                array[TASKS.index(d["task"]), int(d["episode_index"])] = truth(d["success"])
                raw_outcomes.append({**ident, **d, "source_job": job["id"]})
            run.check("outcome_unchanged_and_score:" + job["id"],
                      result["evaluation_state_unchanged"]
                      and abs(float(array.mean()) - result["evaluation"]["macro_success"]) < 1e-12)
            run.check("evaluation_cost:" + job["id"],
                      sum(int(d["length"]) for d in data) == cost["costs"]["environment_steps"])
            run.check("unique_policy:" + job["id"], (p, c, r) not in outcomes)
            outcomes[p, c, r] = array
            asset_rows.append({**ident, "job": job["id"], "kind": "outcome", "path": result["episodes_path"], "rows": len(data)})
        else:
            run.check("training_cost:" + job["id"], cost["costs"]["environment_steps"] == job["steps"])
            if request.get("start_branch"):
                seed_rows.append({**ident, "continuation_rng_seed": request["continuation_rng_seed"]})
            offset = 0 if c == "parent" else 200000
            mdata = run.rows(attempt / "train_metrics.csv")
            edata = run.rows(attempt / "train_episodes.csv")
            run.check("segment_metric_spacing:" + job["id"], [int(d["step"]) for d in mdata] ==
                      list(range(job["start_step"] + 250, job["start_step"] + job["steps"] + 1, 250)))
            run.check("segment_episode_spacing:" + job["id"], [int(d["step"]) for d in edata] ==
                      list(range(job["start_step"] + 500, job["start_step"] + job["steps"] + 1, 500)))
            for d in mdata:
                entry = {**ident, **d, "step": int(d["step"]), "relative_step": int(d["step"]) - offset,
                         "source_job": job["id"]}
                raw_logs.append(entry)
                logs[p, c, r].append(entry)
            for d in edata:
                entry = {**ident, **d, "step": int(d["step"]), "relative_step": int(d["step"]) - offset,
                         "source_job": job["id"]}
                raw_episodes.append(entry)
                episodes[p, c, r].append(entry)
            for name, data, kind in (("train_metrics.csv", mdata, "metric"), ("train_episodes.csv", edata, "episode")):
                asset_rows.append({**ident, "job": job["id"], "kind": kind, "path": str(attempt / name), "rows": len(data)})
    run.check("source_counts", len(outcomes) == 35 and len(raw_outcomes) == 14000
              and len(raw_logs) == 8800 and len(raw_episodes) == 4400
              and Counter(a["kind"] for a in asset_rows) == {"outcome": 35, "metric": 200, "episode": 200})
    run.check("same_training_dependencies", len(packages) == 1)
    for key in logs:
        logs[key].sort(key=lambda d: d["relative_step"])
        episodes[key].sort(key=lambda d: d["relative_step"])
        horizon = 200000 if key[1] == "parent" else 40000
        run.check("full_path_spacing:" + str(key), [x["relative_step"] for x in logs[key]] ==
                  list(range(250, horizon + 1, 250)) and [x["relative_step"] for x in episodes[key]] ==
                  list(range(500, horizon + 1, 500)))
    run.table("outcome_cases.csv", raw_outcomes)
    run.table("training_metrics_raw.csv", raw_logs)
    run.table("training_episodes_raw.csv", raw_episodes)
    run.table("input_assets.csv", asset_rows)
    run.table("continuation_rng_seeds.csv", seed_rows)
    run.write("training_provenance.json", {"packages": list(packages.values()), "source_versions": versions,
                                         "campaign": str(cam), "prior_completed_costs": prior["costs"]})
    return outcomes, logs, episodes, prior, oldcross, protocol


def analyze_selection(run, outcomes, prior, oldcross):
    halves = {(p, r, c, h): float(outcomes[p, c, r][:, 50*h:50*(h+1)].mean() * 100)
              for p, r, c, h in itertools.product(PARENTS, REPEATS, METHODS, (0, 1))}

    def folds(parents, methods, mode, group, excluded=0):
        rows = []
        for p, target, h in itertools.product(parents, REPEATS, (0, 1)):
            source = target if mode == "within" else next(r for r in REPEATS if r != target)
            choice = max(methods, key=lambda c: halves[p, source, c, h])
            other = [q for q in parents if q != p]
            fixed = max(methods, key=lambda c: np.mean([halves[q, r, c, h] for q in other for r in REPEATS]))
            chosen = halves[p, target, choice, 1-h]
            bp, fixed_score = halves[p, target, "dose625", 1-h], halves[p, target, fixed, 1-h]
            rows.append(dict(group=group, excluded_parent=excluded, mode=mode, original_seed=p,
                             target_repeat=target, source_repeat=source, selection_half=h, score_half=1-h,
                             choice=choice, fixed_choice=fixed, selected_pp=chosen, BP_pp=bp,
                             fixed_pp=fixed_score, vs_BP_pp=chosen-bp, vs_fixed_pp=chosen-fixed_score))
        return rows

    mainrows, refitrows, byparent, summaries = [], [], [], []
    groups = [("all", METHODS)] + [("_vs_".join(pair), pair) for pair in PAIRS]
    for group, methods in groups:
        for excluded in (0,) + PARENTS:
            parents = [p for p in PARENTS if p != excluded]
            for mode in ("within", "across"):
                rows = folds(parents, methods, mode, group, excluded)
                (mainrows if not excluded else refitrows).extend(rows)
                for p in parents:
                    chosen = [d for d in rows if d["original_seed"] == p]
                    byparent.append(dict(group=group, excluded_parent=excluded, mode=mode, original_seed=p,
                                         **{k: float(np.mean([d[k] for d in chosen])) for k in
                                            ("selected_pp", "BP_pp", "fixed_pp", "vs_BP_pp", "vs_fixed_pp")}))
                summaries.append(dict(group=group, excluded_parent=excluded, mode=mode, parents=len(parents),
                                      **{k: float(np.mean([d[k] for d in rows])) for k in
                                         ("selected_pp", "BP_pp", "fixed_pp", "vs_BP_pp", "vs_fixed_pp")}))
    across = [d for d in mainrows if d["group"] == "all" and d["mode"] == "across"]
    for new, old in zip(across, oldcross):
        run.check("v45_fold:" + str((new["original_seed"], new["target_repeat"], new["selection_half"])),
                  new["choice"] == old["selected"] and new["fixed_choice"] == old["leave_parent_out_fixed"]
                  and new["original_seed"] == int(old["original_seed"])
                  and new["target_repeat"] == int(old["heldout_continuation"])
                  and all(abs(new[k] - float(old[k])) < 1e-10 for k in ("selected_pp", "vs_BP_pp", "vs_fixed_pp")))
    primary = [d for d in summaries if d["group"] == "all" and not d["excluded_parent"]]
    run.check("v45_across_reproduced", all(abs(primary[1][k] - prior["crossfit"][k]) < 1e-10
                                         for k in ("selected_pp", "vs_BP_pp", "vs_fixed_pp")))
    differences = []
    for group, methods in groups:
        for p in PARENTS:
            sub = [x for x in byparent if x["group"] == group and x["original_seed"] == p and not x["excluded_parent"]]
            w, a = next(x for x in sub if x["mode"] == "within"), next(x for x in sub if x["mode"] == "across")
            differences.append(dict(group=group, original_seed=p, within_vs_BP_pp=w["vs_BP_pp"],
                                    across_vs_BP_pp=a["vs_BP_pp"], within_vs_fixed_pp=w["vs_fixed_pp"],
                                    across_vs_fixed_pp=a["vs_fixed_pp"], within_minus_across_pp=w["selected_pp"]-a["selected_pp"]))
    run.table("a1_folds.csv", mainrows)
    run.table("a1_full_parent_removal_folds.csv", refitrows)
    run.table("a1_parent_scores.csv", byparent)
    run.table("a1_summary.csv", summaries)
    run.table("a1_within_minus_across.csv", differences)
    return {"primary": primary, "parent_differences": [x for x in differences if x["group"] == "all"],
            "full_parent_removal": [x for x in summaries if x["group"] == "all" and x["excluded_parent"]],
            "secondary_pairs": [x for x in summaries if x["group"] != "all" and not x["excluded_parent"]]}


def analyze_case_uncertainty(run, outcomes):
    nboot = 20000
    rng = np.random.default_rng(460202)
    means = np.zeros((nboot, 5, 7), dtype=float)
    observed = np.zeros((5, 7), dtype=float)
    samples, labels, analytic_sd = {}, [], []
    policy_order = [("parent", 0)] + list(itertools.product(METHODS, REPEATS))
    for pi, p in enumerate(PARENTS):
        y = np.stack([outcomes[p, c, r] for c, r in policy_order])
        observed[pi] = y.mean(axis=(1, 2)) * 100
        for ti, task in enumerate(TASKS):
            indices = rng.integers(0, 100, size=(nboot, 100), dtype=np.int64)
            samples[str(p) + "_" + task] = indices.astype(np.uint8)
            # Identical indices for all seven policies, including original parent.
            means[:, pi, :] += y[:, ti, indices].mean(axis=2).T * 25
    columns, point = [], []
    for pi, p in enumerate(PARENTS):
        for a, b in PAIRS:
            da, od, case_diffs = [], [], []
            for r in REPEATS:
                ai, bi = policy_order.index((a, r)), policy_order.index((b, r))
                da.append(means[:, pi, ai] - means[:, pi, bi])
                od.append(float(observed[pi, ai] - observed[pi, bi]))
                case_diffs.append(outcomes[p, a, r].astype(float) - outcomes[p, b, r])
            for label, draws, obs, cd in (
                    ("4201", da[0], od[0], case_diffs[0]),
                    ("4202", da[1], od[1], case_diffs[1]),
                    ("4202-minus-4201", da[1]-da[0], od[1]-od[0], case_diffs[1]-case_diffs[0])):
                labels.append(dict(original_seed=p, a=a, b=b, contrast=label))
                columns.append(draws)
                point.append(obs)
                # Exact empirical paired-bootstrap variance, independent task strata.
                analytic_sd.append(float(np.sqrt(np.var(cd, axis=1, ddof=0).sum()/100) * 25))
    draws, point = np.column_stack(columns), np.array(point)
    sd = draws.std(axis=0, ddof=1)
    good = sd > 1e-12
    maxz = np.max(np.abs((draws[:, good]-point[good])/sd[good]), axis=1)
    q = float(np.quantile(maxz, .95, method="linear"))
    lo, hi = np.quantile(draws, [.025, .975], axis=0, method="linear")
    rows = [dict(**lab, observed_pp=float(point[i]), bootstrap_SD_pp=float(sd[i]),
                 empirical_exact_SD_pp=analytic_sd[i], marginal_low_pp=float(lo[i]), marginal_high_pp=float(hi[i]),
                 simultaneous_low_pp=float(point[i]-q*sd[i]), simultaneous_high_pp=float(point[i]+q*sd[i]),
                 degenerate=bool(not good[i]))
            for i, lab in enumerate(labels)]
    reversals = []
    for i in range(0, 45, 3):
        u, v, delta = rows[i:i+3]
        opposite = u["observed_pp"] * v["observed_pp"] < 0
        adequate = abs(u["observed_pp"]) >= 2 and abs(v["observed_pp"]) >= 2
        excludes = all(d["simultaneous_low_pp"] > 0 or d["simultaneous_high_pp"] < 0 for d in (u, v))
        passed = opposite and adequate and excludes and not u["degenerate"] and not v["degenerate"]
        reversals.append(dict(original_seed=u["original_seed"], a=u["a"], b=u["b"],
                              repeat4201_pp=u["observed_pp"], repeat4202_pp=v["observed_pp"],
                              difference_of_differences_pp=delta["observed_pp"], opposite_sign=bool(opposite),
                              both_ge_2pp=bool(adequate), both_simultaneous_exclude_zero=bool(excludes),
                              strong_reversal=bool(passed)))
    # A deterministic arithmetic reconstruction using saved resampled cases.
    for k in (0, 1, 123, 19999):
        for pi, p in enumerate(PARENTS):
            for pol, (c, r) in enumerate(policy_order):
                direct = sum(float(outcomes[p, c, r][ti, samples[str(p)+"_"+t][k]].mean())
                             for ti, t in enumerate(TASKS)) * 25
                run.check("paired_bootstrap_direct:" + str((k, p, c, r)), abs(direct-means[k, pi, pol]) < 1e-10)
    run.check("45_contrast_family", draws.shape == (20000, 45))
    run.check("bootstrap_SD_vs_analytic", np.all(np.abs(sd[good]/np.array(analytic_sd)[good]-1) < .04))
    run.check("degenerate_draws_constant", np.all(np.abs(draws[:, ~good]-point[~good]) < 1e-10))
    np.savez_compressed(run.path / "a2_resampled_case_indices.npz", **samples)
    np.savez_compressed(run.path / "a2_bootstrap_draws.npz", policy_means_pp=means, contrasts_pp=draws,
                        observed_pp=point, max_standardized_deviation=maxz)
    run.table("a2_contrasts.csv", rows)
    run.table("a2_reversals.csv", reversals)
    run.write("a2_definition.json", dict(replicates=20000, seed=460202, policy_order=policy_order,
                                       parent_order=PARENTS, task_order=TASKS, contrast_order=labels,
                                       simultaneous_critical_value=q, bootstrap_SD_ddof=1,
                                       zero_SE_count=int((~good).sum()), confidence=.95,
                                       interpretation="Conditional evaluation-case uncertainty only; not training or new-parent uncertainty."))
    return {"family_size": 45, "replicates": nboot, "critical_value": q,
            "degenerate_contrasts": int((~good).sum()), "reversals": reversals,
            "strong_reversal_count": sum(d["strong_reversal"] for d in reversals),
            "strong_reversal_parents": sorted({d["original_seed"] for d in reversals if d["strong_reversal"]})}


def analyze_transitions(run, outcomes):
    rows = []
    for p, c, r, ti in itertools.product(PARENTS, METHODS, REPEATS, range(4)):
        before, after = outcomes[p, "parent", 0][ti], outcomes[p, c, r][ti]
        n00 = int(np.sum((before == 0) & (after == 0)))
        n01 = int(np.sum((before == 0) & (after == 1)))
        n10 = int(np.sum((before == 1) & (after == 0)))
        n11 = int(np.sum((before == 1) & (after == 1)))
        run.check("transition_conservation:" + str((p, c, r, ti)),
                  n00+n01+n10+n11 == 100 and n01-n10 == int(after.sum()-before.sum()))
        rows.append(dict(original_seed=p, condition=c, continuation=r, task=TASKS[ti],
                         parent_success=n10+n11, child_success=n01+n11, fail_to_fail=n00,
                         gain=n01, loss=n10, retained=n11, gain_pp=float(n01), loss_pp=float(n10),
                         net_pp=float(n01-n10), acquisition_given_parent_failure=None if n00+n01 == 0 else n01/(n00+n01),
                         retention_given_parent_success=None if n10+n11 == 0 else n11/(n10+n11)))
    paths, parents, methods = [], [], []
    for p, c, r in itertools.product(PARENTS, METHODS, REPEATS):
        block = [d for d in rows if (d["original_seed"], d["condition"], d["continuation"]) == (p, c, r)]
        paths.append(dict(original_seed=p, condition=c, continuation=r,
                          **{k: float(np.mean([d[k] for d in block])) for k in ("gain_pp", "loss_pp", "net_pp")},
                          parent_macro_pp=float(outcomes[p, "parent", 0].mean()*100),
                          child_macro_pp=float(outcomes[p, c, r].mean()*100)))
    for p, c in itertools.product(PARENTS, METHODS):
        block = [d for d in paths if (d["original_seed"], d["condition"]) == (p, c)]
        parents.append(dict(original_seed=p, condition=c, **{
            k: float(np.mean([d[k] for d in block])) for k in ("gain_pp", "loss_pp", "net_pp")}))
    for c in METHODS:
        block = [d for d in paths if d["condition"] == c]
        methods.append(dict(condition=c, **{
            k: float(np.mean([d[k] for d in block])) for k in ("gain_pp", "loss_pp", "net_pp")}))
    taskmeans = []
    for c, t in itertools.product(METHODS, TASKS):
        block = [d for d in rows if d["condition"] == c and d["task"] == t]
        taskmeans.append(dict(condition=c, task=t, **{
            k: float(np.mean([d[k] for d in block])) for k in ("parent_success", "child_success", "gain_pp", "loss_pp", "net_pp")}))
    pairdecomp = []
    for p, r, (a, b) in itertools.product(PARENTS, REPEATS, (("alternate4k", "dose625"), ("mixture", "dose625"), ("alternate4k", "mixture"))):
        for t in TASKS + ("macro",):
            data = rows if t != "macro" else paths
            u = next(d for d in data if d["original_seed"] == p and d["continuation"] == r and d["condition"] == a and (t == "macro" or d["task"] == t))
            v = next(d for d in data if d["original_seed"] == p and d["continuation"] == r and d["condition"] == b and (t == "macro" or d["task"] == t))
            pairdecomp.append(dict(original_seed=p, continuation=r, a=a, b=b, task=t,
                                   gain_difference_pp=u["gain_pp"]-v["gain_pp"],
                                   loss_reduction_pp=v["loss_pp"]-u["loss_pp"],
                                   net_difference_pp=u["net_pp"]-v["net_pp"]))
    run.table("a3_case_transitions.csv", rows)
    run.table("a3_path_gains_losses.csv", paths)
    run.table("a3_parent_gains_losses.csv", parents)
    run.table("a3_method_gains_losses.csv", methods)
    run.table("a3_task_gains_losses.csv", taskmeans)
    run.table("a3_pair_decomposition.csv", pairdecomp)
    return {"methods": methods, "parents": parents, "task_means": taskmeans, "paths": paths,
            "NA_acquisition_count": sum(d["acquisition_given_parent_failure"] is None for d in rows),
            "NA_retention_count": sum(d["retention_given_parent_success"] is None for d in rows)}


def analyze_trajectories(run, logs, episodes):
    windows, task_windows, exposure, prefixes = [], [], [], []
    for key in sorted(logs):
        p, c, r = key
        data, eps = logs[key], episodes[key]
        width, horizon = (20000, 200000) if c == "parent" else (4000, 40000)
        bystep = {x["relative_step"]: x for x in data}
        initial = {f"{kind}_{t}": "0" for kind in ("collected", "sampled") for t in TASKS}
        initial["updates"] = "0"
        if c != "parent":
            initial = logs[p, "parent", 0][-1]
        for end in range(width, horizon+1, width):
            begin = end-width
            block = [d for d in data if begin < d["relative_step"] <= end]
            episode_block = [d for d in eps if begin < d["relative_step"] <= end]
            ident = dict(original_seed=p, condition=c, continuation=r, begin_step=begin, end_step=end)
            for metric in METRICS:
                vals = [num(d[metric]) for d in block]
                run.check("finite_window:" + str((key, end, metric)),
                          all(v is None or math.isfinite(v) for v in vals))
                windows.append(dict(**ident, metric=metric, **statistics(vals)))
            a, b = initial if begin == 0 else bystep[begin], bystep[end]
            update_delta = int(b["updates"])-int(a["updates"])
            counts = {f"{kind}_{t}": int(b[f"{kind}_{t}"])-int(a[f"{kind}_{t}"])
                      for kind in ("collected", "sampled") for t in TASKS}
            run.check("counter_totals:" + str((key, end)),
                      all(v >= 0 for v in counts.values()) and sum(counts["collected_"+t] for t in TASKS) == width
                      and sum(counts["sampled_"+t] for t in TASKS) == 256*update_delta)
            exposure.append(dict(**ident, updates=update_delta, **counts,
                                 **{f"sampled_share_{t}": counts["sampled_"+t]/(256*update_delta) for t in TASKS},
                                 batch_new_fraction_snapshot_mean=float(np.mean([float(d["batch_new_fraction"]) for d in block]))))
            run.check("episode_lengths:" + str((key, end)), all(int(d["length"]) == 500 for d in episode_block))
            for t in TASKS:
                block_t = [d for d in episode_block if d["task"] == t]
                run.check("episode_collected_counts:" + str((key, end, t)), len(block_t)*500 == counts["collected_"+t])
                stats = statistics([float(d["return"]) for d in block_t])
                task_windows.append(dict(**ident, task=t, episodes=len(block_t),
                                         successes=sum(truth(d["success"]) for d in block_t),
                                         success_rate=None if not block_t else sum(truth(d["success"]) for d in block_t)/len(block_t),
                                         **{"return_"+k: v for k, v in stats.items()}))
        if c != "parent":
            vals = [[(float(d["critic_0_abs_td_error"])+float(d["critic_1_abs_td_error"]))/2
                     for d in data if lo < d["relative_step"] <= hi and
                     d["critic_0_abs_td_error"] and d["critic_1_abs_td_error"]]
                    for lo, hi in ((0, 4000), (4000, 8000))]
            valid = all(len(v) >= 12 for v in vals)
            med = [float(np.median(v)) if v else None for v in vals]
            bp = [d for d in eps if 4000 < d["relative_step"] <= 8000 and d["task"] == "BP"]
            alphas = [float(np.median([float(d["entropy_coefficient"]) for d in data if lo < d["relative_step"] <= hi]))
                      for lo, hi in ((0, 4000), (4000, 8000))]
            prefixes.append(dict(original_seed=p, condition=c, continuation=r, valid=valid,
                                 first_window_n=len(vals[0]), second_window_n=len(vals[1]),
                                 TD_0to4k_median=med[0], TD_4to8k_median=med[1],
                                 z=None if not valid else math.log((med[1]+1e-6)/(med[0]+1e-6)),
                                 alpha_0to4k_median=alphas[0], alpha_4to8k_median=alphas[1],
                                 BP_training_success_4to8k=None if not bp else sum(truth(d["success"]) for d in bp)/len(bp),
                                 BP_training_episodes_4to8k=len(bp)))
    run.table("a3_metric_windows.csv", windows)
    run.table("a3_training_task_windows.csv", task_windows)
    run.table("a3_exposure_windows.csv", exposure)
    run.table("a3_prefix_only_signals.csv", prefixes)
    run.check("predefined_windows_complete", len(windows) == 350*len(METRICS)
              and len(task_windows) == 350*4 and len(exposure) == 350)
    run.check("all_prefix_inputs_complete", len(prefixes) == 30 and all(d["valid"] for d in prefixes))
    # A compact endpoint view for description, not a fitted predictor.
    endpoint = []
    for p in PARENTS:
        for end in range(20000, 200001, 20000):
            d = dict(original_seed=p, end_step=end)
            for metric in ("critic_loss", "entropy_coefficient", "critic_0_abs_td_error"):
                found = next(x for x in windows if x["condition"] == "parent" and x["original_seed"] == p
                             and x["end_step"] == end and x["metric"] == metric)
                d[metric+"_median"] = found["median"]
            for t in TASKS:
                found = next(x for x in task_windows if x["condition"] == "parent" and x["original_seed"] == p
                             and x["end_step"] == end and x["task"] == t)
                d[t+"_training_success"] = found["success_rate"]
                d[t+"_return_median"] = found["return_median"]
            endpoint.append(d)
    run.table("a3_pretraining_timeline.csv", endpoint)
    return windows, task_windows, exposure, prefixes, endpoint


def plot_results(run, a1, a2, a3, logs, windows, tasks):
    # Local rendering only; force cache inside this fresh run.
    os.environ["MPLCONFIGDIR"] = str(run.path / "matplotlib_cache")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                         "savefig.dpi": 160, "figure.constrained_layout.use": True})
    figures = run.path / "figures"
    figures.mkdir()
    colors = {"dose625": "#1763A6", "alternate4k": "#D45B27", "mixture": "#218565"}

    def save(fig, name):
        fig.savefig(figures / (name+".png"))
        fig.savefig(figures / (name+".svg"))
        plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.3))
    for ax, control in zip(axes, ("BP", "fixed")):
        x = np.arange(5)
        d = a1["parent_differences"]
        ax.bar(x-.18, [r["within_vs_"+control+"_pp"] for r in d], .36, label="Within continuation", color="#1763A6")
        ax.bar(x+.18, [r["across_vs_"+control+"_pp"] for r in d], .36, label="Across continuations", color="#D45B27")
        ax.set_xticks(x, [str(p) for p in PARENTS])
        ax.axhline(0, color="black", lw=.8)
        ax.set_title("Selection minus " + ("BP" if control == "BP" else "leave-parent-out fixed"))
        ax.set_ylabel("Macro success difference (pp)")
    axes[0].legend()
    fig.suptitle("A1: disjoint evaluation halves; four folds averaged per parent")
    save(fig, "a1_within_across")

    contrasts = run.rows(run.path / "a2_contrasts.csv")
    # This output read is provenance-recorded, not an external source.
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    for ax, (a, b) in zip(axes, PAIRS):
        for ri, r in enumerate(REPEATS):
            rows = [d for d in contrasts if d["a"] == a and d["b"] == b and d["contrast"] == str(r)]
            y = np.arange(5)+(ri-.5)*.22
            point = np.array([float(d["observed_pp"]) for d in rows])
            lo = np.array([float(d["simultaneous_low_pp"]) for d in rows])
            hi = np.array([float(d["simultaneous_high_pp"]) for d in rows])
            ax.errorbar(point, y, xerr=[point-lo, hi-point], fmt="o", capsize=3, label=str(r))
        ax.set_yticks(range(5), [str(p) for p in PARENTS])
        ax.axvline(0, color="black", lw=.8)
        ax.set_xlabel("Macro success difference (pp)")
        ax.set_title(a+" minus "+b)
        ax.invert_yaxis()
    axes[0].legend()
    fig.suptitle("A2: simultaneous 95% intervals across all 45 case-bootstrap contrasts")
    save(fig, "a2_rank_reversal_intervals")

    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), sharey=True)
    for ax, c in zip(axes, METHODS):
        rows = [d for d in a3["parents"] if d["condition"] == c]
        x = np.arange(5)
        ax.bar(x, [d["gain_pp"] for d in rows], color="#218565", label="New success")
        ax.bar(x, [-d["loss_pp"] for d in rows], color="#B53B44", label="Lost parent success")
        ax.plot(x, [d["net_pp"] for d in rows], "ko", label="Net change")
        ax.set_xticks(x, [str(p) for p in PARENTS], rotation=30)
        ax.axhline(0, color="black", lw=.8)
        ax.set_title(c)
    axes[0].set_ylabel("Macro contribution (pp), two-repeat mean")
    axes[0].legend(fontsize=8)
    fig.suptitle("A3: acquisitions and losses on the same parent evaluation cases")
    save(fig, "a3_gains_losses")

    for stage, methods, width, scale, xmax in (("pretraining", ("parent",), 20000, 1000, 200),
                                               ("continuation", METHODS, 4000, 1000, 40)):
        fig, axes = plt.subplots(5, 3, figsize=(14, 13), sharex=True)
        metrics = ("critic_loss", "entropy_coefficient", "critic_0_abs_td_error")
        for pi, p in enumerate(PARENTS):
            for mi, metric in enumerate(metrics):
                ax = axes[pi, mi]
                for c in methods:
                    for r in ((0,) if c == "parent" else REPEATS):
                        color = "#1763A6" if c == "parent" else colors[c]
                        style = "-" if r in (0, 4201) else "--"
                        raw = logs[p, c, r]
                        pairs = [(d["relative_step"]/scale, num(d[metric])) for d in raw if d[metric]]
                        ax.plot([x for x, y in pairs], [y for x, y in pairs], color=color, alpha=.1, lw=.5)
                        b = [d for d in windows if d["original_seed"] == p and d["condition"] == c
                             and d["continuation"] == r and d["metric"] == metric]
                        x = [(d["begin_step"]+d["end_step"])/(2*scale) for d in b]
                        ax.plot(x, [d["median"] for d in b], style, color=color, label=c+" "+str(r), lw=1.5)
                        if c == "parent":
                            ax.fill_between(x, [d["q25"] for d in b], [d["q75"] for d in b], color=color, alpha=.15)
                ax.set_yscale("log")
                ax.set_xlim(0, xmax)
                if stage == "continuation":
                    ax.axvline(8, color="gray", ls=":", lw=.8)
                if pi == 0:
                    ax.set_title(metric)
                if mi == 0:
                    ax.set_ylabel(str(p)+" (log scale)")
                if pi == 4:
                    ax.set_xlabel(stage+" steps (k)")
        if stage == "continuation":
            axes[0, 0].legend(fontsize=6, ncol=2)
        fig.suptitle("A3: "+stage+"; raw snapshots and fixed-window medians (not outcome success)")
        save(fig, "a3_"+stage+"_metrics")
    fig, axes = plt.subplots(5, 4, figsize=(15, 12), sharex=True, sharey=True)
    for pi, p in enumerate(PARENTS):
        for ti, task in enumerate(TASKS):
            ax = axes[pi, ti]
            for c, r in itertools.product(METHODS, REPEATS):
                rows = [d for d in tasks if (d["original_seed"], d["condition"], d["continuation"], d["task"]) == (p, c, r, task)]
                ax.plot([(d["begin_step"]+d["end_step"])/2000 for d in rows],
                        [np.nan if d["success_rate"] is None else d["success_rate"]*100 for d in rows],
                        "-" if r == 4201 else "--", color=colors[c], lw=1)
            ax.axvline(8, color="gray", ls=":", lw=.8)
            if pi == 0:
                ax.set_title(task)
            if ti == 0:
                ax.set_ylabel(str(p)+" training success (%)")
            if pi == 4:
                ax.set_xlabel("Additional training steps (k)")
    fig.suptitle("A3: stochastic training episodes, 4k bins; solid=4201, dashed=4202")
    save(fig, "a3_training_success")
    return matplotlib.__version__


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    run = Run()
    try:
        outcomes, logs, episodes, prior, oldcross, protocol = load_inputs(run)
        print("Inputs verified; calculating A1-A3.", flush=True)
        a1 = analyze_selection(run, outcomes, prior, oldcross)
        a2 = analyze_case_uncertainty(run, outcomes)
        a3 = analyze_transitions(run, outcomes)
        windows, tasks, exposure, prefixes, timeline = analyze_trajectories(run, logs, episodes)
        mpl = plot_results(run, a1, a2, a3, logs, windows, tasks)
        within = next(d for d in a1["primary"] if d["mode"] == "within")
        refits = [d for d in a1["full_parent_removal"] if d["mode"] == "within"]
        screen = {
            "within_at_least_1pp_both": all(within[k] >= 1 for k in ("vs_BP_pp", "vs_fixed_pp")),
            "within_positive_all_full_removals": all(d[k] > 0 for d in refits for k in ("vs_BP_pp", "vs_fixed_pp")),
            "strong_reversal_outside_41013": any(d["strong_reversal"] and d["original_seed"] != 41013 for d in a2["reversals"])
        }
        summary = dict(execution_status="completed_A1_A2_A3", authorization="A_only",
                       original_seeds=PARENTS, continuation_labels=REPEATS, tasks=TASKS,
                       counts=dict(policies=35, evaluation_cases=14000, metric_rows=8800, training_episodes=4400),
                       A1=a1, A2=a2, A3={k: v for k, v in a3.items() if k != "paths"},
                       prefix_BP=[d for d in prefixes if d["condition"] == "dose625"],
                       optional_switch_necessary_screen_parts=screen,
                       optional_switch_necessary_screen_pass=all(screen.values()),
                       continuation="B and C remain unexecuted; screen pass is not authorization or predictive validation",
                       uncertainty="A1: five original parents; four dependent scores per parent. A2: fitted-policy conditional case uncertainty. A3: descriptive observed paths, no causal or online prediction proof.",
                       costs=dict(new_training_steps=0, new_evaluation_steps=0, new_environment_steps=0,
                                  new_SAC_updates=0, GPU_execution=False, wall_seconds=time.perf_counter()-run.started,
                                  CPU_seconds=time.process_time()-run.cpu),
                       runtime=dict(python=sys.version, platform=platform.platform(), numpy=np.__version__, matplotlib=mpl))
        run.write("summary.json", summary)
        run.write("checks.json", {"passed": len(run.checks), "failed": 0, "checks": run.checks,
                                   "scope": "Technical correctness, not scientific significance"})
        # Outputs read while rendering are already listed in output hashes; keep original inputs separate.
        external = {p: h for p, h in run.inputs.items() if not Path(p).is_relative_to(run.path)}
        run.write("input_hashes.json", external)
        run.write("output_hashes.json", {str(p.relative_to(run.path)): digest(p.read_bytes())
                                        for p in run.path.rglob("*") if p.is_file() and "matplotlib_cache" not in p.parts})
        (HERE / "LATEST_ANALYSIS.json").write_text(json.dumps(
            {"run": str(run.path), "summary_sha256": digest((run.path / "summary.json").read_bytes())}, indent=2), encoding="utf-8")
        print(json.dumps({"run": str(run.path), "A1": a1["primary"], "A2_strong_reversals": a2["strong_reversal_count"],
                          "A3_methods": a3["methods"], "switch_necessary_screen": screen,
                          "checks": len(run.checks), "new_environment_steps": 0}, indent=2))
    except BaseException:
        run.write("failure.json", {"traceback": traceback.format_exc(), "checks": run.checks,
                                   "input_hashes": run.inputs, "wall_seconds": time.perf_counter()-run.started,
                                   "CPU_seconds": time.process_time()-run.cpu, "new_environment_steps": 0,
                                   "new_SAC_updates": 0})
        raise


if __name__ == "__main__":
    main()
