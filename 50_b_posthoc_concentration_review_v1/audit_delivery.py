"""Audit the delivered supplement, retaining the exact files checked."""
import hashlib
import json
import re
import shutil
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    start = time.perf_counter()
    out = HERE / "results" / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "_delivery_" + uuid.uuid4().hex[:8])
    snapshot = out / "source_snapshot"
    snapshot.mkdir(parents=True, exist_ok=False)
    files = sorted(p for p in HERE.iterdir() if p.is_file())
    files += [ROOT / "README.md", ROOT / "AGENTS.md"]
    hashes, checks = {}, []
    for path in files:
        relative = path.relative_to(ROOT)
        dest = snapshot / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        hashes[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()

    def dump(name, value):
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                         allow_nan=False), encoding="utf-8")

    def check(label, passed):
        checks.append({"check": label, "passed": bool(passed)})
        if not passed:
            raise AssertionError(label)

    def read_json(path):
        return json.loads(path.read_text(encoding="utf-8-sig"))

    try:
        d = read_json(HERE / "decision_record.json")
        analysis_path = HERE / d["analysis_summary"]
        verification_path = HERE / d["verification_summary"]
        for label, path in (("analysis", analysis_path), ("verification", verification_path)):
            check(label + "_summary_hash", hashlib.sha256(path.read_bytes()).hexdigest()
                  == d[label + "_summary_sha256"])
        a, v = read_json(analysis_path), read_json(verification_path)
        check("independent_arithmetic_verification", v["status"] == "passed" and v["failed_checks"] == 0)
        check("means", list(d["observed_success_percent"].values())
              == [a["full"][k] for k in ("J8", "J40", "hindsight")])
        check("hindsight_gap", d["hindsight_minus_observed_better_fixed_pp"]
              == a["full"]["hindsight_minus_observed_better_fixed"])
        c = next(row for row in a["contributions"] if row["parent"] == 41015)
        check("parent_concentration", d["parent_41015_contribution_pp"] == c["contribution_vs_stop_pp"]
              and d["parent_41015_fraction"] == c["fraction_of_full_gain"])
        removal = next(row for row in a["leave_one_parent_out"] if row["excluded_parent"] == 41015)
        check("refit_sensitivity", d["excluding_41015_refit_fixed_gap_pp"]
              == removal["hindsight_minus_observed_better_fixed"])
        check("no_new_environment_or_training", all(value == 0 for value in d["actual_new_cost"].values()))
        proposal = d["future_repetition_proposal"]
        check("proposal_only", not proposal["execution_authorized"] and not proposal["scheduled"]
              and not proposal["numeric_progression_gate_frozen"] and proposal["technical_budget"] is None)
        check("proposal_main_budget", proposal["main_environment_cap"]
              == proposal["training_total"] + proposal["evaluation_cap"] == 2320000)
        check("original_gate_and_stages_held", d["research_decisions"]["original_stage1_gate"] == "not_passed_unchanged"
              and d["research_decisions"]["C"] == d["research_decisions"]["original_stages_2_3"] == "held_not_scheduled")
        report = (HERE / "report_ko.md").read_text(encoding="utf-8")
        for value in ("36.450%", "+1.725%p", "+2.375%p", "89.855%", "+0.21875", "98.625"):
            check("reported_value:" + value, value in report)
        for path in files:
            if path.suffix != ".md":
                continue
            contents = path.read_text(encoding="utf-8-sig")
            for match in re.finditer(r"!?\[[^\]]*\]\(([^)\n]+)\)", contents):
                link = match.group(1).strip().strip("<>")
                if re.match(r"^[a-zA-Z]+://", link) or link.startswith("#"):
                    continue
                if path.parent == ROOT and not link.startswith(HERE.name + "/"):
                    continue
                target = unquote(link.split("#", 1)[0])
                check("local_link:" + path.name + ":" + link, (path.parent / target).is_file())
        for relative, expected in hashes.items():
            check("source_unchanged:" + relative,
                  hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected)
        summary = {
            "status": "passed", "checks_passed": len(checks), "failed_checks": 0,
            "scope": "delivery_links_and_agreement_with_verified_arithmetic",
            "new_environment_steps": 0, "new_training_steps": 0, "new_SAC_updates": 0,
            "wall_seconds": time.perf_counter() - start, "python": sys.version,
        }
        dump("summary.json", summary)
        dump("checks.json", checks)
        dump("source_hashes.json", hashes)
        (HERE / "LATEST_DELIVERY_AUDIT.json").write_text(
            json.dumps({"run": str(out), "summary_sha256":
                        hashlib.sha256((out / "summary.json").read_bytes()).hexdigest()}, indent=2),
            encoding="utf-8")
        print(json.dumps({"run": str(out), **summary}, indent=2))
    except BaseException:
        dump("failure.json", {"traceback": traceback.format_exc(), "checks": checks})
        dump("source_hashes.json", hashes)
        raise


if __name__ == "__main__":
    main()
