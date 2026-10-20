"""Evaluate one frozen existing checkpoint. There is no training dispatch."""
import argparse
import csv
import json
import os
import time
import traceback
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--request", required=True)
    request_path = Path(ap.parse_args().request).resolve()
    q = json.loads(request_path.read_text(encoding="utf-8-sig"))
    os.environ["PRACTICE_SUITE"] = "B"
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    from practice_allocation.core import (
        Config, configure_runtime, runtime_manifest, source_hashes,
        file_sha256, utc_now, write_json, TASKS)
    from practice_allocation.environment import CostCounter
    from practice_allocation.evaluation import evaluate_model
    from practice_allocation.study_io import (
        load_portable, load_banks, source_snapshot, read_json, IntegrityError)

    out = Path(q["output"])
    out.mkdir(parents=True, exist_ok=True)
    if (out/"runtime.json").exists() or (out/"costs.json").exists():
        raise IntegrityError("Cannot reuse an existing attempt")
    source_snapshot(out)
    costs, engine, error = CostCounter(), None, None
    start, cpu = time.perf_counter(), time.process_time()

    def progress(event, **extra):
        with (out/"progress.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(dict(time=utc_now(), event=event, costs=costs.snapshot(), **extra))+"\n")

    try:
        if source_hashes() != q["source_hashes"]:
            raise IntegrityError("Pinned worker source changed")
        if q["kind"] not in ("research_8k_evaluation", "technical_known_policy"):
            raise IntegrityError("Only checkpoint evaluation is supported")
        config = Config(**q["config"])
        config.validate()
        configure_runtime(config)
        write_json(out/"runtime.json", runtime_manifest(config, q["kind"]))
        progress("start")
        engine = load_portable(q["checkpoint"], config, costs)
        if engine.model.num_timesteps != q["expected_absolute_step"]:
            raise IntegrityError("Restored wrong checkpoint step")
        if engine.schedule.candidate != "dose625":
            raise IntegrityError("Not a BP-focused checkpoint")
        before = engine.fingerprints()
        write_json(out/"restored_fingerprints.json", before)
        bank = load_banks(q["bank"])["outcome"]
        selected = [e for e in bank if e["episode_index"] < q["cases_per_task"]]
        if len(selected) != 4*q["cases_per_task"]:
            raise IntegrityError("Wrong case coverage")
        progress("state_restored", checkpoint_step=engine.model.num_timesteps)
        for lo in range(0, q["cases_per_task"], q["chunk_cases_per_task"]):
            hi = min(q["cases_per_task"], lo+q["chunk_cases_per_task"])
            chunk = [e for e in selected if lo <= e["episode_index"] < hi]
            evaluate_model(engine.model, chunk, costs, out/"evaluation_episodes.csv",
                           q["id"], context=q["kind"])
            progress("evaluation_chunk", cases_completed=costs.evaluation_episodes,
                     expected_cases=4*q["cases_per_task"])
        after = engine.fingerprints()
        if after != before or costs.train_iterations != 0:
            raise IntegrityError("Evaluation changed learning/replay/collector/RNG or trained")
        write_json(out/"post_evaluation_fingerprints.json", after)
        # Verify original binary files after evaluation as well as during load.
        manifest = read_json(Path(q["checkpoint"]["path"])/"checkpoint_manifest.json")
        for name, expected in manifest["files"].items():
            if file_sha256(Path(q["checkpoint"]["path"])/name) != expected:
                raise IntegrityError("Source checkpoint binary changed")
        with (out/"evaluation_episodes.csv").open(encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        identities = {(r["task"], int(r["episode_index"])) for r in rows}
        if len(rows) != len(identities) or identities != {
                (t, i) for t in TASKS for i in range(q["cases_per_task"])}:
            raise IntegrityError("Missing/duplicated evaluation cases")
        if sum(int(r["length"]) for r in rows) != costs.environment_steps:
            raise IntegrityError("Evaluation cost mismatch")
        comparison = None
        if q["kind"] == "technical_known_policy":
            ref = q["known_outcome"]
            if file_sha256(Path(ref["path"])) != ref["sha256"]:
                raise IntegrityError("Known result changed")
            with Path(ref["path"]).open(encoding="utf-8-sig") as f:
                original = {(r["task"], int(r["episode_index"])): r for r in csv.DictReader(f)}
            for r in rows:
                old = original[r["task"], int(r["episode_index"])]
                for k in ("seed", "initial_state_hash", "success", "length"):
                    if r[k] != old[k]:
                        raise IntegrityError("Known policy replay mismatch: "+k)
                if float(r["return"]) != float(old["return"]):
                    raise IntegrityError("Known policy return not exactly reproduced")
            comparison = {"cases": len(rows), "exact_success_length_return_initial_state_match": True}
        scores = {t: sum(int(r["success"]) for r in rows if r["task"] == t)/q["cases_per_task"] for t in TASKS}
        result = dict(id=q["id"], kind=q["kind"], original_seed=q["original_seed"],
                      continuation=q["continuation"], continuation_rng_seed=q["continuation_rng_seed"],
                      condition="dose625", horizon=q["horizon"], absolute_step=engine.model.num_timesteps,
                      checkpoint=q["checkpoint"], bank=q["bank"],
                      evaluation_state_unchanged=True, original_checkpoint_files_unchanged=True,
                      full_restore_verified=True, known_policy_comparison=comparison,
                      episodes_path=str(out/"evaluation_episodes.csv"),
                      episodes_sha256=file_sha256(out/"evaluation_episodes.csv"),
                      evaluation=dict(episodes=len(rows), environment_steps=costs.environment_steps,
                                      success_by_task=scores, macro_success=sum(scores.values())/4,
                                      purpose="Research measurement only; no free online diagnostic input"))
        write_json(out/"result.json", result)
        progress("complete")
    except BaseException as exc:
        error = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
        write_json(out/"error.json", error)
        traceback.print_exc()
    finally:
        if engine is not None:
            engine.close()
        write_json(out/"costs.json", dict(status="failed" if error else "completed", costs=costs.snapshot(),
                                         wall_seconds=time.perf_counter()-start, cpu_seconds=time.process_time()-cpu,
                                         research=q["kind"] == "research_8k_evaluation", gpu_busy_seconds=None))
    return 1 if error else 0


if __name__ == "__main__":
    raise SystemExit(main())
