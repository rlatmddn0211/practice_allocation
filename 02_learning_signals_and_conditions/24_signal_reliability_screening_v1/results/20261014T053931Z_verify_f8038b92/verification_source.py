"""Independent, standard-library check of raw records and full-D decisions."""
import csv
import hashlib
import json
import math
import shutil
import statistics as st
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha(path):
    with Path(path).open("rb") as h:
        return hashlib.file_digest(h, "sha256").hexdigest()


def main():
    source = Path(sys.argv[1]).resolve()
    start = time.perf_counter()
    out = HERE / "results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_verify_") + uuid.uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    shutil.copy2(__file__, out / "verification_source.py")
    checks, evidence = [], {}

    def ck(name, good):
        checks.append({"name": name, "passed": bool(good)})
        if not good:
            raise AssertionError(name)

    def read(name):
        path = source / name
        evidence[str(path)] = sha(path)
        return json.loads(path.read_text(encoding="utf-8-sig"))

    def csvread(path):
        path = Path(path)
        evidence[str(path)] = sha(path)
        with path.open(encoding="utf-8-sig", newline="") as h:
            return list(csv.DictReader(h))

    summary = {"status": "failed", "environment_steps": 0, "learner_updates": 0}
    try:
        p, result, split = read("protocol.json"), read("summary.json"), read("case_splits.json")
        ck("analysis completed", result["status"] == "completed" and result["checks_failed"] == 0)
        ck("executed analysis source hash", sha(source / "analysis_source.py") == result["source_sha256"])
        for path, expected in read("input_hashes.json").items():
            ck("unchanged input " + path, sha(path) == expected)
        data, lens, full, parent = {}, {}, {}, {}
        for r in csvread(source / "evaluations.csv"):
            raw = csvread(r["episodes_path"])
            ck("raw episode manifest " + r["id"], evidence[r["episodes_path"]] == r["episode_sha256"])
            suite, seed, cp = r["suite"], int(r["original_seed"]), int(r["checkpoint_step"])
            by_task = {t: {} for t in p["suites"][suite]}
            by_length = {t: {} for t in by_task}
            for e in raw:
                by_task[e["task"]][int(e["episode_index"])] = int(e["success"])
                by_length[e["task"]][int(e["episode_index"])] = int(e["length"])
            ck("raw scalar " + r["id"], abs(st.mean(st.mean(v.values()) for v in by_task.values()) * 100 - float(r["macro_pct"])) < 1e-9)
            key = (suite, seed, cp, int(r["horizon"]), int(r["continuation_label"]), r["allocation"])
            full[key] = by_task
            for label in ("D", "O"):
                data[key, label] = [[by_task[t][i] for i in split[suite][label][ti]] for ti, t in enumerate(by_task)]
                lens[key, label] = [[by_length[t][i] for i in split[suite][label][ti]] for ti, t in enumerate(by_task)]
            if r["role"] == "baseline":
                parent[suite, seed, cp] = st.mean(sum(data[key, "O"], []))
        decisions = csvread(source / "selection_by_context_repeat.csv")
        checked = 0
        for row in decisions:
            if int(row["cases_per_task"]) != 50:
                continue
            suite, seed, cp = row["suite"], int(row["original_seed"]), int(row["checkpoint_step"])
            names = ["U"] + ["F_" + t for t in p["suites"][suite]]
            repeat = int(row["held_continuation"])
            mode, method = row["mode"], row["method"]
            others = [r for r in p["continuations"][suite] if r != repeat]
            source_h = 40000 if mode == "cross_repeat_40" else 20000
            donors = [repeat] if mode == "same_trajectory_20_to_40" else others
            target_h = 20000 if mode in ("measurement_only_20", "cross_repeat_20") else 40000
            targets = others if mode == "measurement_only_20" else [repeat]
            fixed_scores = {a: st.mean(st.mean(sum(data[(suite, s, cp, 40000, r, a), "D"], []))
                                             for s in p["original_seeds"] if s != seed for r in p["continuations"][suite]) for a in names}
            fixed = max(names, key=fixed_scores.get)
            score = {a: st.mean(st.mean(sum(data[(suite, seed, cp, source_h, r, a), "D"], [])) for r in donors) for a in names}
            greedy = max(names, key=score.get)
            fallback = "U" if method.endswith("Uniform") or method == "Uniform" else fixed
            choice = {"Uniform": "U", "Development_fixed": fixed, "Greedy": greedy}.get(method)
            raw_gap = score[greedy] - score[fallback]
            if method.startswith("Gap2_"):
                choice = greedy if raw_gap >= .02 - 1e-12 else fallback
            if method.startswith("Reliability_"):
                paired = [[st.mean(data[(suite, seed, cp, source_h, r, greedy), "D"][t][i]
                                   - data[(suite, seed, cp, source_h, r, fallback), "D"][t][i] for r in donors)
                           for i in range(50)] for t in range(4)]
                k = len(donors)
                prior_second = st.mean([(-1 + j / k) ** 2 for j in range(2 * k + 1)])
                means = [sum(v) / 51 for v in paired]
                variance = [((sum(x * x for x in v) + prior_second) / 51 - m * m) / 52 for v, m in zip(paired, means)]
                lower = st.mean(means) - p["reliability_rule"]["lower_score_z"] * math.sqrt(sum(variance)) / 4
                agreed = all(st.mean(sum(data[(suite, seed, cp, source_h, r, greedy), "D"], []))
                             > st.mean(sum(data[(suite, seed, cp, source_h, r, fallback), "D"], [])) + 1e-12 for r in donors)
                choice = greedy if raw_gap >= .02 - 1e-12 and lower > 0 and agreed else fallback
            value = st.mean(st.mean(sum(data[(suite, seed, cp, target_h, r, choice), "O"], [])) for r in targets)
            uniform = st.mean(st.mean(sum(data[(suite, seed, cp, target_h, r, "U"), "O"], [])) for r in targets)
            ck("full D decision " + str(checked), abs(float(row["choose_" + choice + "_pct"]) - 100) < 1e-9)
            ck("full D score " + str(checked), abs(float(row["score_pp"]) - value * 100) < 1e-9)
            ck("full D uniform contrast " + str(checked), abs(float(row["vs_uniform_pp"]) - (value - uniform) * 100) < 1e-9)
            ck("full D parent contrast " + str(checked), abs(float(row["absolute_gain_pp"]) - (value - parent[suite, seed, cp]) * 100) < 1e-9)
            if method not in ("Uniform", "Development_fixed"):
                cost = sum(sum(sum(lens[(suite, seed, cp, source_h, r, a), "D"], [])) for r in donors for a in names)
                ck("full D observed eval cost " + str(checked), abs(float(row["simulated_diagnostic_eval_steps_mean"]) - cost) < 1e-9)
            checked += 1
        ck("all 1260 full D rows checked", checked == 1260)
        pooled = csvread(source / "selection_summary.csv")
        for row in pooled:
            match = [r for r in decisions if all(r[k] == row[k] for k in ("mode", "cases_per_task", "method"))]
            for metric in ("vs_uniform_pp", "vs_development_fixed_pp", "vs_greedy_pp", "vs_gap_only_pp", "hindsight_regret_pp"):
                calc = st.mean(st.mean(float(r[metric]) for r in match if r["suite"] == suite) for suite in p["suites"])
                ck("equal suite aggregation " + str((row["mode"], row["cases_per_task"], row["method"], metric)), abs(calc - float(row[metric])) < 1e-9)
        pairs = csvread(source / "horizon_pairs.csv")
        reverse_count = 0
        for row in pairs:
            suite, seed, cp = row["suite"], int(row["original_seed"]), int(row["checkpoint_step"])
            values = []
            for horizon in (20000, 40000):
                per_repeat = []
                for repeat in p["continuations"][suite]:
                    a = full[(suite, seed, cp, horizon, repeat, row["allocation_a"])]
                    b = full[(suite, seed, cp, horizon, repeat, row["allocation_b"])]
                    per_repeat.append(st.mean(st.mean(a[t][i] - b[t][i] for i in range(100)) for t in a) * 100)
                values.append(st.mean(per_repeat))
                ck("independent horizon contrast " + str((suite, seed, cp, horizon, row["allocation_a"], row["allocation_b"])),
                   abs(values[-1] - float(row["difference_" + str(horizon // 1000) + "k_pp"])) < 1e-9)
                if horizon == 40000:
                    ck("observed continuation SD " + str((suite, seed, cp, row["allocation_a"], row["allocation_b"])),
                       abs(st.stdev(per_repeat) - float(row["observed_continuation_sd_40_pp"])) < 1e-9)
            reverse_count += values[0] * values[1] < -1e-12
        ck("horizon reversals independently recovered", reverse_count == result["observed_horizon_reversals"] == 43)
        summary.update(status="passed", full_D_rows_independently_checked=checked, horizon_pairs_checked=len(pairs))
    except Exception:
        summary["error"] = traceback.format_exc()
        print(summary["error"])
    finally:
        summary.update(wall_seconds=time.perf_counter() - start, checks=len(checks), failed=sum(not r["passed"] for r in checks),
                       python=sys.version, analysis_run=str(source), source_sha256=sha(__file__))
        for name, obj in [("summary.json", summary), ("checks.json", checks), ("input_hashes.json", evidence)]:
            with (out / name).open("x", encoding="utf-8") as h:
                json.dump(obj, h, ensure_ascii=False, indent=2)
                h.write("\n")
    print(json.dumps({"output": str(out), **summary}))
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
