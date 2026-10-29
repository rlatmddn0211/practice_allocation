"""Extend the frozen v16 episode-level validation with descriptive E0-E2 analyses.

Standard library only. Does not import any learner or alter experiment state.
Every invocation preserves its source, input hashes, costs and failures in a new run.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
import sys
import time
import traceback
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
V16 = REPO / "16_e0_e2_results_analysis_v1/results/20261012T065024Z_70db8b08"
TASKS = ("DO", "DC", "WO", "WC")
ORDER = ("U", "F_DO", "F_DC", "F_WO", "F_WC")
DCPLUS, WOPLUS = "DC_plus_WO_minus", "DC_minus_WO_plus"


def main():
    started = time.perf_counter()
    out = ROOT / "results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(__file__, out / "analysis_source.py")
    hashes, checks = {}, {}

    def sha(path):
        path = Path(path)
        with path.open("rb") as f:
            h = hashlib.file_digest(f, "sha256").hexdigest()
        hashes[str(path)] = h
        return h

    def read(path):
        sha(path)
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))

    def rows(path):
        sha(path)
        with Path(path).open(encoding="utf-8-sig", newline="") as f:
            result = list(csv.DictReader(f))
        for r in result:
            for k, v in r.items():
                try:
                    r[k] = float(v) if "." in v or "e" in v.lower() else int(v)
                except (ValueError, TypeError):
                    pass
        return result

    def save_json(name, value):
        (out / name).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")

    def save_csv(name, values):
        if values:
            with (out / name).open("x", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, list(values[0]))
                w.writeheader()
                w.writerows(values)

    def close(a, b):
        assert math.isclose(a, b, abs_tol=1e-8), (a, b)

    try:
        validation = read(V16 / "analysis.json")
        assert validation["passed"] and validation["episode_count"] == 112800
        old_hashes = read(V16 / "input_hashes.json")
        branch = rows(V16 / "branch_recomputed.csv")
        baseline = rows(V16 / "baseline_success.csv")
        rule_rows = rows(V16 / "rule_choices.csv")
        old_alloc = rows(V16 / "allocation_summary.csv")
        old_context = rows(V16 / "context_results.csv")
        old_rule_summary = rows(V16 / "rule_summary.csv")
        assert len(branch) == 259 and len(rule_rows) == 252
        numfields = [k for k in branch[0] if k.endswith("_pct") or k.endswith("_pp")]

        def summarize(values, keys):
            groups = defaultdict(list)
            for r in values:
                groups[tuple(r[k] for k in keys)].append(r)
            return [{**dict(zip(keys, k)), **{f: mean(r[f] for r in rs) for f in numfields}}
                    for k, rs in sorted(groups.items())]

        context = summarize(branch, ["stage", "original_seed", "checkpoint_step", "horizon", "allocation"])
        # Check balanced nested grain before using context means.
        counts = Counter((r["stage"], r["original_seed"], r["checkpoint_step"], r["horizon"], r["allocation"]) for r in branch)
        assert all(n == (5 if k[0] == "E0" else 3) for k, n in counts.items())
        seed_mean = summarize([r for r in context if r["stage"] != "E0"], ["stage", "original_seed", "horizon", "allocation"])
        alloc_mean = summarize(seed_mean, ["stage", "horizon", "allocation"])
        for r in alloc_mean:
            stored = next(s for s in old_alloc if all(s[k] == r[k] for k in ("stage", "horizon", "allocation")))
            for f in numfields:
                close(r[f], stored[f])
        for r in context:
            stored = next(s for s in old_context if s["stage"] == r["stage"] and s["seed"] == r["original_seed"]
                          and s["checkpoint"] == r["checkpoint_step"] and s["horizon"] == r["horizon"] and s["allocation"] == r["allocation"])
            for f in numfields:
                close(r[f], stored[f])
        checks["balanced_nested_aggregation"] = True
        checks["reconciled_branch_rows"] = len(branch)
        checks["prior_raw_episode_validation"] = validation["checks"]

        # Inspect only completed E0-E2 records; leave the running E3 queue untouched.
        campaign = Path(read(REPO / "13_e0_e3_autonomous_queue_v1/ACTIVE_CAMPAIGN.json")["campaign"])
        plan = read(campaign / "plan.json")
        assert sha(campaign / "plan.json") == read(campaign / "plan_integrity.json")["sha256"]
        costs, automatic, diagnostic = [], {}, []
        for stage in ("E0", "E1", "E2"):
            markers = sorted((campaign / "completed").glob(stage + "_*.json"))
            assert len(markers) == plan["counts"][stage]["jobs"]
            cs = Counter()
            walls, finished, actual_train_steps = [], [], 0
            for p in markers:
                marker = read(p)
                rp = Path(marker["result_ref"]["path"])
                assert sha(rp) == marker["result_ref"]["sha256"] == old_hashes[str(rp)]
                rec = read(rp)
                cp = rp.parent / "costs.json"
                cost = read(cp)
                assert cost["success"] and not cost["technical_smoke"]
                cs.update(cost["costs"])
                if rec["kind"] == "train":
                    actual_train_steps += cost["costs"]["environment_steps"]
                walls.append(cost["wall_seconds"])
                finished.append(rec["completed_at"])
                if rec["kind"] == "analysis":
                    automatic[stage] = read(rp.parent / "analysis.json")
                if rec["kind"] == "rules":
                    rr = rec["rules"]
                    diagnostic.append({"stage": stage, "seed": rec["original_seed"], "checkpoint": rec["checkpoint_step"],
                                       "Failure": rr["Failure"], "Progress": rr["Progress"],
                                       **{t + "_public_pct": 100 * rr["public_success"][t] for t in TASKS}})
            assert actual_train_steps == plan["counts"][stage]["training_steps"]
            costs.append({"stage": stage, "completed_jobs": len(markers), "training_steps": actual_train_steps,
                          "evaluation_episodes": cs["evaluation_episodes"], "all_environment_steps": cs["environment_steps"],
                          "train_iterations": cs["train_iterations"], "sum_job_wall_hours": sum(walls) / 3600,
                          "last_completed_utc": max(finished)})
        checks["completed_result_hashes_unchanged_since_v16"] = sum(c["completed_jobs"] for c in costs)
        assert sum(c["evaluation_episodes"] for c in costs) == 112800

        e0 = [r for r in old_alloc if r["stage"] == "E0"]
        e1 = [r for r in alloc_mean if r["stage"] == "E1"]
        e2 = [r for r in alloc_mean if r["stage"] == "E2"]
        cp_mean = summarize([r for r in context if r["stage"] == "E1"], ["stage", "checkpoint_step", "horizon", "allocation"])
        primary = []
        for stage, a, b, metric, cohort in [
            ("E0", "F_DC", "U", "macro", "replication_1903_1905"),
            ("E1", "F_DC", "U", "macro", "independent_pretraining"),
            ("E2", DCPLUS, WOPLUS, "DO", "independent_pretraining")]:
            vals = []
            source = branch if stage == "E0" else seed_mean
            seeds = [901] if stage == "E0" else [11, 12, 13]
            for seed in seeds:
                subset = [r for r in source if r["stage"] == stage and r["original_seed"] == seed and r["horizon"] == 40000
                          and (stage != "E0" or r["continuation_label"] in (1903, 1904, 1905))]
                vals.append(mean(r[metric + "_pct"] for r in subset if r["allocation"] == a) - mean(r[metric + "_pct"] for r in subset if r["allocation"] == b))
            ci = next(c for c in automatic[stage]["conditional_evaluation_uncertainty"] if c["cohort"] == cohort)
            primary.append({"stage": stage, "contrast": f"{a} - {b}: {metric}", "mean_pp": mean(vals), "n_original": len(seeds),
                            "positive_originals": sum(v > 0 for v in vals), "seed_values_pp": vals,
                            "case_ci_low": ci["conditional_case_bootstrap_95_interval_pp"][0],
                            "case_ci_high": ci["conditional_case_bootstrap_95_interval_pp"][1],
                            "ci_scope": "Conditional evaluation-case bootstrap; not a training-seed confidence interval"})

        task_tradeoffs = []
        for r in e1:
            if r["horizon"] == 40000:
                close(r["macro_vs_U_pp"], mean(r[t + "_vs_U_pp"] for t in TASKS))
                task_tradeoffs.append({"allocation": r["allocation"], "macro_pct": r["macro_pct"], "macro_vs_U_pp": r["macro_vs_U_pp"],
                                      **{t + "_pct": r[t + "_pct"] for t in TASKS}, **{t + "_vs_U_pp": r[t + "_vs_U_pp"] for t in TASKS}})
        temporal = []
        for a in ORDER:
            r20 = next(r for r in e1 if r["allocation"] == a and r["horizon"] == 20000)
            r40 = next(r for r in e1 if r["allocation"] == a and r["horizon"] == 40000)
            temporal.append({"allocation": a, "macro_at_20k": r20["macro_pct"], "macro_at_40k": r40["macro_pct"],
                             "gain20_vs_U": r20["macro_vs_U_pp"], "gain40_vs_U": r40["macro_vs_U_pp"],
                             "increment_20_to_40_pp": r40["macro_pct"] - r20["macro_pct"]})
        interaction = []
        for a in ORDER[1:]:
            for seed in (11, 12, 13):
                subset = [r for r in context if r["stage"] == "E1" and r["original_seed"] == seed and r["allocation"] == a and r["horizon"] == 40000]
                low = next(r for r in subset if r["checkpoint_step"] == 200000)
                high = next(r for r in subset if r["checkpoint_step"] == 400000)
                interaction.append({"allocation": a, "seed": seed, "gain200_pp": low["macro_vs_U_pp"], "gain400_pp": high["macro_vs_U_pp"],
                                    "checkpoint_interaction_pp": high["macro_vs_U_pp"] - low["macro_vs_U_pp"]})
        rule_summary = []
        for horizon in (20000, 40000):
            for rule in sorted({r["rule"] for r in rule_rows}):
                rs = [r for r in rule_rows if r["horizon"] == horizon and r["rule"] == rule]
                sr = {s: mean(r["gain_vs_U_pp"] for r in rs if r["seed"] == s) for s in (11, 12, 13)}
                v = {"horizon": horizon, "rule": rule, "gain_vs_U_pp": mean(sr.values()), **{f"seed_{s}_pp": v for s, v in sr.items()}}
                stored = next(r for r in old_rule_summary if r["horizon"] == horizon and r["rule"] == rule)
                close(v["gain_vs_U_pp"], stored["gain_vs_U_pp"])
                rule_summary.append(v)
        risk = []
        for a in ORDER:
            rs = [r for r in branch if r["stage"] == "E1" and r["horizon"] == 40000 and r["allocation"] == a]
            worst = max(rs, key=lambda r: r["maximum_task_drop_pp"])
            task = min(TASKS, key=lambda t: worst[t + "_gain_pp"])
            risk.append({"allocation": a, "branches": len(rs), "positive_vs_U_branches": sum(r["macro_vs_U_pp"] > 0 for r in rs),
                         "mean_maximum_task_drop_pp": mean(r["maximum_task_drop_pp"] for r in rs),
                         "worst_drop_pp": worst["maximum_task_drop_pp"], "worst_task": task, "worst_id": worst["id"]})
        e2_contrast = []
        for h in (20000, 40000):
            for seed in (11, 12, 13):
                rs = [r for r in context if r["stage"] == "E2" and r["original_seed"] == seed and r["horizon"] == h]
                dc, wo = [next(r for r in rs if r["allocation"] == a) for a in (DCPLUS, WOPLUS)]
                e2_contrast.append({"seed": seed, "horizon": h, "DO_DCplus_minus_WOplus_pp": dc["DO_pct"] - wo["DO_pct"],
                                    "macro_DCplus_vs_U_pp": dc["macro_vs_U_pp"], "macro_WOplus_vs_U_pp": wo["macro_vs_U_pp"]})
        checks["macro_equals_mean_task_contributions"] = True
        checks["frozen_rule_results_reconciled"] = len(rule_rows)

        datasets = {"primary": primary, "e0": e0, "e1": e1, "e2": e2, "baselines": baseline, "context": context,
                    "seed_effects": seed_mean, "checkpoint_means": cp_mean, "temporal": temporal,
                    "task_tradeoffs": task_tradeoffs, "checkpoint_interaction": interaction,
                    "rules": rule_summary, "rule_choices": rule_rows, "diagnostics": diagnostic,
                    "risk": risk, "e2_contrast": e2_contrast, "costs": costs}
        for name, values in datasets.items():
            save_csv(name + ".csv", values)
        save_json("extended_analysis.json", {**datasets, "e0_failure_audit": automatic["E0"]["failure_audit"]})

        queries = {}
        for name, values in datasets.items():
            qs = {"label": "검증된 E0–E2 실험 결과 · " + name,
                  "files": ["16_e0_e2_results_analysis_v1/results/20261012T065024Z_70db8b08/branch_recomputed.csv",
                            "08_followup_experiment_design_v1/protocol.json", "17_e0_e2_detailed_research_report_v1/analyze.py"],
                  "executedAt": datetime.now(timezone.utc).isoformat(), "timezone": "Asia/Seoul",
                  "evidenceFlow": [
                      {"title": "원자료 검증", "detail": "v16이 282개 정책 평가, 112,800개 에피소드의 성공률을 재계산했다. 각 평가 과제별 100개 사례, 동일 평가 bank와 저장 지표 일치를 확인했다."},
                      {"title": "현재 재집계", "detail": "완료된 E0–E2 결과 592개 해시가 v16 검증 시점과 동일하다. v17은 검증된 CSV를 사용하고, 원래 seed에 동일 가중치를 주어 checkpoint와 continuation 반복을 내부 평균했다."}],
                  "caveats": ["E1/E2 독립 사전학습 seed는 동일한 11/12/13 세 개다. E0는 사전학습 seed 901 하나다.",
                              "성공률 단위는 %, 두 성공률 차이 단위는 %p. 조건부 평가 사례 bootstrap은 사전학습 seed 불확실성을 포함하지 않는다.",
                              "20k/40k는 추가 연습량, 200k/400k는 출발 checkpoint. 탐색적 세부 패턴을 새로운 주 가설로 취급하지 않는다."],
                  "metricDefinitions": [
                      {"label": "Macro 성공률", "definition": "DO, DC, WO, WC 성공률의 동일 가중 평균. 에피소드별 성공은 0/1. 각 정책/과제당 독립 outcome bank 사례 100개를 평가한다.", "formula": "(DO_pct + DC_pct + WO_pct + WC_pct) / 4"},
                      {"label": "Uniform 대비 차이", "definition": "동일 원래 seed, 출발 checkpoint, continuation label, 추가 예산의 U와 뺄셈 후 내부 반복·checkpoint·원래 seed 순으로 평균한다.", "formula": "macro_pct - matched_U_macro_pct"},
                      {"label": "부모 대비 이득", "definition": "같은 outcome bank에서 평가한 출발 부모 정책 성공률을 뺀 값. U 대비 이득과 다르다."}]}
            if name == "rules" or name == "rule_choices":
                qs["files"] = ["16_e0_e2_results_analysis_v1/results/20261012T065024Z_70db8b08/rule_choices.csv", "17_e0_e2_detailed_research_report_v1/analyze.py"]
            if name == "baselines":
                qs["files"] = ["16_e0_e2_results_analysis_v1/results/20261012T065024Z_70db8b08/baseline_success.csv"]
            if name == "costs":
                qs["files"] = [(out / "costs.csv").relative_to(REPO).as_posix(), (out / "input_hashes.json").relative_to(REPO).as_posix()]
                qs["caveats"].append("누적 wall time은 성공한 작업 내부 시간의 합이며, queue 대기·재시도·초기 구현 검증 비용을 포함하지 않는다. 금전 비용은 계측하지 않았다. 각 원본 costs.json의 정확한 경로와 해시는 input_hashes.json에 있다.")
                qs["metricDefinitions"] = [{"label": "작업 내부 실행 시간", "definition": "각 완료 작업 costs.json.wall_seconds를 합해 3600으로 나눈 값. 달력 경과 시간과 다르다."}]
            queries[name] = {"rows": values, "source": qs,
                             "methods": [{"language": "text", "code": f"Run analyze.py in version 17; read the resulting {name}.csv. Average continuation repeats within each original seed/checkpoint, average checkpoints within each original seed where pooled, then weight original seeds equally. E0 discovery and replication cohorts remain separate. The run directory retains exact analysis_source.py, input_hashes.json and checks.json. No learner or environment is instantiated."}]}
        snapshot = {"surface": "report", "title": "E0–E2 연구 결과 상세 분석", "status": "observed", "buildStatus": "creating",
                    "generatedAt": datetime.now(timezone.utc).isoformat(), "filters": [], "queries": queries}
        save_json("reviewed_snapshot.json", snapshot)
        save_json("checks.json", {"passed": True, "checks": checks, "new_training_steps": 0, "new_evaluation_episodes": 0,
                                  "analysis_wall_seconds": time.perf_counter() - started, "python": sys.version,
                                  "dependencies": "Python standard library only", "analysis_source_sha256": sha(out / "analysis_source.py"),
                                  "randomness": "No new random sampling; original case bootstrap intervals reused with their conditional interpretation.",
                                  "scope": "Post-hoc descriptive deepening of frozen primary/secondary contrasts; not a new confirmation study."})
        save_json("input_hashes.json", hashes)
        print(json.dumps({"output": str(out), "passed": True, "costs": costs, "primary": primary}, ensure_ascii=False))
    except BaseException:
        save_json("failure.json", {"traceback": traceback.format_exc(), "elapsed_seconds": time.perf_counter() - started})
        save_json("input_hashes.json", hashes)
        raise


if __name__ == "__main__":
    main()
