"""Bounded runtime certification; research always restores the original parents again."""
from __future__ import annotations
from common import *
import argparse

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--preparation',type=Path,required=True);a=ap.parse_args();prep=a.preparation.resolve()
    if not load(prep/'readiness.json')['archive_support_all_receivers']:raise RuntimeError('Readiness failed; runtime prohibited')
    out=new_output('technical_validation');started=time.perf_counter();checks=[];cost=None;eng=None
    def ck(name,passed,scope='',detail=''):
        checks.append(dict(check=name,passed=bool(passed),scope=scope,detail=detail))
        save(out/'checks_progress.json',checks,replace=True)
        if not passed:raise RuntimeError(name+': '+str(scope)+' '+str(detail))
    try:
        import pilot_runtime as rt
        from pilot_evaluation import rollout as pilot_rollout
        import numpy as np
        import torch
        runtime=rt.initialize_runtime();save(out/'runtime.json',runtime)
        prior=sum(p.read_bytes().count(b'I') for p in (HERE/'results').rglob('technical_control_journal.bin'))
        if prior>=10000:raise RuntimeError('Technical/failed/retry shared cap exhausted')
        cost=rt.Cost(out/'costs','technical',10000-prior)
        seeds=load(prep/'seed_manifest.json')['parent_future_streams']
        stream_lookup={(r['parent_id'],r['future_id']):r['streams'] for r in seeds}
        traces=[]
        def context(parent,arm='BASE',future='F01',cell=900):
            return dict(protocol_version='85_onset_reuse_pilot_v1',parent_id=parent,future_id=future,arm=arm,cell_number=cell)
        def start(parent,directory,arm='BASE',probability=None,cell=900):
            directory.mkdir(parents=True,exist_ok=False)
            engine=rt.restore_parent(parent,cost,directory)
            receipt=rt.configure_future(engine,prep,context(parent,arm,cell=cell),stream_lookup[(parent,'F01')],probability)
            save(directory/'restore_and_rng_receipt.json',receipt)
            return engine
        def short(engine,n):
            digest=hashlib.sha256()
            for _ in range(n):
                row=engine.step()
                digest.update(rt.fingerprint((row,engine.model.replay_buffer.last_indices)).encode())
            state=dict(learning=rt.fingerprint(rt.learning_state(engine.model)),rng=rt.fingerprint(rt.capture_rng()),
                last_policy_mode=engine.model.policy.training,trace=digest.hexdigest(),steps=n)
            return state
        def close(engine):
            if not engine.at_boundary:
                ep=engine.episode
                engine.finish_episode('technical_window_end',False,int(ep.any_success))
            engine.flush();engine.close()
        # Five independent full restore pairs, 100 actual transitions each.
        for i,parent in enumerate(RUNS):
            pair=[]
            for repeat in range(2):
                eng=start(parent,out/f'restore_{parent}_{repeat}',cell=901+i)
                pair.append(short(eng,100));close(eng);eng=None
            ck('same parent restored twice: actions physics rewards updates exactly equal',pair[0]==pair[1],parent)
            traces.append(dict(parent=parent,restore_pair=pair))
            cost.checkpoint(stage='parent_restore',parent=parent)
            print(json.dumps(dict(stage='parent restore pass',parent=parent,technical_steps=cost.completed)),flush=True)
        # Stock sampler versus the intervention path with replacement=0.
        pair=[]
        for role,arm in [('stock','BASE'),('zero','ONSET')]:
            eng=start('R01',out/role,arm=arm,probability=0,cell=920)
            if role=='stock':
                eng.model.replay_buffer.__class__=rt.UsageReplay
                eng.model.update_sink=rt.UpdateSink(eng.out,eng.run_id)
                eng.model.update_sink.first=eng.model._n_updates+1
            pair.append(short(eng,500))
            if role=='zero':
                resume_path=out/'resume_checkpoint';rt.save_full(eng,resume_path)
                continued=short(eng,100)
            close(eng);eng=None
        ck('stock original sampler and zero replacement exactly equal',pair[0]==pair[1])
        eng=rt.restore_full(resume_path,cost,out/'restored_resume')
        resumed=short(eng,100);close(eng);eng=None
        ck('full pilot checkpoint restores optimizer replay collector RNG and exact continuation',resumed==continued)
        # P/U share primitive replacement, episode and offset fields while policy/data may diverge.
        corresponding=[]
        for arm in ('ONSET','RANDOM_PRE'):
            eng=start('R01',out/('pair_'+arm),arm=arm,cell=930)
            short(eng,100);r=eng.model.replay_buffer
            corresponding.append(dict(draw=r.pilot_draw_digest.hex(),mask=r.pilot_mask_digest.hex(),archive_actual=r.pilot_archive_actual,
                native_tasks=r.pilot_native_tasks.tolist()))
            ck('replacement usage conserves 256 final slots per update',r.pilot_native_actual+r.pilot_archive_actual==25600,arm)
            close(eng);eng=None
        ck('P U draw and replacement masks correspond at identical stream keys',corresponding[0]==corresponding[1])
        # Match the original native evaluation in four tasks and repeat DO once.
        eng=start('R01',out/'evaluation_engine',cell=940)
        before=eng.fingerprints();rng=rt.fingerprint(rt.capture_rng())
        cases=load(CAMPAIGN/'evaluation_cases/manifest.json')['cases'];policy=copy_policy=None
        import copy
        with __import__('practice_allocation.core',fromlist=['isolated_rng']).isolated_rng():
            policy=copy.deepcopy(eng.model.policy);policy.set_training_mode(False)
            selected=[next(r for r in cases if r['task_id']==t and r['case_index']==0) for t in ('DO','DC','PU','BP')]
            evalrows=[]
            for row in selected:
                evalrows.append(pilot_rollout(policy,row,out/'evaluation',eng.run_id,1000000,0,context('R01',cell=940),
                    'technical_fixed_parent',cost,rt.CostCounter(),video=False,trace=True))
            repeated=rt.original_rollout(policy,selected[0],out/'original_evaluation',eng.run_id,1000000,cost,rt.CostCounter(),
                logging=False,video=False,snapshot=False,trace=True)
        ck('pilot evaluation matches original deterministic full-horizon evaluator',evalrows[0]['technical_trace_sha256']==repeated['technical_trace_sha256'])
        ck('evaluation keeps all training state and RNG exactly unchanged',eng.fingerprints()==before and rt.fingerprint(rt.capture_rng())==rng)
        ck('all four original physical cases reproduced at native horizon',all(r['episode_length']==500 and r['episode_complete'] for r in evalrows))
        close(eng);eng=None
        save(out/'restore_traces.json',traces);save(out/'paired_draws.json',corresponding)
        costs=cost.checkpoint(stage='complete')
        ck('shared technical/failure reserve obeyed',prior+costs['issued_charged']<=10000)
        sourcehash=load(out/'source_hashes.json')
        save(out/'technical_checks.json',dict(status='passed',checks=checks,prior_charged=prior,actual_cost=costs,
            exact_tolerance=dict(atol=0,rtol=0),research_models='Always restore original parents again',source_hashes=sourcehash))
        save(out/'FINAL_STATUS.json',dict(status='passed',steps=cost.completed,charged=cost.issued,source_snapshot=str(out/'source_snapshot'),preparation=str(prep)))
        save(HERE/'LATEST_TECHNICAL.json',dict(output=out,status='passed',preparation=str(prep)),replace=True)
        print(json.dumps(dict(output=str(out),status='passed',steps=cost.completed)),flush=True)
    except BaseException as ex:
        if eng is not None:
            try:eng.flush();eng.close()
            except BaseException:pass
        save(out/'FAILED.json',dict(error=repr(ex),at=utc(),actual_issued=cost.issued if cost else 0,actual_completed=cost.completed if cost else 0,checks=checks))
        print(json.dumps(dict(output=str(out),error=repr(ex))),flush=True);raise
    finally:
        if cost is not None:cost.close()
        save(out/'execution_costs.json',dict(wall_seconds=time.perf_counter()-started,technical_issued=cost.issued if cost else 0,technical_completed=cost.completed if cost else 0))

if __name__=='__main__':main()
