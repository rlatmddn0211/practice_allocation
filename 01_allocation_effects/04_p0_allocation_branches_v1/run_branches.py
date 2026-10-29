"""Launch ten authorized branches, or a separate five-allocation runner smoke."""

import argparse
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

from practice_allocation.branch_protocol import BranchPlan, verify_evidence
from practice_allocation.branches import BranchExperiment
from practice_allocation.core import ROOT, Config, configure_runtime, utc_now, write_json


@contextmanager
def exclusive_worker():
    lock = ROOT / "results/worker.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+b") as handle:
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/learner.json")
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--runner-validation", type=Path)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.smoke and args.runner_validation is None:
        parser.error("Research branches require a successful current-version runner smoke.")
    config = Config.load(args.config)
    if config.device != "cuda" or config.version != "04_p0_allocation_branches_v1":
        parser.error("The pinned parent requires this version and the original CUDA runtime.")
    configure_runtime(config)
    plan = BranchPlan.smoke() if args.smoke else BranchPlan()
    results = (ROOT / "results").resolve()
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"_{plan.stage}_cuda_" + uuid4().hex[:8]
    output = args.output.resolve() if args.output else results / name
    if output == results or not output.is_relative_to(results):
        parser.error("Output must be a new directory inside this version's results/.")
    with exclusive_worker():
        output.mkdir(parents=True, exist_ok=False)
        try:
            evidence = {"implementation": verify_evidence(args.preflight, config)}
            if args.runner_validation:
                evidence["runner"] = verify_evidence(args.runner_validation, config, runner=True)
        except Exception as error:
            write_json(output / "launch_validation_failed.json", {
                "created_at": utc_now(), "status": "failed", "error": repr(error)})
            raise
        print(f"New {plan.stage} run: {output}", flush=True)
        return 0 if BranchExperiment(config, plan, output, evidence).run() else 1


if __name__ == "__main__":
    raise SystemExit(main())
