"""Passive observation around the unchanged stock SAC update and collector."""
from __future__ import annotations
import copy
import os
import time
from pathlib import Path
os.environ['PRACTICE_SUITE']='B'
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
import numpy as np
import torch
from stable_baselines3 import SAC
from practice_allocation.core import TASKS, AllocationSchedule, derived_seed, seed_learning, fingerprint
from practice_allocation.engine import Engine
from practice_allocation.environment import TaskEpisode, conditioned_observation
from practice_allocation.learning import AuditedSAC, AuditedReplayBuffer
from records import Table, Trajectory, Physics, dump_snapshot, save, utc

class ObservedEpisode(TaskEpisode):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.last_raw_observation=self.initial_raw_observation.copy()
    def step(self,action):
        # Same real step/validation as the baseline; retain its returned raw obs.
        if self.closed or self.steps>=500:raise RuntimeError('Cannot step a completed episode')
        action=np.asarray(action,dtype=np.float32)
        if action.shape!=(4,) or not np.isfinite(action).all() or np.any(np.abs(action)>1):raise RuntimeError('Invalid action')
        obs,reward,terminated,truncated,info=self.raw.step(action)
        self.steps+=1;self.costs.environment_steps+=1
        if terminated or bool(truncated)!=(self.steps==500):raise RuntimeError('Native termination contract changed')
        if getattr(self.raw,'_did_see_sim_exception',False):raise RuntimeError('Simulation exception')
        if not np.isfinite(reward) or not np.isfinite(self.raw.data.qpos).all() or not np.isfinite(self.raw.data.qvel).all():raise RuntimeError('Nonfinite physics/reward')
        if info.get('success') not in (0,1,0.,1.):raise RuntimeError('Missing official success')
        self.any_success|=bool(info['success'])
        self.last_raw_observation=obs.copy()
        self.observation=conditioned_observation(obs,self.task_index)
        return self.observation.copy(),float(reward),False,bool(truncated),dict(info)

def configure_streams(engine,streams):
    engine.reset_root=streams['environment']
    engine.schedule=AllocationSchedule('U',streams['schedule'])
    engine.warmup_rng=np.random.default_rng(streams['warmup_action'])
    seed_learning(streams['training_action_and_update'])
    np.random.seed(streams['replay'])

class UsageReplay(AuditedReplayBuffer):
    def setup_usage(self):
        n=self.buffer_size
        self.transition_ids=np.full(n,-1,dtype=np.int64)
        self.episode_ids=np.full(n,-1,dtype=np.int64)
        self.collection_versions=np.full(n,-1,dtype=np.int64)
        self.insertion_updates=np.full(n,-1,dtype=np.int64)
        self.critic_counts=np.zeros(n,dtype=np.int64);self.actor_counts=np.zeros(n,dtype=np.int64)
        self.first_updates=np.full(n,-1,dtype=np.int64);self.last_updates=np.full(n,-1,dtype=np.int64)
        self.usage_sink=None;self.next_metadata=None;self.current_update=0
    def usage_row(self,i,eviction=None):
        return {'transition_id':int(self.transition_ids[i]),'source_task_id':TASKS[int(self.observations[i,0,-4:].argmax())],
            'source_episode_id':int(self.episode_ids[i]),'collection_policy_version':int(self.collection_versions[i]),
            'collection_env_step':int(self.birth_steps[i]),'insertion_update':int(self.insertion_updates[i]),
            'buffer_slot':int(i),'buffer_generation':int((self.birth_steps[i]-1)//self.buffer_size),
            'critic_sample_count':int(self.critic_counts[i]),'actor_sample_count':int(self.actor_counts[i]),
            'first_sample_update':None if self.first_updates[i]<0 else int(self.first_updates[i]),
            'last_sample_update':None if self.last_updates[i]<0 else int(self.last_updates[i]),
            'eviction_update':eviction,'active_censored':eviction is None}
    def add(self,*args,**kwargs):
        i=self.pos
        if self.transition_ids[i]>=0 and self.usage_sink is not None:
            self.usage_sink.add(self.usage_row(i,int(self.next_metadata['insertion_update'])))
        super().add(*args,**kwargs)
        meta=self.next_metadata
        self.transition_ids[i]=meta['transition_id'];self.episode_ids[i]=meta['episode_id']
        self.collection_versions[i]=meta['policy_version'];self.insertion_updates[i]=meta['insertion_update']
        self.critic_counts[i]=self.actor_counts[i]=0;self.first_updates[i]=self.last_updates[i]=-1
    def _get_samples(self,batch_inds,env=None):
        result=super()._get_samples(batch_inds,env)
        # One sampled batch is actually used once by actor and once by both critics.
        # critic_count is batch usage, not multiplied by the number of Q networks.
        np.add.at(self.critic_counts,batch_inds,1);np.add.at(self.actor_counts,batch_inds,1)
        first=batch_inds[self.first_updates[batch_inds]<0]
        self.first_updates[first]=self.current_update;self.last_updates[batch_inds]=self.current_update
        return result
    def __getstate__(self):
        state=super().__getstate__();state['usage_sink']=None;state['next_metadata']=None
        return state
    def state_for_hash(self):
        d=super().state_for_hash();n=self.size()
        for name in ('transition_ids','episode_ids','collection_versions','insertion_updates','critic_counts','actor_counts','first_updates','last_updates'):
            d[name]=getattr(self,name)[:n]
        d['current_update']=self.current_update
        return d

class UpdateSink:
    def __init__(self,out,run_id):
        self.run_id=run_id;self.scalars=Table(Path(out)/'update_scalars')
        self.summary=Table(Path(out)/'update_summaries');self.batches=Table(Path(out)/'replay_usage/batch_samples')
        self.blocks=[];self.tasks=[];self.ages=[];self.first=1;self.end=0
    def record(self,model,values,grad):
        u=model._n_updates;r=model.replay_buffer;self.end=u
        vals=values.astype(np.float64,copy=False)
        row={'run_id':self.run_id,'actor_update_count':u,'critic_update_count':u,'env_step_total':model.num_timesteps,
            'actor_loss':float(model.logger.name_to_value['train/actor_loss']),
            'critic_loss':float(model.logger.name_to_value['train/critic_loss']),
            'alpha_loss':float(model.logger.name_to_value['train/ent_coef_loss']),
            'alpha_used':float(model.logger.name_to_value['train/ent_coef']),
            'alpha_after':float(model.log_ent_coef.detach().exp().item()),
            'critic_1_mse_derived':float(np.mean(vals[:,3]**2)),
            'critic_2_mse_derived':float(np.mean(vals[:,4]**2)),
            'q1_mean':float(vals[:,0].mean()),'q2_mean':float(vals[:,1].mean()),'target_q_mean':float(vals[:,2].mean()),
            'log_probability_mean':float(vals[:,5].mean()),'actor_lr':model.actor.optimizer.param_groups[0]['lr'],
            'critic_lr':model.critic.optimizer.param_groups[0]['lr'],'target_update_count':u,'replay_size':r.size(),
            'actor_gradient_norm':grad.get('actor'),'critic_gradient_norm':grad.get('critic')}
        self.scalars.add(row)
        ids=r.last_indices
        self.blocks.append(vals);self.tasks.append(r.observations[ids,0,-4:].argmax(axis=1))
        self.ages.append(model.num_timesteps-r.birth_steps[ids])
        if u%250==0:
            self.batches.add({'update':u,'env_step_total':model.num_timesteps,
                'transition_ids':r.transition_ids[ids].tolist(),'buffer_slots':ids.tolist()})
            self.flush_block()
    def flush_block(self):
        if not self.blocks:return
        values=np.concatenate(self.blocks);tasks=np.concatenate(self.tasks);age=np.concatenate(self.ages)
        names=('q1','q2','target_q','td1_signed','td2_signed','log_probability','target_min_q_before_entropy')
        for task in [-1,0,1,2,3]:
            mask=np.ones(len(tasks),dtype=bool) if task<0 else tasks==task
            for name,x in list(zip(names,values.T))+[('experience_age',age)]:
                a=x[mask]
                row={'run_id':self.run_id,'first_update':self.first,'last_update':self.end,
                    'env_step_total':self.end+1000,'task_id':'ALL' if task<0 else TASKS[task],
                    'variable':name,'count':len(a),'mean':float(a.mean()) if len(a) else None,
                    'std':float(a.std()) if len(a) else None,'min':float(a.min()) if len(a) else None,
                    'max':float(a.max()) if len(a) else None}
                for q in (.05,.25,.5,.75,.95):row[f'q{int(q*100):02d}']=float(np.quantile(a,q,method='linear')) if len(a) else None
                self.summary.add(row)
        self.first=self.end+1;self.blocks=[];self.tasks=[];self.ages=[]
    def flush(self):
        self.flush_block();self.scalars.flush();self.summary.flush();self.batches.flush()

class ObservationSAC(AuditedSAC):
    def _excluded_save_params(self):return super()._excluded_save_params()+['update_sink','last_policy_distribution']
    def train(self,gradient_steps,batch_size=64):
        self.replay_buffer.current_update=self._n_updates+1
        if getattr(self,'update_sink',None) is None:
            return super().train(gradient_steps,batch_size)
        if gradient_steps!=1:raise RuntimeError('Unexpected update frequency')
        logps=[];target=[];current=[];grad={}
        alpha=self.log_ent_coef.detach().exp().clone()
        original=self.actor.action_log_prob
        def act(*a,**kw):
            action,lp=original(*a,**kw);logps.append(lp.detach());return action,lp
        def tar(_m,_i,out):target.append(tuple(x.detach() for x in out))
        def cur(_m,_i,out):
            if not current:current.append(tuple(x.detach() for x in out))
        hooks=[self.critic_target.register_forward_hook(tar),self.critic.register_forward_hook(cur)]
        steps=[]
        if (self._n_updates+1)%250==0:
            for name,module in [('actor',self.actor),('critic',self.critic)]:
                opt=module.optimizer;step=opt.step
                def measured(*a,_name=name,_module=module,_step=step,**kw):
                    terms=[p.grad.detach().double().square().sum() for p in _module.parameters() if p.grad is not None]
                    grad[_name]=float(torch.stack(terms).sum().sqrt().item()) if terms else 0.
                    return _step(*a,**kw)
                opt.step=measured;steps.append((opt,step))
        self.actor.action_log_prob=act
        try:SAC.train(self,gradient_steps,batch_size)
        finally:
            del self.actor.action_log_prob
            for h in hooks:h.remove()
            for opt,step in steps:opt.step=step
        if len(logps)!=2 or len(target)!=1 or len(current)!=1:raise RuntimeError('Stock SAC update call structure changed')
        with torch.no_grad():
            samples=self.replay_buffer.last_samples
            tq=torch.cat(target[0],dim=1).min(dim=1,keepdim=True).values
            expected=samples.rewards+(1-samples.dones)*self.gamma*(tq-alpha*logps[1].reshape(-1,1))
            q1,q2=current[0]
            values=torch.cat((q1,q2,expected,q1-expected,q2-expected,logps[0].reshape(-1,1),tq),dim=1).cpu().numpy()
        if not np.isfinite(values).all() or not all(np.isfinite(float(self.logger.name_to_value[k])) for k in ('train/actor_loss','train/critic_loss','train/ent_coef_loss')):
            raise RuntimeError('Nonfinite SAC diagnostics; original baseline integrity rule')
        self.update_sink.record(self,values,grad)
        self.last_update_metrics={'actor_loss':float(self.logger.name_to_value['train/actor_loss']),
            'critic_loss':float(self.logger.name_to_value['train/critic_loss']),
            'entropy_loss':float(self.logger.name_to_value['train/ent_coef_loss']),
            'entropy_coefficient':float(self.log_ent_coef.detach().exp().item())}

def instrument(model,out,run_id,logging=True):
    model.__class__=ObservationSAC
    replay=model.replay_buffer
    if not isinstance(replay,UsageReplay):replay.__class__=UsageReplay;replay.setup_usage()
    model.update_sink=UpdateSink(out,run_id) if logging else None
    replay.usage_sink=Table(Path(out)/'replay_usage/evicted') if logging else None

class ObservedEngine(Engine):
    def __init__(self,config,costs,out,run_id,step_cost,model=None,logging=True):
        super().__init__(config,costs,model)
        self.out=Path(out);self.run_id=run_id;self.step_cost=step_cost;self.logging=logging
        self.id_prefix=(int(run_id[1:]) if run_id.startswith('R') else 99)*10000000
        self.episodes=Table(self.out/'episodes');self.snapshot_selected=set()
        self.traj=None;self.physics=None;self.snapshots=[];self.episode_serial=0;self.first_success=None;self.success_count=0
        instrument(self.model,out,run_id,logging)
    def boundary_state(self):
        d=super().boundary_state();d.update(episode_serial=self.episode_serial,snapshot_selected=sorted(self.snapshot_selected),
            policy_training_mode=self.model.policy.training)
        return d
    def restore_boundary_state(self,state):
        super().restore_boundary_state(state)
        self.episode_serial=state.get('episode_serial',sum(self.task_visits))
        self.snapshot_selected=set(tuple(x) for x in state.get('snapshot_selected',[]))
        self.model.policy.set_training_mode(state.get('policy_training_mode',False))
    def start_episode(self):
        task=self.schedule.next_task();seed=derived_seed(self.reset_root,20,task,int(self.task_visits[task]))
        self.task_visits[task]+=1
        self.episode=ObservedEpisode(task,seed,self.costs);self.observation=self.episode.observation.copy()
        self.step_cost.resets+=1;self.step_cost.creations+=1
        self.episode_return=0.;self.episode_serial+=1;self.first_success=None;self.success_count=0;self.snapshots=[]
        self.start_version=self.model._n_updates;self.start_counter=self.model.num_timesteps
        if self.logging:
            name=f'{self.episode_serial:06d}_{TASKS[task]}'
            self.traj=Trajectory(self.out/'training_transitions'/(name+'.npz'),{
                'experiment_id':self.config.version,'run_id':self.run_id,'attempt_id':'attempt_001','task_id':TASKS[task],
                'split_role':'train','env_instance_id':name,'episode_id':self.episode_serial,
                'initial_case_id':None,'checkpoint_id':None,'reset_seed':seed,'initial_state_hash':self.episode.initial_state_hash,
                'obs_raw_dtype':'float64','obs_policy_dtype':'float32','action_distribution':'pre-tanh mean and log_std',
                'success_semantics':'current raw official evaluate_state success, not a cumulative flag'})
            self.physics=Physics(self.episode)
            schema=self.out/'schema'/('env_feature_'+TASKS[task]+'.json')
            if not schema.exists():save(schema,self.physics.schema)
            key=(self.start_counter//100000,task)
            self.selected=key not in self.snapshot_selected
            if self.selected:
                self.snapshot_selected.add(key);self.take_snapshot(0)
    def take_snapshot(self,step):
        p=self.out/'environment_snapshots/train'/f'{self.episode_serial:06d}'/f'{step:03d}.pkl'
        self.snapshots.append(dump_snapshot(p,self.episode))
    def step(self):
        if self.at_boundary:self.start_episode()
        model=self.model;replay=model.replay_buffer;ep=self.episode
        before=self.observation.copy();raw_before=ep.last_raw_observation.copy();task=ep.task_index
        version=model._n_updates;distribution={}
        if model.num_timesteps<self.config.learning_starts:
            action=self.warmup_rng.uniform(-1,1,4).astype(np.float32);source=0
        else:
            source=1;original=model.actor.get_action_dist_params
            if self.logging:
                def observe(*a,**kw):
                    mean,logstd,extra=original(*a,**kw)
                    distribution['mean']=mean.detach().cpu().numpy().reshape(-1).copy()
                    distribution['log_std']=logstd.detach().cpu().numpy().reshape(-1).copy()
                    return mean,logstd,extra
                model.actor.get_action_dist_params=observe
            try:action,_=model.predict(before,deterministic=False)
            finally:
                if self.logging:del model.actor.get_action_dist_params
        pre_transform=action.copy();scaled=model.policy.scale_action(action);action=model.policy.unscale_action(scaled)
        next_obs,reward,terminated,truncated,info=self.step_cost.step(ep,action)
        physical=self.physics.sample() if self.logging else None
        replay.next_metadata={'transition_id':self.id_prefix+model.num_timesteps+1,'episode_id':self.episode_serial,
            'policy_version':version,'insertion_update':model._n_updates}
        replay.add(before[None],next_obs[None],scaled[None],np.array([reward],dtype=np.float32),
            np.array([terminated or truncated]),[{'TimeLimit.truncated':truncated and not terminated}])
        model.num_timesteps+=1;self.collected_steps[task]+=1;self.episode_return+=reward;self.observation=next_obs
        if info['success']:
            self.success_count+=1
            if self.first_success is None:self.first_success=ep.steps
        if model.num_timesteps>self.config.learning_starts:
            previous=model._n_updates
            try:model.train(gradient_steps=1,batch_size=self.config.batch_size)
            finally:self.costs.train_iterations+=model._n_updates-previous
        if model._n_updates!=max(0,model.num_timesteps-self.config.learning_starts) or replay.total_added!=model.num_timesteps:
            raise RuntimeError('Collector/update counter discrepancy')
        record={'step':model.num_timesteps,'task':task,'observation':before,'action':action.copy(),
            'next_observation':next_obs.copy(),'reward':reward,'terminated':terminated,'truncated':truncated,
            'success':bool(info['success']),'updates':model._n_updates}
        if self.logging:
            info_values={k:float(v) for k,v in info.items() if isinstance(v,(int,float,np.number,bool))}
            # Task-specific info keys are constant within an episode; stored as numerical columns.
            self.traj.add(transition_id=self.id_prefix+model.num_timesteps,episode_step=ep.steps,env_step_total=model.num_timesteps,
                actor_update_count=model._n_updates,critic_update_count=model._n_updates,policy_version=version,
                obs_policy=before,obs_raw=raw_before,action_executed=action.copy(),action_pre_transform=pre_transform,
                next_obs_actual=next_obs.copy(),next_obs_raw_actual=ep.last_raw_observation.copy(),reward=reward,
                success_step=int(info['success']),terminated=terminated,truncated=truncated,action_source=source,
                validity_status=1,bootstrap_mask=float(not terminated),
                policy_mean=distribution.get('mean',np.full(4,np.nan,dtype=np.float32)),
                policy_log_std=distribution.get('log_std',np.full(4,np.nan,dtype=np.float32)),
                **{'info_'+k:v for k,v in info_values.items()},**physical)
            if self.selected and (ep.steps%50==0 or terminated or truncated):self.take_snapshot(ep.steps)
        if terminated or truncated:self.finish_episode('time_limit' if truncated else 'environment_terminated',True,int(info['success']))
        return record
    def finish_episode(self,reason,complete,last_success):
        ep=self.episode
        if self.logging:
            if self.selected and ep.steps%50!=0:self.take_snapshot(ep.steps)
            trajectory=self.traj.flush()
            self.episodes.add({'run_id':self.run_id,'attempt_id':'attempt_001','split_role':'train',
                'episode_id':self.episode_serial,'task_id':TASKS[ep.task_index],'initial_case_id':None,'checkpoint_id':None,
                'start_env_step':self.start_counter,'end_env_step':self.model.num_timesteps,
                'episode_return':self.episode_return,'episode_length':ep.steps,'success_any':int(ep.any_success),
                'success_final':last_success,'first_success_step':self.first_success,'success_step_count':self.success_count,
                'terminated':False,'truncated':complete,'end_reason':reason,'episode_complete':complete,
                'policy_version_start':self.start_version,'policy_version_end':self.model._n_updates,
                'trajectory_ref':trajectory,'video_ref':None,'snapshot_refs':self.snapshots,
                'initial_state_hash':ep.initial_state_hash})
        self.last_episode={'task':TASKS[ep.task_index],'success':ep.any_success,'return':self.episode_return,'length':ep.steps,
            'initial_state_hash':ep.initial_state_hash}
        ep.close();self.episode=None;self.observation=None;self.traj=None;self.physics=None
    def flush(self):
        self.episodes.flush()
        if self.model.update_sink is not None:self.model.update_sink.flush()
        if self.model.replay_buffer.usage_sink is not None:self.model.replay_buffer.usage_sink.flush()
