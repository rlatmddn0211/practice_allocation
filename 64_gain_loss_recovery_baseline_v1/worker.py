"""One approved 32k baseline path, longitudinal scoring, immutable full checkpoints."""
import argparse
import json
import pickle
import time
import traceback
from pathlib import Path
import numpy as np
from common import (
    ROOT,atomic,reference,frozen_inputs,load_state,config_for,fork_future,expected_order,
    fixed_panel,case_bank,read_csv,checked,verify_input_files,close_engine)
from baseline_evaluation import evaluate
from telemetry import BaselineTelemetry
from practice_allocation.core import configure_runtime,source_hashes,runtime_manifest,write_json,utc_now,fingerprint,derived_seed
from practice_allocation.environment import CostCounter
from practice_allocation.study_io import IntegrityError,source_snapshot,save_portable,read_json

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--request',required=True);a=ap.parse_args()
    q=read_json(a.request);out=Path(q['output'])
    if (out/'runtime.json').exists() or (out/'costs.json').exists():raise IntegrityError('Attempt cannot be reused')
    source_snapshot(out)
    costs=CostCounter();engine=None;observer=None;error=None
    started=time.perf_counter();cpu=time.process_time()
    train_steps=0;eval_steps=0;phase='restoration';checkpoints=[];evaluations=[]

    def progress(event,**extra):
        with (out/'progress.jsonl').open('a',encoding='utf-8') as f:
            f.write(json.dumps({'time':utc_now(),'event':event,'costs':costs.snapshot(),
                                'absolute_step':engine.model.num_timesteps if engine else None,**extra})+'\n')
        print(event,extra,flush=True)

    try:
        p,states,jobs=frozen_inputs();job=q['job'];state=states[job['state_index']]
        if job not in jobs or q['source_hashes']!=source_hashes():raise IntegrityError('Frozen job/source changed')
        config=config_for(state);configure_runtime(config)
        write_json(out/'runtime.json',{**runtime_manifest(config,'gain_loss_recovery_baseline'),
                                     'execution_version':ROOT.name,'job':job})
        engine=load_state(state,costs,out)
        write_json(out/'research_start_integrity.json',{'state':state,'full_fingerprints':engine.fingerprints(),
                  'environment_steps_before_fork':costs.environment_steps,'restored_original_S_again':True})
        if costs.environment_steps:raise IntegrityError('Technical rollout leaked into research')
        write_json(out/'fork_integrity.json',fork_future(engine,job))
        expected=expected_order(engine)
        write_json(out/'expected_episode_order.json',expected)
        panel=fixed_panel(engine,state['parent'])
        if panel['fingerprint']!=q['certified_panel_fingerprint']:
            raise IntegrityError('Training-only fixed panel changed')
        np.savez_compressed(out/'training_probe_panel.npz',**{k:v for k,v in panel.items() if isinstance(v,np.ndarray)})
        write_json(out/'training_probe_panel.json',{k:v.tolist() if isinstance(v,np.ndarray) else v for k,v in panel.items() if k!='observations'})
        episode_ref=state.get('episode_labels')
        episode_metadata=read_json(checked(episode_ref)) if episode_ref else []
        observer=BaselineTelemetry(out,episode_metadata=episode_metadata,fixed_panel=panel,
                    enabled=True,probe_seed=derived_seed(640202,6402,state['parent']),metadata={**job,'source_step':208000})
        observer.attach(engine)
        before_counts=engine.collected_steps.copy();before_updates=engine.model._n_updates
        phase='training';progress('research_training_started',condition=job['condition'],future=job['future'])
        actual_order=[]
        for relative in (4000,8000,16000,32000):
            target=208000+relative
            while engine.model.num_timesteps<target:
                if costs.environment_steps+1>q['environment_cap']:raise IntegrityError('Worker cap exhausted')
                fresh=engine.at_boundary
                before_physics=costs.environment_steps
                try:
                    record=engine.step()
                finally:
                    train_steps+=costs.environment_steps-before_physics
                if fresh:actual_order.append(record['task'])
                if train_steps%1000==0:progress('training',relative_step=train_steps)
            if not engine.at_boundary:raise IntegrityError('Full checkpoint must be at completed-episode boundary')
            with observer.suspended():
                cp=save_portable(engine,out/'checkpoints'/('absolute_'+str(target)))
                telemetry_path=Path(cp['path'])/'telemetry_state.pkl'
                with telemetry_path.open('xb') as f:
                    pickle.dump(observer.state_dict(),f,protocol=pickle.HIGHEST_PROTOCOL)
                telemetry_ref=reference(telemetry_path)
                write_json(Path(cp['path'])/'telemetry_state_ref.json',telemetry_ref)
            checkpoints.append({'relative_step':relative,'absolute_step':target,**cp,'telemetry_state':telemetry_ref})
            write_json(out/('checkpoint_'+str(target)+'.json'),checkpoints[-1])
            # All policy probes remain training-only; scoring is never passed to the learner.
            phase='evaluation';bank=case_bank(state,'E50' if relative==32000 else 'T20')
            if len(bank)!=(200 if relative==32000 else 80):raise IntegrityError('Evaluation set size changed')
            summary=evaluate(engine,bank,costs,out/'evaluation_episodes.csv',
                    {'id':job['id'],'parent':state['parent'],'condition':job['condition'],
                     'future':job['future'],'relative_step':relative},q['environment_cap'])
            eval_steps+=summary['environment_steps'];evaluations.append({'relative_step':relative,**summary})
            progress('checkpoint_evaluation_complete',relative_step=relative,cases=summary['episodes'])
            phase='training'
        counts=(engine.collected_steps-before_counts).tolist()
        wanted=[8000]*4 if job['condition']=='dose25' else [4000,4000,4000,20000]
        if actual_order!=expected or counts!=wanted:raise IntegrityError('Episode schedule or 32k quotas changed')
        if train_steps!=32000 or engine.model._n_updates-before_updates!=32000 or costs.train_iterations!=32000:
            raise IntegrityError('Exact training/update contract violated')
        if len(read_csv(out/'evaluation_episodes.csv'))!=440:raise IntegrityError('Longitudinal case coverage incomplete')
        observer.close();observer=None
        verify_input_files(state);frozen_inputs()
        scores=evaluations[-1]['success_by_task']
        write_json(out/'training_summary.json',{'training_steps':train_steps,'SAC_updates':costs.train_iterations,
                   'collected_by_task':dict(zip(('DO','DC','PU','BP'),counts)),
                   'exact_episode_order':True,'checkpoints':checkpoints})
        result={'id':job['id'],'status':'completed','state':state,'parent':state['parent'],
                'condition':job['condition'],'future':job['future'],'job':job,
                'training_steps':train_steps,'evaluation_steps':eval_steps,
                'episodes':reference(out/'evaluation_episodes.csv'),'checkpoints':checkpoints,
                'evaluations':evaluations,'success_by_task':scores,'macro_success':sum(scores.values())/4,
                'telemetry_directory':str(out),'scientific_status':'completed development path; full paired analysis pending'}
        write_json(out/'result.json',result);progress('completed')
    except BaseException as exc:
        error={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
        write_json(out/'error.json',error);traceback.print_exc()
    finally:
        cleanup_errors=[]
        for label,cleanup in [('observer',lambda:observer.close() if observer is not None else None),
                              ('engine',lambda:close_engine(engine))]:
            try:cleanup()
            except BaseException as exc:
                cleanup_errors.append({'component':label,'type':type(exc).__name__,'message':str(exc),
                                       'traceback':traceback.format_exc()})
        if cleanup_errors:
            write_json(out/'cleanup_errors.json',cleanup_errors)
            if error is None:
                error={'type':'IntegrityError','message':'Cleanup failed; see retained cleanup_errors.json'}
                if not (out/'error.json').exists():write_json(out/'error.json',error)
        # Account incomplete physics steps from the counter rather than nominal job lengths.
        eval_steps=costs.environment_steps-train_steps
        write_json(out/'costs.json',{'status':'failed' if error else 'completed','costs':costs.snapshot(),
                  'training_steps':train_steps,'evaluation_steps':eval_steps,'phase_at_exit':phase,
                  'cleanup_errors':cleanup_errors,
                  'wall_seconds':time.perf_counter()-started,'cpu_seconds':time.process_time()-cpu})
    return 1 if error else 0

if __name__=='__main__':raise SystemExit(main())
