"""One-time independent implementation copy; no imports from older versions."""
import hashlib
import json
import shutil
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def main():
    out = HERE / "results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_bootstrap_" + uuid.uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    (out / "source_snapshot").mkdir()
    shutil.copy2(__file__, out / "source_snapshot" / "bootstrap.py")
    write(out / "source_hashes.json", {"bootstrap.py": sha(__file__)})
    start = time.perf_counter()
    try:
        if (HERE / "practice_allocation").exists() or (HERE / "inputs").exists():
            raise RuntimeError("Bootstrap is one-time; preserve existing files")
        old = REPO / "52_same_state_future_replication_v1"
        before = {}
        for directory in ["practice_allocation", "configs"]:
            (HERE / directory).mkdir()
            for source in (old / directory).iterdir():
                if source.is_file() and source.suffix in {".py", ".json"}:
                    target = HERE / directory / source.name
                    shutil.copy2(source, target)
                    before[str(source.relative_to(old))] = {"source": str(source), "sha256": sha(source)}
        for name in ["common.py", "worker.py", "campaign.py", "verify_implementation.py", "launch_queue.ps1", "requirements.txt"]:
            shutil.copy2(old / name, HERE / name)
            before[name] = {"source": str(old / name), "sha256": sha(old / name)}
        (HERE / "inputs").mkdir()
        previous = REPO / "58_confirmation_prediction_preflight_v1"
        inputs = [
            (previous / "protocol.json", "protocol58.json", "438d2b23889c1242319f1592b86e0ff3ca2fa462992db6a3c9d41e669e8ffc7c"),
            (previous / "inputs/frozen_reference_predictions.csv", "frozen_reference_predictions.csv", "e0c34c7c0b010b767e51de6e6ea6d546e7f41d738511117238deabb803f35cc8"),
            (previous / "inputs/proposed_jobs.csv", "proposed_jobs.csv", "db70f8888ad578267c2de1197abc2a248dead4b50f7b310fabf8ae87d40311bf"),
            (previous / "inputs/state_manifest.json", "state_manifest.json", "63728184cc1cdf4dcccacfd7140fc3c1e66908c4bef5c7f8182b4f0a7f953607"),
            (previous / "inputs/paired_outcomes.csv", "reference_paired_outcomes.csv", "7c75c6186ae833ecfb3f9a71180c87bcd7aec37137ee6cd85c6490eec3750efb"),
            (REPO / "49_bp8k_late_value_analysis_v1/results/20261020T053017Z_B_analysis_b2d46333/outcomes_25_policies.csv", "known_8k_outcomes.csv", "a69f194338a918db258a1697bcfa44e7ca84641f60a24856a77df5cb1a6e57df"),
        ]
        provenance = []
        for source, name, expected in inputs:
            if sha(source) != expected:
                raise RuntimeError("Frozen input hash mismatch: " + str(source))
            shutil.copy2(source, HERE / "inputs" / name)
            provenance.append({"source": str(source), "copy": "inputs/" + name, "sha256": expected})
        write(HERE / "inputs/provenance.json", provenance)
        write(HERE / "inputs/copied_implementation.json", before)
        write(HERE / "VERSION.json", {"version": HERE.name, "parent_implementation": old.name, "learner_environment_evaluation": "byte-identical independent copies", "change": "20 F3/F4 futures under frozen protocol58, RNG-only fork and technical gate"})
        frozen = json.loads((HERE / "inputs/protocol58.json").read_text(encoding="utf-8"))
        protocol = {
            "version": HERE.name, "status": "authorized_first_confirmation_bundle",
            "authorization_date": "2026-10-22",
            "authorization": "User approved technical full-state/RNG checks, then all twenty frozen F3/F4 futures without design changes or automatic retries.",
            "scientific_protocol": "inputs/protocol58.json",
            "scientific_protocol_sha256": inputs[0][2],
            "state_manifest_sha256": inputs[3][2], "fixed_predictions_sha256": inputs[1][2],
            "proposed_jobs_sha256": inputs[2][2], "reference_outcomes_sha256": inputs[4][2],
            "known_8k_outcomes_sha256": inputs[5][2],
            "states": 10, "new_futures_per_state": 2, "jobs": 20,
            "training_steps_per_future": 32000, "training_steps_total": 640000,
            "evaluation_cases_per_task": 100, "evaluation_max_steps_per_case": 500,
            "evaluation_cap_total": 4000000, "main_environment_cap": 4640000,
            "technical_environment_cap_all_attempts": 10000, "total_environment_cap": 4650000,
            "automatic_retry_reserve": 0, "max_parallel_workers": 1,
            "full_checkpoint_absolute_steps": frozen["learning_proposal"]["full_save_absolute_steps"],
            "technical_plan": {
                "full_restore_and_rng_only_checks": "all twenty F3/F4 forks, ten original states; zero environment steps",
                "same_original_rng_traces": "two separate original restores, 500 training steps each",
                "each_fresh_future_resume_check": "for both F3 and F4 of one preselected state, 1000 uninterrupted vs 500+lossless save/load+500",
                "known_8k_evaluation": "one previously evaluated case per task, at most 2000 steps",
                "maximum_first_technical_run_steps": 7000,
                "technical_state_not_reused_in_research": True,
            },
            "analysis": "Frozen protocol58 D/G, models, weights, intervals and evidence-vs-investment criteria; no new fitting or result-driven selection.",
            "failure_policy": "Stop on integrity failure; preserve all attempts/checkpoints. No automatic retry, extra futures or new parents.",
            "C_and_original_stages_2_3": "held_not_scheduled",
        }
        write(HERE / "protocol.json", protocol)
        write(out / "COMPLETE.json", {"status": "copied_for_development_not_verified", "copied_code": before, "inputs": provenance, "new_environment_steps": 0, "python": sys.version, "wall_seconds": time.perf_counter()-start})
        print(out)
        return 0
    except BaseException as exc:
        write(out / "FAILED.json", {"error": repr(exc), "traceback": traceback.format_exc(), "new_environment_steps": 0})
        raise


if __name__ == "__main__":
    raise SystemExit(main())
