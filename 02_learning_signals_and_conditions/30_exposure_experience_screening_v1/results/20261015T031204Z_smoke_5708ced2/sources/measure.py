"""Read historical replay and official episode logs without mutating learners."""
import argparse
import csv
import gc
import json
import traceback
from pathlib import Path
import numpy as np
import torch
from common import Run,HERE,ROOT,save,table
from snapshot_io import load_snapshot,choose_panels


def history(run,ref,tasks,cutoff):
    selected={t:[] for t in tasks};segments=[];seen=set();current=ref
    while any(len(v)<20 for v in selected.values()):
        d=Path(current['path']);run.read(d/'checkpoint_manifest.json',current['manifest_sha256'])
        if str(d) in seen:raise AssertionError('Cycle in checkpoint ancestry')
        seen.add(str(d));attempt=d.parent
        log=attempt/'train_episodes.csv'
        if log.exists():
            episodes=run.rows(log);segments.append({'path':str(log),'sha256':run.inputs[str(log)]})
            for row in reversed(episodes):
                task=row['task'];step=int(row['step'])
                if task in selected and step<=cutoff and len(selected[task])<20:
                    run.check('official full training episode',int(row['length'])==500 and row['success'] in ['True','False','0','1','0.0','1.0'])
                    selected[task].append({'step':step,'success':int(row['success'] in ['True','1','1.0']),
                                           'return':float(row['return']),'initial_state_hash':row['initial_state_hash']})
        request=run.read(attempt/'request.json')
        if not request.get('parent'):break
        current=request['parent']
    for task,rows in selected.items():
        run.check('20 unique-time episodes '+task,len(rows)==20 and len({r['step'] for r in rows})==20)
        rows.sort(key=lambda r:r['step'])
    return selected,segments


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--smoke',action='store_true');args=ap.parse_args();run=Run('smoke' if args.smoke else 'measure')
    try:
        torch.set_num_threads(2);p=run.read(HERE/'protocol.json')
        inventory=run.rows(ROOT/p['prior_artifact_manifest']);expected={str((ROOT/'29_neural_plasticity_screening_v1'/r['path']).resolve()):r['sha256'] for r in inventory}
        manifest=run.read(ROOT/p['snapshot_manifest'],expected[str((ROOT/p['snapshot_manifest']).resolve())])
        if args.smoke:manifest=manifest[:3]
        table_rows=[];raw_records=[];parent_cache={}
        for ix,entry in enumerate(manifest):
            ref=entry['checkpoint'];jid=entry['id'];tasks=p['suites'][entry['suite']];cp=entry['checkpoint_step'];h=entry['horizon']
            model,b,cm=load_snapshot(run,ref,'cpu');del model
            ids=b.observations[:b.size(),0,-4:].argmax(1);birth=b.birth_steps[:b.size()]
            order=np.argsort(birth);episodes,segments=history(run,ref,tasks,cp+h)
            moments={};panels=choose_panels(run,b,p,jid)
            for ti,pi,indices in panels:
                obs=b.observations[indices,0,:-4].astype(np.float64)
                moments[tasks[ti]+('_M' if pi==0 else '_A')]={'mean':obs.mean(0).tolist(),'variance':obs.var(0).tolist(),
                                                           'indices':indices.tolist(),'birth_steps':birth[indices].tolist()}
            state={'sampled':b.sampled_task_counts.tolist(),'sampled_total':int(b.sampled_total),
                   'sampled_new_count':int(b.sampled_new_count),'total_added':int(b.total_added),
                   'task_counts':np.bincount(ids,minlength=4).tolist(),
                   'age_by_task':[float(np.mean(cp+h-birth[ids==i])) for i in range(4)]}
            ctx=(entry['suite'],entry['original_seed'],cp)
            if not h:
                parent_cache[ctx]={'state':state,'old_order':ids[order].copy(),'moments':moments}
                exposure=None
            else:
                parent=parent_cache[ctx];old=parent['state'];new_ids=ids[np.argsort(birth)[-h:]]
                run.check('all new transitions available '+jid,np.array_equal(np.sort(birth[birth>cp]),np.arange(cp+1,cp+h+1)))
                sampled=np.array(state['sampled'])-np.array(old['sampled']);sampletotal=state['sampled_total']-old['sampled_total']
                run.check('all branch sample counters '+jid,sampletotal==h*256 and sampled.sum()==sampletotal)
                # start_branch resets branch_start_step but NOT accumulated sampled_new_count.
                newfraction=(state['sampled_new_count']-old['sampled_new_count'])/sampletotal
                added=np.eye(4,dtype=np.int64)[new_ids];removed=np.eye(4,dtype=np.int64)[parent['old_order'][:h]]
                occupancy=np.array(old['task_counts'])+np.cumsum(added-removed,axis=0)
                expected_exposure=occupancy.mean(0)/b.buffer_size
                exposure={'sampled':sampled.tolist(),'sampled_total':sampletotal,'observed_share':(sampled/sampletotal).tolist(),
                          'collected':np.bincount(new_ids,minlength=4).tolist(),'collection_share':np.bincount(new_ids,minlength=4).astype(float).tolist(),
                          'expected_share':expected_exposure.tolist(),'new_fraction':newfraction,
                          'expected_new_fraction':(h+1)/(2*b.buffer_size)}
                exposure['collection_share']=[n/h for n in exposure['collected']]
                run.check('new fraction bounded '+jid,0<=newfraction<=1)
            for ti,task in enumerate(tasks):
                ep=episodes[task];m=moments[task+'_M'];parent=parent_cache[ctx]['moments'][task+'_M']
                pm=np.array(parent['mean']);pv=np.array(parent['variance']);scale=np.maximum(pv,.01**2)
                novelty=np.sqrt(np.mean((np.array(m['variance'])+(np.array(m['mean'])-pm)**2)/scale))
                a=moments[task+'_A'];novelty_a=np.sqrt(np.mean((np.array(a['variance'])+(np.array(a['mean'])-pm)**2)/scale))
                row={k:entry[k] for k in ['id','suite','original_seed','checkpoint_step','horizon','continuation','allocation']}
                row.update(task=task,recent_success=float(np.mean([e['success'] for e in ep])),recent_return=float(np.mean([e['return'] for e in ep])),
                           recent_unique=len({e['initial_state_hash'] for e in ep}),oldest_episode_age=cp+h-ep[0]['step'],
                           mean_replay_age=state['age_by_task'][ti]/b.buffer_size,raw_displacement=float(np.log1p(novelty)),
                           raw_displacement_audit=float(np.log1p(novelty_a)))
                if exposure:row.update(collection_share=exposure['collection_share'][ti],observed_share=exposure['observed_share'][ti],
                                       expected_share=exposure['expected_share'][ti],new_fraction=exposure['new_fraction'])
                table_rows.append(row)
            raw={'entry':{k:v for k,v in entry.items() if k not in ['wall_seconds','compute_wall_seconds']},'episodes':episodes,'episode_sources':segments,
                 'moments':moments,'replay_counters':state,'exposure':exposure}
            rawpath=run.out/(jid+'.json');save(rawpath,raw);raw_records.append({'id':jid,'path':str(rawpath),'sha256':run.hashed(rawpath)})
            print(f'measured {ix+1}/{len(manifest)} {jid}',flush=True);del b;gc.collect()
        table(run.out/'task_features.csv',table_rows);save(run.out/'manifest.json',raw_records)
        run.finish({'status':'completed','factor':'F02_F03','technical_smoke':args.smoke,'snapshots':len(manifest),
                    'task_rows':len(table_rows),'official_training_episode_uses':len(table_rows)*20,'new_environment_steps':0,
                    'coverage_definition':'parent-only raw-state standardization; no task semantic labels inferred'})
    except Exception:
        run.finish({'status':'failed','traceback':traceback.format_exc()});raise


if __name__=='__main__':main()
