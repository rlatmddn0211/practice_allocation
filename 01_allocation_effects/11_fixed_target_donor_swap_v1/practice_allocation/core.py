"""Configuration, deterministic seed streams, immutable artifacts, and hashing."""

from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import json
import os
import platform
import random
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
SUITES = json.loads((ROOT / "configs/suites.json").read_text(encoding="utf-8"))
SUITE = os.environ.get("PRACTICE_SUITE", "A")
if SUITE not in SUITES:
    raise ValueError(f"Unknown suite: {SUITE}")
TASKS = tuple(SUITES[SUITE]["labels"])
ENV_NAMES = tuple(SUITES[SUITE]["envs"])
ALLOCATIONS = {"U": (2, 2, 2, 2)}
ALLOCATIONS.update({f"F_{label}": tuple(5 if i == j else 1 for i in range(4)) for j, label in enumerate(TASKS)})
if SUITE == "A":
    ALLOCATIONS.update({"DC_plus_WO_minus": (2, 3, 1, 2), "DC_minus_WO_plus": (2, 1, 3, 2)})
PINNED = {
    "numpy": "2.2.4", "torch": "2.5.1", "gymnasium": "1.2.3",
    "mujoco": "3.5.0", "metaworld": "3.0.0", "stable-baselines3": "2.7.1",
}


@dataclass(frozen=True)
class Config:
    version: str
    seed: int
    device: str
    torch_threads: int
    deterministic_torch: bool
    episode_steps: int
    reward_function_version: str
    buffer_size: int
    batch_size: int
    learning_starts: int
    learning_rate: float
    gamma: float
    tau: float
    net_arch: list[int]
    n_critics: int
    ent_coef: str
    target_entropy: str
    target_update_interval: int
    train_freq: int
    gradient_steps: int
    normalize_observations: bool
    normalize_rewards: bool
    use_sde: bool
    action_noise: None
    optimize_memory_usage: bool
    handle_timeout_termination: bool
    n_steps: int
    smoke_train_steps: int
    resume_steps: int
    validation_eval_episodes_per_task: int
    diagnostic_bank_episodes_per_task: int
    outcome_bank_episodes_per_task: int
    bank_seed: int
    log_every_steps: int
    resume_atol: float
    resume_rtol: float

    @classmethod
    def load(cls, path: Path, device: str | None = None) -> "Config":
        data = json.loads(path.read_text(encoding="utf-8"))
        if device is not None:
            data["device"] = device
        config = cls(**data)
        config.validate()
        return config

    def validate(self) -> None:
        if self.device not in ("cpu", "cuda"):
            raise ValueError("Use an explicit cpu or cuda device; no automatic fallback.")
        if self.episode_steps != 500 or self.reward_function_version != "v2":
            raise ValueError("This version fixes 500-step episodes and default v2 dense rewards.")
        if (self.train_freq, self.gradient_steps, self.target_update_interval, self.n_steps) != (1, 1, 1, 1):
            raise ValueError("Exactly one one-step SAC iteration per eligible transition is required.")
        if any((self.normalize_observations, self.normalize_rewards, self.use_sde,
                self.optimize_memory_usage)) or self.action_noise is not None:
            raise ValueError("Unsupported normalization, exploration, or replay change.")
        if not self.handle_timeout_termination or self.n_critics != 2:
            raise ValueError("Timeout bootstrapping and two critics are required.")
        if self.smoke_train_steps < 4000 or self.smoke_train_steps % 4000:
            raise ValueError("Training validation must cover complete eight-episode blocks.")
        if self.resume_steps < 500 or self.resume_steps % 500:
            raise ValueError("Resume validation must end at an episode boundary.")
        if self.buffer_size <= self.smoke_train_steps + self.resume_steps:
            raise ValueError("Use the design's replay capacity for the real training validation.")
        if self.ent_coef != "auto" or self.target_entropy != "auto":
            raise ValueError("Use automatic entropy adjustment and action-dimension target entropy.")
        if self.learning_starts >= self.smoke_train_steps:
            raise ValueError("Validation must include actual gradient updates.")
        if not 0 < self.validation_eval_episodes_per_task <= self.diagnostic_bank_episodes_per_task:
            raise ValueError("Evaluation must cover a nonempty subset of the diagnostic bank.")
        if (self.resume_atol, self.resume_rtol) != (0, 0):
            raise ValueError("This version validates exact same-runtime equality.")

    def to_dict(self) -> dict:
        return asdict(self)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def derived_seed(root: int, domain: int, *indices: int) -> int:
    """Stable across processes; never use Python's randomized hash()."""
    return int(np.random.SeedSequence([root, domain, *indices]).generate_state(1)[0])


def configure_runtime(config: Config) -> None:
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    torch.set_num_threads(config.torch_threads)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(config.deterministic_torch)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    if config.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is unavailable.")
    seed_learning(config.seed)


def seed_learning(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def capture_rng() -> dict:
    return {
        "python": random.getstate(),
        "numpy": np.random.get_state(),
        "torch_cpu": torch.get_rng_state().clone(),
        "torch_cuda": [s.clone() for s in torch.cuda.get_rng_state_all()]
        if torch.cuda.is_initialized() else [],
    }


def restore_rng(state: dict) -> None:
    random.setstate(state["python"])
    np.random.set_state(state["numpy"])
    torch.set_rng_state(state["torch_cpu"])
    if state["torch_cuda"]:
        torch.cuda.set_rng_state_all(state["torch_cuda"])


@contextmanager
def isolated_rng():
    state = capture_rng()
    try:
        yield
    finally:
        restore_rng(state)


def fingerprint(value: Any) -> str:
    """Canonical tensor/array hashing, independent of Python storage addresses."""
    digest = hashlib.sha256()

    def visit(item: Any) -> None:
        if isinstance(item, torch.Tensor):
            item = item.detach().cpu().contiguous().numpy()
        if isinstance(item, np.ndarray):
            digest.update(b"array" + str(item.dtype).encode() + str(item.shape).encode())
            digest.update(np.ascontiguousarray(item).tobytes())
        elif isinstance(item, dict):
            digest.update(b"dict")
            for key in sorted(item, key=lambda x: (type(x).__name__, str(x))):
                visit(key)
                visit(item[key])
        elif isinstance(item, (tuple, list)):
            digest.update(type(item).__name__.encode() + str(len(item)).encode())
            for child in item:
                visit(child)
        elif isinstance(item, np.generic):
            visit(item.item())
        elif item is None or isinstance(item, (str, bool, int, float)):
            digest.update(type(item).__name__.encode() + b":" + repr(item).encode("utf-8") + b";")
        else:
            raise TypeError(f"Unsupported fingerprint value: {type(item)}")

    visit(value)
    return digest.hexdigest()


def file_sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def write_json(path: Path, data: Any) -> None:
    """Exclusive creation: completed artifacts are never silently overwritten."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False, allow_nan=False,
                  default=lambda x: x.tolist() if isinstance(x, np.ndarray) else
                  x.item() if isinstance(x, np.generic) else str(x))
        handle.write("\n")


def source_files() -> list[Path]:
    files = sorted(ROOT.glob("*.py")) + sorted(ROOT.glob("*.ps1"))
    files += [ROOT / "requirements.txt", ROOT / "VERSION.json"]
    for directory, glob in (("practice_allocation", "*.py"), ("configs", "*.json"), ("tests", "*.py")):
        files.extend(sorted((ROOT / directory).rglob(glob)))
    return [path for path in files if path.is_file()]


def source_hashes() -> dict[str, str]:
    return {p.relative_to(ROOT).as_posix(): file_sha256(p) for p in source_files()}


def package_versions() -> dict[str, str]:
    return {name: importlib.metadata.version(name) for name in PINNED}


def runtime_manifest(config: Config, stage: str = "implementation_validation") -> dict:
    versions = package_versions()
    mismatch = {name: version for name, version in versions.items()
                if version.split("+")[0] != PINNED[name]}
    if mismatch:
        raise RuntimeError(f"Dependency versions differ from this version's pins: {mismatch}")
    try:
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                           stderr=subprocess.DEVNULL, text=True).strip()
        dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT,
                                        stderr=subprocess.DEVNULL, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        revision, dirty = None, None
    installed_names = sorted({distribution.metadata["Name"] for distribution in importlib.metadata.distributions()
                              if distribution.metadata["Name"]})
    return {
        "implementation": config.version, "stage": stage,
        "created_at": utc_now(), "config": config.to_dict(),
        "config_hash": fingerprint(config.to_dict()), "source_hashes": source_hashes(),
        "git_revision": revision, "git_dirty": bool(dirty),
        "packages": versions,
        "installed_packages": {name: importlib.metadata.version(name) for name in installed_names},
        "python": sys.version, "platform": platform.platform(),
        "processor": platform.processor(), "logical_cpus": os.cpu_count(),
        "device": config.device, "torch_threads": torch.get_num_threads(),
        "cuda_runtime": torch.version.cuda, "cuda_available": torch.cuda.is_available(),
        "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "gpu_total_bytes": torch.cuda.get_device_properties(0).total_memory if torch.cuda.is_available() else None,
        "environment": {
            "tasks": dict(zip(TASKS, ENV_NAMES)), "observation": "39 goal-observable state values + 4 one-hot IDs",
            "reset_distribution": "continuous official per-task _random_reset_space",
            "reset_strategy": "fresh environment per episode; seed() before reset; freeze disabled",
            "reward": "unmodified MetaWorld v2 dense reward", "normalization": "none",
            "train_termination": "500-step truncation; success does not terminate",
            "eval_termination": "first success or 500-step truncation",
        },
        "seed_domains": {"schedule": 10, "train_reset": 20, "warmup_action": 30,
                         "diagnostic_bank": 100, "outcome_bank": 200, "validation_actions": 300},
        "update_contract": "transition t > 1000: exactly one stock SB3 SAC train iteration; checkpoint after update",
        "runtime_environment": "venv may reuse installed system/user packages; exact resolved packages are recorded",
    }


class AllocationSchedule:
    """Exact eight-episode quotas, shuffled independently of training RNG."""

    def __init__(self, candidate: str, seed: int):
        if candidate not in ALLOCATIONS:
            raise ValueError(f"Unknown candidate: {candidate}")
        self.candidate = candidate
        self.rng = np.random.default_rng(seed)
        self.block: list[int] = []
        self.position = 0
        self.blocks_generated = 0

    def next_task(self) -> int:
        if self.position == len(self.block):
            block = np.repeat(np.arange(4), ALLOCATIONS[self.candidate])
            self.block = self.rng.permutation(block).tolist()
            self.position = 0
            self.blocks_generated += 1
        task = self.block[self.position]
        self.position += 1
        return task

    def state(self) -> dict:
        return copy.deepcopy({"candidate": self.candidate, "rng": self.rng.bit_generator.state,
                              "block": self.block, "position": self.position,
                              "blocks_generated": self.blocks_generated})

    @classmethod
    def from_state(cls, state: dict) -> "AllocationSchedule":
        obj = cls(state["candidate"], 0)
        obj.rng.bit_generator.state = copy.deepcopy(state["rng"])
        obj.block = list(state["block"])
        obj.position = state["position"]
        obj.blocks_generated = state["blocks_generated"]
        return obj
