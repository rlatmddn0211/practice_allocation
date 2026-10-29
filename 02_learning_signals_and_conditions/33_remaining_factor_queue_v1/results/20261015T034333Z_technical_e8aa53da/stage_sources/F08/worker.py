"""One immutable F08 job; durable queue owns retries and dependencies."""
import argparse
import csv
import json
import os
import time
import traceback
from pathlib import Path


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--request',required=True);args=ap.parse_args()
    q=json.loads(Path(args.request).read_text(encoding='utf-8-sig'))
    worker_lock=None
    if q.get('worker_lock'):
        import msvcrt
        worker_lock=Path(q['worker_lock']).open('a+b')
        if worker_lock.tell()==0:worker_lock.write(b'0');worker_lock.flush()
        while True:
            try:worker_lock.seek(0);msvcrt.locking(worker_lock.fileno(),msvcrt.LK_NBLCK,1);break
            except OSError:time.sleep(5)
    os.environ['PRACTICE_SUITE']=q['suite'];os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
    from dataclasses import replace
    import numpy as np
    from practice_allocation.core import ROOT,TASKS,Config,configure_runtime,runtime_manifest,write_json,source_hashes,derived_seed,fingerprint,utc_now
    from practice_allocation.environment import CostCounter
    from practice_allocation.evaluation import build_banks,evaluate_model
    from practice_allocation.learning import learning_state
    from practice_allocation.study_io import IntegrityError,AuditEngine,source_snapshot,load_portable,save_portable,load_banks,bank_sets
    from practice_allocation.schedules import full_plan
    out=Path(q['output']);out.mkdir(parents=True,exist_ok=True)
    if (out/'runtime.json').exists() or (out/'result.json').exists():raise RuntimeError('Immutable output cannot be reused')
    source_snapshot(out)
    config=replace(Config.load(ROOT/'configs/learner.json'),seed=q['original_seed'],bank_seed=q.get('bank_seed',328015),
                   diagnostic_bank_episodes_per_task=20,outcome_bank_episodes_per_task=100)
    if q.get('technical_smoke'):config=replace(config,diagnostic_bank_episodes_per_task=2,outcome_bank_episodes_per_task=2)
    costs=CostCounter();engine=None;error=None;result={};started=time.perf_counter();cpu=time.process_time()
    def progress(**fields):
        with (out/'progress.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps({'time':utc_now(),'costs':costs.snapshot(),**fields})+'\n')
    try:
        if source_hashes()!=q['source_hashes']:raise IntegrityError('Source differs from frozen plan')
        configure_runtime(config);write_json(out/'runtime.json',runtime_manifest(config,'F08'))
        if q['kind']=='bank':
            banks=build_banks(config,costs)
            forbidden=json.loads(Path(q['historical_forbidden']).read_text(encoding='utf-8'))
            if __import__('hashlib').sha256(Path(q['historical_forbidden']).read_bytes()).hexdigest()!=q['historical_forbidden_sha256']:raise IntegrityError('Historical set changed')
            sets=[set(forbidden[k]) for k in ['states','parameters','seeds']]
            extra=bank_sets(q.get('other_banks',[]))
            for a,b in zip(sets,extra):a.update(b)
            for rows in banks.values():
                for e in rows:
                    if e['initial_state_hash'] in sets[0] or e['task_parameter_hash'] in sets[1] or e['seed'] in sets[2]:raise IntegrityError('Bank overlap')
            write_json(out/'evaluation_banks.json',banks)
            from practice_allocation.core import file_sha256
            result={'bank':{'path':str(out/'evaluation_banks.json'),'sha256':file_sha256(out/'evaluation_banks.json')}}
        else:
            engine=load_portable(q['parent'],config,costs,AuditEngine)
            if q['kind']=='train':
                if engine.model.num_timesteps!=q['start_step']:raise IntegrityError('Wrong start step')
                if q['start_branch']:
                    before=fingerprint(learning_state(engine.model));engine.start_branch(q['condition'],q['continuation_rng_seed'])
                    if fingerprint(learning_state(engine.model))!=before:raise IntegrityError('Branch changed learned state')
                if engine.schedule.candidate!=q['condition']:raise IntegrityError('Schedule state does not match request')
                engine.forbidden=bank_sets(q['all_banks']);engine.audit_path=out/'training_reset_audit.csv'
                episode_start=(engine.model.num_timesteps-200000)//500
                expected_plan=full_plan(q['condition'],derived_seed(q['continuation_rng_seed'],10),q['suite'])
                before=engine.collected_steps.copy()
                for offset in range(0,q['steps'],1000):
                    count=min(1000,q['steps']-offset)
                    engine.train_steps(count,q['id'],out/'train_metrics.csv',episodes_path=out/'train_episodes.csv')
                    progress(step=engine.model.num_timesteps)
                with (out/'train_episodes.csv').open(encoding='utf-8') as f:episodes=list(csv.DictReader(f))
                actual=[TASKS.index(e['task']) for e in episodes]
                expected=expected_plan[episode_start:episode_start+q['steps']//500]
                if actual!=expected:raise IntegrityError('Exact episode order differs from planned schedule')
                counts=(engine.collected_steps-before).tolist()
                if counts!=(np.bincount(expected,minlength=4)*500).tolist():raise IntegrityError('Collection quota mismatch')
                if costs.train_iterations!=q['steps'] or costs.environment_steps!=q['steps']:raise IntegrityError('Update/environment budget mismatch')
                result={'checkpoint':save_portable(engine,out/'checkpoint'),'step':engine.model.num_timesteps,
                        'collected':dict(zip(TASKS,counts)),'episode_order_verified':True,
                        'training_reset_audit':str(out/'training_reset_audit.csv')}
            elif q['kind']=='evaluate':
                banks=load_banks(q['bank']);before=engine.fingerprints()
                evaluation=evaluate_model(engine.model,banks[q['bank_kind']],costs,out/'evaluation_episodes.csv',q['id'],context='F08')
                if engine.fingerprints()!=before:raise IntegrityError('Evaluation changed training state')
                evaluation['purpose']='technical smoke only' if q.get('technical_smoke') else 'F08 developmental controlled comparison'
                from practice_allocation.core import file_sha256
                result={'evaluation':evaluation,'evaluation_state_unchanged':True,'episodes_path':str(out/'evaluation_episodes.csv'),
                        'episodes_sha256':file_sha256(out/'evaluation_episodes.csv')}
            else:raise IntegrityError('Unknown job')
        progress(complete=True)
    except BaseException as exc:
        error={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc(),
               'integrity_failure':isinstance(exc,(IntegrityError,AssertionError,ValueError)),
               'retryable':isinstance(exc,OSError) and not isinstance(exc,FileExistsError)}
        write_json(out/'error.json',error);traceback.print_exc()
    finally:
        if engine is not None:engine.close()
        write_json(out/'costs.json',{'status':'failed' if error else 'completed','costs':costs.snapshot(),
                   'wall_seconds':time.perf_counter()-started,'cpu_seconds':time.process_time()-cpu,
                   'cuda_event_seconds':None,'gpu_timing':'not instrumented; same device recorded in runtime',
                   'technical_smoke':bool(q.get('technical_smoke'))})
    if error:return 1
    write_json(out/'result.json',{'id':q['id'],'factor':'F08','suite':q['suite'],'kind':q['kind'],
               'original_seed':q['original_seed'],**{k:q[k] for k in ['condition','continuation','horizon'] if k in q},**result})
    return 0


if __name__=='__main__':raise SystemExit(main())
