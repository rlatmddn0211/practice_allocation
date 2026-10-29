"""Calculate proposed budgets and check design consistency; never run RL."""

from __future__ import annotations

import csv
import hashlib
import json
import platform
import re
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


BASE = Path(__file__).resolve().parent
REPO = BASE.parent


def write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def main() -> int:
    start = time.perf_counter()
    started = datetime.now(timezone.utc)
    output = BASE / "results" / (
        started.strftime("%Y%m%dT%H%M%SZ") + "_design_" + uuid4().hex[:8]
    )
    output.mkdir(parents=True, exist_ok=False)
    checks: list[dict] = []
    rows: list[dict] = []
    manifest: list[dict] = []
    error = None

    def check(name: str, passed: bool, detail: object = None) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    try:
        # Exact bytes used by this calculation are retained even after failures.
        inputs = [
            Path(__file__).resolve(), BASE / "protocol.json", BASE / "README.md",
            BASE / "research_design_ko.md", REPO / "README.md",
            REPO / "AGENTS.md", REPO / ".gitattributes",
        ]
        blobs = {}
        for path in inputs:
            data = path.read_bytes()
            relative = path.relative_to(REPO)
            snapshot = output / "evidence_inputs" / relative
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            with snapshot.open("xb") as handle:
                handle.write(data)
            blobs[path] = data
            manifest.append({
                "input_relative_path": relative.as_posix(),
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
                "snapshot": snapshot.relative_to(output).as_posix(),
            })
        p = json.loads(blobs[BASE / "protocol.json"])
        costing = p["costing"]
        tasks = costing["tasks_per_composition"]
        episode_steps = costing["max_episode_steps"]
        diag_episodes = tasks * costing["diagnostic_episodes_per_task"]
        outcome_episodes = tasks * costing["outcome_episodes_per_task"]

        def budget(
            stage: str, contexts: int, branches: int, pretrain: int,
            branch_budget: int, diag_policies: int, outcome_policies: int,
            note: str,
        ) -> dict:
            d = diag_policies * diag_episodes
            o = outcome_policies * outcome_episodes
            row = {
                "stage": stage, "contexts": contexts, "branches": branches,
                "pretrain_env_steps": pretrain,
                "branch_train_or_inclusive_budget_steps": branch_budget,
                "diagnostic_eval_episodes_outside_branch_budget": d,
                "outcome_eval_episodes": o,
                "diagnostic_eval_steps_max_outside_branch_budget": d * episode_steps,
                "outcome_eval_steps_max": o * episode_steps,
                "total_env_steps_max": pretrain + branch_budget + (d + o) * episode_steps,
                "note": note,
            }
            rows.append(row)
            return row

        budget("snapshot_only", 12, 0, 0, 0, 0, 0,
               "No new environment steps; future diagnostic compute costs must be recorded.")
        shared = costing["shared_probe"]
        nprobe = shared["contexts"] * shared["allocations"] * shared["continuations"]
        nstates = shared["contexts"]
        check("shared probe snapshot count",
              shared["diagnostic_policy_snapshots"] == nstates + nprobe)
        budget("shared_4k_probe", nstates, nprobe, 0, nprobe * shared["steps"],
               nstates + nprobe, 0,
               "Development only; new probes and old completions aggregate separately by parent/allocation.")
        extension = costing["optional_probe_extension"]
        check("8k extension snapshot count", extension["extra_policy_snapshots"] == nprobe)
        budget("optional_4k_to_8k_increment", nstates, nprobe, 0,
               nprobe * extension["extra_steps_each"], nprobe, 0,
               "Incremental costs only; not included in the shared 4k row.")

        pilot = costing["factor8_pilot"]
        pilot_branches = pilot["contexts"] * pilot["conditions"] * pilot["continuations"]
        check("F08 parent plus final outcomes",
              pilot["outcome_policy_snapshots"] == pilot["contexts"] + pilot_branches)
        check("F08 diagnostic parents", pilot["diagnostic_policy_snapshots"] == pilot["contexts"])
        budget("optional_F08_pilot", pilot["contexts"], pilot_branches, 0,
               pilot_branches * pilot["steps"], pilot["contexts"],
               pilot["contexts"] + pilot_branches,
               "Standalone upper bound; dose and sequence families use distinct controlled schedules.")

        confirm = p["selection"]["confirmation"]
        nconfirm_seeds = len(confirm["original_seeds_proposed"])
        cstates = nconfirm_seeds * len(confirm["compositions"])
        cbranches = cstates * confirm["allocations"] * confirm["continuations"]
        cdiag = cstates * len(confirm["checkpoint_steps"]) + cbranches * len(confirm["branch_diagnostic_steps"])
        cr = budget("G3_confirmation_example", cstates, cbranches,
                    cstates * confirm["pretrain_steps"], cbranches * confirm["final_steps"],
                    cdiag, cstates + cbranches,
                    "N=8 is a costing example, not a power calculation; probe and final are the same trajectory.")

        online = p["selection"]["online"]
        nonline_seeds = len(online["fresh_original_seeds_proposed"])
        ostates = nonline_seeds * len(online["compositions"])
        obranches = ostates * len(online["methods"]) * online["continuations"]
        odiag = ostates * len(online["initial_public_checkpoints"])
        ooutcome = obranches + ostates * online["no_learning_evaluations_per_parent"]
        orow = budget("G4_online_example", ostates, obranches,
                      ostates * online["pretrain_steps"],
                      obranches * online["budget_steps_including_diagnostics"],
                      odiag, ooutcome,
                      "In-run diagnostics/discarded probes are already inside each 40k budget; do not add them twice.")

        factors = {f["id"]: f for f in p["factor_groups"]}
        check("eight distinct factors", set(factors) == {f"F{i:02}" for i in range(1, 9)})
        f8 = factors["F08"]
        episodes = pilot["steps"] // episode_steps
        check("whole F08 episodes", pilot["steps"] % episode_steps == 0)
        dose_blocks = episodes // f8["dose_block_episodes"]
        check("whole dose blocks", episodes % f8["dose_block_episodes"] == 0)
        for fraction, counts in zip(f8["dose_fractions"], f8["dose_episode_counts"], strict=True):
            check(f"dose {fraction}: exact total and balanced other tasks",
                  len(counts) == tasks and sum(counts) == episodes
                  and counts[0] / episodes == fraction
                  and len(set(counts[1:])) == 1
                  and all(count % dose_blocks == 0 for count in counts), counts)
        sequence_blocks = episodes // f8["sequence_block_episodes"]
        focus_i = f8["focus_block_episode_counts"]
        focus_j = [focus_i[1], focus_i[0], *focus_i[2:]]
        target = f8["sequence_aggregate_episode_counts"]
        check("whole even sequence blocks",
              episodes % f8["sequence_block_episodes"] == 0 and sequence_blocks % 2 == 0)
        paired_total = [(a + b) * (sequence_blocks // 2) for a, b in zip(focus_i, focus_j)]
        static_total = [v * sequence_blocks for v in f8["static_pair_block_episode_counts"]]
        check("forward, reverse and alternating totals equal static mix",
              paired_total == target == static_total, target)
        check("F08 condition count",
              len(f8["dose_fractions"]) + len(f8["sequence_conditions"]) == pilot["conditions"])

        example = online["feasible_diagnostic_example"]
        m = example["candidate_probes"]
        r = example["probe_steps_each"]
        c = m * tasks * example["evaluation_episodes_per_task"] * example["evaluation_steps_per_episode"]
        b = online["budget_steps_including_diagnostics"]
        cap = int(b * online["primary_diagnostic_cap_fraction"])
        check("online evaluation cap calculation", c == example["full_probe_evaluation_steps_max"])
        check("online probe plus evaluation fits diagnostic cap", m * r + c <= cap)
        check("online retained policy training length",
              b - (m - 1) * r - c == example["selected_policy_training_steps_if_retained_min"])
        check("online discarded probe training length",
              b - m * r - c == example["selected_policy_training_steps_if_all_discarded_min"])
        check("development full bank cannot be free online diagnosis", diag_episodes * episode_steps > cap)
        check("small bank is a subset of full diagnostic bank",
              0 < example["evaluation_episodes_per_task"] < costing["diagnostic_episodes_per_task"])
        dev_seeds = set(p["development"]["original_seed_blocks"])
        cseeds = set(confirm["original_seeds_proposed"])
        oseeds = set(online["fresh_original_seeds_proposed"])
        check("development, confirmation and online seeds disjoint",
              not (dev_seeds & cseeds or dev_seeds & oseeds or cseeds & oseeds))
        check("confirmation continuation labels", len(confirm["continuation_labels_proposed"]) == confirm["continuations"])
        check("online continuation labels", len(online["continuation_labels_proposed"]) == online["continuations"])
        check("design only", p["status"] == "design_only_not_executed")

        design = blobs[BASE / "research_design_ko.md"].decode("utf-8-sig")
        for row in rows[1:]:
            formatted = f'{row["total_env_steps_max"] / 1_000_000:.2f}M'
            check(f"budget appears in document: {row['stage']}", formatted in design, formatted)
        check("G3 per-seed scaling", f'{cr["total_env_steps_max"] / nconfirm_seeds / 1e6:.2f}M × N' in design)
        check("G4 per-seed scaling", f'{orow["total_env_steps_max"] / nonline_seeds / 1e6:.2f}M × N' in design)
        for path in (BASE / "README.md", BASE / "research_design_ko.md", REPO / "README.md"):
            markdown = blobs[path].decode("utf-8-sig")
            for target_link in re.findall(r"\[[^\]]*\]\(([^\s)]+)\)", markdown):
                if target_link.startswith(("https://", "http://", "#")):
                    continue
                target_path = target_link.split("#", 1)[0]
                check("local link: " + path.relative_to(REPO).as_posix() + " -> " + target_link,
                      (path.parent / target_path).exists())
        root_readme = blobs[REPO / "README.md"].decode("utf-8-sig")
        for required_row in (
            "| 학습 반응성 | 짧게 더 연습했을 때 해당 과제가 얼마나 개선되는가 |",
            "| 다른 능력의 변화 | 그 연습으로 다른 과제의 성능이 얼마나 좋아지거나 떨어지는가 |",
            "| 효과의 지속성 | 연습을 이어갈수록 개선 속도가 유지되는가, 포화되거나 역전되는가 |",
        ):
            check("requested README table row preserved", required_row in root_readme, required_row)
        # Also detect accidental changes during the run, without touching any input.
        for path, initial_bytes in blobs.items():
            check("input unchanged: " + path.relative_to(REPO).as_posix(), path.read_bytes() == initial_bytes)
    except Exception:
        error = traceback.format_exc()
        check("calculation completed without exception", False, error)
    finally:
        write_json(output / "source_manifest.json", manifest)
        write_json(output / "checks.json", checks)
        write_json(output / "budgets.json", rows)
        if rows:
            with (output / "budgets.csv").open("x", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
        failed = sum(not entry["passed"] for entry in checks)
        summary = {
            "status": "passed" if not failed and error is None else "failed",
            "purpose": "Design arithmetic and local-reference audit only; no scientific validation.",
            "started_utc": started.isoformat(),
            "finished_utc": datetime.now(timezone.utc).isoformat(),
            "runtime_seconds": time.perf_counter() - start,
            "python_version": sys.version,
            "platform": platform.platform(),
            "dependencies": "Python standard library only",
            "random_seed": None,
            "environment_steps_executed": 0,
            "learner_updates_executed": 0,
            "gpu_seconds": 0,
            "checks_total": len(checks),
            "checks_failed": failed,
            "error": error,
            "source_manifest": "source_manifest.json",
        }
        write_json(output / "summary.json", summary)
    print(json.dumps({"output": output.relative_to(REPO).as_posix(), **summary}, ensure_ascii=False))
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
