"""Disjoint physical-state banks and evaluation isolated from learning state."""

from __future__ import annotations

import csv
import time
from pathlib import Path

import numpy as np

from .core import TASKS, Config, derived_seed, fingerprint, isolated_rng
from .environment import CostCounter, TaskEpisode


def build_banks(config: Config, costs: CostCounter) -> dict:
    banks = {}
    physical_hashes, parameter_hashes, seeds = set(), set(), set()
    for name, domain, count in (
        ("diagnostic", 100, config.diagnostic_bank_episodes_per_task),
        ("outcome", 200, config.outcome_bank_episodes_per_task),
    ):
        rows = []
        for task in range(4):
            for index in range(count):
                seed = derived_seed(config.bank_seed, domain, task, index)
                with TaskEpisode(task, seed, costs) as episode:
                    state = episode.initial_state
                    parameter_hash = fingerprint({key: state[key] for key in ("task", "rand_vec", "goal")})
                    if episode.initial_state_hash in physical_hashes or parameter_hash in parameter_hashes or seed in seeds:
                        raise RuntimeError("Evaluation banks contain duplicate states, task parameters, or seeds.")
                    physical_hashes.add(episode.initial_state_hash)
                    parameter_hashes.add(parameter_hash)
                    seeds.add(seed)
                    rows.append({
                        "bank": name, "task": TASKS[task], "task_index": task,
                        "episode_index": index, "seed": seed,
                        "initial_state_hash": episode.initial_state_hash,
                        "task_parameter_hash": parameter_hash,
                        "initial_state": {k: v.tolist() if isinstance(v, np.ndarray) else v for k, v in state.items()},
                    })
            print(f"  {name} bank: {TASKS[task]} {count} distinct initial states", flush=True)
        banks[name] = rows
    return banks


def evaluate_model(model, bank: list[dict], costs: CostCounter, output: Path,
                   evaluation_id: str, limit_per_task: int | None = None,
                   policy_type: str = "learned_sac") -> dict:
    """Success is any official success flag; early stop saves evaluation cost."""
    started = time.perf_counter()
    before_steps = costs.environment_steps
    modes = {name: module.training for name, module in model.policy.named_modules()}
    results = []
    try:
        with isolated_rng():
            for entry in bank:
                if limit_per_task is not None and entry["episode_index"] >= limit_per_task:
                    continue
                with TaskEpisode(entry["task_index"], entry["seed"], costs) as episode:
                    if episode.initial_state_hash != entry["initial_state_hash"]:
                        raise RuntimeError("Evaluation reset failed to recreate its recorded physical state.")
                    observation, total_return, succeeded = episode.observation.copy(), 0.0, False
                    for _ in range(500):
                        action, _ = model.predict(observation, deterministic=True)
                        observation, reward, _, truncated, info = episode.step(action)
                        total_return += reward
                        succeeded |= bool(info["success"])
                        if succeeded or truncated:
                            break
                    costs.evaluation_episodes += 1
                    results.append({
                        "evaluation_id": evaluation_id, "context": "implementation_validation",
                        "policy_type": policy_type,
                        "bank": entry["bank"], "task": entry["task"],
                        "episode_index": entry["episode_index"], "seed": entry["seed"],
                        "initial_state_hash": entry["initial_state_hash"],
                        "success": int(succeeded), "return": total_return, "length": episode.steps,
                    })
    finally:
        for name, module in model.policy.named_modules():
            module.training = modes[name]
        # Keep already completed episodes if evaluation fails partway through.
        if results:
            is_new = not output.exists()
            with output.open("a", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(results[0]))
                if is_new:
                    writer.writeheader()
                writer.writerows(results)
    rates = {task: float(np.mean([row["success"] for row in results if row["task"] == task])) for task in TASKS}
    elapsed = time.perf_counter() - started
    return {
        "episodes": len(results), "environment_steps": costs.environment_steps - before_steps,
        "seconds": elapsed, "steps_per_second": (costs.environment_steps - before_steps) / elapsed,
        "success_by_task": rates, "macro_success": float(np.mean(list(rates.values()))),
        "results_hash": fingerprint([{k: v for k, v in row.items() if k != "evaluation_id"} for row in results]),
        "purpose": "technical reproducibility only; not P0 or a research comparison",
    }
