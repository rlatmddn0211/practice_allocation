"""Outcome-blind cases and isolated, full-horizon deterministic evaluation."""
from __future__ import annotations
import copy
import hashlib
import pickle
import time
from pathlib import Path
import numpy as np
import torch
from practice_allocation.core import TASKS, isolated_rng, fingerprint, capture_rng
from practice_allocation.environment import CostCounter
from records import ROOT, Table, Trajectory, Physics, Video, capture_environment, dump_snapshot, save, load, ref
from learner import ObservedEpisode

def prepare_cases(campaign):
    campaign=Path(campaign);dest=campaign/'evaluation_cases'
    if (dest/'manifest.json').exists():return load(dest/'manifest.json')
    counters=CostCounter();cases=[];physical=set();started=time.perf_counter()
    with isolated_rng():
        for row in load(ROOT/'seed_manifest.json')['evaluation_cases']:
            ep=ObservedEpisode(row['task_index'],row['reset_seed'],counters)
            try:
                initial=copy.deepcopy(ep.initial_state)
                # Includes physical state and task/goal; case labels/seeds are not identity.
                identity=fingerprint(initial)
                if identity in physical:raise RuntimeError('Duplicate physical evaluation case')
                physical.add(identity)
                p=dest/(row['initial_case_id']+'.pkl');dump_snapshot(p,ep)
                features=Physics(ep)
                save(dest/('feature_schema_'+TASKS[ep.task_index]+'.json'),features.schema) if not (dest/('feature_schema_'+TASKS[ep.task_index]+'.json')).exists() else None
                # Recreate each case before any policy labels are observed.
                with ObservedEpisode(row['task_index'],row['reset_seed'],counters) as other:
                    if fingerprint(other.initial_state)!=identity:raise RuntimeError('Physical reset is not reproducible')
                cases.append({**row,'physical_case_id':identity,'initial_state':initial,'snapshot':ref(p),
                    'physical_identity_rule':'task label, randomization vector, goal, qpos, qvel, returned reset observation; same installed source/model hashes',
                    'selection_rule':'fixed SHA256 seed and index; no policy execution or success selection'})
            finally:ep.close()
    manifest={'cases':cases,'unique_physical_cases':len(physical),'panels':4,'per_task':16,
        'outcome_labels_observed':False,'freeze':'before all research initialization evaluations',
        'costs':counters.snapshot(),'wall_seconds':time.perf_counter()-started}
    save(dest/'manifest.json',manifest);return manifest

def rollout(policy,row,out,run_id,checkpoint,cost,counters,logging=True,video=None,snapshot=True,trace=False):
    out=Path(out);name=f"{checkpoint:07d}_{row['initial_case_id']}"
    ep=None;writer=None;traj=None;snapshots=[];first=None;count=0;ret=0.;success_final=None
    start=time.perf_counter();error=None
    trace_hash=hashlib.sha256()
    run_prefix=(int(run_id[1:]) if run_id.startswith('R') else 99)*10000000
    planned=[0,10000,20000,50000,100000,200000,400000,600000,800000,1000000]
    checkpoint_index=planned.index(checkpoint) if checkpoint in planned else 99
    transition_prefix=run_prefix+1000000+checkpoint_index*32000+(row['task_index']*16+row['case_index'])*500
    with isolated_rng():
        try:
            torch.manual_seed(row['action_seed'])
            if torch.cuda.is_available():torch.cuda.manual_seed_all(row['action_seed'])
            ep=ObservedEpisode(row['task_index'],row['reset_seed'],counters)
            cost.resets+=1;cost.creations+=1
            if ep.initial_state_hash!=row['physical_case_id']:raise RuntimeError('Evaluation physical case mismatch')
            use_video=bool(row['video']) if video is None else video
            if logging:
                traj=Trajectory(out/'evaluation_transitions'/(name+'.npz'),{
                    'experiment_id':ROOT.name,'run_id':run_id,'attempt_id':'attempt_001','task_id':row['task_id'],
                    'split_role':'observation_eval','env_instance_id':name,'episode_id':name,'initial_case_id':row['initial_case_id'],
                    'physical_case_id':row['physical_case_id'],'checkpoint_id':checkpoint,'env_step_total':checkpoint,
                    'action_source':'deterministic policy mean through original tanh/scaling path','obs_policy_dtype':'float32','obs_raw_dtype':'float64',
                    'raw_success':'current official success at each returned state; no artificial first-success stop'})
                physics=Physics(ep)
                if use_video:
                    writer=Video(out/'videos'/(name+'.mp4'),ep);writer.frame(0)
                if use_video and snapshot:snapshots.append(dump_snapshot(out/'environment_snapshots/evaluation'/name/'000.pkl',ep))
            for i in range(1,501):
                observation=ep.observation.copy();raw_observation=ep.last_raw_observation.copy()
                action,_=policy.predict(observation,deterministic=True)
                following,reward,terminated,truncated,info=cost.step(ep,action)
                if trace:trace_hash.update(fingerprint((observation,action,following,reward,terminated,truncated,info)).encode())
                ret+=reward;success_final=int(info['success']);count+=success_final
                if success_final and first is None:first=i
                if logging:
                    scalar_info={k:float(v) for k,v in info.items() if isinstance(v,(int,float,np.number,bool))}
                    traj.add(transition_id=transition_prefix+i,episode_step=i,env_step_total=checkpoint,
                        actor_update_count=max(0,checkpoint-1000),critic_update_count=max(0,checkpoint-1000),
                        policy_version=max(0,checkpoint-1000),obs_policy=observation,obs_raw=raw_observation,
                        action_executed=action.copy(),reward=reward,next_obs_actual=following.copy(),
                        next_obs_raw_actual=ep.last_raw_observation.copy(),success_step=success_final,
                        terminated=terminated,truncated=truncated,validity_status=1,action_source=2,
                        bootstrap_mask=float(not terminated),**{'info_'+k:v for k,v in scalar_info.items()},**physics.sample())
                    if writer and (i%5==0 or terminated or truncated):writer.frame(i)
                    if use_video and snapshot and (i%50==0 or terminated or truncated):
                        snapshots.append(dump_snapshot(out/'environment_snapshots/evaluation'/name/f'{i:03d}.pkl',ep))
                if terminated or truncated:break
        except BaseException as exc:
            error=repr(exc);raise
        finally:
            if writer:writer.close()
            if traj:trajectory=traj.flush()
            else:trajectory=None
            if ep:ep.close()
    return {'run_id':run_id,'attempt_id':'attempt_001','task_id':row['task_id'],'split_role':'observation_eval',
        'checkpoint_id':checkpoint,'initial_case_id':row['initial_case_id'],'physical_case_id':row['physical_case_id'],
        'episode_id':name,'episode_return':ret,'episode_length':i,'success_any':int(first is not None),
        'success_final':success_final,'first_success_step':first,'success_step_count':count,
        'terminated':terminated,'truncated':truncated,'end_reason':'time_limit' if truncated else 'environment_terminated',
        'episode_complete':True,'policy_version_start':max(0,checkpoint-1000),'policy_version_end':max(0,checkpoint-1000),
        'trajectory_ref':trajectory,'video_ref':str(writer.path) if writer else None,'snapshot_refs':snapshots,
        'wall_seconds':time.perf_counter()-start,'validity_status':'valid','error':error,
        'technical_trace_sha256':trace_hash.hexdigest() if trace else None}

def evaluate(engine,cases,out,checkpoint,cost):
    # Deep-copy the policy only: no learner mutation, replay, optimizer or normalize updates.
    before=engine.fingerprints();rng=fingerprint(capture_rng());started=time.perf_counter()
    with isolated_rng():
        policy=copy.deepcopy(engine.model.policy);policy.set_training_mode(False)
        counters=CostCounter();table=Table(Path(out)/'evaluation_episodes',flush_rows=64)
        rows=[]
        for row in cases:
            result=rollout(policy,row,out,engine.run_id,checkpoint,cost,counters)
            table.add(result);rows.append(result)
        table.flush();del policy
    after=engine.fingerprints()
    if after!=before or fingerprint(capture_rng())!=rng:raise RuntimeError('Evaluation mutated learner/replay/collector/RNG')
    save(Path(out)/'evaluation_receipts'/f'{checkpoint:07d}.json',{
        'checkpoint':checkpoint,'episodes':len(rows),'physical_cases':len({r['physical_case_id'] for r in rows}),
        'success_by_task':{t:sum(r['success_any'] for r in rows if r['task_id']==t)/16 for t in TASKS},
        'costs':counters.snapshot(),'learner_before':before,'learner_after':after,'state_unchanged':True,
        'wall_seconds':time.perf_counter()-started})
    return rows
