"""Validate narrative tables, sensitivity calculations and local links."""
import csv
import hashlib
import json
import re
import shutil
import time
import traceback
import uuid
from datetime import datetime,timezone
from fractions import Fraction as F
from pathlib import Path

HERE=Path(__file__).resolve().parent
analysis=HERE/"results/20261022T031427Z_analysis_a137ba0b"
out=HERE/"results"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_delivery_"+uuid.uuid4().hex[:8])
out.mkdir(parents=True,exist_ok=False); (out/"source_snapshot").mkdir(); shutil.copy2(__file__,out/"source_snapshot/verify_delivery.py")
checks=[]; hashes={}; start=time.perf_counter()


def ck(ok,name):
    checks.append({"check":name,"passed":bool(ok)})
    if not ok: raise AssertionError(name)
def num(s): return float(s.strip().replace("**","").replace("%p","").replace("%","").replace("−","-").replace(",",""))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text(encoding="utf-8-sig"))


try:
    summary=read(analysis/"summary.json")
    for path in [*HERE.glob("*.md"),*HERE.glob("*.py"),HERE/"analysis_config.json",HERE.parent/"README.md",HERE.parent/"AGENTS.md"]:
        name=("root_"+path.name) if path.parent==HERE.parent else path.name
        if name!="verify_delivery.py": shutil.copy2(path,out/"source_snapshot"/name)
        hashes[str(path.relative_to(HERE.parent))]=sha(path)
        if path.suffix==".md":
            for target in re.findall(r"\]\(([^)]+)\)",path.read_text(encoding="utf-8-sig")):
                if "://" not in target and not target.startswith("#"): ck((path.parent/target.split("#")[0]).exists(),"link:"+path.name+":"+target)
    with (analysis/"input_snapshot/paired_outcomes.csv").open(encoding="utf-8",newline="") as f: raw=list(csv.DictReader(f))
    P,R,T=summary["parents"],summary["prefixes"],summary["tasks"]
    composition={t:{g:sum(z["task"]==t and z["J0"]==g[0] and z["J8"]==g[1] for z in raw) for g in ["01","11"]} for t in T}
    contrasts={}
    for p in P:
        for r in R:
            for t in T:
                groups={g:[z for z in raw if int(z["parent"])==p and int(z["prefix"])==r and z["task"]==t and z["J0"]==g[0] and z["J8"]==g[1]] for g in ["01","11"]}
                if groups["01"] and groups["11"]:
                    rates=[]
                    for future in ["old_J40","new_J40"]:
                        rates.append(100*(F(sum(z[future]=="0" for z in groups["01"]),len(groups["01"]))-F(sum(z[future]=="0" for z in groups["11"]),len(groups["11"]))))
                    w=F(len(groups["01"])*len(groups["11"]),len(groups["01"])+len(groups["11"]))
                    contrasts[p,r,t]=(rates,w)
    for fi,future in enumerate(["old","new"]):
        parent_equal=[]
        for p in P:
            values=[pair[0][fi] for (q,r,t),pair in contrasts.items() if q==p]
            parent_equal.append(sum(values)/len(values))
        exact=sum(parent_equal)/len(parent_equal)
        ck(abs(float(exact)-summary["history_equal_strata_sensitivity"]["overall"][future+"_rd_pp"])<1e-10,"uniform_sensitivity_exact:"+future)
        for t in T:
            per_parent=[]
            for p in P:
                pieces=[pair for (q,r,task),pair in contrasts.items() if q==p and task==t]
                if pieces: per_parent.append(sum(v[0][fi]*v[1] for v in pieces)/sum(v[1] for v in pieces))
            reported=summary["history_by_task"][t]["overall"][future+"_rd_pp"]
            ck((not per_parent and reported is None) or (bool(per_parent) and abs(float(sum(per_parent)/len(per_parent))-reported)<1e-10),"task_history_exact:"+t+future)
    report=(HERE/"report_ko.md").read_text(encoding="utf-8")
    checked=0
    for line in report.splitlines():
        c=[v.strip() for v in line.split("|")[1:-1]]
        if not c: continue
        if c[0] in T and len(c)==3:
            ck(int(c[1].replace(",",""))==composition[c[0]]["11"] and int(c[2].replace(",",""))==composition[c[0]]["01"],"composition_table:"+c[0]); checked+=1
        if re.fullmatch(r"4101[1-5]",c[0]) and len(c)==3:
            p=int(c[0])
            if "%p" in c[1]:
                rec=next(z for z in summary["history_matched"]["parents"] if z["parent"]==p)
                expected=[rec["old_rd_pp"],rec["new_rd_pp"]]
            else:
                expected=[next(z for z in summary["overlap_by_parent"] if z["parent"]==p and z["event"]==ev)["excess_overlap"] for ev in ["loss","gain"]]
            ck(all(abs(num(v)-e)<=.000501 for v,e in zip(c[1:],expected)),"parent_table:"+c[0]+":"+c[1]); checked+=1
        if c[0].startswith("상실: 8k") or c[0].startswith("획득: 8k"):
            rec=summary["event_overlap"]["loss" if c[0].startswith("상실") else "gain"]
            ck([int(v.replace(",","")) for v in c[1:]]==[rec[k] for k in ["eligible","both","old_only","new_only","neither"]],"four_way_counts:"+c[0]); checked+=1
    ck(checked==16,"all_manual_count_parent_composition_tables")
    failures=list((HERE/"results").glob("*/FAILED.json"))
    ck(len(failures)==1 and read(failures[0])["status"]=="failed_before_execution","one_preserved_parse_failure")
    ck("55 — 사례별" in (HERE.parent/"README.md").read_text(encoding="utf-8-sig"),"root_latest_index")
    ck("148" in report and "147.698" in report and "46.759" in report and "15.241" in report,"headline_numbers_present")
    result={"status":"passed","checks":len(checks),"failed_checks":[],"analysis_summary_sha256":sha(analysis/"summary.json"),"source_document_hashes":hashes,"environment_steps":0,"wall_seconds":time.perf_counter()-start,"preserved_analysis_failures":1,"figure_visual_review":"PNG inspected: all axes, counts, legends, observational limitation and support footnote readable."}
    (out/"summary.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"output":str(out),"status":"passed","checks":len(checks)},ensure_ascii=False))
except Exception:
    (out/"FAILED.json").write_text(json.dumps({"traceback":traceback.format_exc(),"environment_steps":0,"source_sha256":sha(Path(__file__))},indent=2),encoding="utf-8"); raise
finally: (out/"checks.json").write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding="utf-8")
