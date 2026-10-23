"""Independent reference-preparation audit using exact rational block enumeration.

No import of model.py or prepare.py. No new outcome, environment or training.
"""
import csv
import hashlib
import itertools
import json
import math
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
ROOT=HERE.parent
def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def rows(p):
    with Path(p).open(encoding='utf-8-sig',newline='') as stream: return list(csv.DictReader(stream))
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,x): Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def exact_monotone(a,b):
    """Enumerate all contiguous equality blocks, not PAVA."""
    m=len(a)
    if not m: return []
    best=None; score=math.inf
    for cuts in itertools.product((False,True),repeat=m-1):
        ends=[0]+[j+1 for j,c in enumerate(cuts) if c]+[m]
        fitted=[]
        for lo,hi in zip(ends,ends[1:]):
            rate=F(sum(a[lo:hi]),sum(b[lo:hi])); fitted.extend([rate]*(hi-lo))
        if any(fitted[j]>fitted[j+1] for j in range(m-1)): continue
        loss=-sum(aa*math.log(float(v))+(bb-aa)*math.log(float(1-v)) for aa,bb,v in zip(a,b,fitted))
        if loss<score-1e-12: score=loss; best=fitted
    return best

def main():
    prepared=Path(sys.argv[1]).resolve(); start,cpu=time.perf_counter(),time.process_time()
    out=HERE/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_verify_'+uuid.uuid4().hex[:8])
    out.mkdir(parents=True,exist_ok=False); (out/'source_snapshot').mkdir()
    sourcehash={}
    for p in sorted([*HERE.glob('*.py'),*HERE.glob('*.md'),HERE/'protocol.json']):
        shutil.copy2(p,out/'source_snapshot'/p.name); sourcehash[p.name]=sha(p)
    dump(out/'source_hashes.json',sourcehash)
    checks=[]; success=False
    def check(ok,name):
        checks.append({'name':name,'passed':bool(ok)})
        if not ok: raise AssertionError(name)
    def near(a,b,name): check(abs(float(a)-float(b))<1e-11,name)
    print(out,flush=True)
    try:
        cfg=read(HERE/'protocol.json'); receipt=read(prepared/'receipt.json')
        check(sha(HERE/'protocol.json')==receipt['protocol_sha256'],'unchanged_frozen_protocol')
        for n,h in read(prepared/'source_hashes.json').items(): check(sha(prepared/'source_snapshot'/n)==h,'source_snapshot:'+n)
        for name in ['model.py','prepare.py']: check(sha(HERE/name)==read(prepared/'source_hashes.json')[name],'unchanged_computation:'+name)
        source=ROOT/cfg['reference_csv']; check(sha(source)==cfg['reference_csv_sha256'],'reference_hash')
        data=rows(source); lookup={(int(z['parent']),int(z['prefix']),z['task'],int(z['case'])):z for z in data}
        saved=rows(prepared/'frozen_reference_predictions.csv')
        output={(int(z['parent']),int(z['prefix']),z['task'],int(z['case'])):z for z in saved}
        check(len(output)==len(saved)==2494,'prediction_unique_keys')
        all_exact={}; differing=[]; focused=[]
        for p,t in itertools.product(cfg['parents'],cfg['tasks']):
            eligible=[i for i in range(100) if lookup[p,4201,t,i]['J8']=='0' and lookup[p,4202,t,i]['J8']=='0']
            k={r:{i:sum(int(lookup[p,r,t,i][f]) for f in ['old_J40','new_J40']) for i in eligible} for r in cfg['prefixes']}
            c={i:k[4201][i]+k[4202][i] for i in eligible}; occupied=sorted(set(c.values()))
            groups={bin:[i for i in eligible if c[i]==bin] for bin in occupied}
            baseline={}
            for r in cfg['prefixes']:
                a=[sum(k[r][i] for i in groups[bin])+1 for bin in occupied]
                b=[2*len(groups[bin])+2 for bin in occupied]
                baseline[r]=dict(zip(occupied,exact_monotone(a,b)))
            for bin in occupied:
                cases=groups[bin]; average=F(sum(k[4201][i] for i in cases),2*len(cases))
                h={i:F(k[4201][i],2)-average for i in cases}; bounds=[F(1,4)]
                for r,sign in [(4201,1),(4202,-1)]:
                    for i in cases:
                        d=sign*h[i]; base=baseline[r][bin]
                        if d>0: bounds.append((1-base)/d)
                        if d<0: bounds.append(base/(-d))
                strength=min(bounds)
                for r,sign in [(4201,1),(4202,-1)]:
                    exacts=[]
                    for i in cases:
                        base=baseline[r][bin]; extra=base+sign*strength*h[i]; key=p,r,t,i
                        near(base,output[key]['M0'],f'M0_exact:{key}'); near(extra,output[key]['M1'],f'M1_exact:{key}')
                        check(int(output[key]['common_difficulty_count'])==c[i] and int(output[key]['state_reference_successes'])==k[r][i],f'reference_features:{key}')
                        check((output[key]['seed'],output[key]['initial_state_hash'])==(lookup[key]['seed'],lookup[key]['initial_state_hash']),f'identity:{key}')
                        check(0<=extra<=1,f'probability:{key}'); exacts.append(extra)
                        all_exact[key]=(base,extra)
                        if t in cfg['focus_tasks']:
                            focused.append(key)
                            if extra!=base: differing.append(key)
                    check(sum(exacts)/len(exacts)==baseline[r][bin],f'exact_bin_mean:{p}/{r}/{t}/{bin}')
                for i in cases: check(sum(all_exact[p,r,t,i][1] for r in cfg['prefixes'])==sum(all_exact[p,r,t,i][0] for r in cfg['prefixes']),f'exact_case_state_mean:{p}/{t}/{i}')
        check(len(focused)==1096 and len(differing)==98,'focus_and_changed_prediction_counts')
        feasibility=[]
        for p in cfg['parents']:
            keys=[key for key in focused if key[0]==p]
            minima=[]; maxima=[]
            for key in keys:
                a,b=all_exact[key]; vals=[a*a-b*b,(1-a)**2-(1-b)**2]; minima.append(min(vals));maxima.append(max(vals))
            original=next(z for z in rows(prepared/'prediction_feasibility.csv') if int(z['parent'])==p)
            near(sum(maxima)/len(keys),original['G_max_over_arbitrary_binary_labels'],f'Brier_algebraic_bound:{p}')
            feasibility.append(sum(maxima)/len(keys))
        near(sum(feasibility)/5,receipt['arbitrary_outcome_upper_bound_G'],'global_algebraic_bound')
        # Verify seed manifest and pinned checkpoint/bank manifests without loading models.
        states=read(ROOT/cfg['state_manifest']); jobs=rows(prepared/'proposed_jobs.csv')
        check(len(jobs)==20,'job_count')
        for state in states:
            cp=Path(state['checkpoint']['path'])/'checkpoint_manifest.json'; bank=Path(state['bank']['path'])
            check(sha(cp)==state['checkpoint']['manifest_sha256'],'checkpoint_manifest:'+str(cp))
            check(sha(bank)==state['bank']['sha256'],'bank:'+str(bank))
            for fid in [3,4]:
                job=next(z for z in jobs if (int(z['parent']),int(z['prefix']),int(z['future_id']))==(state['parent'],state['prefix_continuation'],fid))
                seed=int(np.random.SeedSequence([570202,57,state['parent'],state['prefix_continuation'],fid]).generate_state(1)[0])
                check(int(job['root_seed'])==seed and int(job['schedule_seed'])==int(np.random.SeedSequence([seed,10]).generate_state(1)[0]),'new_seed:'+str((state['parent'],state['prefix_continuation'],fid)))
                check(job['checkpoint_manifest_sha256']==state['checkpoint']['manifest_sha256'] and job['bank_sha256']==state['bank']['sha256'],'job_source:'+str((state['parent'],state['prefix_continuation'],fid)))
        prior_roots={s[k] for s in states for k in ['old_continuation_rng_seed','proposed_new_future_root_seed']}
        newroots={int(z['root_seed']) for z in jobs};check(len(newroots)==20 and not(newroots&prior_roots),'new_root_uniqueness')
        check(sum(int(z['training_steps']) for z in jobs)==640000 and sum(int(z['evaluation_cap']) for z in jobs)==4000000,'budget')
        check(receipt['confirmation_results'] is None and not receipt['launch_or_queue_created'] and not cfg['execution_authorized'] and not cfg['scheduled'],'no_confirmation_executed')
        check(sha(prepared/'frozen_reference_predictions.csv')==receipt['frozen_prediction_sha256'],'prediction_file_frozen')
        check(sha(prepared/'proposed_jobs.csv')==receipt['proposed_jobs_sha256'],'job_manifest_frozen')
        result={'status':'reference_preparation_verified_not_scientific_confirmation','checks_passed':len(checks),'prediction_rows_verified':len(saved),'primary_cases':len(focused)//2,'cases_with_model_difference':len(differing)//2,'prepared':str(prepared),'prediction_sha256':receipt['frozen_prediction_sha256'],'new_environment_steps':0,'no_retraining_or_evaluation':True}
        dump(out/'COMPLETE.json',result);success=True;print(json.dumps(result,ensure_ascii=False),flush=True)
    except BaseException as exc:
        dump(out/'FAILED.json',{'error':repr(exc),'traceback':traceback.format_exc(),'new_environment_steps':0});traceback.print_exc()
    finally:
        dump(out/'checks.json',checks);dump(out/'runtime.json',{'wall_seconds':time.perf_counter()-start,'cpu_seconds':time.process_time()-cpu,'python':sys.version,'numpy':np.__version__,'new_training_steps':0,'new_evaluation_steps':0,'success':success})
    return 0 if success else 1

if __name__=='__main__': raise SystemExit(main())
