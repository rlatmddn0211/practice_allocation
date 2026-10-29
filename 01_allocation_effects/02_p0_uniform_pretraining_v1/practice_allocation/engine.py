"""Audited collection, exact boundary checkpoints, and independent continuations."""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import pickle
import time
from pathlib import Path
from contextlib import nullcontext

import numpy as np
import torch

from .core import (TASKS, AllocationSchedule, Config, capture_rng, derived_seed,
                   file_sha256, fingerprint, package_versions, restore_rng,
                   seed_learning, source_hashes, utc_now, write_json)
from .environment import CostCounter, TaskEpisode
from .learning import AuditedSAC, attach_logger, create_model, learning_state


class Engine:
    def __init__(self, config: Config, costs: CostCounter, model=None):
        self.config, self.costs = config, costs
        self.model = create_model(config) if model is None else model
        self.reset_root = config.seed
        self.schedule = AllocationSchedule("U", derived_seed(config.seed, 10))
        self.task_visits = np.zeros(4, dtype=np.int64)
        self.collected_steps = np.zeros(4, dtype=np.int64)
        self.warmup_rng = np.random.default_rng(derived_seed(config.seed, 30))
        self.episode = None
        self.observation = None
        self.episode_return = 0.0
        self.last_episode = None

    @property
    def at_boundary(self) -> bool:
        return self.episode is None and self.observation is None

    def boundary_state(self) -> dict:
        if not self.at_boundary:
            raise RuntimeError("Full checkpoints are allowed only after a completed episode and update.")
        return {
            "reset_root": self.reset_root, "schedule": self.schedule.state(),
            "task_visits": self.task_visits.copy(), "collected_steps": self.collected_steps.copy(),
            "warmup_rng": copy.deepcopy(self.warmup_rng.bit_generator.state),
            "last_episode": copy.deepcopy(self.last_episode),
        }

    def restore_boundary_state(self, state: dict) -> None:
        self.reset_root = state["reset_root"]
        self.schedule = AllocationSchedule.from_state(state["schedule"])
        self.task_visits = state["task_visits"].copy()
        self.collected_steps = state["collected_steps"].copy()
        self.warmup_rng.bit_generator.state = copy.deepcopy(state["warmup_rng"])
        self.last_episode = copy.deepcopy(state["last_episode"])

    def start_branch(self, candidate: str, repeat_seed: int) -> None:
        if not self.at_boundary:
            raise RuntimeError("A branch must start at an episode boundary.")
        if self.model.num_timesteps <= self.config.learning_starts:
            raise RuntimeError("A branch cannot restart warm-up.")
        self.schedule = AllocationSchedule(candidate, derived_seed(repeat_seed, 10))
        self.reset_root = repeat_seed
        self.task_visits[:] = 0
        self.warmup_rng = np.random.default_rng(derived_seed(repeat_seed, 30))
        self.model.replay_buffer.branch_start_step = self.model.num_timesteps
        # Only continuation random streams are changed; learned state is intact.
        seed_learning(repeat_seed)

    def step(self) -> dict:
        if self.at_boundary:
            task = self.schedule.next_task()
            seed = derived_seed(self.reset_root, 20, task, int(self.task_visits[task]))
            self.task_visits[task] += 1
            self.episode = TaskEpisode(task, seed, self.costs)
            self.observation = self.episode.observation.copy()
            self.episode_return = 0.0

        model, replay = self.model, self.model.replay_buffer
        before_obs = self.observation.copy()
        task = self.episode.task_index
        if model.num_timesteps < self.config.learning_starts:
            action = self.warmup_rng.uniform(-1, 1, size=4).astype(np.float32)
        else:
            action, _ = model.predict(before_obs, deterministic=False)
        scaled_action = model.policy.scale_action(action)
        action = model.policy.unscale_action(scaled_action)
        next_obs, reward, terminated, truncated, info = self.episode.step(action)
        replay.add(before_obs[None], next_obs[None], scaled_action[None],
                   np.array([reward], dtype=np.float32), np.array([terminated or truncated]),
                   [{"TimeLimit.truncated": truncated and not terminated}])
        model.num_timesteps += 1
        self.collected_steps[task] += 1
        self.episode_return += reward
        self.observation = next_obs
        updated = model.num_timesteps > self.config.learning_starts
        if updated:
            previous_updates = model._n_updates
            try:
                model.train(gradient_steps=1, batch_size=self.config.batch_size)
            finally:
                self.costs.train_iterations += model._n_updates - previous_updates
        expected_updates = max(0, model.num_timesteps - self.config.learning_starts)
        if model._n_updates != expected_updates or replay.total_added != model.num_timesteps:
            raise RuntimeError("Transition/update counters violate the contract.")

        record = {
            "step": model.num_timesteps, "task": task, "observation": before_obs,
            "action": action.copy(), "next_observation": next_obs.copy(), "reward": reward,
            "terminated": terminated, "truncated": truncated, "success": bool(info["success"]),
            "initial_state_hash": self.episode.initial_state_hash,
            "replay_pos": replay.pos, "updates": model._n_updates,
            "sampled_indices": replay.last_indices.copy() if updated else np.empty(0, dtype=np.int64),
            "losses": dict(model.last_update_metrics) if updated else {},
        }
        if truncated:
            self.last_episode = {
                "task": TASKS[task], "success": self.episode.any_success,
                "return": self.episode_return, "length": self.episode.steps,
                "initial_state_hash": self.episode.initial_state_hash,
            }
            self.episode.close()
            self.episode = None
            self.observation = None
        return record

    def train_steps(self, steps: int, label: str, metrics_path: Path, trace=False,
                    episodes_path: Path | None = None) -> dict:
        started = time.perf_counter()
        digest = hashlib.sha256()
        first_record = None
        start_steps, start_updates = self.model.num_timesteps, self.model._n_updates
        fields = ["segment", "step", "updates", "replay_size", "replay_pos", "task", "reward", "success",
                  "actor_loss", "critic_loss", "entropy_loss", "entropy_coefficient",
                  "critic_0_abs_td_error", "critic_1_abs_td_error", "batch_new_fraction",
                  *[f"collected_{t}" for t in TASKS], *[f"sampled_{t}" for t in TASKS],
                  *[f"last_batch_{t}" for t in TASKS], "segment_seconds"]
        is_new = not metrics_path.exists()
        episode_new = episodes_path is not None and not episodes_path.exists()
        episode_context = episodes_path.open("a", newline="", encoding="utf-8") if episodes_path else nullcontext()
        with metrics_path.open("a", newline="", encoding="utf-8") as handle, episode_context as episode_handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            if is_new:
                writer.writeheader()
            episode_writer = None
            if episode_handle is not None:
                episode_writer = csv.DictWriter(episode_handle, fieldnames=[
                    "step", "episode", "task", "success", "return", "length", "initial_state_hash"])
                if episode_new:
                    episode_writer.writeheader()
            for index in range(steps):
                record = self.step()
                if record["truncated"] and episode_writer is not None:
                    episode_writer.writerow({"step": record["step"],
                                             "episode": record["step"] // self.config.episode_steps,
                                             **self.last_episode})
                    episode_handle.flush()
                if trace:
                    digest.update(fingerprint(record).encode())
                if first_record is None:
                    first_record = {"task": TASKS[record["task"]],
                                    "observation_hash": fingerprint(record["observation"]),
                                    "action_hash": fingerprint(record["action"]),
                                    "initial_state_hash": record["initial_state_hash"],
                                    "updates": record["updates"]}
                if self.model.num_timesteps % self.config.log_every_steps == 0 or index == steps - 1:
                    replay = self.model.replay_buffer
                    row = {"segment": label, "step": record["step"], "updates": record["updates"],
                           "replay_size": replay.size(), "replay_pos": replay.pos,
                           "task": TASKS[record["task"]], "reward": record["reward"], "success": record["success"],
                           "batch_new_fraction": replay.last_new_fraction, **record["losses"],
                           "segment_seconds": time.perf_counter() - started}
                    row.update({f"collected_{t}": int(self.collected_steps[i]) for i, t in enumerate(TASKS)})
                    row.update({f"sampled_{t}": int(replay.sampled_task_counts[i]) for i, t in enumerate(TASKS)})
                    row.update({f"last_batch_{t}": int(replay.last_task_counts[i]) for i, t in enumerate(TASKS)})
                    writer.writerow(row)
                    handle.flush()
                if (index + 1) % 1000 == 0:
                    print(f"  {label}: {index + 1}/{steps} transitions, {self.model._n_updates} total updates", flush=True)
        elapsed = time.perf_counter() - started
        return {"steps": self.model.num_timesteps - start_steps,
                "updates": self.model._n_updates - start_updates, "seconds": elapsed,
                "steps_per_second": steps / elapsed, "trace_sha256": digest.hexdigest() if trace else None,
                "first_record": first_record}

    def fingerprints(self) -> dict:
        return {
            "learning": fingerprint(learning_state(self.model)),
            "replay": fingerprint(self.model.replay_buffer.state_for_hash()),
            "collector": fingerprint(self.boundary_state()),
            "rng": fingerprint(capture_rng()),
        }

    def close(self) -> None:
        if self.episode is not None:
            self.episode.close()
            self.episode = None
            self.observation = None


def save_checkpoint(engine: Engine, directory: Path) -> dict:
    collector = engine.boundary_state()
    directory.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    rng = capture_rng()
    before = engine.fingerprints()
    engine.model.save(directory / "model.zip")
    engine.model.save_replay_buffer(directory / "replay.pkl")
    state = {"config": engine.config.to_dict(), "collector": collector, "rng": rng}
    with (directory / "collector_and_rng.pkl").open("xb") as handle:
        pickle.dump(state, handle, protocol=pickle.HIGHEST_PROTOCOL)
    if engine.fingerprints() != before:
        raise RuntimeError("Checkpoint creation changed training state.")
    manifest = {
        "schema_version": 1, "created_at": utc_now(), "boundary": "after transition, update, episode close; before next reset",
        "step": engine.model.num_timesteps, "updates": engine.model._n_updates,
        "replay_size": engine.model.replay_buffer.size(), "replay_pos": engine.model.replay_buffer.pos,
        "state_fingerprints": before, "config_hash": fingerprint(engine.config.to_dict()),
        "packages": package_versions(), "source_hashes": source_hashes(),
        "files": {name: file_sha256(directory / name) for name in ("model.zip", "replay.pkl", "collector_and_rng.pkl")},
        "seconds": time.perf_counter() - started,
    }
    write_json(directory / "checkpoint_manifest.json", manifest)
    return manifest


def load_checkpoint(directory: Path, costs: CostCounter) -> Engine:
    manifest = json.loads((directory / "checkpoint_manifest.json").read_text(encoding="utf-8"))
    if manifest["schema_version"] != 1 or manifest["packages"] != package_versions() or manifest["source_hashes"] != source_hashes():
        raise RuntimeError("Checkpoint schema, dependencies, or source differ from the saved version.")
    for name, expected in manifest["files"].items():
        if Path(name).name != name or file_sha256(directory / name) != expected:
            raise RuntimeError(f"Checkpoint integrity failure: {name}")
    # These files are locally generated trusted artifacts; never load an untrusted pickle/zip.
    with (directory / "collector_and_rng.pkl").open("rb") as handle:
        state = pickle.load(handle)
    config = Config(**state["config"])
    config.validate()
    if fingerprint(config.to_dict()) != manifest["config_hash"]:
        raise RuntimeError("Checkpoint configuration hash mismatch.")
    model = AuditedSAC.load(directory / "model.zip", device=config.device)
    model.load_replay_buffer(directory / "replay.pkl")
    attach_logger(model)
    engine = Engine(config, costs, model=model)
    engine.restore_boundary_state(state["collector"])
    restore_rng(state["rng"])
    if engine.fingerprints() != manifest["state_fingerprints"]:
        raise RuntimeError("Restored checkpoint does not match the saved complete state.")
    return engine
