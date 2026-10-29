"""Check reported numerical claims, links, figure data, and source integrity."""
import itertools
import re
import shutil
import xml.etree.ElementTree as ET
from fractions import Fraction as F
from pathlib import Path
import numpy as np
from io_utils import HERE, ROOT, read, rows, sha, dump

def run(out,args):
    analysis=HERE/"results/20261022T035037Z_analyze_9e4e0e84"
    verification=HERE/"results/20261022T035234Z_verify_fdfb3853"
    figure=HERE/"results/20261022T035334Z_make_figure_e15b9cd8"
    summary=read(analysis/"summary.json"); scope=read(verification/"scope_summary.json")
    checks=[]
    def check(ok,name):
        checks.append({"name":name,"passed":bool(ok)})
        if not ok:
            dump(out/"checks.json",checks)
            raise AssertionError(name)
    report=(HERE/"report_ko.md").read_text(encoding="utf-8")
    # Whole reported rows, not isolated numeral searches.
    for event,label in [("gain","획득"),("loss","상실")]:
        z=summary["overall"][event]; u=summary["uncertainty"][event]["D_all_slots_pp"]
        def sign(x): return f"{x:+.3f}".replace("-","−")
        row=f"| {label} | {sign(z['same_T_all_slots_pp'])}%p | {sign(z['cross_T_all_slots_pp'])}%p | **{sign(z['D_all_slots_pp'])}%p** | "
        check(row in report,"report_primary_row:"+event)
        for field in ["case_interval","parent_descriptive_interval"]:
            interval="["+", ".join(sign(v) for v in u[field])+"]"
            check(interval in report,"report_interval:"+event+"/"+field)
        for kind,kor in [("same","동일 상태"),("cross","교차 상태")]:
            row=f"| {label} | {kor} | {z[kind+'_m']:.3f} | {z[kind+'_expected']:.3f} | {sign(z[kind+'_T'])} |"
            check(row in report,"report_average_counts:"+event+"/"+kind)
    for p in [41011,41012,41013,41014,41015]:
        gain=next(z for z in summary["parents"] if z["parent"]==p and z["event"]=="gain")
        loss=next(z for z in summary["parents"] if z["parent"]==p and z["event"]=="loss")
        gaintext="0.000" if gain["D_all_slots_pp"]==0 else sign(gain["D_all_slots_pp"])
        start=f"| {p} | {gain['N']} | {gaintext}%p | {loss['N']} |"
        check(start in report,"parent_table:"+str(p))
    check(f"**{scope['gain_DC_PU_share_percent']:.3f}%**" in report,"task_concentration_95_938")
    check(f"**{scope['max_gain_parent_share_percent']:.1f}%**" in report,"parent_concentration_47_1")
    for event in ("gain","loss"):
        z=summary["coverage"][event]
        check(f"{z['retained_percent']:.3f}%" in report,"coverage_percent:"+event)
    check(read(verification/"COMPLETE.json")["result"]["checks_passed"]==3103,"independent_verification_count")
    check(read(analysis/"COMPLETE.json")["result"]["checks_passed"]==106,"analysis_check_count")
    # Current source definitions remain byte-identical to their pre-execution snapshot.
    for name in ["analysis_config.json","methods_addendum_ko.md","analyze.py","io_utils.py","run.py"]:
        check(sha(HERE/name)==read(analysis/"source_hashes.json")[name],"frozen_calculation_definition:"+name)
    check(sha(HERE/"verify.py")==read(verification/"source_hashes.json")["verify.py"],"frozen_independent_verifier")
    check(read(verification/"verified_inputs.json")["summary_sha256"]==sha(analysis/"summary.json"),"verification_binds_delivered_summary")
    check(read(figure/"figure_inputs.json")["summary_sha256"]==sha(analysis/"summary.json"),"figure_binds_delivered_summary")
    for task,value in read(figure/"figure_inputs.json")["gain_task_contributions_pp"].items():
        expected=next(z["D"] for z in summary["tasks"] if z["task"]==task and z["event"]=="gain")/20
        check(abs(value-expected)<1e-12,"figure_task_value:"+task)
    ET.parse(figure/"same_vs_cross_overlap.svg")
    check((figure/"same_vs_cross_overlap.png").read_bytes()[:8]==b"\x89PNG\r\n\x1a\n","PNG_header")
    # Inspect local Markdown targets; preserve exact final documents in this run.
    for path in sorted(HERE.glob("*.md")):
        text=path.read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)]+)\)",text):
            if target.startswith(("https:","http:","#")): continue
            target=target.split("#")[0]
            check((path.parent/target).exists(),"local_link:"+path.name+":"+target)
    for name in ["README.md","AGENTS.md"]:
        shutil.copy2(ROOT/name,out/"source_snapshot"/("root_"+name))
    check("56_same_vs_cross_state_overlap_v1/report_ko.md" in (ROOT/"README.md").read_text(encoding="utf-8"),"root_latest_index")
    # Enumerate a small independent-Bernoulli model to check mathematical claims.
    # Shared difficulty ranking p1[0]>p1[1], p2[0]>p2[1], yet E[D] can be positive.
    probabilities=[F(4,5),F(1,5),F(3,5),F(2,5)]*2
    ET1=F(0); ED=F(0); mass=F(0)
    for bits in itertools.product((0,1),repeat=8):
        probability=F(1)
        for bit,p in zip(bits,probabilities): probability*=p if bit else 1-p
        a1,a2,b1,b2=[bits[k:k+2] for k in range(0,8,2)]
        def exact_t(a,b): return F(sum(x*y for x,y in zip(a,b)))-F(sum(a)*sum(b),2)
        t11=exact_t(a1,b1); t22=exact_t(a2,b2); t12=exact_t(a1,b2); t21=exact_t(a2,b1)
        ET1+=probability*t11; ED+=probability*(t11+t22-t12-t21)/2; mass+=probability
    check(mass==1 and ET1==F(9,50),"finite_example_E_T_equals_N_Var")
    check(ED==F(1,25),"finite_example_positive_D_without_rank_change")
    # This check has zero training/evaluation cost; guard against accidental new queues.
    completed=list((HERE/"results").glob("*/COMPLETE.json"))
    failures=list((HERE/"results").glob("*/FAILED.json"))
    check(not failures,"no_failed_runs_before_delivery")
    runtimes=[]
    for path in (HERE/"results").glob("*/runtime.json"):
        rt=read(path); check(rt["training_steps"]==0 and rt["evaluation_steps"]==0 and not rt["gpu_used"],"file_only_cost:"+path.parent.name)
        runtimes.append({"run":path.parent.name,"wall_seconds":rt["wall_seconds"],"cpu_seconds":rt["cpu_seconds"]})
    dump(out/"checks.json",checks)
    dump(out/"delivery_receipt.json",{"summary_sha256":sha(analysis/"summary.json"),"report_sha256":sha(HERE/"report_ko.md"),"evidence_sha256":sha(HERE/"evidence_record_ko.md"),"PNG_sha256":sha(figure/"same_vs_cross_overlap.png"),"SVG_sha256":sha(figure/"same_vs_cross_overlap.svg"),"PNG_visual_review":"inspected in tool output: labels, zero lines, values, scales and caveats visible","SVG_validation":"XML structure and shared figure generation; PNG was visually inspected","previous_runs":runtimes,"failure_count_before_delivery":len(failures),"mathematical_example":{"E_T":str(ET1),"E_D":str(ED),"same_case_ranking_in_both_states":True},"new_environment_steps":0})
    return {"checks_passed":len(checks),"report_links_and_claims_checked":True,"source_definitions_unchanged":True,"new_environment_steps":0}
