"""Common-support same-state / cross-state overlap, using existing CSVs only."""
import itertools
import shutil
from pathlib import Path
import numpy as np
from io_utils import HERE, ROOT, read, rows, sha, dump, csvout

def pair_record(a,b,mask,baseline,**labels):
    N=int(mask.sum()); n1=int((a&mask).sum()); n2=int((b&mask).sum()); m=int((a&b&mask).sum())
    expected=n1*n2/N if N else 0.0
    refined=0.0
    for j in (0,1):
        z=mask&(baseline==j); nn=int(z.sum())
        if nn: refined+=int((a&z).sum())*int((b&z).sum())/nn
    low=max(0,n1+n2-N); high=min(n1,n2)
    return {**labels,"N":N,"n_old":n1,"n_new":n2,"m":m,"expected":expected,"T":m-expected,"m_min":low,"m_max":high,"T_min":low-expected,"T_max":high-expected,"variable_margins":0<n1<N and 0<n2<N,"expected_given_J0":refined,"T_given_J0":m-refined}

def combine(records):
    # Each record is ONE parent x task stratum, already averaging its two pairs.
    fields=["N","same_m","cross_m","same_expected","cross_expected","same_T","cross_T","D","same_T_given_J0","cross_T_given_J0","D_given_J0","same_T_max","cross_T_max"]
    ans={k:sum(z[k] for z in records) for k in fields}
    ans.update(strata=len(records),nonempty_strata=sum(z["N"]>0 for z in records),same_variable_pairs=sum(z["same_variable_pairs"] for z in records),cross_variable_pairs=sum(z["cross_variable_pairs"] for z in records))
    for k in ["same_T","cross_T","D","same_T_given_J0","cross_T_given_J0","D_given_J0"]:
        ans[k+"_all_slots_pp"]=ans[k]/len(records)
        ans[k+"_eligible_pp"]=100*ans[k]/ans["N"] if ans["N"] else None
    return ans

def run(out,args):
    cfg=read(HERE/"analysis_config.json")
    parents,prefixes,tasks=cfg["parents"],cfg["prefixes"],cfg["tasks"]
    checks=[]; hashes={}
    def check(ok,label):
        checks.append({"name":label,"passed":bool(ok)})
        dump(out/"checks.json",checks)
        if not ok: raise AssertionError(label)
    def pin(path,expected=None):
        path=Path(path); path=path if path.is_absolute() else ROOT/path
        value=sha(path); hashes[path.relative_to(ROOT).as_posix()]=value
        if expected: check(value==expected,"hash:"+path.relative_to(ROOT).as_posix())
        dump(out/"input_hashes.json",hashes)
        return path
    prior=ROOT/cfg["prior54"]; prior55=ROOT/cfg["prior55"]
    check(read(pin(prior/"summary.json",cfg["prior54_summary_sha256"]))["scientific_status"]=="investment_gate_not_passed","previous_gate_not_passed_preserved")
    pin(prior55/"summary.json",cfg["prior55_summary_sha256"])
    source=pin(cfg["input"],cfg["input_sha256"])
    original_hashes=read(pin(prior/"input_hashes.json"))
    rawoldpath=next(k for k in original_hashes if k.endswith("/outcomes_25_policies.csv"))
    rawold=rows(pin(rawoldpath,original_hashes[rawoldpath]))
    oldlookup={(int(z["original_seed"]),int(z["continuation"]),int(z["horizon"]),z["task"],int(z["episode_index"])):z for z in rawold}
    newlookup={}
    for p,r in itertools.product(parents,prefixes):
        key=next(k for k in original_hashes if f"/B_s{p}_r{r}_new_future/" in k and k.endswith("/evaluation_episodes.csv"))
        for z in rows(pin(key,original_hashes[key])): newlookup[p,r,z["task"],int(z["episode_index"])]=z
    data=rows(source); check(len(data)==4000,"4000_rows")
    arr=np.full((5,2,4,100,4),-1,dtype=np.int8); identity={}; unique=set()
    for z in data:
        p,r,t,i=int(z["parent"]),int(z["prefix"]),z["task"],int(z["case"])
        key=p,r,t,i
        if key in unique: raise AssertionError("duplicate "+str(key))
        unique.add(key)
        values=[int(z[k]) for k in ["J0","J8","old_J40","new_J40"]]
        raw=[oldlookup[p,0,0,t,i],oldlookup[p,r,8000,t,i],oldlookup[p,r,40000,t,i],newlookup[key]]
        if not all(v in (0,1) for v in values) or values!=[int(q["success"]) for q in raw]: raise AssertionError("raw outcomes "+str(key))
        ident=z["seed"],z["initial_state_hash"]
        if not all((q["seed"],q["initial_state_hash"])==ident for q in raw): raise AssertionError("raw identity "+str(key))
        if (p,t,i) in identity and identity[p,t,i]!=ident: raise AssertionError("cross-prefix identity "+str(key))
        identity[p,t,i]=ident
        arr[parents.index(p),prefixes.index(r),tasks.index(t),i]=values
    check(len(unique)==4000 and len(identity)==2000 and np.all(arr>=0),"all_keys_binary_outcomes_and_raw_case_identity_exact")
    check(np.array_equal(arr[:,0,:,:,0],arr[:,1,:,:,0]),"shared_parent_J0")
    (out/"input_snapshot").mkdir()
    for path in [source,prior/"state_results.csv"]:
        shutil.copy2(pin(path),out/"input_snapshot"/path.name)
    # Trace original/new future roots and full-state preservation, without loading models.
    manifest=read(pin(cfg["state_manifest"],cfg["state_manifest_sha256"]))
    reported={(int(z["parent"]),int(z["prefix"])):z for z in rows(prior/"state_results.csv")}
    seeds=[]; all_roots=[]
    for state in manifest:
        p,r=state["parent"],state["prefix_continuation"]
        root=int(np.random.SeedSequence([510202,51,p,r]).generate_state(1)[0])
        schedule=int(np.random.SeedSequence([root,10]).generate_state(1)[0])
        check(root==state["proposed_new_future_root_seed"] and schedule==state["proposed_schedule_seed"],f"seed_recipe:{p}/{r}")
        marker=read(pin(Path(cfg["campaign52"])/"completed"/f"B_s{p}_r{r}_new_future.json"))
        result=read(pin(marker["result"]["path"],marker["result"]["sha256"]))
        forkpath=Path(marker["attempt"])/"fork_integrity.json"
        fork=read(pin(forkpath)); check(result["state"]==state,f"executed_state_manifest:{p}/{r}")
        check(result["status"]=="completed" and result["training_steps"]==32000 and result["fork_verified"] and result["evaluation_state_unchanged"],f"executed_protocol:{p}/{r}")
        old=state["old_continuation_rng_seed"]
        check(fork["root_before"]==old and fork["root_after"]==root and fork["preserved_before"]==fork["preserved_after"] and all(fork["global_streams_changed"].values()) and fork["schedule_rng_changed"],f"rng_only_fork_record:{p}/{r}")
        record=reported[p,r]
        check(int(record["old_root"])==old and int(record["new_root"])==root and int(record["schedule_seed"])==schedule,f"prior54_seed_table:{p}/{r}")
        pin(Path(state["checkpoint"]["path"])/"checkpoint_manifest.json",state["checkpoint"]["manifest_sha256"])
        pin(state["bank"]["path"],state["bank"]["sha256"])
        seeds.append({"parent":p,"prefix":r,"old_root":old,"new_root":root,"schedule_seed":schedule,"bank_sha256":state["bank"]["sha256"],"checkpoint_manifest_sha256":state["checkpoint"]["manifest_sha256"],"fork_record_sha256":sha(forkpath),"preserved_state_verified_in_record":True})
        all_roots.extend([old,root])
    check(len(all_roots)==20 and len(set(all_roots))==20,"20_distinct_future_roots")
    for p in parents: check(len({z["bank_sha256"] for z in seeds if z["parent"]==p})==1,f"same_case_bank:{p}")
    csvout(out/"seed_audit.csv",seeds)
    pairs=[]; strata=[]; coverage=[]; full=[]
    for pi,ti in itertools.product(range(5),range(4)):
        x=arr[pi,:,ti]; baseline=x[0,:,0]; starts=x[:,:,1]
        masks={"loss":(starts==1).all(0),"gain":(starts==0).all(0)}
        coverage.append({"parent":parents[pi],"task":tasks[ti],"both_success":int(masks["loss"].sum()),"both_failure":int(masks["gain"].sum()),"discordant":int((starts[0]!=starts[1]).sum()),"success_S1":int(starts[0].sum()),"success_S2":int(starts[1].sum())})
        for event in cfg["events"]:
            mask=masks[event]; target=0 if event=="loss" else 1
            aa=x[:,:,2]==target; bb=x[:,:,3]==target
            local=[]
            for a,b in cfg["pairs"]:
                rec=pair_record(aa[a],bb[b],mask,baseline,parent=parents[pi],task=tasks[ti],event=event,old_prefix=prefixes[a],new_prefix=prefixes[b],pair_type="same" if a==b else "cross")
                local.append(rec); pairs.append(rec)
            rec={"parent":parents[pi],"task":tasks[ti],"event":event,"N":int(mask.sum())}
            for kind,subset in [("same",local[:2]),("cross",local[2:])]:
                for k in ["m","expected","T","T_given_J0","T_max"]: rec[f"{kind}_{k}"]=sum(z[k] for z in subset)/2
                rec[f"{kind}_variable_pairs"]=sum(z["variable_margins"] for z in subset)
            rec["D"]=rec["same_T"]-rec["cross_T"]
            rec["D_given_J0"]=rec["same_T_given_J0"]-rec["cross_T_given_J0"]
            strata.append(rec)
            for ri in range(2):
                full.append(pair_record(aa[ri],bb[ri],starts[ri]==(1-target),baseline,parent=parents[pi],prefix=prefixes[ri],task=tasks[ti],event=event))
    csvout(out/"overlap_by_pair.csv",pairs); csvout(out/"contrast_by_parent_task.csv",strata)
    csvout(out/"coverage_by_parent_task.csv",coverage); csvout(out/"prior55_full_support_with_bounds.csv",full)
    summary={"execution_status":"completed_existing_data_analysis","scientific_status":"exploratory_state_association_contrast_not_causal","previous_selection_gate":"not_passed_unchanged","overall":{},"parents":[],"tasks":[],"leave_one_parent_out":[],"coverage":{},"uncertainty":{}}
    for event in cfg["events"]:
        subset=[z for z in strata if z["event"]==event]
        summary["overall"][event]=combine(subset)
        for p in parents: summary["parents"].append({"parent":p,"event":event,**combine([z for z in subset if z["parent"]==p])})
        for t in tasks: summary["tasks"].append({"task":t,"event":event,**combine([z for z in subset if z["task"]==t])})
        for p in parents: summary["leave_one_parent_out"].append({"excluded_parent":p,"event":event,**combine([z for z in subset if z["parent"]!=p])})
        old=[z for z in full if z["event"]==event]; eligible=sum(z["N"] for z in old); common=summary["overall"][event]["N"]
        summary["coverage"][event]={"common_unique_parent_task_cases":common,"previous_state_case_eligibility":eligible,"retained_state_case_eligibility":2*common,"retained_percent":100*2*common/eligible,"full_support_excess_count":sum(z["T"] for z in old),"full_support_variable_pairs":sum(z["variable_margins"] for z in old)}
    summary["coverage"]["discordant_unique_parent_task_cases"]=sum(z["discordant"] for z in coverage)
    check(sum(summary["overall"][e]["N"] for e in cfg["events"])+summary["coverage"]["discordant_unique_parent_task_cases"]==2000,"common_and_discordant_partition")
    # One paired resampling stream preserves all prefixes, futures and baseline strata.
    B=cfg["uncertainty"]["case_replicates"]
    indices=np.empty((5,4,B,100),dtype=np.uint8)
    draws=np.zeros((B,5,2,6))
    names=["same_T_all_slots_pp","cross_T_all_slots_pp","D_all_slots_pp","same_T_given_J0_all_slots_pp","cross_T_given_J0_all_slots_pp","D_given_J0_all_slots_pp"]
    rng=np.random.default_rng(cfg["uncertainty"]["case_seed"])
    for pi,ti in itertools.product(range(5),range(4)):
        x=arr[pi,:,ti]; codes=4*x[0,:,0]+2*x[0,:,1]+x[1,:,1]
        for c in range(8):
            positions=np.flatnonzero(codes==c)
            if len(positions): indices[pi,ti][:,positions]=positions[rng.integers(0,len(positions),size=(B,len(positions)))]
        ix=indices[pi,ti].astype(np.int64)
        for ei,event in enumerate(cfg["events"]):
            target=0 if event=="loss" else 1
            mask=(x[:,:,1]==(1-target)).all(0); N=int(mask.sum())
            if not N: continue
            old=[(x[ri,:,2][ix]==target) for ri in range(2)]
            new=[(x[ri,:,3][ix]==target) for ri in range(2)]
            Ts=[]; Rs=[]
            for a,b in cfg["pairs"]:
                z1=old[a]; z2=new[b]; m=(z1[:,mask]&z2[:,mask]).sum(1)
                Ts.append(m-z1[:,mask].sum(1)*z2[:,mask].sum(1)/N)
                exp=np.zeros(B)
                for j in (0,1):
                    sub=mask&(x[0,:,0]==j); nn=int(sub.sum())
                    if nn: exp+=z1[:,sub].sum(1)*z2[:,sub].sum(1)/nn
                Rs.append(m-exp)
            same=(Ts[0]+Ts[1])/2; cross=(Ts[2]+Ts[3])/2
            same_r=(Rs[0]+Rs[1])/2; cross_r=(Rs[2]+Rs[3])/2
            draws[:,pi,ei,:]+=np.column_stack([same,cross,same-cross,same_r,cross_r,same_r-cross_r])/4
    overall_draws=draws.mean(1)
    parent_values=np.array([[ [next(z for z in summary["parents"] if z["parent"]==p and z["event"]==event)[name] for name in names] for event in cfg["events"]] for p in parents])
    parent_indices=np.array(list(itertools.product(range(5),repeat=5)))
    parent_draws=parent_values[parent_indices].mean(1)
    for ei,event in enumerate(cfg["events"]):
        summary["uncertainty"][event]={}
        for k,name in enumerate(names):
            summary["uncertainty"][event][name]={"estimate":summary["overall"][event][name],"case_interval":np.quantile(overall_draws[:,ei,k],[.025,.975],method="linear"),"parent_descriptive_interval":np.quantile(parent_draws[:,ei,k],[.025,.975],method="linear")}
    np.savez_compressed(out/"bootstrap_draws.npz",case_indices=indices,case_parent_draws=draws,case_overall_draws=overall_draws,parent_indices=parent_indices,parent_draws=parent_draws,metric_names=np.array(names))
    for field in ["parents","tasks","leave_one_parent_out"]: csvout(out/(field+".csv"),summary[field])
    summary["uncertainty_scope"]=cfg["uncertainty"]
    summary["costs"]={"training_steps":0,"evaluation_steps":0,"new_environment_steps":0}
    dump(out/"summary.json",summary)
    return {"checks_passed":len(checks),"summary_sha256":sha(out/"summary.json"),"loss_D_pp":summary["overall"]["loss"]["D_all_slots_pp"],"gain_D_pp":summary["overall"]["gain"]["D_all_slots_pp"],"new_environment_steps":0}
