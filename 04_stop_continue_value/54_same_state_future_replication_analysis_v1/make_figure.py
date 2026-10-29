"""Export a descriptive scientific figure from verified results; zero env steps."""
import hashlib
import json
import os
import shutil
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
started = time.perf_counter()
analysis, verification = (Path(p).resolve() for p in sys.argv[1:3])
out = HERE / "results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_figure_" + uuid.uuid4().hex[:8])
out.mkdir(parents=True, exist_ok=False)
(out / "source_snapshot").mkdir()
shutil.copy2(__file__, out / "source_snapshot/make_figure.py")
os.environ["MPLCONFIGDIR"] = str(out / "mplconfig")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


try:
    data = json.loads((analysis / "summary.json").read_text(encoding="utf-8"))
    verified = json.loads((verification / "summary.json").read_text(encoding="utf-8"))
    assert verified["status"] == "passed"
    assert sha(analysis / "summary.json") == verified["analysis_summary_sha256"]
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, (left, right) = plt.subplots(1, 2, figsize=(13.5, 6.6), gridspec_kw={"width_ratios": [1.4, 1]}, layout="constrained")
    states, parents = data["state_results"], data["parent_results"]
    y = np.arange(len(states))
    old = [s["old_late_pp"] for s in states]
    new = [s["new_late_pp"] for s in states]
    for iy,a,b in zip(y,old,new):
        left.plot([a,b],[iy,iy],color="#c0c7cd",lw=1.5,zorder=1)
    left.scatter(old,y,s=48,marker="s",color="#64748b",label="Original future",zorder=2)
    left.scatter(new,y,s=52,marker="o",color="#147d92",label="New future",zorder=3)
    left.set_yticks(y, [f"{s['parent']} / {s['prefix']}" for s in states])
    left.invert_yaxis()
    left.set_xlim(-16,12)
    left.set_xlabel("Continue40 minus stop8 (percentage points)")
    left.set_ylabel("Parent / 8k prefix seed")
    left.set_title("A. Same 8k state, different realized futures",loc="left",fontweight="bold")
    left.legend(loc="lower left",frameon=False)
    yp = np.arange(5)
    right.barh(yp-.18,[p["G_stop_pp"] for p in parents],height=.32,color="#147d92",label="Choice minus always stop8")
    right.barh(yp+.18,[p["G_continue_pp"] for p in parents],height=.32,color="#c48028",label="Choice minus always continue40")
    right.set_yticks(yp,[str(p["parent"]) for p in parents])
    right.invert_yaxis()
    right.set_xlim(-2,9.5)
    right.set_xlabel("Crossed-half choice gain (percentage points)")
    right.set_title("B. Frozen old-future choices, new-future scores",loc="left",fontweight="bold")
    right.legend(loc="lower right",frameon=False,fontsize=9)
    for ax in (left,right):
        ax.axvline(0,color="#444444",lw=.8)
        ax.grid(axis="x",color="#eeeeee",lw=.7)
        ax.set_axisbelow(True)
    fig.suptitle("Same-state future replication: positive conditional gains, investment gate not passed",fontsize=15,fontweight="bold")
    fig.supxlabel("10 states nested within 5 parents. Panel A: one original and one new future per state; no uncertainty bars.\nPanel B: choices use completed old futures, not information available online at 8k.",fontsize=9)
    for suffix in ("png","svg"):
        fig.savefig(out / f"future_replication.{suffix}",dpi=160)
    plt.close(fig)
    (out / "summary.json").write_text(json.dumps({"status":"completed","analysis_summary_sha256":sha(analysis/"summary.json"),"verification_summary_sha256":sha(verification/"summary.json"),"source_sha256":sha(Path(__file__)),"matplotlib":matplotlib.__version__,"numpy":np.__version__,"figure_hashes":{p.name:sha(p) for p in out.glob("future_replication.*")},"environment_steps":0,"wall_seconds":time.perf_counter()-started},indent=2)+"\n",encoding="utf-8")
    print(str(out))
except Exception:
    import traceback
    (out/"FAILED.json").write_text(json.dumps({"traceback":traceback.format_exc(),"environment_steps":0,"source_sha256":sha(Path(__file__))},indent=2),encoding="utf-8")
    raise
