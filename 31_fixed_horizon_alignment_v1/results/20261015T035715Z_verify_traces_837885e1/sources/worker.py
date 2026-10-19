"""Immutable fresh-diagnostic worker. Original learner state is preserved."""
import argparse
import json
import os
import time
import traceback
from pathlib import Path


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--request',required=True);args=ap.parse_args()
    q=json.loads(Path(args.request).read_text(encoding='utf-8-sig'));os.environ['PRACTICE_SUITE']=q['suite'];os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
    worker_lock=None
    if q.get('worker_lock'):
        import msvcrt
        worker_lock=Path(q['worker_lock']).open('a+b')
        if worker_lock.tell()==0:worker_lock.write(b'0');worker_lock.flush()
        while True:
            try:worker_lock.seek(0);msvcrt.locking(worker_lock.fileno(),msvcrt.LK_NBLCK,1);break
            except OSError:time.sleep(5)
    from dataclasses import replace
    from practice_allocation.core import ROOT,Config,configure_runtime,runtime_manifest,source_hashes,write_json,file_sha256,utc_now
    from practice_allocation.environment import CostCounter
    from practice_allocation.evaluation import build_banks
    from practice_allocation.study_io import IntegrityError,source_snapshot,load_portable,load_banks
    from diagnostics import measure
    out=Path(q['output']);out.mkdir(parents=True,exist_ok=True)
    if (out/'runtime.json').exists():raise IntegrityError('Attempt already used')
    source_snapshot(out);started=time.perf_counter();cpu=time.process_time();engine=None;costs=CostCounter();error=None;result={}
    config=replace(Config.load(ROOT/'configs/learner.json'),seed=q['original_seed'],bank_seed=q.get('bank_seed',315015),
                   diagnostic_bank_episodes_per_task=20,outcome_bank_episodes_per_task=1)
    if q.get('technical_smoke'):config=replace(config,diagnostic_bank_episodes_per_task=2)
    def progress(**v):
        with (out/'progress.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps({'time':utc_now(),'costs':costs.snapshot(),**v})+'\n')
    try:
        if source_hashes()!=q['source_hashes']:raise IntegrityError('Frozen source changed')
        configure_runtime(config)
        runtime=runtime_manifest(config,'F05 alignment')
        runtime['actual_diagnostic_protocol']={'horizon':500,'stop_at_success':False,'persistent_training_updates':0,
            'definition':'protocol.json; deterministic full-horizon D and soft stochastic MC with explicitly reported bootstrap tail'}
        write_json(out/'runtime.json',runtime)
        if q['kind']=='bank':
            banks=build_banks(config,costs);path=Path(q['historical_forbidden'])
            if file_sha256(path)!=q['historical_forbidden_sha256']:raise IntegrityError('Historical exclusions changed')
            old=json.loads(path.read_text());sets=[set(old[k]) for k in ['states','parameters','seeds']]
            for rows in banks.values():
                for e in rows:
                    if e['initial_state_hash'] in sets[0] or e['task_parameter_hash'] in sets[1] or e['seed'] in sets[2]:raise IntegrityError('Diagnostic overlaps prior bank/training')
            write_json(out/'evaluation_banks.json',banks);result={'bank':{'path':str(out/'evaluation_banks.json'),'sha256':file_sha256(out/'evaluation_banks.json')}}
        else:
            engine=load_portable(q['parent'],config,costs);before=engine.fingerprints();p=json.loads((ROOT/'protocol.json').read_text())
            result=measure(engine.model,load_banks(q['bank'])['diagnostic'],costs,out/'diagnostics',p,bool(q.get('technical_smoke')),progress)
            if engine.fingerprints()!=before:raise IntegrityError('Diagnostic changed original full state/RNG')
            if costs.train_iterations!=0 or costs.environment_steps!=result['new_environment_steps']:raise IntegrityError('Diagnostic cost mismatch')
            result.update(learner_unchanged=True,checkpoint=q['parent'],original_id=q['original_id'])
        progress(complete=True)
    except BaseException as exc:
        error={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc(),
               'integrity_failure':isinstance(exc,(IntegrityError,AssertionError,ValueError)),
               'retryable':isinstance(exc,OSError) and not isinstance(exc,FileExistsError)}
        write_json(out/'error.json',error);traceback.print_exc()
    finally:
        if engine:engine.close()
        write_json(out/'costs.json',{'status':'failed' if error else 'completed','costs':costs.snapshot(),
                   'wall_seconds':time.perf_counter()-started,'cpu_seconds':time.process_time()-cpu,'cuda_event_seconds':None,
                   'technical_smoke':bool(q.get('technical_smoke'))})
    if error:return 1
    write_json(out/'result.json',{'id':q['id'],'factor':'F05_alignment','suite':q['suite'],'kind':q['kind'],
               'original_seed':q['original_seed'],**result})
    return 0


if __name__=='__main__':raise SystemExit(main())
