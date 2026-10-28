"""Pure-file analysis of the frozen twenty-path baseline (never imports RL code).

E50 endpoints and T20 six-time histories are separate estimands. All missing
paths remain NA; no incomplete-parent mean or effect-dependent progression.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import itertools
import json
import math
import platform
import shutil
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
PARENTS = tuple(range(41011, 41016))
TASKS = ("DO", "DC", "PU", "BP")
CONDITIONS = ("dose25", "dose625")
FUTURES = (1, 2)
STEPS = (4000, 8000, 16000, 32000)
TIMES = (-8000, 0, *STEPS)
METRICS = ("J", "G", "L", "delta", "recovery")
BOOTSTRAP_SEED = 640303


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, np.ndarray):
        return clean(value.tolist())
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(float(value)) else None
    return value


def write_json(path, value):
    Path(path).write_text(json.dumps(clean(value), ensure_ascii=False,
                                    indent=2, allow_nan=False) + "\n", encoding="utf-8")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path, rows, fields=None):
    rows = list(rows)
    if fields is None:
        fields = list(dict.fromkeys(k for row in rows for k in row))
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: "" if v is None else v for k, v in clean(row).items()})


class Audit:
    def __init__(self):
        self.count = 0
        self.failures = []

    def require(self, predicate, label):
        self.count += 1
        if not predicate:
            self.failures.append(label)
            raise ValueError(label)


class Receipt:
    """Short, content-addressed input copies avoid Windows long-path failures."""
    def __init__(self, run):
        self.run = run
        self.assets = []
        (run / "input_snapshot").mkdir()

    def add(self, path, role, expected=None):
        path = Path(path).resolve()
        digest = sha(path)
        if expected is not None and digest != expected:
            raise ValueError("Pinned input hash mismatch: " + str(path))
        target = self.run / "input_snapshot" / (digest + path.suffix.lower())
        if not target.exists():
            shutil.copy2(path, target)
        self.assets.append({"role": role, "path": str(path), "sha256": digest,
                            "snapshot": str(target.relative_to(self.run)), "bytes": path.stat().st_size})
        return path


def unique_run(label, parent=None):
    parent = Path(parent) if parent else ROOT / "results"
    run = parent / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
                    "_" + label + "_" + uuid.uuid4().hex[:8])
    run.mkdir(parents=True, exist_ok=False)
    return run


def source_snapshot(run):
    folder = run / "source_snapshot"
    folder.mkdir()
    values = {}
    sources = sorted(ROOT.glob("*.py")) + sorted((ROOT / "practice_allocation").glob("*.py"))
    sources += sorted((ROOT / "configs").glob("*.json"))
    sources += [p for p in (ROOT / "requirements.txt", ROOT / "VERSION.json") if p.exists()]
    for path in sources:
        rel = path.relative_to(ROOT)
        target = folder / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        values[str(rel)] = sha(path)
    write_json(run / "source_hashes.json", values)
    return values


def resolve_ref(ref, base):
    path = Path(ref["path"] if isinstance(ref, dict) else ref)
    if not path.is_absolute():
        path = (Path(base) / path).resolve()
    return path, ref.get("sha256") if isinstance(ref, dict) else None


def truth(value):
    return value is True or str(value).lower() in ("true", "1")


def case_membership(raw):
    answer = {}
    if isinstance(raw, list) or "rows" in raw:
        rows = raw if isinstance(raw, list) else raw["rows"]
        for row in rows:
            key = (int(row["parent"]), row["task"])
            answer.setdefault(key, {"E50": [], "T20": []})
            idx = int(row.get("episode_index", row.get("case_id")))
            for subset in ("E50", "T20"):
                if truth(row.get("in_" + subset, False)):
                    answer[key][subset].append(idx)
    else:
        for parent, entry in raw["parents"].items():
            for task, sets in entry["tasks"].items():
                answer[(int(parent), task)] = {s: list(map(int, sets[s])) for s in ("E50", "T20")}
    for sets in answer.values():
        for subset in sets:
            sets[subset].sort()
    return answer


def normalized_case(row, audit):
    required = ("task", "episode_index", "seed", "initial_state_hash", "success", "return", "length")
    audit.require(all(k in row for k in required), "Missing mandatory evaluation columns")
    success = int(row["success"])
    length = int(row["length"])
    reward = float(row["return"])
    audit.require(success in (0, 1) and 1 <= length <= 500 and math.isfinite(reward),
                  "Invalid binary success/length/return")
    audit.require(bool(row["initial_state_hash"]), "Empty initial-state identity")
    first = row.get("first_success_step")
    if first not in (None, "", "None"):
        audit.require(success == 1 and 1 <= int(first) <= length,
                      "First success inconsistent with evaluation outcome")
    return {**row, "episode_index": int(row["episode_index"]), "seed": int(row["seed"]),
            "success": success, "length": length, "return": reward}


def load_study(campaign, receipt, audit, allow_incomplete=False):
    campaign = Path(campaign).resolve()
    protocol_path = receipt.add(ROOT / "protocol.json", "protocol")
    baseline_path = receipt.add(ROOT / "inputs" / "baseline_rows.csv", "P_S_outcomes")
    cases_path = receipt.add(ROOT / "inputs" / "evaluation_cases.json", "evaluation_subsets")
    jobs_path = receipt.add(ROOT / "inputs" / "jobs.json", "frozen_jobs")
    states_path = receipt.add(ROOT / "inputs" / "state_manifest.json", "frozen_states")
    plan_path = receipt.add(campaign / "plan.json", "campaign_plan")
    protocol, plan = read_json(protocol_path), read_json(plan_path)
    for rel, digest in protocol.get("input_hashes", {}).items():
        receipt.add(ROOT / rel, "pinned_protocol_input", digest)
    cases = case_membership(read_json(cases_path))
    jobs = read_json(jobs_path)
    jobs = jobs["jobs"] if isinstance(jobs, dict) else jobs
    wanted = {(p, c, f) for p in PARENTS for c in CONDITIONS for f in FUTURES}
    actual = {(int(j["parent"]), j["condition"], int(j["future"])) for j in jobs}
    audit.require(len(jobs) == 20 and actual == wanted, "Frozen twenty-job design changed")
    audit.require(len({j["id"] for j in jobs}) == 20, "Duplicate frozen job identifiers")
    plan_jobs = plan.get("jobs", jobs)
    audit.require({j["id"] for j in plan_jobs} == {j["id"] for j in jobs}, "Campaign/frozen job set mismatch")
    for parent in PARENTS:
        for future in FUTURES:
            pair = [j for j in jobs if int(j["parent"]) == parent and int(j["future"]) == future]
            expected_seed = int(np.random.SeedSequence([640202, 64, parent, 4201, future]).generate_state(1)[0])
            audit.require(all(int(j["root_seed"]) == expected_seed for j in pair), "Future seed mapping changed")
            expected_schedule = int(np.random.SeedSequence([expected_seed, 10]).generate_state(1)[0])
            audit.require(all(int(j["schedule_seed"]) == expected_schedule for j in pair), "Schedule seed mapping changed")
            audit.require(len({int(j["schedule_seed"]) for j in pair}) == 1, "Paired schedule seed mismatch")
        for task in TASKS:
            sets = cases[(parent, task)]
            audit.require(len(sets["E50"]) == len(set(sets["E50"])) == 50, "E50 not fifty unique cases")
            audit.require(len(sets["T20"]) == len(set(sets["T20"])) == 20,
                          "T20 not twenty unique cases")
            audit.require(set(sets["T20"]) <= set(sets["E50"]), "T20 is not nested in E50")
    baseline = {}
    for raw in read_csv(baseline_path):
        row = normalized_case(raw, audit)
        parent, stage, task, idx = int(row["parent"]), row["stage"], row["task"], row["episode_index"]
        audit.require(parent in PARENTS and stage in ("P", "S") and task in TASKS,
                      "Unexpected baseline identity")
        key = (parent, stage, task, idx)
        audit.require(key not in baseline and idx in cases[(parent, task)]["E50"],
                      "Duplicate/non-E50 baseline case")
        baseline[key] = row
    audit.require(len(baseline) == 2000, "P/S E50 coverage is not 2000 rows")
    for parent, task in itertools.product(PARENTS, TASKS):
        for idx in cases[(parent, task)]["E50"]:
            a, b = baseline[(parent, "P", task, idx)], baseline[(parent, "S", task, idx)]
            audit.require((a["seed"], a["initial_state_hash"]) == (b["seed"], b["initial_state_hash"]),
                          "P/S evaluation case pairing mismatch")
    rows, outcomes, statuses, ledger = [], {}, [], []
    for job in jobs:
        marker = campaign / "completed" / (job["id"] + ".json")
        if not marker.exists():
            statuses.append({**job, "execution_status": "missing_or_failed", "analysis_status": "NA"})
            continue
        receipt.add(marker, "completed_marker")
        result_path, expected = resolve_ref(read_json(marker), marker.parent)
        receipt.add(result_path, "worker_result", expected)
        result = read_json(result_path)
        audit.require(result["status"] == "completed", "Completion marker points to a failed worker")
        audit.require(all(result[k] == job[k] for k in ("id", "parent", "condition", "future")),
                      "Worker/frozen job identity mismatch")
        episode_path, expected = resolve_ref(result["episodes"], result_path.parent)
        receipt.add(episode_path, "research_evaluation", expected)
        worker_rows = read_csv(episode_path)
        audit.require(len(worker_rows) == 440, "Completed worker has wrong evaluation coverage")
        seen = set()
        for raw in worker_rows:
            row = normalized_case(raw, audit)
            parent, condition, future = int(row["parent"]), row["condition"], int(row["future"])
            step, task, idx = int(row["relative_step"]), row["task"], row["episode_index"]
            audit.require((parent, condition, future) == (job["parent"], job["condition"], job["future"]),
                          "Evaluation/frozen job identity mismatch")
            audit.require(row["id"] == job["id"] and step in STEPS and task in TASKS,
                          "Unexpected checkpoint/case job")
            subset = "E50" if step == 32000 else "T20"
            audit.require(idx in cases[(parent, task)][subset], "Evaluated case outside frozen subset")
            ref = baseline[(parent, "S", task, idx)]
            audit.require((row["seed"], row["initial_state_hash"]) == (ref["seed"], ref["initial_state_hash"]),
                          "Research/S case identity mismatch")
            key = (parent, condition, future, step, task, idx)
            audit.require(key not in seen and key not in outcomes, "Duplicate research outcome")
            seen.add(key)
            outcomes[key] = row
            rows.append(row)
        expected_keys = {(job["parent"], job["condition"], job["future"], step, task, idx)
                         for step, task in itertools.product(STEPS, TASKS)
                         for idx in cases[(job["parent"], task)]["E50" if step == 32000 else "T20"]}
        audit.require(seen == expected_keys, "Completed worker checkpoint coverage incomplete")
        cost_path = result_path.parent / "costs.json"
        receipt.add(cost_path, "worker_cost")
        cost = read_json(cost_path)
        evaluated = sum(row["length"] for row in worker_rows)
        audit.require(result["training_steps"] == cost["training_steps"] == 32000,
                      "Completed training cost is not 32000")
        audit.require(result["evaluation_steps"] == cost["evaluation_steps"] == evaluated,
                      "Evaluation cost differs from actual CSV episode lengths")
        audit.require(cost["costs"]["environment_steps"] == 32000 + evaluated,
                      "Worker physical cost does not reconcile")
        ledger.append({"id": job["id"], "status": "completed", "path": str(cost_path),
                       "training_steps": 32000, "evaluation_steps": evaluated,
                       "environment_steps": 32000 + evaluated})
        for cp in result["checkpoints"]:
            ref = Path(cp["path"]) / "checkpoint_manifest.json"
            receipt.add(ref, "new_checkpoint_manifest", cp["manifest_sha256"])
            manifest = read_json(ref)
            audit.require(manifest["step"] == 208000 + int(cp["relative_step"]), "Checkpoint absolute step mismatch")
        audit.require({int(cp["relative_step"]) for cp in result["checkpoints"]} == set(STEPS),
                      "Four immutable checkpoints not retained")
        statuses.append({**job, "execution_status": "completed", "analysis_status": "included",
                         "result_path": str(result_path), "telemetry_directory": result.get("telemetry_directory", str(result_path.parent))})
    complete = len(rows) == 8800 and len(ledger) == 20
    audit.require(allow_incomplete or complete, "Campaign incomplete: use --allow-incomplete to record explicit NA")
    # Preserve failed attempts too; never replace their actual cost with a planned 32k.
    known_costs = {item["path"] for item in ledger}
    for path in sorted(campaign.rglob("costs.json")):
        if str(path.resolve()) in known_costs:
            continue
        receipt.add(path, "other_attempt_cost")
        item = read_json(path)
        if "training_steps" in item and "evaluation_steps" in item:
            ledger.append({"id": path.parent.name, "status": item.get("status", "unknown"),
                           "path": str(path), "training_steps": int(item["training_steps"]),
                           "evaluation_steps": int(item["evaluation_steps"]),
                           "environment_steps": int(item["training_steps"]) + int(item["evaluation_steps"])})
    technical_ledger = []
    for record in plan.get("technical_costs", []):
        ref = record["reference"]
        path, digest = resolve_ref(ref, campaign)
        receipt.add(path, "technical_attempt_cost", digest)
        value = read_json(path)
        technical_ledger.append({"path": str(path), "status": value.get("status", "recorded"),
                                 "environment_steps": int(value["costs"]["environment_steps"])})
    technical_total = sum(r["environment_steps"] for r in technical_ledger)
    audit.require(technical_total == int(plan.get("technical_steps", technical_total)), "Technical attempt costs do not reconcile")
    return {"protocol": protocol, "plan": plan, "cases": cases, "baseline": baseline,
            "outcomes": outcomes, "rows": rows, "jobs": jobs, "statuses": statuses,
            "ledger": ledger, "technical_ledger": technical_ledger,
            "technical_steps": technical_total, "complete": complete, "campaign": str(campaign)}


def endpoint_vectors(p, s, y):
    return np.stack((y, (1-s)*y, s*(1-y), y-s, p*(1-s)*y), axis=-1).astype(float)


def trajectory_features(values):
    """Ordered six observed labels; does not infer transitions between checkpoints."""
    values = list(map(int, values))
    gains = [i for i in range(1, 6) if values[i-1] == 0 and values[i] == 1]
    losses = [i for i in range(1, 6) if values[i-1] == 1 and values[i] == 0]
    recoveries = [i for i in gains if any(values[:i-1])]
    late_losses = [i for i in losses if i >= 2]
    late_recoveries = [i for i in recoveries if i >= 2]
    return {"pattern": "".join(map(str, values)), "gain_transitions": len(gains),
            "loss_transitions": len(losses), "recovery_transitions": len(recoveries),
            "ever_loss": int(bool(losses)), "repeated_loss": int(len(losses) >= 2),
            "loss_then_recovery": int(bool(recoveries)),
            "late_loss_transitions": len(late_losses), "late_recovery_transitions": len(late_recoveries),
            "first_observed_loss_end": TIMES[losses[0]] if losses else None,
            "first_observed_late_loss_start": TIMES[late_losses[0]-1] if late_losses else None,
            "first_observed_late_loss_end": TIMES[late_losses[0]] if late_losses else None}


def arrays_for(study):
    p = np.empty((5, 4, 50), dtype=float)
    s = np.empty_like(p)
    y = np.full((5, 4, 2, 2, 50), np.nan)
    histories = np.full((5, 4, 2, 2, 20, 6), np.nan)
    for pi, parent in enumerate(PARENTS):
        for ti, task in enumerate(TASKS):
            e50 = study["cases"][(parent, task)]["E50"]
            t20 = study["cases"][(parent, task)]["T20"]
            for i, idx in enumerate(e50):
                p[pi, ti, i] = study["baseline"][(parent, "P", task, idx)]["success"]
                s[pi, ti, i] = study["baseline"][(parent, "S", task, idx)]["success"]
            for ci, condition in enumerate(CONDITIONS):
                for fi, future in enumerate(FUTURES):
                    for i, idx in enumerate(e50):
                        row = study["outcomes"].get((parent, condition, future, 32000, task, idx))
                        if row:
                            y[pi, ti, ci, fi, i] = row["success"]
                    for i, idx in enumerate(t20):
                        histories[pi, ti, ci, fi, i, :2] = [study["baseline"][(parent, stage, task, idx)]["success"] for stage in ("P", "S")]
                        for k, step in enumerate(STEPS, 2):
                            row = study["outcomes"].get((parent, condition, future, step, task, idx))
                            if row:
                                histories[pi, ti, ci, fi, i, k] = row["success"]
    return p, s, y, histories


def build_tables(study, audit):
    p, s, y, histories = arrays_for(study)
    values = endpoint_vectors(p[:, :, None, None, :], s[:, :, None, None, :], y)
    point = values.mean(axis=4) * 100
    endpoint_rows, groups, cases, transitions, features, patterns = [], [], [], [], [], []
    for pi, parent in enumerate(PARENTS):
        for ti, task in enumerate(TASKS):
            for ci, condition in enumerate(CONDITIONS):
                for fi, future in enumerate(FUTURES):
                    meta = {"parent": parent, "prefix": 4201, "task": task, "condition": condition, "future": future}
                    good = np.isfinite(y[pi, ti, ci, fi]).all()
                    v = point[pi, ti, ci, fi]
                    endpoint_rows.append({**meta, "N": 50, "status": "complete" if good else "NA_incomplete",
                                          "J_P": p[pi, ti].mean()*100, "J_S": s[pi, ti].mean()*100,
                                          **dict(zip(METRICS, v))})
                    if good:
                        audit.require(abs(v[3] - v[1] + v[2]) < 1e-12, "Delta=G-L endpoint identity failed")
                    for group in ("00", "01", "10", "11"):
                        mask = (p[pi, ti] == int(group[0])) & (s[pi, ti] == int(group[1]))
                        n = int(mask.sum())
                        successes = int(y[pi, ti, ci, fi, mask].sum()) if good else None
                        losses = n-successes if successes is not None else None
                        groups.append({**meta, "P_S_group": group, "N": n, "final_success_count": successes,
                                       "final_success_rate_percent": successes/n*100 if n and good else None,
                                       "conditional_gain_percent": successes/n*100 if n and good and group[1] == "0" else None,
                                       "conditional_loss_percent": losses/n*100 if n and good and group[1] == "1" else None,
                                       "conditional_recovery_percent": successes/n*100 if n and good and group == "10" else None,
                                       "zero_support": n == 0, "execution_complete": good})
                    for i, idx in enumerate(study["cases"][(parent, task)]["E50"]):
                        outcome = y[pi, ti, ci, fi, i]
                        cases.append({**meta, "episode_index": idx, "P": int(p[pi, ti, i]),
                                      "S": int(s[pi, ti, i]), "Y32": outcome,
                                      "G": (1-s[pi, ti, i])*outcome, "L": s[pi, ti, i]*(1-outcome),
                                      "recovery": p[pi, ti, i]*(1-s[pi, ti, i])*outcome,
                                      "delta": outcome-s[pi, ti, i]})
                    h = histories[pi, ti, ci, fi]
                    for i, idx in enumerate(study["cases"][(parent, task)]["T20"]):
                        observed = h[i]
                        row = {**meta, "episode_index": idx, **dict(zip(("P", "S", "Y4", "Y8", "Y16", "Y32"), observed))}
                        row.update(trajectory_features(observed) if np.isfinite(observed).all() else
                                   {"pattern": None, "execution_status": "NA_incomplete"})
                        features.append(row)
                    for k in range(1, 6):
                        a, b = h[:, k-1], h[:, k]
                        valid = np.isfinite(h).all()
                        n_gain = int(((a == 0) & (b == 1)).sum()) if valid else None
                        n_loss = int(((a == 1) & (b == 0)).sum()) if valid else None
                        n_failed = int((a == 0).sum()) if valid else None
                        n_successful = int((a == 1).sum()) if valid else None
                        transitions.append({**meta, "window_start": TIMES[k-1], "window_end": TIMES[k],
                                            "N": 20, "gain_count": n_gain, "loss_count": n_loss,
                                            "G": n_gain/20*100 if valid else None, "L": n_loss/20*100 if valid else None,
                                            "delta": float((b-a).mean()*100) if valid else None,
                                            "risk_gain_N": n_failed, "risk_loss_N": n_successful,
                                            "conditional_gain_percent": n_gain/n_failed*100 if n_failed else None,
                                            "conditional_loss_percent": n_loss/n_successful*100 if n_successful else None})
                    if np.isfinite(h).all():
                        codes = ["".join(map(str, row.astype(int))) for row in h]
                        patterns.extend({**meta, "pattern": format(code, "06b"), "count": codes.count(format(code, "06b")),
                                         "N": 20} for code in range(64))
                    else:
                        patterns.extend({**meta, "pattern": format(code, "06b"), "count": None, "N": 20} for code in range(64))
    parent_rows, contrast_rows, task_rows = [], [], []
    parents_point = point.mean(axis=(1, 3))
    for pi, parent in enumerate(PARENTS):
        for ci, condition in enumerate(CONDITIONS):
            parent_rows.append({"parent": parent, "condition": condition,
                                **dict(zip(METRICS, parents_point[pi, ci]))})
        for fi, future in enumerate(FUTURES):
            diff = (point[pi, :, 1, fi] - point[pi, :, 0, fi]).mean(axis=0)
            contrast_rows.append({"parent": parent, "future": future, "contrast": "dose625_minus_dose25",
                                  **dict(zip(METRICS, diff))})
    for ti, task in enumerate(TASKS):
        for ci, condition in enumerate(CONDITIONS):
            avg = point[:, ti, ci].mean(axis=(0, 1))
            task_rows.append({"task": task, "condition": condition, **dict(zip(METRICS, avg)),
                              **{k+"_macro_contribution": v/4 for k, v in zip(METRICS, avg)}})
    stop_parent = s.mean(axis=(1, 2))*100
    stop_task = s.mean(axis=(0, 2))*100
    parent_rows.extend({"parent": parent, "condition": "STOP", "J": stop_parent[pi],
                        "G": 0, "L": 0, "delta": 0, "recovery": 0} for pi, parent in enumerate(PARENTS))
    task_rows.extend({"task": task, "condition": "STOP", "J": stop_task[ti], "J_macro_contribution": stop_task[ti]/4,
                      "G": 0, "L": 0, "delta": 0, "recovery": 0} for ti, task in enumerate(TASKS))
    overall = {condition: dict(zip(METRICS, parents_point[:, ci].mean(axis=0))) for ci, condition in enumerate(CONDITIONS)}
    overall["STOP"] = {"J": float(stop_parent.mean()), "G": 0, "L": 0, "delta": 0, "recovery": 0}
    contrast = dict(zip(METRICS, (parents_point[:, 1]-parents_point[:, 0]).mean(axis=0)))
    lopo = [{"excluded_parent": parent, "contrast": "dose625_minus_dose25",
             **dict(zip(METRICS, np.delete(parents_point[:, 1]-parents_point[:, 0], pi, axis=0).mean(axis=0)))}
            for pi, parent in enumerate(PARENTS)]
    future_results = [{"future": future, "condition": condition,
                       **dict(zip(METRICS, point[:, :, ci, fi].mean(axis=(0, 1))))}
                      for ci, condition in enumerate(CONDITIONS) for fi, future in enumerate(FUTURES)]
    tables = {"e50_metrics.csv": endpoint_rows, "e50_groups.csv": groups, "e50_case_outcomes.csv": cases,
              "parent_results.csv": parent_rows, "paired_condition_contrasts.csv": contrast_rows,
              "task_contributions.csv": task_rows, "leave_one_parent_out.csv": lopo,
              "future_results.csv": future_results, "t20_case_trajectories.csv": features,
              "t20_interval_transitions.csv": transitions, "t20_six_label_patterns.csv": patterns}
    return tables, {"conditions": overall, "paired_BP_minus_uniform": contrast,
                    "J_P": float(p.mean()*100), "J_S": float(s.mean()*100)}, (p, s, y, histories)


def paired_bootstrap(arrays, draws, seed, run, audit):
    p, s, y, histories = arrays
    rng = np.random.default_rng(seed)
    end_counts = np.empty((5, 4, draws, 50), dtype=np.uint8)
    path_counts = np.empty((5, 4, draws, 20), dtype=np.uint8)
    endpoint = np.zeros((draws, 2, len(METRICS)))
    by_future = np.zeros((draws, 2, 2, len(METRICS)))
    by_task = np.zeros((draws, 4, 2, len(METRICS)))
    stop = np.zeros(draws)
    path_metrics = ("late_loss_transitions", "late_recovery_transitions", "ever_loss", "repeated_loss", "loss_then_recovery")
    paths = np.zeros((draws, 2, len(path_metrics)))
    for pi, ti in itertools.product(range(5), range(4)):
        count = rng.multinomial(50, np.full(50, 1/50), size=draws).astype(np.uint8)
        path_count = rng.multinomial(20, np.full(20, 1/20), size=draws).astype(np.uint8)
        end_counts[pi, ti], path_counts[pi, ti] = count, path_count
        audit.require(np.all(count.sum(axis=1) == 50) and np.all(path_count.sum(axis=1) == 20),
                      "Bootstrap case counts changed")
        stop += count @ s[pi, ti] / 50 * (100/20)
        for ci, fi in itertools.product(range(2), range(2)):
            vec = endpoint_vectors(p[pi, ti], s[pi, ti], y[pi, ti, ci, fi])
            sampled = count @ vec / 50 * 100
            endpoint[:, ci] += sampled / 40
            by_future[:, ci, fi] += sampled / 20
            by_task[:, ti, ci] += sampled / 10
            fv = np.array([[trajectory_features(h)[name] for name in path_metrics]
                           for h in histories[pi, ti, ci, fi]], dtype=float)
            paths[:, ci] += (path_count @ fv / 20 * 100) / 40
    paired = endpoint[:, 1] - endpoint[:, 0]
    audit.require(np.allclose(paired[:, 3], paired[:, 1]-paired[:, 2], atol=1e-12),
                  "Paired bootstrap DeltaG-DeltaL identity failed")
    np.savez_compressed(run / "case_resample_counts.npz", E50=end_counts, T20=path_counts)
    np.savez_compressed(run / "bootstrap_draws.npz", endpoint=endpoint, paired=paired,
                        future=by_future, task=by_task, STOP_J=stop, trajectory=paths)
    rows = []
    for ci, condition in enumerate(CONDITIONS):
        for mi, metric in enumerate(METRICS):
            lo, hi = np.quantile(endpoint[:, ci, mi], [.025, .975], method="linear")
            rows.append({"scope": "E50", "condition": condition, "metric": metric, "lower": lo, "upper": hi})
    for mi, metric in enumerate(METRICS):
        lo, hi = np.quantile(paired[:, mi], [.025, .975], method="linear")
        rows.append({"scope": "E50", "condition": "dose625_minus_dose25", "metric": metric, "lower": lo, "upper": hi})
    lo, hi = np.quantile(stop, [.025, .975], method="linear")
    rows.append({"scope": "E50", "condition": "STOP", "metric": "J", "lower": lo, "upper": hi})
    for ci, condition in enumerate(CONDITIONS):
        for mi, metric in enumerate(path_metrics):
            lo, hi = np.quantile(paths[:, ci, mi], [.025, .975], method="linear")
            rows.append({"scope": "T20", "condition": condition, "metric": metric, "lower": lo, "upper": hi})
    for mi, metric in enumerate(path_metrics):
        lo, hi = np.quantile(paths[:, 1, mi]-paths[:, 0, mi], [.025, .975], method="linear")
        rows.append({"scope": "T20", "condition": "dose625_minus_dose25", "metric": metric, "lower": lo, "upper": hi})
    return rows


def flatten_numbers(obj, prefix=""):
    answer = {}
    if isinstance(obj, dict):
        for key, value in obj.items():
            answer.update(flatten_numbers(value, prefix+"."+str(key) if prefix else str(key)))
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool) and math.isfinite(float(obj)):
        answer[prefix] = obj
    return answer


def exploratory_telemetry(study, receipt, interval_rows):
    """Time-aligned descriptive tables, never fit a predictor or select a signal."""
    windows, probes, episodes, aligned, availability = [], [], [], [], []
    interval_lookup = {(int(r["parent"]), r["condition"], int(r["future"]), r["task"], r["window_end"]): r
                       for r in interval_rows if r["window_start"] >= 0}
    quantities = ("q_replay_0", "q_replay_1", "target", "q_actor_min", "reward",
                  "td_abs_0", "td_abs_1", "td_signed_0", "td_signed_1", "actor_objective")
    def records(path):
        with path.open(encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]
    def mean_stat(obj):
        return obj.get("mean") if isinstance(obj, dict) else None
    for status in study["statuses"]:
        if status["execution_status"] != "completed":
            continue
        folder = Path(status["telemetry_directory"])
        source = {}
        meta = {key: status[key] for key in ("id", "parent", "condition", "future")}
        for name, kind in (("windows_250.jsonl", "training_window"),
                           ("policy_drift_1000.jsonl", "training_only_fixed_panel"),
                           ("training_episodes.jsonl", "training_episode")):
            path = folder / name
            if not path.exists():
                availability.append({**meta, "kind": kind, "status": "unavailable", "source": str(path)})
                source[kind] = []
                continue
            receipt.add(path, "exploratory_training_telemetry")
            source[kind] = records(path)
            availability.append({**meta, "kind": kind, "status": "recorded", "rows": len(source[kind]), "source": str(path)})
        local_windows, local_probes, local_episodes = [], [], []
        for obj in source["training_window"]:
            start, end = int(obj["relative_start"]), int(obj["relative_end"])
            for task in TASKS:
                sampled = obj.get("sampled_replay", {}).get("by_task", {}).get(task, {})
                buffer = obj.get("buffer_snapshot", {}).get("by_task", {}).get(task, {})
                row = {**meta, "task": task, "window_start": start, "window_end": end,
                       "sampled_n": sampled.get("n", 0), "sampled_total_n": obj.get("sampled_replay", {}).get("n", 0),
                       "sampled_fraction": sampled.get("fraction"), "sampled_age_mean": mean_stat(sampled.get("age_stats")),
                       "sampled_new_fraction": sampled.get("new_fraction"),
                       "sampled_known_fraction": sampled.get("known_fraction"),
                       "sampled_successful_fraction_known": sampled.get("successful_fraction_known"),
                       "buffer_fraction": buffer.get("fraction"), "buffer_new_fraction": buffer.get("new_fraction"),
                       "buffer_known_fraction": buffer.get("known_fraction"),
                       "alpha_mean": mean_stat(obj.get("learning_metrics", {}).get("alpha_used_in_this_update"))}
                for quantity in quantities:
                    stat = obj.get("sac_by_task", {}).get(task, {}).get(quantity, {})
                    row[quantity+"_mean"] = stat.get("mean")
                    row[quantity+"_n"] = stat.get("n", 0)
                windows.append(row); local_windows.append(row)
        for obj in source["training_only_fixed_panel"]:
            for task in TASKS:
                item = obj.get("by_task", {}).get(task, {})
                row = {**meta, "task": task, "relative_step": int(obj["relative_step"]), "alpha": obj.get("alpha")}
                for name in ("gaussian_entropy_unsquashed", "squashed_entropy_mc_tanh_exact", "squashed_entropy_mc_sb3_epsilon",
                             "kl_frozen_to_current", "kl_current_to_frozen", "kl_previous_to_current", "kl_current_to_previous",
                             "mu_mse_to_frozen", "mu_mse_to_previous", "std_mse_to_frozen", "std_mse_to_previous"):
                    row[name] = mean_stat(item.get(name))
                probes.append(row); local_probes.append(row)
        for obj in source["training_episode"]:
            row = {**meta, **{key: obj.get(key) for key in ("task", "relative_start", "relative_end", "success", "return", "length",
                   "first_success_within_episode", "policy_version_first_success", "policy_version_first_action", "policy_version_last_action")}}
            episodes.append(row); local_episodes.append(row)
        def weighted(items, value_key, count_key):
            valid = [(float(r[value_key]), int(r[count_key])) for r in items
                     if r.get(value_key) is not None and int(r.get(count_key, 0)) > 0]
            return sum(v*n for v,n in valid)/sum(n for _,n in valid) if valid else None
        for task in TASKS:
            for start, end in zip((0, *STEPS[:-1]), STEPS):
                ew = [r for r in local_windows if r["task"] == task and start < r["window_end"] <= end]
                ep = [r for r in local_episodes if r["task"] == task and start < int(r["relative_end"]) <= end]
                pr = [r for r in local_probes if r["task"] == task and start < r["relative_step"] <= end]
                last_probe = next((r for r in pr if r["relative_step"] == end), {})
                total_sampled = sum(int(r["sampled_total_n"]) for r in ew)
                task_sampled = sum(int(r["sampled_n"]) for r in ew)
                observed = interval_lookup[(int(status["parent"]), status["condition"], int(status["future"]), task, end)]
                row = {**meta, "task": task, "window_start": start, "window_end": end,
                       "evaluation_N": 20, "observed_gain_count": observed["gain_count"], "observed_loss_count": observed["loss_count"],
                       "evaluation_delta_pp": observed["delta"], "sampled_task_n": task_sampled,
                       "sampled_task_fraction": task_sampled/total_sampled if total_sampled else None,
                       "sampled_age_mean": weighted(ew, "sampled_age_mean", "sampled_n"),
                       "sampled_new_fraction": weighted(ew, "sampled_new_fraction", "sampled_n"),
                       "sampled_known_fraction": weighted(ew, "sampled_known_fraction", "sampled_n"),
                       "training_episodes": len(ep), "training_success_rate": sum(int(r["success"]) for r in ep)/len(ep) if ep else None,
                       "training_return_mean": sum(float(r["return"]) for r in ep)/len(ep) if ep else None,
                       "endpoint_alpha": last_probe.get("alpha"),
                       "endpoint_KL_frozen_to_current": last_probe.get("kl_frozen_to_current"),
                       "endpoint_KL_current_to_frozen": last_probe.get("kl_current_to_frozen"),
                       "endpoint_squashed_entropy": last_probe.get("squashed_entropy_mc_tanh_exact"),
                       "endpoint_gaussian_entropy": last_probe.get("gaussian_entropy_unsquashed")}
                prior = [r["kl_previous_to_current"] for r in pr if r.get("kl_previous_to_current") is not None]
                row["mean_1k_probe_KL_previous_to_current"] = sum(prior)/len(prior) if prior else None
                for quantity in quantities:
                    row[quantity+"_mean"] = weighted(ew, quantity+"_mean", quantity+"_n")
                aligned.append(row)
    pairs = []
    numeric = ("observed_gain_count", "observed_loss_count", "evaluation_delta_pp", "sampled_task_fraction",
               "sampled_age_mean", "sampled_new_fraction", "training_success_rate", "training_return_mean",
               "endpoint_KL_frozen_to_current", "endpoint_KL_current_to_frozen", "endpoint_squashed_entropy",
               "mean_1k_probe_KL_previous_to_current", *(q+"_mean" for q in quantities))
    lookup = {(r["parent"], r["condition"], r["future"], r["task"], r["window_end"]): r for r in aligned}
    for parent, task, end in itertools.product(PARENTS, TASKS, STEPS):
        row = {"parent": parent, "task": task, "window_end": end, "contrast": "dose625_minus_dose25_two_future_mean"}
        for quantity in numeric:
            values = [lookup.get((parent, c, f, task, end), {}).get(quantity) for c in CONDITIONS for f in FUTURES]
            row[quantity] = (values[2]+values[3]-values[0]-values[1])/2 if all(v is not None for v in values) else None
        pairs.append(row)
    return {"telemetry_availability.csv": availability, "telemetry_250_task_windows.csv": windows,
            "policy_drift_1000_by_task.csv": probes, "training_episode_summaries.csv": episodes,
            "exploratory_evaluation_aligned.csv": aligned, "exploratory_paired_condition_differences.csv": pairs}


def report(run, summary, tables, telemetry):
    def number(value, places=3):
        return "NA" if value is None or not math.isfinite(float(value)) else f"{float(value):.{places}f}"
    def table(rows, columns):
        lines = ["| "+" | ".join(label for _,label in columns)+" |",
                 "|"+"|".join("---" for _ in columns)+"|"]
        for row in rows:
            lines.append("| "+" | ".join(number(row.get(key)) if isinstance(row.get(key),(float,np.floating)) else
                                         str(row.get(key)) if row.get(key) is not None else "NA" for key,_ in columns)+" |")
        return "\n".join(lines)
    lines = ["# 같은8k 상태 이후 성공 획득·상실·회복 기준선", "",
             f"실행 완료 {summary['completed_jobs']}/20. 이번 분석은 기존 파일만 읽었으며 새 환경 step·SAC update는0이다.",
             "실행 상태와 과학적 해석은 별개다. 이 기준선에는 효과 방향에 따른 진행 관문이 없다.", "",
             "부모5개·prefix4201의 동일208k 전체 상태에서 UNIFORM/BP625와 짝지은 미래2개를 비교했다. "
             "부모 안에서 두 미래를 평균하고, 과제4개 및 부모5개에 동일 가중했다.", "",
             "## 종료 E50 결과", "",
             f"부모 P 평균 {number(summary['primary']['J_P'])}%, 출발 S 평균 {number(summary['primary']['J_S'])}%.", "",
             "G는S실패→종료성공, L은S성공→종료실패의 전체 E50사례 대비%p다. 회복은P성공/S실패/종료성공으로G의 일부다.", ""]
    overall = [{"condition": condition, **value} for condition,value in summary["primary"]["conditions"].items()]
    lines += [table(overall, [("condition","조건"),("J","최종 J %"),("G","획득 %p"),("L","상실 %p"),("delta","S대비 순변화 %p"),("recovery","회복 %p")]), "",
              "STOP은S정책을 그대로 보존한 참고점이다. 상실을 피하면서 신규 획득·회복도 포기하며, 학습 예산이 동일한 방법은 아니다.", "",
              "BP625−UNIFORM의 짝지은 평균 차이:", "",
              table([summary["primary"]["paired_BP_minus_uniform"]], [("J","ΔJ %p"),("G","ΔG %p"),("L","ΔL %p"),("delta","순변화 차이 %p")]), "",
              "각 경로와 모든 사례 재표집에서 ΔJ=ΔG−ΔL을 확인했다. 상실 감소만을 순개선으로 바꾸어 해석하지 않는다.", "",
              "## 조건부 사례 불확실성", "",
              "E50와T20를 별도로20,000회 재표집했다. 같은 부모·과제의 사례 multiplicity를 P/S·모든조건·두미래에 공유했다. "
              "개별95% percentile구간이며 다중 비교 동시구간이나 새 부모·새 학습 미래 전체의 불확실성이 아니다.", ""]
    intervals = [r for r in summary["case_intervals"] if r["scope"] == "E50"]
    lines += [table(intervals, [("condition","조건/대조"),("metric","지표"),("lower","하한"),("upper","상한")]) if intervals else
              "미완료 경로가 있어 전체 구간을 계산하지 않았다. 누락된 부모·미래를 제외한 유리한 평균은 만들지 않았다.", "",
              "## 부모·과제·미래별 범위", "",
              table(tables["parent_results.csv"], [("parent","부모"),("condition","조건"),("J","J %"),("G","G %p"),("L","L %p"),("delta","순변화 %p")]), "",
              table(tables["task_contributions.csv"], [("task","과제"),("condition","조건"),("J","J %"),("G","G %p"),("L","L %p")]), "",
              table(tables["future_results.csv"], [("future","미래"),("condition","조건"),("J","J %"),("G","G %p"),("L","L %p")]), "",
              "부모 하나씩 제외한 다섯 짝지은 차이는 leave_one_parent_out.csv에 모두 남겼다. 독립 부모는5개이며20경로나평가사례를독립부모로세지않는다.", "",
              "## 성공 이력과 중간 T20", "",
              "P/S의00·01·10·11을나눠 지원사례수와조건부획득·상실·회복률을e50_groups.csv에기록했다. "
              "지원0의위험은NA이며집단간조건부위험차이를인과효과로계산하지않았다.", "",
              "T20만P/S/+4/+8/+16/+32k의6시점이력으로연결했다. 64개이진패턴·재상실·재획득·최초관측상실구간을모두보존했다. "
              "이는관측checkpoint사이의전이이며정확한발생시점이나사이의추가반전을알려주지않는다. E50의나머지30사례중간값은대입하지않았다.", "",
              "## 기존 학습 로그의 세 탐색 질문", "",
              "①노출·경험나이·새경험비중과상실,②고정training-panel정책변화와상실,③reward/Q/TD와성공을 "
              "같은4개평가구간에정렬했다. exploratory_evaluation_aligned.csv와미래2개평균후조건차이표에모든부모·과제·구간을남겼다.", "",
              f"250step과제별계측행 {len(telemetry['telemetry_250_task_windows.csv'])}개, 1k정책probe과제행 {len(telemetry['policy_drift_1000_by_task.csv'])}개, "
              f"학습episode행 {len(telemetry['training_episode_summaries.csv'])}개. 계측누락은telemetry_availability.csv에명시했다.", "",
              "이표는동시관측의탐색자료다. 변화하는학습정책의성공과checkpoint의결정론적평가성공은다르다. "
              "Gaussian KL과tanh이후정책엔트로피도구분했다. 예측기·유리한신호·임계값을적합하지않았으며인과기전을판정하지않는다.", "",
              "## 비용과 한계", "",
              f"연구시도 학습 {summary['costs_all_research_attempts']['training_steps']:,}, 평가 {summary['costs_all_research_attempts']['evaluation_steps']:,}, "
              f"기술검사 {summary['technical_steps']:,}, 실제환경총합 {summary['total_environment_steps_all_attempts']:,}step.", "",
              "P/S의기존E50평가재사용비용은새환경비용에중복합산하지않았다. 실패시도도physical_cost_ledger.csv에보존한다.", "",
              "이번범위는기존B구성·부모5개·하나의사전학습단계·기존O100사례다. 관측성공상실은내부표상의망각진단이아니다. "
              "새부모·MT10/CW·A/B/C/D개입·선택기·기존보류단계의자동진행을허가하지않는다."]
    (run/"report_ko.md").write_text("\n".join(lines)+"\n", encoding="utf-8")


def analyze(campaign, allow_incomplete=False, draws=20000):
    started, cpu = time.perf_counter(), time.process_time()
    run = unique_run("analysis")
    source_snapshot(run)
    audit, receipt = Audit(), Receipt(run)
    try:
        study = load_study(campaign, receipt, audit, allow_incomplete)
        tables, primary, arrays = build_tables(study, audit)
        for name, rows in tables.items():
            write_csv(run / name, rows)
        write_csv(run / "execution_status.csv", study["statuses"])
        write_csv(run / "physical_cost_ledger.csv", study["ledger"])
        write_csv(run / "technical_cost_ledger.csv", study["technical_ledger"])
        if study["complete"]:
            intervals = paired_bootstrap(arrays, draws, BOOTSTRAP_SEED, run, audit)
            write_csv(run / "case_intervals.csv", intervals)
        else:
            intervals = []
        telemetry = exploratory_telemetry(study, receipt, tables["t20_interval_transitions.csv"])
        for name, rows in telemetry.items():
            write_csv(run / name, rows)
        write_json(run / "exploratory_questions.json", {
            "exposure_vs_loss": "Task sampling, replay age/newness and observed T20 loss in the same frozen checkpoint interval.",
            "policy_churn_vs_loss": "Training-only fixed-panel Gaussian KL/mean change and observed success transitions; KL is not task forgetting.",
            "reward_value_vs_success": "Actual sampled-batch rewards/Q/TD and changing training-policy episode outcomes alongside fixed-policy T20 success.",
            "status": "Exploratory descriptive co-occurrence; no signal selection, model fitting, causal attribution or scientific progression gate.",
            "alignment": "Intervals (0,4k],(4k,8k],(8k,16k],(16k,32k]; longer windows contain more updates and are not equal-duration hazards.",
            "pairing": "Condition differences computed within parent/task/interval after averaging the two futures; no missing-future deletion."})
        costs = {k: sum(row[k] for row in study["ledger"]) for k in ("training_steps", "evaluation_steps", "environment_steps")}
        summary = {"execution_status": "completed_file_only_analysis" if study["complete"] else "partial_file_only_analysis",
                   "campaign": study["campaign"], "completed_jobs": sum(s["execution_status"] == "completed" for s in study["statuses"]),
                   "planned_jobs": 20, "primary": primary, "case_intervals": intervals,
                   "scientific_status": "descriptive baseline; effect direction is not an execution/progression gate",
                   "uncertainty_scope": "individual conditional-policy case-percentile intervals; not simultaneous, parent-population, or future-training uncertainty",
                   "weighting": "within task E50/T20 equal cases; tasks equal; futures two averaged within each parent; five parents equal; no incomplete-parent exclusion",
                   "bootstrap": {"draws": draws if study["complete"] else 0, "seed": BOOTSTRAP_SEED,
                                 "pairing": "same case multiplicities across P/S, conditions and futures within parent/task; E50 and T20 sampled separately",
                                 "method": "percentile_2.5_97.5_linear", "parent_resampling": "not an independent confirmation; five LOPO point summaries retained"},
                   "costs_all_research_attempts": costs, "technical_steps": study["technical_steps"],
                   "total_environment_steps_all_attempts": costs["environment_steps"]+study["technical_steps"]+int(study["plan"].get("new_P_S_evaluation_steps",0)),
                   "analysis_new_environment_steps": 0,
                   "analysis_SAC_updates": 0, "future_execution_authorized_by_analysis": False,
                   "limitations": ["Five existing parents; fixed prefix4201 and a single pretraining stage.",
                                   "Existing known O100 cases; no new-case or new-parent confirmation.",
                                   "T20 labels record coarse observed transitions; unseen intermediate E50 labels are not imputed.",
                                   "Measured success loss is not a diagnosis of representational forgetting.",
                                   "Internal/exposure/drift telemetry is exploratory and not a predictor or causal mechanism test.",
                                   "STOP preserves the fixed S policy; training and evaluation costs must be distinguished."]}
        write_json(run / "summary.json", summary)
        report(run, summary, tables, telemetry)
        write_json(run / "analysis_config.json", {"parents": PARENTS, "tasks": TASKS, "conditions": CONDITIONS,
                                                  "futures": FUTURES, "steps": STEPS, "times": TIMES,
                                                  "E50": 50, "T20": 20, "bootstrap_seed": BOOTSTRAP_SEED,
                                                  "bootstrap_draws": draws, "no_new_rollouts": True})
        write_json(run / "checks.json", {"passed": audit.count, "failed": audit.failures})
        write_json(run / "input_assets.json", receipt.assets)
        write_json(run / "runtime.json", {"python": sys.version, "platform": platform.platform(),
                                          "numpy": np.__version__, "wall_seconds": time.perf_counter()-started,
                                          "cpu_seconds": time.process_time()-cpu,
                                          "new_environment_steps": 0, "SAC_updates": 0})
        write_json(run / "COMPLETE.json", {"status": "completed", "summary_sha256": sha(run / "summary.json"),
                                           "input_count": len(receipt.assets), "checks_passed": audit.count})
    except BaseException:
        write_json(run / "input_assets.json", receipt.assets)
        write_json(run / "checks.json", {"passed_before_failure": audit.count, "failed": audit.failures})
        write_json(run / "FAILED.json", {"traceback": traceback.format_exc(), "new_environment_steps": 0,
                                         "wall_seconds": time.perf_counter()-started})
        raise
    return run


def self_test():
    run = unique_run("analysis_selftest")
    source_snapshot(run)
    audit = Audit()
    try:
        for bits in itertools.product((0, 1), repeat=6):
            result = trajectory_features(bits)
            audit.require(result["loss_transitions"] == sum(a == 1 and b == 0 for a, b in zip(bits, bits[1:])), "Six-time loss count")
            audit.require(result["gain_transitions"]-result["loss_transitions"] == bits[-1]-bits[0], "Trajectory telescoping identity")
        p, s, y = np.array([0, 0, 1, 1]), np.array([0, 1, 0, 1]), np.array([1, 0, 1, 0])
        v = endpoint_vectors(p, s, y)
        audit.require(np.array_equal(v[:, 3], v[:, 1]-v[:, 2]), "Endpoint gain/loss identity")
        audit.require(v[:, 4].tolist() == [0, 0, 1, 0], "Recovery is P1/S0/final1 only")
        audit.require(trajectory_features([1, 0, 1, 0, 1, 0])["loss_transitions"] == 3, "Repeated losses retained")
        audit.require(trajectory_features([1, 0, 1, 0, 1, 0])["recovery_transitions"] == 2, "Repeated recoveries retained")
        audit.require(trajectory_features([0, 0, 0, 0, 0, 0])["first_observed_late_loss_end"] is None, "No loss is NA")
        # All twenty identities, empty risk sets and six observed times, no environment.
        fixture = {"cases": {}, "baseline": {}, "outcomes": {}}
        for parent, task in itertools.product(PARENTS, TASKS):
            fixture["cases"][(parent, task)] = {"E50": list(range(50)), "T20": list(range(20))}
            for idx in range(50):
                for stage in ("P", "S"):
                    bit = (idx+PARENTS.index(parent)+int(stage == "S")) % 2
                    fixture["baseline"][(parent, stage, task, idx)] = {"success": bit}
                for condition, future, step in itertools.product(CONDITIONS, FUTURES, STEPS):
                    if step != 32000 and idx >= 20:
                        continue
                    bit = (idx+future+CONDITIONS.index(condition)+STEPS.index(step)) % 2
                    fixture["outcomes"][(parent, condition, future, step, task, idx)] = {"success": bit}
        tables, primary, arrays = build_tables(fixture, audit)
        audit.require(len(tables["e50_case_outcomes.csv"]) == 4000, "E50 twenty-path synthetic row count")
        audit.require(len(tables["t20_case_trajectories.csv"]) == 1600, "T20 twenty-path synthetic row count")
        audit.require(len(tables["t20_interval_transitions.csv"]) == 400, "Unequal five interval coverage")
        audit.require(all(abs(primary["conditions"][c]["J"]-50) < 1e-12 for c in CONDITIONS), "Balanced toy endpoint success")
        intervals = paired_bootstrap(arrays, 64, BOOTSTRAP_SEED, run, audit)
        audit.require(len(intervals) == 31, "E50 and T20 individual interval coverage")
        # A separate missing-path fixture must never silently discard the parent.
        fixture["outcomes"] = {k: v for k,v in fixture["outcomes"].items() if not (k[0] == 41011 and k[1] == "dose25" and k[2] == 1)}
        _, missing, _ = build_tables(fixture, audit)
        audit.require(math.isnan(missing["conditions"]["dose25"]["J"]), "Missing future propagates NA into fixed-weight mean")
        write_json(run / "summary.json", {"status": "passed", "checks": audit.count,
                                         "scientific_evidence": False, "synthetic_outcomes_only": True,
                                         "new_environment_steps": 0})
        write_json(run / "COMPLETE.json", {"status": "completed", "source_sha256": sha(__file__)})
    except BaseException:
        write_json(run / "FAILED.json", {"traceback": traceback.format_exc(), "new_environment_steps": 0})
        raise
    return run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign")
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        run = self_test()
    elif args.campaign:
        run = analyze(args.campaign, args.allow_incomplete)
    else:
        parser.error("--campaign or --self-test required")
    print(json.dumps({"analysis_dir": str(run)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
