"""Standalone research figures; source-backed PNG and SVG exports."""
import csv
import hashlib
import json
import os
import shutil
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    start = time.perf_counter()
    source = Path(sys.argv[1]).resolve()
    out = HERE / "results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_figures_") + uuid.uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    shutil.copy2(__file__, out / "plot_source.py")
    os.environ["MPLCONFIGDIR"] = str(out / "matplotlib_cache")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    hashes, figures = {}, []

    def rows(name):
        path = source / name
        hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        with path.open(encoding="utf-8-sig", newline="") as h:
            return list(csv.DictReader(h))

    summary = rows("selection_summary.csv")
    groups = rows("selection_by_group.csv")
    pairs = rows("horizon_pairs.csv")
    plt.rcParams.update({"font.family": "Malgun Gothic", "font.size": 11,
                         "axes.unicode_minus": False, "axes.spines.top": False,
                         "axes.spines.right": False, "svg.fonttype": "none",
                         "axes.labelcolor": "#263442", "text.color": "#263442"})
    colors = ["#2368a2", "#d88a20", "#a34868", "#6f7f39"]

    def finish(fig, stem, note, top=.94):
        fig.text(.06, .025, note, fontsize=9, color="#52606d", va="bottom")
        fig.tight_layout(rect=(.025, .09, .995, top))
        for suffix in ("png", "svg"):
            dest = out / (stem + "." + suffix)
            fig.savefig(dest, dpi=170, facecolor="white")
        plt.close(fig)
        figures.append(stem)

    ns = [2, 5, 10, 20, 50]
    modes = [("measurement_only_20", "같은 정책 · 20k"), ("cross_repeat_20", "다른 후속 seed · 20k"),
             ("cross_repeat_20_to_40", "다른 후속 seed · 20k→40k"), ("cross_repeat_40", "다른 후속 seed · 40k 참고")]
    fig, ax = plt.subplots(figsize=(10.2, 6.4))
    for idx, (mode, label) in enumerate(modes):
        vals = [float(next(r for r in summary if r["mode"] == mode and int(r["cases_per_task"]) == n and r["method"] == "Greedy")["hindsight_regret_pp"]) for n in ns]
        ax.plot(ns, vals, marker=["o", "s", "D", "^"][idx], color=colors[idx], linewidth=2, label=label)
    ax.set(xticks=ns, xlabel="과제당 선택용 평가 사례 수", ylabel="보류 사례의 관측 최상위 대비 손실 (%p)", ylim=(0, 8.5))
    ax.grid(axis="y", color="#e5e9ed")
    ax.legend(loc="center left", bbox_to_anchor=(1.01, .55), frameon=False, fontsize=10)
    fig.suptitle("사례 수와 선택 결과의 재현성", fontsize=17)
    finish(fig, "selection_transfer", "A/B/C 동일 가중. 선택·채점 사례 분리. 관측 최상위는 잡음이 있는 참고값이며 true oracle이 아님.\n선택용 부분집합 2,000회는 독립 RL 반복이 아님. 모든 곡선은 Greedy 선택.")

    fig, axes = plt.subplots(1, 2, figsize=(12, 5.7), sharey=True)
    method_names = [("Greedy", "항상 최고 점수"), ("Gap2_Development_fixed", "차이 2%p 규칙"), ("Reliability_Development_fixed", "신뢰도 + 반복 동의")]
    group_keys = [("A", 200000), ("A", 400000), ("B", 200000), ("C", 200000)]
    for ax, n in zip(axes, [2, 20]):
        for mi, (method, label) in enumerate(method_names):
            vals = [float(next(r for r in groups if r["mode"] == "cross_repeat_20_to_40" and int(r["cases_per_task"]) == n and r["method"] == method and r["suite"] == s and int(r["checkpoint_step"]) == cp)["vs_development_fixed_pp"]) for s, cp in group_keys]
            ax.bar(np.arange(4) + (mi - 1) * .24, vals, width=.22, color=colors[mi], label=label,
                   hatch=["", "//", ".."][mi], edgecolor="white", linewidth=.7)
        ax.axhline(0, color="#263442", linewidth=1)
        ax.set(xticks=range(4), xticklabels=["A 200k", "A 400k", "B 200k", "C 200k"], title=f"과제당 {n}회", ylim=(-6, 6))
        ax.grid(axis="y", color="#e5e9ed", zorder=0)
        ax.set_axisbelow(True)
    axes[0].set_ylabel("개발 고정 배분 대비 40k 차이 (%p)")
    handles, labels = axes[1].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(.5, .915), ncol=3, fontsize=10, frameon=False)
    fig.suptitle("기본 배분의 품질에 따라 달라지는 신뢰도 규칙", fontsize=17)
    finish(fig, "gate_by_group", "다른 두 후속 seed의 20k로 선택, 남긴 seed의 40k·별도 50사례로 채점.\n고정 배분은 해당 원래 seed를 제외한 개발 자료로 선정. 진단 비용을 차감한 온라인 성적이 아님.", top=.85)

    fig, ax = plt.subplots(figsize=(9.5, 5.9))
    for i, (metric, label, color) in enumerate([
        ("observed_continuation_sd_40_pp", "같은 100사례에서 후속 seed 간 SD", colors[0]),
        ("rms_single_continuation_case_se_40_pp", "고정 정책의 평가 사례 SE", colors[1])]):
        vals = []
        for s, cp in group_keys:
            rs = [r for r in pairs if r["suite"] == s and int(r["checkpoint_step"]) == cp]
            vals.append(float(np.sqrt(np.mean([float(r[metric]) ** 2 for r in rs]))))
        bars = ax.bar(np.arange(4) + (i - .5) * .34, vals, width=.32, color=color, label=label, hatch="" if i == 0 else "//")
        ax.bar_label(bars, fmt="%.2f", padding=3, fontsize=10)
    ax.set(xticks=range(4), xticklabels=["A 200k", "A 400k", "B 200k", "C 200k"], ylabel="배분 간 macro 차이의 변동 (%p)")
    ax.set_ylim(0, ax.get_ylim()[1] * 1.17)
    ax.legend(frameon=False, loc="upper left", fontsize=10)
    ax.grid(axis="y", color="#e5e9ed")
    ax.set_axisbelow(True)
    fig.suptitle("후속 학습 변동과 평가 사례 오차", fontsize=17)
    finish(fig, "variation_sources", "그룹별 30개 배분 쌍 통계의 RMS. 각 출발 상태의 후속 seed는 3개.\n서로 다른 변동 척도의 기술적 비교이며, 독립 성분으로 분해한 분산이나 인과 기여율이 아님.")

    fig, axes = plt.subplots(2, 2, figsize=(10, 9), sharex=True, sharey=True)
    limit = 25
    for ax, (s, cp) in zip(axes.flat, group_keys):
        rs = [r for r in pairs if r["suite"] == s and int(r["checkpoint_step"]) == cp]
        for robust, marker, color in [(False, "o", "#9aafc0"), (True, "D", "#a34868")]:
            sub = [r for r in rs if (r["simultaneous_case_robust_reversal"] == "True") == robust]
            ax.scatter([float(r["difference_20k_pp"]) for r in sub], [float(r["difference_40k_pp"]) for r in sub],
                       marker=marker, c=color, s=44 if robust else 26, alpha=.9, edgecolors="white", linewidths=.5)
        ax.axhline(0, color="#6d7780", linewidth=.8)
        ax.axvline(0, color="#6d7780", linewidth=.8)
        ax.plot([-limit, limit], [-limit, limit], linestyle="--", linewidth=.7, color="#bcc4cb")
        count = sum(r["reversed"] == "True" for r in rs)
        robust_count = sum(r["simultaneous_case_robust_reversal"] == "True" for r in rs)
        ax.set(title=f"{s} {cp // 1000}k: 반전 {count}/30, 동시 구간 {robust_count}", xlim=(-limit, limit), ylim=(-limit, limit))
        ax.set_aspect("equal")
    for ax in axes[-1]:
        ax.set_xlabel("20k의 배분 a - b (%p)")
    for ax in axes[:, 0]:
        ax.set_ylabel("40k의 배분 a - b (%p)")
    fig.suptitle("시간이 지나며 방향이 바뀐 배분 차이", fontsize=17)
    finish(fig, "horizon_reversals", "마름모: 출발 상태별 동시 95% case-bootstrap 구간에서도 반대 부호. 고정된 3개 학습 반복에 조건부.\n정책·원래 seed의 모집단 불확실성은 포함하지 않음. 120개 쌍은 독립 실험 120회가 아님.")
    manifest = {"analysis_run": str(source), "figures": figures, "input_hashes": hashes,
                "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "matplotlib": matplotlib.__version__, "numpy": np.__version__, "python": sys.version,
                "wall_seconds": time.perf_counter() - start, "environment_steps": 0, "learner_updates": 0}
    with (out / "manifest.json").open("x", encoding="utf-8") as h:
        json.dump(manifest, h, indent=2, ensure_ascii=False)
    print(json.dumps({"output": str(out), "figures": figures, "wall_seconds": manifest["wall_seconds"]}))


if __name__ == "__main__":
    main()
