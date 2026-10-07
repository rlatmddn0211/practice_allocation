"""Run the fixed 400k-step P0, or an explicitly separate 8k runner smoke test."""

from __future__ import annotations

import argparse
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

from practice_allocation.core import ROOT, Config, configure_runtime
from practice_allocation.pretraining import Plan, Pretraining, verify_validation


@contextmanager
def exclusive_worker():
    """An OS lock releases on exit/crash and prevents duplicate P0 workers."""
    lock_path = ROOT / "results" / "worker.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "pretraining.json")
    parser.add_argument("--output", type=Path, help="New directory inside this version's results/.")
    parser.add_argument("--smoke", action="store_true", help="Technical 8k runner test; never counts as P0.")
    parser.add_argument("--preflight", type=Path, help="Successful current-version implementation validation.")
    parser.add_argument("--runner-validation", type=Path, help="Successful current-version runner smoke test.")
    args = parser.parse_args()
    config = Config.load(args.config)
    configure_runtime(config)
    plan = Plan.smoke() if args.smoke else Plan()
    evidence = {}
    if not args.smoke and (args.preflight is None or args.runner_validation is None):
        parser.error("P0 requires --preflight and --runner-validation evidence from this version.")
    if args.preflight is not None:
        evidence["implementation"] = verify_validation(args.preflight, config)
    if args.runner_validation is not None:
        evidence["runner"] = verify_validation(args.runner_validation, config, runner=True)
    results_root = (ROOT / "results").resolve()
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"_{plan.stage}_{config.device}_" + uuid4().hex[:8]
    output = args.output.resolve() if args.output else results_root / name
    if output == results_root or not output.is_relative_to(results_root):
        parser.error("--output must name a new directory inside this version's results/.")
    with exclusive_worker():
        output.mkdir(parents=True, exist_ok=False)
        print(f"New {plan.stage} run: {output}", flush=True)
        return 0 if Pretraining(config, plan, output, evidence).run() else 1


if __name__ == "__main__":
    raise SystemExit(main())
