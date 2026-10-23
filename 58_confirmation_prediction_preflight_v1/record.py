"""Run recording only; no shared statistical computations."""
import csv
import hashlib
import json
import platform
import shutil
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def csvout(path, values):
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(values[0]))
        writer.writeheader()
        writer.writerows(values)


class Run:
    def __init__(self, name):
        self.start, self.cpu = time.perf_counter(), time.process_time()
        self.out = HERE / "results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + name + "_" + uuid.uuid4().hex[:8])
        self.out.mkdir(parents=True, exist_ok=False)
        (self.out / "source_snapshot").mkdir()
        (self.out / "input_snapshot").mkdir()
        self.checks, self.inputs = [], []
        sources = {}
        for path in sorted(HERE.iterdir()):
            if path.is_file() and path.suffix in {".py", ".json", ".md"}:
                shutil.copy2(path, self.out / "source_snapshot" / path.name)
                sources[path.name] = sha(path)
        dump(self.out / "source_hashes.json", sources)
        print(self.out, flush=True)

    def check(self, condition, label):
        self.checks.append({"name": label, "passed": bool(condition)})
        if not condition:
            raise AssertionError(label)

    def near(self, actual, expected, label, tol=1e-11):
        self.check(abs(float(actual) - float(expected)) <= tol, label)

    def input(self, path, expected=None):
        path = Path(path)
        digest = sha(path)
        if expected:
            self.check(digest == expected, "input_hash:" + str(path))
        filename = str(len(self.inputs)).zfill(2) + "_" + path.name
        shutil.copy2(path, self.out / "input_snapshot" / filename)
        self.inputs.append({"path": str(path), "sha256": digest, "snapshot": filename})

    def finish(self, result=None, exc=None):
        dump(self.out / "checks.json", self.checks)
        dump(self.out / "inputs.json", self.inputs)
        dump(self.out / "runtime.json", {
            "wall_seconds": time.perf_counter() - self.start,
            "cpu_seconds": time.process_time() - self.cpu,
            "python": sys.version, "platform": platform.platform(), "dependencies": "Python standard library only",
            "new_training_steps": 0, "new_evaluation_steps": 0, "new_environment_steps": 0,
            "new_SAC_updates": 0, "success": exc is None,
        })
        if exc is not None:
            dump(self.out / "FAILED.json", {"error": repr(exc), "traceback": traceback.format_exc(), "new_environment_steps": 0})
            traceback.print_exc()
            return 1
        result = {**(result or {}), "checks_passed": len(self.checks), "new_environment_steps": 0, "new_training_steps": 0, "new_SAC_updates": 0}
        dump(self.out / "COMPLETE.json", result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return 0
