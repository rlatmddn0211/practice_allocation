"""Passive baseline telemetry; no environment calls or learner updates.

Attach only AFTER exact checkpoint restoration and the approved RNG fork.  The
learner's four frozen source files are deliberately not imported by path or
modified.  Update observers are present only during ``BaselineEngine.step`` and
are always removed before a worker may serialize a checkpoint.
"""
from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
import copy
import json
import math
from pathlib import Path
import time

import numpy as np
import torch

from practice_allocation.core import TASKS, capture_rng, fingerprint, restore_rng, utc_now, write_json
from practice_allocation.study_io import AuditEngine, IntegrityError


SCHEMA_VERSION = 1


def _array(value):
    if isinstance(value, torch.Tensor):
        return value.detach().cpu().numpy().copy()
    return np.asarray(value).copy()


def _stats(values, quantiles=True):
    values = np.asarray(values, dtype=np.float64).reshape(-1)
    if not len(values):
        return {"n": 0, "sum": 0.0, "mean": None, "std": None,
                "min": None, "max": None,
                **({f"p{p:02d}": None for p in (5, 25, 50, 75, 95)} if quantiles else {})}
    if not np.all(np.isfinite(values)):
        raise IntegrityError("Non-finite passive telemetry quantity.")
    result = {"n": int(len(values)), "sum": float(values.sum()),
              "mean": float(values.mean()), "std": float(values.std(ddof=0)),
              "min": float(values.min()), "max": float(values.max())}
    if quantiles:
        result.update({f"p{p:02d}": float(np.quantile(values, p / 100))
                       for p in (5, 25, 50, 75, 95)})
    return result


def _truth(value):
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.lower() in ("true", "false", "0", "1"):
        return value.lower() in ("true", "1")
    raise ValueError(f"Invalid episode success label: {value!r}")


def _gaussian_kl(mu_a, log_std_a, mu_b, log_std_b):
    """KL(N_a || N_b), summed across action dimensions, in float64."""
    return np.sum(log_std_b - log_std_a +
                  0.5 * (np.exp(2 * (log_std_a - log_std_b)) +
                         (mu_a - mu_b) ** 2 * np.exp(-2 * log_std_b) - 1), axis=-1)


class BaselineTelemetry:
    """Observe actual SAC batches and fixed training-state policy panels.

    ``episode_metadata`` accepts the preparation artifact containing
    ``episode_rows``, a list of rows, or a mapping keyed by episode end step.
    Rows need ``end_step`` (or ``step``), ``task`` and ``success``. Missing labels
    remain explicitly unknown. Transition birth step b belongs to the episode
    ending at ceil(b / episode_steps) * episode_steps.

    ``fixed_panel`` is {"observations": array[N, obs_dim], "task_indices":
    optional array[N], "provenance": optional JSON object}. A task->array mapping
    is also accepted. Selection belongs to the worker and must be success-blind.
    No replay samples are drawn by this class.
    """

    def __init__(self, output_dir, episode_metadata=None, fixed_panel=None, *,
                 enabled=True, probe_seed=640202, window_steps=250,
                 panel_every=1000, entropy_samples=32, metadata=None):
        self.output_dir = Path(output_dir)
        self.episode_metadata = episode_metadata
        self.fixed_panel_input = fixed_panel
        self.enabled = bool(enabled)
        self.probe_seed = int(probe_seed)
        self.window_steps = int(window_steps)
        self.panel_every = int(panel_every)
        self.entropy_samples = int(entropy_samples)
        if (self.window_steps != 250 or self.panel_every != 1000 or
                self.entropy_samples < 1):
            raise ValueError("The frozen cadence is 250-step windows and 1k-step panels.")
        self.metadata = copy.deepcopy(metadata or {})
        self.engine = None
        self._handles = []
        self._streams = {}
        self._distribution = None
        self._original_log_prob = None
        self._original_log_prob_instance = None
        self._had_log_prob_instance = False
        self._suspend_depth = 0
        self._pending = None
        self._known_episodes = {}
        self._learning_values = defaultdict(list)
        self._task_values = {task: defaultdict(list) for task in TASKS}
        self._sample_chunks = []
        self._collection_counts = np.zeros(len(TASKS), dtype=np.int64)
        self._collection_total_counts = np.zeros(len(TASKS), dtype=np.int64)
        self._collected_baseline = None
        self._episode = None
        self._window_steps = 0
        self._window_first = None
        self._closed = False
        self._resume_state = None
        self._counts = {"observed_steps": 0, "observed_updates": 0,
                        "windows": 0, "episodes": 0, "policy_probes": 0,
                        "sampled_transitions": 0, "extra_environment_steps": 0,
                        "extra_learner_updates": 0}
        self._wall_seconds = 0.0
        self._cpu_seconds = 0.0

    def attach(self, engine):
        """Initialize passive state after load/fork, at an episode boundary."""
        if self.engine is not None:
            raise RuntimeError("Telemetry may be attached only once.")
        if not engine.at_boundary:
            raise IntegrityError("Telemetry must attach at the restored episode boundary.")
        self.engine = engine
        engine.telemetry = self
        self.start_step = int(engine.model.num_timesteps)
        self.start_updates = int(engine.model._n_updates)
        self._collected_baseline = _array(engine.collected_steps).astype(np.int64)
        self.episode_steps = int(engine.config.episode_steps)
        if self.episode_steps != 500 or self.start_step % self.episode_steps:
            raise IntegrityError("Expected a full 500-step episode boundary.")
        if not self.enabled:
            return self
        before_rng = fingerprint(capture_rng())
        self._load_labels()
        self.panel, self.panel_tasks, panel_provenance = self._prepare_panel()
        attached_at_step = self.start_step
        if self._resume_state is not None:
            self._apply_resume_state(engine)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        # Exclusive creation protects completed and failed telemetry attempts.
        for name in ("windows_250", "training_episodes", "policy_drift_1000"):
            self._streams[name] = (self.output_dir / f"{name}.jsonl").open(
                "x", encoding="utf-8", newline="\n")
        self._write_metadata(panel_provenance, attached_at_step)
        if self._resume_state is None:
            self._frozen_parameters = None
            self._previous_parameters = None
            self._previous_probe_step = None
            self._probe_policy(engine)
        if fingerprint(capture_rng()) != before_rng:
            raise IntegrityError("Telemetry attachment changed a training RNG.")
        return self

    def _load_labels(self):
        data = self.episode_metadata
        if isinstance(data, (str, Path)):
            data = json.loads(Path(data).read_text(encoding="utf-8-sig"))
        self._historical_metadata_hash = fingerprint(data)
        if data is None:
            rows = []
        elif isinstance(data, dict) and "episode_rows" in data:
            rows = data["episode_rows"]
        elif isinstance(data, dict):
            rows = []
            for key, value in data.items():
                row = dict(value) if isinstance(value, dict) else {"success": value}
                row.setdefault("end_step", int(key))
                rows.append(row)
        else:
            rows = data
        for raw in rows:
            row = dict(raw)
            end = int(row.get("end_step", row.get("step", row.get("last_birth_step", -1))))
            if end <= 0 or end % self.episode_steps or end > self.start_step:
                raise IntegrityError("Historical episode labels are not past complete episodes.")
            task = row.get("task")
            if isinstance(task, (int, np.integer)):
                task = TASKS[int(task)]
            if task not in TASKS:
                raise IntegrityError("Historical episode label has an invalid task.")
            success = _truth(row.get("success", row.get("success_episode")))
            value = {"task": task, "success": success, "available_after_step": end,
                     "source": "historical_complete_training_episode"}
            if end in self._known_episodes and self._known_episodes[end] != value:
                raise IntegrityError("Conflicting historical episode labels.")
            self._known_episodes[end] = value

    def _prepare_panel(self):
        panel = self.fixed_panel_input
        if panel is None:
            raise IntegrityError("Enabled telemetry needs the frozen training-only panel.")
        provenance = {}
        if isinstance(panel, dict) and "observations" in panel:
            observations = _array(panel["observations"]).astype(np.float32, copy=False)
            task_indices = panel.get("task_indices")
            provenance = copy.deepcopy({key: value for key, value in panel.items()
                                        if key not in ("observations", "task_indices")})
        elif isinstance(panel, dict) and all(task in panel for task in TASKS):
            observations = np.concatenate([_array(panel[task]) for task in TASKS]).astype(np.float32)
            task_indices = np.concatenate([np.full(len(panel[task]), i, dtype=np.int64)
                                           for i, task in enumerate(TASKS)])
        else:
            observations = _array(panel).astype(np.float32, copy=False)
            task_indices = None
        if observations.ndim != 2 or not np.all(np.isfinite(observations)):
            raise IntegrityError("Malformed fixed training-state panel.")
        inferred = observations[:, -len(TASKS):].argmax(axis=1).astype(np.int64)
        if task_indices is None:
            task_indices = inferred
        else:
            task_indices = _array(task_indices).astype(np.int64).reshape(-1)
            if len(task_indices) != len(observations) or not np.array_equal(task_indices, inferred):
                raise IntegrityError("Fixed-panel task IDs disagree with the observation task IDs.")
        if set(task_indices.tolist()) != set(range(len(TASKS))):
            raise IntegrityError("The fixed panel must cover all four training tasks.")
        return observations.copy(), task_indices.copy(), provenance

    def _write_metadata(self, panel_provenance, attached_at_step):
        write_json(self.output_dir / "telemetry_metadata.json", {
            "schema_version": SCHEMA_VERSION, "created_at": utc_now(),
            "start_step": self.start_step, "start_updates": self.start_updates,
            "attached_at_step": attached_at_step,
            "resumed_from_sidecar": self._resume_state is not None,
            "tasks": list(TASKS), "window_steps": self.window_steps,
            "policy_probe_every_steps": self.panel_every,
            "panel_count": int(len(self.panel)),
            "panel_count_by_task": {task: int(np.sum(self.panel_tasks == i))
                                    for i, task in enumerate(TASKS)},
            "panel_observations_sha256": fingerprint(self.panel),
            "panel_provenance": panel_provenance,
            "known_complete_episode_labels_at_attachment": len(self._known_episodes),
            "historical_episode_metadata_sha256": self._historical_metadata_hash,
            "collected_steps_at_original_S": {task: int(self._collected_baseline[i])
                                              for i, task in enumerate(TASKS)},
            "probe_seed": self.probe_seed, "entropy_samples_per_panel_state": self.entropy_samples,
            "probe_rng": "private torch.Generator; all global RNG states restored; no learner draws",
            "success_label_rule": "birth b -> episode end ceil(b/500)*500; only complete episodes already known at sampling time; unknown ongoing episodes are never relabeled retrospectively",
            "replay_snapshot_rule": "all currently valid replay entries, after this window's final episode completion; distinct from sampling-time exposure labels",
            "q_target_rule": "actual sampled transitions, actual current/next actor log probabilities and pre-update alpha; actual pre-update target critic and replay-action critic forwards",
            "policy_metric_units": "unsquashed diagonal Gaussian mean/std and analytical KL; tanh-squashed differential entropy is a separate Monte Carlo quantity",
            "mean_std_definition": "population std (ddof=0); distribution quantiles from every observation in the window, no subsampling",
            "metadata": self.metadata,
        })

    def _append(self, name, row):
        row = {"schema_version": SCHEMA_VERSION, **row}
        stream = self._streams[name]
        stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
        stream.flush()

    def before_step(self, engine):
        if not self.enabled:
            return
        if self._suspend_depth:
            raise IntegrityError("A training step cannot run inside telemetry.suspended().")
        if self.engine is not engine or self._closed or self._pending is not None:
            raise RuntimeError("Invalid telemetry step lifecycle.")
        model = engine.model
        self._pending = {"step_before": int(model.num_timesteps),
                         "updates_before": int(model._n_updates),
                         "alpha_before": float(model.log_ent_coef.detach().exp().item()),
                         "log_probs": [], "target_q": [], "critic_q": [],
                         "started_wall": time.perf_counter(), "started_cpu": time.process_time()}
        distribution = model.actor.action_dist
        self._distribution = distribution
        self._had_log_prob_instance = "log_prob" in distribution.__dict__
        self._original_log_prob_instance = distribution.__dict__.get("log_prob")
        self._original_log_prob = distribution.log_prob

        def observe_log_prob(*args, **kwargs):
            result = self._original_log_prob(*args, **kwargs)
            self._pending["log_probs"].append(result.detach().clone())
            return result

        def observe_target(_module, _inputs, outputs):
            self._pending["target_q"].append(tuple(value.detach().clone() for value in outputs))

        def observe_critic(_module, _inputs, outputs):
            self._pending["critic_q"].append(tuple(value.detach().clone() for value in outputs))

        distribution.log_prob = observe_log_prob
        self._handles = [model.critic_target.register_forward_hook(observe_target),
                         model.critic.register_forward_hook(observe_critic)]

    def end_step(self):
        """Remove every temporary observer, including when the learner failed."""
        for handle in self._handles:
            handle.remove()
        self._handles = []
        if self._distribution is not None:
            if self._had_log_prob_instance:
                self._distribution.log_prob = self._original_log_prob_instance
            else:
                self._distribution.__dict__.pop("log_prob", None)
        self._distribution = None
        self._original_log_prob = None
        self._original_log_prob_instance = None

    def observe(self, record, engine):
        if not self.enabled or self._suspend_depth:
            return
        pending = self._pending
        if pending is None:
            raise RuntimeError("observe() requires before_step().")
        # Probes and output must see the original distribution object, never a
        # wrapper. This also makes all checkpoints outside step() hook-free.
        self.end_step()
        step = int(record["step"])
        if step != pending["step_before"] + 1:
            raise IntegrityError("Passive telemetry missed or duplicated a transition.")
        if self._window_first is None:
            self._window_first = step
        self._window_steps += 1
        self._collection_counts[int(record["task"])] += 1
        self._collection_total_counts[int(record["task"])] += 1
        self._counts["observed_steps"] += 1
        updated = int(record["updates"]) - pending["updates_before"]
        if updated not in (0, 1):
            raise IntegrityError("Passive telemetry requires at most one SAC update per transition.")
        if updated:
            self._observe_update(record, engine, pending)
        elif pending["log_probs"] or pending["target_q"] or pending["critic_q"]:
            raise IntegrityError("Unexpected SAC forward without an update.")
        self._observe_episode(record, engine, pending)
        if self._window_steps == self.window_steps:
            self._flush_window(engine, complete=True)
        elif self._window_steps > self.window_steps:
            raise IntegrityError("Telemetry exceeded the fixed window size.")
        if (step - self.start_step) % self.panel_every == 0:
            self._probe_policy(engine)
        self._wall_seconds += time.perf_counter() - pending["started_wall"]
        self._cpu_seconds += time.process_time() - pending["started_cpu"]
        self._pending = None

    def _sample_description(self, births, tasks, step):
        births = np.asarray(births, dtype=np.int64).reshape(-1)
        tasks = np.asarray(tasks, dtype=np.int64).reshape(-1)
        if len(births) != len(tasks) or np.any(births <= 0) or np.any(births > step):
            raise IntegrityError("Invalid replay birth metadata.")
        ends = ((births - 1) // self.episode_steps + 1) * self.episode_steps
        labels = np.full(len(births), -1, dtype=np.int8)
        for end in np.unique(ends):
            known = self._known_episodes.get(int(end))
            if known is None:
                continue
            mask = ends == end
            if np.any(tasks[mask] != TASKS.index(known["task"])):
                raise IntegrityError("Episode labels and replay task provenance disagree.")
            labels[mask] = int(known["success"])
        return {"births": births, "tasks": tasks, "ages": step - births,
                "labels": labels, "new": births > self.start_step}

    def _observe_update(self, record, engine, pending):
        if (len(pending["log_probs"]) != 2 or len(pending["target_q"]) != 1 or
                len(pending["critic_q"]) != 2):
            raise IntegrityError("SAC call structure changed; telemetry needs revalidation.")
        model, replay = engine.model, engine.model.replay_buffer
        samples = replay.last_samples
        indices = np.asarray(record["sampled_indices"], dtype=np.int64)
        tasks = _array(samples.observations[:, -len(TASKS):]).argmax(axis=1)
        chunk = self._sample_description(replay.birth_steps[indices], tasks, int(record["step"]))
        self._sample_chunks.append(chunk)
        self._counts["sampled_transitions"] += len(indices)
        self._counts["observed_updates"] += 1
        for key, value in record["losses"].items():
            self._learning_values[key].append(float(value))
        self._learning_values["alpha_used_in_this_update"].append(pending["alpha_before"])
        current_lp, next_lp = [value.reshape(-1, 1) for value in pending["log_probs"]]
        with torch.no_grad():
            next_q_min = torch.cat(pending["target_q"][0], dim=1).min(dim=1, keepdim=True).values
            discounts = getattr(samples, "discounts", None)
            if discounts is None:
                discounts = model.gamma
            target = samples.rewards + (1 - samples.dones) * discounts * (
                next_q_min - pending["alpha_before"] * next_lp)
            replay_q = pending["critic_q"][0]
            actor_q_min = torch.cat(pending["critic_q"][1], dim=1).min(dim=1, keepdim=True).values
            quantities = {"q_replay_0": replay_q[0], "q_replay_1": replay_q[1],
                          "target": target, "q_target_next_min": next_q_min,
                          "q_actor_min": actor_q_min,
                          "log_prob_current": current_lp, "log_prob_next": next_lp,
                          "reward": samples.rewards,
                          "actor_objective": pending["alpha_before"] * current_lp - actor_q_min}
            for i, q in enumerate(replay_q):
                quantities[f"td_signed_{i}"] = q - target
                quantities[f"td_abs_{i}"] = (q - target).abs()
                quantities[f"td_squared_{i}"] = (q - target).square()
        actor_mean = float(quantities["actor_objective"].mean().item())
        arrays = {key: _array(value).reshape(-1) for key, value in quantities.items()}
        # These identities tie the passive quantities to the actual loss used.
        if not math.isclose(actor_mean, record["losses"]["actor_loss"], rel_tol=2e-6, abs_tol=2e-5):
            raise IntegrityError("Observed actor objective disagrees with actual SAC loss.")
        for i, task in enumerate(TASKS):
            mask = tasks == i
            if np.any(mask):
                for key, values in arrays.items():
                    self._task_values[task][key].append(values[mask])

    def _observe_episode(self, record, engine, pending):
        step = int(record["step"])
        if self._episode is None:
            self._episode = {"start_step": step - 1, "end_step": None,
                             "relative_start": step - 1 - self.start_step,
                             "task": TASKS[int(record["task"])],
                             "seed": int(engine.episode.seed) if engine.episode is not None else None,
                             "initial_state_hash": record["initial_state_hash"],
                             "success": False, "first_success_step": None,
                             "first_success_within_episode": None,
                             "policy_version_first_success": None,
                             "policy_version_first_action": pending["updates_before"],
                             "return": 0.0, "length": 0}
        row = self._episode
        if row["task"] != TASKS[int(record["task"])]:
            raise IntegrityError("Training task changed inside an episode.")
        row["length"] += 1
        row["return"] += float(record["reward"])
        row["policy_version_last_action"] = pending["updates_before"]
        if bool(record["success"]) and row["first_success_step"] is None:
            row.update({"success": True, "first_success_step": step,
                        "first_success_within_episode": row["length"],
                        "policy_version_first_success": pending["updates_before"]})
        if not record["truncated"]:
            return
        if row["length"] != self.episode_steps or step % self.episode_steps:
            raise IntegrityError("Training episode differs from the frozen 500-step contract.")
        if row["success"] != bool(engine.last_episode["success"]):
            raise IntegrityError("Training episode success aggregation disagrees with the collector.")
        row.update({"end_step": step, "relative_end": step - self.start_step,
                    "episode": step // self.episode_steps,
                    "policy_changes_within_episode": True,
                    "label_available_after_update_at_step": step})
        self._append("training_episodes", row)
        # Deliberately after this update's exposure classification. A completed
        # episode never gives its earlier sampled transitions a future label.
        self._known_episodes[step] = {"task": row["task"], "success": row["success"],
                                      "available_after_step": step,
                                      "source": "new_complete_training_episode"}
        self._counts["episodes"] += 1
        self._episode = None

    def _summarize_exposure(self, data):
        result = {"n": int(len(data["births"])), "by_task": {}}
        for i, task in enumerate(TASKS):
            mask = data["tasks"] == i
            labels = data["labels"][mask]
            n = int(mask.sum())
            known = int(np.sum(labels >= 0))
            result["by_task"][task] = {
                "n": n, "fraction": n / result["n"] if result["n"] else None,
                "age_stats": _stats(data["ages"][mask]),
                "birth_step_stats": _stats(data["births"][mask]),
                "labels": {"successful": int(np.sum(labels == 1)),
                           "unsuccessful": int(np.sum(labels == 0)),
                           "unknown": int(np.sum(labels < 0))},
                "known_fraction": known / n if n else None,
                "successful_fraction_all": int(np.sum(labels == 1)) / n if n else None,
                "successful_fraction_known": int(np.sum(labels == 1)) / known if known else None,
                "new_fraction": float(data["new"][mask].mean()) if n else None}
        labels = data["labels"]
        result.update({"age_stats": _stats(data["ages"]),
                       "labels": {"successful": int(np.sum(labels == 1)),
                                  "unsuccessful": int(np.sum(labels == 0)),
                                  "unknown": int(np.sum(labels < 0))},
                       "known_fraction": float(np.mean(labels >= 0)) if len(labels) else None,
                       "new_fraction": float(data["new"].mean()) if len(labels) else None})
        return result

    def _buffer_snapshot(self, engine):
        replay = engine.model.replay_buffer
        size = replay.size()
        births = replay.birth_steps[:size]
        tasks = replay.observations[:size, 0, -len(TASKS):].argmax(axis=1)
        return self._summarize_exposure(self._sample_description(
            births, tasks, int(engine.model.num_timesteps)))

    @staticmethod
    def _collection_summary(counts):
        n = int(np.sum(counts))
        return {"n": n, "by_task": {
            task: {"n": int(counts[i]), "fraction": int(counts[i]) / n if n else None}
            for i, task in enumerate(TASKS)}}

    def _flush_window(self, engine, *, complete):
        if not self._window_steps:
            return
        if self._sample_chunks:
            data = {key: np.concatenate([chunk[key] for chunk in self._sample_chunks])
                    for key in self._sample_chunks[0]}
        else:
            data = {key: np.empty(0, dtype=np.int64)
                    for key in ("births", "tasks", "ages", "labels", "new")}
        end = int(engine.model.num_timesteps)
        if int(self._collection_counts.sum()) != self._window_steps:
            raise IntegrityError("Per-record collection counts do not match this telemetry window.")
        if complete and not np.array_equal(
                np.asarray(engine.collected_steps, dtype=np.int64) - self._collected_baseline,
                self._collection_total_counts):
            raise IntegrityError("Observed cumulative collection differs from the full collector state.")
        row = {"window_start_step": self._window_first, "window_end_step": end,
               "relative_start": self._window_first - 1 - self.start_step,
               "relative_end": end - self.start_step,
               "window_steps": self._window_steps, "complete_250_window": bool(complete),
               "collected": self._collection_summary(self._collection_counts),
               "collected_cumulative_since_S": self._collection_summary(self._collection_total_counts),
               "learning_metrics": {key: _stats(value, quantiles=False)
                                    for key, value in self._learning_values.items()},
               "sampled_replay": self._summarize_exposure(data),
               "buffer_snapshot": self._buffer_snapshot(engine),
               "sac_by_task": {task: {key: _stats(np.concatenate(chunks))
                                      for key, chunks in self._task_values[task].items()}
                               for task in TASKS},
               "known_complete_episode_labels_at_window_end": len(self._known_episodes)}
        self._append("windows_250", row)
        self._counts["windows"] += 1
        self._learning_values = defaultdict(list)
        self._task_values = {task: defaultdict(list) for task in TASKS}
        self._sample_chunks = []
        self._collection_counts = np.zeros(len(TASKS), dtype=np.int64)
        self._window_steps = 0
        self._window_first = None

    def _probe_policy(self, engine):
        model = engine.model
        step = int(model.num_timesteps)
        before_rng = capture_rng()
        modes = [(module, module.training) for module in model.policy.modules()]
        try:
            model.policy.set_training_mode(False)
            with torch.no_grad():
                observation = torch.as_tensor(self.panel, device=model.device)
                mu_t, log_std_t, _ = model.actor.get_action_dist_params(observation)
                mu = _array(mu_t).astype(np.float64)
                log_std = _array(log_std_t).astype(np.float64)
                std = np.exp(log_std)
                # A private generator gives common Monte Carlo noise across
                # checkpoints without consuming or reseeding training RNGs.
                generator = torch.Generator(device=model.device)
                generator.manual_seed(self.probe_seed)
                eps = torch.randn((self.entropy_samples, *mu_t.shape), generator=generator,
                                  device=model.device, dtype=torch.float64)
                mu64 = mu_t.to(dtype=torch.float64)
                log_std64 = log_std_t.to(dtype=torch.float64)
                latent = mu64.unsqueeze(0) + log_std64.exp().unsqueeze(0) * eps
                normal_log_prob = (-0.5 * eps.square() - log_std64.unsqueeze(0) -
                                   0.5 * math.log(2 * math.pi)).sum(dim=-1)
                stable_log_jacobian = (2 * (math.log(2) - latent -
                                          torch.nn.functional.softplus(-2 * latent))).sum(dim=-1)
                exact_tanh_entropy = _array(-(normal_log_prob - stable_log_jacobian)).mean(axis=0)
                sb3_log_jacobian = torch.log(1 - latent.tanh().square() +
                                            float(model.actor.action_dist.epsilon)).sum(dim=-1)
                sb3_tanh_entropy = _array(-(normal_log_prob - sb3_log_jacobian)).mean(axis=0)
        finally:
            for module, was_training in modes:
                module.training = was_training
            restore_rng(before_rng)
        if fingerprint(capture_rng()) != fingerprint(before_rng):
            raise IntegrityError("Policy probe changed a global training RNG.")
        if self._frozen_parameters is None:
            self._frozen_parameters = (mu.copy(), log_std.copy())
            self._previous_parameters = (mu.copy(), log_std.copy())
            self._previous_probe_step = step
        frozen_mu, frozen_log_std = self._frozen_parameters
        previous_mu, previous_log_std = self._previous_parameters
        gaussian_entropy = np.sum(log_std + 0.5 * math.log(2 * math.pi * math.e), axis=-1)
        comparisons = {
            "kl_frozen_to_current": _gaussian_kl(frozen_mu, frozen_log_std, mu, log_std),
            "kl_current_to_frozen": _gaussian_kl(mu, log_std, frozen_mu, frozen_log_std),
            "kl_previous_to_current": _gaussian_kl(previous_mu, previous_log_std, mu, log_std),
            "kl_current_to_previous": _gaussian_kl(mu, log_std, previous_mu, previous_log_std),
            "mu_mse_to_frozen": ((mu - frozen_mu) ** 2).mean(axis=-1),
            "mu_mse_to_previous": ((mu - previous_mu) ** 2).mean(axis=-1),
            "std_mse_to_frozen": ((std - np.exp(frozen_log_std)) ** 2).mean(axis=-1),
            "std_mse_to_previous": ((std - np.exp(previous_log_std)) ** 2).mean(axis=-1)}
        by_task = {}
        for i, task in enumerate(TASKS):
            mask = self.panel_tasks == i
            by_task[task] = {"n": int(mask.sum()), "mean_mu": mu[mask].mean(axis=0).tolist(),
                             "mean_std": std[mask].mean(axis=0).tolist(),
                             "mean_tanh_mu": np.tanh(mu[mask]).mean(axis=0).tolist(),
                             "mu_stats": _stats(mu[mask]), "std_stats": _stats(std[mask]),
                             "log_std_stats": _stats(log_std[mask]),
                             "gaussian_entropy_unsquashed": _stats(gaussian_entropy[mask]),
                             "squashed_entropy_mc_tanh_exact": _stats(exact_tanh_entropy[mask]),
                             "squashed_entropy_mc_sb3_epsilon": _stats(sb3_tanh_entropy[mask]),
                             **{key: _stats(value[mask]) for key, value in comparisons.items()}}
        row = {"step": step, "relative_step": step - self.start_step,
               "updates": int(model._n_updates), "frozen_reference_step": self.start_step,
               "previous_probe_step": self._previous_probe_step,
               "alpha": float(model.log_ent_coef.detach().exp().item()),
               "panel_observations_sha256": fingerprint(self.panel),
               "unsquashed_gaussian_parameters_sha256": fingerprint({"mu": mu, "log_std": log_std}),
               "mc_samples_per_state": self.entropy_samples,
               "entropy_action_units": "normalized tanh actions in (-1,1), not environment-unit rescaling",
               "kl_space": "unsquashed diagonal Gaussian; summed over action dimensions",
               "by_task": by_task}
        self._append("policy_drift_1000", row)
        self._previous_parameters = (mu.copy(), log_std.copy())
        self._previous_probe_step = step
        self._counts["policy_probes"] += 1

    @contextmanager
    def suspended(self):
        """Explicit checkpoint context; temporary hooks must already be absent."""
        if self._handles or self._distribution is not None or self._pending is not None:
            raise IntegrityError("Cannot save a checkpoint inside an observed learner update.")
        self._suspend_depth += 1
        try:
            yield
        finally:
            self._suspend_depth -= 1

    def state_dict(self):
        """Sidecar state for an exact boundary resume, excluding all file/model objects.

        Serialize this with pickle in the worker's new checkpoint directory.
        The restored observer must call load_state_dict BEFORE attach, with the
        same frozen panel. Its output belongs in a fresh segment directory.
        """
        if self.engine is None or self._handles or self._distribution is not None or self._pending is not None:
            raise IntegrityError("Telemetry sidecars require a completed observed step.")
        if not self.engine.at_boundary:
            raise IntegrityError("Telemetry sidecars require a full episode boundary.")
        if not self.enabled:
            return {"schema_version": SCHEMA_VERSION, "enabled": False,
                    "checkpoint_step": int(self.engine.model.num_timesteps)}
        return copy.deepcopy({
            "schema_version": SCHEMA_VERSION, "enabled": True,
            "checkpoint_step": int(self.engine.model.num_timesteps),
            "checkpoint_updates": int(self.engine.model._n_updates),
            "start_step": self.start_step, "start_updates": self.start_updates,
            "episode_steps": self.episode_steps, "window_steps": self.window_steps,
            "panel_every": self.panel_every, "probe_seed": self.probe_seed,
            "entropy_samples": self.entropy_samples,
            "panel_observations_sha256": fingerprint(self.panel),
            "panel_task_indices_sha256": fingerprint(self.panel_tasks),
            "frozen_parameters": self._frozen_parameters,
            "previous_parameters": self._previous_parameters,
            "previous_probe_step": self._previous_probe_step,
            "known_episodes": self._known_episodes,
            "learning_values": dict(self._learning_values),
            "task_values": {task: dict(value) for task, value in self._task_values.items()},
            "sample_chunks": self._sample_chunks,
            "collection_counts": self._collection_counts,
            "collection_total_counts": self._collection_total_counts,
            "collected_baseline": self._collected_baseline,
            "episode": self._episode, "current_window_steps": self._window_steps,
            "window_first": self._window_first, "counts": self._counts,
            "wall_seconds": self._wall_seconds, "cpu_seconds": self._cpu_seconds,
        })

    def load_state_dict(self, state):
        """Stage a trusted, hash-pinned sidecar before attaching to a restored engine."""
        if self.engine is not None:
            raise RuntimeError("Load the telemetry sidecar before attach(), in a fresh output segment.")
        state = copy.deepcopy(state)
        if state.get("schema_version") != SCHEMA_VERSION or state.get("enabled") != self.enabled:
            raise IntegrityError("Telemetry sidecar schema or enable mode differs.")
        if self.enabled:
            for key in ("window_steps", "panel_every", "probe_seed", "entropy_samples"):
                if state[key] != getattr(self, key):
                    raise IntegrityError(f"Telemetry resume configuration differs: {key}.")
        self._resume_state = state

    def _apply_resume_state(self, engine):
        state = self._resume_state
        if (int(engine.model.num_timesteps) != state["checkpoint_step"] or
                int(engine.model._n_updates) != state["checkpoint_updates"] or
                self.episode_steps != state["episode_steps"]):
            raise IntegrityError("Telemetry sidecar does not match the restored learner boundary.")
        if (fingerprint(self.panel) != state["panel_observations_sha256"] or
                fingerprint(self.panel_tasks) != state["panel_task_indices_sha256"]):
            raise IntegrityError("The fixed training panel changed across a resume.")
        if state["episode"] is not None:
            raise IntegrityError("A full boundary sidecar cannot contain an unfinished episode.")
        self.start_step = int(state["start_step"])
        self.start_updates = int(state["start_updates"])
        self._frozen_parameters = state["frozen_parameters"]
        self._previous_parameters = state["previous_parameters"]
        self._previous_probe_step = state["previous_probe_step"]
        self._known_episodes = state["known_episodes"]
        self._learning_values = defaultdict(list, state["learning_values"])
        self._task_values = {task: defaultdict(list, state["task_values"][task]) for task in TASKS}
        self._sample_chunks = state["sample_chunks"]
        self._collection_counts = state["collection_counts"]
        self._collection_total_counts = state["collection_total_counts"]
        self._collected_baseline = state["collected_baseline"]
        if not np.array_equal(np.asarray(engine.collected_steps, dtype=np.int64) - self._collected_baseline,
                              self._collection_total_counts):
            raise IntegrityError("Telemetry collection counters differ from the restored collector.")
        self._episode = None
        self._window_steps = state["current_window_steps"]
        self._window_first = state["window_first"]
        self._counts = state["counts"]
        self._wall_seconds = state["wall_seconds"]
        self._cpu_seconds = state["cpu_seconds"]

    def close(self):
        if self._closed:
            return
        self.end_step()
        if self.enabled and self.engine is not None:
            # Preserve an interrupted partial window without calling it a full
            # 250-step measurement. Do not complete an interrupted episode.
            self._flush_window(self.engine, complete=False)
            write_json(self.output_dir / "telemetry_summary.json", {
                "schema_version": SCHEMA_VERSION, "created_at": utc_now(),
                "start_step": self.start_step, "end_step": int(self.engine.model.num_timesteps),
                "counts": self._counts, "known_complete_episode_labels": len(self._known_episodes),
                "collected_cumulative_since_S": self._collection_summary(self._collection_total_counts),
                "partial_episode_preserved": copy.deepcopy(self._episode),
                "step_observation_wall_seconds": self._wall_seconds,
                "step_observation_process_cpu_seconds": self._cpu_seconds,
                "timing_scope": "includes ordinary Engine.step learner/collector time; not telemetry-only overhead; attachment probe excluded",
                "gpu_busy_time": None,
            })
        for stream in self._streams.values():
            stream.close()
        self._streams = {}
        self._closed = True


class BaselineEngine(AuditEngine):
    """Exact loader-compatible engine with an optional passive observer."""

    def __init__(self, config, costs, model=None, telemetry=None):
        super().__init__(config, costs, model=model)
        self.telemetry = telemetry

    def step(self):
        telemetry = self.telemetry
        if telemetry is None or not telemetry.enabled:
            return super().step()
        telemetry.before_step(self)
        try:
            record = super().step()
            telemetry.observe(record, self)
            return record
        finally:
            telemetry.end_step()

    def close(self):
        try:
            if self.telemetry is not None:
                self.telemetry.close()
        finally:
            super().close()
