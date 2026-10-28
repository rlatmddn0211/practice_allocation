"""Pinned intervention inputs, exact restoration, paired futures and ledgers."""
import copy
import csv
import gc
import json
import os
import pickle
import uuid
from datetime import datetime, timezone
from pathlib import Path

os.environ['PRACTICE_SUITE'] = 'B'
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
import numpy as np
import torch
from practice_allocation.core import (
    ROOT, TASKS, Config, AllocationSchedule, capture_rng, derived_seed, file_sha256,
    fingerprint, package_versions, restore_rng, seed_learning, source_hashes, utc_now, write_json)
from practice_allocation.study_io import (
    IntegrityError, bank_sets, load_portable, load_banks, read_json)

REPOSITORY = ROOT.parent
TOTAL_CAP = 10_100_000
TECH_CAP = 20_000

def unique(parent, label):
    out = Path(parent)/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+label+'_'+uuid.uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    return out

def atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name+'.'+uuid.uuid4().hex[:8]+'.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n',encoding='utf-8')
    os.replace(tmp,path)

def reference(path):
    path = Path(path).resolve()
    return {'path':str(path),'sha256':file_sha256(path)}

def checked(ref):
    path=Path(ref['path'])
    if file_sha256(path)!=ref['sha256']:
        raise IntegrityError('Pinned input changed: '+str(path))
    return path

def read_csv(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))

def frozen_inputs():
    p=read_json(ROOT/'protocol.json')
    states=read_json(ROOT/'inputs/state_manifest.json')
    jobs=read_json(ROOT/'inputs/jobs.json')
    if isinstance(jobs,dict): jobs=jobs['jobs']
    if len(states)!=5 or [s['parent'] for s in states]!=list(range(41011,41016)) or any(s['prefix_continuation']!=4201 for s in states):
        raise IntegrityError('Five fixed prefix4201 states changed')
    if len(jobs)!=40 or {(j['parent'],j.get('arm'),j['future']) for j in jobs}!={(r,c,n) for r in range(41011,41016) for c in 'ABCD' for n in (1,2)} or any(j['condition']!='dose625' for j in jobs):
        raise IntegrityError('Frozen forty-job coverage changed')
    if any(s['packages']!=package_versions() for s in states):
        raise IntegrityError('Checkpoint package versions changed')
    # All references are validated, including the provenance bundle; no result-dependent selection.
    for rel,h in p.get('input_hashes',{}).items():
        path=ROOT/rel
        if file_sha256(path)!=h: raise IntegrityError('Frozen file changed: '+rel)
    for r in states:
        checked(r['bank'])
    for parent in range(41011,41016):
        for fid in (1,2):
            pair=[j for j in jobs if j['parent']==parent and j['future']==fid]
            if len({j['root_seed'] for j in pair})!=1 or len({j['schedule_seed'] for j in pair})!=1:
                raise IntegrityError('Arms do not share the declared paired future streams')
    return p,states,jobs

def config_for(state):
    ref=state['checkpoint']; cp=Path(ref['path'])
    if file_sha256(cp/'checkpoint_manifest.json')!=ref['manifest_sha256']:
        raise IntegrityError('Original S manifest changed')
    m=read_json(cp/'checkpoint_manifest.json')
    if m['step']!=208000: raise IntegrityError('Wrong S checkpoint')
    for name,h in m['files'].items():
        if Path(name).name!=name or file_sha256(cp/name)!=h:
            raise IntegrityError('Original S binary changed: '+name)
    with (cp/'collector_and_rng.pkl').open('rb') as f: saved=pickle.load(f)
    config=Config(**saved['config']);config.validate()
    required={'learning_rate':3e-4,'batch_size':256,'buffer_size':100000,
              'gamma':0.99,'tau':0.005,'net_arch':[256,256],'learning_starts':1000,
              'train_freq':1,'gradient_steps':1,'n_critics':2}
    if any(getattr(config,k)!=v for k,v in required.items()):
        raise IntegrityError('Checkpoint differs from authorized SAC baseline specification')
    return config

def load_state(state,costs,out=None,engine_class=None):
    if engine_class is None:
        from telemetry import BaselineEngine
        engine_class=BaselineEngine
    engine=load_portable(state['checkpoint'],config_for(state),costs,engine_class)
    if not engine.at_boundary or engine.model.num_timesteps!=208000 or engine.model._n_updates!=207000:
        raise IntegrityError('Wrong learned boundary or warm-up/update state')
    if engine.schedule.candidate!='dose625' or engine.model.replay_buffer.branch_start_step!=200000:
        raise IntegrityError('Wrong original concentration/replay history')
    if engine.reset_root!=state['old_continuation_rng_seed']:
        raise IntegrityError('Original continuation RNG root changed')
    _,states,_=frozen_inputs()
    engine.forbidden=bank_sets([s['bank'] for s in states])
    if out is not None: engine.audit_path=Path(out)/'training_reset_audit.csv'
    return engine

def nonrandom_fingerprints(engine):
    c=copy.deepcopy(engine.boundary_state())
    c.pop('reset_root');c['schedule'].pop('rng');c['schedule'].pop('candidate')
    f=engine.fingerprints()
    return {'learning':f['learning'],'replay':f['replay'],
            'collector_except_future_rng_and_candidate':fingerprint(c),
            'config':fingerprint(engine.config.to_dict())}

def fork_future(engine,job):
    before=nonrandom_fingerprints(engine)
    schedule_before=engine.schedule.state()
    if schedule_before['position']!=len(schedule_before['block']):
        raise IntegrityError('S has a pending task queue: cannot switch without a frozen rule')
    if len(schedule_before['block'])!=16 or schedule_before['blocks_generated']!=1:
        raise IntegrityError('S is not the end of the first original 8k dose block')
    old=capture_rng()
    engine.reset_root=int(job['root_seed'])
    engine.schedule.candidate=job['condition']
    engine.schedule.rng.bit_generator.state=copy.deepcopy(np.random.default_rng(int(job['schedule_seed'])).bit_generator.state)
    # Preserve counters, old exhausted queue, optimizer, replay and warm-up state.
    seed_learning(int(job['root_seed']))
    after=nonrandom_fingerprints(engine)
    changes={k:fingerprint(old[k])!=fingerprint(capture_rng()[k]) for k in old}
    if before!=after or not all(changes.values()):
        raise IntegrityError('Collection fork changed learned state or did not replace random streams')
    return {'before':before,'after':after,'schedule_before':schedule_before,
            'schedule_after':engine.schedule.state(),'global_rng_streams_changed':changes,
            'condition':job['condition'],'root_seed':job['root_seed'],
            'preserved_visits_and_queue':True,'replay_branch_boundary_preserved':200000,
            'telemetry_new_experience_boundary':208000}

def expected_order(engine,episodes=64):
    clone=AllocationSchedule.from_state(engine.schedule.state())
    return [clone.next_task() for _ in range(episodes)]

def reserve(costs,maximum_additional,cap):
    if costs.environment_steps+maximum_additional>cap:
        raise IntegrityError('Environment step reservation would exceed cap')

def close_engine(engine):
    if engine is not None:
        telemetry=getattr(engine,'telemetry',None)
        if telemetry is not None: telemetry.close()
        engine.close()
    gc.collect()

def fixed_panel(engine,parent,count_per_task=64):
    replay=engine.model.replay_buffer
    length=replay.size();ids=replay.observations[:length,0,-4:].argmax(1)
    rng=np.random.default_rng(derived_seed(640202,6401,parent))
    indices=[]
    for t in range(4):
        options=np.flatnonzero(ids==t)
        if len(options)<count_per_task: raise IntegrityError('Insufficient training-panel support')
        indices.extend(rng.choice(options,size=count_per_task,replace=False).tolist())
    idx=np.array(indices,dtype=np.int64)
    obs=replay.observations[idx,0].copy()
    provenance={'replay_indices':idx.tolist(),'birth_steps':replay.birth_steps[idx].tolist(),
                'selection_seed':derived_seed(640202,6401,parent),'source':'S training replay; no outcome labels used'}
    return {'observations':obs,'task_indices':ids[idx].copy(),'replay_indices':idx,
            'birth_steps':replay.birth_steps[idx].copy(),'selection_seed':derived_seed(640202,6401,parent),
            'fingerprint':fingerprint({'observations':obs,'birth_steps':replay.birth_steps[idx]}),'provenance':provenance}

def case_bank(state,subset):
    selected=read_json(checked(state['selected_cases']))
    # Prepared inputs retain complete bank records and explicit nested E50/T20 membership.
    if isinstance(selected,list):
        rows=[r for r in selected if subset=='E50' or r.get('in_T20',False)]
    else:
        rows=selected.get(subset,selected.get('entries',[]))
        if subset=='T20' and 'T20' not in selected:
            rows=[r for r in rows if r.get('in_T20',False)]
    if rows and 'initial_state' in rows[0]: return rows
    original=load_banks(state['bank'])['outcome']
    wanted={(r['task'],int(r['episode_index'])) for r in rows}
    return [r for r in original if (r['task'],r['episode_index']) in wanted]

def verify_input_files(state):
    cp=Path(state['checkpoint']['path'])
    if file_sha256(cp/'checkpoint_manifest.json')!=state['checkpoint']['manifest_sha256']:
        raise IntegrityError('Original S manifest changed')
    for name,h in read_json(cp/'checkpoint_manifest.json')['files'].items():
        if file_sha256(cp/name)!=h: raise IntegrityError('Original S binary changed')
    checked(state['bank'])
