"""Prepare immutable reference predictions and proposed seed/job manifest; no launch."""
import csv
import hashlib
import json
import platform
import shutil
import sys
import time
import traceback
import uuid
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from model import fit

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent

def sha(path):
    with Path(path).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()

def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def dump(path,value): Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def csvout(path,records):
    with Path(path).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(records[0])); w.writeheader(); w.writerows(records)

def main():
    start,cpu=time.perf_counter(),time.process_time()
    out=HERE/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_prepare_'+uuid.uuid4().hex[:8])
    out.mkdir(parents=True,exist_ok=False); (out/'source_snapshot').mkdir(); (out/'input_snapshot').mkdir()
    sources={}
    for path in sorted([*HERE.glob('*.py'),*HERE.glob('*.md'),HERE/'protocol.json']):
        shutil.copy2(path,out/'source_snapshot'/path.name); sources[path.name]=sha(path)
    dump(out/'source_hashes.json',sources)
    checks=[]; success=False
    def check(ok,name):
        checks.append({'name':name,'passed':bool(ok)})
        if not ok: raise AssertionError(name)
    print(out,flush=True)
    try:
        cfg=read(HERE/'protocol.json'); source=ROOT/cfg['reference_csv']; statespath=ROOT/cfg['state_manifest']
        check(sha(source)==cfg['reference_csv_sha256'],'reference_input_hash')
        check(sha(statespath)==cfg['state_manifest_sha256'],'state_manifest_hash')
        for path in [source,statespath]: shutil.copy2(path,out/'input_snapshot'/path.name)
        with source.open(encoding='utf-8',newline='') as f: data=list(csv.DictReader(f))
        check(len(data)==4000,'4000_reference_rows')
        lookup={(int(z['parent']),int(z['prefix']),z['task'],int(z['case'])):z for z in data}
        check(len(lookup)==4000,'reference_unique_keys')
        predictions=[]; bins=[]; coverage=[]; feasibility=[]
        for p in cfg['parents']:
            changes=[]; lower=[]; upper=[]; focusN=0
            for task in cfg['tasks']:
                cases=[i for i in range(100) if all(int(lookup[p,r,task,i]['J8'])==0 for r in cfg['prefixes'])]
                for i in cases:
                    x=lookup[p,4201,task,i]; y=lookup[p,4202,task,i]
                    check((x['seed'],x['initial_state_hash'])==(y['seed'],y['initial_state_hash']),f'cross_state_identity:{p}/{task}/{i}')
                ref=np.array([[[int(lookup[p,r,task,i][k]) for i in cases] for k in cfg['reference_future_columns']] for r in cfg['prefixes']],dtype=np.int64)
                result=fit(ref,cfg['models']['M1_shrinkage'])
                p0,p1=result['M0'],result['M1']
                check(np.all((p1>=-1e-12)&(p1<=1+1e-12)),f'probability_bounds:{p}/{task}')
                check(np.allclose(p0.sum(0),p1.sum(0),rtol=0,atol=1e-12),f'case_mean_preserved:{p}/{task}')
                for b in result['bins']:
                    c=b['common_success_count']; mask=result['difficulty']==c
                    check(np.allclose(p0[:,mask].mean(1),p1[:,mask].mean(1),rtol=0,atol=1e-12),f'bin_means_preserved:{p}/{task}/{c}')
                    bins.append({'parent':p,'task':task,**b})
                coverage.append({'parent':p,'task':task,'common_failure_cases':len(cases),'focus':task in cfg['focus_tasks'],'state_case_predictions_differ':int((abs(p0-p1)>1e-12).sum())})
                for s,r in enumerate(cfg['prefixes']):
                    for j,i in enumerate(cases):
                        z=lookup[p,r,task,i]
                        predictions.append({'parent':p,'prefix':r,'task':task,'case':i,'seed':z['seed'],'initial_state_hash':z['initial_state_hash'],'common_difficulty_count':int(result['difficulty'][j]),'state_reference_successes':int(result['reference_successes'][s,j]),'M0':float(p0[s,j]),'M1':float(p1[s,j]),'focus':task in cfg['focus_tasks']})
                if task in cfg['focus_tasks']:
                    focusN+=len(cases)
                    e0=p0*p0-p1*p1; e1=(1-p0)**2-(1-p1)**2
                    lower.extend(np.minimum(e0,e1).ravel().tolist()); upper.extend(np.maximum(e0,e1).ravel().tolist())
                    changes.extend((abs(p0-p1)>1e-12).ravel().tolist())
            check(focusN>0,f'nonempty_primary_parent:{p}')
            feasibility.append({'parent':p,'eligible_focus_cases':focusN,'changed_state_case_predictions':int(sum(changes)),'G_min_over_arbitrary_binary_labels':float(np.mean(lower)),'G_max_over_arbitrary_binary_labels':float(np.mean(upper))})
        csvout(out/'frozen_reference_predictions.csv',predictions); csvout(out/'reference_bins.csv',bins)
        csvout(out/'coverage.csv',coverage); csvout(out/'prediction_feasibility.csv',feasibility)
        states=read(statespath); oldroots={int(s[k]) for s in states for k in ['old_continuation_rng_seed','proposed_new_future_root_seed']}
        jobs=[]
        for state in states:
            p,r=state['parent'],state['prefix_continuation']
            for future in cfg['confirmation_future_ids']:
                seed=int(np.random.SeedSequence([570202,57,p,r,future]).generate_state(1)[0]); schedule=int(np.random.SeedSequence([seed,10]).generate_state(1)[0])
                jobs.append({'parent':p,'prefix':r,'future_id':future,'root_seed':seed,'schedule_seed':schedule,'training_steps':32000,'evaluation_cap':200000,'checkpoint_path':state['checkpoint']['path'],'checkpoint_manifest_sha256':state['checkpoint']['manifest_sha256'],'bank_path':state['bank']['path'],'bank_sha256':state['bank']['sha256']})
        check(len(jobs)==20 and len({z['root_seed'] for z in jobs})==20,'20_distinct_new_roots')
        check(not (oldroots&{z['root_seed'] for z in jobs}),'no_previous_root_collision')
        order=np.random.default_rng(570101).permutation(20)
        jobs=[{'proposed_order':k+1,**jobs[int(i)]} for k,i in enumerate(order)]
        csvout(out/'proposed_jobs.csv',jobs)
        check(sum(z['training_steps'] for z in jobs)==640000,'training_budget_640k')
        check(sum(z['evaluation_cap'] for z in jobs)==4000000,'evaluation_cap_4M')
        check(cfg['budget_proposal']['including_technical_cap']==4650000,'overall_proposed_cap')
        b2=cfg['second_bundle']; check(200000+2*8000+2*4*32000==b2['per_parent_training_steps'],'bundle2_training_per_parent')
        check((2+2*4)*4*100*500==b2['per_parent_evaluation_cap'],'bundle2_evaluation_per_parent')
        check(not cfg['execution_authorized'] and not cfg['scheduled'],'proposal_not_launch')
        maxgain=float(np.mean([z['G_max_over_arbitrary_binary_labels'] for z in feasibility]))
        check(maxgain>cfg['proposed_investment_gate']['G_Brier_minimum'],'Brier_gate_not_algebraically_impossible')
        receipt={'status':'reference_preparation_complete_confirmation_not_run','reference_predictions':len(predictions),'focus_state_case_predictions':sum(z['focus'] for z in predictions),'focus_case_counts':{str(z['parent']):z['eligible_focus_cases'] for z in feasibility},'parents_with_nonidentical_predictions':sum(z['changed_state_case_predictions']>0 for z in feasibility),'arbitrary_outcome_upper_bound_G':maxgain,'upper_bound_is_not_a_forecast':True,'frozen_prediction_sha256':sha(out/'frozen_reference_predictions.csv'),'proposed_jobs_sha256':sha(out/'proposed_jobs.csv'),'protocol_sha256':sha(HERE/'protocol.json'),'input_sha256':sha(source),'checks_passed':len(checks),'new_environment_steps':0,'new_training_steps':0,'new_SAC_updates':0,'confirmation_results':None,'launch_or_queue_created':False}
        dump(out/'receipt.json',receipt);dump(out/'COMPLETE.json',receipt); success=True
        print(json.dumps(receipt,ensure_ascii=False),flush=True)
    except BaseException as exc:
        dump(out/'FAILED.json',{'error':repr(exc),'traceback':traceback.format_exc(),'new_environment_steps':0});traceback.print_exc()
    finally:
        dump(out/'checks.json',checks)
        dump(out/'runtime.json',{'wall_seconds':time.perf_counter()-start,'cpu_seconds':time.process_time()-cpu,'python':sys.version,'numpy':np.__version__,'platform':platform.platform(),'new_training_steps':0,'new_evaluation_steps':0,'success':success})
    return 0 if success else 1

if __name__=='__main__': raise SystemExit(main())
