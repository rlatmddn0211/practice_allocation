"""Standalone scientific figure; saved as PNG and SVG with underlying values."""
import os
from pathlib import Path
import numpy as np
from io_utils import read, dump, sha

def run(out,args):
    analysis=Path(args[0]).resolve()
    os.environ["MPLCONFIGDIR"]=str(out/"mplconfig")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    s=read(analysis/"summary.json")
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10,"axes.spines.top":False,"axes.spines.right":False,"svg.fonttype":"none"})
    fig,axes=plt.subplots(2,2,figsize=(13,9.0))
    colors={"gain":"#176B5B","loss":"#A94646"}
    for ax,event,title in [(axes[0,0],"gain","A. Gain: same-state excess exceeds cross-state excess"),(axes[0,1],"loss","B. Loss: no positive same-state advantage")]:
        names=["same_T_all_slots_pp","cross_T_all_slots_pp","D_all_slots_pp"]
        values=np.array([s["overall"][event][key] for key in names])
        ci=np.array([s["uncertainty"][event][key]["case_interval"] for key in names])
        positions=np.arange(3)
        ax.errorbar(positions,values,yerr=np.array([values-ci[:,0],ci[:,1]-values]),fmt="o",color=colors[event],capsize=5,markersize=7,linewidth=1.8)
        for x,y in zip(positions,values): ax.annotate(f"{y:+.3f}",(x,y),xytext=(9,0),textcoords="offset points",va="center",fontsize=10)
        ax.axhline(0,color="0.5",linewidth=.8)
        ax.set_xticks(positions,["Same state","Cross state","D = same - cross"])
        ax.set_xlim(-.4,2.7); ax.set_ylim(-.45,.5)
        ax.set_ylabel("Excess overlap (pp of 2,000 case slots)")
        ax.set_title(title,loc="left",fontsize=11,fontweight="bold",pad=16)
        ax.grid(axis="y",alpha=.15)
    ax=axes[1,0]
    parents=[41011,41012,41013,41014,41015]; y=np.arange(5)
    for offset,event,marker in [(-.13,"gain","o"),(.13,"loss","s")]:
        values=[next(z["D_all_slots_pp"] for z in s["parents"] if z["parent"]==p and z["event"]==event) for p in parents]
        ax.scatter(values,y+offset,color=colors[event],marker=marker,label=event.capitalize(),s=42)
    ax.set_yticks(y,[str(p) for p in parents]); ax.invert_yaxis()
    ax.axvline(0,color="0.5",linewidth=.8); ax.set_xlim(-1.0,.60)
    ax.set_xlabel("Parent-specific D (pp of 400 case slots)")
    ax.set_title("C. Gain D: 3 positive parents, 2 zero",loc="left",fontsize=11,fontweight="bold",pad=16)
    ax.legend(loc="lower left",frameon=False,ncol=2)
    ax.grid(axis="x",alpha=.15)
    ax=axes[1,1]
    tasks=["DO","DC","PU","BP"]
    values=[next(z["D"] for z in s["tasks"] if z["task"]==t and z["event"]=="gain")/20 for t in tasks]
    ax.barh(tasks,values,color=colors["gain"],height=.55)
    for i,v in enumerate(values): ax.text(v+.003,i,f"{v:+.3f}",va="center")
    ax.set_xlim(0,.145); ax.invert_yaxis(); ax.set_xlabel("Contribution to overall gain D (pp)")
    ax.set_title("D. DC and PU contribute 95.9% of gain D",loc="left",fontsize=11,fontweight="bold",pad=16)
    ax.grid(axis="x",alpha=.15)
    fig.suptitle("Common-case comparison of two 8k states: exploratory existing-data analysis",fontsize=15,fontweight="bold",y=.98)
    fig.text(.06,.025,"A/B: pointwise 95% paired case intervals, conditional on fixed trained policies and baseline histories.\n5 parents; 2 states per parent; 2 observed futures per state. Overlap metrics are not performance gains.\nCommon eligible cases: gain 1,247; loss 636. Parent 41013 has no common loss-eligible cases (structural zero in C).",fontsize=9,color=".25",va="bottom")
    fig.subplots_adjust(top=.89,bottom=.17,left=.075,right=.97,wspace=.27,hspace=.43)
    fig.savefig(out/"same_vs_cross_overlap.png",dpi=180)
    fig.savefig(out/"same_vs_cross_overlap.svg")
    plt.close(fig)
    dump(out/"figure_inputs.json",{"analysis":str(analysis),"summary_sha256":sha(analysis/"summary.json"),"matplotlib":matplotlib.__version__,"gain_task_contributions_pp":dict(zip(tasks,values)),"not_performance_gains":True})
    return {"png":"same_vs_cross_overlap.png","svg":"same_vs_cross_overlap.svg","new_environment_steps":0}
