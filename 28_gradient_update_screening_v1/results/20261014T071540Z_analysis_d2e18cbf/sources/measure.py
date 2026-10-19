"""Read-only checkpoint diagnostics; virtual optimizer steps affect clones only."""
import argparse
import copy
import gc
import time
import traceback
from pathlib import Path
import numpy as np
import torch
from common import Run,HERE,campaign,record,contexts,prefix,allocations,save,table,seed_for,sha
from snapshot_io import load_snapshot,choose_panels,fingerprint,learning_state,replay_state

def tensor(a,device):return torch.as_tensor(a,device=device)

def gradients(model,replay,ix,seed,device):
    obs=tensor(replay.observations[ix,0],device);nxt=tensor(replay.next_observations[ix,0],device)
    act=tensor(replay.actions[ix,0],device);reward=tensor(replay.rewards[ix,0],device).reshape(-1,1)
    mask=tensor(1-replay.dones[ix,0]*(1-replay.timeouts[ix,0]),device).reshape(-1,1)
    alpha=model.log_ent_coef.detach().exp()
    with torch.random.fork_rng(devices=[0] if device=='cuda' else []):
        torch.manual_seed(seed)
        actions,lp=model.actor.action_log_prob(obs);lp=lp.reshape(-1,1)
        qpi=torch.cat(model.critic(obs,actions),1).min(1,keepdim=True).values
        actor_samples=alpha*lp-qpi
        ag=torch.autograd.grad(actor_samples.mean(),tuple(model.actor.parameters()))
        with torch.no_grad():
            na,nlp=model.actor.action_log_prob(nxt)
            qn=torch.cat(model.critic_target(nxt,na),1).min(1,keepdim=True).values
            target=reward+model.gamma*mask*(qn-alpha*nlp.reshape(-1,1))
        q0,q1=model.critic(obs,act);critic_samples=((q0-target)**2+(q1-target)**2)/2
        cg=torch.autograd.grad(critic_samples.mean(),tuple(model.critic.parameters()))
    def flat(g):return torch.cat([v.detach().reshape(-1) for v in g])
    def stats(v):
        a=v.detach().double()
        return {'loss':float(a.mean()),'loss_rms':float(a.square().mean().sqrt())}
    return {'actor':flat(ag),'critic':flat(cg)}, {'actor':stats(actor_samples),'critic':stats(critic_samples),'entropy':float(-lp.detach().mean())}

class VirtualAdam:
    def __init__(self,optimizer):
        self.original=optimizer
        self.params=[q for group in optimizer.param_groups for q in group['params']]
        self.clones=[torch.nn.Parameter(q.detach().clone()) for q in self.params]
        groups=[];pos=0
        for group in optimizer.param_groups:
            n=len(group['params']);groups.append({**{k:v for k,v in group.items() if k!='params'},'params':self.clones[pos:pos+n]});pos+=n
        self.opt=torch.optim.Adam(groups)
        self.state=copy.deepcopy(optimizer.state_dict())
        self.count=0

    def step(self,gradient):
        self.opt.load_state_dict(copy.deepcopy(self.state));offset=0
        with torch.no_grad():
            for orig,cl in zip(self.params,self.clones):
                cl.copy_(orig);cl.grad=gradient[offset:offset+cl.numel()].view_as(cl).clone();offset+=cl.numel()
            self.opt.step()
            delta=torch.cat([(cl-orig).reshape(-1) for cl,orig in zip(self.clones,self.params)])
        self.count+=1
        return delta.detach()

def matrix_stats(gm,ga,sm,sa,weights,virtual):
    # Dot products in float64 prevent cancellation in small first-order changes.
    mm=gm.double()@gm.double().T;aa=ga.double()@ga.double().T;cross=ga.double()@gm.double().T
    nm=mm.diag().sqrt();na=aa.diag().sqrt();pairden=nm[:,None]*nm[None,:]
    cos=mm/torch.clamp(pairden,min=1e-30);off=torch.triu_indices(4,4,1,device=gm.device)
    result={'gram_source':mm.cpu().tolist(),'gram_eval':aa.cpu().tolist(),'cross_eval_source':cross.cpu().tolist(),
            'loss_rms_source':sm,'loss_rms_eval':sa,'raw_cosine':float(cos[off[0],off[1]].mean()),
            'negative_pair_fraction':float((cos[off[0],off[1]]<0).double().mean()),
            'gradient_norm_mean':float(nm.mean()),'gradient_norm_ratio':float(nm.max()/torch.clamp(nm.min(),min=1e-30)),
            'zero_gradient_tasks':int((nm<1e-15).sum()),'directions':{}}
    for name,ww in [('exposure',weights),('uniform',np.full(4,.25))]:
        w=tensor(np.asarray(ww,dtype=np.float32),gm.device);mix=w@gm;dn=virtual.step(mix)
        norm=dn.double().norm();dot=ga.double()@dn.double();mixnorm=mix.double().norm()
        rawalign=(cross@w.double())/torch.clamp(na*mixnorm,min=1e-30)
        normalized=-dot/tensor(np.maximum(sa,1e-6),gm.device)
        result['directions'][name]={'weights':list(map(float,ww)),'delta_norm':float(norm),'eval_dot_delta':dot.cpu().tolist(),
            'adam_relative':float(normalized.mean()),'adam_cosine':float((-dot/torch.clamp(na*norm,min=1e-30)).mean()),
            'weighted_alignment':float(rawalign.mean()),'raw_mixed_norm':float(mixnorm)}
    return result

def one(run,entry,ref,p,device,parent_counts,check_finite_difference=False):
    start=time.perf_counter();key=entry['id'];model,replay,manifest=load_snapshot(run,ref,device)
    lm=fingerprint(learning_state(model));rb=fingerprint(replay_state(replay))
    run.check('snapshot step '+key,model.num_timesteps==entry['checkpoint_step']+entry['horizon'])
    run.check('task order '+key,list(manifest['tasks'])==p['suites'][entry['suite']])
    counts=np.array(replay.sampled_task_counts,dtype=np.int64)
    if entry['horizon']==0:
        ids=replay.observations[:replay.size(),0,-4:].argmax(1);weights=np.bincount(ids,minlength=4)/len(ids)
        source='current_replay_fractions';increment=None
    else:
        increment=counts-parent_counts
        run.check('20k available exposure '+key,(increment>=0).all() and increment.sum()==20000*256)
        weights=increment/increment.sum();source='past_0to20k_sample_counts'
    panels=choose_panels(run,replay,p,key);panel_map={(t,pi):ix for t,pi,ix in panels}
    virtual={name:VirtualAdam(getattr(model,name).optimizer) for name in ['actor','critic']}
    batchrows=[];rawbatches=[];taskrows=[];gpu_ms=0.;compute_wall=0.;fd=[]
    for bi in range(8):
        # Each128-item batch has16 entries from EACH chronological stratum.
        selections={(t,pi):ix.reshape(8,128)[:,bi*16:(bi+1)*16].reshape(-1) for (t,pi),ix in panel_map.items()}
        gs={};stats={};before=time.perf_counter()
        if device=='cuda':ev0=torch.cuda.Event(enable_timing=True);ev1=torch.cuda.Event(enable_timing=True);ev0.record()
        for pi in [0,1]:
            for ti in range(4):
                seed=seed_for(2804101,key,ti,pi,bi)
                gs[ti,pi],stats[ti,pi]=gradients(model,replay,selections[ti,pi],seed,device)
                taskrows.append({**entry,'batch':bi,'task':p['suites'][entry['suite']][ti],'panel':'M' if pi==0 else 'A',
                    'entropy':stats[ti,pi]['entropy'],'alpha':float(model.log_ent_coef.detach().exp()),
                    **{f'{name}_{field}':stats[ti,pi][name][field] for name in ['actor','critic'] for field in ['loss','loss_rms']}})
        for module in ['actor','critic']:
            for src,ev in [(0,1),(1,0)]:
                gm=torch.stack([gs[t,src][module] for t in range(4)]);ga=torch.stack([gs[t,ev][module] for t in range(4)])
                sm=[stats[t,src][module]['loss_rms'] for t in range(4)];sa=[stats[t,ev][module]['loss_rms'] for t in range(4)]
                raw=matrix_stats(gm,ga,sm,sa,weights,virtual[module]);raw.update(module=module,batch=bi,source_panel='M' if src==0 else 'A')
                rawbatches.append(raw);ex=raw['directions']['exposure'];un=raw['directions']['uniform']
                batchrows.append({**entry,'module':module,'batch':bi,'source_panel':raw['source_panel'],
                    **{k:raw[k] for k in ['raw_cosine','negative_pair_fraction','gradient_norm_mean','gradient_norm_ratio','zero_gradient_tasks']},
                    'adam_relative':ex['adam_relative'],'uniform_adam_relative':un['adam_relative'],
                    'weighted_alignment':ex['weighted_alignment'],'adam_cosine':ex['adam_cosine'],'adam_norm':ex['delta_norm']})
        if device=='cuda':ev1.record();ev1.synchronize();gpu_ms+=ev0.elapsed_time(ev1)
        compute_wall+=time.perf_counter()-before
    run.check('finite gradients '+key,all(np.isfinite(float(v)) for r in batchrows for k,v in r.items() if k in ['raw_cosine','adam_relative','weighted_alignment','adam_norm']))
    run.check('no original model update '+key,fingerprint(learning_state(model))==lm)
    run.check('no original replay mutation '+key,fingerprint(replay_state(replay))==rb)
    for file,digest in manifest['files'].items():run.hashed(Path(ref['path'])/file,digest)
    run.hashed(Path(ref['path'])/'checkpoint_manifest.json',ref['manifest_sha256'])
    rawpath=run.out/'raw'/(key+'.json')
    save(rawpath,{'entry':entry,'batches':rawbatches,'panels':[{'task':t,'panel':pi,'indices':ix.tolist()} for t,pi,ix in panels],
                  'task_batches':taskrows,'exposure_source':source,'weights':weights.tolist(),'cumulative_sample_counts':counts.tolist(),
                  'parent_sample_counts':parent_counts.tolist() if parent_counts is not None else None,
                  'increment_sample_counts':increment.tolist() if increment is not None else None})
    timing={**entry,'checkpoint':ref,'raw_path':str(rawpath),'raw_sha256':sha(rawpath),'wall_seconds':time.perf_counter()-start,
        'compute_wall_seconds':compute_wall,'gpu_compute_seconds':gpu_ms/1000,'virtual_optimizer_steps':sum(v.count for v in virtual.values()),
        'gradient_evaluations':8*4*2*2,'unique_replay_transitions':8192,'model_state_hash':lm,'replay_state_hash':rb}
    del model,replay,gs,virtual;gc.collect()
    return batchrows,taskrows,timing,counts

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--smoke',action='store_true');ap.add_argument('--device',default='cuda');args=ap.parse_args()
    run=Run('smoke' if args.smoke else 'measure')
    try:
        p=run.read(HERE/'protocol.json');cam,plan=campaign(run);torch.set_num_threads(4)
        if args.device=='cuda':torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
        # The installed objective implementation is part of measurement provenance.
        import inspect
        from stable_baselines3 import SAC
        run.hashed(inspect.getsourcefile(SAC.train))
        schedule=[]
        for ctx in contexts(p):
            s,n,c=ctx;pre=prefix(ctx);base,path=record(run,cam,plan,pre+'_base');req=run.read(path.parent/'request.json')
            schedule.append(({'id':pre+'_base','suite':s,'original_seed':n,'checkpoint_step':c,'horizon':0,'continuation':0,'allocation':'parent'},req['parent']))
            for rep in p['continuations'][s]:
                for alloc in allocations(p,s):
                    jid=pre+f'_r{rep}_{alloc}_t20';rec,_=record(run,cam,plan,jid)
                    schedule.append(({'id':jid,'suite':s,'original_seed':n,'checkpoint_step':c,'horizon':20000,'continuation':rep,'allocation':alloc},rec['checkpoint']))
        run.check('192 snapshots',len(schedule)==192)
        if args.smoke:schedule=schedule[:3]
        save(run.out/'schedule.json',[dict(e,checkpoint=ref) for e,ref in schedule]);(run.out/'raw').mkdir()
        rows=[];taskrows=[];timings=[];pc=None
        for i,(entry,ref) in enumerate(schedule):
            rr,tt,tm,counts=one(run,entry,ref,p,args.device,pc)
            if entry['horizon']==0:pc=counts
            rows+=rr;taskrows+=tt;timings.append(tm)
            save(run.out/(entry['id']+'_completed.json'),tm)
            print(f"measured {i+1}/{len(schedule)} {entry['id']} {tm['wall_seconds']:.2f}s",flush=True)
        table(run.out/'batch_diagnostics.csv',rows);table(run.out/'task_diagnostics.csv',taskrows);save(run.out/'snapshot_manifest.json',timings)
        run.finish({'status':'completed','technical_smoke':args.smoke,'snapshots':len(timings),'batch_rows':len(rows),'task_batch_rows':len(taskrows),
                    'unique_replay_transitions':sum(t['unique_replay_transitions'] for t in timings),
                    'gradient_evaluations':sum(t['gradient_evaluations'] for t in timings),
                    'virtual_optimizer_steps':sum(t['virtual_optimizer_steps'] for t in timings),
                    'gpu_compute_seconds':sum(t['gpu_compute_seconds'] for t in timings),'device':args.device,'gpu':torch.cuda.get_device_name(0) if args.device=='cuda' else None})
    except Exception:
        run.finish({'status':'failed','traceback':traceback.format_exc()});raise

if __name__=='__main__':main()
