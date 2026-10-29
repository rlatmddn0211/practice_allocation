"""Validate a staged, byte-preserving publication without touching live training."""
import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import traceback
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True).stdout


def save(path, data):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def main():
    start, cpu = time.perf_counter(), time.process_time()
    out = HERE/"results"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                          +"_publication_check_"+uuid.uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    (out/"sources").mkdir()
    for path in HERE.glob("*.py"):
        shutil.copy2(path, out/"sources"/path.name)
    save(out/"source_hashes.json", {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.glob("*.py")})
    save(out/"runtime.json", {"python": sys.version, "git": git("--version").decode().strip(),
                              "dependencies": "Python standard library and Git"})
    checks, records, links = [], [], []
    group = defaultdict(lambda: {"files": 0, "bytes": 0})
    error = None

    def check(name, condition):
        checks.append({"check": name, "passed": bool(condition)})
        if not condition:
            raise AssertionError(name)

    try:
        check("authorized remote", git("remote", "get-url", "origin").decode().strip()
              == "https://github.com/rlatmddn0211/practice_allocation.git")
        check("main branch", git("branch", "--show-current").decode().strip() == "main")
        check("fetched baseline synchronized",
              git("rev-parse", "HEAD") == git("rev-parse", "origin/main"))
        staged = {}
        for entry in git("ls-files", "--stage", "-z").split(b"\0"):
            if not entry:
                continue
            meta, path = entry.split(b"\t", 1)
            mode, blob, level = meta.decode().split()
            check("index unmerged "+path.decode(), level == "0")
            staged[path.decode("utf-8")] = blob
        fmt = git("rev-parse", "--show-object-format").decode().strip()
        for rel, blob in staged.items():
            if not re.match(r"^(3[9]|4[0-9]|5[0-3])_", rel):
                continue
            data = (ROOT/rel).read_bytes()
            digest = hashlib.new(fmt, b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
            check("staged bytes match "+rel, digest == blob)
            check("ordinary git size "+rel, len(data) < 50*1024**2)
            check("no browser or offline cache "+rel,
                  "/profile/" not in rel and "/.data-app-offline/" not in rel)
            check("no live research job "+rel,
                  not (rel.startswith("52_") and "_future_replication_" in rel and "/jobs/" in rel))
            records.append({"path": rel, "bytes": len(data),
                            "sha256": hashlib.sha256(data).hexdigest(), "git_blob": blob})
            top = rel.split("/")[0]
            group[top]["files"] += 1
            group[top]["bytes"] += len(data)
        check("fifteen independent version directories", len(group) == 15)
        staged_files = set(staged)
        primary = [
            ROOT/"README.md", HERE/"README.md",
            ROOT/"45_stage1_selection_value_analysis_v1/report_ko.md",
            ROOT/"47_existing_data_path_loss_analysis_v1/report_ko.md",
            ROOT/"49_bp8k_late_value_analysis_v1/report_ko.md",
            ROOT/"50_b_posthoc_concentration_review_v1/report_ko.md",
            ROOT/"51_same_state_future_investment_protocol_v1/research_protocol_ko.md",
            ROOT/"52_same_state_future_replication_v1/README.md"]
        for doc in primary:
            check("primary document staged "+doc.name, doc.relative_to(ROOT).as_posix() in staged)
            text = doc.read_text(encoding="utf-8-sig")
            for match in re.finditer(r"!?\[[^\]]*\]\(([^)]+)\)", text):
                href = match.group(1).strip().split(" ", 1)[0].strip("<>")
                if href.startswith(("https:", "http:", "#", "mailto:")):
                    continue
                target = (doc.parent/unquote(href.split("#", 1)[0])).resolve()
                local = target.relative_to(ROOT).as_posix() if target.is_relative_to(ROOT) else str(target)
                check("local target exists "+local, target.exists())
                public = local in staged_files or (
                    target.is_dir() and any(s.startswith(local+"/") for s in staged_files))
                links.append({"document": doc.relative_to(ROOT).as_posix(), "target": local,
                              "available_in_git": public, "local_only": not public})
        # Runtime inputs and already verified science are not recalculated here.
        for version, key, expected in (
            ("51_same_state_future_investment_protocol_v1", "protocol.json",
             "d1133da832a8840dfa1114d5b3a4d2386185f1519ea713be78d8a86e4fbd760d"),
            ("49_bp8k_late_value_analysis_v1",
             "results/20261020T053017Z_B_analysis_b2d46333/outcomes_25_policies.csv",
             "a69f194338a918db258a1697bcfa44e7ca84641f60a24856a77df5cb1a6e57df")):
            check("key evidence hash "+key, hashlib.sha256((ROOT/version/key).read_bytes()).hexdigest() == expected)
        frozen = json.loads((ROOT/"52_same_state_future_replication_v1/results/"
                             "20261020T094942Z_future_replication_bbc18607/plan.json").read_text(encoding="utf-8"))
        for rel, expected in frozen["source_hashes"].items():
            path = ROOT/"52_same_state_future_replication_v1"/rel
            check("running experiment source unchanged "+rel,
                  hashlib.sha256(path.read_bytes()).hexdigest() == expected)
        # High-precision credential markers only; do not print source contents.
        credential_patterns = [
            rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
            rb"ghp_[A-Za-z0-9]{36}", rb"github_pat_[A-Za-z0-9_]{70,}",
            rb"AKIA[0-9A-Z]{16}", rb"sk-proj-[A-Za-z0-9_-]{40,}"]
        hits = []
        for record in records:
            path = ROOT/record["path"]
            if path.suffix.lower() not in (".json", ".md", ".py", ".ps1", ".log", ".csv", ".txt", ".yaml", ".yml"):
                continue
            payload = path.read_bytes()
            if any(re.search(p, payload) for p in credential_patterns):
                hits.append(record["path"])
        save(out/"credential_scan.json", {"matched_paths": hits})
        check("no concrete credential markers", not hits)
    except BaseException as exc:
        error = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
    finally:
        with (out/"staged_manifest.csv").open("x", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["path", "bytes", "sha256", "git_blob"])
            writer.writeheader()
            writer.writerows(records)
        save(out/"checks.json", checks)
        save(out/"links.json", links)
        summary = {"status": "failed" if error else "passed", "error": error,
                   "checked_files": len(records), "bytes": sum(r["bytes"] for r in records),
                   "groups": dict(group), "checks": len(checks),
                   "failed_checks": [c for c in checks if not c["passed"]],
                   "local_only_links": [l for l in links if l["local_only"]],
                   "costs": {"wall_seconds": time.perf_counter()-start, "cpu_seconds": time.process_time()-cpu,
                             "new_environment_steps": 0, "new_SAC_updates": 0}}
        save(out/"summary.json", summary)
    print(json.dumps({"run": str(out), **summary}, ensure_ascii=False), flush=True)
    return 1 if error else 0


if __name__ == "__main__":
    raise SystemExit(main())
