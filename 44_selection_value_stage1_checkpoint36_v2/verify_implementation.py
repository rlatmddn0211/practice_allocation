"""Scientific bookkeeping, adversarial selector checks and exact real-SAC recovery."""
import ast
import json
import os
import time
import traceback
import uuid
import itertools
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
from selection_rule import score_q,candidates,fit_rule,action,lopo


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
        check('protocol copy exact',file_sha256(ROOT/'configs/research_protocol.json')==file_sha256(ROOT.parent/'43_feedback_revised_selection_protocol_v1/protocol.json'))
        check('36k checkpoint present',protocol['branch_checkpoint_horizons']==[4000,8000,20000,36000,40000])
        for cond in CONDITIONS:
            order=full_plan(cond,4201,'B'); sched=AllocationSchedule(cond,4201)
            check('80 episodes '+cond,len(order)==80)
            expected=[10,10,10,50] if cond=='dose625' else [30,10,10,30]
            check('exact total quota '+cond,np.bincount(order,minlength=4).tolist()==expected)
            check('actual schedule '+cond,order==[sched.next_task() for _ in range(80)])
            for n in (8,16,40,72):
                sched=AllocationSchedule(cond,4201)
                for _ in range(n): sched.next_task()
                saved=sched.state(); loaded=AllocationSchedule.from_state(saved)
                check(f'schedule resume {cond} at {n*500}',[loaded.next_task() for _ in range(80-n)]==order[n:])
        parents=list(range(5)); repeats=[0,1]
        for scenario in ('constant_fixed','repeatable_heterogeneity','continuation_noise','half_noise','influential_fixed_donor'):
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
                            if scenario=='influential_fixed_donor':
                                value=({'dose625':0.,'alternate4k':100.,'mixture':0.} if p==0 else {'dose625':60.,'alternate4k':55.,'mixture':0.})[c]
                            scores[p,r,c,h]=value; vals.append(value)
                        means[p,r,c]=float(np.mean(vals))
            records=choice_records(scores,parents,repeats); result=gate(records,means,parents,repeats,scores)
            check('scientific gate synthetic '+scenario,result['stage2_investment_gate_pass']==(scenario=='repeatable_heterogeneity'))
            check('all crossed folds '+scenario,len(records)==20 and all(x['score_half']!=x['selection_half'] for x in records))
            if scenario=='influential_fixed_donor':
                check('old deletion sensitivity would pass',result['deletion_of_precomputed_gains_secondary_only']['vs_fixed_pp'][0]==5.0)
                check('full donor removal corrects baseline',result['full_parent_removal_refitted_means']['vs_fixed_pp'][0]==0.0)
        qs={score_q(dict(zip(('DO','DC','PU','BP'),counts))) for counts in itertools.product(range(3),repeat=4)}
        check('exactly thirteen diagnostic scores',qs==set(range(-6,7)))
        check('26 frozen distinct decision rules',len({tuple(action(rule,q) for q in range(-6,7)) for rule in candidates()})==26)
        rows=[{'original_seed':p,'continuation':r,'q':-6 if p<2 else 6,
               'keep_successes':100 if p<2 else 200,'switch_successes':200 if p<2 else 100} for p in range(5) for r in range(2)]
        predicted=lopo(rows)
        check('one-score rule learns state-dependent actions',sum(r['vs_keep_pp'] for r in predicted)>0 and sum(r['vs_switch_pp'] for r in predicted)>0)
        constant=[{**r,'keep_successes':144,'switch_successes':168} for r in rows]
        check('always-switch counterexample selects constant',fit_rule(constant)['id']=='always_switch')
        check('always-switch has zero information gain',all(r['vs_switch_pp']==0 for r in lopo(constant)))
        equal=[{**r,'keep_successes':200,'switch_successes':200} for r in rows]
        check('tie defaults to keep',fit_rule(equal)['id']=='always_keep')
        full_protocol=json.loads((ROOT/'configs/research_protocol.json').read_text(encoding='utf-8'))
        check('five equal operational budgets',len(full_protocol['stage3']['arms'])==5 and all(sum(a.values())==40000 for a in full_protocol['stage3']['arms'].values()))
        check('stage2 28k budget',10*28000+10*4000+20*4*100*500==full_protocol['stage2']['total_environment_steps_upper_if_keep_reused'])
        check('shared stage3 research cost',8000+32000+32000+4000==full_protocol['stage3']['sharing']['physical_operational_total_per_parent_continuation'])
        config=replace(Config.load(ROOT/'configs/learner.json'),seed=44998)
        configure_runtime(config); write_json(out/'runtime.json',runtime_manifest(config,'stage1 technical validation'))
        engine=AuditEngine(config,costs)
        engine.train_steps(4000,'uniform_warmup',out/'warmup.csv',episodes_path=out/'warmup_episodes.csv')
        check('warmup exact uniform',engine.collected_steps.tolist()==[1000]*4)
        check('warmup update count',engine.model._n_updates==3000)
        engine.start_branch('dose625',derived_seed(44901,420,44998))
        # 4k is exactly halfway through an 8k dose block, like the 36k boundary.
        engine.train_steps(4000,'prefix',out/'prefix.csv',episodes_path=out/'prefix_episodes.csv')
        checkpoint=save_portable(engine,out/'checkpoint')
        a=engine.train_steps(500,'uninterrupted',out/'uninterrupted.csv',trace=True,episodes_path=out/'uninterrupted_episodes.csv')
        fingerprints=engine.fingerprints(); engine.close()
        engine=load_portable(checkpoint,config,costs,AuditEngine)
        b=engine.train_steps(500,'resumed',out/'resumed.csv',trace=True,episodes_path=out/'resumed_episodes.csv')
        check('exact transition and replay sample trace',a['trace_sha256']==b['trace_sha256'])
        check('exact full state after recovery',engine.fingerprints()==fingerprints)
        bank=[]
        for t in range(4):
            seed=derived_seed(44998,777,t)
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
