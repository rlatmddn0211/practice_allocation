"""Read immutable SAC snapshots; measure two episode-disjoint replay panels."""
from __future__ import annotations
import argparse
import csv
import gc
import gzip
import json
import lzma
import pickle
import time
import traceback
from pathlib import Path

import numpy as np
import torch
from stable_baselines3 import SAC
from stable_baselines3.common.buffers import ReplayBuffer

from common import Run, HERE, allocations, campaign, contexts, prefix, record, save, seed_for, table

def fingerprint(value):
    # Canonical format from the frozen learner core, independently copied here.
    import hashlib
    digest=hashlib.sha256()
    def visit(item):
        if isinstance(item,torch.Tensor):
            item=item.detach().cpu().contiguous().numpy()
        if isinstance(item,np.ndarray):
            digest.update(b'array'+str(item.dtype).encode()+str(item.shape).encode())
            digest.update(np.ascontiguousarray(item).tobytes())
        elif isinstance(item,dict):
            digest.update(b'dict')
            for k in sorted(item,key=lambda x:(type(x).__name__,str(x))):
                visit(k);visit(item[k])
        elif isinstance(item,(tuple,list)):
            digest.update(type(item).__name__.encode()+str(len(item)).encode())
            for child in item:visit(child)
        elif isinstance(item,np.generic):visit(item.item())
        elif item is None or isinstance(item,(str,bool,int,float)):
            digest.update(type(item).__name__.encode()+b':'+repr(item).encode()+b';')
        else:raise TypeError(type(item))
    visit(value)
    return digest.hexdigest()

def learning_state(m):
    return {'parameters_and_optimizers':m.get_parameters(),'log_entropy_coefficient':m.log_ent_coef,
            'num_timesteps':m.num_timesteps,'n_updates':m._n_updates,'target_entropy':m.target_entropy}

def replay_state(b):
    n=b.size()
    names=['observations','next_observations','actions','rewards','dones','timeouts','birth_steps']
    state={k:getattr(b,k)[:n] for k in names}
    state.update({k:getattr(b,k) for k in ['pos','full','total_added','branch_start_step','sampled_task_counts',
                                        'sampled_new_count','sampled_total','last_indices']})
    return state

class ReplayReader(pickle.Unpickler):
    def find_class(self,module,name):
        if module=='practice_allocation.learning' and name=='AuditedReplayBuffer':
            return ReplayBuffer
        return super().find_class(module,name)

def load_snapshot(run,ref,device):
    d=Path(ref['path'])
    manifest=run.read(d/'checkpoint_manifest.json',ref['manifest_sha256'])
    run.check('lossless schema2 '+str(d),manifest['schema_version']==2)
    for name,digest in manifest['files'].items():
        run.check('safe file name',Path(name).name==name)
        run.hashed(d/name,digest)
    import importlib.metadata
    for name,version in manifest['packages'].items():
        run.check('package '+name,importlib.metadata.version(name)==version)
    # Only repository-generated, manifest-verified pickle/model artifacts are read.
    model=SAC.load(d/'model.zip',device=device,custom_objects={'replay_buffer_class':ReplayBuffer})
    with lzma.open(d/'replay.pkl.xz','rb') as f:
        replay=ReplayReader(f).load()
    model.policy.set_training_mode(False)
    run.check('learner restored '+str(d),fingerprint(learning_state(model))==manifest['state_fingerprints']['learning'])
    run.check('replay restored '+str(d),fingerprint(replay_state(replay))==manifest['state_fingerprints']['replay'])
    return model,replay,manifest

def choose_panels(run,b,p,key):
    births=b.birth_steps[:b.size()]
    ids=b.observations[:b.size(),0,-4:].argmax(1)
    onehot=b.observations[:b.size(),0,-4:]
    run.check('onehot '+key,np.isin(onehot,[0,1]).all() and (onehot.sum(1)==1).all())
    ep=(births-1)//500
    unique,counts=np.unique(ep,return_counts=True)
    run.check('complete500step episodes '+key,(counts==500).all() and np.unique(births).size==len(births))
    run.check('verified episode boundaries '+key,np.array_equal(b.dones[:b.size(),0],(births%500==0).astype(float)))
    run.check('timeouts masked '+key,np.array_equal(b.timeouts[:b.size(),0],b.dones[:b.size(),0]))
    result=[]
    for t in range(4):
        episodes=np.unique(ep[ids==t])
        run.check('single task per episode '+key+str(t),all((ids[ep==e]==t).all() for e in episodes))
        groups=[[],[]]
        for pos in range(0,len(episodes),2):
            pair=episodes[pos:pos+2]
            flip=seed_for(p['panel']['seed'],key,t,int(pair[0]))%2
            for j,e in enumerate(pair):groups[(flip+j)%2].append(e)
        selected=[]
        for pi,eps in enumerate(groups):
            pool=np.flatnonzero((ids==t)&np.isin(ep,eps))
            pool=pool[np.argsort(births[pool])]
            rng=np.random.default_rng(seed_for(p['panel']['seed'],key,t,pi))
            strata=np.array_split(pool,p['panel']['age_strata'])
            n=p['panel']['samples_per_task_per_panel']//len(strata)
            run.check('enough panel samples '+key+str((t,pi)),all(len(s)>=n for s in strata))
            ix=np.concatenate([rng.choice(s,n,replace=False) for s in strata])
            result.append((t,pi,ix))
            selected.append(ix)
        run.check('disjoint episodes '+key+str(t),not set(ep[selected[0]])&set(ep[selected[1]]))
    return result

def summarize(raw):
    q0,q1,y=(raw[n].astype(np.float64) for n in ['q0','q1','target'])
    residual=np.sqrt(np.mean(((q0-y)**2+(q1-y)**2)/2))
    gap=np.sqrt(np.mean((q0-q1)**2))
    scale=max(float(np.sqrt(np.mean(y*y))),1e-6)
    return {'residual_rms':float(residual),'gap_rms':float(gap),'target_rms':scale,
            'residual_normalized':float(residual/scale),'gap_normalized':float(gap/scale),
            'reward_rms':float(np.sqrt(np.mean(raw['reward'].astype(float)**2))),
            'q_mean':float(np.mean((q0+q1)/2)),'target_mean':float(y.mean()),
            'target_mc_sd_mean':float(np.mean(raw['target_mc_sd'].astype(np.float64))),
            'timeout_count':int(raw['timeout'].sum()),'sample_count':len(y)}

def measure_one(run,entry,ref,p,device,rawdir):
    key=entry['id'];start=time.perf_counter()
    m,b,manifest=load_snapshot(run,ref,device)
    before_model=fingerprint(learning_state(m));before_replay=fingerprint(replay_state(b))
    run.check('step matches '+key,m.num_timesteps==entry['checkpoint_step']+entry['horizon'])
    run.check('task order '+key,list(manifest['tasks'])==p['suites'][entry['suite']])
    panels=choose_panels(run,b,p,key)
    rawpath=rawdir/(key+'.csv.gz')
    rows=[];batches=[];gpu_ms=0.;forward_wall=0.
    with gzip.open(rawpath,'xt',encoding='utf-8',newline='',compresslevel=6) as f:
        writer=None
        for task,panel,ix in panels:
            def tensor(a):return torch.as_tensor(a,device=device)
            obs=tensor(b.observations[ix,0]);next_obs=tensor(b.next_observations[ix,0]);act=tensor(b.actions[ix,0])
            rewards=tensor(b.rewards[ix,0]).reshape(-1,1)
            masks=tensor(1-b.dones[ix,0]*(1-b.timeouts[ix,0])).reshape(-1,1)
            begin=time.perf_counter()
            start_event=end_event=None
            if device=='cuda':
                start_event=torch.cuda.Event(enable_timing=True);end_event=torch.cuda.Event(enable_timing=True)
                start_event.record()
            with torch.no_grad(),torch.random.fork_rng(devices=[0] if device=='cuda' else []):
                torch.manual_seed(seed_for(p['panel']['seed'],key,task,panel,'actions'))
                alpha=float(m.log_ent_coef.detach().exp().item())
                q0,q1=m.critic(obs,act)
                qns=[];lps=[];targets=[]
                for k in range(p['panel']['target_action_draws']):
                    next_action,lp=m.actor.action_log_prob(next_obs)
                    qn=torch.cat(m.critic_target(next_obs,next_action),1).min(1,keepdim=True).values
                    lp=lp.reshape(-1,1)
                    targets.append(rewards+m.gamma*masks*(qn-alpha*lp))
                    qns.append(qn);lps.append(lp)
                yy=torch.stack(targets).mean(0)
                mc_sd=torch.stack(targets).std(0,unbiased=True)
            if device=='cuda':
                end_event.record();end_event.synchronize();gpu_ms+=start_event.elapsed_time(end_event)
            forward_wall+=time.perf_counter()-begin
            raw={'task':np.full(len(ix),task),'panel':np.full(len(ix),panel),
                 'stratum':np.repeat(np.arange(8),128),'storage_index':ix,'birth_step':b.birth_steps[ix],
                 'q0':q0.cpu().numpy().ravel(),'q1':q1.cpu().numpy().ravel(),
                 'reward':b.rewards[ix,0],'done':b.dones[ix,0],'timeout':b.timeouts[ix,0],
                 'target':yy.cpu().numpy().ravel(),'target_mc_sd':mc_sd.cpu().numpy().ravel(),
                 'alpha':np.full(len(ix),alpha),'gamma':np.full(len(ix),m.gamma)}
            for k,(qn,lp) in enumerate(zip(qns,lps)):
                raw['next_min_q_'+str(k)]=qn.cpu().numpy().ravel()
                raw['next_logp_'+str(k)]=lp.cpu().numpy().ravel()
            run.check('finite diagnostic '+key+str((task,panel)),all(np.isfinite(v).all() for v in raw.values()))
            # Compare timeout/action/observation handling to the installed ReplayBuffer.
            old_device=b.device;b.device=torch.device(device)
            sampled=ReplayBuffer._get_samples(b,ix)
            b.device=old_device
            run.check('SB3 replay semantics '+key+str((task,panel)),
                      torch.equal(sampled.observations,obs) and torch.equal(sampled.actions,act)
                      and torch.equal(sampled.next_observations,next_obs)
                      and torch.equal(sampled.rewards,rewards) and torch.equal(1-sampled.dones,masks))
            row={**entry,'task':p['suites'][entry['suite']][task],'panel':'M' if panel==0 else 'A',**summarize(raw)}
            rows.append(row)
            for bi in range(8):
                subset={name:arr[bi*128:(bi+1)*128] for name,arr in raw.items()}
                batches.append({**entry,'task':row['task'],'panel':row['panel'],'stratum':bi,**summarize(subset)})
            if writer is None:
                writer=csv.writer(f);writer.writerow(list(raw))
            for j in range(len(ix)):
                writer.writerow([v[j].item() for v in raw.values()])
    run.check('no model update '+key,fingerprint(learning_state(m))==before_model)
    run.check('no replay mutation '+key,fingerprint(replay_state(b))==before_replay)
    d=Path(ref['path'])
    for name,digest in manifest['files'].items():run.hashed(d/name,digest)
    run.hashed(d/'checkpoint_manifest.json',ref['manifest_sha256'])
    from common import sha
    timing={**entry,'checkpoint':ref,'raw_path':str(rawpath),'raw_sha256':sha(rawpath),
            'wall_seconds':time.perf_counter()-start,'forward_wall_seconds':forward_wall,'gpu_forward_seconds':gpu_ms/1000,
            'model_state_hash':before_model,'replay_state_hash':before_replay,
            'samples':sum(r['sample_count'] for r in rows),'alpha':alpha,'gamma':m.gamma}
    del m,b
    gc.collect()
    return rows,batches,timing

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--smoke',action='store_true');parser.add_argument('--device',default='cuda')
    args=parser.parse_args();run=Run('smoke' if args.smoke else 'measure')
    try:
        p=run.read(HERE/'protocol.json');cam,planned=campaign(run)
        torch.set_num_threads(4)
        if args.device=='cuda':torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
        schedule=[]
        for ctx in contexts(p):
            s,n,c=ctx;pre=prefix(ctx)
            base,path=record(run,cam,planned,pre+'_base')
            req=run.read(path.parent/'request.json')
            schedule.append(({'id':pre+'_base','suite':s,'original_seed':n,'checkpoint_step':c,'horizon':0,'continuation':0,'allocation':'parent'},req['parent']))
            for rep in p['continuations'][s]:
                for a in allocations(p,s):
                    jid=pre+f'_r{rep}_{a}_t20';rec,path=record(run,cam,planned,jid)
                    schedule.append(({'id':jid,'suite':s,'original_seed':n,'checkpoint_step':c,'horizon':20000,'continuation':rep,'allocation':a},rec['checkpoint']))
        run.check('192 planned snapshots',len(schedule)==p['expected_snapshots'])
        if args.smoke:schedule=schedule[:2]
        save(run.out/'schedule.json',[dict(e,checkpoint=r) for e,r in schedule])
        rawdir=run.out/'raw';rawdir.mkdir()
        rows=[];batches=[];timings=[]
        for i,(entry,ref) in enumerate(schedule):
            rr,bb,tt=measure_one(run,entry,ref,p,args.device,rawdir)
            rows+=rr;batches+=bb;timings.append(tt)
            save(run.out/(entry['id']+'_completed.json'),{'task_rows':rr,'batch_rows':bb,'timing':tt})
            print(f"measured {i+1}/{len(schedule)} {entry['id']} {tt['wall_seconds']:.2f}s",flush=True)
        table(run.out/'task_diagnostics.csv',rows);table(run.out/'batch_diagnostics.csv',batches)
        save(run.out/'snapshot_manifest.json',timings)
        run.finish({'status':'completed','technical_smoke':args.smoke,'snapshots':len(timings),'task_panel_rows':len(rows),
                    'transitions_measured':sum(t['samples'] for t in timings),'gpu_forward_seconds':sum(t['gpu_forward_seconds'] for t in timings),
                    'device':args.device,'gpu_name':torch.cuda.get_device_name(0) if args.device=='cuda' else None})
    except Exception:
        run.finish({'status':'failed','technical_smoke':args.smoke,'traceback':traceback.format_exc()})
        raise

if __name__=='__main__':main()
