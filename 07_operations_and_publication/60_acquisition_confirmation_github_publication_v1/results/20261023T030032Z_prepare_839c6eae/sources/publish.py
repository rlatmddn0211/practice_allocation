"""Publish a fixed research snapshot while the approved training continues."""
import argparse
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
V59 = ROOT / "59_fresh_future_confirmation_v1"
CAMPAIGN = V59 / "results/20261022T062003Z_fresh_confirmation_2e8df6e0"
TECH = V59 / "results/20261022T061733Z_technical_8d040174/VERIFIED.json"
REMOTE = "https://github.com/rlatmddn0211/practice_allocation.git"


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True).stdout


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path):
    return path.resolve().relative_to(ROOT).as_posix()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["prepare", "verify"])
    parser.add_argument("--preparation", type=Path)
    args = parser.parse_args()
    wall, cpu = time.perf_counter(), time.process_time()
    out = HERE / "results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                                 + "_" + args.mode + "_" + uuid.uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    (out / "sources").mkdir()
    shutil.copy2(__file__, out / "sources/publish.py")
    save(out / "source_hashes.json", {"publish.py": sha(Path(__file__))})
    save(out / "runtime.json", {"python": sys.version, "git": git("--version").decode().strip(),
                               "dependencies": "Python standard library and Git"})
    checks, rows, links = [], [], []
    groups = defaultdict(lambda: {"files": 0, "bytes": 0})
    error = None

    def check(name, condition):
        checks.append({"check": name, "passed": bool(condition)})
        if not condition:
            raise AssertionError(name)

    try:
        check("authorized origin", git("remote", "get-url", "origin").decode().strip() == REMOTE)
        check("main branch", git("branch", "--show-current").decode().strip() == "main")
        check("remote baseline synchronized", git("rev-parse", "HEAD") == git("rev-parse", "origin/main"))
        for rel, expected in load(TECH)["source_hashes"].items():
            check("active experiment source unchanged: " + rel, sha(V59 / rel) == expected)

        if args.mode == "prepare":
            staged_changes = [p for p in git("diff", "--cached", "--name-only", "-z").split(b"\0") if p]
            check("existing staging belongs to this publication", all(
                p.decode("utf-8") in [".gitattributes", "AGENTS.md", "README.md"]
                or re.match(r"^(52_|5[4-9]_|60_acquisition_confirmation_github_publication_v1/)", p.decode("utf-8"))
                for p in staged_changes))
            status = load(CAMPAIGN / "STATUS.json")
            save(out / "campaign59_status.json", status)
            completed = {}
            for marker in sorted((CAMPAIGN / "completed").glob("*.json")):
                record = load(marker)
                if record["completed_at"] > status["updated_at"]:
                    continue
                for key in ["result", "costs"]:
                    check("completed evidence: " + marker.stem + ":" + key,
                          sha(Path(record[key]["path"])) == record[key]["sha256"])
                result = load(Path(record["result"]["path"]))
                check("completed 32k and immutable evaluation: " + marker.stem,
                      result["status"] == "completed" and result["training_steps"] == 32000
                      and result["fork_verified"] and result["evaluation_state_unchanged"])
                check("evaluation episode bytes: " + marker.stem,
                      sha(Path(result["episodes"]["path"])) == result["episodes"]["sha256"])
                for checkpoint in result["checkpoints"]:
                    check("checkpoint manifest: " + marker.stem + ":" + str(checkpoint["absolute_step"]),
                          sha(Path(checkpoint["path"]) / "checkpoint_manifest.json") == checkpoint["manifest_sha256"])
                completed[marker.stem] = relative(Path(record["attempt"])) + "/"
            check("completion count agrees with snapshot", len(completed) == status["completed"])
            if status["status"] == "completed":
                receipt = load(CAMPAIGN / "COMPLETE.json")["summary"]
                check("completion summary hash", sha(Path(receipt["path"])) == receipt["sha256"])
                summary = load(Path(receipt["path"]))
                check("all twenty futures complete", len(completed) == 20)
                check("cost sums and budget", summary["research_training_steps"] == 640000
                      and sum(r["costs"]["evaluation_steps"] for r in summary["results"]) == summary["research_evaluation_steps"]
                      and summary["total_environment_steps"] == summary["research_training_steps"]
                          + summary["research_evaluation_steps"] + summary["technical_environment_steps_all_attempts"]
                      and summary["total_environment_steps"] <= 4650000)
            candidates = staged_changes + git("ls-files", "--others", "--exclude-standard", "-z").split(b"\0")
            selected = [".gitattributes", "AGENTS.md", "README.md"]
            for raw in candidates:
                if not raw:
                    continue
                rel = raw.decode("utf-8")
                if not re.match(r"^(52_|5[4-9]_)", rel):
                    continue
                if rel.endswith(("/stdout.log", "/stderr.log")):
                    continue
                if rel.startswith("59_"):
                    if rel.endswith("/ACTIVE_CAMPAIGN.json"):
                        continue
                    if "/jobs/" in rel and not any(rel.startswith(p) for p in completed.values()):
                        continue
                    if "/completed/" in rel and Path(rel).stem not in completed:
                        continue
                selected.append(rel)
            selected = sorted(set(selected))
            for rel in selected:
                path = ROOT / rel
                check("ordinary Git size: " + rel, path.stat().st_size < 50 * 1024**2)
                rows.append({"path": rel, "bytes": path.stat().st_size, "sha256": sha(path)})
            save(out / "publication_scope.json", {
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "base_commit": git("rev-parse", "HEAD").decode().strip(),
                "snapshot_timestamp": status["updated_at"],
                "completed_futures": list(completed), "completed": len(completed), "total": 20,
                "selected_file_count": len(selected), "selected_files": selected,
                "excluded": ["unfinished futures", "live controller logs", "existing Git-ignored checkpoints/replay/NPZ/source duplicates"],
                "scientific_analysis": "No new F3/F4 scientific analysis; frozen protocol remains unchanged."})
            (out / "staging_paths.nul").write_bytes(b"\0".join(p.encode("utf-8") for p in selected) + b"\0")
        else:
            check("preparation specified", args.preparation is not None)
            prep = args.preparation.resolve()
            scope = load(prep / "publication_scope.json")
            check("same base commit", git("rev-parse", "HEAD").decode().strip() == scope["base_commit"])
            original = {r["path"]: r for r in csv.DictReader((prep / "manifest.csv").open(encoding="utf-8", newline=""))}
            staged = {}
            for entry in git("ls-files", "--stage", "-z").split(b"\0"):
                if not entry:
                    continue
                meta, raw = entry.split(b"\t", 1)
                _, blob, level = meta.decode().split()
                rel = raw.decode("utf-8")
                check("no unmerged index entry: " + rel, level == "0")
                staged[rel] = blob
            changed = [p.decode("utf-8") for p in git("diff", "--cached", "--name-only", "-z").split(b"\0") if p]
            check("all selected files staged", set(scope["selected_files"]).issubset(changed))
            check("only selected scope plus publication record staged",
                  all(p in scope["selected_files"] or p.startswith(HERE.name + "/") for p in changed))
            fmt = git("rev-parse", "--show-object-format").decode().strip()
            patterns = [rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", rb"ghp_[A-Za-z0-9]{36}",
                        rb"github_pat_[A-Za-z0-9_]{70,}", rb"AKIA[0-9A-Z]{16}", rb"sk-proj-[A-Za-z0-9_-]{40,}"]
            for rel in changed:
                data = (ROOT / rel).read_bytes()
                digest = hashlib.new(fmt, b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
                # Root indexes retain their existing text normalization policy.
                expected_blob = (git("hash-object", "--path=" + rel, "--", rel).decode().strip()
                                 if rel in [".gitattributes", "AGENTS.md", "README.md"] else digest)
                check("staged file matches worktree: " + rel, staged[rel] == expected_blob)
                if rel not in [".gitattributes", "AGENTS.md", "README.md"]:
                    check("preserve exact experiment bytes: " + rel, staged[rel] == digest)
                check("ordinary Git size: " + rel, len(data) < 50 * 1024**2)
                check("no concrete credential markers: " + rel, not any(re.search(p, data) for p in patterns))
                if rel in original:
                    check("prepared file unchanged: " + rel, hashlib.sha256(data).hexdigest() == original[rel]["sha256"])
                rows.append({"path": rel, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
            primary = [ROOT / "README.md", HERE / "README.md"]
            primary += [p for p in ROOT.glob("5[4-9]*/*.md") if p.name in {
                "README.md", "report_ko.md", "one_page_spec_ko.md", "statistical_spec_ko.md",
                "paper_scope_ko.md", "evidence_record_ko.md"}]
            for doc in primary:
                for match in re.finditer(r"!?\[[^\]]*\]\(([^)]+)\)", doc.read_text(encoding="utf-8-sig")):
                    href = match.group(1).strip().split(" ", 1)[0].strip("<>")
                    if href.startswith(("http:", "https:", "#", "mailto:")):
                        continue
                    target = (doc.parent / unquote(href.split("#", 1)[0])).resolve()
                    check("local link exists: " + str(target), target.exists())
                    local = relative(target) if target.is_relative_to(ROOT) else str(target)
                    public = local in staged or (target.is_dir() and any(p.startswith(local + "/") for p in staged))
                    links.append({"document": relative(doc), "target": local, "available_in_git": public})
            save(out / "links.json", links)
            save(out / "preparation_receipt.json", {"path": relative(prep), "scope_sha256": sha(prep / "publication_scope.json")})
    except BaseException as exc:
        error = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
    finally:
        with (out / "manifest.csv").open("x", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["path", "bytes", "sha256"])
            writer.writeheader()
            writer.writerows(rows)
        for row in rows:
            group = groups[row["path"].split("/")[0]]
            group["files"] += 1
            group["bytes"] += int(row["bytes"])
        save(out / "checks.json", checks)
        summary = {"status": "failed" if error else "passed", "error": error, "checks": len(checks),
                   "failed_checks": [c for c in checks if not c["passed"]], "files": len(rows), "groups": dict(groups),
                   "local_only_links": [l for l in links if not l["available_in_git"]],
                   "costs": {"wall_seconds": time.perf_counter() - wall, "cpu_seconds": time.process_time() - cpu,
                             "new_environment_steps": 0, "new_SAC_updates": 0}}
        save(out / "summary.json", summary)
    print(json.dumps({"run": str(out), **summary}, ensure_ascii=False), flush=True)
    return 1 if error else 0


if __name__ == "__main__":
    raise SystemExit(main())
