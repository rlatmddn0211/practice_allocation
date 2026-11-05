"""Stock SB3 SAC updates with passive replay and TD-error instrumentation."""

from __future__ import annotations

import numpy as np
import torch
from stable_baselines3 import SAC
from stable_baselines3.common.buffers import ReplayBuffer
from stable_baselines3.common.logger import configure

from .core import Config
from .environment import PolicySpaces


class AuditedReplayBuffer(ReplayBuffer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.n_envs != 1 or self.optimize_memory_usage:
            raise ValueError("This collector requires a single environment and ordinary replay storage.")
        self.birth_steps = np.full(self.buffer_size, -1, dtype=np.int64)
        self.total_added = 0
        self.branch_start_step = None
        self.sampled_task_counts = np.zeros(4, dtype=np.int64)
        self.sampled_new_count = 0
        self.sampled_total = 0
        self.last_indices = np.empty(0, dtype=np.int64)
        self.last_samples = None
        self.last_task_counts = np.zeros(4, dtype=np.int64)
        self.last_new_fraction = 0.0

    def add(self, obs, next_obs, action, reward, done, infos):
        position = self.pos
        super().add(obs, next_obs, action, reward, done, infos)
        self.total_added += 1
        self.birth_steps[position] = self.total_added

    def _get_samples(self, batch_inds, env=None):
        # The parent performs the actual, unchanged sampling and timeout masking.
        result = super()._get_samples(batch_inds, env)
        self.last_indices = batch_inds.copy()
        ids = self.observations[batch_inds, 0, -4:].argmax(axis=1)
        self.last_task_counts = np.bincount(ids, minlength=4)
        self.sampled_task_counts += self.last_task_counts
        self.sampled_total += len(batch_inds)
        new_count = int(np.count_nonzero(self.birth_steps[batch_inds] > self.branch_start_step)) if self.branch_start_step is not None else 0
        self.sampled_new_count += new_count
        self.last_new_fraction = new_count / len(batch_inds)
        self.last_samples = result
        return result

    def __getstate__(self):
        state = self.__dict__.copy()
        # Device tensors from the previous update are transient diagnostics.
        state["last_samples"] = None
        return state

    def state_for_hash(self) -> dict:
        length = self.size()
        return {
            "pos": self.pos, "full": self.full, "total_added": self.total_added,
            "observations": self.observations[:length],
            "next_observations": self.next_observations[:length],
            "actions": self.actions[:length], "rewards": self.rewards[:length],
            "dones": self.dones[:length], "timeouts": self.timeouts[:length],
            "birth_steps": self.birth_steps[:length], "branch_start_step": self.branch_start_step,
            "sampled_task_counts": self.sampled_task_counts,
            "sampled_new_count": self.sampled_new_count, "sampled_total": self.sampled_total,
            "last_indices": self.last_indices,
        }


class AuditedSAC(SAC):
    """Observe tensors used by SAC.train(); do not replace its loss or updates.

    Hooks capture the actual pre-update critic outputs and the stochastic next
    action's log probability. No diagnostic resampling or additional RNG draws.
    A stock-SAC equivalence gate verifies this instrumentation on a saved model.
    """

    def train(self, gradient_steps: int, batch_size: int = 64) -> None:
        if gradient_steps != 1:
            raise ValueError("The audited update contract requires gradient_steps=1.")
        log_probs, target_outputs, current_outputs = [], [], []
        alpha = self.log_ent_coef.detach().exp().clone()
        original = self.actor.action_log_prob

        def observe_action(*args, **kwargs):
            actions, log_prob = original(*args, **kwargs)
            log_probs.append(log_prob.detach())
            return actions, log_prob

        def observe_target(_module, _inputs, outputs):
            target_outputs.append(tuple(value.detach() for value in outputs))

        def observe_current(_module, _inputs, outputs):
            if not current_outputs:
                current_outputs.append(tuple(value.detach() for value in outputs))

        target_hook = self.critic_target.register_forward_hook(observe_target)
        current_hook = self.critic.register_forward_hook(observe_current)
        self.actor.action_log_prob = observe_action
        try:
            super().train(gradient_steps=gradient_steps, batch_size=batch_size)
        finally:
            del self.actor.action_log_prob
            target_hook.remove()
            current_hook.remove()

        if len(log_probs) != 2 or len(target_outputs) != 1 or len(current_outputs) != 1:
            raise RuntimeError("SB3's update call structure changed; instrumentation must be revalidated.")
        samples = self.replay_buffer.last_samples
        with torch.no_grad():
            next_q = torch.cat(target_outputs[0], dim=1).min(dim=1, keepdim=True).values
            target = samples.rewards + (1 - samples.dones) * self.gamma * (next_q - alpha * log_probs[1].reshape(-1, 1))
            td = [(value - target).abs().mean().item() for value in current_outputs[0]]
        self.last_update_metrics = {
            "actor_loss": float(self.logger.name_to_value["train/actor_loss"]),
            "critic_loss": float(self.logger.name_to_value["train/critic_loss"]),
            "entropy_loss": float(self.logger.name_to_value["train/ent_coef_loss"]),
            "entropy_coefficient": float(self.log_ent_coef.detach().exp().item()),
            "critic_0_abs_td_error": td[0], "critic_1_abs_td_error": td[1],
        }
        if not all(np.isfinite(v) for v in self.last_update_metrics.values()):
            raise RuntimeError(f"Non-finite SAC diagnostics: {self.last_update_metrics}")


def attach_logger(model: SAC) -> None:
    model.set_logger(configure(folder=None, format_strings=[]))


def create_model(config: Config) -> AuditedSAC:
    model = AuditedSAC(
        "MlpPolicy", PolicySpaces(), device=config.device, seed=config.seed,
        learning_rate=config.learning_rate, buffer_size=config.buffer_size,
        learning_starts=config.learning_starts, batch_size=config.batch_size,
        tau=config.tau, gamma=config.gamma, train_freq=(config.train_freq, "step"),
        gradient_steps=config.gradient_steps, action_noise=None,
        replay_buffer_class=AuditedReplayBuffer,
        replay_buffer_kwargs={"handle_timeout_termination": True},
        optimize_memory_usage=False, n_steps=1, ent_coef=config.ent_coef,
        target_update_interval=1, target_entropy=config.target_entropy,
        use_sde=False, sde_sample_freq=-1, use_sde_at_warmup=False,
        stats_window_size=100, tensorboard_log=None, verbose=0,
        policy_kwargs={
            "net_arch": {"pi": config.net_arch, "qf": config.net_arch},
            "activation_fn": torch.nn.ReLU, "n_critics": 2,
            "share_features_extractor": False, "normalize_images": False,
            "optimizer_class": torch.optim.Adam,
            "optimizer_kwargs": {"eps": 1e-8, "betas": (0.9, 0.999), "weight_decay": 0, "amsgrad": False},
        },
    )
    attach_logger(model)
    return model


def learning_state(model: SAC) -> dict:
    return {
        "parameters_and_optimizers": model.get_parameters(),
        "log_entropy_coefficient": model.log_ent_coef,
        "num_timesteps": model.num_timesteps, "n_updates": model._n_updates,
        "target_entropy": model.target_entropy,
    }
