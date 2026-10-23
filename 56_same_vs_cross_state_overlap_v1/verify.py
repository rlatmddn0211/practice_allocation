"""Independent set/Fraction point estimates and frequency-weight bootstrap checks.

Does not import analyze.py or reuse its computational helpers.
"""
import itertools
from fractions import Fraction as F
from pathlib import Path
import numpy as np
from io_utils import HERE, ROOT, read, rows, sha, dump

def run(out,args):
    analysis=Path(args[0]).resolve(); cfg=read(HERE/"analysis_config.json")
    checks=[]
    def check(ok,name):
        checks.append({"name":name,"passed":bool(ok)})
        if not ok:
            dump(out/"checks.json",checks)
            raise AssertionError(name)
    def near(a,b,name): check(abs(float(a)-float(b))<1e-10,name)
    for name,value in read(analysis/"source_hashes.json").items():
        check(sha(analysis/"source_snapshot"/name)==value,"executed_source_snapshot:"+name)
    for name,value in read(analysis/"input_hashes.json").items(): check(sha(ROOT/name)==value,"input_still_pinned:"+name)
    data=rows(ROOT/cfg["input"]); check(sha(ROOT/cfg["input"])==cfg["input_sha256"],"primary_input_hash")
    lookup={(int(z["parent"]),int(z["prefix"]),z["task"],int(z["case"])):z for z in data}
    parents,prefixes,tasks=cfg["parents"],cfg["prefixes"],cfg["tasks"]
    outputs={(int(z["parent"]),z["task"],z["event"],int(z["old_prefix"]),int(z["new_prefix"])):z for z in rows(analysis/"overlap_by_pair.csv")}
    full={(int(z["parent"]),z["task"],z["event"],int(z["prefix"])):z for z in rows(analysis/"prior55_full_support_with_bounds.csv")}
    point={}; exact_pair={}; tensors={}; support={}
    for p,t in itertools.product(parents,tasks):
        policies=[]
        for r in prefixes:
            policies.append(np.array([[int(lookup[p,r,t,i][k]) for k in ["J0","J8","old_J40","new_J40"]] for i in range(100)],dtype=np.int64))
        x=np.array(policies); tensors[p,t]=x
        for event in cfg["events"]:
            baseline=1 if event=="loss" else 0; future=1-baseline
            eligible={i for i in range(100) if all(x[r,i,1]==baseline for r in range(2))}
            support[p,t,event]=len(eligible)
            a=[{i for i in eligible if x[r,i,2]==future} for r in range(2)]
            b=[{i for i in eligible if x[r,i,3]==future} for r in range(2)]
            TT=[]; RR=[]
            for ra,rb in [(0,0),(1,1),(0,1),(1,0)]:
                N=len(eligible); n1=len(a[ra]); n2=len(b[rb]); m=len(a[ra]&b[rb])
                expectation=F(n1*n2,N) if N else F(0)
                refined=F(0)
                for j in (0,1):
                    group={i for i in eligible if x[0,i,0]==j}
                    if group: refined+=F(len(a[ra]&group)*len(b[rb]&group),len(group))
                values={"N":N,"n_old":n1,"n_new":n2,"m":m,"expected":expectation,"T":m-expectation,"m_min":max(0,n1+n2-N),"m_max":min(n1,n2),"T_min":max(0,n1+n2-N)-expectation,"T_max":min(n1,n2)-expectation,"expected_given_J0":refined,"T_given_J0":m-refined}
                label=p,t,event,prefixes[ra],prefixes[rb]; recorded=outputs[label]
                for key,v in values.items(): near(v,recorded[key],f"set_fraction_pair:{label}:{key}")
                check(recorded["variable_margins"]==str(0<n1<N and 0<n2<N),f"support:{label}")
                check(values["m_min"]<=m<=values["m_max"],f"overlap_bounds:{label}")
                TT.append(m-expectation); RR.append(m-refined); exact_pair[label]=values
            same=(TT[0]+TT[1])/2; cross=(TT[2]+TT[3])/2
            same_r=(RR[0]+RR[1])/2; cross_r=(RR[2]+RR[3])/2
            point[p,t,event]=[same,cross,same-cross,same_r,cross_r,same_r-cross_r]
            u={i:int(i in a[0])-int(i in a[1]) for i in eligible}
            v={i:int(i in b[0])-int(i in b[1]) for i in eligible}
            identity=(F(sum(u[i]*v[i] for i in eligible))-F(sum(u.values())*sum(v.values()),len(eligible)))/2 if eligible else F(0)
            near(identity,same-cross,f"centered_difference_identity:{p}/{t}/{event}")
            for ri,r in enumerate(prefixes):
                mask={i for i in range(100) if x[ri,i,1]==baseline}
                aa={i for i in mask if x[ri,i,2]==future}; bb={i for i in mask if x[ri,i,3]==future}
                expected=F(len(aa)*len(bb),len(mask)) if mask else F(0)
                rec=full[p,t,event,r]
                for k,val in {"N":len(mask),"n_old":len(aa),"n_new":len(bb),"m":len(aa&bb),"T":len(aa&bb)-expected,"T_max":min(len(aa),len(bb))-expected}.items(): near(val,rec[k],f"full_support:{p}/{t}/{event}/{r}:{k}")
    summary=read(analysis/"summary.json")
    names=["same_T_all_slots_pp","cross_T_all_slots_pp","D_all_slots_pp","same_T_given_J0_all_slots_pp","cross_T_given_J0_all_slots_pp","D_given_J0_all_slots_pp"]
    parent_values=np.zeros((5,2,6))
    for ei,event in enumerate(cfg["events"]):
        for pi,p in enumerate(parents):
            parent_values[pi,ei]=[float(sum(point[p,t,event][k] for t in tasks)/4) for k in range(6)]
            rec=next(z for z in summary["parents"] if z["parent"]==p and z["event"]==event)
            for k,name in enumerate(names): near(parent_values[pi,ei,k],rec[name],f"parent:{p}/{event}/{name}")
        for k,name in enumerate(names): near(parent_values[:,ei,k].mean(),summary["overall"][event][name],f"overall:{event}/{name}")
        near(sum(support[p,t,event] for p,t in itertools.product(parents,tasks)),summary["overall"][event]["N"],f"eligible:{event}")
        for p in parents:
            rec=next(z for z in summary["leave_one_parent_out"] if z["excluded_parent"]==p and z["event"]==event)
            for k,name in enumerate(names): near(sum(point[q,t,event][k] for q in parents if q!=p for t in tasks)/16,rec[name],f"lopo:{p}/{event}/{name}")
        for t in tasks:
            rec=next(z for z in summary["tasks"] if z["task"]==t and z["event"]==event)
            for k,name in enumerate(names): near(sum(point[p,t,event][k] for p in parents)/5,rec[name],f"task:{t}/{event}/{name}")
    # Recompute ALL bootstrap draws with frequency weights, not sampled outcome arrays.
    boot=np.load(analysis/"bootstrap_draws.npz",allow_pickle=False); indices=boot["case_indices"]
    B=cfg["uncertainty"]["case_replicates"]; calculated=np.zeros((B,5,2,6))
    rng=np.random.default_rng(cfg["uncertainty"]["case_seed"])
    for pi,p in enumerate(parents):
        for ti,t in enumerate(tasks):
            x=tensors[p,t]; ix=indices[pi,ti].astype(int)
            codes=4*x[0,:,0]+2*x[0,:,1]+x[1,:,1]
            regenerated=np.zeros_like(ix)
            for code in range(8):
                pos=np.where(codes==code)[0]
                if len(pos): regenerated[:,pos]=pos[rng.integers(0,len(pos),size=(B,len(pos)))]
            check(np.array_equal(ix,regenerated),f"bootstrap_seed:{p}/{t}")
            check(np.all(codes[ix]==codes[None,:]),f"joint_history_preserved:{p}/{t}")
            freq=np.zeros((B,100),dtype=np.float64)
            np.add.at(freq,(np.arange(B)[:,None],ix),1)
            for ei,event in enumerate(cfg["events"]):
                baseline=1 if event=="loss" else 0; target=1-baseline
                mask=np.all(x[:,:,1]==baseline,axis=0); N=int(mask.sum())
                if not N: continue
                a=(x[:,:,2]==target).astype(np.int64); b=(x[:,:,3]==target).astype(np.int64)
                terms=[]; refined=[]
                for ra,rb in [(0,0),(1,1),(0,1),(1,0)]:
                    m=freq@(mask*a[ra]*b[rb]); exp=(freq@(mask*a[ra]))*(freq@(mask*b[rb]))/N
                    er=np.zeros(B)
                    for j in (0,1):
                        sub=mask&(x[0,:,0]==j); nj=int(sub.sum())
                        if nj: er+=(freq@(sub*a[ra]))*(freq@(sub*b[rb]))/nj
                    terms.append(m-exp); refined.append(m-er)
                s=(terms[0]+terms[1])/2; c=(terms[2]+terms[3])/2
                sr=(refined[0]+refined[1])/2; cr=(refined[2]+refined[3])/2
                calculated[:,pi,ei]+=np.column_stack([s,c,s-c,sr,cr,sr-cr])/4
                u=a[0]-a[1]; v=b[0]-b[1]
                identity=((freq@(mask*u*v))-(freq@(mask*u))*(freq@(mask*v))/N)/2
                check(np.allclose(s-c,identity,rtol=0,atol=1e-10),f"all_bootstrap_D_identity:{p}/{t}/{event}")
    check(np.allclose(calculated,boot["case_parent_draws"],rtol=0,atol=1e-10),"all_20000_paired_frequency_bootstrap_draws")
    check(np.allclose(calculated.mean(1),boot["case_overall_draws"],rtol=0,atol=1e-10),"case_parent_equal_weight")
    parent_draws=np.array([parent_values[list(sample)].mean(0) for sample in itertools.product(range(5),repeat=5)])
    check(np.allclose(parent_draws,boot["parent_draws"],rtol=0,atol=1e-10),"all_3125_parent_draws")
    for ei,event in enumerate(cfg["events"]):
        for k,name in enumerate(names):
            rec=summary["uncertainty"][event][name]
            check(np.allclose(np.quantile(calculated.mean(1)[:,ei,k],[.025,.975]),rec["case_interval"],rtol=0,atol=1e-10),f"paired_case_interval:{event}/{name}")
            check(np.allclose(np.quantile(parent_draws[:,ei,k],[.025,.975]),rec["parent_descriptive_interval"],rtol=0,atol=1e-10),f"parent_interval:{event}/{name}")
    # Scope-sensitive arithmetic: task contributions and excluded-case coverage.
    gain=summary["overall"]["gain"]; loss=summary["overall"]["loss"]
    task_gain={z["task"]:z["D"] for z in summary["tasks"] if z["event"]=="gain"}
    scope={"gain_D_by_task_count":task_gain,"gain_DC_PU_share_percent":100*(task_gain["DC"]+task_gain["PU"])/gain["D"],"loss_41013_common_eligible":sum(support[41013,t,"loss"] for t in tasks),"gain_positive_parent_count":sum(parent_values[:,1,2]>1e-12),"gain_zero_parent_count":sum(abs(parent_values[:,1,2])<1e-12),"max_gain_parent_share_percent":100*parent_values[:,1,2].max()/parent_values[:,1,2].sum()}
    check(gain["N"]+loss["N"]+summary["coverage"]["discordant_unique_parent_task_cases"]==2000,"full_common_support_partition")
    check(summary["costs"]["new_environment_steps"]==0 and summary["previous_selection_gate"]=="not_passed_unchanged","scope_and_gate_unchanged")
    dump(out/"scope_summary.json",scope)
    dump(out/"checks.json",checks)
    dump(out/"verified_inputs.json",{"analysis":str(analysis),"summary_sha256":sha(analysis/"summary.json"),"bootstrap_sha256":sha(analysis/"bootstrap_draws.npz"),"primary_csv_sha256":sha(ROOT/cfg["input"]),"all_pinned_input_files_checked":len(read(analysis/"input_hashes.json"))})
    return {"checks_passed":len(checks),"all_point_estimates_verified_with_sets_and_exact_fractions":True,"all_case_bootstrap_draws_verified":B,"parent_draws_verified":3125,"new_environment_steps":0}
