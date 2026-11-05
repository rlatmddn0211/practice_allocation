"""Version-pinned adapter with explicit reset and termination semantics."""

from __future__ import annotations

from dataclasses import dataclass

import gymnasium as gym
import numpy as np
from metaworld.env_dict import ALL_V3_ENVIRONMENTS

from .core import ENV_NAMES, TASKS, fingerprint, isolated_rng


@dataclass
class CostCounter:
    environment_creations: int = 0
    resets: int = 0
    environment_steps: int = 0
    train_iterations: int = 0
    evaluation_episodes: int = 0

    def snapshot(self) -> dict:
        return dict(vars(self))


def conditioned_observation(raw: np.ndarray, task_index: int) -> np.ndarray:
    raw = np.asarray(raw)
    if raw.shape != (39,) or not np.isfinite(raw).all():
        raise RuntimeError(f"Invalid MetaWorld observation: shape={raw.shape}")
    return np.concatenate((raw.astype(np.float32), np.eye(4, dtype=np.float32)[task_index]))


class TaskEpisode:
    """Fresh physics instance per episode makes boundary-only resume unambiguous.

    MetaWorld 3.0.0 ignores the seed passed to reset(). Its low-level task flags
    are explicitly configured here. Their behavior is checked by the preflight.
    """

    def __init__(self, task_index: int, seed: int, costs: CostCounter):
        self.task_index, self.seed, self.costs = task_index, seed, costs
        self.steps = 0
        self.any_success = False
        self.closed = False
        self.raw = None
        try:
            with isolated_rng():
                self.raw = ALL_V3_ENVIRONMENTS[ENV_NAMES[task_index]](reward_function_version="v2")
                costs.environment_creations += 1
                self.raw._partially_observable = False
                self.raw.__dict__.pop("sawyer_observation_space", None)
                self.raw._freeze_rand_vec = False
                # seed() initializes np_random but does not enable its use in
                # MetaWorld 3.0.0's _get_state_rand_vec(). Both are necessary.
                self.raw.seeded_rand_vec = True
                self.raw._set_task_called = True
                self.raw.seed(seed)
                obs, _ = self.raw.reset()
                costs.resets += 1
            self.initial_raw_observation = obs.copy()
            self.observation = conditioned_observation(obs, task_index)
            if not np.allclose(obs[-3:], self.raw._target_pos, atol=1e-12, rtol=0):
                raise RuntimeError("Goal observation is not the environment's target position.")
            if self.raw.max_path_length != 500 or self.raw.reward_function_version != "v2":
                raise RuntimeError("Unexpected installed environment semantics.")
            if self.raw.action_space.shape != (4,) or not np.array_equal(self.raw.action_space.low, [-1] * 4) or not np.array_equal(self.raw.action_space.high, [1] * 4):
                raise RuntimeError("Unexpected action shape/range.")
            self.initial_state = {
                "task": TASKS[task_index], "rand_vec": self.raw._last_rand_vec.copy(),
                "goal": self.raw._target_pos.copy(), "qpos": self.raw.data.qpos.copy(),
                "qvel": self.raw.data.qvel.copy(), "observation": obs.copy(),
            }
            self.initial_state_hash = fingerprint(self.initial_state)
        except BaseException:
            self.close()
            raise

    def step(self, action: np.ndarray):
        if self.closed or self.steps >= 500:
            raise RuntimeError("Cannot step a closed or completed episode.")
        action = np.asarray(action, dtype=np.float32)
        if action.shape != (4,) or not np.isfinite(action).all() or np.any(np.abs(action) > 1):
            raise RuntimeError("Invalid action.")
        obs, reward, terminated, truncated, info = self.raw.step(action)
        self.steps += 1
        self.costs.environment_steps += 1
        if terminated or bool(truncated) != (self.steps == 500):
            raise RuntimeError(f"Unexpected termination at step {self.steps}: {terminated=}, {truncated=}")
        if getattr(self.raw, "_did_see_sim_exception", False):
            raise RuntimeError("MetaWorld reported a simulation exception.")
        if not np.isfinite(reward) or not np.isfinite(self.raw.data.qpos).all() or not np.isfinite(self.raw.data.qvel).all():
            raise RuntimeError("Non-finite physics or reward.")
        if info.get("success") not in (0, 1, 0.0, 1.0):
            raise RuntimeError("Missing or invalid official success signal.")
        self.any_success |= bool(info["success"])
        self.observation = conditioned_observation(obs, self.task_index)
        return self.observation.copy(), float(reward), False, bool(truncated), dict(info)

    def close(self) -> None:
        if self.raw is not None and not self.closed:
            self.raw.close()
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class PolicySpaces(gym.Env):
    """SB3 network construction only; the audited collector owns real episodes."""

    observation_space = gym.spaces.Box(-np.inf, np.inf, shape=(43,), dtype=np.float32)
    action_space = gym.spaces.Box(-1.0, 1.0, shape=(4,), dtype=np.float32)

    def reset(self, *, seed=None, options=None):
        raise RuntimeError("Use the version's Engine collector, not SAC.learn().")

    def step(self, action):
        raise RuntimeError("Use the version's Engine collector, not SAC.learn().")
