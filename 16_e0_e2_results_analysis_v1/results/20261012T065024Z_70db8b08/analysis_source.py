"""Independently recompute E0-E2 findings from episode CSVs; no RL imports."""
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
TASKS = ("DO", "DC", "WO", "WC")
FIELDS = ("macro", *TASKS)
ORDER = ["U", "F_DO", "F_DC", "F_WO", "F_WC"]


def main():
    started = time.perf_counter()
    output = ROOT / "results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(__file__, output / "analysis_source.py")
    hashes, checked = {}, Counter()

    def sha(path):
        with Path(path).open("rb") as stream:
            value = hashlib.file_digest(stream, "sha256").hexdigest()
        hashes[str(path)] = value
        return value

    def read(path):
        sha(path)
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))

    def csv_rows(path):
        sha(path)
        with Path(path).open(encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))

    def save_csv(name, values):
        if values:
            keys = list(dict.fromkeys(key for row in values for key in row))
            with (output / name).open("x", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=keys)
                writer.writeheader()
                writer.writerows(values)

    def close(left, right):
        assert abs(float(left) - float(right)) < 1e-9, (left, right)

    try:
        campaign = Path(read(REPO / "13_e0_e3_autonomous_queue_v1/ACTIVE_CAMPAIGN.json")["campaign"])
        plan = read(campaign / "plan.json")
        assert sha(campaign / "plan.json") == read(campaign / "plan_integrity.json")["sha256"]
        records, metrics, case_sets, analyses = [], [], {}, {}
        for stage in ("E0", "E1", "E2"):
            marker_paths = sorted((campaign / "completed").glob(stage + "_*.json"))
            assert len(marker_paths) == plan["counts"][stage]["jobs"]
            for path in marker_paths:
                marker = read(path)
                result_path = Path(marker["result_ref"]["path"])
                assert sha(result_path) == marker["result_ref"]["sha256"]
                record = read(result_path)
                records.append(record)
                if record["kind"] == "analysis":
                    analyses[stage] = result_path.parent
                if record["kind"] != "evaluate":
                    continue
                assert sha(record["episodes_path"]) == record["episodes_sha256"]
                episodes = csv_rows(record["episodes_path"])
                assert len(episodes) == 400
                assert Counter(row["task"] for row in episodes) == {task: 100 for task in TASKS}
                assert len({(row["task"], row["episode_index"]) for row in episodes}) == 400
                assert all(int(row["success"]) in (0, 1) and 1 <= int(row["length"]) <= 500
                           and math.isfinite(float(row["return"])) for row in episodes)
                signature = sorted((row["task"], row["episode_index"], row["seed"], row["initial_state_hash"]) for row in episodes)
                bank = episodes[0]["bank"]
                assert all(row["bank"] == bank for row in episodes)
                case_key = (stage, bank)
                if case_key in case_sets:
                    assert signature == case_sets[case_key]
                else:
                    case_sets[case_key] = signature
                counts = {task: sum(int(row["success"]) for row in episodes if row["task"] == task) for task in TASKS}
                values = {**counts, "macro": mean(counts.values())}
                for task in TASKS:
                    close(values[task], 100 * record["evaluation"]["success_by_task"][task])
                close(values["macro"], 100 * record["evaluation"]["macro_success"])
                metrics.append({**record, **values})
                checked[stage + "_evaluation_episodes"] += len(episodes)
                checked["policy_evaluations"] += 1

        branches = [row for row in metrics if row.get("role") == "branch"]
        base = {(row["stage"], row["original_seed"], row["checkpoint_step"]): row for row in metrics if row.get("role") == "baseline"}
        public = {(row["stage"], row["original_seed"], row["checkpoint_step"]): row for row in metrics if row.get("role") == "public"}
        rules = {(row["stage"], row["original_seed"], row["checkpoint_step"]): row["rules"] for row in records if row["kind"] == "rules"}
        indexed = {(row["stage"], row["original_seed"], row["checkpoint_step"], row["continuation_label"], row["horizon"], row["allocation"]): row for row in branches}
        assert len(indexed) == len(branches) == 259
        branch_rows = []
        for key, row in indexed.items():
            baseline, uniform = base[key[:3]], indexed[(*key[:-1], "U")]
            entry = {name: row[name] for name in ("stage", "id", "original_seed", "checkpoint_step", "continuation_label", "horizon", "allocation")}
            entry.update({field + "_pct": row[field] for field in FIELDS})
            entry.update({field + "_gain_pp": row[field] - baseline[field] for field in FIELDS})
            entry.update({field + "_vs_U_pp": row[field] - uniform[field] for field in FIELDS})
            entry["maximum_task_drop_pp"] = max(0, max(baseline[task] - row[task] for task in TASKS))
            branch_rows.append(entry)

        # Compare independent calculations with previously delivered tables.
        for stage, directory in analyses.items():
            recomputed = {(r["original_seed"], r["checkpoint_step"], r["continuation_label"], r["horizon"], r["allocation"]): r for r in branch_rows if r["stage"] == stage}
            for old in csv_rows(directory / "branch_metrics.csv"):
                key = (*[int(old[name]) for name in ("original_seed", "checkpoint_step", "continuation_label", "horizon")], old["allocation"])
                row = recomputed[key]
                for new, prior in (("macro_pct", "macro_success_pct"), ("macro_gain_pp", "gain_pp"), ("macro_vs_U_pp", "extra_gain_vs_U_pp"), ("maximum_task_drop_pp", "maximum_task_drop_pp")):
                    close(row[new], old[prior])
                for task in TASKS:
                    close(row[task + "_pct"], old[task + "_success_pct"])
                checked["branch_rows_reconciled"] += 1

        summaries, contexts, seed_effects = [], [], []
        for stage in ("E0", "E1", "E2"):
            stage_rows = [r for r in branch_rows if r["stage"] == stage]
            cohorts = {"independent_pretraining": stage_rows} if stage != "E0" else {
                "replication_1903_1905": [r for r in stage_rows if r["continuation_label"] >= 1903],
                "discovery_1901_1902": [r for r in stage_rows if r["continuation_label"] <= 1902],
                "combined_descriptive": stage_rows}
            for cohort, rows in cohorts.items():
                for horizon in sorted({r["horizon"] for r in rows}):
                    for allocation in sorted({r["allocation"] for r in rows}):
                        selected = [r for r in rows if r["horizon"] == horizon and r["allocation"] == allocation]
                        seeds = sorted({r["original_seed"] for r in selected})
                        per_seed = []
                        for seed in seeds:
                            sample = [r for r in selected if r["original_seed"] == seed]
                            numeric = {name: mean(r[name] for r in sample) for name in sample[0] if name.endswith(("_pct", "_pp"))}
                            per_seed.append({"stage": stage, "cohort": cohort, "horizon": horizon, "allocation": allocation,
                                             "original_seed": seed, **numeric})
                        seed_effects.extend(per_seed)
                        summaries.append({"stage": stage, "cohort": cohort, "horizon": horizon, "allocation": allocation,
                            "original_seeds": len(seeds), **{name: mean(r[name] for r in per_seed) for name in numeric},
                            "positive_original_seeds": sum(r["macro_vs_U_pp"] > 0 for r in per_seed),
                            "seed_min_pp": min(r["macro_vs_U_pp"] for r in per_seed), "seed_max_pp": max(r["macro_vs_U_pp"] for r in per_seed)})
            for seed, cp, horizon in sorted({(r["original_seed"], r["checkpoint_step"], r["horizon"]) for r in stage_rows}):
                for allocation in sorted({r["allocation"] for r in stage_rows}):
                    sample = [r for r in stage_rows if (r["original_seed"], r["checkpoint_step"], r["horizon"], r["allocation"]) == (seed, cp, horizon, allocation)]
                    contexts.append({"stage": stage, "seed": seed, "checkpoint": cp, "horizon": horizon, "allocation": allocation,
                                     **{name: mean(r[name] for r in sample) for name in sample[0] if name.endswith(("_pct", "_pp"))}})

        # Derive held-out rule scores independently from the episode-level scores.
        rule_rows, rule_summary = [], []
        for seed, cp in sorted({(r["original_seed"], r["checkpoint_step"]) for r in branches if r["stage"] == "E1"}):
            context_rules = rules[("E1", seed, cp)]
            current, earlier = public[("E1", seed, cp)], public[("E1", seed, 100000 if cp == 200000 else 200000)]
            lowest = min(current[task] for task in TASKS)
            worst = [task for task in TASKS if current[task] == lowest]
            assert context_rules["Failure"] == ("F_" + worst[0] if len(worst) == 1 else "U")
            gains = {task: current[task] - earlier[task] for task in TASKS}
            best_gain = max(gains.values())
            fastest = [task for task in TASKS if gains[task] == best_gain]
            assert context_rules["Progress"] == ("F_" + fastest[0] if best_gain > 0 and len(fastest) == 1 else "U")
            for horizon in (20000, 40000):
                def choose(pool):
                    scores = {name: mean(r["macro"] for r in pool if r["allocation"] == name) for name in ORDER}
                    return max(ORDER, key=scores.get)
                other_seeds = [r for r in branches if r["stage"] == "E1" and r["original_seed"] != seed and r["horizon"] == horizon]
                global_choice, time_choice = choose(other_seeds), choose([r for r in other_seeds if r["checkpoint_step"] == cp])
                for repeat in (2101, 2102, 2103):
                    other_repeats = [r for r in branches if (r["stage"], r["original_seed"], r["checkpoint_step"], r["horizon"]) == ("E1", seed, cp, horizon) and r["continuation_label"] != repeat]
                    choices = {"Uniform": "U", "Failure": context_rules["Failure"], "Progress": context_rules["Progress"],
                               "Fixed_DC": "F_DC", "LOSO_global_fixed": global_choice, "LOSO_time_fixed": time_choice,
                               "cross_repeat_diagnostic": choose(other_repeats)}
                    uniform = indexed[("E1", seed, cp, repeat, horizon, "U")]
                    for name, allocation in choices.items():
                        selected = indexed[("E1", seed, cp, repeat, horizon, allocation)]
                        rule_rows.append({"seed": seed, "checkpoint": cp, "horizon": horizon, "repeat": repeat,
                                          "rule": name, "choice": allocation, "macro_pct": selected["macro"],
                                          "gain_vs_U_pp": selected["macro"] - uniform["macro"]})
        raw_rule_index = {(r["seed"], r["checkpoint"], r["horizon"], r["repeat"], r["rule"]): r for r in rule_rows}
        for old in csv_rows(analyses["E1"] / "held_out_rule_results.csv"):
            row = raw_rule_index[(*[int(old[name]) for name in ("original_seed", "checkpoint_step", "horizon", "continuation_label")], old["rule"])]
            assert row["choice"] == old["choice"], (row, old)
            close(row["gain_vs_U_pp"], old["extra_gain_vs_U_pp"])
            checked["held_out_rule_rows_reconciled"] += 1
        for horizon in (20000, 40000):
            for rule in sorted({r["rule"] for r in rule_rows}):
                effects = {seed: mean(r["gain_vs_U_pp"] for r in rule_rows if r["seed"] == seed and r["horizon"] == horizon and r["rule"] == rule) for seed in (11, 12, 13)}
                rule_summary.append({"horizon": horizon, "rule": rule, "gain_vs_U_pp": mean(effects.values()),
                                     **{"seed_" + str(seed) + "_pp": value for seed, value in effects.items()}})

        baseline_rows = [{"stage": key[0], "seed": key[1], "checkpoint": key[2], **{field + "_pct": r[field] for field in FIELDS}} for key, r in sorted(base.items())]
        donor = [{"seed": seed, "horizon": horizon,
                  "DO_DCplus_minus_WOplus_pp": mean(indexed[("E2", seed, 200000, repeat, horizon, "DC_plus_WO_minus")]["DO"] - indexed[("E2", seed, 200000, repeat, horizon, "DC_minus_WO_plus")]["DO"] for repeat in (2201, 2202, 2203))}
                 for seed in (11, 12, 13) for horizon in (20000, 40000)]
        for name, data in (("branch_recomputed.csv", branch_rows), ("allocation_summary.csv", summaries),
                           ("context_results.csv", contexts), ("original_seed_effects.csv", seed_effects),
                           ("baseline_success.csv", baseline_rows), ("rule_choices.csv", rule_rows),
                           ("rule_summary.csv", rule_summary), ("donor_swap_DO.csv", donor)):
            save_csv(name, data)
        summary = {"observed_at": datetime.now(timezone.utc).isoformat(), "passed": True,
                   "output": str(output), "checks": dict(checked), "episode_count": sum(checked[s + "_evaluation_episodes"] for s in ("E0", "E1", "E2")),
                   "allocation_summary_40k": [r for r in summaries if r["horizon"] == 40000],
                   "E1_rules": rule_summary, "E2_DO_donor_contrast": donor, "baseline_success": baseline_rows,
                   "E0_diagnostic_rules": rules[("E0", 901, 200000)],
                   "analysis_wall_seconds": time.perf_counter() - started, "python": sys.version,
                   "dependencies": "Python standard library only", "new_training_steps": 0, "new_evaluation_episodes": 0,
                   "original_seeds": {"E0": [901], "E1": [11, 12, 13], "E2": [11, 12, 13]},
                   "scope": "Equal original-seed weights; checkpoints and continuation repeats nested. Cross-repeat choices use training branch outcomes and are retrospective diagnostics.",
                   "source_sha256": sha(output / "analysis_source.py")}
        (output / "analysis.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        (output / "input_hashes.json").write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"output": str(output), "passed": True, "checks": dict(checked), "wall_seconds": summary["analysis_wall_seconds"]}, indent=2))
    except BaseException as exc:
        (output / "failed_check.json").write_text(json.dumps({"error": str(exc), "traceback": traceback.format_exc(), "checks": dict(checked)}, indent=2) + "\n", encoding="utf-8")
        raise


if __name__ == "__main__":
    main()
