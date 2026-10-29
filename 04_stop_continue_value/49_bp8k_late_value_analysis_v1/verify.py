"""Independent B arithmetic checks or synthetic preflight, no environments."""
import argparse
import ast
import csv
import hashlib
import io
import itertools
import json
import math
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
REPEATS = (4201, 4202)
TASKS = ("DO", "DC", "PU", "BP")


def synthetic_checks(check):
    # Eight possible histories show why gains/losses cannot be added over intervals.
    for a, b, c in itertools.product((0, 1), repeat=3):
        eg, el = int(a == 0 and b == 1), int(a == 1 and b == 0)
        lg, ll = int(b == 0 and c == 1), int(b == 1 and c == 0)
        tg, tl = int(a == 0 and c == 1), int(a == 1 and c == 0)
        turns = int((a, b, c) in ((0, 1, 0), (1, 0, 1)))
        check("synthetic_trajectory:"+str((a, b, c)), eg-el+lg-ll == tg-tl == c-a
              and eg+lg-tg == el+ll-tl == turns)
    # Deliberately separate axes and asymmetric weights to catch bootstrap indexing errors.
    data = np.arange(5*5*4*100).reshape(5, 5, 4, 100)
    index = np.array([[0, 0, 3, 99], [4, 1, 1, 10]])
    for pi, ti in itertools.product(range(5), range(4)):
        observed = data[pi, :, ti, :][:, index].mean(axis=2).T
        explicit = np.array([[sum(data[pi, q, ti, i] for i in row)/len(row) for q in range(5)] for row in index])
        check("synthetic_bootstrap_axes:"+str((pi, ti)), np.array_equal(observed, explicit))
    # A large between-parent difference and no within-parent difference must count as 2, not 4 units.
    sample = [[-10, -10], [10, 10]]
    parent_mean = [statistics.mean(x) for x in sample]
    check("repeat_aggregation", parent_mean == [-10, 10] and statistics.mean(parent_mean) == 0)
    # Sign inversion must swap interval endpoints for stop8 = -late.
    late, interval = 3., [-2., 8.]
    check("stop_interval_sign", -late == -3. and [-interval[1], -interval[0]] == [-8., 2.])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preflight", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    started, cpu = time.perf_counter(), time.process_time()
    label = "synthetic_check" if args.preflight else "independent_verification"
    out = HERE/"results"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+label+"_"+uuid.uuid4().hex[:8])
    (out/"source_snapshot").mkdir(parents=True, exist_ok=False)
    for p in list(HERE.glob("*.py"))+[HERE/"analysis_config.json"]:
        shutil.copy2(p, out/"source_snapshot"/p.name)
    checks, inputs = [], {}

    def check(name, ok):
        checks.append({"check": name, "passed": bool(ok)})
        if not ok:
            raise AssertionError(name)

    def read(path):
        path = Path(path).resolve()
        b = path.read_bytes()
        inputs[str(path)] = hashlib.sha256(b).hexdigest()
        return b

    def js(path):
        return json.loads(read(path).decode("utf-8-sig"))

    def rows(path):
        return list(csv.DictReader(io.StringIO(read(path).decode("utf-8-sig"))))

    def save(name, obj):
        with (out/name).open("x", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False, allow_nan=False)

    def eq(a, b):
        return abs(float(a)-float(b)) < 1e-8

    try:
        for p in HERE.glob("*.py"):
            ast.parse(read(p).decode("utf-8"))
            check("syntax:"+p.name, True)
        synthetic_checks(check)
        summary = {"mode": label, "scientific_effect_evidence": False,
                   "scope": "Technical and arithmetic verification, not an independent scientific replication"}
        if not args.preflight:
            ref = js(HERE/"LATEST_ANALYSIS.json")
            run = Path(ref["run"])
            check("summary_hash", hashlib.sha256(read(run/"summary.json")).hexdigest() == ref["summary_sha256"])
            for manifest in ("input_hashes.json", "output_hashes.json"):
                for path, h in js(run/manifest).items():
                    p = Path(path) if manifest.startswith("input") else run/path
                    check("unchanged:"+str(p), hashlib.sha256(read(p)).hexdigest() == h)
            s = js(run/"summary.json")
            raw = rows(run/"outcomes_25_policies.csv")
            y = {}
            identities = {}
            for d in raw:
                p, q, t, i = int(d["original_seed"]), d["policy"], d["task"], int(d["episode_index"])
                y[p, q, t, i] = int(d["success"])
                sig = d["seed"], d["initial_state_hash"]
                if (p, t, i) in identities:
                    check("case_pairing:"+str((p, q, t, i)), identities[p, t, i] == sig)
                identities[p, t, i] = sig
            check("unique_rows", len(y) == 10000 and len(identities) == 2000)
            for d in rows(run/"case_trajectories.csv"):
                p, r, t, i = int(d["original_seed"]), int(d["continuation"]), d["task"], int(d["episode_index"])
                triple = tuple(y[p, q, t, i] for q in ("J0", f"J8_{r}", f"J40_{r}"))
                check("trajectory_join:"+str((p, r, t, i)), triple == tuple(int(d[k]) for k in ("success0", "success8", "success40"))
                      and d["pattern"] == "".join(map(str, triple)))
            for d in rows(run/"task_gains_losses.csv"):
                p, r, t = int(d["original_seed"]), int(d["continuation"]), d["task"]
                sets = [{i for i in range(100) if y[p, q, t, i]} for q in ("J0", f"J8_{r}", f"J40_{r}")]
                a, b, c = sets
                for stage, before, after in (("early", a, b), ("late", b, c), ("total", a, c)):
                    check("set_gain_loss:"+str((p, r, t, stage)), eq(len(after-before), d[stage+"_gain_pp"])
                          and eq(len(before-after), d[stage+"_loss_pp"]) and eq(len(after)-len(before), d[stage+"_net_pp"]))
                check("conditional_empty_denominators:"+str((p, r, t)),
                      (d["late_loss_given_success8"] == "") == (len(b) == 0)
                      and (d["late_acquisition_given_failure8"] == "") == (len(b) == 100)
                      and (d["old_retention_at40"] == "") == (len(a) == 0))
            pattern_rows = rows(run/"three_time_patterns.csv")
            for p, r, t in itertools.product(PARENTS, REPEATS, TASKS):
                expected = Counter("".join(str(y[p, q, t, i]) for q in ("J0", f"J8_{r}", f"J40_{r}")) for i in range(100))
                block = [d for d in pattern_rows if (d["original_seed"], d["continuation"], d["task"]) == (str(p), str(r), t)]
                check("all_eight_patterns:"+str((p, r, t)), len(block) == 8 and sum(int(d["count"]) for d in block) == 100
                      and all(int(d["count"]) == expected[d["pattern"]] for d in block))
            for d in rows(run/"path_scores.csv"):
                p, r = int(d["original_seed"]), int(d["continuation"])
                means = [sum(y[p, q, t, i] for t in TASKS for i in range(100))/4 for q in ("J0", f"J8_{r}", f"J40_{r}")]
                check("path_scores:"+str((p, r)), all(eq(d[k], v) for k, v in zip(("J0", "J8", "J40"), means))
                      and eq(d["early_pp"], means[1]-means[0]) and eq(d["late_pp"], means[2]-means[1])
                      and eq(d["stop8_advantage_pp"], means[1]-means[2]))
            parent = rows(run/"parent_scores.csv")
            for d in parent:
                p = int(d["original_seed"])
                early, late = [], []
                for r in REPEATS:
                    a, b, c = [sum(y[p, q, t, i] for t in TASKS for i in range(100))/4
                               for q in ("J0", f"J8_{r}", f"J40_{r}")]
                    early.append(b-a)
                    late.append(c-b)
                check("parent_unit:"+str(p), eq(d["early_pp"], statistics.mean(early))
                      and eq(d["late_pp"], statistics.mean(late)))
            for d in rows(run/"parent_removal.csv"):
                p = int(d["excluded_parent"])
                block = [x for x in parent if int(x["original_seed"]) != p]
                check("whole_parent_removal:"+str(p), all(eq(d[k], statistics.mean(float(x[k]) for x in block))
                      for k in ("J0", "J8", "J40", "early_pp", "late_pp", "stop8_advantage_pp")))
            idx = np.load(run/"case_resample_indices.npz")
            bt = np.load(run/"bootstrap_draws.npz")
            definition = js(run/"bootstrap_definition.json")
            rng = np.random.default_rng(480202)
            for pi, p in enumerate(PARENTS):
                for ti, t in enumerate(TASKS):
                    ix = idx[str(p)+"_"+t]
                    check("saved_rng:"+str((p, t)), np.array_equal(ix, rng.integers(0, 100, size=(20000, 100), dtype=np.int64)))
                    for b in (0, 123, 9999, 19999):
                        w = Counter(ix[b].tolist())
                        for qi, q in enumerate(definition["policy_order"]):
                            direct = sum(count*y[p, q, t, i] for i, count in w.items())
                            check("weighted_bootstrap:"+str((p, t, b, q)),
                                  eq(direct, bt["task_policy_means_pp"][b, pi, qi, ti]))
            contrasts = rows(run/"path_contrasts_uncertainty.csv")
            macros = bt["task_policy_means_pp"].mean(axis=3)
            standardized = []
            for j, d in enumerate(contrasts):
                p, r = int(d["original_seed"]), int(d["continuation"])
                lo, hi = {"early": ("J0", f"J8_{r}"), "late": (f"J8_{r}", f"J40_{r}"),
                          "total": ("J0", f"J40_{r}")}[d["contrast"]]
                pi = PARENTS.index(p)
                ai, bi = definition["policy_order"].index(lo), definition["policy_order"].index(hi)
                v = macros[:, pi, bi]-macros[:, pi, ai]
                point = sum(y[p, hi, t, i]-y[p, lo, t, i] for t in TASKS for i in range(100))/4
                se = np.std(v, ddof=1)
                check("all_macro_draws:"+str(j), np.allclose(v, bt["macro_contrasts_pp"][:, j], atol=1e-10)
                      and eq(point, d["difference_pp"]) and eq(se, d["bootstrap_SD_pp"]))
                ci = np.quantile(v, [.025, .975])
                check("marginal_interval:"+str(j), eq(ci[0], d["marginal_low_pp"]) and eq(ci[1], d["marginal_high_pp"]))
                if se > 1e-12:
                    standardized.append(np.abs((v-point)/se))
            critical = float(np.quantile(np.max(np.stack(standardized), axis=0), .95)) if standardized else 0.
            check("joint_critical", eq(critical, definition["simultaneous_critical_value"]))
            for j, d in enumerate(contrasts):
                point, se = float(d["difference_pp"]), float(d["bootstrap_SD_pp"])
                check("simultaneous_interval:"+str(j), eq(point-critical*se, d["simultaneous_low_pp"])
                      and eq(point+critical*se, d["simultaneous_high_pp"]))
            for d in rows(run/"global_contrasts_uncertainty.csv"):
                kind = d["contrast"]
                if kind == "stop8_advantage":
                    vals = [-float(x["late_pp"]) for x in parent]
                else:
                    vals = [float(x[kind+"_pp"]) for x in parent]
                direct = sorted(statistics.mean(vals[i] for i in inds) for inds in itertools.product(range(5), repeat=5))
                ci = np.quantile(direct, [.025, .975])
                check("exact_parent_resampling:"+kind, eq(ci[0], d["parent_percentile_low_pp"])
                      and eq(ci[1], d["parent_percentile_high_pp"]) and eq(statistics.mean(vals), d["difference_pp"]))
            check("no_new_training", s["costs"]["new_training_steps"] == s["costs"]["new_SAC_updates"] == 0)
            summary.update(analysis_run=str(run), analysis_summary_sha256=ref["summary_sha256"])
        summary.update(status="passed", checks_passed=len(checks), failed_checks=0,
                       new_environment_steps=0, new_SAC_updates=0,
                       wall_seconds=time.perf_counter()-started, CPU_seconds=time.process_time()-cpu,
                       python=sys.version, numpy=np.__version__)
        save("summary.json", summary)
        save("checks.json", checks)
        save("input_hashes.json", inputs)
        save("source_hashes.json", {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (out/"source_snapshot").iterdir()})
        pointer = "LATEST_PREFLIGHT.json" if args.preflight else "LATEST_VERIFICATION.json"
        (HERE/pointer).write_text(json.dumps({"run": str(out), "summary_sha256": hashlib.sha256((out/"summary.json").read_bytes()).hexdigest()},
                                           indent=2), encoding="utf-8")
        print(json.dumps({"run": str(out), **summary}, indent=2))
    except BaseException:
        save("failure.json", dict(traceback=traceback.format_exc(), checks=checks, input_hashes=inputs,
                                 new_environment_steps=0, new_SAC_updates=0))
        raise


if __name__ == "__main__":
    main()
