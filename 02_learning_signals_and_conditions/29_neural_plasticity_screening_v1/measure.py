"""Static activation and controlled clone-fitting diagnostics, no new RL."""
import argparse
import copy
import gc
import inspect
import math
import time
import traceback
from pathlib import Path
import numpy as np
import torch
from common import Run,HERE,allocations,campaign,contexts,prefix,record,save,seed_for,sha,table
from snapshot_io import load_snapshot,choose_panels,fingerprint,learning_state,replay_state

def fixed_actor_samples(actor,critic,obs,eps,alpha):
    mu,logstd,_=actor.get_action_dist_params(obs)
    z=mu+logstd.exp()*eps;actions=torch.tanh(z)
    logp=torch.distributions.Normal(mu,logstd.exp()).log_prob(z).sum(-1)
    logp-=torch.log(1-actions.square()+actor.action_dist.epsilon).sum(-1)
    q0,q1=critic(obs,actions)
    return alpha*logp-torch.minimum(q0,q1).reshape(-1)

def fixed_critic_samples(critic,obs,actions,target):
    q0,q1=critic(obs,actions)
    return ((q0.reshape(-1)-target).square()+(q1.reshape(-1)-target).square())/2

def spectrum(matrix):
    h=matrix.detach().double().cpu();gram=h.T@h
    eigen=torch.linalg.eigvalsh(gram);power=eigen.clamp_min(0)
    trace=float(power.sum());q=power/trace if trace>0 else power
    rank=float(torch.exp(-(q[q>0]*torch.log(q[q>0])).sum()))/min(h.shape) if trace>0 else 0.
    return {'power':power.tolist(),'raw_min_eigenvalue':float(eigen.min()),'trace':trace,
            'normalized_rank':rank,'rows':h.shape[0],'width':h.shape[1],'all_zero':trace==0}

def activation_stats(h):
    mean=h.detach().double().abs().mean(0).cpu();average=float(mean.mean())
    scores=mean/average if average>0 else torch.zeros_like(mean)
    spec=spectrum(h)
    return {**spec,'neuron_mean_abs':mean.tolist(),'mean_abs':average,
            'dormant_zero':float((scores<=0).double().mean()),
            'dormant_primary':float((scores<=.01).double().mean()),
            'dormant_tenth':float((scores<=.1).double().mean())}

def data_panels(run,m,b,panels,key,p,device):
    data={};raw=[]
    def t(a):return torch.as_tensor(a,device=device)
    for ti,pi,ix in panels:
        obs=t(b.observations[ix,0]);nxt=t(b.next_observations[ix,0]);actions=t(b.actions[ix,0])
        reward=t(b.rewards[ix,0]);mask=t(1-b.dones[ix,0]*(1-b.timeouts[ix,0]))
        with torch.no_grad(),torch.random.fork_rng(devices=[0] if device=='cuda' else []):
            torch.manual_seed(seed_for(p['dynamic']['seed'],key,ti,pi,'target'))
            ys=[]
            for _ in range(p['dynamic']['target_action_draws']):
                na,nlp=m.actor.action_log_prob(nxt);q0,q1=m.critic_target(nxt,na)
                ys.append(reward+m.gamma*mask*(torch.minimum(q0,q1).reshape(-1)-m.log_ent_coef.detach().exp()*nlp))
            target=torch.stack(ys).mean(0)
            torch.manual_seed(seed_for(p['dynamic']['seed'],key,ti,pi,'actor_noise'))
            eps=torch.randn(actions.shape,device=device)
        data[ti,pi]={'obs':obs,'actions':actions,'target':target,'eps':eps}
        raw.append({'task':ti,'panel':pi,'indices':ix.tolist(),'birth_steps':b.birth_steps[ix].tolist(),
                    'target_fingerprint':fingerprint(target),'noise_fingerprint':fingerprint(eps),
                    'target_mean':float(target.double().mean()),'target_rms':float(target.double().square().mean().sqrt())})
        run.check('finite fixed targets/noise '+key+str((ti,pi)),torch.isfinite(target).all() and torch.isfinite(eps).all())
    return data,raw

def batch_schedule(key,pi,p):
    orders=[]
    for ti in range(4):
        rng=np.random.default_rng(seed_for(p['dynamic']['seed'],key,ti,pi,'batch'))
        orders.append(np.stack([rng.permutation(128) for _ in range(8)]))
    result=[]
    for step in range(p['dynamic']['updates']):
        offset=step%16
        result.append([np.concatenate([st*128+orders[ti][st,offset*8:(offset+1)*8] for st in range(8)]) for ti in range(4)])
    return result

def cloned(run,module,label):
    result=copy.deepcopy(module);original=list(module.parameters());params=list(result.parameters())
    run.check('clone parameter identity '+label,len(original)==len(params) and all(a.data_ptr()!=b.data_ptr() and torch.equal(a,b) for a,b in zip(original,params)))
    run.check('cloned optimizer attached '+label,{id(v) for g in result.optimizer.param_groups for v in g['params']}=={id(v) for v in params})
    run.check('cloned Adam state '+label,fingerprint(result.optimizer.state_dict())==fingerprint(module.optimizer.state_dict()))
    return result

def fit_clone(run,m,data,entry,pi,module,p):
    key=entry['id'];clone=cloned(run,getattr(m,module),key+module+str(pi))
    frozen=copy.deepcopy(m.critic) if module=='actor' else None
    if frozen is not None:
        for q in frozen.parameters():q.requires_grad_(False)
    alpha=m.log_ent_coef.detach().exp();schedule=batch_schedule(key,pi,p);lossrows=[]
    def evaluate(step):
        with torch.no_grad():
            for ep in [0,1]:
                for ti in range(4):
                    d=data[ti,ep]
                    values=fixed_actor_samples(clone,frozen,d['obs'],d['eps'],alpha) if module=='actor' else fixed_critic_samples(clone,d['obs'],d['actions'],d['target'])
                    x=values.double();lossrows.append({**entry,'module':module,'train_panel':'M' if pi==0 else 'A',
                        'eval_panel':'M' if ep==0 else 'A','step':step,'task':p['suites'][entry['suite']][ti],
                        'loss':float(x.mean()),'loss_rms':float(x.square().mean().sqrt()),'samples':len(x)})
    evaluate(0)
    for step,inds in enumerate(schedule,1):
        batch={field:torch.cat([data[ti,pi][field][inds[ti]] for ti in range(4)]) for field in ['obs','actions','target','eps']}
        clone.optimizer.zero_grad(set_to_none=True)
        v=fixed_actor_samples(clone,frozen,batch['obs'],batch['eps'],alpha) if module=='actor' else fixed_critic_samples(clone,batch['obs'],batch['actions'],batch['target'])
        loss=v.mean();run.check('finite clone loss '+key+module+str((pi,step)),torch.isfinite(loss).item())
        loss.backward();clone.optimizer.step();run.clone_steps+=1
        if step in [1,p['dynamic']['updates']]:evaluate(step)
    result={'module':module,'train_panel':'M' if pi==0 else 'A','updates':p['dynamic']['updates'],
            'final_parameters_fingerprint':fingerprint(clone.state_dict()),'final_optimizer_fingerprint':fingerprint(clone.optimizer.state_dict()),
            'batch_indices':[[x.tolist() for x in batch] for batch in schedule]}
    del clone,frozen
    return lossrows,result

def measure_one(run,entry,ref,p,device):
    started=time.perf_counter();before_steps=run.clone_steps;key=entry['id']
    m,b,manifest=load_snapshot(run,ref,device);model_hash=fingerprint(learning_state(m));replay_hash=fingerprint(replay_state(b))
    run.check('step/task identity '+key,m.num_timesteps==entry['checkpoint_step']+entry['horizon'] and list(manifest['tasks'])==p['suites'][entry['suite']])
    run.check('supported deterministic MLP '+key,not m.actor.use_sde and not m.critic.share_features_extractor and
              not any(isinstance(x,(torch.nn.Dropout,torch.nn.modules.batchnorm._BatchNorm)) for x in m.policy.modules()))
    run.check('hidden layer contract '+key,isinstance(m.actor.latent_pi[-1],torch.nn.ReLU) and len(m.critic.q_networks)==2 and
              all(isinstance(net[-1],torch.nn.Linear) and isinstance(net[-2],torch.nn.ReLU) for net in m.critic.q_networks))
    panels=choose_panels(run,b,p,key);start_compute=time.perf_counter()
    if device=='cuda':start_event=torch.cuda.Event(enable_timing=True);end_event=torch.cuda.Event(enable_timing=True);start_event.record()
    data,rawpanels=data_panels(run,m,b,panels,key,p,device);static=[];states=[];losses=[];clone_records=[]
    with torch.no_grad():
        for ti,pi,_ in panels:
            d=data[ti,pi];h=m.actor.latent_pi(m.actor.extract_features(d['obs'],m.actor.features_extractor))
            hs={'actor':h};cf=m.critic.extract_features(d['obs'],m.critic.features_extractor);inp=torch.cat([cf,d['actions']],1)
            for j,net in enumerate(m.critic.q_networks):hs['critic'+str(j)]=net[:-1](inp)
            for name,h in hs.items():
                stats=activation_stats(h);run.check('positive semidefinite activation Gram '+key+str((ti,pi,name)),stats['raw_min_eigenvalue']>=-1e-10*max(stats['trace'],1.))
                static.append({**entry,'task':p['suites'][entry['suite']][ti],'panel':'M' if pi==0 else 'A','module':name,**stats})
            obs=d['obs'][:,:-4].double();centered=obs-obs.mean(0);spec=spectrum(centered)
            states.append({**entry,'task':p['suites'][entry['suite']][ti],'panel':'M' if pi==0 else 'A',
                           'spread':float(centered.square().sum(1).mean().sqrt()),**spec})
    for pi in [0,1]:
        for module in ['actor','critic']:
            rr,cc=fit_clone(run,m,data,entry,pi,module,p);losses+=rr;clone_records.append(cc)
    if device=='cuda':end_event.record();end_event.synchronize();gpu_seconds=start_event.elapsed_time(end_event)/1000
    else:gpu_seconds=None
    compute_wall=time.perf_counter()-start_compute
    run.check('original learner unchanged '+key,fingerprint(learning_state(m))==model_hash)
    run.check('original replay unchanged '+key,fingerprint(replay_state(b))==replay_hash)
    for filename,digest in manifest['files'].items():run.hashed(Path(ref['path'])/filename,digest)
    run.hashed(Path(ref['path'])/'checkpoint_manifest.json',ref['manifest_sha256'])
    rawpath=run.out/'raw'/(key+'.json')
    save(rawpath,{'entry':entry,'checkpoint':ref,'panels':rawpanels,'static':static,'states':states,'losses':losses,'clones':clone_records,
                  'alpha':float(m.log_ent_coef.detach().exp()),'gamma':m.gamma})
    scalar_static=[{k:v for k,v in r.items() if k not in ['neuron_mean_abs','power']} for r in static]
    scalar_states=[{k:v for k,v in r.items() if k!='power'} for r in states]
    timing={**entry,'checkpoint':ref,'raw_path':str(rawpath),'raw_sha256':sha(rawpath),'model_state_hash':model_hash,'replay_state_hash':replay_hash,
        'wall_seconds':time.perf_counter()-started,'compute_wall_seconds':compute_wall,'gpu_compute_seconds':gpu_seconds,
        'clone_optimizer_steps':run.clone_steps-before_steps,'panel_transition_entries':8192}
    del m,b,data;gc.collect()
    return scalar_static,scalar_states,losses,timing

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--smoke',action='store_true');ap.add_argument('--device',default='cuda');args=ap.parse_args()
    run=Run('smoke' if args.smoke else 'measure');run.clone_steps=0
    try:
        p=run.read(HERE/'protocol.json');cam,plan=campaign(run);torch.set_num_threads(4)
        if args.device=='cuda':torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
        from stable_baselines3 import SAC
        from stable_baselines3.sac.policies import Actor
        from stable_baselines3.common.distributions import SquashedDiagGaussianDistribution
        for obj in [SAC.train,Actor,SquashedDiagGaussianDistribution]:run.hashed(inspect.getsourcefile(obj))
        schedule=[]
        for ctx in contexts(p):
            s,n,c=ctx;pre=prefix(ctx);rec,path=record(run,cam,plan,pre+'_base');req=run.read(path.parent/'request.json')
            schedule.append(({'id':pre+'_base','suite':s,'original_seed':n,'checkpoint_step':c,'horizon':0,'continuation':0,'allocation':'parent'},req['parent']))
            for rep in p['continuations'][s]:
                for a in allocations(p,s):
                    jid=pre+f'_r{rep}_{a}_t20';rr,_=record(run,cam,plan,jid)
                    schedule.append(({'id':jid,'suite':s,'original_seed':n,'checkpoint_step':c,'horizon':20000,'continuation':rep,'allocation':a},rr['checkpoint']))
        run.check('192 snapshots planned',len(schedule)==192)
        if args.smoke:schedule=schedule[:3]
        save(run.out/'schedule.json',[dict(e,checkpoint=r) for e,r in schedule]);(run.out/'raw').mkdir()
        sr=[];cr=[];lr=[];tm=[]
        for i,(entry,ref) in enumerate(schedule):
            ss,cc,ll,tt=measure_one(run,entry,ref,p,args.device);sr+=ss;cr+=cc;lr+=ll;tm.append(tt)
            save(run.out/(entry['id']+'_completed.json'),tt)
            print(f"measured {i+1}/{len(schedule)} {entry['id']} {tt['wall_seconds']:.2f}s",flush=True)
        table(run.out/'static_diagnostics.csv',sr);table(run.out/'state_controls.csv',cr);table(run.out/'clone_losses.csv',lr);save(run.out/'snapshot_manifest.json',tm)
        run.check('planned clone steps',run.clone_steps==len(schedule)*80)
        run.finish({'status':'completed','technical_smoke':args.smoke,'snapshots':len(tm),'static_task_rows':len(sr),'state_task_rows':len(cr),
                    'clone_loss_rows':len(lr),'clone_optimizer_steps':run.clone_steps,'panel_transition_entries':len(tm)*8192,
                    'gpu_compute_seconds':sum(t['gpu_compute_seconds'] or 0 for t in tm),'device':args.device,
                    'gpu':torch.cuda.get_device_name(0) if args.device=='cuda' else None})
    except Exception:
        run.finish({'status':'failed','technical_smoke':args.smoke,'clone_optimizer_steps':run.clone_steps,'traceback':traceback.format_exc()});raise

if __name__=='__main__':main()
