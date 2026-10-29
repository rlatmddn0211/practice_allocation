"""Run the real implementation gates; never starts P0 automatically."""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

# This must be set before torch initializes CUDA.
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

from practice_allocation.core import ROOT, Config, configure_runtime
from practice_allocation.preflight import Preflight


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "validation.json")
    parser.add_argument("--device", choices=("cpu", "cuda"), help="Explicitly override and record the compute device.")
    parser.add_argument("--output", type=Path, help="Must be a new directory under this version's results/.")
    args = parser.parse_args()
    config = Config.load(args.config, args.device)
    configure_runtime(config)
    results_root = (ROOT / "results").resolve()
    run_name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"_{config.device}_" + uuid4().hex[:8]
    output = args.output.resolve() if args.output else results_root / run_name
    if not output.is_relative_to(results_root) or output == results_root:
        parser.error("--output must name a new directory inside this implementation's results/.")
    output.mkdir(parents=True, exist_ok=False)
    print(f"New validation run: {output}", flush=True)
    return 0 if Preflight(config, output).run() else 1


if __name__ == "__main__":
    raise SystemExit(main())
