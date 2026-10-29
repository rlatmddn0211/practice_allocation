"""Schedule, exact checkpoint resume and evaluation-state integrity gates."""
import argparse
import json
import os
import time
import traceback
import uuid
from datetime import datetime,timezone
from pathlib import Path


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--parent',required=True);args=ap.parse_args()
    os.environ['PRACTICE_SUITE']='A';os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
    import numpy as np
    from dataclasses import replace
    from practice_allocation.core import ROOT,Config,AllocationSchedule,configure_runtime,write_json,derived_seed,runtime_manifest
    from practice_allocation.environment import CostCounter,TaskEpisode
    from practice_allocation.evaluation import evaluate_model
    from practice_allocation.study_io import load_portable,save_portable,source_snapshot
    from practice_allocation.schedules import CONDITIONS,PAIR_INDICES,quotas,full_plan
    out=ROOT/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_verify_implementation_')+uuid.uuid4().hex[:8]);out.mkdir(parents=True)
    source_snapshot(out);print(str(out),flush=True);checks=[];costs=CostCounter();start=time.perf_counter();cpu=time.process_time();engine=None
    def check(name,value):
        checks.append({'name':name,'passed':bool(value)})
        if not value:raise AssertionError(name)
    try:
        for suite,(i,j) in PAIR_INDICES.items():
            for cond in CONDITIONS:
                for seed in [3801,3802,3803]:
                    plan=full_plan(cond,seed,suite)
                    check('80 episodes '+str((suite,cond,seed)),len(plan)==80)
                    if cond.startswith('dose'):
                        q={'dose25':(20,20),'dose4375':(35,15),'dose625':(50,10),'dose8125':(65,5)}[cond]
                        expected=[q[1]]*4;expected[i]=q[0]
                    else:expected=[10]*4;expected[i]=expected[j]=30
                    check('exact totals '+str((suite,cond,seed)),np.bincount(plan,minlength=4).tolist()==expected)
        for cond in CONDITIONS:
            sched=AllocationSchedule(cond,3801);before=[sched.next_task() for _ in range(40)];state=sched.state()
            after=[sched.next_task() for _ in range(40)];loaded=AllocationSchedule.from_state(state)
            check('schedule resume '+cond,after==[loaded.next_task() for _ in range(40)])
            check('schedule implementation agrees '+cond,before+after==full_plan(cond,3801,'A'))
        ref=json.loads(Path(args.parent).read_text(encoding='utf-8'))
        config=replace(Config.load(ROOT/'configs/learner.json'),seed=12)
        configure_runtime(config);write_json(out/'runtime.json',runtime_manifest(config,'F08 technical verification'))
        engine=load_portable(ref,config,costs);engine.start_branch('dose4375',328099)
        engine.train_steps(500,'prefix',out/'prefix_metrics.csv',trace=True,episodes_path=out/'prefix_episodes.csv')
        checkpoint=save_portable(engine,out/'checkpoint_500')
        a=engine.train_steps(500,'uninterrupted',out/'uninterrupted_metrics.csv',trace=True,episodes_path=out/'uninterrupted_episodes.csv')
        expected=engine.fingerprints();engine.close()
        engine=load_portable(checkpoint,config,costs)
        b=engine.train_steps(500,'resumed',out/'resumed_metrics.csv',trace=True,episodes_path=out/'resumed_episodes.csv')
        check('resume exact transition/update trace',a['trace_sha256']==b['trace_sha256'])
        check('resume exact full learner/replay/collector/RNG',engine.fingerprints()==expected)
        before=engine.fingerprints();bank=[]
        for task in range(4):
            seed=derived_seed(328099,100,task,0)
            with TaskEpisode(task,seed,costs) as ep:bank.append({'task_index':task,'seed':seed,'initial_state_hash':ep.initial_state_hash,'bank':'technical','task':('DO','DC','WO','WC')[task],'episode_index':0})
        evaluate_model(engine.model,bank,costs,out/'evaluation.csv','technical',context='technical smoke')
        check('evaluation preserves full state',engine.fingerprints()==before)
        summary={'status':'completed','scientific_evidence':False,'resume_exact':True}
    except BaseException:
        summary={'status':'failed','traceback':traceback.format_exc(),'scientific_evidence':False};traceback.print_exc()
    finally:
        if engine is not None:engine.close()
        write_json(out/'checks.json',checks)
        summary.update(costs=costs.snapshot(),wall_seconds=time.perf_counter()-start,cpu_seconds=time.process_time()-cpu,
                       checks_passed=sum(c['passed'] for c in checks),checks_failed=sum(not c['passed'] for c in checks))
        write_json(out/'summary.json',summary);print(json.dumps(summary,indent=2),flush=True)
    return 0 if summary['status']=='completed' else 1


if __name__=='__main__':raise SystemExit(main())
