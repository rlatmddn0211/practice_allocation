"""Real-state integrity gate; no research outcome or rule selection."""
import json
import time
import traceback
from pathlib import Path

from common import (
    ROOT, REPOSITORY, unique, frozen_inputs, config_for, load_state, fork_future,
    expected_order, reserve, close_engine, read_csv, verify_input_files, reference)
from practice_allocation.core import (
    TASKS, configure_runtime, fingerprint, source_hashes, runtime_manifest,
    write_json, utc_now, file_sha256)
from practice_allocation.environment import CostCounter
from practice_allocation.evaluation import evaluate_model
from practice_allocation.study_io import (
    IntegrityError, read_json, source_snapshot, save_portable, load_portable, AuditEngine,
    load_banks)


def main():
    out = unique(ROOT/"results", "technical")
    source_snapshot(out)
    costs, engine, error = CostCounter(), None, None
    start, cpu = time.perf_counter(), time.process_time()
    checks = []
    previous = sum(read_json(p)["costs"]["environment_steps"]
                   for p in (ROOT/"results").glob("*_technical_*/costs.json"))

    def check(name, condition, details=None):
        checks.append({"name": name, "passed": bool(condition), "details": details})
        with (out/"checks.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(checks[-1])+"\n")
        if not condition:
            raise IntegrityError(name)

    def progress(event):
        with (out/"progress.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"time": utc_now(), "event": event, "costs": costs.snapshot()})+"\n")
        print(event, flush=True)

    def traced(engine, steps, label):
        reserve(costs, steps, 10000-previous)
        records = []
        original = engine.step
        def observe():
            record = original()
            records.append(fingerprint(record))
            return record
        engine.step = observe
        try:
            result = engine.train_steps(steps, label, out/(label+"_metrics.csv"),
                                       episodes_path=out/(label+"_episodes.csv"))
        finally:
            del engine.step
        write_json(out/(label+"_trace.json"), records)
        return records, result

    try:
        python_sources = list((out/"source_snapshot").rglob("*.py"))
        for path in python_sources:
            compile(path.read_text(encoding="utf-8-sig"), str(path), "exec")
        check("all_frozen_python_sources_compile", True, {"files": len(python_sources)})
        protocol, states = frozen_inputs()
        # This complete technical plan consumes at most 5000 environment steps.
        check("technical_budget_available", previous+5000 <= protocol["technical_environment_cap_all_attempts"],
              {"previous_actual": previous, "reserved": 5000})
        config = config_for(states[0])
        configure_runtime(config)
        write_json(out/"runtime.json", {
            **runtime_manifest(config, "same_state_integrity"),
            "execution_version": "52_same_state_future_replication_v1",
            "preserved_checkpoint_config_version": config.version})
        write_json(out/"input_manifest.json", states)
        write_json(out/"frozen_choice_ref.json", reference(ROOT/"inputs/fixed_choices.csv"))
        # All ten real full states must restore exactly, including optimizer/replay.
        fork_records = []
        for state in states:
            engine = load_state(state, costs)
            record = fork_future(engine, state)
            order = expected_order(engine, 64)
            check("future_32k_quotas_"+str(state["parent"])+"_"+str(state["prefix_continuation"]),
                  [order.count(i) for i in range(4)] == [8, 8, 8, 40])
            fork_records.append({"parent": state["parent"], "prefix": state["prefix_continuation"],
                                 **record, "episode_order": order})
            verify_input_files(state)
            close_engine(engine)
            engine = None
            progress("restored_and_forked_"+str(state["parent"])+"_"+str(state["prefix_continuation"]))
        write_json(out/"all_state_fork_checks.json", fork_records)
        check("all_state_checks_zero_environment_steps", costs.environment_steps == 0)

        state = states[0]
        old_traces, old_final = [], []
        for rep in range(2):
            engine = load_state(state, costs, out)
            trace, _ = traced(engine, 500, "old_rng_"+str(rep))
            old_traces.append(trace)
            old_final.append(engine.fingerprints())
            close_engine(engine)
            engine = None
        check("same_rng_transition_action_sample_loss_trace_exact", old_traces[0] == old_traces[1])
        check("same_rng_full_end_state_exact", old_final[0] == old_final[1])
        progress("old_rng_exact_reproduction_passed")

        engine = load_state(state, costs, out)
        fork_future(engine, state)
        trace_full, _ = traced(engine, 1000, "new_rng_whole")
        final_full = engine.fingerprints()
        close_engine(engine)
        engine = None
        engine = load_state(state, costs, out)
        fork_future(engine, state)
        trace_a, _ = traced(engine, 500, "new_rng_split_a")
        midpoint = save_portable(engine, out/"midpoint_checkpoint")
        close_engine(engine)
        engine = None
        engine = load_portable(midpoint, config, costs, AuditEngine)
        trace_b, _ = traced(engine, 500, "new_rng_split_b")
        check("chunk_horizon_and_checkpoint_trace_exact", trace_full == trace_a+trace_b)
        check("chunk_horizon_and_checkpoint_full_end_state_exact", final_full == engine.fingerprints())
        check("new_future_trace_differs_from_old", trace_full[:500] != old_traces[0])
        check("technical_updates_exact", costs.train_iterations == 3000)
        close_engine(engine)
        engine = None
        progress("new_rng_resume_and_horizon_checks_passed")

        # Re-evaluate a known existing 8k policy; do not score any new future.
        engine = load_state(state, costs)
        before = engine.fingerprints()
        bank = load_banks(state["bank"])["outcome"]
        reserve(costs, 2000, 10000-previous)
        evaluate_model(engine.model, [e for e in bank if e["episode_index"] == 0], costs,
                       out/"known_8k_evaluation.csv", "technical_known8k", context="technical_integrity")
        observed = read_csv(out/"known_8k_evaluation.csv")
        spec = read_json(ROOT/"inputs/protocol51.json")
        source = REPOSITORY/spec["source_outcomes"]
        check("known_outcomes_hash", file_sha256(source) == spec["source_outcomes_sha256"])
        old = read_csv(source)
        write_json(out/"known_outcome_ref.json", reference(source))
        # The canonical analysis CSV uses horizon labels; validate its schema explicitly.
        wanted = [r for r in old if int(r["original_seed"]) == state["parent"]
                  and int(r["continuation"]) == state["prefix_continuation"]
                  and int(r["horizon"]) == 8000 and int(r["episode_index"]) == 0]
        lookup = {r["task"]: r for r in wanted}
        check("known_reference_four_tasks", set(lookup) == set(TASKS))
        for row in observed:
            ref = lookup[row["task"]]
            for key in ("seed", "initial_state_hash", "success", "length"):
                check("known_"+row["task"]+"_"+key, row[key] == ref[key])
            check("known_"+row["task"]+"_return", float(row["return"]) == float(ref["return"]))
        check("evaluation_full_state_unchanged", before == engine.fingerprints())
        check("no_evaluation_updates", costs.train_iterations == 3000)
        check("all_checks_within_reserved_5000", costs.environment_steps <= 5000)
        for state in states:
            verify_input_files(state)
        progress("technical_gate_passed")
    except BaseException as exc:
        error = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
        write_json(out/"error.json", error)
        traceback.print_exc()
    finally:
        close_engine(engine)
        write_json(out/"costs.json", {
            "status": "failed" if error else "completed", "costs": costs.snapshot(),
            "wall_seconds": time.perf_counter()-start, "cpu_seconds": time.process_time()-cpu,
            "previous_technical_environment_steps": previous, "new_scientific_results": False})
        write_json(out/"summary.json", {
            "status": "failed" if error else "passed", "checks": len(checks),
            "failed_checks": [c for c in checks if not c["passed"]], "error": error,
            "source_hashes": source_hashes(), "costs": costs.snapshot(),
            "total_technical_environment_steps_all_attempts": previous+costs.environment_steps,
            "scope": "Implementation integrity only; not evidence of scientific benefit"})
    if not error:
        write_json(out/"VERIFIED.json", {"summary": reference(out/"summary.json"),
                                        "source_hashes": source_hashes(), "created_at": utc_now()})
    print(json.dumps({"run": str(out), "passed": error is None, "costs": costs.snapshot()}), flush=True)
    return 1 if error else 0


if __name__ == "__main__":
    raise SystemExit(main())
