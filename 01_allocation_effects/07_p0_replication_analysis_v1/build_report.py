"""Build the local report, preserving each invocation and its source bytes."""
import argparse
import hashlib
import json
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = ROOT / "report_app"
PLUGIN = Path(r"C:\Users\SS\.codex\plugins\cache\openai-curated-remote\data-analytics\1.0.11")
NODE = Path(r"C:\Program Files\nodejs\node.exe")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--complete", action="store_true")
    args = parser.parse_args()
    if args.complete:
        data_path = APP / "src/data.json"
        data = json.loads(data_path.read_text(encoding="utf-8"))
        data["buildStatus"] = "complete"
        data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output = ROOT / "results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_report_build_" + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    snapshot = output / "source_snapshot"
    snapshot.mkdir()
    shutil.copy2(__file__, snapshot / "build_report.py")
    shutil.copytree(APP / "src", snapshot / "src")
    sources = {p.relative_to(APP).as_posix(): sha(p) for p in sorted((APP / "src").rglob("*")) if p.is_file()}
    command = [str(NODE), str(PLUGIN / "scripts/data-app.mjs"), "build", "--project-dir", str(APP), "--separate-data"]
    start = time.perf_counter()
    run = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    (output / "stdout.log").write_text(run.stdout, encoding="utf-8")
    (output / "stderr.log").write_text(run.stderr, encoding="utf-8")
    unchanged = all(sha(APP / name) == expected for name, expected in sources.items())
    if run.returncode == 0:
        shutil.copytree(APP / "dist", output / "dist")
    record = {"created_at": datetime.now(timezone.utc).isoformat(), "status": "passed" if run.returncode == 0 and unchanged else "failed",
              "source_hashes": sources, "script_sha256": sha(Path(__file__)), "source_unchanged": unchanged,
              "plugin_version": "1.0.11", "build_script_sha256": sha(PLUGIN / "scripts/data-app.mjs"), "command": command,
              "node_version": subprocess.check_output([str(NODE), "--version"], text=True).strip(),
              "exit_code": run.returncode, "seconds": time.perf_counter() - start,
              "additional_training_steps": 0, "additional_policy_evaluation_episodes": 0,
              "built_files": {p.relative_to(output / "dist").as_posix(): sha(p) for p in (output / "dist").rglob("*") if p.is_file()} if run.returncode == 0 else {}}
    (output / "verification.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": record["status"], "output": str(output), "build_output": run.stdout[-3500:], "error": run.stderr[-2000:]}, ensure_ascii=False))
    raise SystemExit(0 if record["status"] == "passed" else 1)
