"""Actor-only interventions around unchanged AuditedSAC/SB3 train methods.

The original SAC actor loss is backpropagated by SB3. A temporary optimizer
pre-step hook then accumulates lambda * KL(teacher || student), and the SAME
actor optimizer step applies both gradients. No second actor/SAC update and no
historical-transition Bellman backup is introduced.
"""
from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
import copy
import json
import math
from pathlib import Path
from types import MethodType

import numpy as np
import torch

from practice_allocation.core import TASKS, fingerprint, utc_now, write_json


class RetentionIntegrityError(RuntimeError):
    pass


def teacher_to_student_kl(teacher_mu, teacher_log_std, student_mu, student_log_std):
    """Analytic diagonal-Gaussian forward KL, summed over action dimensions.

    For the same invertible elementwise tanh transform, exact distributional KL
    is invariant. This expression is in pre-tanh Gaussian coordinates; it is not
    an action MSE or the epsilon-adjusted sampled SAC log-density.
    """
    return (student_log_std - teacher_log_std + 0.5 * (
        torch.exp(2 * (teacher_log_std - student_log_std)) +
        (teacher_mu - student_mu).square() * torch.exp(-2 * student_log_std) - 1)).sum(dim=-1)


def _cpu_tree(value):
    if isinstance(value, torch.Tensor):
        return value.detach().cpu().clone()
    if isinstance(value, dict):
        return {key: _cpu_tree(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return tuple(_cpu_tree(child) for child in value)
    if isinstance(value, list):
        return [_cpu_tree(child) for child in value]
    return copy.deepcopy(value)


def _clone_frozen_actor(actor):
    # Distribution caches can contain non-leaf tensors, which torch refuses to
    # deepcopy. Supply a clean COPY through deepcopy's memo; never mutate the
    # original actor/distribution/optimizer to construct the teacher.
    clean_distribution = copy.copy(actor.action_dist)
    clean_distribution.distribution = None
    if hasattr(clean_distribution, "gaussian_actions"):
        clean_distribution.gaussian_actions = None
    teacher = copy.deepcopy(actor, memo={id(actor.action_dist): clean_distribution})
    teacher.__dict__.pop("optimizer", None)
    teacher.eval()
    teacher.requires_grad_(False)
    return teacher


def _train_dispatch(model, *args, **kwargs):
    return model._retention_runtime._train(*args, **kwargs)


def _save_dispatch(model, *args, **kwargs):
    controller = model._retention_runtime
    with controller.suspended():
        return controller._original_save(*args, **kwargs)


def _summary(values):
    values = np.asarray(values, dtype=np.float64)
    if not len(values) or not np.all(np.isfinite(values)):
        raise RetentionIntegrityError("Empty or non-finite retention telemetry.")
    return {"n": int(len(values)), "sum": float(values.sum()), "mean": float(values.mean()),
            "std": float(values.std()), "min": float(values.min()), "max": float(values.max())}


ARM_NAMES = {
    "A": "A", "stock": "A", "A_stock": "A",
    "B": "B", "actor_lr_half": "B", "B_actor_lr_half": "B",
    "C": "C", "general": "C", "C_general": "C",
    "D": "D", "success": "D", "D_success": "D",
}


class RetentionController:
    """External treatment state; runtime dispatchers never enter model.zip.

    Required treatment config: batch_size, kl_coefficient, actor_lr_multiplier,
    memory_sampling='with_replacement', telemetry_window_steps,
    kl_direction='teacher_to_student', same_actor_step=True.
    ``state`` restores the ORIGINAL frozen teacher and private RNG before the
    first resumed update. Dynamic state intentionally excludes paths/timestamps,
    enabling exact comparisons across output segments and observer enable modes.
    """

    def __init__(self, engine, arm, memories, config, seed, output=None, state=None):
        if arm not in ARM_NAMES:
            raise ValueError(f"Unknown intervention arm: {arm!r}")
        self.arm = ARM_NAMES[arm]
        self.engine, self.model = engine, engine.model
        self.config = copy.deepcopy(config)
        required = ("batch_size", "kl_coefficient", "actor_lr_multiplier", "memory_sampling",
                    "telemetry_window_steps", "kl_direction", "same_actor_step")
        if any(key not in config for key in required):
            raise ValueError(f"Treatment configuration requires {required}.")
        if (config["memory_sampling"] != "with_replacement" or
                config["kl_direction"] != "teacher_to_student" or config["same_actor_step"] is not True):
            raise ValueError("The frozen treatment uses forward KL and the same actor step.")
        self.batch_size = int(config["batch_size"])
        self.coefficient = float(config["kl_coefficient"])
        self.actor_lr_multiplier = float(config["actor_lr_multiplier"])
        self.window_steps = int(config["telemetry_window_steps"])
        if (self.batch_size <= 0 or self.window_steps <= 0 or self.coefficient < 0 or
                not math.isfinite(self.coefficient) or not 0 < self.actor_lr_multiplier <= 1):
            raise ValueError("Invalid retention batch, cadence, coefficient, or actor LR multiplier.")
        if not engine.at_boundary:
            raise RetentionIntegrityError("Attach treatment only after exact full-state restoration at a boundary.")
        if hasattr(self.model, "_retention_runtime"):
            raise RetentionIntegrityError("A treatment is already attached to this learner.")
        if self.model.use_sde or self.model.policy.share_features_extractor:
            raise RetentionIntegrityError("Only the approved separate-feature ordinary SAC actor is supported.")
        if type(self.model.actor.action_dist).__name__ != "SquashedDiagGaussianDistribution":
            raise RetentionIntegrityError("The approved actor uses a tanh-squashed diagonal Gaussian.")
        for module in self.model.actor.modules():
            if isinstance(module, torch.nn.modules.batchnorm._BatchNorm):
                raise RetentionIntegrityError("Additional actor forwards would mutate BatchNorm state.")
            if isinstance(module, torch.nn.modules.dropout._DropoutNd) and module.p:
                raise RetentionIntegrityError("Stochastic dropout is outside the approved RNG-neutral KL rule.")
        self.seed = int(seed)
        self.rng = np.random.default_rng(self.seed)
        self.source_step = int(self.model.num_timesteps)
        self.source_updates = int(self.model._n_updates)
        self._original_train = self.model.train
        self._original_save = self.model.save
        self._original_instance_attributes = {
            key: (key in self.model.__dict__, self.model.__dict__.get(key))
            for key in ("train", "save", "_retention_runtime")}
        self._active = False
        self._suspend_depth = 0
        self._installed = False
        self._closed = False
        self._actor_hook = None
        self._lr_restore = None
        self._actor_step_calls = 0
        self._calls = 0
        self._regularizer_updates = 0
        self._last_step = self.source_step
        self.last_update_metrics = {}
        self._hook_metrics = None
        self._window_values = defaultdict(list)
        self._window_first_step = None
        self._window_count = 0
        self._windows_written = 0
        self._stream = None
        self.output = Path(output) if output is not None else None
        self.memory = None
        self.teacher = None
        self.teacher_hash = None
        self._teacher_mu = None
        self._teacher_log_std = None
        self._window_memory_counts = np.zeros(0, dtype=np.int64)
        self._total_memory_counts = np.zeros(0, dtype=np.int64)
        if self.arm in ("C", "D"):
            name = "general" if self.arm == "C" else "success"
            self.memory = copy.deepcopy(memories[name])
            actual_memory_hash = fingerprint({key: value for key, value in self.memory.items()
                                              if key not in ("fingerprint", "provenance")})
            if actual_memory_hash != self.memory["fingerprint"]:
                raise RetentionIntegrityError("The frozen memory's arrays differ from its fingerprint.")
            expected_source = int(state["source_step"]) if state is not None else self.source_step
            if int(self.memory["provenance"]["source_step"]) != expected_source:
                raise RetentionIntegrityError("Memory and frozen teacher must originate at the same S; resume requires its sidecar.")
            obs = np.asarray(self.memory["observations"])
            if (obs.dtype != np.float32 or obs.ndim != 2 or not len(obs) or
                    not np.all(np.isfinite(obs))):
                raise RetentionIntegrityError("A finite, frozen float32 training-observation memory is required.")
            for key in ("task_indices", "age_bin_indices"):
                if len(self.memory[key]) != len(obs):
                    raise RetentionIntegrityError("Memory support arrays have inconsistent lengths.")
            self.teacher = _clone_frozen_actor(self.model.actor)
            self._window_memory_counts = np.zeros(len(obs), dtype=np.int64)
            self._total_memory_counts = np.zeros(len(obs), dtype=np.int64)
            if state is None:
                self._cache_teacher()
        if state is not None:
            self.load_state_dict(state)
        if self.output is not None:
            self.output.mkdir(parents=True, exist_ok=True)
            write_json(self.output / "intervention_metadata.json", self.provenance())
            self._stream = (self.output / "retention_updates_250.jsonl").open(
                "x", encoding="utf-8", newline="\n")
        self._install_dispatchers()

    def _cache_teacher(self):
        if self.teacher is None:
            return
        self.teacher_hash = fingerprint(self.teacher.state_dict())
        with torch.no_grad():
            obs = torch.as_tensor(self.memory["observations"], device=self.model.device)
            mean, log_std, kwargs = self.teacher.get_action_dist_params(obs)
            if kwargs:
                raise RetentionIntegrityError("Unsupported teacher distribution parameters.")
            self._teacher_mu = mean.detach().clone()
            self._teacher_log_std = log_std.detach().clone()
        if (not torch.isfinite(self._teacher_mu).all() or not torch.isfinite(self._teacher_log_std).all()):
            raise RetentionIntegrityError("Frozen teacher outputs are not finite.")

    def provenance(self):
        return {"schema_version": 1, "created_at": utc_now(), "arm": self.arm,
                "source_step": self.source_step, "source_updates": self.source_updates,
                "config": self.config, "regularizer_seed": self.seed,
                "teacher_state_sha256": self.teacher_hash,
                "memory_sha256": self.memory["fingerprint"] if self.memory else None,
                "memory_provenance": self.memory.get("provenance") if self.memory else None,
                "objective": "stock SAC actor objective + lambda * mean KL(frozen S teacher || student) on historical training observations",
                "update_rule": "one existing actor optimizer step; KL gradient accumulated after stock actor backward, before that step",
                "historical_value_learning": False, "stock_replay_sampler_changed": False,
                "teacher_evaluation": "deterministic Gaussian parameters; frozen; cached once; no sampled teacher actions",
                "memory_batch_sampling": "private numpy Generator, with replacement; does not touch global or learner RNGs",
                "kl_space": "analytic pre-tanh diagonal Gaussian; exact KL invariant under shared bijective tanh; not epsilon-adjusted sampled log-density",
                "loss_logging": "stock actor_loss remains the SAC component; total objective reported separately",
                "gradient_norms": "actor L2: SAC before retention, combined after, retention from their actual floating-point difference (includes lambda); no extra backward",
                "resume_restored": self._calls > 0}

    def _install_dispatchers(self):
        if self._installed or self._closed or self._suspend_depth:
            return
        self.model._retention_runtime = self
        self.model.train = MethodType(_train_dispatch, self.model)
        self.model.save = MethodType(_save_dispatch, self.model)
        self._installed = True

    def _remove_dispatchers(self):
        if not self._installed:
            return
        for key, (had_value, value) in self._original_instance_attributes.items():
            if had_value:
                setattr(self.model, key, value)
            else:
                self.model.__dict__.pop(key, None)
        self._installed = False

    @contextmanager
    def suspended(self):
        """Serialize only original SAC state; keep treatment state in its sidecar."""
        if self._active or self._actor_hook is not None or self._lr_restore is not None:
            raise RetentionIntegrityError("Cannot checkpoint inside an active actor update.")
        self._suspend_depth += 1
        if self._suspend_depth == 1:
            self._remove_dispatchers()
        try:
            yield
        finally:
            self._suspend_depth -= 1
            if not self._suspend_depth:
                self._install_dispatchers()

    @contextmanager
    def _training_context(self):
        if self._active or self._closed or self._suspend_depth:
            raise RetentionIntegrityError("Invalid or nested intervention training context.")
        self._active = True
        self._actor_step_calls = 0
        self._hook_metrics = None
        try:
            if self.arm == "B":
                had = "_update_learning_rate" in self.model.__dict__
                old_instance = self.model.__dict__.get("_update_learning_rate")
                original = self.model._update_learning_rate

                def actor_only_lr(_model, optimizers):
                    original(optimizers)
                    for group in _model.actor.optimizer.param_groups:
                        group["lr"] *= self.actor_lr_multiplier

                self._lr_restore = (had, old_instance)
                self.model._update_learning_rate = MethodType(actor_only_lr, self.model)
            # A/B use the same passive gradient observer, with no extra forward,
            # backward, memory sample, or change to their actor gradients.
            self._actor_hook = self.model.actor.optimizer.register_step_pre_hook(self._before_actor_step)
            yield
        finally:
            if self._actor_hook is not None:
                self._actor_hook.remove()
                self._actor_hook = None
            if self._lr_restore is not None:
                had, old_instance = self._lr_restore
                if had:
                    self.model._update_learning_rate = old_instance
                else:
                    self.model.__dict__.pop("_update_learning_rate", None)
                self._lr_restore = None
            self._active = False

    def _before_actor_step(self, _optimizer, _args, _kwargs):
        self._actor_step_calls += 1
        if self._actor_step_calls != 1:
            raise RetentionIntegrityError("The approved SAC call has exactly one actor optimizer step.")
        parameters = [parameter for parameter in self.model.actor.parameters() if parameter.requires_grad]
        with torch.no_grad():
            before = torch.cat([(parameter.grad.detach() if parameter.grad is not None else
                                 torch.zeros_like(parameter)).reshape(-1) for parameter in parameters])
        if self.arm not in ("C", "D"):
            norm = float(torch.linalg.vector_norm(before).item())
            if not math.isfinite(norm):
                raise RetentionIntegrityError("Non-finite stock actor gradient norm.")
            self._hook_metrics = {"retention_kl": 0.0, "retention_weighted_loss": 0.0,
                                  "memory_batch_n": 0, "memory_indices_sha256": None,
                                  "sac_actor_grad_norm": norm,
                                  "retention_weighted_actor_grad_norm": 0.0,
                                  "combined_actor_grad_norm": norm}
            return
        indices = self.rng.integers(0, len(self.memory["observations"]), size=self.batch_size)
        observations = torch.as_tensor(self.memory["observations"][indices], device=self.model.device)
        target_indices = torch.as_tensor(indices, device=self.model.device, dtype=torch.long)
        teacher_mu = self._teacher_mu[target_indices]
        teacher_log_std = self._teacher_log_std[target_indices]
        student_mu, student_log_std, kwargs = self.model.actor.get_action_dist_params(observations)
        if kwargs:
            raise RetentionIntegrityError("Unsupported student Gaussian policy.")
        kl = teacher_to_student_kl(teacher_mu, teacher_log_std, student_mu, student_log_std)
        loss = kl.mean()
        weighted = self.coefficient * loss
        if not torch.isfinite(kl).all() or not torch.isfinite(weighted):
            raise RetentionIntegrityError("Non-finite fixed-teacher KL.")
        # In the coefficient-zero technical control do not add even a zero
        # gradient; the stock actor gradient/optimizer state remain bit-exact.
        if self.coefficient:
            weighted.backward()
        with torch.no_grad():
            after = torch.cat([(parameter.grad.detach() if parameter.grad is not None else
                                torch.zeros_like(parameter)).reshape(-1) for parameter in parameters])
            norm_values = torch.stack((torch.linalg.vector_norm(before),
                                       torch.linalg.vector_norm(after - before),
                                       torch.linalg.vector_norm(after))).detach().cpu().tolist()
        if not all(math.isfinite(value) for value in norm_values):
            raise RetentionIntegrityError("Non-finite combined or retention actor gradient norm.")
        counts = np.bincount(indices, minlength=len(self._window_memory_counts))
        self._window_memory_counts += counts
        self._total_memory_counts += counts
        self._regularizer_updates += 1
        self._hook_metrics = {"retention_kl": float(loss.detach().item()),
                              "retention_weighted_loss": float(weighted.detach().item()),
                              "memory_batch_n": int(len(indices)),
                              "memory_indices_sha256": fingerprint(indices.astype(np.int64)),
                              "sac_actor_grad_norm": float(norm_values[0]),
                              "retention_weighted_actor_grad_norm": float(norm_values[1]),
                              "combined_actor_grad_norm": float(norm_values[2])}

    def _train(self, *args, **kwargs):
        updates_before = int(self.model._n_updates)
        with self._training_context():
            result = self._original_train(*args, **kwargs)
        if int(self.model._n_updates) - updates_before != 1:
            raise RetentionIntegrityError("Treatment changed or encountered the SAC update-count contract.")
        if self._actor_step_calls != 1:
            raise RetentionIntegrityError("The fixed-teacher loss missed the existing actor step.")
        self._calls += 1
        self._last_step = int(self.model.num_timesteps)
        actor_sac_loss = float(self.model.last_update_metrics["actor_loss"])
        retained = self._hook_metrics or {"retention_kl": 0.0, "retention_weighted_loss": 0.0,
                                         "memory_batch_n": 0, "memory_indices_sha256": None}
        self.last_update_metrics = {
            **retained, "actor_loss_sac": actor_sac_loss,
            "actor_loss_with_retention": actor_sac_loss + retained["retention_weighted_loss"],
            "actor_lr": float(self.model.actor.optimizer.param_groups[0]["lr"]),
            "critic_lr": float(self.model.critic.optimizer.param_groups[0]["lr"]),
            "alpha_lr": float(self.model.ent_coef_optimizer.param_groups[0]["lr"])
                        if self.model.ent_coef_optimizer is not None else None,
        }
        self._record_window()
        return result

    def _record_window(self):
        if self._window_first_step is None:
            self._window_first_step = self._last_step
        self._window_count += 1
        for key, value in self.last_update_metrics.items():
            if key != "memory_indices_sha256" and value is not None:
                self._window_values[key].append(float(value))
        if self._window_count == self.window_steps:
            self._flush_window(complete=True)

    def _flush_window(self, complete):
        if not self._window_count:
            return
        row = {"schema_version": 1, "arm": self.arm,
               "window_start_step": self._window_first_step, "window_end_step": self._last_step,
               "relative_start": self._window_first_step - 1 - self.source_step,
               "relative_end": self._last_step - self.source_step,
               "updates": self._window_count, "complete_window": bool(complete),
               "metrics": {key: _summary(values) for key, values in self._window_values.items()},
               "regularizer_updates_total": self._regularizer_updates,
               "memory_transitions_sampled": int(self._window_memory_counts.sum()),
               "memory_unique_observations_sampled": int(np.count_nonzero(self._window_memory_counts)),
               "memory_observation_sample_counts_sha256": fingerprint(self._window_memory_counts)}
        if self.memory is not None:
            row["sampled_by_task"] = {task: int(self._window_memory_counts[
                self.memory["task_indices"] == i].sum()) for i, task in enumerate(TASKS)}
            row["sampled_by_age_bin"] = {str(i): int(self._window_memory_counts[
                self.memory["age_bin_indices"] == i].sum())
                for i in sorted(np.unique(self.memory["age_bin_indices"]).tolist())}
        if self._stream is not None:
            self._stream.write(json.dumps(row, allow_nan=False, ensure_ascii=False) + "\n")
            self._stream.flush()
        self._windows_written += 1
        self._window_values = defaultdict(list)
        self._window_first_step = None
        self._window_count = 0
        self._window_memory_counts[:] = 0

    def state_dict(self):
        if self._active or self._actor_hook is not None or self._lr_restore is not None:
            raise RetentionIntegrityError("Treatment sidecars require the completed update boundary.")
        return _cpu_tree({
            "schema_version": 1, "arm": self.arm, "config": self.config, "seed": self.seed,
            "source_step": self.source_step, "source_updates": self.source_updates,
            "checkpoint_step": int(self.model.num_timesteps),
            "checkpoint_updates": int(self.model._n_updates),
            "memory": self.memory,
            "teacher_state": self.teacher.state_dict() if self.teacher is not None else None,
            "teacher_hash": self.teacher_hash,
            "teacher_mu": self._teacher_mu, "teacher_log_std": self._teacher_log_std,
            "private_rng": copy.deepcopy(self.rng.bit_generator.state),
            "training_calls": self._calls, "regularizer_updates": self._regularizer_updates,
            "last_step": self._last_step, "last_update_metrics": self.last_update_metrics,
            "window_values": dict(self._window_values), "window_first_step": self._window_first_step,
            "window_count": self._window_count, "windows_written": self._windows_written,
            "window_memory_counts": self._window_memory_counts,
            "total_memory_counts": self._total_memory_counts,
        })

    def load_state_dict(self, state):
        if self._active:
            raise RetentionIntegrityError("Cannot restore a treatment inside an optimizer update.")
        state = _cpu_tree(state)
        if (state["schema_version"] != 1 or state["arm"] != self.arm or
                state["config"] != self.config or state["seed"] != self.seed):
            raise RetentionIntegrityError("Treatment sidecar configuration differs.")
        if (state["checkpoint_step"] != int(self.model.num_timesteps) or
                state["checkpoint_updates"] != int(self.model._n_updates)):
            raise RetentionIntegrityError("Treatment sidecar does not match the restored full learner.")
        if self.memory is not None:
            if state["memory"]["fingerprint"] != self.memory["fingerprint"]:
                raise RetentionIntegrityError("Frozen training memory changed across resume.")
            self.memory = state["memory"]
            self.teacher.load_state_dict(state["teacher_state"], strict=True)
            self.teacher.eval()
            self.teacher.requires_grad_(False)
            self.teacher_hash = fingerprint(self.teacher.state_dict())
            if self.teacher_hash != state["teacher_hash"]:
                raise RetentionIntegrityError("Frozen teacher changed across resume.")
            self._teacher_mu = state["teacher_mu"].to(self.model.device).detach().clone()
            self._teacher_log_std = state["teacher_log_std"].to(self.model.device).detach().clone()
        elif state["memory"] is not None or state["teacher_state"] is not None:
            raise RetentionIntegrityError("A/B cannot restore a hidden teacher or retention memory.")
        self.source_step, self.source_updates = int(state["source_step"]), int(state["source_updates"])
        self.rng.bit_generator.state = copy.deepcopy(state["private_rng"])
        self._calls, self._regularizer_updates = state["training_calls"], state["regularizer_updates"]
        self._last_step = state["last_step"]
        self.last_update_metrics = state["last_update_metrics"]
        self._window_values = defaultdict(list, state["window_values"])
        self._window_first_step, self._window_count = state["window_first_step"], state["window_count"]
        self._windows_written = state["windows_written"]
        self._window_memory_counts = np.asarray(state["window_memory_counts"], dtype=np.int64).copy()
        self._total_memory_counts = np.asarray(state["total_memory_counts"], dtype=np.int64).copy()

    def close(self):
        if self._closed:
            return
        if self._active:
            raise RetentionIntegrityError("Cannot close a controller during an active learner update.")
        self._flush_window(complete=False)
        self._remove_dispatchers()
        if self._stream is not None:
            self._stream.close()
            self._stream = None
        self._closed = True


def attach_intervention(engine, arm, memories, config, seed, output=None, state=None):
    """Attach A/B/C/D to an exactly restored engine; return its sidecar controller."""
    return RetentionController(engine, arm, memories, config, seed, output=output, state=state)
