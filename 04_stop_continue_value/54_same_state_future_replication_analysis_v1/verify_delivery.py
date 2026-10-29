"""Check delivered links and manually written numerical tables, snapshot docs."""
import hashlib
import json
import re
import shutil
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
analysis = HERE / "results/20261022T021845Z_analysis_98fe07c3"
started = time.perf_counter()
out = HERE / "results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_delivery_" + uuid.uuid4().hex[:8])
out.mkdir(parents=True, exist_ok=False)
(out / "source_snapshot").mkdir()
shutil.copy2(__file__, out / "source_snapshot/verify_delivery.py")
checks, hashes = [], {}


def check(ok, name):
    checks.append({"name":name,"passed":bool(ok)})
    if not ok:
        raise AssertionError(name)


def num(text):
    return float(text.strip().replace("%p", "").replace("%", "").replace("−", "-").replace("**", ""))


try:
    summary = json.loads((analysis / "summary.json").read_text(encoding="utf-8"))
    for path in [*HERE.glob("*.md"), *HERE.glob("*.py"), HERE / "analysis_config.json", HERE.parent / "README.md"]:
        dest = out / "source_snapshot" / ("root_README.md" if path.parent == HERE.parent else path.name)
        if dest.name != "verify_delivery.py":
            shutil.copy2(path,dest)
        hashes[str(path.relative_to(HERE.parent))] = hashlib.sha256(path.read_bytes()).hexdigest()
        if path.suffix == ".md":
            content=path.read_text(encoding="utf-8-sig")
            for target in re.findall(r"\]\(([^)]+)\)",content):
                if "://" in target or target.startswith("#"):
                    continue
                local=target.split("#")[0]
                check((path.parent/local).exists(),f"local_link:{path.name}:{target}")
    report=(HERE/"report_ko.md").read_text(encoding="utf-8")
    count=0
    for line in report.splitlines():
        cells=[s.strip() for s in line.split("|")[1:-1]]
        if not cells:
            continue
        match=re.fullmatch(r"(\d{5}) / (\d{4})",cells[0])
        if match:
            p,r=map(int,match.groups())
            record=next(s for s in summary["state_results"] if s["parent"]==p and s["prefix"]==r)
            expected=[record[k] for k in ["J8_percent","old_J40_percent","new_J40_percent","old_late_pp","new_late_pp"]]
            check(len(cells)==6 and all(abs(num(v)-e)<1e-9 for v,e in zip(cells[1:],expected)),f"state_table:{p}:{r}")
            count+=1
        elif re.fullmatch(r"4101[1-5]",cells[0]) and len(cells)==6:
            record=next(s for s in summary["parent_results"] if s["parent"]==int(cells[0]))
            expected=[record[k] for k in ["stop_percent","continue_percent","selected_percent","G_stop_pp","G_continue_pp"]]
            check(all(abs(num(v)-e)<1e-9 for v,e in zip(cells[1:],expected)),f"parent_table:{cells[0]}")
        elif re.fullmatch(r"4101[1-5]",cells[0]) and len(cells)==3:
            record=next(s for s in summary["leave_one_parent_out"] if s["excluded_parent"]==int(cells[0]))
            check(abs(num(cells[1])-record["G_stop_pp"])<1e-9 and abs(num(cells[2])-record["G_continue_pp"])<1e-9,f"removal_table:{cells[0]}")
        elif cells[0] in ("DO","DC","PU","BP") and len(cells)==5:
            record=next(s for s in summary["task_results"] if s["task"]==cells[0])
            check(all(abs(num(v)-record[k])<1e-9 for v,k in zip(cells[1:],["J0_percent","J8_percent","old_J40_percent","new_J40_percent"])),f"task_table:{cells[0]}")
    check(count==10,"ten_state_rows")
    check(not any(analysis.parent.glob("*/FAILED.json")),"no_failed_analysis_or_verification_runs")
    check("최신 완료 결과는 49·50번" not in (HERE.parent/"README.md").read_text(encoding="utf-8-sig"),"latest_index_updated")
    result={"status":"passed","checks":len(checks),"failed_checks":[],"source_and_document_hashes":hashes,"analysis_summary_sha256":hashlib.sha256((analysis/"summary.json").read_bytes()).hexdigest(),"environment_steps":0,"wall_seconds":time.perf_counter()-started,"figure_visual_review":"PNG inspected; labels, axes, legends and footnotes readable; realized values not presented as expectation estimates"}
    (out/"summary.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"output":str(out),"status":"passed","checks":len(checks)},ensure_ascii=False))
except Exception:
    (out/"FAILED.json").write_text(json.dumps({"traceback":traceback.format_exc(),"environment_steps":0},indent=2),encoding="utf-8")
    raise
finally:
    (out/"checks.json").write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding="utf-8")
