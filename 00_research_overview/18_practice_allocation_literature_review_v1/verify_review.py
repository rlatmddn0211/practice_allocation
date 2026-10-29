"""Preserve an immutable review snapshot and check references, metadata and links.

This checks document integrity, not scientific correctness or completeness.
Standard library only. No network, training, or environment interaction.
"""

from __future__ import annotations

import csv
import hashlib
import json
import platform
import re
import shutil
import sys
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    started = time.perf_counter()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "verification" / f"{timestamp}_{uuid.uuid4().hex[:8]}"
    output.mkdir(parents=True, exist_ok=False)
    snapshot = output / "source_snapshot"
    snapshot.mkdir()
    checks = []
    inputs = {}
    errors = []

    def check(name: str, passed: bool, detail=None):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    try:
        files = [ROOT / name for name in (
            "README.md", "literature_review_ko.md", "sources.json",
            "search_log.json", "verify_review.py",
        )]
        for path in files:
            shutil.copy2(path, snapshot / path.name)
            inputs[str(path.relative_to(REPO))] = sha256(path)

        refs = json.loads((snapshot / "sources.json").read_text(encoding="utf-8"))
        search = json.loads((snapshot / "search_log.json").read_text(encoding="utf-8"))
        report = (snapshot / "literature_review_ko.md").read_text(encoding="utf-8")
        papers = refs["papers"]
        identifiers = [paper["id"] for paper in papers]
        cutoff = date.fromisoformat(refs["cutoff_date"])
        check("unique_reference_ids", len(set(identifiers)) == len(identifiers))
        check("18_curated_references", len(papers) == 18, len(papers))
        check("consistent_cutoff", search["cutoff_date"] == refs["cutoff_date"])
        check("reference_dates_before_cutoff", all(
            date.fromisoformat(p["date_for_cutoff"]) <= cutoff for p in papers
        ))
        check("evidence_locators_and_read_depth", all(
            p["locators"] and p["read_depth"] and p["boundary"] for p in papers
        ))
        cited_ids = set(re.findall(r"\bP\d{2}\b", report))
        check("all_reference_ids_used", set(identifiers) == cited_ids,
              {"unused": sorted(set(identifiers) - cited_ids),
               "unknown": sorted(cited_ids - set(identifiers))})

        allowed_web = {p[k].split("#")[0] for p in papers for k in ("url", "full_text")}
        links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", report)
        web_links = [link for link in links if link.startswith("https://")]
        check("web_citations_registered", all(link.split("#")[0] in allowed_web for link in web_links),
              sorted({link for link in web_links if link.split("#")[0] not in allowed_web}))
        check("https_primary_source_links", all(
            urlsplit(link).scheme == "https" for link in allowed_web
        ))
        local_links = [link for link in links if not urlsplit(link).scheme]
        missing = []
        for link in local_links:
            path = (ROOT / unquote(link.split("#")[0])).resolve()
            if not path.exists():
                missing.append(link)
            elif path.is_file():
                inputs[str(path.relative_to(REPO))] = sha256(path)
        check("local_evidence_links_exist", not missing, missing)
        check("no_internal_web_reference_tokens", not re.search(r"turn\d+(?:view|search|academia)\d+|\ue200", report))
        check("no_replacement_characters", "\ufffd" not in report)

        rows = [
            {key: p[key] for key in (
                "id", "short_name", "year", "status", "domain", "budget_role",
                "interaction_model", "diagnostic_cost", "boundary", "url", "read_depth",
            )}
            for p in papers
        ]
        with (output / "comparison.csv").open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

        # Produce a convenience copy only when absent; immutable runs always retain theirs.
        convenience = ROOT / "comparison.csv"
        if not convenience.exists():
            shutil.copy2(output / "comparison.csv", convenience)
        check("comparison_matches_current_sources", convenience.read_bytes() == (output / "comparison.csv").read_bytes())
    except Exception as exc:
        errors.append({"type": type(exc).__name__, "message": str(exc)})
        check("verification_completed", False, errors[-1])

    result = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "passed": bool(checks) and all(item["passed"] for item in checks) and not errors,
        "checks": checks,
        "errors": errors,
        "input_sha256": inputs,
        "output_sha256": {p.name: sha256(p) for p in output.iterdir() if p.is_file()},
        "environment": {"python": sys.version, "platform": platform.platform(), "dependencies": "Python standard library only"},
        "actual_cost": {"verification_wall_seconds": time.perf_counter() - started,
                        "training_steps": 0, "evaluation_episodes": 0,
                        "financial_cost": "not measured", "random_seed": "not applicable; document checks only"},
        "limits": "Mechanical checks do not validate scientific interpretations, priority claims, or cited empirical results.",
    }
    (output / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "passed": result["passed"],
                      "checks": len(checks), "failures": [c for c in checks if not c["passed"]]}, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
