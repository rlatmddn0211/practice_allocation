"""Original81 evaluation step loop, with pilot identifiers before first write."""
from __future__ import annotations
from common import HERE
import sys
sys.path.insert(0,str(HERE/'baseline81'))
import hashlib
import time
import numpy as np
import torch
from practice_allocation.core import isolated_rng,fingerprint
from records import Trajectory,Physics,Video
from learner import ObservedEpisode
from pathlib import Path

def rollout(policy,case,out,parent_id,checkpoint,relative_step,context,checkpoint_hash,cost,counters,video=False,trace=False):
    out=Path(out);name=f'{checkpoint:07d}_{case["initial_case_id"]}'
    ep=None;writer=None;traj=None;first=None;count=0;ret=0.;last=None;started=time.perf_counter();trace_hash=hashlib.sha256()
    stage={0:0,16000:1,32000:2,64000:3}[relative_step]
    base=6000000000+int(context['cell_number'])*10000000+stage*32000+(case['task_index']*16+case['case_index'])*500
    with isolated_rng():
        try:
            torch.manual_seed(case['action_seed'])
            if torch.cuda.is_available():torch.cuda.manual_seed_all(case['action_seed'])
            ep=ObservedEpisode(case['task_index'],case['reset_seed'],counters);cost.resets+=1;cost.creations+=1
            if ep.initial_state_hash!=case['physical_case_id']:raise RuntimeError('Evaluation physical case mismatch')
            traj=Trajectory(out/'evaluation_transitions'/(name+'.npz'),{
                'experiment_id':'85_onset_reuse_pilot_v1','protocol_version':'85_onset_reuse_pilot_v1',**context,
                'run_id':parent_id,'attempt_id':'attempt_001','task_id':case['task_id'],'split_role':'observation_eval',
                'env_instance_id':name,'episode_id':name,'initial_case_id':case['initial_case_id'],
                'physical_case_id':case['physical_case_id'],'checkpoint_id':checkpoint,'env_step_total':checkpoint,
                'relative_train_step':relative_step,'checkpoint_hash':checkpoint_hash,
                'action_source':'deterministic policy mean through original tanh/scaling path',
                'obs_policy_dtype':'float32','obs_raw_dtype':'float64',
                'raw_success':'current official success at returned state; continue to native 500-step horizon'})
            physical=Physics(ep)
            if video and case['video']:
                writer=Video(out/'videos'/(name+'.mp4'),ep);writer.frame(0)
            for t in range(1,501):
                before=ep.observation.copy();raw_before=ep.last_raw_observation.copy()
                action,_=policy.predict(before,deterministic=True)
                after,reward,terminated,truncated,info=cost.step(ep,action)
                if trace:trace_hash.update(fingerprint((before,action,after,reward,terminated,truncated,info)).encode())
                ret+=reward;last=int(info['success']);count+=last
                if last and first is None:first=t
                scalar_info={k:float(v) for k,v in info.items() if isinstance(v,(int,float,np.number,bool))}
                traj.add(transition_id=base+t,episode_step=t,env_step_total=checkpoint,
                    actor_update_count=max(0,checkpoint-1000),critic_update_count=max(0,checkpoint-1000),policy_version=max(0,checkpoint-1000),
                    obs_policy=before,obs_raw=raw_before,action_executed=action.copy(),reward=reward,
                    next_obs_actual=after.copy(),next_obs_raw_actual=ep.last_raw_observation.copy(),
                    success_step=last,terminated=terminated,truncated=truncated,validity_status=1,action_source=2,
                    bootstrap_mask=float(not terminated),**{'info_'+k:v for k,v in scalar_info.items()},**physical.sample())
                if writer and (t%5==0 or terminated or truncated):writer.frame(t)
                if terminated or truncated:break
        finally:
            if writer:writer.close()
            trajectory=traj.flush() if traj else None
            if ep:ep.close()
    return {'run_id':parent_id,**context,'attempt_id':'attempt_001','task_id':case['task_id'],'split_role':'observation_eval',
        'checkpoint_id':checkpoint,'relative_train_step':relative_step,'checkpoint_hash':checkpoint_hash,
        'initial_case_id':case['initial_case_id'],'physical_case_id':case['physical_case_id'],'episode_id':name,
        'episode_return':ret,'episode_length':t,'success_any':int(first is not None),'success_final':last,
        'first_success_step':first,'success_step_count':count,'terminated':terminated,'truncated':truncated,
        'end_reason':'time_limit' if truncated else 'environment_terminated','episode_complete':True,
        'policy_version_start':max(0,checkpoint-1000),'policy_version_end':max(0,checkpoint-1000),
        'trajectory_ref':trajectory,'video_ref':str(writer.path) if writer else None,'snapshot_refs':[],
        'wall_seconds':time.perf_counter()-started,'validity_status':'valid','error':None,
        'technical_trace_sha256':trace_hash.hexdigest() if trace else None}
