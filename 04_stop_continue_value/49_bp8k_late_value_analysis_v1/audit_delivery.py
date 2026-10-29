"""Check durable report links, evidence scope and source references; no simulation."""
import hashlib
import json
import re
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent


def main():
    start = time.perf_counter()
    out = HERE/"results"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_delivery_"+uuid.uuid4().hex[:8])
    snap = out/"source_snapshot"
    snap.mkdir(parents=True, exist_ok=False)
    for p in list(HERE.glob("*.py"))+list(HERE.glob("*.md"))+[HERE/"decision_record.json", HERE/"analysis_config.json"]:
        shutil.copy2(p, snap/p.name)
    checks, inputs = [], {}

    def check(label, ok):
        checks.append({"check": label, "passed": bool(ok)})
        if not ok:
            raise AssertionError(label)

    def read(p):
        p = Path(p).resolve()
        raw = p.read_bytes()
        inputs[str(p)] = hashlib.sha256(raw).hexdigest()
        return raw

    def js(p):
        return json.loads(read(p).decode("utf-8-sig"))

    try:
        ar, vr = js(HERE/"LATEST_ANALYSIS.json"), js(HERE/"LATEST_VERIFICATION.json")
        analysis, verify = Path(ar["run"]), Path(vr["run"])
        s, v = js(analysis/"summary.json"), js(verify/"summary.json")
        check("analysis_summary_hash", hashlib.sha256(read(analysis/"summary.json")).hexdigest() == ar["summary_sha256"])
        check("verification_summary_hash", hashlib.sha256(read(verify/"summary.json")).hexdigest() == vr["summary_sha256"])
        check("independent_verification", v["status"] == "passed" and v["analysis_summary_sha256"] == ar["summary_sha256"])
        d = js(HERE/"decision_record.json")
        check("completed_scope", d["execution_status"] == "B_completed")
        check("no_future_authorization", d["C"] == d["original_stages_2_3"] == "held_not_scheduled")
        check("no_selector_fit", d["selector_fitted"] is False and d["TD_thresholds_changed"] is False)
        check("scientific_limits_preserved", d["one_realized_future_per_state"] and not d["independent_predictive_validation"])
        check("means_match", d["means"] == s["means"])
        check("costs_match", d["costs"] == s["costs"])
        check("prior_records_linked", all((HERE/p).exists() for p in d["prior_records"]))
        for path in list(HERE.glob("*.md"))+[HERE.parent/"README.md", HERE.parent/"48_bp8k_checkpoint_evaluation_v1/README.md"]:
            body = read(path).decode("utf-8")
            # Markdown links in these documents use local relative paths or standard URLs.
            for match in re.finditer(r"!?\[[^\]\n]*\]\(([^)\n]+)\)", body):
                target = match.group(1).strip().split(" ", 1)[0].strip("<>")
                if "://" in target or target.startswith("#") or target.startswith("mailto:"):
                    continue
                local = unquote(target.split("#", 1)[0])
                if path == HERE.parent/"README.md" and not local.startswith(("48_", "49_")):
                    continue
                check("link:"+str(path)+":"+local, (path.parent/local).exists())
        report = read(HERE/"report_ko.md").decode("utf-8")
        for token in ("ddof=1", "41011", "41015", "4201", "4202", "2,000,000", "36k", "C", "O100"):
            check("report_context:"+token, token in report)
        for fig in ("three_time_success", "late_value_intervals", "early_late_gains_losses", "three_time_patterns"):
            check("figure:"+fig, all((analysis/"figures"/(fig+"."+ext)).exists() for ext in ("png", "svg")))
        summary = dict(status="passed", checks_passed=len(checks), failed_checks=0,
                       new_environment_steps=0, new_SAC_updates=0,
                       scientific_effect_evidence=False, wall_seconds=time.perf_counter()-start)
        (out/"summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        (HERE/"LATEST_DELIVERY.json").write_text(json.dumps({"run": str(out), "summary_sha256":
            hashlib.sha256((out/"summary.json").read_bytes()).hexdigest()}, indent=2), encoding="utf-8")
        print(json.dumps({"run": str(out), **summary}, indent=2))
    except BaseException as e:
        (out/"failure.json").write_text(json.dumps({"error": repr(e), "new_environment_steps": 0,
                                                   "new_SAC_updates": 0}, indent=2), encoding="utf-8")
        raise
    finally:
        (out/"checks.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
        (out/"input_hashes.json").write_text(json.dumps(inputs, indent=2), encoding="utf-8")
        (out/"source_hashes.json").write_text(json.dumps({p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in snap.iterdir()}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
