"""Scientific export of verified case-overlap and observational history contrasts."""
import hashlib
import json
import os
import shutil
import sys
import time
import traceback
import uuid
from datetime import datetime,timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent
start=time.perf_counter(); analysis,verification=(Path(x).resolve() for x in sys.argv[1:3])
out=HERE/"results"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_figure_"+uuid.uuid4().hex[:8])
out.mkdir(parents=True,exist_ok=False); (out/"source_snapshot").mkdir(); shutil.copy2(__file__,out/"source_snapshot/make_figure.py")
os.environ["MPLCONFIGDIR"]=str(out/"mplconfig")


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    data=json.loads((analysis/"summary.json").read_text(encoding="utf-8")); v=json.loads((verification/"summary.json").read_text(encoding="utf-8"))
    assert v["status"]=="passed" and v["analysis_summary_sha256"]==sha(analysis/"summary.json")
    plt.rcParams.update({"font.size":10,"font.family":"DejaVu Sans","axes.spines.top":False,"axes.spines.right":False})
    fig,(ax,bx)=plt.subplots(1,2,figsize=(13,6.2),layout="constrained",gridspec_kw={"width_ratios":[1,1.25]})
    x=np.arange(2); events=[data["event_overlap"][e] for e in ["loss","gain"]]
    a=ax.bar(x-.18,[e["both"] for e in events],width=.34,color="#167f90",label="Observed shared events")
    b=ax.bar(x+.18,[e["expected_overlap"] for e in events],width=.34,color="#a3acb8",label="Expected after stratification")
    ax.bar_label(a,labels=[str(e["both"]) for e in events],padding=4)
    ax.bar_label(b,labels=[f"{e['expected_overlap']:.2f}" for e in events],padding=4)
    ax.set_xticks(x,["Loss\n(8k success)","Gain\n(8k failure)"]); ax.set_ylim(0,185)
    ax.set_ylabel("Shared state-case event observations")
    ax.set_title("A. Overlap relative to event-count expectations",loc="left",fontweight="bold")
    ax.legend(frameon=False,loc="upper right",fontsize=9)
    ax.grid(axis="y",color="#eeeeee"); ax.set_axisbelow(True)
    h=data["history_matched"]["parents"]; y=np.arange(len(h))
    for i,z in enumerate(h): bx.plot([z["old_rd_pp"],z["new_rd_pp"]],[i,i],color="#c6ccd3",lw=1.3,zorder=1)
    bx.scatter([z["old_rd_pp"] for z in h],y,color="#6b7280",marker="s",s=50,label="Original future",zorder=2)
    bx.scatter([z["new_rd_pp"] for z in h],y,color="#167f90",s=54,label="New future",zorder=3)
    bx.set_yticks(y,[str(z["parent"]) for z in h]); bx.invert_yaxis(); bx.set_xlim(-40,50)
    bx.axvline(0,color="#333333",lw=.8); bx.grid(axis="x",color="#eeeeee"); bx.set_axisbelow(True)
    bx.set_xlabel("Loss risk: newly observed minus persistent observed success (pp)")
    bx.set_ylabel("Parent"); bx.set_title("B. History association differs across parents",loc="left",fontweight="bold")
    bx.legend(frameon=False,loc="lower left",fontsize=9)
    fig.suptitle("Case-level repeatability: excess shared gains, little aggregate excess shared loss",fontsize=14,fontweight="bold")
    fig.supxlabel("5 parents; 10 fixed 8k states; 2 futures per state. A: expected = sum(n_old*n_new/N) within parent, prefix, task and 8k status.\nB: common support in 8 of 40 state-task cells; overlap weights within each parent. Observational contrasts, not causal effects.",fontsize=9)
    for ext in ["png","svg"]: fig.savefig(out/f"casewise_repeatability.{ext}",dpi=160)
    plt.close(fig)
    (out/"summary.json").write_text(json.dumps({"status":"completed","analysis_summary_sha256":sha(analysis/"summary.json"),"verification_summary_sha256":sha(verification/"summary.json"),"source_sha256":sha(Path(__file__)),"matplotlib":matplotlib.__version__,"numpy":np.__version__,"environment_steps":0,"wall_seconds":time.perf_counter()-start,"files":{p.name:sha(p) for p in out.glob("casewise_repeatability.*")}},indent=2)+"\n",encoding="utf-8")
    print(str(out))
except Exception:
    (out/"FAILED.json").write_text(json.dumps({"traceback":traceback.format_exc(),"source_sha256":sha(Path(__file__)),"environment_steps":0},indent=2),encoding="utf-8")
    raise
