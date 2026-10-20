"""Scientific bookkeeping, adversarial selector checks and exact real-SAC recovery."""
import ast
import json
import os
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
os.environ['PRACTICE_SUITE']='B'
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
from dataclasses import replace
import numpy as np
from practice_allocation.core import (ROOT, Config, AllocationSchedule, configure_runtime, write_json,
    derived_seed, runtime_manifest, file_sha256, source_hashes)
from practice_allocation.environment import CostCounter, TaskEpisode
from practice_allocation.evaluation import evaluate_model
from practice_allocation.study_io import AuditEngine, load_portable, save_portable, source_snapshot
from practice_allocation.schedules import full_plan
from analyze import CONDITIONS, choice_records, gate


def main():
    out=ROOT/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_verify_')+uuid.uuid4().hex[:8]); out.mkdir(parents=True)
    source_snapshot(out); print(str(out),flush=True); checks=[]; costs=CostCounter(); engine=None; started=time.perf_counter()
    def check(name,passed):
        checks.append({'name':name,'passed':bool(passed)})
        if not passed: raise AssertionError(name)
    try:
        for path in list(ROOT.glob('*.py'))+list((ROOT/'practice_allocation').glob('*.py')):
            ast.parse(path.read_text(encoding='utf-8')); check('syntax '+path.name,True)
        for name in ('engine.py','learning.py','environment.py','evaluation.py'):
            check('unchanged validated learner '+name,file_sha256(ROOT/'practice_allocation'/name)==file_sha256(ROOT.parent/'32_dose_order_intervention_v1/practice_allocation'/name))
        protocol=json.loads((ROOT/'configs/research_protocol.json').read_text(encoding='utf-8'))['stage1']
        check('30 branches',len(protocol['original_seeds'])*len(protocol['continuation_labels'])*len(CONDITIONS)==30)
        check('2.2M train budget',5*200000+30*40000==protocol['training_environment_steps'])
        check('9.2M total upper bound',5*200000+30*40000+35*4*100*500==protocol['total_environment_steps_upper'])
        check('protocol copy exact',file_sha256(ROOT/'configs/research_protocol.json')==file_sha256(ROOT.parent/'41_selection_value_three_stage_protocol_v1/protocol.json'))
        for cond in CONDITIONS:
            order=full_plan(cond,4201,'B'); sched=AllocationSchedule(cond,4201)
            check('80 episodes '+cond,len(order)==80)
            expected=[10,10,10,50] if cond=='dose625' else [30,10,10,30]
            check('exact total quota '+cond,np.bincount(order,minlength=4).tolist()==expected)
            check('actual schedule '+cond,order==[sched.next_task() for _ in range(80)])
            for n in (8,16,40):
                sched=AllocationSchedule(cond,4201)
                for _ in range(n): sched.next_task()
                saved=sched.state(); loaded=AllocationSchedule.from_state(saved)
                check(f'schedule resume {cond} at {n*500}',[loaded.next_task() for _ in range(80-n)]==order[n:])
        parents=list(range(5)); repeats=[0,1]
        for scenario in ('constant_fixed','repeatable_heterogeneity','continuation_noise','half_noise'):
            scores={}; means={}
            for p in parents:
                for r in repeats:
                    for c in CONDITIONS:
                        vals=[]
                        for h in (0,1):
                            good='dose625' if scenario=='constant_fixed' else ('alternate4k' if p<2 else 'dose625')
                            if scenario=='continuation_noise': good='dose625' if r==0 else 'alternate4k'
                            if scenario=='half_noise': good='dose625' if h==0 else 'alternate4k'
                            value=75.0 if c==good else 50.0 if c!='mixture' else 40.0
                            scores[p,r,c,h]=value; vals.append(value)
                        means[p,r,c]=float(np.mean(vals))
            records=choice_records(scores,parents,repeats); result=gate(records,means,parents,repeats)
            check('scientific gate synthetic '+scenario,result['stage2_investment_gate_pass']==(scenario=='repeatable_heterogeneity'))
            check('all crossed folds '+scenario,len(records)==20 and all(x['score_half']!=x['selection_half'] for x in records))
        config=replace(Config.load(ROOT/'configs/learner.json'),seed=42998)
        configure_runtime(config); write_json(out/'runtime.json',runtime_manifest(config,'stage1 technical validation'))
        engine=AuditEngine(config,costs)
        engine.train_steps(4000,'uniform_warmup',out/'warmup.csv',episodes_path=out/'warmup_episodes.csv')
        check('warmup exact uniform',engine.collected_steps.tolist()==[1000]*4)
        check('warmup update count',engine.model._n_updates==3000)
        engine.start_branch('dose625',derived_seed(42901,420,42998))
        engine.train_steps(500,'prefix',out/'prefix.csv',episodes_path=out/'prefix_episodes.csv')
        checkpoint=save_portable(engine,out/'checkpoint')
        a=engine.train_steps(500,'uninterrupted',out/'uninterrupted.csv',trace=True,episodes_path=out/'uninterrupted_episodes.csv')
        fingerprints=engine.fingerprints(); engine.close()
        engine=load_portable(checkpoint,config,costs,AuditEngine)
        b=engine.train_steps(500,'resumed',out/'resumed.csv',trace=True,episodes_path=out/'resumed_episodes.csv')
        check('exact transition and replay sample trace',a['trace_sha256']==b['trace_sha256'])
        check('exact full state after recovery',engine.fingerprints()==fingerprints)
        bank=[]
        for t in range(4):
            seed=derived_seed(42998,777,t)
            with TaskEpisode(t,seed,costs) as ep:
                bank.append({'task_index':t,'seed':seed,'initial_state_hash':ep.initial_state_hash,'bank':'technical','task':('DO','DC','PU','BP')[t],'episode_index':0})
        before=engine.fingerprints(); evaluate_model(engine.model,bank,costs,out/'evaluation.csv','technical',context='technical')
        check('evaluation preserves learner replay collector and RNG',engine.fingerprints()==before)
        summary={'status':'completed','scientific_evidence':False}
    except BaseException:
        summary={'status':'failed','traceback':traceback.format_exc(),'scientific_evidence':False}; traceback.print_exc()
    finally:
        if engine is not None: engine.close()
        write_json(out/'checks.json',checks)
        summary.update(costs=costs.snapshot(),wall_seconds=time.perf_counter()-started,
                       checks_passed=sum(c['passed'] for c in checks),checks_failed=sum(not c['passed'] for c in checks))
        write_json(out/'summary.json',summary); print(json.dumps(summary,indent=2),flush=True)
    if summary['status']=='completed':
        from campaign import atomic,reference
        atomic(ROOT/'VERIFIED.json',reference(out/'summary.json'))
    return 0 if summary['status']=='completed' else 1


if __name__=='__main__': raise SystemExit(main())
