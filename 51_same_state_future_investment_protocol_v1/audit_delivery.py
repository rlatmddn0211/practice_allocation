"""Read-only checks of proposal contents; save a new immutable audit directory."""
import csv
import hashlib
import json
import re
import shutil
import sys
import time
import traceback
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def main():
    start = time.perf_counter()
    out = HERE / "results" / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "_delivery_audit_" + uuid.uuid4().hex[:8])
    snapshot = out / "source_snapshot"
    snapshot.mkdir(parents=True, exist_ok=False)
    files = sorted(p for p in HERE.iterdir() if p.is_file()) + [ROOT / "README.md", ROOT / "AGENTS.md"]
    hashes, checks = {}, []
    for p in files:
        rel = p.relative_to(ROOT)
        dest = snapshot / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dest)
        hashes[str(rel)] = hashlib.sha256(p.read_bytes()).hexdigest()

    def js(p):
        return json.loads(Path(p).read_text(encoding="utf-8-sig"))

    def check(name, passed):
        checks.append(dict(check=name, passed=bool(passed)))
        if not passed:
            raise AssertionError(name)

    def dump(name, obj):
        (out / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        ref, cfg = js(HERE / "PREPARED_CHOICES.json"), js(HERE / "protocol.json")
        run = Path(ref["run"])
        for key, path in (
            ("summary_sha256", run / "summary.json"),
            ("choices_sha256", run / "fixed_choices.csv"),
            ("state_manifest_sha256", run / "state_manifest.json"),
            ("protocol_sha256", HERE / "protocol.json"),
        ):
            check("frozen:" + key, hashlib.sha256(path.read_bytes()).hexdigest() == ref[key])
        for path, sha in js(run / "input_hashes.json").items():
            check("input_unchanged:" + path, hashlib.sha256(Path(path).read_bytes()).hexdigest() == sha)
        for name, sha in js(run / "output_hashes.json").items():
            check("output_unchanged:" + name, hashlib.sha256((run / name).read_bytes()).hexdigest() == sha)
        with (run / "fixed_choices.csv").open(encoding="utf-8", newline="") as f:
            choices = list(csv.DictReader(f))
        check("30_fixed_choices", len(choices) == 30)
        counts = Counter(r["fixed_action"] for r in choices if r["selection_cases"] == "O100")
        check("full_5_each", counts == {"stop": 5, "continue": 5})
        counts = Counter(r["fixed_action"] for r in choices if r["selection_cases"] != "O100")
        check("primary_counts", counts == {"stop": 11, "continue": 9})
        check("primary_disjoint_halves", all(
            r["selection_cases"] != r["scoring_cases"] for r in choices if r["selection_cases"] != "O100"))
        check("fixed_zero_threshold", all(
            r["fixed_action"] == ("continue" if float(r["old_late_pp"]) > 0 else "stop") for r in choices))
        check("not_launched", not cfg["execution_authorized"] and not cfg["scheduled"])
        check("no_actual_steps", all(x == 0 for x in cfg["actual_preparation_cost"].values()))
        check("proposed_gate_only", cfg["proposed_investment_gate"]["status"].endswith("not_user_approved"))
        budget = cfg["budget_proposal"]
        check("explicit_technical_addition", budget["main_environment_cap"] == 2320000
              and budget["technical_environment_cap"] == 10000
              and budget["including_technical_cap"] == 2330000)
        check("no_retry_reserve", budget["automatic_retry_reserve"] == 0)
        for p in files:
            if p.suffix != ".md":
                continue
            for match in re.finditer(r"!?\[[^\]]*\]\(([^)\n]+)\)", p.read_text(encoding="utf-8-sig")):
                target = match.group(1)
                if re.match(r"^[a-zA-Z]+://", target) or target.startswith("#"):
                    continue
                if p.parent == ROOT and not target.startswith(HERE.name + "/"):
                    continue
                check("link:" + p.name + ":" + target, (p.parent / target.split("#")[0]).is_file())
        for rel, sha in hashes.items():
            check("snapshot_current:" + rel, hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == sha)
        summary = dict(status="passed", checks_passed=len(checks), failed_checks=0,
                       new_environment_steps=0, new_training_steps=0, new_SAC_updates=0,
                       validates_execution_implementation=False, wall_seconds=time.perf_counter() - start,
                       python=sys.version)
        dump("summary.json", summary)
        dump("checks.json", checks)
        dump("source_hashes.json", hashes)
        (HERE / "LATEST_DELIVERY_AUDIT.json").write_text(json.dumps(dict(
            run=str(out), summary_sha256=hashlib.sha256((out / "summary.json").read_bytes()).hexdigest()),
            indent=2), encoding="utf-8")
        print(json.dumps(dict(run=str(out), **summary), indent=2))
    except BaseException:
        dump("failure.json", dict(traceback=traceback.format_exc(), checks=checks))
        dump("source_hashes.json", hashes)
        raise


if __name__ == "__main__":
    main()
