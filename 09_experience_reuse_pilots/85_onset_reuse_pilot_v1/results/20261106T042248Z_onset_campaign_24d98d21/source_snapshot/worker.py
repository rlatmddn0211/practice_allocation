"""One immutable shared-start evaluation or one frozen 64k research cell."""
from __future__ import annotations
from common import *
import argparse

def assert_frozen(campaign):
    for relative,digest in load(Path(campaign)/'research_source_hashes.json').items():
        if sha(HERE/relative)!=digest:raise RuntimeError('Frozen research source changed: '+relative)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--campaign',type=Path,required=True)
    ap.add_argument('--cell');ap.add_argument('--start-parent');args=ap.parse_args();campaign=args.campaign.resolve()
    assert_frozen(campaign)
    import pilot_runtime as rt
    import pandas as pd
    import numpy as np
    import psutil
    config=load(campaign/'campaign_config.json');prep=Path(config['preparation']);started=time.perf_counter()
    key=args.cell or ('START_'+args.start_parent)
    base=campaign/'jobs'/key
    if (base/'COMPLETE.json').exists():raise RuntimeError('A valid completed job must not be executed again: '+key)
    attempt=base/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_attempt_'+uuid.uuid4().hex[:8])
    attempt.mkdir(parents=True,exist_ok=False)
    shutil.copytree(campaign/'source_snapshot',attempt/'source_snapshot')
    save(attempt/'source_hashes.json',load(campaign/'research_source_hashes.json'))
    save(base/'ACTIVE_ATTEMPT.json',dict(attempt=attempt),replace=True)
    eng=None;train_cost=None;eval_cost=None
    try:
        save(attempt/'runtime.json',rt.initialize_runtime())
        cases=load(CAMPAIGN/'evaluation_cases/manifest.json')['cases']
        if args.start_parent:
            parent=args.start_parent;eval_cost=rt.Cost(attempt/'costs','start_eval',32000)
            eng=rt.restore_parent(parent,eval_cost,attempt)
            original_model=CAMPAIGN/'runs'/parent/'checkpoints/full/1000000/model.zip'
            outcomes=rt.evaluate(eng,cases,attempt,0,eval_cost,sha(original_model),100+RUNS.index(parent),video=False)
            # Compare with the entire original final panel, without selecting matching cases.
            original=pd.concat([pd.read_parquet(p) for p in sorted((CAMPAIGN/'runs'/parent/'evaluation_episodes').glob('part_*.parquet'))],ignore_index=True)
            old=original[original.checkpoint_id==1000000].set_index(['task_id','initial_case_id'])
            discrepancies=[]
            for row in outcomes:
                previous=old.loc[(row['task_id'],row['initial_case_id'])]
                for metric in ('success_any','success_final','episode_length','episode_return'):
                    if row[metric]!=previous[metric]:discrepancies.append(dict(case=row['initial_case_id'],metric=metric,old=float(previous[metric]),new=float(row[metric])))
            save(attempt/'original_1M_comparison.json',dict(compared_cases=len(outcomes),mismatches=discrepancies,labels_and_returns_exact=not discrepancies))
            if discrepancies:raise RuntimeError('Shared +0 differs from original 1M panel; investigate without selecting parents')
            eng.flush();eval_cost.close()
            result=dict(status='complete',kind='shared_start',parent_id=parent,attempt=str(attempt),evaluation_episodes=64,eval_issued=eval_cost.issued,eval_completed=eval_cost.completed,train_completed=0)
        else:
            plan=pd.read_csv(campaign/'execution_plan.csv');cell=plan[plan.cell_id==args.cell]
            if len(cell)!=1:raise RuntimeError('Cell not in frozen plan')
            cell=cell.iloc[0];parent=cell.parent_id;future=cell.future_id;arm=cell.arm
            seeds=load(prep/'seed_manifest.json')['parent_future_streams']
            streams=next(r['streams'] for r in seeds if r['parent_id']==parent and r['future_id']==future)
            context=dict(protocol_version='85_onset_reuse_pilot_v1',parent_id=parent,future_id=future,arm=arm,cell_number=int(cell.execution_order))
            train_cost=rt.Cost(attempt/'costs','train',64000);eval_cost=rt.Cost(attempt/'costs','post_eval',96000)
            eng=rt.restore_parent(parent,train_cost,attempt)
            receipt=rt.configure_future(eng,prep,context,streams)
            save(attempt/'state_and_rng_change_manifest.json',receipt)
            rt.usage_snapshot(eng,attempt/'archive_usage/000000')
            # A complete native 4k block is also a durable restart barrier. This
            # extra storage schedule is frozen before outcomes and spends no steps.
            for relative in range(4000,64001,4000):
                target=1000000+relative
                while eng.model.num_timesteps<target:
                    eng.step()
                    if eng.model.num_timesteps%250==0:
                        save(base/'status.json',dict(state='training',cell_id=key,attempt=str(attempt),relative_train_step=eng.model.num_timesteps-1000000,
                            train_issued=train_cost.issued,eval_issued=eval_cost.issued,wall_seconds=time.perf_counter()-started),replace=True)
                eng.flush()
                full=attempt/'checkpoints/full'/f'{relative:06d}';t=time.perf_counter();rt.save_full(eng,full)
                append_row=dict(relative_train_step=relative,full=str(full),seconds=time.perf_counter()-t,bytes=sum(p.stat().st_size for p in full.rglob('*') if p.is_file()))
                with (attempt/'checkpoint_io.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(append_row)+'\n')
                if relative in (16000,32000,64000):
                    if relative in (16000,32000):
                        light=attempt/'checkpoints/light'/f'{relative:06d}';rt.original_checkpoints.light(eng,light);model_hash=sha(light/'model.zip')
                    else:model_hash=sha(full/'model.zip')
                    rt.usage_snapshot(eng,attempt/'archive_usage'/f'{relative:06d}')
                    save(base/'status.json',dict(state='evaluation',cell_id=key,attempt=str(attempt),relative_train_step=relative,train_issued=train_cost.issued,eval_issued=eval_cost.issued),replace=True)
                    rt.evaluate(eng,cases,attempt,relative,eval_cost,model_hash,int(cell.execution_order),video=relative==64000)
                train_cost.checkpoint(relative_train_step=relative);eval_cost.checkpoint(relative_train_step=relative)
                print(json.dumps(dict(cell=key,relative=relative,train=train_cost.completed,eval=eval_cost.completed,wall_seconds=time.perf_counter()-started)),flush=True)
            if eng.collected_steps.tolist()!=[266000]*4:raise RuntimeError('Original uniform four-task continuation counts differ')
            if eng.model._n_updates!=1063000 or eng.model.num_timesteps!=1064000:raise RuntimeError('Final learner counters differ')
            summary=rt.usage_snapshot(eng,attempt/'archive_usage/final')
            if summary['native_draw_count']!=64000*256:raise RuntimeError('Actual update draw count differs')
            result=dict(status='complete',kind='branch',**context,attempt=str(attempt),train_issued=train_cost.issued,train_completed=train_cost.completed,
                eval_issued=eval_cost.issued,eval_completed=eval_cost.completed,evaluation_episodes=192,
                final_full=str(full),final_model_hash=sha(full/'model.zip'),usage=summary)
        result.update(completed_at=utc(),wall_seconds=time.perf_counter()-started)
        process=psutil.Process();result['resource_costs']=dict(memory=process.memory_info()._asdict(),cpu=process.cpu_times()._asdict(),io=process.io_counters()._asdict())
        save(attempt/'COMPLETE.json',result);save(base/'COMPLETE.json',result)
        save(base/'status.json',dict(state='complete',**result),replace=True)
    except BaseException as ex:
        failure=dict(state='failed',cell_id=key,attempt=str(attempt),error=repr(ex),at=utc(),
            train_issued=train_cost.issued if train_cost else 0,eval_issued=eval_cost.issued if eval_cost else 0,
            train_completed=train_cost.completed if train_cost else 0,eval_completed=eval_cost.completed if eval_cost else 0,
            classification='requires_integrity_review; nonfinite algorithm failures are treatment outcomes, never seed replacement')
        save(attempt/'FAILED.json',failure);save(base/'status.json',failure,replace=True)
        print(json.dumps(failure),flush=True);raise
    finally:
        if eng is not None:
            try:eng.flush();eng.close()
            except BaseException:pass
        if train_cost is not None:train_cost.close()
        if eval_cost is not None:eval_cost.close()

if __name__=='__main__':main()
