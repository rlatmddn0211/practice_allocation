"""Recompute reported diagnostics from saved step-level observations."""
import argparse
import csv
import json
import traceback
from pathlib import Path
import numpy as np
from common import Run


def verify_record(result,check,hashed):
    for path,digest in [('episodes_path','episodes_sha256'),('mc_path','mc_sha256'),('traces_path','traces_sha256')]:hashed(result[path],result[digest])
    with Path(result['episodes_path']).open(encoding='utf-8') as f:episodes=list(csv.DictReader(f))
    with Path(result['mc_path']).open(encoding='utf-8') as f:mc=list(csv.DictReader(f))
    near=lambda label,a,b:check(label,bool(np.allclose(a,b,rtol=1e-10,atol=1e-9)))
    with np.load(result['traces_path'],allow_pickle=False) as trace:
        expected=set();q_by_state={};noise=set()
        for row in episodes:
            key='D_'+row['task']+'_'+row['episode_index'];expected.add(key);arr=trace[key]
            check('500 finite deterministic observations',arr.shape==(500,5) and np.isfinite(arr).all())
            check('official binary outcomes',np.isin(arr[:,1:4],[0,1]).all())
            successes=np.flatnonzero(arr[:,1]);first=int(successes[0]+1) if len(successes) else None
            check('first success step',row['first_success_step']==('' if first is None else str(first)))
            near('same-length return',float(row['return500']),sum(arr[:,0]))
            near('any-success',int(row['success']),int(bool(len(successes))))
            near('early prefix return',float(row['return_to_first_success']),sum(arr[:first if first else 500,0]))
            near('near-object flag',int(row['near_object_reached']),arr[:,2].max())
            near('official grasp flag',int(row['official_grasp_flag_reached']),arr[:,3].max())
            near('official goal distance',float(row['minimum_official_target_distance']),arr[:,4].min())
        for row in mc:
            key=row['task']+'_'+row['episode_index']+'_'+row['repeat'];expected.update(['MC_'+key,'tail_'+key]);arr=trace['MC_'+key];tail=trace['tail_'+key]
            check('500 finite MC observations',arr.shape==(500,3) and tail.shape==(16,3) and np.isfinite(arr).all() and np.isfinite(tail).all())
            check('no entropy at fixed initial action',arr[0,1]==0)
            gamma,alpha=float(row['gamma']),float(row['alpha'])
            # Reverse recurrence is independent of production's vector dot product.
            no_tail=0.
            for r,lp,_ in reversed(arr):no_tail=float(r)-alpha*float(lp)+gamma*no_tail
            tail_value=gamma**500*sum(min(q0,q1)-alpha*lp for q0,q1,lp in tail)/len(tail)
            near('soft reward recurrence',float(row['tail_free_return']),no_tail)
            near('tail value',float(row['discounted_tail']),tail_value)
            near('full soft estimate',float(row['soft_return']),no_tail+tail_value)
            near('initial twin min',float(row['q_min']),min(float(row['q0']),float(row['q1'])))
            identity=(row['task'],row['episode_index']);qq=(float(row['q0']),float(row['q1']))
            if identity in q_by_state:near('same fixed initial Q across repeats',qq,q_by_state[identity])
            q_by_state[identity]=qq
            check('unique MC action stream',row['action_noise_seed'] not in noise);noise.add(row['action_noise_seed'])
        check('all and only expected traces',set(trace.files)==expected)
    check('episode counts',len(episodes)==result['deterministic_episodes'] and len(mc)==result['MC_episodes'])
    check('environment step count',result['new_environment_steps']==500*(len(episodes)+len(mc)))
    check('original learner unchanged',result['learner_unchanged'])
    return len(episodes),len(mc)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('result');args=ap.parse_args();run=Run('verify_traces')
    try:
        rec=run.read(args.result);d,m=verify_record(rec,run.check,run.hashed)
        run.finish({'status':'completed','source':str(args.result),'deterministic_episodes_verified':d,'MC_episodes_verified':m,'new_diagnostic_environment_steps':0})
    except Exception:
        run.finish({'status':'failed','traceback':traceback.format_exc()});raise


if __name__=='__main__':main()
