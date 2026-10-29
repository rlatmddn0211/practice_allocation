"""Immutable inputs, RNG-only forks, cost boundaries and provenance."""
import copy
import csv
import gc
import json
import os
import pickle
import uuid
from datetime import datetime, timezone
from pathlib import Path

os.environ["PRACTICE_SUITE"] = "B"
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
import numpy as np
import torch
from practice_allocation.core import (
    ROOT, Config, AllocationSchedule, capture_rng, derived_seed, file_sha256,
    fingerprint, package_versions, seed_learning, source_hashes, utc_now, write_json)
from practice_allocation.study_io import (
    AuditEngine, IntegrityError, bank_sets, load_portable, read_json)

REPOSITORY = next(p for p in ROOT.parents
                  if (p/"AGENTS.md").is_file() and (p/"58_confirmation_prediction_preflight_v1").is_dir())


def unique(parent, label):
    out = Path(parent)/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                        + "_" + label + "_" + uuid.uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    return out


def atomic(path, data):
    path = Path(path)
    temp = path.with_name(path.name+"."+uuid.uuid4().hex[:8]+".tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False)+"\n",
                    encoding="utf-8")
    os.replace(temp, path)


def reference(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": file_sha256(path)}


def checked(ref):
    path = Path(ref["path"])
    if file_sha256(path) != ref["sha256"]:
        raise IntegrityError("Input changed: "+str(path))
    return path


def frozen_inputs():
    p = read_json(ROOT/"protocol.json")
    for name, key in (("protocol58.json", "scientific_protocol_sha256"),
                      ("state_manifest.json", "state_manifest_sha256"),
                      ("frozen_reference_predictions.csv", "fixed_predictions_sha256"),
                      ("proposed_jobs.csv", "proposed_jobs_sha256"),
                      ("reference_paired_outcomes.csv", "reference_outcomes_sha256"),
                      ("known_8k_outcomes.csv", "known_8k_outcomes_sha256")):
        if file_sha256(ROOT/"inputs"/name) != p[key]:
            raise IntegrityError("Frozen input changed: "+name)
    states = read_json(ROOT/"inputs/state_manifest.json")
    if len(states) != 10 or {(s["parent"], s["prefix_continuation"]) for s in states} != {
            (p, r) for p in range(41011, 41016) for r in (4201, 4202)}:
        raise IntegrityError("The ten-state set changed")
    for s in states:
        if s["packages"] != package_versions():
            raise IntegrityError("Dependency mismatch")
    lookup = {(s["parent"], s["prefix_continuation"]): s for s in states}
    previous_roots = {s[k] for s in states for k in ("old_continuation_rng_seed", "proposed_new_future_root_seed")}
    jobs = read_csv(ROOT/"inputs/proposed_jobs.csv")
    if len(jobs) != 20 or [int(j["proposed_order"]) for j in jobs] != list(range(1, 21)):
        raise IntegrityError("Frozen job count/order changed")
    futures = []
    for job in jobs:
        parent, prefix, fid = (int(job[k]) for k in ("parent", "prefix", "future_id"))
        base = lookup[parent, prefix]
        root = int(job["root_seed"])
        schedule = int(job["schedule_seed"])
        expected = int(np.random.SeedSequence([570202, 57, parent, prefix, fid]).generate_state(1)[0])
        if fid not in (3, 4) or root != expected or schedule != derived_seed(root, 10) or root in previous_roots:
            raise IntegrityError("F3/F4 root differs from frozen mapping")
        if (job["checkpoint_path"] != base["checkpoint"]["path"]
                or job["checkpoint_manifest_sha256"] != base["checkpoint"]["manifest_sha256"]
                or job["bank_path"] != base["bank"]["path"] or job["bank_sha256"] != base["bank"]["sha256"]
                or int(job["training_steps"]) != 32000 or int(job["evaluation_cap"]) != 200000):
            raise IntegrityError("F3/F4 job source or budget changed")
        future = copy.deepcopy(base)
        future.update(reference_future2_root_seed=base["proposed_new_future_root_seed"],
                      reference_future2_schedule_seed=base["proposed_schedule_seed"],
                      proposed_new_future_root_seed=root, proposed_schedule_seed=schedule,
                      future_id=fid, proposed_order=int(job["proposed_order"]))
        futures.append(future)
    if (len({s["proposed_new_future_root_seed"] for s in futures}) != 20 or
            {(s["parent"], s["prefix_continuation"], s["future_id"]) for s in futures} !=
            {(parent, prefix, fid) for parent in range(41011, 41016) for prefix in (4201, 4202) for fid in (3, 4)}):
        raise IntegrityError("F3/F4 coverage or unique roots changed")
    return p, futures


def config_for(state):
    """Read only trusted, hash-checked repository checkpoint metadata."""
    cp = Path(state["checkpoint"]["path"])
    if file_sha256(cp/"checkpoint_manifest.json") != state["checkpoint"]["manifest_sha256"]:
        raise IntegrityError("Checkpoint manifest mismatch")
    manifest = read_json(cp/"checkpoint_manifest.json")
    if manifest["step"] != 208000:
        raise IntegrityError("Not an 8k state")
    for name, h in manifest["files"].items():
        if Path(name).name != name or file_sha256(cp/name) != h:
            raise IntegrityError("Checkpoint binary mismatch: "+name)
    with (cp/"collector_and_rng.pkl").open("rb") as handle:
        saved = pickle.load(handle)
    config = Config(**saved["config"])
    config.validate()
    return config


def load_state(state, costs, out=None):
    config = config_for(state)
    engine = load_portable(state["checkpoint"], config, costs, AuditEngine)
    if not engine.at_boundary or engine.model.num_timesteps != 208000:
        raise IntegrityError("Wrong checkpoint boundary")
    if engine.schedule.candidate != "dose625" or engine.model.num_timesteps <= config.learning_starts:
        raise IntegrityError("Wrong schedule or warmup active")
    if engine.model.replay_buffer.branch_start_step != 200000:
        raise IntegrityError("Original replay branch boundary changed")
    if engine.reset_root != state["old_continuation_rng_seed"]:
        raise IntegrityError("Wrong old-future RNG root")
    _, all_states = frozen_inputs()
    banks = {s["bank"]["path"]: s["bank"] for s in all_states}
    engine.forbidden = bank_sets(list(banks.values()))
    if out is not None:
        engine.audit_path = Path(out)/"training_reset_audit.csv"
    return engine


def nonrandom_fingerprints(engine):
    collector = copy.deepcopy(engine.boundary_state())
    collector.pop("reset_root")
    collector["schedule"].pop("rng")
    values = engine.fingerprints()
    return {
        "learning": values["learning"], "replay": values["replay"],
        "collector_excluding_active_rng": fingerprint(collector),
        "config": fingerprint(engine.config.to_dict()),
    }


def fork_future(engine, state):
    before = nonrandom_fingerprints(engine)
    old_rng = capture_rng()
    old_schedule = fingerprint(engine.schedule.rng.bit_generator.state)
    old_root = engine.reset_root
    root = state["proposed_new_future_root_seed"]
    # Do not call start_branch: its reset of visits/replay boundary is forbidden.
    engine.reset_root = root
    engine.schedule.rng.bit_generator.state = copy.deepcopy(
        np.random.default_rng(state["proposed_schedule_seed"]).bit_generator.state)
    seed_learning(root)
    after = nonrandom_fingerprints(engine)
    new_rng = capture_rng()
    changed = {k: fingerprint(old_rng[k]) != fingerprint(new_rng[k]) for k in old_rng}
    if before != after or root == old_root or not all(changed.values()):
        raise IntegrityError("RNG fork changed learned state or failed to change RNG streams")
    if old_schedule == fingerprint(engine.schedule.rng.bit_generator.state):
        raise IntegrityError("Schedule RNG did not change")
    return {"preserved_before": before, "preserved_after": after, "root_before": old_root,
            "root_after": root, "global_streams_changed": changed,
            "schedule_rng_changed": True, "full_fingerprints_after": engine.fingerprints()}


def expected_order(engine, episodes):
    clone = AllocationSchedule.from_state(engine.schedule.state())
    return [clone.next_task() for _ in range(episodes)]


def reserve(costs, maximum_additional, cap):
    if costs.environment_steps + maximum_additional > cap:
        raise IntegrityError("Environment step cap would be exceeded")


def close_engine(engine):
    if engine is not None:
        engine.close()
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def verify_input_files(state):
    cp = Path(state["checkpoint"]["path"])
    manifest = read_json(cp/"checkpoint_manifest.json")
    if file_sha256(cp/"checkpoint_manifest.json") != state["checkpoint"]["manifest_sha256"]:
        raise IntegrityError("Original manifest changed")
    for name, h in manifest["files"].items():
        if file_sha256(cp/name) != h:
            raise IntegrityError("Original checkpoint changed: "+name)
    checked(state["bank"])
