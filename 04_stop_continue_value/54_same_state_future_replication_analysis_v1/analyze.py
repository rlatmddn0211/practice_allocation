"""Read-only analysis of frozen 51/52 evidence; never imports an RL learner."""
from __future__ import annotations

import csv
import hashlib
import itertools
import json
import platform
import shutil
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def dump(path, value):
    def scalar(x):
        if isinstance(x, np.ndarray):
            return x.tolist()
        if isinstance(x, np.generic):
            return x.item()
        raise TypeError(type(x).__name__)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=scalar) + "\n", encoding="utf-8")


def rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, values):
    with Path(path).open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(values[0]))
        w.writeheader()
        w.writerows(values)


def main():
    started = time.perf_counter()
    cpu = time.process_time()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = HERE / "results" / f"{stamp}_analysis_{uuid.uuid4().hex[:8]}"
    out.mkdir(parents=True, exist_ok=False)
    snap = out / "source_snapshot"
    snap.mkdir()
    source_hashes = {}
    for path in sorted([*HERE.glob("*.py"), HERE / "analysis_config.json"]):
        shutil.copy2(path, snap / path.name)
        source_hashes[path.name] = sha(path)
    dump(out / "source_hashes.json", source_hashes)
    audit, inputs = [], {}

    def require(ok, label):
        audit.append({"check": label, "passed": bool(ok)})
        if not ok:
            raise AssertionError(label)

    def pin(path, expected=None):
        path = Path(path)
        if not path.is_absolute():
            path = ROOT / path
        actual = sha(path)
        inputs[str(path.relative_to(ROOT)).replace("\\", "/")] = actual
        if expected is not None:
            require(actual == expected, f"sha256:{path.relative_to(ROOT)}")
        return path

    def reference(ref):
        return pin(ref["path"], ref["sha256"])

    def checkpoint(ref):
        directory = Path(ref["path"])
        manifest = read(pin(directory / "checkpoint_manifest.json", ref["manifest_sha256"]))
        for name, expected in manifest["files"].items():
            pin(directory / name, expected)
        return manifest

    try:
        cfg = read(HERE / "analysis_config.json")
        campaign = ROOT / cfg["campaign"]
        implementation = campaign.parent.parent
        plan = read(pin(campaign / "plan.json", cfg["plan_sha256"]))
        complete = read(pin(campaign / "COMPLETE.json"))
        completion = read(reference(complete["summary"]))
        require(sha(campaign / "completion_summary.json") == cfg["completion_summary_sha256"], "pinned_completion")
        require(completion["execution_status"] == "completed" and completion["states"] == 10, "ten_completed")
        for name, expected in plan["source_hashes"].items():
            pin(implementation / name, expected)
        protocol = read(pin(implementation / "inputs/protocol51.json", cfg["scientific_protocol_sha256"]))
        choices_path = pin(implementation / "inputs/fixed_choices.csv", cfg["fixed_choices_sha256"])
        choices = rows(choices_path)
        old_path = pin(protocol["source_outcomes"], protocol["source_outcomes_sha256"])
        pin(protocol["source_checkpoint_provenance"], protocol["source_checkpoint_provenance_sha256"])
        old = rows(old_path)
        require(len(old) == 10000, "25_existing_policies_10000_cases")
        verified = read(reference(plan["verification"]))
        technical = read(reference(verified["summary"]))
        require(technical["status"] == "passed" and not technical["failed_checks"], "prior_technical_pass")
        technical_steps = sum(read(reference(c["reference"]))["costs"]["environment_steps"] for c in plan["technical_costs"])
        parents, prefixes, tasks = protocol["parents"], protocol["prefix_continuations"], protocol["tasks"]
        lookup = {}
        for row in old:
            key = (int(row["original_seed"]), int(row["continuation"]), int(row["horizon"]), row["task"], int(row["episode_index"]))
            require(key not in lookup, f"unique_old:{key}")
            lookup[key] = row
        shape = (5, 2, 4, 100)
        j0, j8, jold, jnew = [np.zeros(shape, dtype=np.int8) for _ in range(4)]
        cases, state_records = [], []
        total_train = total_eval = 0
        worker_wall = worker_cpu = training_wall = 0.0
        snapshots = out / "input_snapshot"
        snapshots.mkdir()
        for path in [old_path, choices_path, implementation / "inputs/protocol51.json", implementation / "inputs/state_manifest.json", campaign / "plan.json", campaign / "completion_summary.json"]:
            shutil.copy2(path, snapshots / path.name)
        require(len(plan["jobs"]) == 10 and len(list((campaign / "completed").glob("*.json"))) == 10, "all_and_only_ten_markers")
        for job in plan["jobs"]:
            marker = read(pin(campaign / "completed" / f"{job['id']}.json"))
            result = read(reference(marker["result"]))
            cost = read(reference(marker["costs"]))
            attempt = Path(marker["attempt"])
            require(len(list((campaign / "jobs" / job["id"]).iterdir())) == 1, f"one_attempt:{job['id']}")
            require(result["id"] == job["id"] and result["state"] == job["state"], f"state_identity:{job['id']}")
            require(result["status"] == "completed" and result["fork_verified"] and result["evaluation_state_unchanged"] and not result["rule_fitted"], f"integrity_flags:{job['id']}")
            state = result["state"]
            p, r = parents.index(state["parent"]), prefixes.index(state["prefix_continuation"])
            fork = read(pin(attempt / "fork_integrity.json"))
            runtime = read(pin(attempt / "runtime.json"))
            training = read(pin(attempt / "training_summary.json"))
            initial = checkpoint(state["checkpoint"])
            reference(state["bank"])
            require(initial["step"] == 208000, f"same_8k_start:{job['id']}")
            require(fork["preserved_before"] == fork["preserved_after"], f"rng_only_preserved:{job['id']}")
            require(all(fork["global_streams_changed"].values()) and fork["schedule_rng_changed"], f"future_rng_replaced:{job['id']}")
            require(fork["root_before"] == state["old_continuation_rng_seed"] and fork["root_after"] == state["proposed_new_future_root_seed"], f"roots:{job['id']}")
            expected_seed = int(np.random.SeedSequence([510202, 51, state["parent"], state["prefix_continuation"]]).generate_state(1)[0])
            require(expected_seed == fork["root_after"], f"seed_recipe:{job['id']}")
            require(runtime["source_hashes"] == plan["source_hashes"], f"executed_sources:{job['id']}")
            require(training["training_steps"] == training["SAC_updates"] == 32000 and training["episode_order_exact"], f"train_budget:{job['id']}")
            require(result["training_counts"] == {"DO": 4000, "DC": 4000, "PU": 4000, "BP": 20000}, f"dose625:{job['id']}")
            require([c["absolute_step"] for c in result["checkpoints"]] == [216000, 224000, 232000, 240000], f"full_save_steps:{job['id']}")
            for ck in result["checkpoints"]:
                m = checkpoint(ck)
                require(m["step"] == ck["absolute_step"] and m["source_hashes"] == plan["source_hashes"], f"checkpoint_source:{job['id']}:{m['step']}")
            evalpath = reference(result["episodes"])
            shutil.copy2(evalpath, snapshots / f"{job['id']}.csv")
            evaluation = rows(evalpath)
            require(len(evaluation) == 400, f"O100_count:{job['id']}")
            seen = set()
            for row in evaluation:
                t, i = tasks.index(row["task"]), int(row["episode_index"])
                require((t, i) not in seen and 0 <= i < 100, f"new_case_unique:{job['id']}:{t}:{i}")
                seen.add((t, i))
                pair = [lookup[(state["parent"], 0, 0, row["task"], i)], lookup[(state["parent"], state["prefix_continuation"], 8000, row["task"], i)], lookup[(state["parent"], state["prefix_continuation"], 40000, row["task"], i)], row]
                identity = {(z["seed"], z["initial_state_hash"]) for z in pair}
                require(len(identity) == 1 and all(z["success"] in ("0", "1") for z in pair), f"paired_identity:{job['id']}:{t}:{i}")
                require(all(1 <= int(z["length"]) <= 500 for z in pair), f"episode_lengths:{job['id']}:{t}:{i}")
                for arr, item in zip((j0, j8, jold, jnew), pair):
                    arr[p, r, t, i] = int(item["success"])
                cases.append({"parent": state["parent"], "prefix": state["prefix_continuation"], "task": row["task"], "case": i, "seed": row["seed"], "initial_state_hash": row["initial_state_hash"], "J0": int(pair[0]["success"]), "J8": int(pair[1]["success"]), "old_J40": int(pair[2]["success"]), "new_J40": int(row["success"])})
            require(np.isclose(jnew[p, r].mean(), result["macro_success"]), f"reported_macro:{job['id']}")
            require(all(np.isclose(jnew[p, r, t].mean(), result["success_by_task"][task]) for t, task in enumerate(tasks)), f"reported_tasks:{job['id']}")
            evsteps = sum(int(z["length"]) for z in evaluation)
            require(evsteps == result["evaluation_steps"] == cost["evaluation_steps"], f"evaluation_cost:{job['id']}")
            require(cost["costs"]["environment_steps"] == 32000 + evsteps, f"total_cost:{job['id']}")
            total_train += training["training_steps"]
            total_eval += evsteps
            worker_wall += cost["wall_seconds"]
            worker_cpu += cost["cpu_seconds"]
            training_wall += training["wall_seconds"]
            state_records.append({"parent": state["parent"], "prefix": state["prefix_continuation"], "old_root": fork["root_before"], "new_root": fork["root_after"], "schedule_seed": state["proposed_schedule_seed"], "J0_percent": 100 * j0[p, r].mean(), "J8_percent": 100 * j8[p, r].mean(), "old_J40_percent": 100 * jold[p, r].mean(), "new_J40_percent": 100 * jnew[p, r].mean(), "old_late_pp": 100 * (jold[p, r] - j8[p, r]).mean(), "new_late_pp": 100 * (jnew[p, r] - j8[p, r]).mean(), "new_minus_old_pp": 100 * (jnew[p, r] - jold[p, r]).mean()})
        require(total_train == completion["research_training_steps"] == 320000, "aggregate_training_cost")
        require(total_eval == completion["research_evaluation_steps"], "aggregate_evaluation_cost")
        require(technical_steps == completion["technical_environment_steps_all_attempts"] == 4515, "aggregate_technical_cost")
        require(total_train + total_eval + technical_steps == completion["total_environment_steps"], "aggregate_all_cost")
        write_csv(out / "paired_outcomes.csv", cases)
        write_csv(out / "state_results.csv", state_records)
        actions = np.full((5, 2, 2), -1, dtype=np.int8)  # indexed by scoring half
        full_actions = np.full((5, 2), -1, dtype=np.int8)
        choice_records = []
        for c in choices:
            p, r = parents.index(int(c["parent"])), prefixes.index(int(c["prefix_continuation"]))
            selection = slice(0, 50) if c["selection_cases"] == "A" else slice(50, 100) if c["selection_cases"] == "B" else slice(None)
            late = float(100 * (jold[p, r, :, selection] - j8[p, r, :, selection]).mean())
            require(np.isclose(late, float(c["old_late_pp"])), f"frozen_choice_score:{p}:{r}:{c['selection_cases']}")
            a = int(c["fixed_action"] == "continue")
            require(a == int(late > 0), f"frozen_choice_rule:{p}:{r}:{c['selection_cases']}")
            if c["selection_cases"] == "O100":
                full_actions[p, r] = a
                scoring = slice(None)
            else:
                h = 0 if c["scoring_cases"] == "A" else 1
                require(c["selection_cases"] != c["scoring_cases"] and actions[p, r, h] == -1, "crossed_disjoint_halves")
                actions[p, r, h] = a
                scoring = slice(h * 50, (h + 1) * 50)
            stop, cont = [float(100 * arr[p, r, :, scoring].mean()) for arr in (j8, jnew)]
            selected = cont if a else stop
            choice_records.append({**c, "new_stop_percent": stop, "new_continue_percent": cont, "selected_percent": selected, "G_stop_pp": selected - stop, "G_continue_pp": selected - cont})
        require(len(choices) == 30 and np.all(actions >= 0) and np.all(full_actions >= 0), "complete_fixed_choice_tables")
        write_csv(out / "frozen_choice_scores.csv", choice_records)
        # P,R,T,H,I; actions use the opposite half's old outcome for each scoring half.
        stop = j8.reshape(5, 2, 4, 2, 50).astype(float)
        cont = jnew.reshape(5, 2, 4, 2, 50).astype(float)
        selected = np.where(actions[:, :, None, :, None] == 1, cont, stop)
        diffs = np.stack((selected - stop, selected - cont), axis=-1)
        parent_gains = diffs.mean(axis=(1, 2, 3, 4)) * 100
        theta = parent_gains.mean(axis=0)
        parent_rows = []
        for p, parent in enumerate(parents):
            parent_rows.append({"parent": parent, "stop_percent": 100 * stop[p].mean(), "continue_percent": 100 * cont[p].mean(), "selected_percent": 100 * selected[p].mean(), "G_stop_pp": parent_gains[p, 0], "G_continue_pp": parent_gains[p, 1]})
        write_csv(out / "parent_results.csv", parent_rows)
        removal = []
        for p, parent in enumerate(parents):
            mask = np.arange(5) != p
            a, b, c = [float(100 * v[mask].mean()) for v in (stop, cont, selected)]
            removal.append({"excluded_parent": parent, "stop_percent": a, "continue_percent": b, "selected_percent": c, "G_stop_pp": c-a, "G_continue_pp": c-b, "observed_better_fixed": "stop" if a >= b else "continue", "gain_over_better_fixed_pp": c-max(a,b)})
        write_csv(out / "leave_one_parent_out.csv", removal)
        unc = protocol["uncertainty"]
        count = unc["case_bootstrap_replicates"]
        rng = np.random.default_rng(unc["case_bootstrap_seed"])
        indices = np.empty((5, 4, 2, count, 50), dtype=np.uint8)
        samples = np.zeros((count, 2))
        # Prefixes are dependent within parent: SAME resampled cases for both.
        case_gains = diffs.mean(axis=1) * 100  # P,T,H,I,contrast
        for p, t, h in itertools.product(range(5), range(4), range(2)):
            idx = rng.integers(0, 50, size=(count, 50))
            indices[p,t,h] = idx
            samples += case_gains[p,t,h][idx].mean(axis=1) / 40
        q = float(np.quantile(np.max(theta[None, :] - samples, axis=1), 0.95, method="linear"))
        lower = theta - q
        parent_indices = np.array(list(itertools.product(range(5), repeat=5)), dtype=np.uint8)
        parent_samples = parent_gains[parent_indices].mean(axis=1)
        parent_ci = np.quantile(parent_samples, [0.025, 0.975], axis=0, method="linear").T
        case_ci = np.quantile(samples, [0.025, 0.975], axis=0, method="linear").T
        np.savez_compressed(out / "bootstrap_draws.npz", indices=indices, case_estimates=samples, parent_indices=parent_indices, parent_estimates=parent_samples)
        shares = []
        for b in range(2):
            positives = np.maximum(parent_gains[:, b], 0)
            shares.append(float(positives.max() / positives.sum()) if positives.sum() > 0 else None)
        gate = protocol["proposed_investment_gate"]
        conditions = {
            "both_gains_at_least_1pp": bool(np.all(theta >= gate["minimum_each_primary_gain_pp"])),
            "both_conditional_joint_lower_bounds_positive": bool(np.all(lower > 0)),
            "both_gains_positive_in_every_parent_removal": all(r["G_stop_pp"] > 0 and r["G_continue_pp"] > 0 for r in removal),
            "both_positive_concentration_shares_at_most_two_thirds": all(v is not None and v <= gate["maximum_positive_parent_contribution_share_each"] for v in shares),
            "technical_integrity": True,
        }
        full_selected = np.where(full_actions[:, :, None, None], jnew, j8)
        full_gains = [float(100 * (full_selected - a).mean()) for a in (j8, jnew)]
        task_rows = []
        pattern_rows = []
        for t, task in enumerate(tasks):
            task_rows.append({"task": task, **{name: float(100 * arr[:, :, t].mean()) for name, arr in (("J0_percent", j0), ("J8_percent", j8), ("old_J40_percent", jold), ("new_J40_percent", jnew))}})
        for future, arr in (("old", jold), ("new", jnew)):
            codes = j0 * 4 + j8 * 2 + arr
            for p, r, t, code in itertools.product(range(5), range(2), range(4), range(8)):
                n = int(np.sum(codes[p, r, t] == code))
                pattern_rows.append({"parent": parents[p], "prefix": prefixes[r], "task": tasks[t], "future": future, "pattern": f"{code:03b}", "count": n, "task_percent": n, "macro_contribution_pp": n / 4})
        write_csv(out / "task_results.csv", task_rows)
        write_csv(out / "success_patterns.csv", pattern_rows)
        pattern_totals = {future: {f"{code:03b}": float(100 * np.mean(j0 * 4 + j8 * 2 + arr == code)) for code in range(8)} for future, arr in (("old", jold), ("new", jnew))}
        dump(out / "success_pattern_totals.json", pattern_totals)
        summary = {
            "execution_status": "completed", "scientific_status": "investment_gate_passed" if all(conditions.values()) else "investment_gate_not_passed",
            "analysis_environment_steps": 0, "parents": parents, "prefixes": prefixes, "independent_parent_count": 5, "state_count": 10, "futures_per_state_including_old": 2,
            "means_percent": {"parent": float(100*j0.mean()), "stop8": float(100*stop.mean()), "old_continue40": float(100*jold.mean()), "new_continue40": float(100*cont.mean()), "primary_fixed_choice": float(100*selected.mean())},
            "primary_gains_pp": dict(zip(("versus_stop", "versus_new_continue"), theta.tolist())),
            "conditional_case_joint_lower_bounds_pp": lower, "joint_q_pp": q,
            "case_marginal_percentile_95_pp_secondary": case_ci, "parent_percentile_95_pp_descriptive": parent_ci,
            "maximum_positive_parent_contribution_shares": shares, "gate_conditions": conditions,
            "secondary_full_O100": {"selected_percent": float(100*full_selected.mean()), "gains_pp": full_gains, "warning": "same J8 cases used in old selection and new scoring; not primary"},
            "primary_actions": {"stop": int((actions == 0).sum()), "continue": int((actions == 1).sum())},
            "state_results": state_records, "parent_results": parent_rows, "leave_one_parent_out": removal,
            "task_results": task_rows, "success_pattern_totals": pattern_totals,
            "costs": {"training_steps": total_train, "SAC_updates": total_train, "evaluation_steps": total_eval, "main_environment_steps": total_train + total_eval, "technical_steps": technical_steps, "all_environment_steps": total_train + total_eval + technical_steps, "worker_wall_seconds_sum": worker_wall, "worker_cpu_seconds_sum": worker_cpu, "training_wall_seconds_sum": training_wall, "GPU_busy_seconds": None},
            "completed_at": completion["completed_at"], "next_decision": "No automatic expansion. C and original stages 2/3 remain held; no threshold or predictor fitting.",
            "limitations": ["Only two realized futures per fixed state, five independent parents.", "Choices use an old completed 40k future, not deployable decision-time information.", "Conditional case intervals omit future learning and population uncertainty.", "Known development evaluation bank and selected existing states; not a fresh-parent validation.", "No allocation switch action, replay intervention, online diagnosis, or noninferiority test."],
        }
        dump(out / "summary.json", summary)
        dump(out / "decision_record.json", {"scientific_status": summary["scientific_status"], "conditions": conditions, "criteria_source": cfg["scientific_protocol_sha256"], "thresholds_changed": False, "new_experiments_scheduled": False})
        dump(out / "runtime.json", {"python": sys.version, "platform": platform.platform(), "numpy": np.__version__, "wall_seconds": time.perf_counter()-started, "cpu_seconds": time.process_time()-cpu, "environment_steps": 0, "SAC_updates": 0, "model_loaded": False, "GPU_used": False})
        dump(out / "COMPLETE.json", {"summary": {"path": str(out / "summary.json"), "sha256": sha(out / "summary.json")}})
        print(json.dumps({"output": str(out), "means": summary["means_percent"], "gains": theta.tolist(), "joint_lower": lower.tolist(), "parent_ci": parent_ci.tolist(), "concentration": shares, "conditions": conditions}, ensure_ascii=False, indent=2))
    except Exception:
        dump(out / "FAILED.json", {"traceback": traceback.format_exc(), "environment_steps": 0, "source_hashes": source_hashes})
        raise
    finally:
        dump(out / "input_hashes.json", inputs)
        dump(out / "checks.json", {"total": len(audit), "failed": [c for c in audit if not c["passed"]], "checks": audit})


if __name__ == "__main__":
    main()
