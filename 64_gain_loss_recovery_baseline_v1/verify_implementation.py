"""Cumulative <=10k real-step restoration/instrumentation/resume/evaluation gate."""
import argparse
import json
import pickle
import time
import traceback
from pathlib import Path
import numpy as np
from common import (ROOT,TECH_CAP,unique,reference,checked,frozen_inputs,config_for,load_state,
                    fork_future,expected_order,fixed_panel,case_bank,read_csv,reserve,
                    verify_input_files,close_engine)
from baseline_evaluation import evaluate
from telemetry import BaselineTelemetry,BaselineEngine
from practice_allocation.core import configure_runtime,source_hashes,runtime_manifest,fingerprint,write_json,utc_now,derived_seed
from practice_allocation.environment import CostCounter
from practice_allocation.study_io import IntegrityError,source_snapshot,read_json,save_portable,load_portable

def main():
    out=unique(ROOT/'results','technical');source_snapshot(out)
    checks=[];costs=CostCounter();engine=None;error=None
    started=time.perf_counter();cpu=time.process_time()
    previous=sum(read_json(p)['costs']['environment_steps'] for p in (ROOT/'results').glob('*_technical_*/costs.json'))
    source_state=source_hashes()
    panel_cache={}

    def check(name,passed,details=None):
        row={'name':name,'passed':bool(passed),'details':details};checks.append(row)
        with (out/'checks.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(row,default=str)+'\n')
        if not passed:raise IntegrityError(name)

    def event(name):
        print(name,flush=True)
        with (out/'progress.jsonl').open('a',encoding='utf-8') as f:
            f.write(json.dumps({'time':utc_now(),'event':name,'costs':costs.snapshot()})+'\n')

    def attach(e,state,job,label,enabled,resume_state=None):
        observer=BaselineTelemetry(out/label,episode_metadata=read_json(checked(state['episode_labels'])),
                    fixed_panel=panel_cache[state['parent']],enabled=enabled,
                    probe_seed=derived_seed(640202,6402,state['parent']),metadata={**job,'source_step':208000})
        if resume_state is not None:observer.load_state_dict(resume_state)
        observer.attach(e);return observer

    def trace(e,steps,label):
        reserve(costs,steps,TECH_CAP-previous)
        values=[]
        for _ in range(steps):values.append(fingerprint(e.step()))
        write_json(out/(label+'_trace.json'),values)
        return values

    try:
        for src in (out/'source_snapshot').rglob('*.py'):
            compile(src.read_text(encoding='utf-8-sig'),str(src),'exec')
        check('source_compile',True)
        p,states,jobs=frozen_inputs()
        check('technical_9000_reservation_available',previous+9000<=TECH_CAP,{'previous':previous,'first_run_max':9000})
        config=config_for(states[0]);configure_runtime(config)
        write_json(out/'runtime.json',{**runtime_manifest(config,'baseline_integrity'),'execution_version':ROOT.name})
        originals={};panels={};forks=[]
        # All twenty jobs restore originals, but these checks consume no environment transitions.
        for state in states:
            engine=load_state(state,costs)
            originals[state['parent']]=engine.fingerprints()
            replay=engine.model.replay_buffer;n=replay.size()
            birth=replay.birth_steps[:n]
            check('replay_birth_coverage_'+str(state['parent']),
                  n==100000 and len(np.unique(birth))==100000 and int(birth.min())==108001 and int(birth.max())==208000)
            panel=fixed_panel(engine,state['parent']);panels[str(state['parent'])]={'fingerprint':panel['fingerprint'],
                'observations':256,'birth_steps':panel['birth_steps'].tolist(),'selection_seed':panel['selection_seed']}
            panel_cache[state['parent']]=panel
            check('fixed_panel_task_support_'+str(state['parent']),np.bincount(panel['task_indices'],minlength=4).tolist()==[64]*4)
            selected=case_bank(state,'E50');tracked=case_bank(state,'T20')
            check('nested_case_sets_'+str(state['parent']),len(selected)==200 and len(tracked)==80 and
                  {(x['task'],x['episode_index']) for x in tracked}<={(x['task'],x['episode_index']) for x in selected})
            close_engine(engine);engine=None
            for job in [j for j in jobs if j['parent']==state['parent']]:
                engine=load_state(state,costs)
                check('same_original_S_'+job['id'],engine.fingerprints()==originals[state['parent']])
                fork=fork_future(engine,job);order=expected_order(engine)
                wanted=[16]*4 if job['condition']=='dose25' else [8,8,8,40]
                check('future_schedule_quotas_'+job['id'],[order.count(t) for t in range(4)]==wanted,
                      {'episode_counts':wanted,'first_4k_actual':[order[:8].count(t)*500 for t in range(4)]})
                forks.append({'id':job['id'],**fork,'episode_order':order})
                close_engine(engine);engine=None
            event('all_forks_restored_'+str(state['parent']))
        check('all_restore_checks_zero_environment_steps',costs.environment_steps==0)
        write_json(out/'certified_panels.json',panels);write_json(out/'all_forks.json',forks)
        state=states[0];condition_results={}
        for condition in ('dose25','dose625'):
            job=next(j for j in jobs if j['parent']==state['parent'] and j['condition']==condition and j['future']==1)
            # Logging on/off must retain exact actions, samples, updates, collector and RNG.
            traces=[];finals=[]
            for enabled in (True,False):
                label=condition+('_on' if enabled else '_off')
                engine=load_state(state,costs,out);fork_future(engine,job)
                observer=attach(engine,state,job,label,enabled)
                traces.append(trace(engine,1000,label));finals.append(engine.fingerprints())
                close_engine(engine);engine=None
            check(condition+'_logging_trace_exact',traces[0]==traces[1])
            check(condition+'_logging_full_state_exact',finals[0]==finals[1])
            # Separate restore again: a lossless save/reload at 500 steps must not change the next 500.
            engine=load_state(state,costs,out);fork_future(engine,job)
            observer=attach(engine,state,job,condition+'_split_a',True)
            first=trace(engine,500,condition+'_split_a')
            with observer.suspended(): cp=save_portable(engine,out/(condition+'_resume_checkpoint'))
            metadata=observer.state_dict() if hasattr(observer,'state_dict') else None
            if metadata is not None:
                with (out/(condition+'_telemetry_state.pkl')).open('xb') as f:pickle.dump(metadata,f,protocol=pickle.HIGHEST_PROTOCOL)
            close_engine(engine);engine=None
            engine=load_portable(cp,config,costs,BaselineEngine)
            observer=attach(engine,state,job,condition+'_split_b',True,resume_state=metadata)
            second=trace(engine,500,condition+'_split_b')
            check(condition+'_resume_trace_exact',traces[0]==first+second)
            check(condition+'_resume_full_state_exact',finals[0]==engine.fingerprints())
            condition_results[condition]={'trace_first_500':traces[0][:500],'trace_full':traces[0]}
            close_engine(engine);engine=None;event(condition+'_logging_and_resume_passed')
        # N2 must be an independently rerandomized future, not a duplicate of N1.
        job=next(j for j in jobs if j['parent']==state['parent'] and j['condition']=='dose625' and j['future']==2)
        engine=load_state(state,costs,out);fork_future(engine,job);attach(engine,state,job,'dose625_N2',True)
        second=trace(engine,500,'dose625_N2')
        check('new_futures_not_duplicate',second!=condition_results['dose625']['trace_first_500'])
        close_engine(engine);engine=None
        check('technical_training_cost_exact',costs.train_iterations==6500)
        # Same known policy/cases, no newly trained future is used for this integrity test.
        engine=load_state(state,costs)
        bank=case_bank(state,'E50');selected=[]
        for task in ('DO','DC','PU','BP'):selected.append(next(r for r in bank if r['task']==task))
        before=engine.fingerprints()
        evaluate(engine,selected,costs,out/'known_S.csv',{'id':'technical_known_S','parent':state['parent'],
                      'condition':'STOP','future':0,'relative_step':0},TECH_CAP-previous)
        actual=read_csv(out/'known_S.csv')
        baseline=read_csv(ROOT/'inputs/baseline_rows.csv')
        old={(r['task'],int(r['episode_index'])):r for r in baseline if int(r['parent'])==state['parent'] and r['stage']=='S'}
        for row in actual:
            ref=old[row['task'],int(row['episode_index'])]
            for field in ('seed','initial_state_hash','success','length'):
                check('known_S_'+row['task']+'_'+field,str(row[field])==str(ref[field]))
            check('known_S_'+row['task']+'_return',float(row['return'])==float(ref['return']))
        check('known_evaluation_preserves_full_state',engine.fingerprints()==before)
        # Repeat a preselected exact case to check deterministic replay and log identity.
        evaluate(engine,[selected[0]],costs,out/'known_S_repeat.csv',{'id':'technical_known_S_repeat','parent':state['parent'],
                      'condition':'STOP','future':0,'relative_step':0},TECH_CAP-previous)
        repeated=read_csv(out/'known_S_repeat.csv')[0]
        check('fixed_policy_case_repeat_exact',all(repeated[k]==actual[0][k] for k in ('success','length','return','initial_state_hash','seed')))
        close_engine(engine);engine=None
        for state in states:verify_input_files(state)
        check('technical_cap_preserved',previous+costs.environment_steps<=TECH_CAP)
        check('source_unchanged_during_gate',source_hashes()==source_state)
        event('technical_gate_passed')
    except BaseException as exc:
        error={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
        write_json(out/'error.json',error);traceback.print_exc()
    finally:
        try:close_engine(engine)
        except BaseException as exc:
            cleanup={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
            write_json(out/'cleanup_error.json',cleanup)
            if error is None:error=cleanup
        write_json(out/'costs.json',{'status':'failed' if error else 'completed','costs':costs.snapshot(),
                   'previous_technical_environment_steps':previous,'wall_seconds':time.perf_counter()-started,
                   'cpu_seconds':time.process_time()-cpu,'scientific_effect_test':False})
        summary={'status':'failed' if error else 'passed','checks':len(checks),'failed_checks':[c for c in checks if not c['passed']],
                 'source_hashes':source_hashes(),'costs':costs.snapshot(),'error':error,
                 'total_technical_environment_steps_all_attempts':previous+costs.environment_steps}
        write_json(out/'summary.json',summary)
    if not error:
        write_json(out/'VERIFIED.json',{'summary':reference(out/'summary.json'),'panels':reference(out/'certified_panels.json'),
                   'source_hashes':source_hashes(),'created_at':utc_now()})
    print(json.dumps({'run':str(out),'passed':error is None,'costs':costs.snapshot()}),flush=True)
    return 1 if error else 0

if __name__=='__main__':raise SystemExit(main())
