"""Exploratory case overlap and matched history analysis; no RL/environment imports."""
from __future__ import annotations
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
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def dump(path, obj):
    def serial(x):
        if isinstance(x, np.ndarray): return x.tolist()
        if isinstance(x, np.generic): return x.item()
        raise TypeError(type(x).__name__)
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=serial, allow_nan=False)+"\n",encoding="utf-8")


def csvout(path, records):
    with Path(path).open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(records[0])); w.writeheader(); w.writerows(records)


def pct(n,d):
    return 100*n/d if d else None


def event_record(a,b,eligible,base,parent,prefix,task,event):
    n=int(eligible.sum()); x=int((a&eligible).sum()); y=int((b&eligible).sum()); both=int((a&b&eligible).sum())
    expected=x*y/n if n else 0.0
    refined=0.0
    for previous in (0,1):
        mask=eligible&(base==previous); nn=int(mask.sum())
        if nn: refined+=int((a&mask).sum())*int((b&mask).sum())/nn
    return {"parent":parent,"prefix":prefix,"task":task,"event":event,"eligible":n,"old_events":x,"new_events":y,"both":both,"old_only":x-both,"new_only":y-both,"neither":n-x-y+both,"expected_overlap":expected,"excess_overlap":both-expected,"expected_given_J0":refined,"excess_given_J0":both-refined,"excess_all_cases_pp":both-expected,"both_eligible_percent":pct(both,n),"expected_eligible_percent":pct(expected,n),"old_to_new_event_repeat_percent":pct(both,x),"new_to_old_event_repeat_percent":pct(both,y),"jaccard_percent":pct(both,x+y-both),"variable_margins":bool(0<x<n and 0<y<n)}


def aggregate_events(records):
    n=sum(z["eligible"] for z in records); count=len(records)
    totals={k:sum(z[k] for z in records) for k in ["eligible","old_events","new_events","both","old_only","new_only","neither","expected_overlap","excess_overlap","expected_given_J0","excess_given_J0"]}
    return {**totals,"strata":count,"nonempty_strata":sum(z["eligible"]>0 for z in records),"variable_margin_strata":sum(z["variable_margins"] for z in records),"both_eligible_percent":pct(totals["both"],n),"expected_eligible_percent":pct(totals["expected_overlap"],n),"excess_eligible_pp":pct(totals["excess_overlap"],n),"excess_all_cases_pp":totals["excess_overlap"]/count,"excess_given_J0_all_cases_pp":totals["excess_given_J0"]/count,"jaccard_percent":pct(totals["both"],totals["old_events"]+totals["new_events"]-totals["both"]),"old_to_new_repeat_percent":pct(totals["both"],totals["old_events"]),"new_to_old_repeat_percent":pct(totals["both"],totals["new_events"])}


def history_estimate(records, parents, uniform=False):
    per_parent=[]
    for p in parents:
        valid=[z for z in records if z["parent"]==p and z["common_support"]]
        if not valid:
            per_parent.append({"parent":p,"supported_strata":0,"weight_sum":0,"old_rd_pp":None,"new_rd_pp":None})
            continue
        weights=np.array([1.0 if uniform else z["overlap_weight"] for z in valid]); denom=weights.sum()
        rates={}
        for future in ["old","new"]:
            for group in ["01","11"]:
                rates[f"{future}_risk_{group}_percent"]=float(sum(w*100*z[f"{future}_loss_{group}"]/z[f"N{group}"] for w,z in zip(weights,valid))/denom)
            rates[f"{future}_rd_pp"]=rates[f"{future}_risk_01_percent"]-rates[f"{future}_risk_11_percent"]
        per_parent.append({"parent":p,"supported_strata":len(valid),"weight_sum":float(denom),**rates})
    valid=[z for z in per_parent if z["supported_strata"]]
    names=[f"{f}_{suffix}" for f in ["old","new"] for suffix in ["risk_01_percent","risk_11_percent","rd_pp"]]
    return {"supported_parents":len(valid),"supported_parent_ids":[z["parent"] for z in valid],"supported_strata":sum(z["supported_strata"] for z in valid),"overall":{k:float(np.mean([z[k] for z in valid])) if valid else None for k in names},"parents":per_parent}


def main():
    start,cpu=time.perf_counter(),time.process_time()
    out=HERE/"results"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_analysis_"+uuid.uuid4().hex[:8])
    out.mkdir(parents=True,exist_ok=False); (out/"source_snapshot").mkdir(); (out/"input_snapshot").mkdir()
    sources={}
    for path in sorted([*HERE.glob("*.py"),HERE/"analysis_config.json",HERE/"research_question_ko.md"]):
        shutil.copy2(path,out/"source_snapshot"/path.name); sources[path.name]=sha(path)
    dump(out/"source_hashes.json",sources)
    checks=[]; inputs={}
    def check(ok,name):
        checks.append({"name":name,"passed":bool(ok)})
        if not ok: raise AssertionError(name)
    def pin(path,expected=None):
        path=Path(path); path=path if path.is_absolute() else ROOT/path
        actual=sha(path); inputs[str(path.relative_to(ROOT)).replace("\\","/")]=actual
        if expected: check(actual==expected,"hash:"+str(path.relative_to(ROOT)))
        return path
    try:
        cfg=read(HERE/"analysis_config.json"); parents,prefixes,tasks=cfg["parents"],cfg["prefixes"],cfg["tasks"]
        inputpath=pin(cfg["input"],cfg["input_sha256"]); prior=ROOT/cfg["prior_analysis"]
        oldsummary=read(pin(prior/"summary.json",cfg["prior_summary_sha256"]))
        check(oldsummary["scientific_status"]=="investment_gate_not_passed","previous_gate_preserved")
        source_hashes=read(pin(prior/"input_hashes.json")); rawoldpath=next(k for k in source_hashes if k.endswith("/outcomes_25_policies.csv"))
        rawold=rows(pin(rawoldpath,source_hashes[rawoldpath])); oldlookup={(int(z["original_seed"]),int(z["continuation"]),int(z["horizon"]),z["task"],int(z["episode_index"])):z for z in rawold}
        newlookup={}
        for p,r in itertools.product(parents,prefixes):
            key=next(k for k in source_hashes if f"/B_s{p}_r{r}_new_future/" in k and k.endswith("/evaluation_episodes.csv"))
            for z in rows(pin(key,source_hashes[key])): newlookup[p,r,z["task"],int(z["episode_index"])]=z
        data=rows(inputpath); check(len(data)==4000,"4000_state_case_observations")
        arr=np.full((5,2,4,100,4),-1,dtype=np.int8); seen=set()
        for z in data:
            p,r,t,i=int(z["parent"]),int(z["prefix"]),z["task"],int(z["case"]); key=(p,r,t,i)
            check(key not in seen,"unique:"+str(key)); seen.add(key)
            raw=[oldlookup[p,0,0,t,i],oldlookup[p,r,8000,t,i],oldlookup[p,r,40000,t,i],newlookup[key]]
            check(all((q["seed"],q["initial_state_hash"])==(z["seed"],z["initial_state_hash"]) for q in raw),"paired_identity:"+str(key))
            values=[int(z[k]) for k in ["J0","J8","old_J40","new_J40"]]
            check(values==[int(q["success"]) for q in raw] and all(v in [0,1] for v in values),"original_outcome_values:"+str(key))
            arr[parents.index(p),prefixes.index(r),tasks.index(t),i]=values
        check(np.all(arr>=0),"complete_tensor")
        check(np.array_equal(arr[:,0,:,:,0],arr[:,1,:,:,0]),"same_parent_policy_across_prefixes")
        for path in [inputpath,prior/"state_results.csv",prior/"summary.json"]:
            shutil.copy2(pin(path),out/"input_snapshot"/path.name)
        events=[]; histories=[]
        for pi,ri,ti in itertools.product(range(5),range(2),range(4)):
            x=arr[pi,ri,ti]; b,m,o,n=x.T
            for event in ["loss","gain"]:
                eligible=(m==1) if event=="loss" else (m==0)
                a=(o==0) if event=="loss" else (o==1); c=(n==0) if event=="loss" else (n==1)
                events.append(event_record(a,c,eligible,b,parents[pi],prefixes[ri],tasks[ti],event))
            mask01=(b==0)&(m==1); mask11=(b==1)&(m==1); n01=int(mask01.sum()); n11=int(mask11.sum())
            z={"parent":parents[pi],"prefix":prefixes[ri],"task":tasks[ti],"N01":n01,"N11":n11,"common_support":n01>0 and n11>0,"overlap_weight":n01*n11/(n01+n11) if n01+n11 else 0.0}
            for f,y in [("old",o),("new",n)]:
                for label,mask in [("01",mask01),("11",mask11)]: z[f+"_loss_"+label]=int(((y==0)&mask).sum())
                z[f+"_rd_pp"]=100*(z[f+"_loss_01"]/n01-z[f+"_loss_11"]/n11) if n01 and n11 else None
            z["both_loss_01"]=int(((o==0)&(n==0)&mask01).sum()); z["both_loss_11"]=int(((o==0)&(n==0)&mask11).sum())
            histories.append(z)
        csvout(out/"overlap_by_state_task.csv",events); csvout(out/"history_by_state_task.csv",histories)
        overall={e:aggregate_events([z for z in events if z["event"]==e]) for e in ["loss","gain"]}
        parent_overlaps=[{"parent":p,"event":e,**aggregate_events([z for z in events if z["parent"]==p and z["event"]==e])} for p,e in itertools.product(parents,["loss","gain"])]
        task_overlaps=[{"task":t,"event":e,**aggregate_events([z for z in events if z["task"]==t and z["event"]==e])} for t,e in itertools.product(tasks,["loss","gain"])]
        csvout(out/"overlap_by_parent.csv",parent_overlaps); csvout(out/"overlap_by_task.csv",task_overlaps)
        matched=history_estimate(histories,parents); equal=history_estimate(histories,parents,True)
        task_history={t:history_estimate([z for z in histories if z["task"]==t],parents) for t in tasks}
        csvout(out/"history_matched_by_parent.csv",matched["parents"])
        pooled={}
        for g in ["01","11"]:
            nn=sum(z["N"+g] for z in histories)
            pooled[g]={"N":nn,"old_loss":sum(z["old_loss_"+g] for z in histories),"new_loss":sum(z["new_loss_"+g] for z in histories),"both_loss":sum(z["both_loss_"+g] for z in histories)}
            for f in ["old","new","both"]: pooled[g][f+"_risk_percent"]=pct(pooled[g][f+"_loss"],nn)
        matched_coverage={g:{"supported_cases":sum(z["N"+g] for z in histories if z["common_support"]),"all_cases":pooled[g]["N"]} for g in ["01","11"]}
        # All zero-support cells remain visible; do not give them artificial zero risk differences.
        supported=matched["supported_parent_ids"]
        check(len(supported)>0,"history_estimable_in_some_parents")
        remove=[]
        for p in parents:
            remaining=[q for q in parents if q!=p]
            h=history_estimate(histories,remaining)
            z={"excluded_parent":p,"history_old_rd_pp":h["overall"]["old_rd_pp"],"history_new_rd_pp":h["overall"]["new_rd_pp"],"history_supported_parents":h["supported_parents"]}
            for e in ["loss","gain"]: z[e+"_excess_all_cases_pp"]=aggregate_events([r for r in events if r["parent"]!=p and r["event"]==e])["excess_all_cases_pp"]
            remove.append(z)
        csvout(out/"leave_one_parent_out.csv",remove)
        B=cfg["uncertainty"]["case_replicates"]; rng=np.random.default_rng(cfg["uncertainty"]["case_seed"])
        # Axes: parent, task, draw, case position; the same draw is used for both prefixes/futures.
        indices=np.empty((5,4,B,100),dtype=np.uint8)
        boot_events=np.zeros((B,5,2,2))  # draw,parent,event,ordinary/refined
        boot_history_num=np.zeros((B,5,2)); weight_den=np.zeros(5)
        for pi,p in enumerate(parents):
            for ti,t in enumerate(tasks):
                history_code=4*arr[pi,0,ti,:,0]+2*arr[pi,0,ti,:,1]+arr[pi,1,ti,:,1]
                for code in range(8):
                    positions=np.flatnonzero(history_code==code)
                    if len(positions): indices[pi,ti][:,positions]=positions[rng.integers(0,len(positions),size=(B,len(positions)))]
                ix=indices[pi,ti].astype(np.int64)
                for ri,r in enumerate(prefixes):
                    x=arr[pi,ri,ti]; b,m,o,n=x.T
                    old=x[:,2][ix]; new=x[:,3][ix]
                    for ei,e in enumerate(["loss","gain"]):
                        eligible=m==(1 if e=="loss" else 0); N=int(eligible.sum())
                        if not N: continue
                        a=(old==0) if e=="loss" else (old==1); c=(new==0) if e=="loss" else (new==1)
                        s1=a[:,eligible].sum(1); s2=c[:,eligible].sum(1); shared=(a[:,eligible]&c[:,eligible]).sum(1)
                        exp=s1*s2/N; exp_history=np.zeros(B)
                        for previous in [0,1]:
                            mask=eligible&(b==previous); NN=int(mask.sum())
                            if NN: exp_history+=a[:,mask].sum(1)*c[:,mask].sum(1)/NN
                        boot_events[:,pi,ei,0]+=(shared-exp)/8
                        boot_events[:,pi,ei,1]+=(shared-exp_history)/8
                    mask01=(b==0)&(m==1); mask11=(b==1)&(m==1); n01=int(mask01.sum()); n11=int(mask11.sum())
                    if n01 and n11:
                        weight=n01*n11/(n01+n11); weight_den[pi]+=weight
                        for fi,endpoint in enumerate([old,new]):
                            rd=100*((endpoint[:,mask01]==0).mean(1)-(endpoint[:,mask11]==0).mean(1))
                            boot_history_num[:,pi,fi]+=weight*rd
        valid=weight_den>0
        boot_history=boot_history_num[:,valid,:]/weight_den[valid][None,:,None]
        boot=np.column_stack((boot_events[:,:,:,0].mean(1),boot_history.mean(1),boot_events[:,:,:,1].mean(1)))
        metric_names=["loss_excess_all_cases_pp","gain_excess_all_cases_pp","history_old_rd_pp","history_new_rd_pp","loss_excess_given_J0_pp","gain_excess_given_J0_pp"]
        estimates=[overall["loss"]["excess_all_cases_pp"],overall["gain"]["excess_all_cases_pp"],matched["overall"]["old_rd_pp"],matched["overall"]["new_rd_pp"],overall["loss"]["excess_given_J0_all_cases_pp"],overall["gain"]["excess_given_J0_all_cases_pp"]]
        case_ci=np.quantile(boot,[.025,.975],axis=0,method="linear").T
        # Parent resampling: preserve each parent's two prefixes and all cases as a cluster.
        parent_matrix=[]
        for p in parents:
            loss=next(z for z in parent_overlaps if z["parent"]==p and z["event"]=="loss")
            gain=next(z for z in parent_overlaps if z["parent"]==p and z["event"]=="gain")
            hist=next(z for z in matched["parents"] if z["parent"]==p)
            parent_matrix.append([loss["excess_all_cases_pp"],gain["excess_all_cases_pp"],hist["old_rd_pp"] if hist["old_rd_pp"] is not None else np.nan,hist["new_rd_pp"] if hist["new_rd_pp"] is not None else np.nan,loss["excess_given_J0_all_cases_pp"],gain["excess_given_J0_all_cases_pp"]])
        parent_matrix=np.array(parent_matrix); parent_indices=np.array(list(itertools.product(range(5),repeat=5)),dtype=np.uint8)
        gathered=parent_matrix[parent_indices]; den=np.isfinite(gathered).sum(1); sums=np.nansum(gathered,axis=1)
        parent_boot=np.divide(sums,den,out=np.full_like(sums,np.nan),where=den>0)
        parent_ci=np.nanquantile(parent_boot,[.025,.975],axis=0,method="linear").T
        np.savez_compressed(out/"bootstrap_draws.npz",case_indices=indices,case_estimates=boot,parent_indices=parent_indices,parent_estimates=parent_boot)
        uncertainty={name:{"estimate":float(estimates[i]),"case_interval":case_ci[i].tolist(),"parent_descriptive_interval":parent_ci[i].tolist(),"parent_draws_without_support":int((den[:,i]==0).sum())} for i,name in enumerate(metric_names)}
        summary={"status":"completed_exploratory_analysis","new_environment_steps":0,"new_SAC_updates":0,"scientific_gate":"no_new_gate_not_a_selector_success","previous_selection_gate":"not_passed_unchanged","parents":parents,"prefixes":prefixes,"tasks":tasks,"independent_parent_count":5,"state_count":10,"state_case_observations":4000,"unique_parent_task_cases":2000,"futures_per_state":2,"event_overlap":overall,"overlap_by_parent":parent_overlaps,"overlap_by_task":task_overlaps,"history_pooled":pooled,"history_matched":matched,"history_equal_strata_sensitivity":equal,"history_by_task":task_history,"history_common_support_coverage":matched_coverage,"leave_one_parent_out":remove,"uncertainty":uncertainty,"bootstrap_config":cfg["uncertainty"],"source_summary_sha256":cfg["prior_summary_sha256"],"limitations":["Exploratory hypotheses developed after prior outcomes; no confirmatory independence.","Only two futures per state, five parents, known O100 case bank.","Chance excess may reflect shared case difficulty; no causal mechanism demonstrated.","History groups are observational, not randomized mastery age.","Case intervals condition on observed history composition and fixed trained policies.","Do not infer relative gain/loss repeatability from raw overlap with different prevalences.","Selection development and original C/stages2/3 remain held."]}
        dump(out/"summary.json",summary)
        dump(out/"runtime.json",{"python":sys.version,"platform":platform.platform(),"numpy":np.__version__,"wall_seconds":time.perf_counter()-start,"cpu_seconds":time.process_time()-cpu,"environment_steps":0,"SAC_updates":0,"models_loaded":False,"GPU_used":False})
        dump(out/"COMPLETE.json",{"summary_sha256":sha(out/"summary.json")})
        print(json.dumps({"output":str(out),"overlap":overall,"history_pooled":pooled,"history_matched":matched,"uncertainty":uncertainty,"coverage":matched_coverage},ensure_ascii=False,indent=2))
    except Exception:
        dump(out/"FAILED.json",{"traceback":traceback.format_exc(),"environment_steps":0,"sources":sources}); raise
    finally:
        dump(out/"input_hashes.json",inputs); dump(out/"checks.json",{"checks":len(checks),"failed":[c for c in checks if not c["passed"]],"detail":checks})


if __name__=="__main__": main()
