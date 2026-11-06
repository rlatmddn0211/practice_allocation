"""SAC continuation adapter over an exact, local frozen copy of implementation81."""
from __future__ import annotations
from common import *
os.environ['PRACTICE_SUITE']='B'
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
sys.path.insert(0,str(HERE/'baseline81'))
import copy
import pickle
import numpy as np
import pandas as pd
import torch
from contextlib import contextmanager
from detector import derived_seed as keyed_seed
from sampler_contract import replacement_fields
from practice_allocation.core import Config, configure_runtime, capture_rng, restore_rng, fingerprint, source_hashes, package_versions, seed_learning
from practice_allocation.environment import CostCounter
from practice_allocation.engine import save_checkpoint
from practice_allocation.learning import AuditedReplayBuffer, learning_state, attach_logger
from learner import ObservationSAC, ObservedEngine, UsageReplay, UpdateSink
from records import Table, Trajectory, Physics, Video, Cost, save as baseline_save
import checkpoints as original_checkpoints
from evaluation import rollout as original_rollout

def initialize_runtime():
    config=Config.load(HERE/'baseline81/configs/learner.json',device='cuda')
    configure_runtime(config)
    return dict(packages=package_versions(),gpu=torch.cuda.get_device_name(0),torch_threads=torch.get_num_threads(),
        source_hashes=source_hashes(),device='cuda',pid=os.getpid())

def load_archive(preparation,parent,arm):
    preparation=Path(preparation);manifest=load(preparation/'loo_archive_manifest.json')[parent]
    windows=pd.read_parquet(preparation/'archive_windows.parquet')
    window_lookup={(r.permanent_episode_id,r.arm):int(i) for i,r in windows.iterrows()}
    cols={'observations':'obs_policy','actions':'action_executed','next_observations':'next_obs_actual',
        'rewards':'reward','transition_ids':'transition_id'}
    result={k:[] for k in cols};result['dones']=[]
    ids=manifest['permanent_episode_ids']
    with np.load(preparation/'selected_window_arrays.npz',allow_pickle=False) as z:
        for ep in ids:
            index=window_lookup[(ep,arm if arm!='BASE' else 'ONSET')]
            for field,original in cols.items():
                values=z[f'{index:03d}_{original}'].copy()
                if field=='rewards':values=values.astype(np.float32).reshape(32,1)
                result[field].append(values)
            terminated=z[f'{index:03d}_terminated'];truncated=z[f'{index:03d}_truncated']
            # Match ReplayBuffer._get_samples' TimeLimit.truncated correction.
            done=(terminated|truncated).astype(np.float32)*(1-(truncated&~terminated).astype(np.float32))
            result['dones'].append(done.reshape(32,1))
    result={k:np.stack(v) for k,v in result.items()}
    if any(len(v)!=len(ids) for v in result.values()):raise RuntimeError('Archive episode mapping failed')
    if not np.all(result['observations'][:,:,-4:]==[1,0,0,0]):raise RuntimeError('Archive changed task labels')
    return result,ids

class PilotSAC(ObservationSAC):
    def predict(self,observation,state=None,episode_start=None,deterministic=False):
        if deterministic or not hasattr(self,'pilot_streams'):
            return super().predict(observation,state,episode_start,deterministic)
        # Separate keyed rollout action RNG from the original stochastic SAC
        # update stream. Only RNG state is exchanged; no policy/optimizer reset.
        seed=keyed_seed('onset_reuse_pilot_v1',int(self.pilot_streams['rollout_action']),int(self.num_timesteps))%(2**63-1)
        devices=list(range(torch.cuda.device_count())) if self.device.type=='cuda' else []
        with torch.random.fork_rng(devices=devices,enabled=True):
            torch.manual_seed(seed)
            return super().predict(observation,state,episode_start,False)

class PilotReplay(UsageReplay):
    def prepare_pilot(self,context,archive,episode_ids,streams,probability):
        self.pilot_context=dict(context);self.pilot_streams=dict(streams);self.pilot_probability=float(probability)
        self.archive_arrays=archive;self.archive_episode_ids=list(episode_ids)
        self.archive_counts=np.zeros((len(episode_ids),32),dtype=np.int64)
        self.pilot_native_draws=0;self.pilot_native_actual=0;self.pilot_archive_actual=0
        self.pilot_native_tasks=np.zeros(4,dtype=np.int64)
        self.pilot_draw_digest=bytes(32);self.pilot_mask_digest=bytes(32)
        self.pilot_last_hash=None;self.pilot_last_mask=np.zeros(256,dtype=bool)
        self._build_tensors()
    def _build_tensors(self):
        self.archive_tensors={k:torch.as_tensor(v,device=self.device) for k,v in self.archive_arrays.items() if k!='transition_ids'}
    def _get_samples(self,batch_inds,env=None):
        native=AuditedReplayBuffer._get_samples(self,batch_inds,env)
        ids=self.observations[batch_inds,0,-4:].argmax(axis=1)
        fields,episodes,offsets,draw_hash=replacement_fields('onset_reuse_pilot_v1',self.pilot_context['parent_id'],self.pilot_context['future_id'],
            self.current_update, len(batch_inds),len(self.archive_episode_ids),int(self.pilot_streams['archive_replacement']))
        mask=(ids==0)&(fields<self.pilot_probability)
        retained=batch_inds[~mask]
        np.add.at(self.critic_counts,retained,1);np.add.at(self.actor_counts,retained,1)
        first=retained[self.first_updates[retained]<0]
        self.first_updates[first]=self.current_update;self.last_updates[retained]=self.current_update
        final_ids=self.transition_ids[batch_inds].copy()
        ages=self.total_added-self.birth_steps[batch_inds]
        changed={}
        if mask.any():
            where=np.flatnonzero(mask);ei=episodes[mask];oi=offsets[mask]
            wi=torch.as_tensor(where,device=self.device);et=torch.as_tensor(ei,device=self.device);ot=torch.as_tensor(oi,device=self.device)
            for name in ('observations','actions','next_observations','rewards','dones'):
                tensor=getattr(native,name).clone();tensor[wi]=self.archive_tensors[name][et,ot];changed[name]=tensor
            np.add.at(self.archive_counts,(ei,oi),1)
            final_ids[mask]=self.archive_arrays['transition_ids'][ei,oi]
            ages[mask]=self.total_added-(final_ids[mask]%10000000)
        result=native._replace(**changed) if changed else native
        self.last_samples=result;self.pilot_last_mask=mask;self.pilot_last_hash=draw_hash
        self.pilot_last_final_ids=final_ids;self.pilot_last_ages=ages
        self.pilot_native_draws+=len(batch_inds);self.pilot_native_actual+=len(retained);self.pilot_archive_actual+=int(mask.sum())
        self.pilot_native_tasks+=np.bincount(ids,minlength=4)
        self.pilot_draw_digest=hashlib.sha256(self.pilot_draw_digest+bytes.fromhex(draw_hash)).digest()
        self.pilot_mask_digest=hashlib.sha256(self.pilot_mask_digest+mask.tobytes()).digest()
        return result
    def state_for_hash(self):
        base=super().state_for_hash()
        if hasattr(self,'pilot_context'):
            base['pilot']={k:getattr(self,k) for k in ('pilot_context','pilot_streams','pilot_probability','archive_arrays','archive_episode_ids',
                'archive_counts','pilot_native_draws','pilot_native_actual','pilot_archive_actual','pilot_native_tasks')}
            base['pilot']['draw_digest']=self.pilot_draw_digest.hex();base['pilot']['mask_digest']=self.pilot_mask_digest.hex()
        return base
    def __getstate__(self):
        result=super().__getstate__();result.pop('archive_tensors',None)
        return result

class PilotUpdateSink(UpdateSink):
    def record(self,model,values,grad):
        u=model._n_updates;r=model.replay_buffer;self.end=u;v=values.astype(np.float64,copy=False)
        self.scalars.add({'run_id':self.run_id,**r.pilot_context,'actor_update_count':u,'critic_update_count':u,'env_step_total':model.num_timesteps,
            'actor_loss':float(model.logger.name_to_value['train/actor_loss']),'critic_loss':float(model.logger.name_to_value['train/critic_loss']),
            'alpha_loss':float(model.logger.name_to_value['train/ent_coef_loss']),'alpha_used':float(model.logger.name_to_value['train/ent_coef']),
            'alpha_after':float(model.log_ent_coef.detach().exp().item()),'q1_mean':float(v[:,0].mean()),'q2_mean':float(v[:,1].mean()),
            'target_q_mean':float(v[:,2].mean()),'critic_1_mse_derived':float(np.mean(v[:,3]**2)),
            'critic_2_mse_derived':float(np.mean(v[:,4]**2)),'log_probability_mean':float(v[:,5].mean()),
            'actor_lr':model.actor.optimizer.param_groups[0]['lr'],'critic_lr':model.critic.optimizer.param_groups[0]['lr'],
            'target_update_count':u,'replay_size':r.size(),'actor_gradient_norm':grad.get('actor'),'critic_gradient_norm':grad.get('critic'),
            'native_DO_slots':int(r.last_task_counts[0]),'replaced_DO_slots':int(r.pilot_last_mask.sum()),'common_draw_hash':r.pilot_last_hash})
        self.blocks.append(v);self.tasks.append(r.observations[r.last_indices,0,-4:].argmax(axis=1));self.ages.append(r.pilot_last_ages.copy())
        if u%250==0:
            self.batches.add({'update':u,'env_step_total':model.num_timesteps,'native_draw_transition_ids':r.transition_ids[r.last_indices].tolist(),
                'actual_final_transition_ids':r.pilot_last_final_ids.tolist(),'replacement_mask':r.pilot_last_mask.tolist(),
                'common_draw_hash':r.pilot_last_hash})
            self.flush_block()

class PilotEngine(ObservedEngine):
    def boundary_state(self):
        result=super().boundary_state()
        if hasattr(self,'pilot_context'):result['pilot_context']=copy.deepcopy(self.pilot_context)
        return result
    def restore_boundary_state(self,state):
        super().restore_boundary_state(state)
        if 'pilot_context' in state:self.pilot_context=copy.deepcopy(state['pilot_context'])
    def start_episode(self):
        super().start_episode()
        if self.logging:self.traj.meta.update(experiment_id='85_onset_reuse_pilot_v1',**self.pilot_context)

def restore_parent(parent,cost,out):
    counters=CostCounter()
    engine=original_checkpoints.restore(CAMPAIGN/'runs'/parent/'checkpoints/full/1000000',counters,out,parent,cost,logging=True)
    if not engine.at_boundary or engine.schedule.position!=8 or len(engine.schedule.block)!=8:
        raise RuntimeError('Original parent is not the expected exhausted 8-episode block boundary')
    return engine

def configure_future(engine,preparation,context,streams,probability=None):
    if not engine.at_boundary or engine.model.num_timesteps!=1000000:raise RuntimeError('Future must begin at exact original full boundary')
    before=engine.fingerprints();original_schedule=engine.schedule.state()
    # Preserve exhausted block, block count, task visits, counters and replay.
    engine.schedule.rng=np.random.Generator(np.random.PCG64(int(streams['task_order'])))
    engine.reset_root=int(streams['reset_goal'])
    seed_learning(int(streams['learning_action']));np.random.seed(int(streams['native_replay']))
    archive,episode_ids=load_archive(preparation,context['parent_id'],context['arm'])
    engine.__class__=PilotEngine;engine.pilot_context=dict(context)
    engine.model.__class__=PilotSAC;engine.model.pilot_streams=dict(streams)
    r=engine.model.replay_buffer;r.__class__=PilotReplay
    p=(0. if context['arm']=='BASE' else .25) if probability is None else probability
    r.prepare_pilot(context,archive,episode_ids,streams,p)
    engine.model.update_sink=PilotUpdateSink(engine.out,engine.run_id)
    engine.model.update_sink.first=engine.model._n_updates+1
    # Distinct numeric namespace for newly collected transitions; source archive
    # keeps its immutable original permanent IDs. Cell context is always retained.
    engine.id_prefix=1000000000+int(context['cell_number'])*10000000
    after_learning=fingerprint(learning_state(engine.model))
    if after_learning!=before['learning']:raise RuntimeError('RNG-only setup changed model or optimizer')
    return dict(before=before,after=engine.fingerprints(),preserved_learning=True,
        preserved_schedule_fields={k:original_schedule[k] for k in ('candidate','block','position','blocks_generated')},
        changes=['schedule RNG','reset root','NumPy native-replay RNG','PyTorch learner RNG','keyed rollout RNG','read-only archive sampler metadata','new-transition provenance namespace'],
        learner_counter=engine.model.num_timesteps,updates=engine.model._n_updates,task_visits=engine.task_visits.tolist(),
        collected_steps=engine.collected_steps.tolist(),replay_pointer=r.pos,replacement_probability=p)

def usage_snapshot(engine,dest):
    r=engine.model.replay_buffer;table=Table(Path(dest)/'archive_usage',flush_rows=10000)
    for i,ep in enumerate(r.archive_episode_ids):
        donor=ep.split(':')[0]
        for offset in range(32):
            count=int(r.archive_counts[i,offset])
            table.add({**r.pilot_context,'checkpoint':engine.model.num_timesteps,'donor_run':donor,'source_episode_id':ep,
                'archive_transition_id':int(r.archive_arrays['transition_ids'][i,offset]),'window_offset':offset,
                'actor_sample_count':count,'critic_sample_count':count})
    table.flush()
    summary={**r.pilot_context,'actual_train_step':engine.model.num_timesteps,'update_id':engine.model._n_updates,
        'native_draw_count':r.pilot_native_draws,'native_actual_use':r.pilot_native_actual,'archive_actual_use':r.pilot_archive_actual,
        'native_task_draw_counts':r.pilot_native_tasks.tolist(),'archive_draw_hash':r.pilot_draw_digest.hex(),'replacement_mask_hash':r.pilot_mask_digest.hex(),
        'archive_actor_use':int(r.archive_counts.sum()),'archive_critic_use':int(r.archive_counts.sum())}
    if summary['native_actual_use']+summary['archive_actual_use']!=summary['native_draw_count']:raise RuntimeError('Actual-use accounting mismatch')
    if summary['archive_actual_use']!=summary['archive_actor_use']:raise RuntimeError('Archive usage counter mismatch')
    save(Path(dest)/'usage_summary.json',summary)
    return summary

def save_full(engine,path):
    path=Path(path);tmp=path.with_name(path.name+'.partial')
    if path.exists() or tmp.exists():raise FileExistsError(path)
    engine.flush();save_checkpoint(engine,tmp)
    active=Table(tmp/'active_replay_usage',flush_rows=10000)
    for i in range(engine.model.replay_buffer.size()):active.add(engine.model.replay_buffer.usage_row(i))
    active.flush()
    save(tmp/'pilot_resume_metadata.json',dict(protocol_version='85_onset_reuse_pilot_v1',context=engine.pilot_context,
        streams=engine.model.pilot_streams,id_prefix=engine.id_prefix,
        pilot_source_hashes={p.name:sha(p) for p in HERE.glob('*.py')}))
    save(tmp/'COMPLETE.json',dict(kind='full_pilot_boundary',environment_active=False,
        checkpoint_manifest_sha256=sha(tmp/'checkpoint_manifest.json'),pilot_metadata_sha256=sha(tmp/'pilot_resume_metadata.json')))
    path.parent.mkdir(parents=True,exist_ok=True);os.replace(tmp,path)

def restore_full(path,cost,out):
    path=Path(path);manifest=load(path/'checkpoint_manifest.json');meta=load(path/'pilot_resume_metadata.json')
    complete=load(path/'COMPLETE.json')
    if sha(path/'checkpoint_manifest.json')!=complete['checkpoint_manifest_sha256'] or sha(path/'pilot_resume_metadata.json')!=complete['pilot_metadata_sha256']:raise RuntimeError('Incomplete pilot checkpoint')
    if manifest['source_hashes']!=source_hashes() or manifest['packages']!=package_versions():raise RuntimeError('Baseline restore code/dependency mismatch')
    for relative,digest in meta['pilot_source_hashes'].items():
        if sha(HERE/relative)!=digest:raise RuntimeError('Pilot source changed after checkpoint')
    for relative,digest in manifest['files'].items():
        if sha(path/relative)!=digest:raise RuntimeError('Pilot checkpoint payload hash mismatch')
    with (path/'collector_and_rng.pkl').open('rb') as f:state=pickle.load(f)
    config=Config(**state['config']);model=PilotSAC.load(path/'model.zip',device=config.device)
    model.load_replay_buffer(path/'replay.pkl');attach_logger(model)
    engine=ObservedEngine(config,CostCounter(),out,meta['context']['parent_id'],cost,model=model,logging=True)
    engine.__class__=PilotEngine;engine.model.__class__=PilotSAC
    engine.restore_boundary_state(state['collector']);engine.id_prefix=int(meta['id_prefix'])
    engine.model.update_sink=PilotUpdateSink(engine.out,engine.run_id);engine.model.update_sink.first=model._n_updates+1
    engine.model.replay_buffer._build_tensors();restore_rng(state['rng'])
    if engine.fingerprints()!=manifest['state_fingerprints']:raise RuntimeError('Pilot full restore differs')
    return engine

def evaluate(engine,cases,out,relative_step,cost,checkpoint_hash,cell_number,video=False):
    """Original evaluator's deterministic full-horizon loop, with unique pilot IDs."""
    out=Path(out);before=engine.fingerprints();rng_before=fingerprint(capture_rng());rows=[]
    with __import__('practice_allocation.core',fromlist=['isolated_rng']).isolated_rng():
        policy=copy.deepcopy(engine.model.policy);policy.set_training_mode(False)
        counters=CostCounter()
        from pilot_evaluation import rollout as pilot_rollout
        for case in cases:
            context=getattr(engine,'pilot_context',{'parent_id':engine.run_id,'future_id':None,'arm':'SHARED_START','cell_number':cell_number})
            row=pilot_rollout(policy,case,out,engine.run_id,int(engine.model.num_timesteps),relative_step,context,checkpoint_hash,cost,counters,video=video)
            rows.append(row)
        del policy
    if engine.fingerprints()!=before or fingerprint(capture_rng())!=rng_before:raise RuntimeError('Evaluation changed training state or RNG')
    table=Table(out/'evaluation_episodes',flush_rows=64)
    for row in rows:table.add(row)
    table.flush()
    save(out/'evaluation_receipts'/f'{relative_step:06d}.json',dict(actual_train_step=engine.model.num_timesteps,relative_step=relative_step,
        episodes=len(rows),state_unchanged=True,before=before,after=engine.fingerprints(),counter=counters.snapshot()))
    return rows
