"""Static evaluation-scope and unchanged-runtime checks; no environment creation."""
import ast
import json
import os
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
os.environ["PRACTICE_SUITE"] = "B"
from practice_allocation.core import ROOT, file_sha256, write_json, source_files, package_versions
from practice_allocation.study_io import source_snapshot


def main():
    out = ROOT/"results"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_static_check_"+uuid.uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    source_snapshot(out)
    checks = []

    def check(name, condition):
        checks.append({"check": name, "passed": bool(condition)})
        if not condition:
            raise AssertionError(name)

    start = time.perf_counter()
    try:
        for p in source_files():
            if p.suffix == ".py":
                ast.parse(p.read_text(encoding="utf-8"))
                check("syntax:"+str(p.relative_to(ROOT)), True)
        for name in ("learning.py", "engine.py", "environment.py", "evaluation.py", "study_io.py", "core.py", "schedules.py"):
            check("unchanged:"+name, file_sha256(ROOT/"practice_allocation"/name) ==
                  file_sha256(ROOT.parent/"44_selection_value_stage1_checkpoint36_v2/practice_allocation"/name))
        p = json.loads((ROOT/"protocol.json").read_text(encoding="utf-8"))
        check("ten_existing_states", len(p["original_seeds"])*len(p["continuations"]) == 10)
        check("two_million_research_upper", 10*4*100*500 == p["budget"]["research_evaluation_steps_upper"])
        check("separate_technical_upper", 1*4*2*500 == p["budget"]["technical_evaluation_steps_upper"])
        check("no_training_budget", p["budget"]["new_training_steps"] == p["budget"]["new_SAC_updates"] == 0)
        worker = ast.parse((ROOT/"worker.py").read_text(encoding="utf-8"))
        calls = {n.func.attr for n in ast.walk(worker) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        check("no_learner_dispatch", not calls.intersection({"train", "learn", "train_steps", "start_branch", "step"}))
        check("all_eight_patterns", set(p["analysis"]["three_timepoint_patterns"]) == {f"{i:03b}" for i in range(8)})
        check("three_time_net_identity", all((b-a)+(c-b) == c-a for a in (0, 1) for b in (0, 1) for c in (0, 1)))
        summary = {"status": "passed", "checks_passed": len(checks), "new_environment_steps": 0,
                   "new_SAC_updates": 0, "packages": package_versions(), "wall_seconds": time.perf_counter()-start}
    except BaseException:
        summary = {"status": "failed", "traceback": traceback.format_exc(), "new_environment_steps": 0, "new_SAC_updates": 0}
    write_json(out/"checks.json", checks)
    write_json(out/"summary.json", summary)
    print(json.dumps({"run": str(out), **summary}, indent=2))
    return int(summary["status"] != "passed")


if __name__ == "__main__":
    raise SystemExit(main())
