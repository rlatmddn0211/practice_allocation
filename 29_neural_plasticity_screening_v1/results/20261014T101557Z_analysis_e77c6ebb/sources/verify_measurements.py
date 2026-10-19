"""Independent spectra, native-SAC loss and clone trajectory reconstruction."""
import argparse
import copy
import math
import traceback
from pathlib import Path
import numpy as np
import torch
from common import Run,save,seed_for
from snapshot_io import load_snapshot,fingerprint,learning_state,replay_state

def close(run,label,actual,expected,rtol=2e-8,atol=1e-10):
    a=np.asarray(actual,dtype=float);b=np.asarray(expected,dtype=float)
    run.check(label,np.allclose(a,b,rtol=rtol,atol=atol),{'max_abs_error':float(np.max(np.abs(a-b)))})

def independent_data(run,m,b,raw,p):
    data={};key=raw['entry']['id'];device=m.device
    for panel in raw['panels']:
        ti,pi=panel['task'],panel['panel'];ix=np.array(panel['indices']);obs=torch.as_tensor(b.observations[ix,0],device=device)
        nxt=torch.as_tensor(b.next_observations[ix,0],device=device);act=torch.as_tensor(b.actions[ix,0],device=device)
        with torch.no_grad(),torch.random.fork_rng(devices=[0]):
            torch.manual_seed(seed_for(p['dynamic']['seed'],key,ti,pi,'target'));ys=[]
            for _ in range(4):
                na,lp=m.actor.action_log_prob(nxt);qa,qb=m.critic_target(nxt,na)
                boot=torch.minimum(qa,qb).squeeze(1)-m.log_ent_coef.detach().exp()*lp
                ys.append(torch.as_tensor(b.rewards[ix,0],device=device)+m.gamma*torch.as_tensor(1-b.dones[ix,0]*(1-b.timeouts[ix,0]),device=device)*boot)
            target=torch.stack(ys).mean(dim=0)
            torch.manual_seed(seed_for(p['dynamic']['seed'],key,ti,pi,'actor_noise'));noise=torch.randn(act.shape,device=device)
        run.check('fixed target independently reproduced',fingerprint(target)==panel['target_fingerprint'])
        run.check('fixed noise independently reproduced',fingerprint(noise)==panel['noise_fingerprint'])
        data[ti,pi]={'obs':obs,'actions':act,'target':target,'eps':noise}
    return data

def native_samples(module,clone,frozen,alpha,d):
    if module=='critic':
        qa,qb=clone(d['obs'],d['actions']);return ((qa[:,0]-d['target']).square()+(qb[:,0]-d['target']).square())*.5
    mean,logstd,_=clone.get_action_dist_params(d['obs']);gaussian=mean+logstd.exp()*d['eps'];action=gaussian.tanh()
    dist=clone.action_dist.proba_distribution(mean,logstd)
    lp=dist.log_prob(action,gaussian_actions=gaussian)
    qa,qb=frozen(d['obs'],action)
    return alpha*lp-torch.minimum(qa,qb)[:,0]

def reference(run,tm,p):
    raw=run.read(tm['raw_path'],tm['raw_sha256']);m,b,_=load_snapshot(run,tm['checkpoint'],'cuda')
    mh=fingerprint(learning_state(m));bh=fingerprint(replay_state(b));data=independent_data(run,m,b,raw,p)
    static={(r['task'],r['panel'],r['module']):r for r in raw['static']};max_loss_error=0.
    # Forward hooks independently locate actual last hidden outputs; direct SVD replaces Gram eigenvalues.
    for ti,t in enumerate(p['suites'][tm['suite']]):
        for pi,panel in [(0,'M'),(1,'A')]:
            captured={};handles=[]
            for name,layer in [('actor',m.actor.latent_pi[-1])]+[('critic'+str(i),net[-2]) for i,net in enumerate(m.critic.q_networks)]:
                handles.append(layer.register_forward_hook(lambda mod,inputs,out,n=name:captured.__setitem__(n,out.detach().clone())))
            try:
                with torch.no_grad():m.actor.get_action_dist_params(data[ti,pi]['obs']);m.critic(data[ti,pi]['obs'],data[ti,pi]['actions'])
            finally:
                for h in handles:h.remove()
            for name,h in captured.items():
                rec=static[t,panel,name];matrix=h.double().cpu();means=matrix.abs().mean(0)
                singular=torch.linalg.svdvals(matrix);power=singular.square();mass=float(power.sum())
                prob=power[power>0]/mass if mass else power
                rank=float(torch.exp(-(prob*torch.log(prob)).sum()))/min(matrix.shape) if mass else 0.
                close(run,'hook mean activations',rec['neuron_mean_abs'],means.numpy())
                close(run,'direct SVD effective rank',rec['normalized_rank'],rank,rtol=2e-7)
                ratio=means/means.mean() if float(means.mean()) else torch.zeros_like(means)
                for field,threshold in [('dormant_zero',0),('dormant_primary',.01),('dormant_tenth',.1)]:
                    close(run,'direct activation dormancy',rec[field],float((ratio<=threshold).double().mean()))
    losses={(r['module'],r['train_panel'],r['eval_panel'],r['step'],r['task']):r for r in raw['losses']}
    for clone_record in raw['clones']:
        module=clone_record['module'];panel=clone_record['train_panel'];pi=0 if panel=='M' else 1
        clone=copy.deepcopy(getattr(m,module));frozen=copy.deepcopy(m.critic)
        for v in frozen.parameters():v.requires_grad_(False)
        alpha=m.log_ent_coef.detach().exp()
        def check_loss(step):
            nonlocal max_loss_error
            with torch.no_grad():
                for ei,ep in [(0,'M'),(1,'A')]:
                    for ti,t in enumerate(p['suites'][tm['suite']]):
                        z=native_samples(module,clone,frozen,alpha,data[ti,ei]).double();rr=losses[module,panel,ep,step,t]
                        mm=float(z.mean());rms=float(z.square().mean().sqrt());max_loss_error=max(max_loss_error,abs(mm-rr['loss']))
                        close(run,'independent clone loss '+str((module,panel,step,t)),rr['loss'],mm,rtol=1e-4,atol=3e-5)
                        close(run,'independent clone RMS',rr['loss_rms'],rms,rtol=1e-4,atol=3e-5)
        check_loss(0)
        for step,indices in enumerate(clone_record['batch_indices'],1):
            batch={k:torch.cat([data[ti,pi][k][indices[ti]] for ti in range(4)]) for k in ['obs','actions','target','eps']}
            clone.optimizer.zero_grad(set_to_none=True);loss=native_samples(module,clone,frozen,alpha,batch).mean()
            grads=torch.autograd.grad(loss,tuple(clone.parameters()))
            for param,g in zip(clone.parameters(),grads):param.grad=g
            clone.optimizer.step();run.clone_steps+=1
            if step in [1,20]:check_loss(step)
        del clone,frozen
    # Zero-learning-rate control: optimizer bookkeeping may change, parameters and loss may not.
    for module in ['actor','critic']:
        clone=copy.deepcopy(getattr(m,module));frozen=copy.deepcopy(m.critic)
        for v in frozen.parameters():v.requires_grad_(False)
        for g in clone.optimizer.param_groups:g['lr']=0.
        before=fingerprint(clone.state_dict());d=data[0,0]
        loss=native_samples(module,clone,frozen,m.log_ent_coef.detach().exp(),d).mean()
        grads=torch.autograd.grad(loss,tuple(clone.parameters()))
        for q,g in zip(clone.parameters(),grads):q.grad=g
        clone.optimizer.step();run.clone_steps+=1
        run.check('zero LR exact parameter preservation',fingerprint(clone.state_dict())==before)
        after=native_samples(module,clone,frozen,m.log_ent_coef.detach().exp(),d).mean()
        close(run,'zero LR exact loss',float(loss.detach()),float(after.detach()),rtol=0,atol=0)
    run.check('reference learner unchanged',fingerprint(learning_state(m))==mh)
    run.check('reference replay unchanged',fingerprint(replay_state(b))==bh)
    return {'id':tm['id'],'max_independent_mean_loss_abs_error':max_loss_error}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('measurement_dir');args=ap.parse_args();run=Run('verify_measurements');run.clone_steps=0
    try:
        src=Path(args.measurement_dir);summary=run.read(src/'summary.json');p=run.read(src/'sources/protocol.json');manifest=run.read(src/'snapshot_manifest.json')
        run.check('completed source',summary['status']=='completed')
        torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
        sc={(r['id'],r['task'],r['panel'],r['module']):r for r in run.rows(src/'static_diagnostics.csv')}
        states={(r['id'],r['task'],r['panel']):r for r in run.rows(src/'state_controls.csv')}
        loss_csv={(r['id'],r['module'],r['train_panel'],r['eval_panel'],int(r['step']),r['task']):r for r in run.rows(src/'clone_losses.csv')}
        for tm in manifest:
            raw=run.read(tm['raw_path'],tm['raw_sha256']);key=tm['id'];panels=raw['panels']
            for ti in range(4):
                a=next(r for r in panels if r['task']==ti and r['panel']==0);b=next(r for r in panels if r['task']==ti and r['panel']==1)
                run.check('1024 unique per panel',len(set(a['indices']))==len(set(b['indices']))==1024)
                run.check('episode-disjoint panels',not {(int(x)-1)//500 for x in a['birth_steps']}&{(int(x)-1)//500 for x in b['birth_steps']})
            for r in raw['static']:
                means=np.array(r['neuron_mean_abs']);power=np.array(r['power']);m=means.mean();ratio=means/m if m else np.zeros_like(means)
                run.check('nonnegative finite spectrum',np.isfinite(power).all() and (power>=0).all())
                q=power[power>0]/power.sum() if power.sum() else np.zeros(0);rank=math.exp(-sum(float(v)*math.log(float(v)) for v in q))/min(r['rows'],r['width']) if q.size else 0
                for field,value in [('dormant_zero',(ratio<=0).mean()),('dormant_primary',(ratio<=.01).mean()),('dormant_tenth',(ratio<=.1).mean()),('normalized_rank',rank)]:
                    close(run,'all static raw feature '+field,r[field],value);close(run,'static CSV '+field,float(sc[key,r['task'],r['panel'],r['module']][field]),value)
                run.check('degenerate layer explicitly recorded',bool(r['all_zero'])==(power.sum()==0))
            for r in raw['states']:
                close(run,'state spread from spectral trace',r['spread'],math.sqrt(sum(r['power'])/r['rows']))
                for field in ['spread','normalized_rank']:close(run,'state CSV '+field,float(states[key,r['task'],r['panel']][field]),r[field])
            for cc in raw['clones']:
                pi=0 if cc['train_panel']=='M' else 1;indices=cc['batch_indices']
                run.check('20 batches',len(indices)==20)
                for ti in range(4):
                    rng=np.random.default_rng(seed_for(p['dynamic']['seed'],key,ti,pi,'batch'));perm=[rng.permutation(128).tolist() for _ in range(8)]
                    for step in range(20):
                        expected=[st*128+idx for st in range(8) for idx in perm[st][8*(step%16):8*(step%16+1)]]
                        run.check('stratified fixed batch independently reconstructed',indices[step][ti]==expected)
                    run.check('first16 batches cover full task panel',sorted(x for inds in indices[:16] for x in inds[ti])==list(range(1024)))
            for r in raw['losses']:
                saved=loss_csv[key,r['module'],r['train_panel'],r['eval_panel'],r['step'],r['task']]
                for field in ['loss','loss_rms']:close(run,'all clone CSV '+field,float(saved[field]),r[field])
                run.check('finite loss with valid RMS',np.isfinite([r['loss'],r['loss_rms']]).all() and r['loss_rms']>=abs(r['loss'])-1e-8)
            for module in ['actor','critic']:
                for ep in ['M','A']:
                    for task in p['suites'][tm['suite']]:
                        x=loss_csv[key,module,'M',ep,0,task];y=loss_csv[key,module,'A',ep,0,task]
                        close(run,'independent clones same initial objective',float(x['loss']),float(y['loss']),rtol=0,atol=0)
        selected=[];seen=set()
        for tm in manifest:
            kind='parent' if tm['horizon']==0 else 'focus' if tm['allocation'].startswith('F_') else None
            group=(tm['suite'],tm['checkpoint_step'],kind)
            if kind and group not in seen:selected.append(tm);seen.add(group)
        rr=[reference(run,tm,p) for tm in selected];save(run.out/'reference_checks.json',rr)
        run.finish({'status':'completed','source':str(src),'technical_smoke_source':summary['technical_smoke'],'snapshots_verified':len(manifest),
                    'static_rows_verified':len(sc),'clone_loss_rows_verified':len(loss_csv),'reference_snapshots':rr,'clone_optimizer_steps':run.clone_steps})
    except Exception:
        run.finish({'status':'failed','clone_optimizer_steps':run.clone_steps,'traceback':traceback.format_exc()});raise

if __name__=='__main__':main()
