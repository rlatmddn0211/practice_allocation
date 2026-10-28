"""Zero-environment validation before the scarce real-step technical gate."""
import json
import traceback
from pathlib import Path
import numpy as np
from common import (ROOT,unique,frozen_inputs,config_for,load_state,fork_future,expected_order,
                    fixed_panel,case_bank,read_csv,checked,close_engine)
from telemetry import BaselineTelemetry
from practice_allocation.core import configure_runtime,fingerprint,file_sha256,source_hashes,write_json
from practice_allocation.environment import CostCounter
from practice_allocation.study_io import source_snapshot,read_json,IntegrityError

def main():
    out=unique(ROOT/'results','static');source_snapshot(out)
    checks=[];error=None;costs=CostCounter();engine=None
    def check(name,value,details=None):
        checks.append({'name':name,'passed':bool(value),'details':details})
        if not value:raise IntegrityError(name)
    try:
        for file in (out/'source_snapshot').glob('*.py'):
            compile(file.read_text(encoding='utf-8-sig'),str(file),'exec')
        check('all_python_compiles',True)
        p,states,jobs=frozen_inputs();configure_runtime(config_for(states[0]))
        for name,digest in p['critical_source_hashes'].items():
            check('unchanged_'+name,file_sha256(ROOT/name)==digest)
        check('budget_arithmetic',640000+4400000+1000000+10000==6050000)
        check('endpoint_baseline_rows',len(read_csv(ROOT/'inputs/baseline_rows.csv'))==2000)
        for state in states:
            engine=load_state(state,costs)
            before=engine.fingerprints();panel=fixed_panel(engine,state['parent'])
            check('panel_is_noninterfering_'+str(state['parent']),engine.fingerprints()==before)
            e=case_bank(state,'E50');t=case_bank(state,'T20')
            check('evaluation_sizes_'+str(state['parent']),len(e)==200 and len(t)==80)
            observer=BaselineTelemetry(out/('probe_'+str(state['parent'])),
                episode_metadata=read_json(checked(state['episode_labels'])),fixed_panel=panel,enabled=True,
                probe_seed=state.get('panel_seed',640202),metadata={'zero_step_static':True})
            observer.attach(engine)
            replay=engine.model.replay_buffer;n=replay.size()
            birth=replay.birth_steps[:n];tasks=replay.observations[:n,0,-4:].argmax(1)
            descriptions=observer._sample_description(birth,tasks,208000)
            check('historical_labels_join_'+str(state['parent']),len(descriptions['labels'])==100000)
            check('initial_policy_probe_preserves_fullstate_'+str(state['parent']),engine.fingerprints()==before)
            observer.close()
            for job in [x for x in jobs if x['parent']==state['parent']]:
                # Restore the original collector and RNG between future-plan dry checks.
                close_engine(engine);engine=load_state(state,costs)
                fork_future(engine,job);order=expected_order(engine)
                check('planned_counts_'+job['id'],[order.count(i)*500 for i in range(4)]==
                      ([8000]*4 if job['condition']=='dose25' else [4000,4000,4000,20000]))
            close_engine(engine);engine=None
        check('zero_environment_execution',costs.environment_steps==0 and costs.train_iterations==0)
    except BaseException as exc:
        error={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
        traceback.print_exc()
    finally:
        close_engine(engine)
        write_json(out/'checks.json',checks)
        write_json(out/'summary.json',{'status':'failed' if error else 'passed','checks':len(checks),
            'failed_checks':[x for x in checks if not x['passed']],'error':error,'costs':costs.snapshot(),
            'source_hashes':source_hashes(),'scope':'static/code/full-restore probe validation only; no scientific effect'})
    print(json.dumps({'run':str(out),'passed':error is None,'costs':costs.snapshot()}),flush=True)
    return 1 if error else 0

if __name__=='__main__':raise SystemExit(main())
