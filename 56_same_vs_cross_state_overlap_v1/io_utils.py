"""File-only utilities; no experiment or analysis computations."""
import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))

def dump(path, value):
    def serial(obj):
        if hasattr(obj, "tolist"): return obj.tolist()
        if hasattr(obj, "item"): return obj.item()
        raise TypeError(type(obj).__name__)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=serial, allow_nan=False)+"\n", encoding="utf-8")

def csvout(path, values):
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer=csv.DictWriter(stream, fieldnames=list(values[0]))
        writer.writeheader(); writer.writerows(values)
