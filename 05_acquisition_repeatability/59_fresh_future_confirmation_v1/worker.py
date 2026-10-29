"""One independently re-randomized future, exact BP continuation and final O100."""
import argparse
import csv
import json
import time
import traceback
from pathlib import Path

from common import (
    ROOT, frozen_inputs, config_for, load_state, fork_future, expected_order,
    reserve, read_csv, verify_input_files, reference, checked)
from practice_allocation.core import (
    TASKS, configure_runtime, source_hashes, runtime_manifest, utc_now, write_json)
from practice_allocation.environment import CostCounter
from practice_allocation.evaluation import evaluate_model
from practice_allocation.study_io import (
    IntegrityError, source_snapshot, load_banks, save_portable, read_json)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--request", required=True)
    args = ap.parse_args()
    q = read_json(args.request)
    out = Path(q["output"])
    if (out/"runtime.json").exists() or (out/"costs.json").exists():
        raise IntegrityError("Attempt cannot be reused")
    source_snapshot(out)
    costs, engine, error = CostCounter(), None, None
    start, cpu = time.perf_counter(), time.process_time()
    checkpoints, result = [], {}
    training, evaluation = 0, 0
    phase = "training"

    def progress(event, **extra):
        with (out/"progress.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "time": utc_now(), "event": event, "costs": costs.snapshot(),
                "absolute_step": engine.model.num_timesteps if engine else None, **extra})+"\n")

    try:
        protocol, states = frozen_inputs()
        state = q["state"]
        if state not in states or q["source_hashes"] != source_hashes():
            raise IntegrityError("Pinned input or worker source changed")
        config = config_for(state)
        configure_runtime(config)
        write_json(out/"runtime.json", {
            **runtime_manifest(config, "same_state_new_future"),
            "execution_version": "59_fresh_future_confirmation_v1",
            "preserved_checkpoint_config_version": config.version})
        engine = load_state(state, costs, out)
        write_json(out/"research_start_integrity.json", {
            "original_8k_checkpoint": state["checkpoint"], "future_id": state["future_id"],
            "absolute_step": engine.model.num_timesteps, "full_state_fingerprints": engine.fingerprints(),
            "environment_steps_before_fork": costs.environment_steps,
            "independent_of_technical_rollouts": True})
        if costs.environment_steps != 0:
            raise IntegrityError("Research start contaminated by prior rollout")
        progress("restored_original_full_8k_state", future_id=state["future_id"])
        write_json(out/"fork_integrity.json", fork_future(engine, state))
        expected = expected_order(engine, 64)
        write_json(out/"expected_episode_order.json", expected)
        before_counts = engine.collected_steps.copy()
        before_updates = engine.model._n_updates
        for end in protocol["full_checkpoint_absolute_steps"]:
            while engine.model.num_timesteps < end:
                steps = min(1000, end-engine.model.num_timesteps)
                reserve(costs, steps, 32000)
                engine.train_steps(steps, q["id"], out/"train_metrics.csv",
                                   episodes_path=out/"train_episodes.csv")
                training = costs.environment_steps
                progress("training")
            if not engine.at_boundary:
                raise IntegrityError("Checkpoint not at episode boundary")
            cp = save_portable(engine, out/"checkpoints"/("absolute_"+str(end)))
            checkpoints.append({"absolute_step": end, **cp})
            write_json(out/("checkpoint_"+str(end)+".json"), cp)
            progress("checkpoint_saved")
        episodes = read_csv(out/"train_episodes.csv")
        actual = [TASKS.index(row["task"]) for row in episodes]
        counts = (engine.collected_steps-before_counts).tolist()
        if actual != expected or counts != [4000, 4000, 4000, 20000]:
            raise IntegrityError("Collection schedule or exact task counts changed")
        if (training, costs.train_iterations, engine.model._n_updates-before_updates) != (32000, 32000, 32000):
            raise IntegrityError("Training or update cost mismatch")
        write_json(out/"training_summary.json", {
            "training_steps": training, "SAC_updates": costs.train_iterations,
            "collected_by_task": dict(zip(TASKS, counts)), "episode_order_exact": True,
            "checkpoints": checkpoints, "wall_seconds": time.perf_counter()-start})
        progress("training_complete")

        phase = "evaluation"
        bank = load_banks(state["bank"])["outcome"]
        if {(e["task"], e["episode_index"]) for e in bank} != {(t, i) for t in TASKS for i in range(100)} or len(bank) != 400:
            raise IntegrityError("O100 bank coverage changed")
        before = engine.fingerprints()
        for lo in range(0, 100, 10):
            reserve(costs, 40*500, 232000)
            evaluate_model(engine.model, [e for e in bank if lo <= e["episode_index"] < lo+10],
                           costs, out/"evaluation_episodes.csv", q["id"], context="new_future_final_O100")
            evaluation = costs.environment_steps-training
            progress("evaluation", cases_completed=costs.evaluation_episodes)
        if engine.fingerprints() != before or costs.train_iterations != 32000:
            raise IntegrityError("Evaluation changed full state or trained")
        rows = read_csv(out/"evaluation_episodes.csv")
        if len(rows) != 400 or len({(r["task"], int(r["episode_index"])) for r in rows}) != 400:
            raise IntegrityError("Final evaluation case coverage invalid")
        if sum(int(r["length"]) for r in rows) != evaluation or evaluation > 200000:
            raise IntegrityError("Evaluation cost mismatch")
        # Explicitly match paired identities, independent of success/return outcomes.
        identities = {(e["task"], e["episode_index"]): e for e in bank}
        for row in rows:
            known = identities[row["task"], int(row["episode_index"])]
            if int(row["seed"]) != known["seed"] or row["initial_state_hash"] != known["initial_state_hash"]:
                raise IntegrityError("Paired evaluation identity changed")
        verify_input_files(state)
        scores = {t: sum(int(r["success"]) for r in rows if r["task"] == t)/100 for t in TASKS}
        result = {
            "id": q["id"], "state": state, "status": "completed",
            "fork_verified": True, "evaluation_state_unchanged": True,
            "training_steps": training, "evaluation_steps": evaluation,
            "training_counts": dict(zip(TASKS, counts)), "checkpoints": checkpoints,
            "episodes": reference(out/"evaluation_episodes.csv"),
            "success_by_task": scores, "macro_success": sum(scores.values())/4,
            "fixed_prediction_sha256": protocol["fixed_predictions_sha256"],
            "rule_fitted": False, "scientific_interpretation": "pending all twenty F3/F4 futures and frozen protocol58 analysis"}
        frozen_inputs()
        progress("complete")
    except BaseException as exc:
        error = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
        write_json(out/"error.json", error)
        traceback.print_exc()
    finally:
        if engine is not None:
            engine.close()
        # All consumed steps remain counted even after a partially failed block.
        training = costs.environment_steps if phase == "training" else 32000
        evaluation = costs.environment_steps-training
        write_json(out/"costs.json", {
            "status": "failed" if error else "completed", "costs": costs.snapshot(),
            "training_steps": training, "evaluation_steps": evaluation,
            "wall_seconds": time.perf_counter()-start, "cpu_seconds": time.process_time()-cpu,
            "gpu_busy_seconds": None})
    if error is None:
        write_json(out/"result.json", result)
    return 1 if error else 0


if __name__ == "__main__":
    raise SystemExit(main())
