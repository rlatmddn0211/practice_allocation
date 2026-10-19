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

