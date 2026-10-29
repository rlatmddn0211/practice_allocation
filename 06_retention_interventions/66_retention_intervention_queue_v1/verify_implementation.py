"""Prospective technical gate only; never tune treatment using evaluation results."""
import argparse
import copy
import json
import pickle
import time
import traceback
from pathlib import Path
import numpy as np
from common import (ROOT,TECH_CAP,unique,reference,checked,frozen_inputs,config_for,load_state,
                    fork_future,fixed_panel,case_bank,close_engine,read_csv,expected_order,reserve)
from retention_memory import build_memories
from retention_learning import attach_intervention
from baseline_evaluation import evaluate
from telemetry import BaselineTelemetry,BaselineEngine
from practice_allocation.core import (capture_rng,fingerprint,configure_runtime,source_hashes,
                                     derived_seed,write_json,runtime_manifest,utc_now)
from practice_allocation.environment import CostCounter
from practice_allocation.study_io import read_json,source_snapshot,save_portable,load_portable,IntegrityError

def main():
    ap=argparse.ArgumentParser();ap.parse_args()
    previous=sum(read_json(p)['costs']['environment_steps'] for p in (ROOT/'results').glob('*_technical_*/costs.json'))
    out=unique(ROOT/'results','technical');source_snapshot(out);source=source_hashes()
    costs=CostCounter();checks=[];engine=None;controller=None;observer=None;error=None
    started=time.perf_counter();panels={};certified_memories={}
    def check(label,value,detail=None):
        checks.append({'label':label,'passed':bool(value),'detail':detail})
        write_json(out/('check_'+str(len(checks)).zfill(4)+'.json'),checks[-1])
        if not value:raise IntegrityError(label)
    def cleanup():
        nonlocal engine,controller,observer
        if observer is not None:observer.close();observer=None
        if controller is not None:controller.close();controller=None
        close_engine(engine);engine=None
    def make(state,job,label,arm=None,enabled=True,coefficient=None,resume=None,bare=False):
        nonlocal engine,controller,observer
        if resume is None:
            engine=load_state(state,costs,out);fork_future(engine,job)
        else:engine=load_portable(resume['checkpoint'],config_for(state),costs,BaselineEngine)
        cfg={**p['retention'],'memory_seed':derived_seed(660202,6601,state['parent'])}
        if coefficient is not None:cfg['kl_coefficient']=coefficient
        memory=build_memories(engine,read_json(checked(state['episode_labels'])),state['parent'],cfg) if resume is None else resume['memory']
        if not bare:
            controller=attach_intervention(engine,arm or job['arm'],memory,cfg,
                    derived_seed(job['root_seed'],6602),out/label,state=None if resume is None else resume['retention'])
        observer=BaselineTelemetry(out/label,episode_metadata=read_json(checked(state['episode_labels'])),
            fixed_panel=panel_cache[state['parent']],enabled=enabled,
            probe_seed=derived_seed(640202,6402,state['parent']),metadata={**job,'technical':True})
        if resume is not None:observer.load_state_dict(resume['telemetry'])
        observer.attach(engine)
        return memory
    def trace(n,label):
        reserve(costs,n,TECH_CAP-previous);values=[]
        for _ in range(n):
            record=engine.step()
            # Numerical equivalence compares behavior/sampling and the complete final state;
            # treatment-only diagnostic fields are not scientific outcomes.
            values.append(fingerprint({k:v for k,v in record.items() if k!='losses'}))
        write_json(out/(label+'_trace.json'),values)
        return values
    panel_cache={}
    try:
        p,states,jobs=frozen_inputs()
        check('at_least_15000_technical_steps_available',previous+15000<=TECH_CAP,{'previous':previous})
        config=config_for(states[0]);configure_runtime(config)
        write_json(out/'runtime.json',runtime_manifest(config,'retention_intervention_integrity'))
        for file in (out/'source_snapshot').rglob('*.py'):compile(file.read_text(encoding='utf-8-sig'),str(file),'exec')
        check('all_source_compiles',True)
        for state in states:
            engine=load_state(state,costs);original=engine.fingerprints()
            panel=fixed_panel(engine,state['parent']);panel_cache[state['parent']]=panel
            panels[str(state['parent'])]={'fingerprint':panel['fingerprint']}
            cfg={**p['retention'],'memory_seed':derived_seed(660202,6601,state['parent'])}
            before=fingerprint(capture_rng())
            memory=build_memories(engine,read_json(checked(state['episode_labels'])),state['parent'],cfg)
            check('memory_rng_isolated_'+str(state['parent']),fingerprint(capture_rng())==before)
            check('memory_creation_fullstate_unchanged_'+str(state['parent']),engine.fingerprints()==original)
            check('matched_memory_size_'+str(state['parent']),len(memory['general']['observations'])==len(memory['success']['observations'])>0)
            certified_memories[str(state['parent'])]={'general':memory['general']['provenance'],
                        'success':memory['success']['provenance'],'support':memory['support']}
            cleanup()
            for job in [j for j in jobs if j['parent']==state['parent']]:
                engine=load_state(state,costs)
                check('exact_original_S_'+job['id'],engine.fingerprints()==original)
                fork_future(engine,job);order=expected_order(engine)
                check('BP625_schedule_'+job['id'],[order.count(t) for t in range(4)]==[8,8,8,40])
                cleanup()
        check('all_restore_and_memory_checks_zero_environment',costs.environment_steps==0)
        write_json(out/'certified_panels.json',panels);write_json(out/'certified_memories.json',certified_memories)
        s=states[0];job=next(j for j in jobs if j['parent']==s['parent'] and j['future']==1 and j['arm']=='A')
        make(s,job,'original_unwrapped_SAC',arm='A',bare=True)
        original_trace=trace(1000,'original_unwrapped_SAC');original_final=engine.fingerprints();cleanup()
        make(s,job,'stock_A',arm='A');a=trace(1000,'stock_A');af=engine.fingerprints();cleanup()
        check('A_dispatch_is_original_SAC_behavior',a==original_trace)
        check('A_dispatch_is_original_SAC_fullstate',af==original_final)
        make(s,job,'C_lambda_zero',arm='C',coefficient=0);zero=trace(1000,'C_lambda_zero')
        check('zero_lambda_behavior_and_sampling_exact',a==zero)
        check('zero_lambda_full_state_exact',engine.fingerprints()==af);cleanup()
        for arm in 'BCD':
            results=[];finals=[];retentions=[]
            for enabled in (True,False):
                label=arm+('_on' if enabled else '_off')
                make(s,job,label,arm=arm,enabled=enabled)
                results.append(trace(1000,label));finals.append(engine.fingerprints())
                retentions.append(fingerprint(controller.state_dict()))
                check(label+'_actor_learning_rate',all(abs(g['lr']-(1.5e-4 if arm=='B' else 3e-4))<1e-12 for g in engine.model.actor.optimizer.param_groups))
                check(label+'_critic_learning_rate',all(abs(g['lr']-3e-4)<1e-12 for g in engine.model.critic.optimizer.param_groups))
                check(label+'_entropy_learning_rate',all(abs(g['lr']-3e-4)<1e-12 for g in engine.model.ent_coef_optimizer.param_groups))
                cleanup()
            check(arm+'_logging_behavior_exact',results[0]==results[1])
            check(arm+'_logging_fullstate_exact',finals[0]==finals[1])
            check(arm+'_logging_retention_state_exact',retentions[0]==retentions[1])
            mem=make(s,job,arm+'_split_a',arm=arm);first=trace(500,arm+'_split_a')
            with observer.suspended(),controller.suspended():
                cp=save_portable(engine,out/(arm+'_resume_checkpoint'))
                resume={'checkpoint':cp,'memory':mem,'retention':controller.state_dict(),'telemetry':observer.state_dict()}
                with (out/(arm+'_resume_sidecar.pkl')).open('xb') as f:pickle.dump(resume,f,protocol=pickle.HIGHEST_PROTOCOL)
            cleanup();make(s,job,arm+'_split_b',arm=arm,resume=resume);second=trace(500,arm+'_split_b')
            check(arm+'_lossless_resume_trace',results[0]==first+second)
            check(arm+'_lossless_resume_fullstate',finals[0]==engine.fingerprints())
            check(arm+'_lossless_resume_retention',retentions[0]==fingerprint(controller.state_dict()))
            cleanup()
        # Evaluation must preserve both ordinary learner and private intervention state.
        make(s,job,'evaluation_isolation',arm='D')
        bank=[next(r for r in case_bank(s,'E50') if r['task']==task) for task in ('DO','DC','PU','BP')]
        before=engine.fingerprints();r_before=fingerprint(controller.state_dict())
        evaluate(engine,bank,costs,out/'known_S.csv',{'id':'technical','parent':s['parent'],'condition':'D','future':0,'relative_step':0},TECH_CAP-previous)
        check('evaluation_full_state_unchanged',before==engine.fingerprints())
        check('evaluation_retention_state_unchanged',r_before==fingerprint(controller.state_dict()))
        actual=read_csv(out/'known_S.csv')
        prior={(r['task'],int(r['episode_index'])):r for r in read_csv(ROOT/'inputs/baseline_rows.csv') if int(r['parent'])==s['parent'] and r['stage']=='S'}
        for row in actual:
            r=prior[row['task'],int(row['episode_index'])]
            check('evaluation_reused_S_exact_'+row['task'],all(str(row[k])==str(r[k]) for k in ('success','seed','length','initial_state_hash')) and float(row['return'])==float(r['return']))
        cleanup()
        check('technical_training_contract',costs.train_iterations==12000)
        check('technical_cumulative_cap',previous+costs.environment_steps<=TECH_CAP)
        check('source_unchanged',source==source_hashes())
    except BaseException as exc:
        error={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
        write_json(out/'error.json',error);traceback.print_exc()
    finally:
        try:cleanup()
        except BaseException as exc:
            if error is None:error={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
            write_json(out/'cleanup_error.json',str(exc))
        cost={'status':'failed' if error else 'completed','costs':costs.snapshot(),
              'previous_technical_environment_steps':previous,'wall_seconds':time.perf_counter()-started}
        write_json(out/'costs.json',cost)
        summary={'status':'failed' if error else 'passed','checks':len(checks),
            'failed_checks':[c for c in checks if not c['passed']], 'error':error,
            'source_hashes':source,'costs':costs.snapshot(),
            'total_technical_environment_steps_all_attempts':previous+costs.environment_steps,
            'scientific_effect_test':False}
        write_json(out/'summary.json',summary)
    if error is None:write_json(out/'VERIFIED.json',{'summary':reference(out/'summary.json'),
        'panels':reference(out/'certified_panels.json'),'memories':reference(out/'certified_memories.json'),
        'source_hashes':source,'created_at':utc_now()})
    print(json.dumps({'run':str(out),'passed':error is None,'costs':costs.snapshot()}),flush=True)
    return 1 if error else 0
if __name__=='__main__':raise SystemExit(main())
