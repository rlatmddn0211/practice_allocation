"""Matrix reconstruction, independent backward/formula and finite differences."""
import argparse
import math
import time
import traceback
from pathlib import Path
import numpy as np
import torch
from common import Run,save,table,seed_for
from snapshot_io import load_snapshot,fingerprint,learning_state,replay_state

def close(run,name,a,b,rtol=2e-8,atol=1e-10):
    run.check(name,np.allclose(a,b,rtol=rtol,atol=atol),{'max_error':float(np.max(np.abs(np.asarray(a)-np.asarray(b))))})

def loss_pair(model,replay,ix,seed):
    # Separately implemented reference objective using backward(), not production autograd.grad.
    def t(a):return torch.as_tensor(a,device=model.device)
    obs=t(replay.observations[ix,0]);nxt=t(replay.next_observations[ix,0]);act=t(replay.actions[ix,0])
    with torch.random.fork_rng(devices=[0]):
        torch.manual_seed(seed);actions,lp=model.actor.action_log_prob(obs)
        actor=model.log_ent_coef.detach().exp()*lp[:,None]-torch.minimum(*model.critic(obs,actions))
        with torch.no_grad():
            na,nlp=model.actor.action_log_prob(nxt)
            y=t(replay.rewards[ix,0])[:,None]+model.gamma*(1-t(replay.dones[ix,0]*(1-replay.timeouts[ix,0])))[:,None]*(torch.minimum(*model.critic_target(nxt,na))-model.log_ent_coef.detach().exp()*nlp[:,None])
        qa,qb=model.critic(obs,act);critic=0.5*((qa-y).square()+(qb-y).square())
    return {'actor':actor.mean(),'critic':critic.mean()}

def flat_backward(model,loss,module):
    model.policy.zero_grad(set_to_none=True);loss.backward()
    return torch.cat([p.grad.detach().view(-1) for p in getattr(model,module).parameters()])

def formula_delta(optimizer,flat):
    # Float64 Adam arithmetic, round resulting parameters back to stored float32.
    out=[];off=0
    for group in optimizer.param_groups:
        if group.get('amsgrad') or group.get('weight_decay') or group.get('maximize'):raise AssertionError('unsupported Adam option')
        b1,b2=group['betas']
        for param in group['params']:
            g=flat[off:off+param.numel()].view_as(param).double();off+=param.numel();st=optimizer.state[param];step=float(st['step'])+1
            moment=b1*st['exp_avg'].double()+(1-b1)*g
            variance=b2*st['exp_avg_sq'].double()+(1-b2)*g.square()
            delta=-(group['lr']/(1-b1**step))*moment/(variance.sqrt()/math.sqrt(1-b2**step)+group['eps'])
            out.append(((param.detach().double()+delta).to(param.dtype)-param.detach()).flatten())
    return torch.cat(out)

def verify_reference(run,tm):
    raw=run.read(tm['raw_path'],tm['raw_sha256']);m,b,_=load_snapshot(run,tm['checkpoint'],'cuda')
    before=fingerprint(learning_state(m));before_b=fingerprint(replay_state(b));key=tm['id']
    panels={(r['task'],r['panel']):np.array(r['indices']) for r in raw['panels']}
    bi=0;gs={};fd=[]
    for pi in [0,1]:
        for ti in range(4):
            ix=panels[ti,pi].reshape(8,128)[:,:16].reshape(-1);seed=seed_for(2804101,key,ti,pi,bi)
            for module in ['actor','critic']:
                losses=loss_pair(m,b,ix,seed);gs[ti,pi,module]=flat_backward(m,losses[module],module)
                if pi==0 and ti==0:
                    params=list(getattr(m,module).parameters());saved=[q.detach().clone() for q in params]
                    direction=gs[ti,pi,module]/gs[ti,pi,module].norm();expected=float(gs[ti,pi,module].double()@direction.double());errors=[]
                    for eps in [0.001,0.0003]:
                        vals=[]
                        for sign in [-1,1]:
                            pos=0
                            with torch.no_grad():
                                for q,old in zip(params,saved):q.copy_(old+sign*eps*direction[pos:pos+q.numel()].view_as(q));pos+=q.numel()
                            vals.append(float(loss_pair(m,b,ix,seed)[module].detach()))
                        observed=(vals[1]-vals[0])/(2*eps);errors.append(abs(observed-expected)/max(abs(expected),1e-8))
                    with torch.no_grad():
                        for q,old in zip(params,saved):q.copy_(old)
                    run.check('fixed-noise finite difference '+key+module,min(errors)<.08,{'relative_errors':errors})
                    fd.append({'id':key,'module':module,'expected_directional_derivative':expected,'relative_errors':errors})
    for module in ['actor','critic']:
        gm=torch.stack([gs[t,0,module] for t in range(4)]);ga=torch.stack([gs[t,1,module] for t in range(4)])
        rec=next(r for r in raw['batches'] if r['batch']==0 and r['module']==module and r['source_panel']=='M')
        close(run,'independent backward Gram '+module,rec['gram_source'],(gm.double()@gm.double().T).cpu().numpy(),rtol=2e-5,atol=1e-6)
        close(run,'independent cross Gram '+module,rec['cross_eval_source'],(ga.double()@gm.double().T).cpu().numpy(),rtol=2e-5,atol=1e-6)
        for name in ['exposure','uniform']:
            dr=rec['directions'][name];weights=torch.tensor(dr['weights'],device='cuda',dtype=gm.dtype);delta=formula_delta(getattr(m,module).optimizer,weights@gm)
            norm=float(delta.double().norm());dots=(ga.double()@delta.double()).cpu().numpy()
            close(run,'independent Adam step norm '+key+module+name,dr['delta_norm'],norm,rtol=.002,atol=1e-7)
            # Rounding in the cloned float32 optimizer is bounded by parameter ULP.
            close(run,'independent Adam dot '+key+module+name,dr['eval_dot_delta'],dots,rtol=.005,atol=2e-6)
    run.check('verification restored model '+key,fingerprint(learning_state(m))==before)
    run.check('verification preserved replay '+key,fingerprint(replay_state(b))==before_b)
    return fd

def main():
    ap=argparse.ArgumentParser();ap.add_argument('measurement_dir');args=ap.parse_args();run=Run('verify_measurements')
    try:
        src=Path(args.measurement_dir);summ=run.read(src/'summary.json');manifest=run.read(src/'snapshot_manifest.json')
        torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
        batch={(r['id'],r['module'],r['source_panel'],int(r['batch'])):r for r in run.rows(src/'batch_diagnostics.csv')}
        max_mixed_norm_error=0.;max_roundoff_bound_ratio=0.
        for tm in manifest:
            raw=run.read(tm['raw_path'],tm['raw_sha256']);panels=raw['panels'];births={}
            for task in range(4):
                aa=next(r['indices'] for r in panels if r['task']==task and r['panel']==0)
                bb=next(r['indices'] for r in panels if r['task']==task and r['panel']==1)
                run.check('disjoint unique indices '+tm['id']+str(task),len(set(aa))==1024 and len(set(bb))==1024 and not set(aa)&set(bb))
            if tm['horizon']:
                inc=np.array(raw['cumulative_sample_counts'])-np.array(raw['parent_sample_counts'])
                close(run,'past exposure weights',raw['weights'],inc/inc.sum());run.check('past sample count',int(inc.sum())==5120000)
            for r in raw['batches']:
                mm=np.array(r['gram_source']);aa=np.array(r['gram_eval']);cross=np.array(r['cross_eval_source']);nm=np.sqrt(mm.diagonal());na=np.sqrt(aa.diagonal())
                cosine=mm/np.maximum(nm[:,None]*nm[None,:],1e-30);off=cosine[np.triu_indices(4,1)]
                expected={'raw_cosine':off.mean(),'negative_pair_fraction':(off<0).mean(),'gradient_norm_mean':nm.mean(),'gradient_norm_ratio':nm.max()/max(nm.min(),1e-30)}
                saved=batch[tm['id'],r['module'],r['source_panel'],r['batch']]
                for k,v in expected.items():close(run,'batch reconstructed '+k,float(saved[k]),v)
                for name,dr in r['directions'].items():
                    # Production forms a 4-term weighted sum in float32, then a float64 norm.
                    # Reconstruct rounded weights; bound summation rounding independently.
                    w=np.array(dr['weights'],dtype=np.float32).astype(np.float64)
                    exactnorm=math.sqrt(max(float(w@mm@w),0));gnorm=dr['raw_mixed_norm']
                    bound=float(8*float(np.finfo(np.float32).eps)*float(np.abs(w)@nm)+1e-12)
                    error=abs(gnorm-exactnorm)
                    run.check('float32 mixed-gradient rounding bound',error<=bound,{'error':error,'bound':bound})
                    max_mixed_norm_error=max(max_mixed_norm_error,error);max_roundoff_bound_ratio=max(max_roundoff_bound_ratio,error/bound)
                    dots=np.array(dr['eval_dot_delta']);dn=dr['delta_norm']
                    relative=np.mean(-dots/np.maximum(r['loss_rms_eval'],1e-6));alignment=np.mean(cross@w/np.maximum(na*gnorm,1e-30))
                    close(run,'dot product normalization',dr['adam_relative'],relative)
                    close(run,'raw alignment reconstruction',dr['weighted_alignment'],alignment)
                    close(run,'step cosine reconstruction',dr['adam_cosine'],np.mean(-dots/np.maximum(na*dn,1e-30)))
                    close(run,'feature CSV',float(saved['adam_relative' if name=='exposure' else 'uniform_adam_relative']),relative)
        # Earliest parent/focus in every suite/checkpoint group, independent of outcomes.
        chosen=[];seen=set()
        for tm in manifest:
            kind='parent' if tm['horizon']==0 else 'focus' if tm['allocation'].startswith('F_') else None
            group=tm['suite'],tm['checkpoint_step'],kind
            if kind and group not in seen:chosen.append(tm);seen.add(group)
        fd=[]
        for tm in chosen:fd+=verify_reference(run,tm)
        save(run.out/'finite_differences.json',fd)
        run.finish({'status':'completed','source':str(src),'technical_smoke_source':summ['technical_smoke'],'snapshots_verified':len(manifest),
                    'batch_rows_verified':len(batch),'reference_snapshots':[t['id'] for t in chosen],
                    'finite_difference_cases':len(fd),'virtual_optimizer_steps':0,'finite_difference_parameter_perturbations':len(fd)*4,
                    'max_float32_mixed_norm_error':max_mixed_norm_error,'max_roundoff_bound_ratio':max_roundoff_bound_ratio})
    except Exception:
        run.finish({'status':'failed','traceback':traceback.format_exc()});raise

if __name__=='__main__':main()
