"""Check newly authored reports against completed A outputs; preserve a delivery snapshot."""
import csv
import hashlib
import io
import json
import re
import shutil
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    start = time.perf_counter()
    out = HERE/"results"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_delivery_"+uuid.uuid4().hex[:8])
    (out/"source_snapshot").mkdir(parents=True, exist_ok=False)
    for p in HERE.iterdir():
        if p.is_file() and p.suffix in (".py", ".json", ".md"):
            shutil.copy2(p, out/"source_snapshot"/p.name)
    (out/"repository_index_snapshot").mkdir()
    for name in ("README.md", "AGENTS.md"):
        shutil.copy2(HERE.parent/name, out/"repository_index_snapshot"/name)
    checks, inputs = [], {}

    def read(p):
        p = Path(p).resolve()
        b = p.read_bytes()
        inputs[str(p)] = hashlib.sha256(b).hexdigest()
        return b.decode("utf-8-sig")

    def js(p):
        return json.loads(read(p))

    def rows(p):
        return list(csv.DictReader(io.StringIO(read(p))))

    def check(label, ok):
        checks.append({"check": label, "passed": bool(ok)})
        if not ok:
            raise AssertionError(label)

    def save(name, obj):
        with (out/name).open("x", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False, allow_nan=False)

    try:
        ref = js(HERE/"LATEST_ANALYSIS.json")
        analysis = Path(ref["run"])
        s = js(analysis/"summary.json")
        vref = js(HERE/"LATEST_VERIFICATION.json")
        verification = Path(vref["run"])
        v = js(verification/"summary.json")
        check("verified_current_analysis", v["status"] == "verified" and v["analysis_run"] == str(analysis)
              and v["analysis_summary_sha256"] == ref["summary_sha256"])
        for n in ("analyze.py", "analysis_config.json"):
            check("analyzed_source_unchanged:"+n, read(HERE/n) == read(analysis/"source_snapshot"/n))
        check("verification_source_unchanged", read(HERE/"verify.py") == read(verification/"source_snapshot/verify.py"))
        report = read(HERE/"report_ko.md")
        for path in (HERE/"README.md", HERE/"report_ko.md", HERE/"evidence_record_ko.md", HERE.parent/"README.md"):
            txt = read(path)
            check("clean_unicode:"+path.name, "\ufffd" not in txt and not re.search(r"[\u3040-\u30ff]", txt))
            for target in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", txt):
                if target.startswith(("http:", "https:", "#", "mailto:")):
                    continue
                check("link:"+str(path.name)+":"+target, (path.parent/target.split("#", 1)[0]).exists())
        d = js(HERE/"decision_record.json")
        w, a = s["A1"]["primary"]
        for key, expected in (
                ("within_minus_BP_pp", w["vs_BP_pp"]),
                ("within_minus_parent_excluded_fixed_pp", w["vs_fixed_pp"]),
                ("across_minus_BP_pp", a["vs_BP_pp"]),
                ("across_minus_parent_excluded_fixed_pp", a["vs_fixed_pp"]),
                ("within_minus_across_pp", w["selected_pp"]-a["selected_pp"])):
            check("decision_A1:"+key, abs(d["A1"][key]-expected) < 1e-10)
        for key in ("z_min", "z_max", "minimum_numeric_threshold"):
            check("decision_prefix:"+key, abs(d["prefix_input_audit"][key]-v["prefix_action_audit"][key]) < 1e-10)
        check("decision_reversal", s["A2"]["strong_reversal_count"] == len(d["A2"]["strong_reversals"]) == 2
              and s["A2"]["strong_reversal_parents"] == [41014])
        bp = next(x for x in s["A3"]["methods"] if x["condition"] == "dose625")
        check("decision_BP_decomposition", d["A3_BP_macro_pp"] == {
            "gains": bp["gain_pp"], "losses": bp["loss_pp"], "net": bp["net_pp"]})
        for value in ("+2.775", "+4.125", "−2.850", "−1.500", "+5.625", "+0.375",
                      "5.750", "5.375", "0.4055", "0.1128", "20,000", "18,091", "6,163"):
            check("report_key_value:"+value, value in report)
        transitions = rows(analysis/"a3_case_transitions.csv")
        for p, gains, losses in ((41014, [15, 14], [20, 63]), (41015, [4, 4], [20, 6])):
            rr = [x for x in transitions if x["original_seed"] == str(p) and x["condition"] == "dose625" and x["task"] == "BP"]
            check("reported_BP_acquisition_loss:"+str(p), [int(x["gain"]) for x in rr] == gains
                  and [int(x["loss"]) for x in rr] == losses)
        check("zero_new_experiment", s["costs"]["new_environment_steps"] == s["costs"]["new_SAC_updates"]
              == v["new_environment_steps"] == v["new_SAC_updates"] == d["new_environment_steps"] == 0)
        check("holds_recorded", all(d[k] == "not_executed_not_scheduled" for k in ("B", "C"))
              and d["original_stage2"] == d["original_stage3"] == "on_hold")
        check("six_scientific_figures", len(list((analysis/"figures").glob("*.png"))) == 6
              and len(list((analysis/"figures").glob("*.svg"))) == 6)
        check("failed_run_retained", (HERE/"results/20261020T033940Z_syntax_failure_68e9d998/failure.json").exists())
        summary = dict(status="delivery_checked", analysis_run=str(analysis), verification_run=str(verification),
                       checks_passed=len(checks), failed_checks=0, new_environment_steps=0, new_SAC_updates=0,
                       wall_seconds=time.perf_counter()-start)
        save("summary.json", summary)
        save("checks.json", checks)
        save("input_hashes.json", inputs)
        save("snapshot_hashes.json", {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in out.rglob("*") if p.is_file() and p.name != "snapshot_hashes.json"})
        (HERE/"LATEST_DELIVERY.json").write_text(json.dumps(
            {"run": str(out), "summary_sha256": hashlib.sha256((out/"summary.json").read_bytes()).hexdigest()}, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
    except BaseException:
        save("failure.json", {"traceback": traceback.format_exc(), "checks": checks, "input_hashes": inputs,
                             "new_environment_steps": 0, "new_SAC_updates": 0})
        raise


if __name__ == "__main__":
    main()
