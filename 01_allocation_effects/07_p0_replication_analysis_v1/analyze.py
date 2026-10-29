"""Read-only replication audit and descriptive analysis; never trains a policy."""
from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import math
import platform
import shutil
import subprocess
import sys
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
TASKS = ("DO", "DC", "WO", "WC")
CANDIDATES = ("U", "F_DO", "F_DC", "F_WO", "F_WC")
QUOTAS = dict(zip(CANDIDATES, ((2, 2, 2, 2), (5, 1, 1, 1), (1, 5, 1, 1), (1, 1, 5, 1), (1, 1, 1, 5))))
LABELS = dict(zip(CANDIDATES, ("균등", "서랍열기 집중", "서랍닫기 집중", "창문열기 집중", "창문닫기 집중")))
COHORTS = {
    "replication": (1903, 1904, 1905),
    "discovery": (1901, 1902),
    "combined_descriptive": (1901, 1902, 1903, 1904, 1905),
}
RUNS = {
    "replication": REPO / "06_p0_branch_replication_v1/results/20261008T030554Z_branch_replication_cuda_2c28c437/run",
    "discovery": REPO / "04_p0_allocation_branches_v1/results/20261007T091127Z_allocation_branches_cuda_64ec1ea7/run",
}
CHECKS, INPUTS = [], {}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def remember(path):
    INPUTS[Path(path).relative_to(REPO).as_posix()] = sha(path)


def js(path):
    remember(path)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def rows(path):
    remember(path)
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def check(name, condition):
    CHECKS.append({"name": name, "passed": bool(condition)})
    if not condition:
        raise AssertionError(name)


def near(a, b):
    return math.isclose(float(a), float(b), abs_tol=1e-8, rel_tol=0)


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def write_csv(path, values):
    with Path(path).open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(values[0]))
        writer.writeheader()
        writer.writerows(values)


def audit_run(cohort, full_checkpoint_audit):
    run = RUNS[cohort]
    version = run.parents[2]
    seeds = COHORTS[cohort]
    summary, manifest = js(run / "run_summary.json"), js(run / "run_manifest.json")
    receipt = js(run / "parent_provenance.json")
    plan = js(run / "execution_plan.json")
    label = cohort + ":"
    count = len(seeds) * 5
    check(label + "complete_authorized_plan", summary["status"] == "completed" and summary["error"] is None
          and summary["branches_completed"] == summary["branches_planned"] == count
          and tuple(summary["continuation_seeds"]) == seeds and summary["original_seed"] == 901
          and summary["parent_step"] == 200000 and tuple(plan["candidates"]) == CANDIDATES
          and plan["steps_per_branch"] == 40000 and plan["evaluation_steps"] == [20000, 40000])
    for name, expected in manifest["source_hashes"].items():
        check(label + "source:" + name, sha(version / name) == expected
              and sha(run / "source_snapshot" / name) == expected)
    for name, expected in receipt["pinned_inputs"].items():
        check(label + "parent_input:" + name, sha(Path(receipt["parent_run"]) / name) == expected)
    for name, expected in receipt["checkpoint_files"].items():
        check(label + "parent_checkpoint:" + name, sha(Path(receipt["checkpoint"]) / name) == expected)
    config = js(run / "resolved_config.json")
    check(label + "dense_reward_contract", config["reward_function_version"] == "v2" and not config["normalize_rewards"])
    if full_checkpoint_audit:
        checkpoints = [run / "initial_checkpoint", *sorted((run / "branches").glob("*/checkpoints/*"))]
        check(label + "checkpoint_count", len(checkpoints) == 31)
        for directory in checkpoints:
            cm = js(directory / "checkpoint_manifest.json")
            restore = js(directory / "restore_verification.json")
            check(label + "restore:" + directory.relative_to(run).as_posix(), restore["restored_state_matches"]
                  and cm["source_hashes"] == manifest["source_hashes"])
            check(label + "checkpoint_step:" + directory.relative_to(run).as_posix(),
                  cm["step"] in (200000, 220000, 240000) and cm["updates"] == cm["step"] - 1000
                  and cm["replay_size"] == 100000)
            for name, expected in cm["files"].items():
                path = directory / name
                remember(path)
                check(label + "checkpoint_bytes:" + path.relative_to(run).as_posix(), INPUTS[path.relative_to(REPO).as_posix()] == expected)
    raw = rows(run / "evaluation_episodes.csv")
    groups = defaultdict(list)
    for row in raw:
        groups[row["evaluation_id"]].append(row)
    banks = js(run / "evaluation_banks.json")
    expected = {(r["task"], str(r["episode_index"]), str(r["seed"]), r["initial_state_hash"]) for r in banks["outcome"]}
    check(label + "evaluation_grain", len(raw) == (1 + count * 2) * 200 and len(groups) == 1 + count * 2
          and len(expected) == 200 and len({r["initial_state_hash"] for r in raw}) == 200)
    rates = {}
    for name, group in groups.items():
        check(label + "evaluation_cases:" + name, len(group) == 200
              and Counter(r["task"] for r in group) == Counter({t: 50 for t in TASKS})
              and {(r["task"], r["episode_index"], r["seed"], r["initial_state_hash"]) for r in group} == expected
              and all(r["bank"] == "outcome" and r["success"] in ("0", "1") and 1 <= int(r["length"]) <= 500
                      and math.isfinite(float(r["return"])) for r in group))
        rates[name] = {t: sum(int(r["success"]) for r in group if r["task"] == t) / 50 for t in TASKS}
    baseline = js(run / "baseline/evaluation.json")
    check(label + "baseline", rates["baseline"] == baseline["success_by_task"] == {"DO": .06, "DC": 1., "WO": .04, "WC": .84})
    exposure, fingerprints, training = [], [], []
    for seed in seeds:
        for candidate in CANDIDATES:
            branch_id = f"repeat_{seed}_{candidate}"
            directory = run / "branches" / branch_id
            b, start = js(directory / "branch_summary.json"), js(directory / "branch_started.json")
            check(label + "start:" + branch_id, start["before_fingerprints"] == receipt["parent_state_fingerprints"]
                  and start["before_fingerprints"]["learning"] == start["after_fingerprints"]["learning"]
                  and start["learned_state_and_replay_history_preserved"])
            check(label + "budget:" + branch_id, b["status"] == "completed"
                  and b["additional_training_steps"] == b["additional_sac_iterations"] == 40000)
            episodes = rows(directory / "train_episodes.csv")
            training.extend(episodes)
            check(label + "episodes:" + branch_id, len(episodes) == 80 and all(int(r["length"]) == 500 for r in episodes))
            for block in range(10):
                n = Counter(r["task"] for r in episodes[block * 8:(block + 1) * 8])
                check(f"{label}quota:{branch_id}:{block}", [n[t] for t in TASKS] == list(QUOTAS[candidate]))
            check(label + "collection:" + branch_id, b["collected_new_by_task"] == {t: q * 5000 for t, q in zip(TASKS, QUOTAS[candidate])})
            check(label + "sampling:" + branch_id, sum(b["sampled_during_branch_by_task"].values()) == 40000 * 256
                  and near(b["new_experience_fraction_in_final_replay"], .4))
            reset = js(directory / "training_reset_audit.json")
            check(label + "reset:" + branch_id, reset["passed"] and reset["common_reset_cases_match"]
                  and reset["no_evaluation_states_used_for_training"]
                  and (cohort != "replication" or reset["no_discovery_states_reused"]))
            for horizon in (20000, 40000):
                outcome = b["outcomes"][str(horizon)]
                check(f"{label}outcome:{branch_id}:{horizon}", rates[outcome["evaluation_id"]] == outcome["success_by_task"] and outcome["state_unchanged"])
            fingerprints.append(b["final_state_fingerprints"]["learning"])
            total_sampled = sum(b["sampled_during_branch_by_task"].values())
            exposure.append({"cohort": cohort, "seed": seed, "candidate": candidate,
                             "new_sample_pct": b["sampled_new_experience_fraction"] * 100,
                             **{t + "_batch_pct": b["sampled_during_branch_by_task"][t] / total_sampled * 100 for t in TASKS}})
    check(label + "distinct_final_models", len(set(fingerprints)) == count)
    check(label + "total_training", sum(int(r["length"]) for r in training) == count * 40000 == summary["additional_training_steps"])
    ledger = rows(run / "cost_ledger.csv")
    for key, value in summary["costs"].items():
        check(label + "cost:" + key, sum(int(r[key]) for r in ledger) == value)
    check(label + "evaluation_cost", sum(int(r["length"]) for r in raw) == summary["evaluation_transitions"])
    check(label + "total_cost", summary["costs"]["environment_steps"] == count * 40000 + summary["evaluation_transitions"])
    comparison = rows(run / "allocation_comparison.csv")
    check(label + "comparison_count", len(comparison) == count * 2)
    calculated = []
    for row in comparison:
        seed, candidate, horizon = int(row["repeat_seed"]), row["candidate"], int(row["additional_steps"])
        values = rates[f"repeat_{seed}_{candidate}_h{horizon:06d}"]
        uniform = rates[f"repeat_{seed}_U_h{horizon:06d}"]
        macro = mean(values.values()) * 100
        delta = macro - mean(uniform.values()) * 100
        drop = max(0., max((rates["baseline"][t] - values[t]) * 100 for t in TASKS))
        check(f"{label}comparison:{seed}:{candidate}:{horizon}", near(row["macro_success"], macro / 100)
              and near(row["gain_pp"], macro - 48.5) and near(row["extra_gain_vs_uniform_pp"], delta)
              and near(row["max_drop_pp"], drop) and all(near(row["success_" + t], values[t]) for t in TASKS))
        calculated.append({"cohort": cohort, "seed": seed, "candidate": candidate, "allocation": LABELS[candidate],
                           "horizon": horizon, "macro_pct": round(macro, 10), "gain_pp": round(macro - 48.5, 10),
                           "delta_pp": round(delta, 10), "max_drop_pp": round(drop, 10),
                           **{t: round(values[t] * 100, 10) for t in TASKS}})
    selection = js(run / "frozen_selection_rules.json")
    parent_selection = js(Path(receipt["parent_run"]) / "selected_checkpoint.json")
    check(label + "frozen_selector", selection == parent_selection and not selection["outcome_scores_used"])
    return {"summary": summary, "raw": raw, "groups": groups, "rates": rates, "calculated": calculated,
            "exposure": exposure, "manifest": manifest, "config": config, "banks": banks}


def analyze(out):
    runs = {c: audit_run(c, c == "replication") for c in ("replication", "discovery")}
    check("same_evaluation_bank", runs["replication"]["banks"] == runs["discovery"]["banks"])
    def functional(group):
        return sorted(tuple(r[k] for k in ("task", "seed", "episode_index", "initial_state_hash", "success", "return", "length")) for r in group)
    check("same_200_baseline_results", functional(runs["replication"]["groups"]["baseline"]) == functional(runs["discovery"]["groups"]["baseline"]))
    cfgs = [{k: v for k, v in r["config"].items() if k != "version"} for r in runs.values()]
    check("same_learner_configuration", cfgs[0] == cfgs[1])
    check("same_packages", runs["replication"]["manifest"]["packages"] == runs["discovery"]["manifest"]["packages"])
    spec = js(RUNS["replication"] / "frozen_replication_analysis_plan.json")
    for name, expected in spec["file_hashes"].items():
        check("frozen_discovery_input:" + name, sha(RUNS["discovery"] / name) == expected)
    records = runs["replication"]["calculated"] + runs["discovery"]["calculated"]
    index = {(r["seed"], r["candidate"], r["horizon"]): r for r in records}
    summaries, breakdown, by_horizon = [], [], []
    for cohort, seeds in COHORTS.items():
        for candidate in CANDIDATES:
            group = [index[s, candidate, 40000] for s in seeds]
            deltas = [r["delta_pp"] for r in group]
            summaries.append({"cohort": cohort, "candidate": candidate, "allocation": LABELS[candidate], "n": len(seeds),
                              "macro_pct": mean(r["macro_pct"] for r in group), "gain_pp": mean(r["gain_pp"] for r in group),
                              "delta_pp": mean(deltas), "min_delta_pp": min(deltas), "max_delta_pp": max(deltas),
                              "wins": sum(x > 0 for x in deltas), "ties": sum(x == 0 for x in deltas), "losses": sum(x < 0 for x in deltas),
                              **{t: mean(r[t] for r in group) for t in TASKS}})
            for task in TASKS:
                effect = mean(index[s, candidate, 40000][task] - index[s, "U", 40000][task] for s in seeds)
                breakdown.append({"cohort": cohort, "candidate": candidate, "allocation": LABELS[candidate], "task": task,
                                  "task_difference_pp": effect, "macro_contribution_pp": effect / 4})
            for horizon in (20000, 40000):
                g = [index[s, candidate, horizon] for s in seeds]
                by_horizon.append({"cohort": cohort, "candidate": candidate, "allocation": LABELS[candidate], "horizon": horizon,
                                   "macro_pct": mean(r["macro_pct"] for r in g), "gain_pp": mean(r["gain_pp"] for r in g),
                                   "delta_pp": mean(r["delta_pp"] for r in g)})
    published = rows(RUNS["replication"] / "cohort_summary.csv")
    check("cohort_table_complete", len(published) == len(summaries) == 15)
    for expected, actual in zip(published, summaries):
        check("cohort_recalculation:" + actual["cohort"] + ":" + actual["candidate"],
              expected["cohort"] == actual["cohort"] and expected["candidate"] == actual["candidate"]
              and near(expected["mean_macro_success"], actual["macro_pct"] / 100)
              and near(expected["mean_extra_gain_vs_uniform_pp"], actual["delta_pp"])
              and int(expected["positive_repeats"]) == actual["wins"])
    secondary, paired = [], []
    for cohort in ("replication", "discovery"):
        for seed in COHORTS[cohort]:
            a, b = index[seed, "F_DC", 40000], index[seed, "F_DO", 40000]
            mid = index[seed, "F_DO", 20000]
            secondary.append({"cohort": cohort, "seed": seed, "DO_F_DC": a["DO"], "DO_F_DO": b["DO"],
                              "DO_difference_pp": a["DO"] - b["DO"], "DO_direction_repeated": a["DO"] > b["DO"],
                              "WC_baseline": 84., "WC_20k": mid["WC"], "WC_40k": b["WC"],
                              "WC_dip_recovery": mid["WC"] < 84 and b["WC"] >= 84})
            for task in TASKS:
                get = lambda candidate: {r["initial_state_hash"]: int(r["success"]) for r in runs[cohort]["groups"][f"repeat_{seed}_{candidate}_h040000"] if r["task"] == task}
                left, right = get("F_DC"), get("F_DO")
                wins = sum(left[k] == 1 and right[k] == 0 for k in left)
                losses = sum(left[k] == 0 and right[k] == 1 for k in left)
                paired.append({"cohort": cohort, "seed": seed, "task": task, "F_DC_only_success": wins,
                               "F_DO_only_success": losses, "same_outcome": 50 - wins - losses, "difference_pp": 2 * (wins - losses)})
    saved_secondary = rows(RUNS["replication"] / "prespecified_secondary_contrasts.csv")
    check("secondary_table_complete", len(saved_secondary) == len(secondary) == 5)
    for expected, actual in zip(saved_secondary, secondary):
        check("secondary_recalculation:" + str(actual["seed"]), int(expected["repeat_seed"]) == actual["seed"]
              and near(expected["do_f_dc_minus_f_do_pp"], actual["DO_difference_pp"])
              and (expected["wc_dip_then_return_to_baseline"] == "True") == actual["WC_dip_recovery"])
    # All seeds are retained. This diagnostic shows how a mean depends on each seed; it does not select runs.
    sensitivity = [{"candidate": c, "omitted_seed_for_diagnostic": s,
                    "remaining_mean_delta_pp": mean(index[q, c, 40000]["delta_pp"] for q in COHORTS["replication"] if q != s)}
                   for c in CANDIDATES[1:] for s in COHORTS["replication"]]
    for name, values in (("branch_results", records), ("cohort_results", summaries), ("task_contributions", breakdown),
                         ("budget_comparison", by_horizon), ("secondary_contrasts", secondary), ("paired_cases", paired),
                         ("mean_sensitivity", sensitivity), ("replay_exposure", runs["replication"]["exposure"] + runs["discovery"]["exposure"])):
        write_csv(out / (name + ".csv"), values)
    findings = {
        "completion": {k: v for k, v in runs["replication"]["summary"].items() if k not in ("branches", "baseline")},
        "primary_cohorts": summaries, "secondary": secondary, "budget_comparison": by_horizon,
        "task_contributions": breakdown, "sensitivity_exploratory": sensitivity,
        "limits": ["One original pretrained seed 901 at one 200k checkpoint.",
                   "Three new continuation seeds; original two discovery seeds remain separate.",
                   "50 fixed cases per task reused across all evaluations; 6200 episodes are not 6200 independent cases.",
                   "Observed ranges are not confidence intervals; no automatic significance test.",
                   "Allocation changes both focused practice and other practice; it does not isolate direct transfer.",
                   "Three evaluation horizons cannot establish complete learning curves or future recovery.",
                   "One fixed start cannot establish a state-aware selector or the need for extra information."],
        "scientific_scope": "Descriptive replication, prespecified 40k endpoint and two secondary contrasts; decomposition and leave-one-seed-out means are exploratory.",
    }
    write_json(out / "findings.json", findings)
    build_snapshot(out, records, summaries, secondary, breakdown, by_horizon, findings)
    plots(out, records, secondary)
    for name, expected in INPUTS.items():
        check("input_unchanged:" + name, sha(REPO / name) == expected)
    return findings


def build_snapshot(out, records, summaries, secondary, breakdown, by_horizon, findings):
    completion = findings["completion"]["completed_at"]
    github = "https://github.com/rlatmddn0211/practice_allocation/blob/main/"
    files = [str((RUNS[c] / "evaluation_episodes.csv").relative_to(REPO)).replace("\\", "/") for c in ("replication", "discovery")]
    source = {"label": "동결된 SAC 분기 실험의 episode별 평가 원자료", "files": files,
              "links": [{"label": "새 3 seed 평가 원자료", "url": github + files[0]}, {"label": "기존 2 seed 평가 원자료", "url": github + files[1]}],
              "executedAt": completion, "timeZone": "Asia/Seoul",
              "evidenceFlow": [{"title": "원자료", "detail": "06의 평가 6200행과 04의 평가 4200행을 읽음. 각각 고유 초기 상태 200개를 재사용."},
                               {"title": "독립 재계산", "detail": "analyze.py에서 공식 success를 과제당 50회로 나눈 뒤 네 과제를 동일 가중 평균. 같은 후속 seed의 U와 짝지어 차이를 계산."},
                               {"title": "검증", "detail": "학습 비용, 배분 quota, 결과 집계, 동결 소스, 전체 체크포인트 31개의 파일 hash 및 저장된 복원 검사를 대조. 추가 학습·평가 없음."}],
              "caveats": findings["limits"],
              "metricDefinitions": [{"label": "평균 성공률", "definition": "네 과제 성공률의 동일 가중 평균(%). 과제별 성공률은 성공 episode 수 / 50.",
                                     "formula": "100 * mean(success_DO, success_DC, success_WO, success_WC)"},
                                    {"label": "균등 대비 차이", "definition": "같은 후속 seed와 예산에서 해당 배분의 평균 성공률 − U 평균 성공률(%p)."},
                                    {"label": "시작점 대비 개선", "definition": "평균 성공률 − 공통 출발점 48.5%(%p)."}]}
    datasets = {"branches": records, "cohorts": summaries, "secondary": secondary, "contributions": breakdown, "budgets": by_horizon}
    snapshot = {"surface": "report", "title": "실패율 기준 배분은 불안정했고, 다른 배분의 이득은 반복됐습니다",
                "generatedAt": datetime.now(timezone.utc).isoformat(), "status": "reviewed", "buildStatus": "creating", "filters": [],
                "report": {"title": "실패율 기준 배분은 불안정했고, 다른 배분의 이득은 반복됐습니다", "asOf": completion[:10]},
                "queries": {name: {"rows": values, "source": source,
                                    "methods": [{"language": "text", "code": "python 07_p0_replication_analysis_v1/analyze.py; 새 출력 폴더를 생성하며 전체 원자료 hash와 계산 산출물을 보존."}]}
                            for name, values in datasets.items()}}
    snapshot["queries"]["secondary"]["source"] = {**source, "metricDefinitions": [
        {"label": "서랍열기 대비", "definition": "추가 40k에서 F_DC의 서랍열기 성공률 − F_DO의 서랍열기 성공률(%p)."},
        {"label": "창문닫기 하락·회복", "definition": "F_DO의 창문닫기가 20k에서 시작점 84%보다 낮고, 40k에서 84% 이상이면 재현. 세 시점 모두 표시."}]}
    snapshot["queries"]["contributions"]["source"] = {**source, "metricDefinitions": [
        {"label": "과제별 차이", "definition": "같은 seed와 40k에서 배분별 과제 성공률 − 균등 배분의 해당 과제 성공률을 cohort 내 평균(%p)."},
        {"label": "평균 성공률 기여", "definition": "과제별 차이 / 4. 네 과제 기여를 더하면 전체 평균 성공률 차이와 일치. 산술 분해이며 원인 규명은 아님."}]}
    write_json(out / "reviewed_snapshot.json", snapshot)


def plots(out, records, secondary):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False, "svg.fonttype": "none"})
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.8), layout="constrained")
    colors = ["#285f94", "#b26b22", "#67753b"]
    for i, seed in enumerate(COHORTS["replication"]):
        group = [next(r for r in records if r["seed"] == seed and r["candidate"] == c and r["horizon"] == 40000) for c in CANDIDATES[1:]]
        x = np.arange(4) + (i - 1) * .22
        ax[0].bar(x, [r["delta_pp"] for r in group], width=.2, label=str(seed), color=colors[i])
    ax[0].axhline(0, color="#333333", linewidth=.9)
    ax[0].set_xticks(range(4), CANDIDATES[1:])
    ax[0].set_ylabel("Macro success minus same-seed U (pp)")
    ax[0].set_title("New repeats: 40k allocation effect")
    ax[0].legend(title="Continuation seed", ncols=3, fontsize=9)
    ax[0].set_ylim(-10, 20)
    for i, row in enumerate(sorted(secondary, key=lambda r: r["seed"])):
        color = "#9aa4af" if row["cohort"] == "discovery" else "#285f94"
        ax[1].plot([row["DO_F_DO"], row["DO_F_DC"]], [i, i], color=color, linewidth=2)
        ax[1].scatter(row["DO_F_DO"], i, facecolors="white", edgecolors=color, s=60, zorder=3)
        ax[1].scatter(row["DO_F_DC"], i, color=color, marker="s", s=45, zorder=3)
        ax[1].text(max(row["DO_F_DO"], row["DO_F_DC"]) + 1, i, f'+{row["DO_difference_pp"]:.0f} pp', va="center", fontsize=9)
    ax[1].set_yticks(range(5), ["1901 (discovery)", "1902 (discovery)", "1903 (new)", "1904 (new)", "1905 (new)"])
    ax[1].set_xlim(0, 45)
    ax[1].set_xlabel("Drawer-open success (%)")
    ax[1].set_title("Open circles: F_DO / Filled squares: F_DC")
    fig.suptitle("Same original seed 901, 200k start | 50 fixed cases per task | Descriptive, no confidence intervals", fontsize=11)
    fig.savefig(out / "replication_evidence.png", dpi=180)
    fig.savefig(out / "replication_evidence.svg")
    plt.close(fig)


if __name__ == "__main__":
    started = time.perf_counter()
    out = HERE / "results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_analysis_" + uuid.uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    snapshot_dir = out / "source_snapshot"
    snapshot_dir.mkdir()
    shutil.copy2(__file__, snapshot_dir / "analyze.py")
    record = {"started_at": datetime.now(timezone.utc).isoformat(), "status": "running",
              "source_sha256": sha(Path(__file__)), "git_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
              "python": sys.version, "platform": platform.platform(),
              "packages": {p: importlib.metadata.version(p) for p in ("matplotlib", "numpy")},
              "configuration": {"original_seed": 901, "parent_step": 200000, "cohorts": COHORTS, "primary_horizon": 40000},
              "additional_training_steps": 0, "additional_policy_evaluation_episodes": 0}
    try:
        findings = analyze(out)
        check("analysis_source_unchanged", sha(Path(__file__)) == record["source_sha256"] == sha(snapshot_dir / "analyze.py"))
        record["status"] = "passed"
    except BaseException as error:
        record["status"] = "failed"
        record["error"] = repr(error)
        raise
    finally:
        record.update({"completed_at": datetime.now(timezone.utc).isoformat(), "elapsed_seconds": time.perf_counter() - started,
                       "checks": CHECKS, "checks_passed": sum(c["passed"] for c in CHECKS), "input_hashes": INPUTS})
        write_json(out / "verification.json", record)
        print(json.dumps({"status": record["status"], "checks_passed": record["checks_passed"], "output": str(out),
                          "seconds": record["elapsed_seconds"]}, ensure_ascii=False))
