"""Build the report using the protected installed runtime; preserve every attempt."""
from pathlib import Path
import hashlib, json, shutil, subprocess, sys, time, uuid
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
APP = ROOT / "report_app"
PLUGIN = Path(r"C:\Users\SS\.codex\plugins\cache\openai-curated-remote\data-analytics\1.0.11")
out = ROOT / "results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_build_" + uuid.uuid4().hex[:8])
out.mkdir(parents=True, exist_ok=False)
start = time.perf_counter()
def sha(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()
inputs = [Path(__file__), APP / "src/data.json", APP / "src/theme.css", *sorted((APP / "src/content/report").rglob("*"))]
hashes = {}
for p in inputs:
    if p.is_file():
        rel = p.relative_to(ROOT)
        target = out / "source_snapshot" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, target)
        hashes[str(rel)] = sha(p)
command = [r"C:\Program Files\nodejs\node.exe", str(PLUGIN / "scripts/data-app.mjs"), "build", "--project-dir", str(APP), "--separate-data"]
result = subprocess.run(command, capture_output=True)
(out / "stdout.log").write_bytes(result.stdout)
(out / "stderr.log").write_bytes(result.stderr)
record = {"exit_code": result.returncode, "command": command, "source_hashes": hashes, "wall_seconds": time.perf_counter()-start,
          "python": sys.version, "dist_hashes": {p.name:sha(p) for p in (APP / "dist").glob("*") if p.is_file()} if result.returncode == 0 else {}}
(out / "build.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
print(json.dumps({"output":str(out),"exit_code":result.returncode}))
print(result.stdout.decode("utf-8",errors="replace"))
if result.returncode:
    print(result.stderr.decode("utf-8",errors="replace"))
    raise SystemExit(result.returncode)
