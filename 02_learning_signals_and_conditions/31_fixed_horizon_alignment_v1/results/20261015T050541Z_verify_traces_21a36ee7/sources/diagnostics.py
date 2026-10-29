"""Fixed-length target alignment and finite-horizon soft-value diagnostics."""
import csv
import inspect
import json
from pathlib import Path
import numpy as np
import torch
from practice_allocation.core import TASKS,ENV_NAMES,derived_seed,isolated_rng,file_sha256,write_json
from practice_allocation.environment import TaskEpisode


def measure(model,bank,costs,out,protocol,technical=False,progress=None):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);episodes=[];mc=[];traces={};modes={name:m.training for name,m in model.policy.named_modules()}
    alpha=float(model.log_ent_coef.detach().exp());gamma=float(model.gamma);device=model.device
    def tensor(x):return torch.as_tensor(x,dtype=torch.float32,device=device)
    source={}
    try:
        with isolated_rng(),torch.no_grad():
            for entry in bank:
                if technical and entry['episode_index']>=1:continue
                task=entry['task'];index=entry['episode_index'];key=f'{task}_{index}'
                with TaskEpisode(entry['task_index'],entry['seed'],costs) as ep:
                    if ep.initial_state_hash!=entry['initial_state_hash']:raise AssertionError('D reset mismatch')
                    path=Path(inspect.getsourcefile(type(ep.raw)));source[str(path)]=file_sha256(path)
                    obs=ep.observation.copy();values=[];first=None
                    for step in range(500):
                        action,_=model.predict(obs,deterministic=True);obs,reward,_,truncated,info=ep.step(action)
                        values.append([reward,int(info['success']),float(info['near_object']),float(info['grasp_success']),float(info['obj_to_target'])])
                        if info['success'] and first is None:first=step+1
                    arr=np.array(values,dtype=np.float64)
                    if len(arr)!=500 or not truncated or not np.isfinite(arr).all():raise AssertionError('Invalid500-step trace')
                    traces['D_'+key]=arr;costs.evaluation_episodes+=1
                    episodes.append({'task':task,'episode_index':index,'seed':entry['seed'],'initial_state_hash':ep.initial_state_hash,
                        'success':int(arr[:,1].max()),'return500':float(arr[:,0].sum()),'length':500,'first_success_step':first,
                        'return_to_first_success':float(arr[:first if first else 500,0].sum()),
                        'near_object_reached':int(arr[:,2].max()),'official_grasp_flag_reached':int(arr[:,3].max()),'minimum_official_target_distance':float(arr[:,4].min())})
                if progress:progress(kind='deterministic',task=task,episode=index)
            count=1 if technical else protocol['MC']['initial_states_per_task'];repeats=2 if technical else protocol['MC']['repeats']
            for entry in bank:
                if entry['episode_index']>=count:continue
                for repeat in range(repeats):
                    task=entry['task'];index=entry['episode_index'];key=f'{task}_{index}_{repeat}'
                    noise_seed=derived_seed(protocol['MC']['seed'],ord(task[0])+sum(map(ord,task)),entry['seed'],repeat)
                    torch.manual_seed(noise_seed)
                    with TaskEpisode(entry['task_index'],entry['seed'],costs) as ep:
                        if ep.initial_state_hash!=entry['initial_state_hash']:raise AssertionError('MC reset mismatch')
                        obs=ep.observation.copy();a0,_=model.predict(obs,deterministic=True)
                        initial_q=[float(q.item()) for q in model.critic(tensor(obs[None]),tensor(model.policy.scale_action(a0)[None]))]
                        vals=[]
                        for step in range(500):
                            if step==0:action=a0;logp=0.
                            else:
                                scaled,lp=model.actor.action_log_prob(tensor(obs[None]));action=model.policy.unscale_action(scaled.cpu().numpy()[0]);logp=float(lp.item())
                            obs,reward,_,truncated,info=ep.step(action);vals.append([reward,logp,int(info['success'])])
                        tail=[]
                        for _ in range(protocol['MC']['tail_action_draws']):
                            scaled,lp=model.actor.action_log_prob(tensor(obs[None]));q0,q1=model.critic(tensor(obs[None]),scaled)
                            tail.append([float(q0.item()),float(q1.item()),float(lp.item())])
                        arr=np.array(vals,dtype=np.float64);tt=np.array(tail);weights=gamma**np.arange(500)
                        reward_sum=float(weights@arr[:,0]);entropy_sum=float(-alpha*(weights@arr[:,1]));tail_sum=float(gamma**500*np.mean(np.min(tt[:,:2],axis=1)-alpha*tt[:,2]))
                        traces['MC_'+key]=arr;traces['tail_'+key]=tt;costs.evaluation_episodes+=1
                        mc.append({'task':task,'episode_index':index,'repeat':repeat,'seed':entry['seed'],'action_noise_seed':noise_seed,
                                   'initial_state_hash':ep.initial_state_hash,'length':500,'alpha':alpha,'gamma':gamma,
                                   'q0':initial_q[0],'q1':initial_q[1],'q_min':min(initial_q),
                                   'discounted_rewards':reward_sum,'discounted_entropy':entropy_sum,'discounted_tail':tail_sum,
                                   'tail_free_return':reward_sum+entropy_sum,'soft_return':reward_sum+entropy_sum+tail_sum})
                    if progress:progress(kind='MC',task=task,episode=index,repeat=repeat)
    finally:
        for name,module in model.policy.named_modules():module.training=modes[name]
        # Retain all completed evidence even if a later episode fails.
        for filename,rows in [('episodes.csv',episodes),('mc_episodes.csv',mc)]:
            if rows:
                with (out/filename).open('x',encoding='utf-8',newline='') as f:
                    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
        if traces:
            with (out/'traces.npz').open('xb') as f:np.savez_compressed(f,**traces)
        write_json(out/'environment_sources.json',source)
    expected_D=4 if technical else 80;expected_MC=8 if technical else 32
    if len(episodes)!=expected_D or len(mc)!=expected_MC:raise AssertionError('Wrong diagnostic sample count')
    return {'deterministic_episodes':len(episodes),'MC_episodes':len(mc),'new_environment_steps':500*(len(episodes)+len(mc)),
            'episodes_path':str(out/'episodes.csv'),'episodes_sha256':file_sha256(out/'episodes.csv'),
            'mc_path':str(out/'mc_episodes.csv'),'mc_sha256':file_sha256(out/'mc_episodes.csv'),
            'traces_path':str(out/'traces.npz'),'traces_sha256':file_sha256(out/'traces.npz'),
            'alpha':alpha,'gamma':gamma,'sampling_scope':'first2 new-D initial states/task,4 independent action streams each; finite-horizon tail bootstrap'}
