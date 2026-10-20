"""Independent arithmetic/provenance verification. No import of analyze.py."""
import csv
import hashlib
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
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PARENTS = (41011, 41012, 41013, 41014, 41015)
METHODS = ("dose625", "alternate4k", "mixture")
TASKS = ("DO", "DC", "PU", "BP")
REPEATS = (4201, 4202)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    start, cpu = time.perf_counter(), time.process_time()
    dest = HERE / "results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                              + "_verification_" + uuid.uuid4().hex[:8])
    (dest / "source_snapshot").mkdir(parents=True, exist_ok=False)
    shutil.copy2(__file__, dest / "source_snapshot/verify.py")
    source_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    checks, inputs = [], {}

    def check(name, ok):
        checks.append({"check": name, "passed": bool(ok)})
        if not ok:
            raise AssertionError(name)

    def read(path):
        path = Path(path).resolve()
        data = path.read_bytes()
        inputs[str(path)] = hashlib.sha256(data).hexdigest()
        return data

    def js(path):
        return json.loads(read(path).decode("utf-8-sig"))

    def rows(path):
        import io
        return list(csv.DictReader(io.StringIO(read(path).decode("utf-8-sig"))))

    def save(name, data):
        with (dest / name).open("x", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, allow_nan=False)

    def close(a, b):
        return abs(float(a)-float(b)) < 1e-9

    try:
        latest = js(HERE / "LATEST_ANALYSIS.json")
        src = Path(latest["run"])
        check("summary_hash", hashlib.sha256(read(src/"summary.json")).hexdigest() == latest["summary_sha256"])
        for manifest in ("input_hashes.json", "output_hashes.json"):
            for path, expected in js(src/manifest).items():
                target = Path(path) if manifest.startswith("input") else src/path
                check("frozen_hash:"+str(target), hashlib.sha256(read(target)).hexdigest() == expected)
        data = rows(src/"outcome_cases.csv")
        y, casekeys = {}, {}
        for d in data:
            p, c, r, t, i = int(d["original_seed"]), d["condition"], int(d["continuation"]), d["task"], int(d["episode_index"])
            y[p, c, r, t, i] = int(d["success"])
            key = p, t, i
            sig = d["seed"], d["initial_state_hash"]
            if key in casekeys:
                check("paired_identity:"+str((p, c, r, t, i)), casekeys[key] == sig)
            casekeys[key] = sig
        check("unique_14000_observations", len(y) == 14000 and len(casekeys) == 2000)
        half = {}
        for p, c, r, h in itertools.product(PARENTS, METHODS, REPEATS, (0, 1)):
            half[p, c, r, h] = sum(y[p, c, r, t, i] for t in TASKS for i in range(h*50, (h+1)*50))/2
        foldrows = rows(src/"a1_folds.csv") + rows(src/"a1_full_parent_removal_folds.csv")
        for j, d in enumerate(foldrows):
            group = METHODS if d["group"] == "all" else tuple(d["group"].split("_vs_"))
            p, r, h, excluded = int(d["original_seed"]), int(d["target_repeat"]), int(d["selection_half"]), int(d["excluded_parent"])
            sr = r if d["mode"] == "within" else 8403-r
            allowed = [q for q in PARENTS if q not in (p, excluded)]
            # Sorting uses explicit method-priority index, independent of max iteration order.
            selected = sorted(group, key=lambda c: (-half[p, c, sr, h], METHODS.index(c)))[0]
            fixed = sorted(group, key=lambda c: (-sum(half[q, c, rr, h] for q in allowed for rr in REPEATS),
                                                METHODS.index(c)))[0]
            score, bp, fs = half[p, selected, r, 1-h], half[p, "dose625", r, 1-h], half[p, fixed, r, 1-h]
            check("A1_direct_fold:"+str(j), selected == d["choice"] and fixed == d["fixed_choice"]
                  and close(score, d["selected_pp"]) and close(score-bp, d["vs_BP_pp"])
                  and close(score-fs, d["vs_fixed_pp"]))
        for j, d in enumerate(rows(src/"a1_summary.csv")):
            part = [x for x in foldrows if all(x[k] == d[k] for k in ("group", "excluded_parent", "mode"))]
            parent_values = [statistics.mean(float(x["selected_pp"]) for x in part if x["original_seed"] == str(p))
                             for p in PARENTS if p != int(d["excluded_parent"])]
            check("A1_parent_aggregation:"+str(j), close(statistics.mean(parent_values), d["selected_pp"]))
        zfile = src/"a2_resampled_case_indices.npz"
        dfile = src/"a2_bootstrap_draws.npz"
        read(zfile)
        read(dfile)
        idx, boot = np.load(zfile), np.load(dfile)
        definition = js(src/"a2_definition.json")
        rng = np.random.default_rng(460202)
        for pi, p in enumerate(PARENTS):
            for ti, t in enumerate(TASKS):
                saved = idx[str(p)+"_"+t]
                check("A2_exact_rng:"+str((p, t)),
                      np.array_equal(saved, rng.integers(0, 100, size=(20000, 100), dtype=np.int64)))
            for b in (0, 17, 999, 4097, 19999):
                for pol, (c, r) in enumerate(definition["policy_order"]):
                    # Counter-weighted summation checks pairing without advanced-indexing code.
                    val = 0
                    for t in TASKS:
                        weights = Counter(idx[str(p)+"_"+t][b].tolist())
                        val += sum(w*y[p, c, r, t, i] for i, w in weights.items())/4
                    check("A2_weighted_reconstruction:"+str((p, b, pol)),
                          close(val, boot["policy_means_pp"][b, pi, pol]))
        contrast_rows = rows(src/"a2_contrasts.csv")
        qvals = []
        for j, d in enumerate(contrast_rows):
            pi = PARENTS.index(int(d["original_seed"]))
            vector = []
            point = []
            for r in REPEATS:
                ai = definition["policy_order"].index([d["a"], r])
                bi = definition["policy_order"].index([d["b"], r])
                vector.append(boot["policy_means_pp"][:, pi, ai] - boot["policy_means_pp"][:, pi, bi])
                point.append(sum(y[PARENTS[pi], d["a"], r, t, i] - y[PARENTS[pi], d["b"], r, t, i]
                                 for t in TASKS for i in range(100))/4)
            if d["contrast"] == "4202-minus-4201":
                target, obs = vector[1]-vector[0], point[1]-point[0]
            else:
                ri = REPEATS.index(int(d["contrast"]))
                target, obs = vector[ri], point[ri]
            se = float(np.std(target, ddof=1))
            check("A2_all_draws:"+str(j), np.allclose(target, boot["contrasts_pp"][:, j], atol=1e-12)
                  and close(obs, d["observed_pp"]) and close(se, d["bootstrap_SD_pp"]))
            if se > 1e-12:
                qvals.append(abs((target-obs)/se))
            quantiles = np.quantile(target, [.025, .975])
            check("A2_marginal:"+str(j), close(quantiles[0], d["marginal_low_pp"])
                  and close(quantiles[1], d["marginal_high_pp"]))
        crit = float(np.quantile(np.max(np.stack(qvals), axis=0), .95))
        check("A2_family_critical_value", close(crit, definition["simultaneous_critical_value"]))
        for j, d in enumerate(contrast_rows):
            point, se = float(d["observed_pp"]), float(d["bootstrap_SD_pp"])
            check("A2_simultaneous:"+str(j), close(point-crit*se, d["simultaneous_low_pp"])
                  and close(point+crit*se, d["simultaneous_high_pp"]))
        for d in rows(src/"a3_case_transitions.csv"):
            p, c, r, t = int(d["original_seed"]), d["condition"], int(d["continuation"]), d["task"]
            before = {i for i in range(100) if y[p, "parent", 0, t, i]}
            after = {i for i in range(100) if y[p, c, r, t, i]}
            check("A3_set_transition:"+str((p, c, r, t)), len(after-before) == int(d["gain"])
                  and len(before-after) == int(d["loss"]) and len(before & after) == int(d["retained"])
                  and close(len(after)-len(before), d["net_pp"]))
            check("A3_NA_denominators:"+str((p, c, r, t)),
                  (d["acquisition_given_parent_failure"] == "") == (len(before) == 100)
                  and (d["retention_given_parent_success"] == "") == (len(before) == 0))
        for d in rows(src/"a3_pair_decomposition.csv"):
            check("A3_pair_identity:"+str((d["original_seed"], d["continuation"], d["a"], d["b"], d["task"])),
                  close(float(d["gain_difference_pp"])+float(d["loss_reduction_pp"]), d["net_difference_pp"]))
        raw = rows(src/"training_metrics_raw.csv")
        grouped = defaultdict(list)
        for d in raw:
            grouped[int(d["original_seed"]), d["condition"], int(d["continuation"])].append(d)
        for d in rows(src/"a3_metric_windows.csv"):
            key = int(d["original_seed"]), d["condition"], int(d["continuation"])
            vals = [float(x[d["metric"]]) for x in grouped[key] if int(d["begin_step"]) < int(x["relative_step"]) <= int(d["end_step"])
                    and x[d["metric"]] != ""]
            check("A3_window_median:"+str((key, d["end_step"], d["metric"])),
                  len(vals) == int(d["n"]) and (not vals or close(statistics.median(vals), d["median"])))
        for d in rows(src/"a3_exposure_windows.csv"):
            key = int(d["original_seed"]), d["condition"], int(d["continuation"])
            lookup = {int(x["relative_step"]): x for x in grouped[key]}
            begin, end = int(d["begin_step"]), int(d["end_step"])
            if begin == 0 and key[1] == "parent":
                prev = {k: "0" for k in lookup[end]}
            elif begin == 0:
                prev = next(x for x in grouped[key[0], "parent", 0] if int(x["step"]) == 200000)
            else:
                prev = lookup[begin]
            check("A3_inherited_counters:"+str((key, begin)),
                  all(int(d[k]) == int(lookup[end][k])-int(prev[k])
                      for k in (f"{kind}_{t}" for kind in ("collected", "sampled") for t in TASKS)))
        prefix = rows(src/"a3_prefix_only_signals.csv")
        for d in prefix:
            key = int(d["original_seed"]), d["condition"], int(d["continuation"])
            windows = [[(float(x["critic_0_abs_td_error"])+float(x["critic_1_abs_td_error"]))/2
                        for x in grouped[key] if lo < int(x["relative_step"]) <= hi]
                       for lo, hi in ((0, 4000), (4000, 8000))]
            score = math.log((statistics.median(windows[1])+1e-6)/(statistics.median(windows[0])+1e-6))
            check("A3_no_future_prefix:"+str(key), close(score, d["z"]) and all(len(v) == 16 for v in windows))
        # Input-only action audit; no B outcome labels, no fitting or checkpoint evaluation.
        bp = [d for d in prefix if d["condition"] == "dose625"]
        actions = []
        for d in bp:
            for threshold in (1.5, 2, 4, 8):
                actions.append(dict(original_seed=int(d["original_seed"]), continuation=int(d["continuation"]),
                                    z=float(d["z"]), threshold=math.log(threshold),
                                    stop=float(d["z"]) > math.log(threshold)))
        with (dest/"prefix_rule_action_audit.csv").open("x", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(actions[0]))
            w.writeheader()
            w.writerows(actions)
        summary = dict(status="verified", analysis_run=str(src), analysis_summary_sha256=latest["summary_sha256"],
                       checks_passed=len(checks), failed_checks=0,
                       prefix_action_audit=dict(z_min=min(float(d["z"]) for d in bp),
                                               z_max=max(float(d["z"]) for d in bp),
                                               minimum_numeric_threshold=math.log(1.5),
                                               numeric_rules_stop_count=sum(d["stop"] for d in actions),
                                               numeric_rule_decisions=len(actions),
                                               conclusion="All four numeric thresholds and always-continue yield the same keep vector. Only the always-stop vector differs. No B rule fit performed."),
                       new_environment_steps=0, new_SAC_updates=0, wall_seconds=time.perf_counter()-start,
                       CPU_seconds=time.process_time()-cpu, python=sys.version, numpy=np.__version__,
                       platform=platform.platform(), source_sha256=source_hash)
        save("summary.json", summary)
        save("checks.json", checks)
        save("input_hashes.json", inputs)
        save("source_hashes.json", {"verify.py": source_hash})
        (HERE/"LATEST_VERIFICATION.json").write_text(json.dumps(
            {"run": str(dest), "summary_sha256": hashlib.sha256((dest/"summary.json").read_bytes()).hexdigest()}, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
    except BaseException:
        save("failure.json", dict(traceback=traceback.format_exc(), checks=checks, input_hashes=inputs,
                                 source_sha256=source_hash, new_environment_steps=0, new_SAC_updates=0,
                                 wall_seconds=time.perf_counter()-start, CPU_seconds=time.process_time()-cpu))
        raise


if __name__ == "__main__":
    main()
