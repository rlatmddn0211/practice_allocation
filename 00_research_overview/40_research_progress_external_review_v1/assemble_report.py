"""Assemble a read-only synthesis; retain unique source/evidence snapshots per run.

No learner/environment imports, persistent or clone updates, or Git writes.
This checks the synthesis against delivered aggregates; it does not repeat the
original scientific analyses or bootstrap procedures.
"""
from pathlib import Path
from datetime import datetime, timezone
import csv
import hashlib
import json
import re
import shutil
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
T0 = time.perf_counter()
NOW = datetime.now(timezone.utc).isoformat()
OUT = ROOT / "results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_assemble_" + uuid.uuid4().hex[:8])
OUT.mkdir(parents=True, exist_ok=False)
checks, inputs, queries = [], {}, {}


def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(path):
    path = path.resolve()
    rel = path.relative_to(REPO).as_posix()
    if rel not in inputs:
        target = OUT / "input_snapshot" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        inputs[rel] = {"sha256": sha(path), "bytes": path.stat().st_size}
    return rel


def check(name, passed, detail=None):
    checks.append({"name": name, "passed": bool(passed), "detail": detail})


def near(name, actual, expected, tolerance=1e-8):
    check(name, abs(float(actual)-expected) <= tolerance, {"actual": actual, "expected": expected})


def cell(value):
    if value is None or value == "":
        return None
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return value


def csv_rows(path):
    record(path)
    with path.open(encoding="utf-8-sig", newline="") as f:
        return [{k: cell(v) for k, v in row.items()} for row in csv.DictReader(f)]


def js(path):
    record(path)
    return json.loads(path.read_text(encoding="utf-8-sig"))


def locate_run(prefix, tag):
    candidates = list(REPO.glob(prefix + "/results/*" + tag + "*/run/run_summary.json"))
    if len(candidates) != 1:
        raise ValueError((prefix, tag, candidates))
    return candidates[0]


P17 = REPO / "17_e0_e2_detailed_research_report_v1/results/20261013T052346Z_7e2f6a68"
P21 = REPO / "21_e3_completed_results_analysis_v1/results/20261014T024817Z_ca372238"
P36 = REPO / "36_all_candidate_evidence_review_v1/results/20261015T104602Z_review_0d1cb1b0"
P37 = REPO / "37_f08_integrated_candidate_review_v1/results/20261019T024708Z_review_cef06973"


def query(qid, rows, paths, components, definition, caveats=None):
    queries[qid] = {
        "rows": rows,
        "source": {
            "label": qid,
            "files": [record(p) for p in paths],
            "timezone": "Asia/Seoul",
            "classification": "observed" if qid != "proposal" else "unexecuted proposal",
            "metricDefinitions": [{"label": "측정 범위와 단위", "definition": definition,
                                   "componentIds": components}],
            "evidenceFlow": [
                {"title": "보존된 근거", "detail": "이전 실행·검산 산출물의 명시된 파일을 읽고 SHA-256과 사본을 보존했다."},
                {"title": "보고서 조립", "detail": "assemble_report.py가 표·핵심 대비·비용 합계를 확인했다. 원래 학습·bootstrap을 재실행하지 않았다."}
            ],
            "caveats": caveats or ["새 학습 결과가 아닌 기존 연구 결과의 종합이다."]
        },
        "methods": [{"language": "text", "code": "Read the listed immutable CSV/JSON/report files. Preserve their stated comparison grain and units. See assemble_report.py and the unique results run for exact hashes and checks."}]
    }


status = "failed"
try:
    report_path = ROOT / "research_progress_report_ko.md"
    source_copy = OUT / "source_snapshot"
    source_copy.mkdir()
    for p in [Path(__file__), report_path]:
        shutil.copyfile(p, source_copy / p.name)
    md = report_path.read_text(encoding="utf-8")
    chunks = re.split(r"(?m)^(## \d+\. .+)$", md)
    sections = []
    for i in range(1, len(chunks), 2):
        title = chunks[i][3:]
        number = int(title.split(".")[0])
        sections.append({"id": f"section-{number:02d}", "title": title,
                         "markdown": chunks[i] + chunks[i+1]})
    check("17_complete_sections", len(sections) == 17)
    check("no_replacement_characters", "\ufffd" not in md)
    check("no_unresolved_placeholders", not re.search(r"\b(TODO|TBD|FIXME)\b", md))
    section = {int(s["id"].split("-")[-1]): s["markdown"] for s in sections}
    task_abbreviations = set(re.findall(r"\((DO|DC|WO|WC|PU|BP|PP)\)", section[3]))
    check("seven_distinct_tasks_across_compositions", len(task_abbreviations) == 7 and "총 일곱 종류" in section[3], sorted(task_abbreviations))

    p0_path = locate_run("02_p0_uniform_pretraining_v1", "p0_cuda")
    d_path = locate_run("04_p0_allocation_branches_v1", "allocation_branches_cuda")
    r_path = locate_run("06_p0_branch_replication_v1", "replication_cuda")
    p0, discovery, replication = js(p0_path), js(d_path), js(r_path)
    config_path = p0_path.parent / "resolved_config.json"
    config = js(config_path)
    runtime_path = p0_path.parent / "run_manifest.json"
    runtime = js(runtime_path)
    env_path = REPO / "02_p0_uniform_pretraining_v1/practice_allocation/environment.py"
    env_text = env_path.read_text(encoding="utf-8-sig")
    record(env_path)
    check("v3_environment_v2_reward_distinction", "ALL_V3_ENVIRONMENTS" in env_text and 'reward_function_version="v2"' in env_text and "V3 환경 클래스" in section[3])
    query("learner", [{k: config[k] for k in ["seed", "reward_function_version", "buffer_size", "batch_size", "learning_rate", "gamma", "tau", "net_arch", "normalize_rewards", "normalize_observations"]}], [config_path, runtime_path, env_path], ["section-03"], "공유 SAC 설정. 환경은 V3 클래스, 보상 함수 버전은 v2 dense다.")

    early = []
    for cohort, run in [("discovery", discovery), ("replication", replication)]:
        for candidate in ["U", "F_DO", "F_DC", "F_WO", "F_WC"]:
            branches = [b for b in run["branches"] if b["candidate"] == candidate]
            early.append({"cohort": cohort, "allocation": candidate,
                          "macro_pct": sum(b["outcomes"]["40000"]["macro_success"]*100 for b in branches)/len(branches),
                          "continuation_seeds": [b["repeat_seed"] for b in branches], "original_seed": 901})
    query("early", early, [d_path, r_path], ["section-06"], "O50/task의 최종 macro %, 발견 2개와 후속 확인 3개를 분리. 모두 동일 seed-901 부모.")
    for row in early:
        check("early_report_value_"+row["cohort"]+row["allocation"], f'{row["macro_pct"]:.2f}' in section[6])

    primary = csv_rows(P17 / "primary.csv")
    means = csv_rows(P17 / "checkpoint_means.csv")
    costs_e012 = csv_rows(P17 / "costs.csv")
    query("primary", primary, [P17 / "primary.csv"], ["section-01", "section-07"], "E0/E1은 macro %p, E2는 DO 성공률 %p. 사례 bootstrap은 학습 seed CI가 아니다.")
    query("e1_means", [r for r in means if r["horizon"] == 40000], [P17 / "checkpoint_means.csv"], ["section-07"], "원래 seed 3개, 두 출발 시점별 최종 macro % 및 Uniform 대비 %p.")
    for row, value in zip(primary, [7.916666666666667, .388888888888889, -.777777777777778]):
        near("primary_"+row["stage"], row["mean_pp"], value)
        check("primary_rendered_"+row["stage"], f'{value:+.2f}' in section[7])
    for row in queries["e1_means"]["rows"]:
        check("e1_rendered_"+str(row["checkpoint_step"])+row["allocation"], f'{row["macro_pct"]:.2f}' in section[7])

    e3 = [r for r in csv_rows(P21 / "allocation_summary.csv") if r["horizon"] == 40000]
    query("e3", e3, [P21 / "allocation_summary.csv", P21 / "original_seed_effects.csv", P21 / "rule_summary.csv"], ["section-01", "section-08"], "B/C 각각 원래 seed 3개와 후속 seed 3개. 최종 macro %, 부모·Uniform 대비 차이는 %p.")
    for row in e3:
        for key in ["macro_pct", "macro_gain_pp", "macro_vs_U_pp"]:
            check("e3_rendered_"+row["suite"]+row["allocation"]+key, f'{row[key]:.2f}' in section[8])
    near("e3_B_BP_gain", next(r for r in e3 if r["suite"] == "B" and r["allocation"] == "F_BP")["macro_vs_U_pp"], 5.861111111111111)

    comparisons = csv_rows(P36 / "comparisons.csv")
    f07 = csv_rows(P37 / "prior_F07_reference_rules.csv")
    query("factors", comparisons, [P36 / "comparisons.csv", P36 / "common_baseline_review.csv"], ["section-10"], "추가 선택 이득 %p. 후보마다 다른 기준과의 차이이며 후보 간 순위가 아니다. 원래 seed를 제외해 평가한 개발 자료.")
    query("reliability", f07, [P37 / "prior_F07_reference_rules.csv"], ["section-10"], "F07의 조건부 재표집. 평가 사례 수·비교 기준을 구분한다.")
    factor_expect = {"F01": [-.074074074074, -.148148148148], "F02": [0, -.425925925926], "F03": [-.361111111111, .481481481481], "F04": [.064814814815, .111111111111], "F05_critic": [0, 0], "F05_alignment": [-.296296296296, -.351851851852], "F06": [.074074074074, .703703703704]}
    for factor, values in factor_expect.items():
        for mode, value in zip(["same_repeat", "cross_repeat"], values):
            row = next(r for r in comparisons if r["factor"] == factor and r["mode"] == mode)
            near("factor_"+factor+mode, row["increment_pp"], value)
            check("factor_rendered_"+factor+mode, f'{value:+.3f}'.replace("+0.000", "0.000") in section[10])

    f08 = csv_rows(P37 / "condition_means.csv")
    contrasts = csv_rows(P37 / "contrast_review.csv")
    f08costs = csv_rows(P37 / "F08_cost_summary.csv")
    query("f08", f08, [P37 / "condition_means.csv", P37 / "parent_scores.csv", P37 / "branch_scores.csv"], ["section-01", "section-11"], "원래 seed 12 하나/구성, 후속 3801/3802/3803. 최종 macro 성공률 %, 표기 mean_macro_pp는 수준값이다.")
    query("f08_contrasts", contrasts, [P37 / "contrast_review.csv", P37 / "contrast_task_means.csv"], ["section-11"], "스케줄 간 차이 %p. 21개 개발 대조; 사례 구간은 원래 seed 불확실성 제외.")
    for row in f08:
        check("f08_rendered_"+row["suite"]+row["condition"], f'{row["mean_macro_pp"]:.2f}' in section[11])
    b_alt = next(r for r in f08 if r["suite"] == "B" and r["condition"] == "alternate4k")
    b_mix = next(r for r in f08 if r["suite"] == "B" and r["condition"] == "mixture")
    b_focus = next(r for r in f08 if r["suite"] == "B" and r["condition"] == "dose625")
    near("B_alternate_minus_mixture", b_alt["mean_macro_pp"]-b_mix["mean_macro_pp"], 5.833333333333333)
    near("B_fixed_focus_minus_alternate", b_focus["mean_macro_pp"]-b_alt["mean_macro_pp"], 3.416666666666667)

    e3costs = csv_rows(P21 / "completed_job_costs.csv")
    ledger = []
    for label, run, training in [("P0", p0, 400000), ("Discovery", discovery, 400000), ("Replication", replication, 600000)]:
        total = run["costs"]["environment_steps"]
        ledger.append({"stage": label, "training_steps": training, "evaluation_diagnostic_steps": total-training, "environment_steps": total})
    for r in costs_e012:
        ledger.append({"stage": r["stage"], "training_steps": r["training_steps"], "evaluation_diagnostic_steps": r["all_environment_steps"]-r["training_steps"], "environment_steps": r["all_environment_steps"]})
    e3total = sum(r["environment_steps"] for r in e3costs)
    ledger.append({"stage": "E3", "training_steps": 4800000, "evaluation_diagnostic_steps": e3total-4800000, "environment_steps": e3total})
    f05_summary_path = REPO / "31_fixed_horizon_alignment_v1/results/20261015T100729Z_analysis_5fa7ae88/summary.json"
    f05_steps = js(f05_summary_path)["diagnostics"]["new_diagnostic_environment_steps"]
    ledger.append({"stage": "F05_alignment", "training_steps": 0, "evaluation_diagnostic_steps": f05_steps, "environment_steps": f05_steps})
    f08total = sum(r["environment_steps"] for r in f08costs)
    f08train = sum(r["train_iterations"] for r in f08costs)
    ledger.append({"stage": "F08", "training_steps": f08train, "evaluation_diagnostic_steps": f08total-f08train, "environment_steps": f08total})
    totals = {k: sum(r[k] for r in ledger) for k in ["training_steps", "evaluation_diagnostic_steps", "environment_steps"]}
    for key, expected in zip(totals, [14960000, 78276809, 93236809]):
        near("cost_total_"+key, totals[key], expected, 0)
        check("cost_total_rendered_"+key, f"{expected:,}" in section[12])
    for row in ledger:
        for key in ["training_steps", "evaluation_diagnostic_steps", "environment_steps"]:
            check("cost_rendered_"+row["stage"]+key, f'{row[key]:,}' in section[12])
    dump(OUT / "completed_cost_ledger.json", {"rows": ledger, "totals": totals, "excludes": "technical checks, smoke, interrupted attempts, analysis CPU, clone updates, reporting"})
    costpaths = [p0_path, d_path, r_path, P17 / "costs.csv", P21 / "completed_job_costs.csv", P37 / "F08_cost_summary.csv", f05_summary_path, REPO / "37_f08_integrated_candidate_review_v1/report_ko.md"]
    query("costs", ledger, costpaths, ["section-12"], "완료된 주요 본 실행만 합산한 실제 환경 step. smoke·중단 시도·분석은 제외. GPU 시간이나 총 금전 비용이 아니다.")

    doc_map = {
        "p0": ["03_p0_pretraining_analysis_v1/README.md"],
        "history": ["LOCAL_PRACTICE_ALLOCATION_PILOT_DESIGN_20261007.md", "08_followup_experiment_design_v1/README.md", "22_candidate_factor_grounding_v1/research_development_ko.md"],
        "forecast": ["19_budgeted_practice_research_feasibility_v1/research_plan_ko.md"],
        "literature": ["18_practice_allocation_literature_review_v1/README.md", "22_candidate_factor_grounding_v1/research_development_ko.md"],
        "candidate_context": ["23_candidate_factor_screening_design_v1/README.md", "36_all_candidate_evidence_review_v1/report_ko.md", "37_f08_integrated_candidate_review_v1/factor_status_ko.md"],
        "recovery": ["14_power_interruption_audit_v1/results/20261012T052748Z_4be8fe6c/audit.json", "15_verified_power_loss_recovery_v1/results/20261012T055235Z_verify_ced11a81/verification.json"],
        "proposal": ["39_next_research_decision_plan_v1/research_plan_ko.md", "39_next_research_decision_plan_v1/proposal.json"],
        "provenance": ["38_candidate_factor_publication_v1/README.md", "05_results_github_archive_v1/README.md", "20_e0_e2_github_publication_v1/README.md"]
    }
    components_map = {"p0": ["section-05"], "history": ["section-02", "section-04"], "forecast": ["section-09"], "literature": ["section-13"], "candidate_context": ["section-10"], "recovery": ["section-12"], "proposal": ["section-15"], "provenance": ["section-17"]}
    for key, filenames in doc_map.items():
        paths = [REPO / p for p in filenames]
        rows = [{"document": p.relative_to(REPO).as_posix(), "sha256": sha(p), "type": "proposal" if key == "proposal" else "delivered_record"} for p in paths]
        query(key, rows, paths, components_map[key], "문서 근거와 범위. 제안은 실행 결과가 아니다; 경로·hash로 출처를 확인한다.")
    web_sources = js(ROOT / "external_sources.json")
    query("external_review", web_sources, [ROOT / "external_sources.json"], ["section-13", "section-14"], "사용자 제공 외부 평가와 공식 문헌 초록 확인. 원시 실험의 독립 재현 아님.")

    section_queries = {
        1: ["primary", "e3", "f08"], 2: ["history"], 3: ["learner"],
        4: ["history", "costs"], 5: ["p0"], 6: ["early"],
        7: ["primary", "e1_means"], 8: ["e3"], 9: ["forecast"],
        10: ["factors", "reliability", "candidate_context"],
        11: ["f08", "f08_contrasts"], 12: ["costs", "recovery"],
        13: ["literature", "external_review"], 14: ["external_review"],
        15: ["proposal"], 16: [], 17: ["provenance"]
    }
    # Correct definitions to exactly match authored consumers, including summary sections.
    for qid, q in queries.items():
        consumers = [f"section-{n:02d}" for n, ids in section_queries.items() if qid in ids]
        for definition in q["source"]["metricDefinitions"]:
            definition["componentIds"] = consumers
    for s in sections:
        s["queryIds"] = section_queries[int(s["id"].split("-")[-1])]
    snapshot = {
        "surface": "report", "title": "추가 연습 배분 연구: 지금까지 확인한 것과 아직 입증하지 못한 것",
        "status": "observed", "buildStatus": "complete", "generatedAt": NOW,
        "filters": [], "queries": queries,
        "report": {"asOf": "2026-10-19", "experimentalEvidenceThrough": "2026-10-16", "sections": sections,
                   "introduction": chunks[0].split("\n", 1)[1].strip()},
        "sourceManifest": inputs,
        "scope": {"new_environment_steps": 0, "persistent_updates": 0, "clone_updates": 0,
                  "new_experiments_authorized": False, "publication_requested": False,
                  "scientific_analyses_rerun": False}
    }
    check("all_queries_declared", all(q in queries for s in sections for q in s["queryIds"]))
    check("all_source_paths_exist", all((REPO / p).is_file() for p in inputs))
    check("proposal_explicitly_unexecuted", "실행·예약하지 않았고" in section[15])
    check("external_review_not_replication", "독립 재실행한 검증" in section[14])
    check("not_all_factors_ineffective", "요인들이 모두 무효" in section[10])
    check("C_absolute_losses_retained", "19개가 부모보다 낮고" in section[11])
    check("strong_fixed_baseline_retained", "3.42%p 높다" in section[11])
    check("source_scopes_exact", all(d["componentIds"] == [s["id"] for s in sections if qid in s["queryIds"]] for qid, q in queries.items() for d in q["source"]["metricDefinitions"]))
    dump(OUT / "reviewed_snapshot.json", snapshot)
    dump(ROOT / "reviewed_snapshot.json", snapshot)
    status = "passed" if all(c["passed"] for c in checks) else "failed"
except Exception as exc:
    checks.append({"name": "assembly_exception", "passed": False, "detail": repr(exc)})
finally:
    dump(OUT / "checks.json", checks)
    dump(OUT / "input_hashes.json", inputs)
    summary = {"status": status, "checks": len(checks), "failed": [c for c in checks if not c["passed"]],
               "started_at": NOW, "wall_seconds": time.perf_counter()-T0, "python": sys.version,
               "source_sha256": sha(Path(__file__)), "report_sha256": sha(ROOT / "research_progress_report_ko.md"),
               "report_characters": len((ROOT / "research_progress_report_ko.md").read_text(encoding="utf-8")),
               "new_environment_steps": 0, "persistent_updates": 0, "clone_updates": 0}
    dump(OUT / "summary.json", summary)
    print(json.dumps({"output": str(OUT), **summary}, ensure_ascii=False))
    if status != "passed":
        sys.exit(1)
