"""NumPy-only batch replacement contract. No learner is executed by this module.

Native sampling stays outside this function. Replacement fields are independent
of native sampling and rollout RNG. A later runtime adapter must still pass the
original-SAC/zero-replacement and exact-resume checks before research is allowed.
"""
from __future__ import annotations
import hashlib
import numpy as np
from detector import derived_seed

def replacement_fields(protocol_version, parent_id, future_id, update_id, n, pool_size, root_seed):
    if pool_size < 1: raise ValueError('Empty archive pool')
    fields = {}
    key=(protocol_version,root_seed,parent_id,future_id,int(update_id))
    for name in ('replacement','episode','offset'):
        rng=np.random.Generator(np.random.PCG64(derived_seed(*key,name)))
        fields[name]=rng.random(n)
    episodes=np.floor(fields['episode']*pool_size).astype(np.int64)
    offsets=np.floor(fields['offset']*32).astype(np.int64)
    fingerprint=hashlib.sha256(b''.join(fields[n].astype('<f8').tobytes() for n in ('replacement','episode','offset'))).hexdigest()
    return fields['replacement'],episodes,offsets,fingerprint

def replace_batch(native, archive, parent_id, future_id, update_id, root_seed, arm, probability=.25):
    """archive array shape = [episodes,32,...], native array shape = [256,...].

    Native dones already have the original timeout correction; archive dones
    must be assembled with that same correction, never the window edge.
    Returns actual-use provenance separately from the original native draws.
    """
    if arm not in ('BASE','ONSET','RANDOM_PRE'): raise ValueError(arm)
    n=len(native['observations'])
    if n!=256: raise ValueError('Original batch must contain exactly 256 slots')
    tasks=np.argmax(native['observations'][:,-4:],axis=1)
    result={k:v.copy() for k,v in native.items()}
    mask=np.zeros(n,dtype=bool); episode=np.full(n,-1,dtype=np.int64);offset=np.full(n,-1,dtype=np.int64);fp=None
    if arm!='BASE' and probability>0:
        u,episode,offset,fp=replacement_fields('onset_reuse_pilot_v1',parent_id,future_id,update_id,n,len(archive['observations']),root_seed)
        mask=(tasks==0)&(u<probability)
        for name in native:
            if name in archive: result[name][mask]=archive[name][episode[mask],offset[mask]]
    if not np.array_equal(np.argmax(result['observations'][:,-4:],axis=1),tasks):
        raise RuntimeError('Replacement changed native task slot counts')
    return result,dict(replaced_mask=mask,episode_indices=episode,offsets=offset,
        common_draw_hash=fp,native_task_counts=np.bincount(tasks,minlength=4),replaced_DO=int(mask.sum()),
        native_draw_transition_ids=native.get('transition_ids'),
        actual_native_transition_ids=native['transition_ids'][~mask] if 'transition_ids' in native else None,
        actual_archive_transition_ids=result['transition_ids'][mask] if 'transition_ids' in result else None)

def contract_checks():
    checks=[]
    def ck(name,truth):
        checks.append(dict(check=name,passed=bool(truth),scope='synthetic sampler contract; no SAC runtime'))
        if not truth:raise AssertionError(name)
    native={'observations':np.zeros((256,43),np.float32),'actions':np.zeros((256,4),np.float32),
        'next_observations':np.zeros((256,43),np.float32),'rewards':np.zeros((256,1),np.float32),
        'dones':np.zeros((256,1),np.float32),'transition_ids':np.arange(1,257,dtype=np.int64)}
    for i in range(256):native['observations'][i,39+i%4]=native['next_observations'][i,39+i%4]=1
    archive={k:np.zeros((9,32)+v.shape[1:],dtype=v.dtype) for k,v in native.items()}
    archive['observations'][:,:,39]=archive['next_observations'][:,:,39]=1
    archive['transition_ids'][:]=10000+np.arange(9*32).reshape(9,32)
    original=np.random.get_state()
    p,mp=replace_batch(native,archive,'R01','F01',999001,123,'ONSET')
    u,mu=replace_batch(native,archive,'R01','F01',999001,123,'RANDOM_PRE')
    after=np.random.get_state()
    ck('replacement preserves legacy global NumPy RNG',original[0]==after[0] and np.array_equal(original[1],after[1]) and original[2:]==after[2:])
    ck('P U primitive draws and episode offsets correspond',mp['common_draw_hash']==mu['common_draw_hash'] and np.array_equal(mp['episode_indices'],mu['episode_indices']) and np.array_equal(mp['offsets'],mu['offsets']))
    ck('all task slots preserved exactly',np.array_equal(mp['native_task_counts'],[64,64,64,64]) and np.all(np.argmax(p['observations'][mp['replaced_mask'],-4:],axis=1)==0))
    z,mz=replace_batch(native,archive,'R01','F01',999001,123,'ONSET',probability=0)
    b,mb=replace_batch(native,archive,'R01','F01',999001,123,'BASE')
    ck('zero replacement and BASE leave original arrays bitwise identical',all(np.array_equal(v,z[k]) and np.array_equal(v,b[k]) for k,v in native.items()))
    ck('actual native use excludes replaced original draws',len(mp['actual_native_transition_ids'])+len(mp['actual_archive_transition_ids'])==256 and len(mp['actual_native_transition_ids'])==256-mp['replaced_DO'])
    ck('no window-edge artificial terminal',not p['dones'].any())
    # Statistical contract at a fixed, outcome-independent number of array draws.
    counts=np.zeros(9,dtype=int);off=np.zeros(32,dtype=int);total=0;replaced=0
    for update in range(800):
        fields,ep,ofs,_=replacement_fields('fixture','R01','F01',update,256,9,123)
        counts+=np.bincount(ep,minlength=9);off+=np.bincount(ofs,minlength=32)
        total+=256;replaced+=int((fields<.25).sum())
    ck('episode and offset marginals uniform within fixed 6 sigma audit',np.max(np.abs(counts-total/9))<6*np.sqrt(total*(1/9)*(8/9)) and np.max(np.abs(off-total/32))<6*np.sqrt(total*(1/32)*(31/32)))
    ck('Bernoulli rate within fixed 6 sigma audit',abs(replaced-total*.25)<6*np.sqrt(total*.25*.75))
    return checks
