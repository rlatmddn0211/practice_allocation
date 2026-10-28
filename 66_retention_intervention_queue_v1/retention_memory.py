"""Frozen training-only memories, with matched task/age/episode support.

Construction is WITHOUT replacement (episodes and transitions within episodes).
The controller's independent training-time minibatch sampling may separately be
WITH replacement. Neither operation calls or changes SAC's replay sampler.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from practice_allocation.core import TASKS, fingerprint


class MemoryIntegrityError(RuntimeError):
    pass


def _bool(value):
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.lower() in ("true", "false", "0", "1"):
        return value.lower() in ("true", "1")
    raise MemoryIntegrityError("An episode success label is missing or invalid.")


def _episode_rows(metadata, source_step, episode_steps):
    if isinstance(metadata, (str, Path)):
        metadata = json.loads(Path(metadata).read_text(encoding="utf-8-sig"))
    if not isinstance(metadata, dict) or not isinstance(metadata.get("episode_rows"), list):
        raise MemoryIntegrityError("Expected the frozen episode_rows training artifact.")
    result = {}
    for row in metadata["episode_rows"]:
        end = int(row.get("end_step", row.get("step", -1)))
        if end <= 0 or end % episode_steps or end > source_step:
            raise MemoryIntegrityError("Episode metadata contains an incomplete or future episode.")
        task = row.get("task")
        if isinstance(task, (int, np.integer)) and 0 <= task < len(TASKS):
            task = TASKS[int(task)]
        if task not in TASKS:
            raise MemoryIntegrityError("Invalid task in the training episode artifact.")
        value = {"task": task, "success": _bool(row.get("success", row.get("success_episode")))}
        if end in result and result[end] != value:
            raise MemoryIntegrityError("Conflicting labels for the same training episode.")
        result[end] = value
    return result, fingerprint(metadata)


def _pack(replay, rows, arm_name, metadata):
    # row = (replay_index, episode_end, task_index, age_bin, known_success_or_none)
    indices = np.asarray([row[0] for row in rows], dtype=np.int64)
    observations = np.asarray(replay.observations[indices, 0], dtype=np.float32).copy()
    result = {
        "observations": observations,
        "replay_indices": indices,
        "birth_steps": np.asarray(replay.birth_steps[indices], dtype=np.int64).copy(),
        "episode_end_steps": np.asarray([row[1] for row in rows], dtype=np.int64),
        "task_indices": np.asarray([row[2] for row in rows], dtype=np.int64),
        "age_bin_indices": np.asarray([row[3] for row in rows], dtype=np.int64),
        "success_labels": np.asarray([-1 if row[4] is None else int(row[4]) for row in rows], dtype=np.int8),
    }
    if not len(observations) or observations.ndim != 2 or not np.all(np.isfinite(observations)):
        raise MemoryIntegrityError("The approved fixed memory has no usable finite observations.")
    if len(np.unique(indices)) != len(indices):
        raise MemoryIntegrityError("Fixed-memory construction repeated a transition.")
    result["fingerprint"] = fingerprint(result)
    result["provenance"] = {"arm_memory": arm_name, **metadata,
                            "observations_sha256": fingerprint(observations),
                            "memory_sha256": result["fingerprint"],
                            "transitions": int(len(indices)),
                            "unique_episodes": int(len(np.unique(result["episode_end_steps"]))),
                            "known_success_transitions": int(np.sum(result["success_labels"] == 1)),
                            "known_unsuccessful_transitions": int(np.sum(result["success_labels"] == 0)),
                            "unknown_label_transitions": int(np.sum(result["success_labels"] < 0))}
    return result


def build_memories(engine, episode_metadata, parent, config):
    """Return general/success memories selected once from the full restored S.

    Required config: age_bins, episodes_per_stratum, observations_per_episode,
    memory_seed, zero_success_fallback='shared_general'. Equal-width age bins
    cover the CURRENT valid replay. A complete retained episode must fit wholly
    inside one age bin; partial/boundary episodes are reported and excluded.
    Each nonempty-success stratum uses k=min(cap, success episodes). General C
    samples k episodes from all eligible episodes, including successes. D samples
    k successful episodes. With zero success support C/D share exactly the same
    general episodes AND observations; this fallback is reported, never hidden.
    """
    required = ("age_bins", "episodes_per_stratum", "observations_per_episode",
                "memory_seed", "zero_success_fallback")
    if any(key not in config for key in required):
        raise ValueError(f"Memory configuration requires {required}.")
    if config["zero_success_fallback"] != "shared_general":
        raise ValueError("Only the explicitly approved shared_general fallback is supported.")
    n_bins, cap, n_obs = (int(config[key]) for key in required[:3])
    if min(n_bins, cap, n_obs) <= 0:
        raise ValueError("Memory counts must be positive.")
    if not engine.at_boundary:
        raise MemoryIntegrityError("Build memories only at the restored full S boundary.")
    replay, source_step = engine.model.replay_buffer, int(engine.model.num_timesteps)
    episode_steps = int(engine.config.episode_steps)
    if source_step % episode_steps or n_obs > episode_steps:
        raise MemoryIntegrityError("Invalid episode boundary or observations-per-episode budget.")
    if replay.n_envs != 1 or replay.optimize_memory_usage or replay.total_added != source_step:
        raise MemoryIntegrityError("The frozen single-environment ordinary replay contract changed.")
    size = int(replay.size())
    indices = np.arange(size, dtype=np.int64)
    births = np.asarray(replay.birth_steps[:size], dtype=np.int64)
    if (not size or np.any(births <= 0) or np.any(births > source_step) or
            len(np.unique(births)) != size):
        raise MemoryIntegrityError("Replay birth provenance is incomplete or duplicated.")
    task_ids = np.asarray(replay.observations[:size, 0, -len(TASKS):]).argmax(axis=1)
    labels, label_hash = _episode_rows(episode_metadata, source_step, episode_steps)
    ages = source_step - births
    width = int(math.ceil((int(ages.max()) + 1) / n_bins))
    bin_ids = np.minimum(ages // width, n_bins - 1)
    episode_ends = ((births - 1) // episode_steps + 1) * episode_steps
    pools = {(task, age_bin): [] for task in range(len(TASKS)) for age_bin in range(n_bins)}
    exclusions = []
    for end in sorted(np.unique(episode_ends).tolist()):
        selected = indices[episode_ends == end]
        episode_births = births[selected]
        reason = None
        if len(selected) != episode_steps or not np.array_equal(
                np.sort(episode_births), np.arange(end - episode_steps + 1, end + 1)):
            reason = "not_a_complete_retained_episode"
        elif len(np.unique(task_ids[selected])) != 1:
            raise MemoryIntegrityError("A historical episode contains multiple task IDs.")
        elif len(np.unique(bin_ids[selected])) != 1:
            reason = "episode_crosses_age_bin_boundary"
        if reason:
            exclusions.append({"episode_end": int(end), "reason": reason,
                               "retained_transitions": len(selected)})
            continue
        task, age_bin = int(task_ids[selected[0]]), int(bin_ids[selected[0]])
        label = labels.get(int(end))
        if label is not None and label["task"] != TASKS[task]:
            raise MemoryIntegrityError("Historical labels disagree with actual replay task IDs.")
        pools[(task, age_bin)].append({"end": int(end), "indices": selected,
                                      "success": label["success"] if label else None})
    rng = np.random.default_rng(int(config["memory_seed"]))
    general_rows, success_rows, support = [], [], []

    def append_episode(destination, episode, task, age_bin):
        chosen = rng.choice(episode["indices"], size=n_obs, replace=False)
        destination.extend((int(index), episode["end"], task, age_bin, episode["success"])
                           for index in chosen)

    for task in range(len(TASKS)):
        for age_bin in range(n_bins):
            pool = pools[(task, age_bin)]
            success_pool = [episode for episode in pool if episode["success"] is True]
            fallback = not success_pool
            k = min(cap, len(success_pool) if success_pool else len(pool))
            start_c, start_d = len(general_rows), len(success_rows)
            if k:
                c_episodes = [pool[int(i)] for i in rng.choice(len(pool), size=k, replace=False)]
                for episode in c_episodes:
                    append_episode(general_rows, episode, task, age_bin)
                if fallback:
                    success_rows.extend(general_rows[start_c:])
                    d_episodes = c_episodes
                else:
                    d_episodes = [success_pool[int(i)] for i in rng.choice(len(success_pool), size=k, replace=False)]
                    for episode in d_episodes:
                        append_episode(success_rows, episode, task, age_bin)
            else:
                c_episodes, d_episodes = [], []
            support.append({
                "task": TASKS[task], "age_bin": age_bin,
                "age_min": age_bin * width,
                "age_max": min((age_bin + 1) * width - 1, int(ages.max())),
                "eligible_general_episodes": len(pool),
                "eligible_known_success_episodes": len(success_pool),
                "eligible_known_unsuccessful_episodes": sum(e["success"] is False for e in pool),
                "eligible_unknown_episodes": sum(e["success"] is None for e in pool),
                "selected_episodes_per_arm": k, "observations_per_episode": n_obs,
                "general_episode_ends": [e["end"] for e in c_episodes],
                "success_episode_ends": [e["end"] for e in d_episodes],
                "general_transition_count": len(general_rows) - start_c,
                "success_transition_count": len(success_rows) - start_d,
                "shared_general_fallback": bool(fallback and k),
                "no_eligible_general_support": not bool(pool),
                "same_observation_fallback": bool(fallback and k),
            })
    if len(general_rows) != len(success_rows):
        raise MemoryIntegrityError("C/D fixed memories have unmatched transition counts.")
    common = {"schema_version": 1, "parent": int(parent), "source_step": source_step,
              "source_updates": int(engine.model._n_updates),
              "memory_seed": int(config["memory_seed"]),
              "age_bins": n_bins, "age_bin_width": width,
              "age_rule": "source_step - birth_step; complete episodes wholly within one equal-width age bin",
              "episode_cap_per_stratum": cap, "observations_per_episode": n_obs,
              "construction_sampling": "episodes and transitions without replacement",
              "general_pool_includes_successes": True,
              "zero_success_fallback": config["zero_success_fallback"],
              "episode_metadata_sha256": label_hash,
              "valid_replay_birth_min": int(births.min()), "valid_replay_birth_max": int(births.max()),
              "eligible_episode_exclusions": exclusions,
              "support": support,
              "shared_fallback_transitions_per_arm": sum(
                  row["general_transition_count"] for row in support if row["shared_general_fallback"])}
    general = _pack(replay, general_rows, "general", common)
    success = _pack(replay, success_rows, "success", common)
    for task in range(len(TASKS)):
        for age_bin in range(n_bins):
            c = (general["task_indices"] == task) & (general["age_bin_indices"] == age_bin)
            d = (success["task_indices"] == task) & (success["age_bin_indices"] == age_bin)
            if int(c.sum()) != int(d.sum()):
                raise MemoryIntegrityError("C/D task-by-age observation counts differ.")
    return {"general": general, "success": success, "support": support,
            "provenance": {**common, "general_memory_sha256": general["fingerprint"],
                           "success_memory_sha256": success["fingerprint"],
                           "shared_replay_indices": len(np.intersect1d(
                               general["replay_indices"], success["replay_indices"]))}}
