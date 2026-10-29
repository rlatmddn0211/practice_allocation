"""Independent sets/Fraction calculation and frequency-weight bootstrap audit."""
import csv
import hashlib
import itertools
import json
import platform
import shutil
import sys
import time
import traceback
import uuid
from datetime import datetime,timezone
from fractions import Fraction as F
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent


def read(p): return json.loads(p.read_text(encoding="utf-8-sig"))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def csvrows(p):
    with p.open(encoding="utf-8-sig",newline="") as f: return list(csv.DictReader(f))
def save(p,obj): p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


def main():
    start,cpu=time.perf_counter(),time.process_time(); analysis=Path(sys.argv[1]).resolve()
    out=HERE/"results"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_verification_"+uuid.uuid4().hex[:8])
    out.mkdir(parents=True,exist_ok=False); (out/"source_snapshot").mkdir(); shutil.copy2(__file__,out/"source_snapshot/verify.py")
    checks=[]
    def ck(ok,name):
        checks.append({"name":name,"passed":bool(ok)})
        if not ok: raise AssertionError(name)
    def close(a,b,name): ck(abs(float(a)-float(b))<1e-9,name)
    try:
        config=read(HERE/"analysis_config.json"); summary=read(analysis/"summary.json")
        inp=analysis/"input_snapshot/paired_outcomes.csv"; ck(sha(inp)==config["input_sha256"],"paired_source_sha")
        for name,digest in read(analysis/"source_hashes.json").items(): ck(sha(analysis/"source_snapshot"/name)==digest,"source_snapshot:"+name)
        P,R,T=config["parents"],config["prefixes"],config["tasks"]
        raw={(int(z["parent"]),int(z["prefix"]),z["task"],int(z["case"])):tuple(int(z[k]) for k in ["J0","J8","old_J40","new_J40"]) for z in csvrows(inp)}
        cells={}; hist={}; expected_tables=csvrows(analysis/"overlap_by_state_task.csv")
        for p,r,t in itertools.product(P,R,T):
            group={i:raw[p,r,t,i] for i in range(100)}
            h01={i for i,z in group.items() if z[0:2]==(0,1)}; h11={i for i,z in group.items() if z[0:2]==(1,1)}
            hist[p,r,t]={"01":h01,"11":h11}
            for ev in ["loss","gain"]:
                target=0 if ev=="loss" else 1
                eligible={i for i,z in group.items() if z[1]==1-target}
                a={i for i in eligible if group[i][2]==target}; b={i for i in eligible if group[i][3]==target}
                expected=F(len(a)*len(b),len(eligible)) if eligible else F(0)
                refined=F(0)
                for history in [0,1]:
                    subset={i for i in eligible if group[i][0]==history}
                    if subset: refined+=F(len(a&subset)*len(b&subset),len(subset))
                cells[p,r,t,ev]={"eligible":eligible,"old":a,"new":b,"both":a&b,"expected":expected,"excess":F(len(a&b))-expected,"refined_excess":F(len(a&b))-refined}
                z=next(z for z in expected_tables if (int(z["parent"]),int(z["prefix"]),z["task"],z["event"])==(p,r,t,ev))
                for field,value in [("eligible",len(eligible)),("old_events",len(a)),("new_events",len(b)),("both",len(a&b)),("old_only",len(a-b)),("new_only",len(b-a)),("neither",len(eligible-(a|b))),("expected_overlap",expected),("excess_overlap",F(len(a&b))-expected),("excess_given_J0",F(len(a&b))-refined)]: close(value,z[field],f"cell:{p}:{r}:{t}:{ev}:{field}")
        exact=[]; weights={}
        for p in P:
            row=[]
            for ev in ["loss","gain"]: row.append(sum(cells[p,r,t,ev]["excess"] for r,t in itertools.product(R,T))/8)
            for r,t in itertools.product(R,T):
                a,b=hist[p,r,t]["01"],hist[p,r,t]["11"]
                weights[p,r,t]=F(len(a)*len(b),len(a)+len(b)) if a and b else F(0)
            W=sum(weights[p,r,t] for r,t in itertools.product(R,T))
            ck(W>0,f"parent_history_support:{p}")
            for col in [2,3]:
                total=F(0)
                for r,t in itertools.product(R,T):
                    if weights[p,r,t]:
                        aa,bb=hist[p,r,t]["01"],hist[p,r,t]["11"]
                        risk_a=F(sum(raw[p,r,t,i][col]==0 for i in aa),len(aa))
                        risk_b=F(sum(raw[p,r,t,i][col]==0 for i in bb),len(bb))
                        total+=weights[p,r,t]*(risk_a-risk_b)*100
                row.append(total/W)
            for ev in ["loss","gain"]: row.append(sum(cells[p,r,t,ev]["refined_excess"] for r,t in itertools.product(R,T))/8)
            exact.append(row)
        names=list(summary["uncertainty"])
        for j,name in enumerate(names): close(sum(row[j] for row in exact)/5,summary["uncertainty"][name]["estimate"],"primary_exact:"+name)
        # Check the user's pooled calculation independently and the support counts.
        for g in ["01","11"]:
            N=sum(len(z[g]) for z in hist.values()); z=summary["history_pooled"][g]
            ck(N==z["N"],"history_N:"+g)
            for f,col in [("old",2),("new",3)]:
                n=sum(sum(raw[p,r,t,i][col]==0 for i in hist[p,r,t][g]) for p,r,t in itertools.product(P,R,T))
                ck(n==z[f+"_loss"],"history_loss:"+g+f); close(F(100*n,N),z[f+"_risk_percent"],"history_risk:"+g+f)
        npz=np.load(analysis/"bootstrap_draws.npz"); ix_all=npz["case_indices"]; B=config["uncertainty"]["case_replicates"]
        rng=np.random.default_rng(config["uncertainty"]["case_seed"])
        bootstrap=np.zeros((B,5,6)); history_num=np.zeros((B,5,2)); ws=np.zeros(5)
        for pi,p in enumerate(P):
            for ti,t in enumerate(T):
                codes=np.array([4*raw[p,R[0],t,i][0]+2*raw[p,R[0],t,i][1]+raw[p,R[1],t,i][1] for i in range(100)])
                ix=ix_all[pi,ti].astype(np.int64)
                for code in range(8):
                    ids=np.flatnonzero(codes==code)
                    if len(ids): ck(np.array_equal(ix[:,ids],ids[rng.integers(0,len(ids),size=(B,len(ids)))]),f"seeded_draws:{p}:{t}:{code}")
                ck(np.all(codes[ix]==codes[None,:]),f"history_denominators_preserved:{p}:{t}")
                freq=np.bincount((ix+100*np.arange(B)[:,None]).ravel(),minlength=B*100).reshape(B,100)
                def tally(ids): return freq[:,sorted(ids)].sum(1) if ids else np.zeros(B,dtype=int)
                for r in R:
                    for ei,ev in enumerate(["loss","gain"]):
                        cell=cells[p,r,t,ev]; N=len(cell["eligible"])
                        if N:
                            observed=tally(cell["both"]); expected=tally(cell["old"])*tally(cell["new"])/N
                            refined=np.zeros(B)
                            for before in [0,1]:
                                eligible={i for i in cell["eligible"] if raw[p,r,t,i][0]==before}
                                if eligible: refined+=tally(cell["old"]&eligible)*tally(cell["new"]&eligible)/len(eligible)
                            bootstrap[:,pi,ei]+=(observed-expected)/8
                            bootstrap[:,pi,ei+4]+=(observed-refined)/8
                    if weights[p,r,t]:
                        w=float(weights[p,r,t]); ws[pi]+=w
                        a,b=hist[p,r,t]["01"],hist[p,r,t]["11"]
                        for fi,col in enumerate([2,3]):
                            losses_a={i for i in a if raw[p,r,t,i][col]==0}; losses_b={i for i in b if raw[p,r,t,i][col]==0}
                            history_num[:,pi,fi]+=100*w*(tally(losses_a)/len(a)-tally(losses_b)/len(b))
        bootstrap[:,:,2:4]=history_num/ws[None,:,None]; boot=bootstrap.mean(1)
        ck(np.allclose(boot,npz["case_estimates"],atol=1e-9,rtol=0),"all_20000_bootstrap_six_metric_vectors_via_case_frequencies")
        for j,name in enumerate(names):
            ci=np.quantile(boot[:,j],[.025,.975],method="linear")
            ck(np.allclose(ci,summary["uncertainty"][name]["case_interval"],atol=1e-9),"case_CI:"+name)
        parentdraws=list(itertools.product(range(5),repeat=5)); point=np.array([[float(v) for v in row] for row in exact])
        parentboot=np.array([[sum(point[i,j] for i in draw)/5 for j in range(6)] for draw in parentdraws])
        ck(np.allclose(parentboot,npz["parent_estimates"],atol=1e-9,rtol=0),"all_3125_parent_vectors")
        for j,name in enumerate(names): ck(np.allclose(np.quantile(parentboot[:,j],[.025,.975]),summary["uncertainty"][name]["parent_descriptive_interval"],atol=1e-9),"parent_CI:"+name)
        for pi,p in enumerate(P):
            z=summary["leave_one_parent_out"][pi]
            for j,name in enumerate(names[:4]): close(sum(exact[k][j] for k in range(5) if k!=pi)/4,z[name],f"parent_removal:{p}:{name}")
        result={"status":"passed","checks":len(checks),"failed_checks":[],"exact_point_fractions":{name:str(sum(row[j] for row in exact)/5) for j,name in enumerate(names)},"analysis_summary_sha256":sha(analysis/"summary.json"),"analysis":str(analysis),"source_sha256":sha(Path(__file__)),"bootstrap_sha256":sha(analysis/"bootstrap_draws.npz"),"python":sys.version,"numpy":np.__version__,"platform":platform.platform(),"wall_seconds":time.perf_counter()-start,"cpu_seconds":time.process_time()-cpu,"environment_steps":0,"SAC_updates":0}
        save(out/"summary.json",result); save(out/"VERIFIED.json",{"summary_sha256":sha(out/"summary.json"),"analysis_summary_sha256":result["analysis_summary_sha256"]})
        print(json.dumps({"output":str(out),"status":"passed","checks":len(checks)},ensure_ascii=False))
    except Exception:
        save(out/"FAILED.json",{"traceback":traceback.format_exc(),"source_sha256":sha(Path(__file__)),"environment_steps":0}); raise
    finally: save(out/"checks.json",checks)


if __name__=="__main__": main()
