"""Read-only P0 log audit and reproducible scientific figures; no RL execution."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import shutil
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from statistics import NormalDist
from uuid import uuid4

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.lines import Line2D
from scipy.stats import binomtest

ROOT = Path(__file__).resolve().parent
TASKS = ("DO", "DC", "WO", "WC")
NAMES = {"DO": "서랍 열기", "DC": "서랍 닫기", "WO": "창문 열기", "WC": "창문 닫기"}
COLORS = {"DO": "#a65430", "DC": "#326b9e", "WO": "#ac7f15", "WC": "#6a7742"}
CHECKPOINTS = (0, 100000, 200000, 400000)
DEFAULT_RUN = ROOT.parent / "02_p0_uniform_pretraining_v1/results/20261007T060310Z_p0_cuda_50621c50/run"
METRICS = ("actor_loss", "critic_loss", "entropy_loss", "entropy_coefficient",
           "critic_0_abs_td_error", "critic_1_abs_td_error")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False,
                  default=lambda x: x.item() if isinstance(x, np.generic) else str(x))
        handle.write("\n")


def csv_output(path, frame):
    with path.open("x", encoding="utf-8-sig", newline="") as handle:
        frame.to_csv(handle, index=False, lineterminator="\n")


def wilson(k, n):
    z = NormalDist().inv_cdf(0.975)
    p = k / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    radius = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return max(0, center - radius), min(1, center + radius)


class Analysis:
    def __init__(self, run, output):
        self.run, self.output = run, output
        self.checks = []
        self.input_hashes = {}
        self.summary = read_json(run / "run_summary.json")
        self.manifest = read_json(run / "run_manifest.json")
        self.config = read_json(run / "resolved_config.json")
        self.train = pd.read_csv(run / "train_episodes.csv")
        self.train["success"] = self.train["success"].map({True: 1, False: 0, "True": 1, "False": 0})
        self.metrics = pd.read_csv(run / "train_metrics.csv")
        self.evals = pd.read_csv(run / "diagnostic_episodes.csv")
        self.evals["step"] = self.evals["evaluation_id"].str.extract(r"^step_(\d+)$").astype(int)
        self.ledger = pd.read_csv(run / "cost_ledger.csv")
        self.banks = read_json(run / "evaluation_banks.json")
        self.selected = read_json(run / "selected_checkpoint.json")

    def check(self, name, condition, details=None):
        passed = bool(condition)
        self.checks.append({"name": name, "passed": passed, "details": details})
        if not passed:
            raise AssertionError(f"{name}: {details}")

    def snapshot(self):
        inputs = [p for p in self.run.rglob("*") if p.is_file()
                  and "source_snapshot" not in p.parts and p.suffix in (".json", ".jsonl", ".csv")]
        for source in sorted(inputs):
            key = source.relative_to(self.run).as_posix()
            self.input_hashes[key] = sha256(source)
            dest = self.output / "evidence" / key
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
        for name in ("analyze_p0.py", "requirements.txt", "references.json"):
            shutil.copy2(ROOT / name, self.output / name)

    def audit(self):
        s, tr, ev, mt = self.summary, self.train, self.evals, self.metrics
        self.check("completed_seed901_budget", s["status"] == "completed" and s["error"] is None
                   and self.config["seed"] == 901 and s["training_steps"] == 400000
                   and s["sac_iterations"] == 399000)
        self.check("800_complete_episodes", len(tr) == 800 and not tr.isna().any().any()
                   and tr["episode"].tolist() == list(range(1, 801))
                   and (tr["step"] == tr["episode"] * 500).all() and (tr["length"] == 500).all()
                   and tr["success"].isin([0, 1]).all())
        self.check("200_episodes_and_100k_steps_per_task",
                   tr.groupby("task").size().to_dict() == dict.fromkeys(TASKS, 200)
                   and tr.groupby("task")["length"].sum().to_dict() == s["collected_by_task"])
        block_counts = tr.groupby([(tr["episode"] - 1) // 8, "task"]).size().unstack(fill_value=0)
        self.check("all_100_blocks_uniform", len(block_counts) == 100 and (block_counts == 2).all().all())
        self.check("unique_training_resets", tr["initial_state_hash"].nunique() == 800)
        all_bank_rows = self.banks["diagnostic"] + self.banks["outcome"]
        self.check("280_disjoint_evaluation_states", len(all_bank_rows) == 280
                   and len({r["initial_state_hash"] for r in all_bank_rows}) == 280
                   and len({r["task_parameter_hash"] for r in all_bank_rows}) == 280
                   and len({r["seed"] for r in all_bank_rows}) == 280)
        self.check("no_training_reset_in_evaluation_banks",
                   not set(tr["initial_state_hash"]) & {r["initial_state_hash"] for r in all_bank_rows})
        self.check("complete_320_evaluation_rows", len(ev) == 320 and not ev.isna().any().any()
                   and sorted(ev["step"].unique()) == list(CHECKPOINTS)
                   and (ev.groupby(["step", "task"]).size() == 20).all()
                   and not ev.duplicated(["step", "task", "episode_index"]).any())
        self.check("public_bank_only", ev["bank"].eq("diagnostic").all()
                   and ev["context"].eq("p0_pretraining").all()
                   and ev["policy_type"].eq("learned_sac").all()
                   and s["outcome_bank_episodes_evaluated"] == 0 and s["research_branches_executed"] == 0)
        self.check("evaluation_horizons", ev["success"].isin([0, 1]).all()
                   and ev["length"].between(1, 500).all()
                   and ev.loc[ev["success"] == 0, "length"].eq(500).all())
        known = {(r["task"], r["episode_index"]): r for r in self.banks["diagnostic"]}
        same_bank = all(row.seed == known[(row.task, row.episode_index)]["seed"]
                        and row.initial_state_hash == known[(row.task, row.episode_index)]["initial_state_hash"]
                        for row in ev.itertuples())
        self.check("same_physical_cases_at_all_four_checkpoints", same_bank)
        for step in CHECKPOINTS:
            actual = ev[ev["step"] == step].groupby("task")["success"].sum().to_dict()
            diagnostic = s["diagnostics"][str(step)]
            self.check(f"recomputed_diagnostic_{step}", actual == diagnostic["success_counts"]
                       and math.isclose(sum(actual.values()) / 80, diagnostic["macro_success"])
                       and ev.loc[ev["step"] == step, "length"].sum() == diagnostic["environment_steps"]
                       and diagnostic["state_unchanged"], actual)
        self.check("all_1600_metric_rows", len(mt) == 1600 and mt["step"].tolist() == list(range(250, 400001, 250)))
        self.check("update_contract_at_all_logged_steps", (mt["updates"] == (mt["step"] - 1000).clip(lower=0)).all())
        collected, sampled = [f"collected_{t}" for t in TASKS], [f"sampled_{t}" for t in TASKS]
        self.check("collection_and_batch_accounting", (mt[collected].sum(axis=1) == mt["step"]).all()
                   and (mt[sampled].sum(axis=1) == mt["updates"] * 256).all()
                   and mt[sampled].diff().iloc[1:].ge(0).all().all()
                   and (mt.loc[mt["step"] > 1000, [f"last_batch_{t}" for t in TASKS]].sum(axis=1) == 256).all())
        self.check("replay_ring_counters", (mt["replay_size"] == mt["step"].clip(upper=100000)).all()
                   and (mt["replay_pos"] == mt["step"] % 100000).all())
        self.check("finite_post_warmup_metrics", np.isfinite(mt.loc[mt["step"] > 1000, list(METRICS)].to_numpy()).all()
                   and mt.loc[mt["step"] > 1000, "entropy_coefficient"].gt(0).all())
        self.check("sampled_final_counts_match_summary", {t: int(mt.iloc[-1][f"sampled_{t}"]) for t in TASKS} == s["sampled_by_task"])
        self.check("recorded_parameter_changes_finite_positive", all(np.isfinite(v) and v > 0
                   for v in s["parameter_max_abs_change"].values()))
        self.check("cost_ledger_reconciles", self.ledger["passed"].all()
                   and all(int(self.ledger[k].sum()) == value for k, value in s["costs"].items())
                   and int(tr["length"].sum() + ev["length"].sum()) == s["costs"]["environment_steps"])
        self.check("training_time_reconciles", math.isclose(self.ledger.loc[self.ledger["stage"].str.startswith("train_"), "seconds"].sum(), s["training_seconds"]))
        source_root = self.run.parents[2]
        for name, expected in self.manifest["source_hashes"].items():
            self.check(f"frozen_source_{name}", sha256(source_root / name) == expected
                       and sha256(self.run / "source_snapshot" / name) == expected)
        for step in (200000, 400000):
            directory = self.run / "checkpoints" / f"step_{step:09d}"
            checkpoint, restored = read_json(directory / "checkpoint_manifest.json"), read_json(directory / "restore_verification.json")
            self.check(f"checkpoint_counters_{step}", checkpoint["step"] == step
                       and checkpoint["updates"] == step - 1000 and checkpoint["replay_size"] == 100000
                       and checkpoint["source_hashes"] == self.manifest["source_hashes"]
                       and restored["restored_state_matches"])
            for name, expected in checkpoint["files"].items():
                self.check(f"checkpoint_file_{step}_{name}", sha256(directory / name) == expected)
        self.check("first_eligible_checkpoint_remains_200k", self.selected["step"] == 200000
                   and s["selected_checkpoint_step"] == 200000 and self.selected["eligible"]
                   and self.selected["mixed_success_tasks"] == ["WO", "WC"])

    def tables(self):
        rows = []
        for (step, task), group in self.evals.groupby(["step", "task"]):
            k, n = int(group["success"].sum()), len(group)
            lo, hi = wilson(k, n)
            other = binomtest(k, n).proportion_ci(confidence_level=0.95, method="wilson")
            self.check(f"wilson_independent_check_{step}_{task}", math.isclose(lo, other.low, abs_tol=1e-12)
                       and math.isclose(hi, other.high, abs_tol=1e-12))
            successful = group.loc[group["success"] == 1, "length"]
            rows.append({"step": step, "task": task, "successes": k, "episodes": n, "success_rate": k / n,
                         "wilson95_low": lo, "wilson95_high": hi,
                         "mean_eval_length": group["length"].mean(), "mean_eval_return": group["return"].mean(),
                         "median_steps_among_successes": successful.median() if len(successful) else np.nan,
                         "min_steps_among_successes": successful.min() if len(successful) else np.nan,
                         "max_steps_among_successes": successful.max() if len(successful) else np.nan})
        self.diagnostics = pd.DataFrame(rows)
        rows = []
        case_rows = []
        for first, last in ((0, 100000), (100000, 200000), (200000, 400000), (0, 400000)):
            for task in TASKS:
                frame = self.evals[self.evals["task"] == task].pivot(index="episode_index", columns="step", values="success")
                before, after = frame[first], frame[last]
                wins = (before.eq(0) & after.eq(1))
                losses = (before.eq(1) & after.eq(0))
                rows.append({"from_step": first, "to_step": last, "task": task,
                             "paired_episodes": len(frame), "new_successes": int(wins.sum()),
                             "lost_successes": int(losses.sum()), "persistent_successes": int((before.eq(1) & after.eq(1)).sum()),
                             "persistent_failures": int((before.eq(0) & after.eq(0)).sum()),
                             "task_gain_pp": 100 * (after.mean() - before.mean()),
                             "macro_gain_contribution_pp": 25 * (after.mean() - before.mean())})
                for index in frame.index:
                    case_rows.append({"from_step": first, "to_step": last, "task": task, "episode_index": index,
                                      "before": int(before[index]), "after": int(after[index]),
                                      "change": int(after[index] - before[index])})
        self.paired = pd.DataFrame(rows)
        self.case_changes = pd.DataFrame(case_rows)
        self.train_windows = {}
        for width in (40000, 100000):
            rows = []
            windows = ((self.train["step"] - 1) // width + 1) * width
            for (end, task), group in self.train.groupby([windows, "task"]):
                rows.append({"start_step": end - width, "end_step": end, "task": task,
                             "episodes": len(group), "successes": int(group["success"].sum()),
                             "success_rate": group["success"].mean(), "return_mean": group["return"].mean(),
                             "return_p10": group["return"].quantile(.1), "return_median": group["return"].median(),
                             "return_p90": group["return"].quantile(.9), "return_min": group["return"].min(),
                             "return_max": group["return"].max()})
            self.train_windows[width] = pd.DataFrame(rows)
        optimization = []
        mt = self.metrics[self.metrics["step"] > 1000]
        for end, group in mt.groupby(((mt["step"] - 1) // 100000 + 1) * 100000):
            row = {"window_end": end, "logged_updates": len(group)}
            for column in METRICS:
                for label, value in (("median", group[column].median()), ("p10", group[column].quantile(.1)),
                                     ("p90", group[column].quantile(.9)), ("min", group[column].min()), ("max", group[column].max())):
                    row[f"{column}_{label}"] = value
            optimization.append(row)
        self.optimization = pd.DataFrame(optimization)
        exposure = []
        for step in (4000, 100000, 200000, 400000):
            row = self.metrics[self.metrics["step"] == step].iloc[0]
            total = row["updates"] * 256
            for task in TASKS:
                exposure.append({"step": step, "task": task, "collected_transitions": int(row[f"collected_{task}"]),
                                 "sampled_transitions_with_replacement": int(row[f"sampled_{task}"]),
                                 "sample_share": row[f"sampled_{task}"] / total,
                                 "percentage_point_deviation_from_25": 100 * row[f"sampled_{task}"] / total - 25})
        self.exposure = pd.DataFrame(exposure)
        timing = []
        for kind, prefix in (("train", "train_"), ("evaluation", "diagnostic_"), ("checkpoint", "checkpoint_"),
                             ("bank_generation", "build_evaluation_banks"), ("model_initialization", "initialize_fresh_sac")):
            group = self.ledger[self.ledger["stage"].str.startswith(prefix)]
            timing.append({"category": kind, "seconds": group["seconds"].sum(),
                           "environment_steps": int(group["environment_steps"].sum()),
                           "steps_per_second": group["environment_steps"].sum() / group["seconds"].sum()})
        self.timing = pd.DataFrame(timing)
        comparisons = self.train_windows[100000].query("end_step == 400000").merge(
            self.diagnostics.query("step == 400000"), on="task", suffixes=("_training_last100k", "_evaluation_400k"))
        selector_rows = []
        for step in (200000, 400000):
            selector = read_json(self.run / "selectors" / f"step_{step:09d}.json")
            rates = self.diagnostics.query("step == @step").set_index("task")["success_rate"]
            for method, candidate in selector["recommendations"].items():
                task = candidate.removeprefix("F_") if candidate != "U" else None
                selector_rows.append({"step": step, "rule": method, "recommendation": candidate,
                                      "selected_checkpoint": step == self.selected["step"],
                                      "target_task_direct_macro_headroom_pp": (1 - rates[task]) * 25 if task else np.nan})
        self.selectors = pd.DataFrame(selector_rows)
        for name, frame in {"diagnostic_summary": self.diagnostics, "paired_changes": self.paired,
                            "paired_case_changes": self.case_changes, "train_40k_windows": self.train_windows[40000],
                            "train_100k_windows": self.train_windows[100000], "optimization_100k_windows": self.optimization,
                            "replay_exposure": self.exposure, "runtime_costs": self.timing,
                            "training_vs_evaluation": comparisons, "selector_analysis": self.selectors}.items():
            csv_output(self.output / f"{name}.csv", frame)

    def figures(self):
        plt.rcParams.update({"font.family": "Malgun Gothic", "axes.unicode_minus": False,
                             "font.size": 10, "axes.titlesize": 12, "axes.spines.top": False,
                             "axes.spines.right": False, "figure.facecolor": "white",
                             "axes.labelcolor": "#252525", "text.color": "#252525", "savefig.dpi": 170})

        def finish(fig, name, note):
            fig.text(.02, .02, note, fontsize=9, color="#555555", va="bottom")
            fig.tight_layout(rect=(0, .12, 1, .92))
            fig.savefig(self.output / f"{name}.png", facecolor="white")
            fig.savefig(self.output / f"{name}.svg", facecolor="white")
            plt.close(fig)

        fig, (ax, ci) = plt.subplots(1, 2, figsize=(12, 5.4), gridspec_kw={"width_ratios": [1.1, 1]})
        fig.suptitle("공개 진단 성공률과 최종 평가의 불확실성", x=.02, ha="left", fontsize=17, fontweight="bold")
        matrix = self.diagnostics.pivot(index="task", columns="step", values="success_rate").reindex(TASKS)
        ax.imshow(matrix.to_numpy(), cmap="Blues", vmin=0, vmax=1, aspect="auto")
        ax.set_xticks(range(4), ["0", "100k", "200k", "400k"])
        ax.set_yticks(range(4), [f"{t}  {NAMES[t]}" for t in TASKS])
        ax.set_xlabel("전체 학습 steps")
        for i in range(4):
            for j in range(4):
                rate = matrix.iloc[i, j]
                ax.text(j, i, f"{rate:.0%}\n({int(round(rate * 20))}/20)", ha="center", va="center",
                        color="white" if rate >= .6 else "#202020", fontsize=11)
        final = self.diagnostics.query("step == 400000").set_index("task").loc[list(TASKS)]
        for i, task in enumerate(TASKS):
            row = final.loc[task]
            ci.errorbar(row.success_rate * 100, i,
                        xerr=[[100 * (row.success_rate - row.wilson95_low)], [100 * (row.wilson95_high - row.success_rate)]],
                        fmt="o", color=COLORS[task], markersize=7, capsize=4, lw=2)
            ci.text(row.success_rate * 100, i - .22, f"{row.success_rate:.0%}", ha="center", fontsize=10)
        ci.set_yticks(range(4), list(TASKS)); ci.invert_yaxis(); ci.set_ylim(3.55, -.55)
        ci.set_xlim(-4, 106); ci.set_xticks([0, 25, 50, 75, 100]); ci.set_xlabel("400k 성공률 (%)")
        ci.grid(axis="x", color="#e5e5e5")
        ci.set_title("과제별 95% Wilson 구간")
        finish(fig, "01_diagnostic_success", "동일한 초기 상태 20개/과제, seed 901의 deterministic 정책. 구간은 초기 상태 표본의 불확실성만 근사합니다.\n사전학습 seed 간 변동은 포함하지 않으며, 네 구간을 동시에 보장하는 보정은 적용하지 않았습니다.")

        fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=True, sharey=True)
        fig.suptitle("학습 중 성공과 고정 정책 공개 평가", x=.02, ha="left", fontsize=17, fontweight="bold")
        for ax, task in zip(axes.flat, TASKS):
            data = self.train_windows[40000].query("task == @task")
            ax.plot((data.start_step + data.end_step) / 2000, data.success_rate * 100,
                    color=COLORS[task], marker="s", markersize=5, label="학습: 40k 구간 평균")
            diagnostic = self.diagnostics.query("task == @task")
            ax.scatter(diagnostic.step / 1000, diagnostic.success_rate * 100, facecolors="white",
                       edgecolors="#222222", s=72, zorder=4, linewidths=1.7, label="공개 평가: 해당 checkpoint")
            ax.set_title(f"{task}  {NAMES[task]}", loc="left"); ax.set_ylim(-5, 105)
            ax.set_xlim(-8, 408); ax.set_xticks([0, 100, 200, 300, 400]); ax.grid(color="#eeeeee")
            ax.set_xlabel("전체 학습 steps (천)"); ax.set_ylabel("성공 episode 비율 (%)")
        axes.flat[0].legend(loc="lower right", fontsize=9)
        finish(fig, "02_training_and_evaluation", "학습 곡선: 각 40k 구간에 과제당 20 episodes, stochastic 행동, 학습 중 바뀌는 정책과 새 초기 상태.\n평가 점: 고정 정책, deterministic 행동, 별도 고정 20개 초기 상태. 두 비율의 차이는 일반화 오차로 바로 해석할 수 없습니다.")

        fig, axes = plt.subplots(1, 4, figsize=(12, 7), sharey=True)
        fig.suptitle("같은 평가 초기 상태에서 성공이 유지되는가", x=.02, ha="left", fontsize=17, fontweight="bold")
        for ax, task in zip(axes, TASKS):
            cases = self.evals.query("task == @task").pivot(index="episode_index", columns="step", values="success")
            ax.imshow(cases.to_numpy(), cmap=ListedColormap(["#eeeeee", COLORS[task]]), vmin=0, vmax=1, aspect="auto")
            ax.set_xticks(range(4), ["0", "100k", "200k", "400k"])
            ax.set_yticks(range(20), range(1, 21)); ax.set_title(f"{task} {NAMES[task]}")
            ax.set_xticks(np.arange(-.5, 4, 1), minor=True); ax.set_yticks(np.arange(-.5, 20, 1), minor=True)
            ax.grid(which="minor", color="white", linewidth=1.3); ax.tick_params(which="minor", length=0)
            for i in range(20):
                for j in range(4):
                    if cases.iloc[i, j]:
                        ax.text(j, i, "1", va="center", ha="center", color="white", fontsize=8)
        axes[0].set_ylabel("고정 평가 episode 번호 (1부터 표시)")
        finish(fig, "03_paired_evaluation_cases", "색이 있는 칸/1 = 성공, 연한 회색 = 실패. 같은 행은 동일 seed·물리 상태이며 checkpoint 간에 짝지어 비교했습니다.\n20개 초기 상태를 4회 평가한 것이며, 과제당 80개의 독립 초기 상태로 세지 않습니다.")

        fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=True)
        fig.suptitle("학습 진단과 실제 replay 배치 노출", x=.02, ha="left", fontsize=17, fontweight="bold")
        mt = self.metrics.query("step > 1000")
        xs = mt.step / 1000
        axes[0, 0].plot(xs, mt.critic_loss, color="#d3dce3", lw=.6)
        axes[0, 0].plot(xs, mt.critic_loss.rolling(40, min_periods=1).median(), color="#326b9e", lw=1.8)
        axes[0, 0].set_title("Critic loss: 원시 로그와 최근 10k 중앙값", loc="left")
        axes[0, 0].set_ylabel("loss (성공률 지표가 아님)")
        axes[0, 1].plot(xs, mt.entropy_coefficient, color="#6a7742", lw=1)
        axes[0, 1].set_title("자동 entropy coefficient", loc="left"); axes[0, 1].set_ylabel("alpha")
        for i, color in enumerate(("#326b9e", "#a65430")):
            axes[1, 0].plot(xs, mt[f"critic_{i}_abs_td_error"].rolling(40, min_periods=1).median(),
                            label=f"critic {i}", color=color, lw=1.7, linestyle="-" if i == 0 else "--")
        axes[1, 0].set_title("절대 TD error: 최근 10k 중앙값", loc="left"); axes[1, 0].legend()
        axes[1, 0].set_ylabel("평균 절대 TD error")
        for task, marker in zip(TASKS, ("o", "s", "^", "D")):
            share = 100 * mt[f"sampled_{task}"] / (mt.updates * 256)
            axes[1, 1].plot(xs, share, color=COLORS[task], label=task, marker=marker, markevery=160, markersize=4)
        axes[1, 1].axhline(25, color="#777777", ls=":", lw=1)
        axes[1, 1].set_title("실제 gradient batch의 누적 과제 비율", loc="left")
        axes[1, 1].set_ylabel("노출 비율 (%)"); axes[1, 1].set_ylim(0, 100); axes[1, 1].legend(ncol=4, fontsize=8)
        for ax in axes.flat:
            ax.set_xlim(0, 400); ax.set_xticks([0, 100, 200, 300, 400]); ax.grid(color="#eeeeee")
            ax.set_xlabel("전체 학습 steps (천)")
        finish(fig, "04_optimization_and_exposure", "250 steps마다 기록한 진단값입니다. TD/loss는 여러 과제가 섞인 batch에서 계산되므로 수집 중인 task의 loss로 볼 수 없습니다.\nLoss 크기나 actor loss의 부호만으로 성능·수렴 여부를 판단하지 않습니다. Replay 노출은 중복 sampling을 포함한 횟수입니다.")

    def report(self):
        final = self.diagnostics.query("step == 400000").set_index("task").loc[list(TASKS)]
        late = self.train_windows[100000].query("end_step == 400000").set_index("task").loc[list(TASKS)]
        gains = self.paired.query("from_step == 200000 and to_step == 400000")
        exposure = self.exposure.query("step == 400000")
        summary = {
            "assessment": "technically_valid_pilot_with_uneven_task_proficiency",
            "original_seed": 901, "training_steps": 400000, "gradient_iterations": 399000,
            "evaluation_unique_initial_states": 80, "evaluation_episode_records": 320,
            "macro_success_by_step": {str(step): float(self.diagnostics.query("step == @step").success_rate.mean()) for step in CHECKPOINTS},
            "final_success_rates": final.success_rate.to_dict(),
            "final_wilson95": {t: [float(final.loc[t, "wilson95_low"]), float(final.loc[t, "wilson95_high"])] for t in TASKS},
            "last100k_training_success": late.success_rate.to_dict(),
            "last100k_training_episode_counts": late.episodes.to_dict(),
            "last100k_mean_return": late.return_mean.to_dict(),
            "paired_200k_to_400k": gains.to_dict(orient="records"),
            "final_sample_shares": exposure.set_index("task").sample_share.to_dict(),
            "final_optimization_metrics": {key: float(self.metrics.iloc[-1][key]) for key in METRICS},
            "selected_checkpoint_step": int(self.selected["step"]),
            "frozen_200k_recommendations": self.selected["recommendations"],
            "recorded_400k_recommendations": read_json(self.run / "selectors/step_000400000.json")["recommendations"],
            "timing": self.timing.to_dict(orient="records"),
            "training_transitions": 400000, "evaluation_transitions": int(self.evals.length.sum()),
            "original_elapsed_seconds": self.summary["elapsed_seconds"],
            "cuda_peak_pytorch_tensor_MiB": self.summary["cuda_peak_allocated_bytes"] / (1024 ** 2),
            "interval_scope": "Approximate marginal 95% Wilson intervals conditional on one learned policy; no training-seed uncertainty or simultaneous coverage.",
            "limits": ["No outcome-bank policy scores were evaluated.", "No allocation branches have run.",
                       "Only four diagnostic checkpoints; no claim of detailed deterministic learning curves or convergence.",
                       "Training success uses stochastic actions and changing policies/resets; not an unbiased estimate of final deterministic evaluation.",
                       "Task failure mechanisms, gradient conflict, and causal allocation effects are not identified by these aggregate logs."]}
        write_json(self.output / "analysis_summary.json", summary)
        return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
    output = args.output.resolve() if args.output else ROOT / "results" / name
    if not output.is_relative_to((ROOT / "results").resolve()) or output == (ROOT / "results").resolve():
        parser.error("Output must be a new directory inside this analysis version's results/.")
    output.mkdir(parents=True, exist_ok=False)
    started, analysis = time.perf_counter(), None
    print(f"Analysis output: {output}", flush=True)
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "source_run": str(args.run.resolve()),
                "python": sys.version, "packages": {name: importlib.metadata.version(name) for name in ("numpy", "pandas", "scipy", "matplotlib")},
                "analysis_code_sha256": sha256(Path(__file__)), "status": "failed",
                "additional_training_steps": 0, "additional_evaluation_episodes": 0}
    try:
        analysis = Analysis(args.run.resolve(), output)
        analysis.snapshot()
        analysis.audit()
        print(f"Audit passed: {len(analysis.checks)} checks", flush=True)
        analysis.tables()
        analysis.figures()
        result = analysis.report()
        analysis.check("input_files_unchanged", all(sha256(analysis.run / name) == digest
                       for name, digest in analysis.input_hashes.items()))
        manifest["status"] = "completed"
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    except BaseException:
        (output / "failure_traceback.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise
    finally:
        manifest["elapsed_seconds"] = time.perf_counter() - started
        manifest["input_hashes"] = analysis.input_hashes if analysis else {}
        manifest["output_hashes"] = {p.relative_to(output).as_posix(): sha256(p) for p in sorted(output.glob("*")) if p.is_file()}
        write_json(output / "analysis_manifest.json", manifest)
        write_json(output / "audit_checks.json", analysis.checks if analysis else [])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
