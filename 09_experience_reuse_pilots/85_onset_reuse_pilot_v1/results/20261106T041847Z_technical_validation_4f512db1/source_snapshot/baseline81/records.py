"""Lossless numerical records, passive physics, immutable snapshots and costs."""
from __future__ import annotations
import copy
import hashlib
import json
import os
import pickle
import shutil
import time
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import mujoco

ROOT=Path(__file__).resolve().parent
SCHEMA=1

def utc(): return datetime.now(timezone.utc).isoformat()
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def jsonable(x):
    if isinstance(x,np.ndarray):return x.tolist()
    if isinstance(x,np.generic):return x.item()
    if isinstance(x,Path):return str(x)
    raise TypeError(type(x).__name__)
def save(path,value,replace=False):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and not replace:raise FileExistsError(path)
    tmp=path.with_name(path.name+'.partial')
    with tmp.open('w',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False,default=jsonable);f.write('\n')
        f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)
def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def ref(path):return {'path':str(Path(path).resolve()),'bytes':Path(path).stat().st_size,'sha256':sha(path)}
def append(path,row):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False,default=jsonable,allow_nan=False)+'\n')
def snapshot_source(out):
    files=sorted(ROOT.glob('*.py'))+sorted(ROOT.glob('*.json'))+sorted(ROOT.glob('*.md'))
    files+=sorted((ROOT/'practice_allocation').glob('*.py'))+sorted((ROOT/'configs').glob('*.json'))
    mapping={}
    for p in files:
        relative=p.relative_to(ROOT).as_posix();dest=Path(out)/'source_snapshot'/relative
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
        mapping[relative]={'sha256':sha(p),'bytes':p.stat().st_size}
    save(Path(out)/'source_hashes.json',mapping)
    return mapping
def check_source(mapping):
    for name,row in mapping.items():
        if sha(ROOT/name)!=row['sha256']:raise RuntimeError('Frozen source changed: '+name)

class Table:
    """Immutable Parquet parts; never silently discard an incomplete buffer."""
    def __init__(self,path,flush_rows=4096):
        self.path=Path(path);self.path.mkdir(parents=True,exist_ok=True)
        self.rows=[];self.count=0;self.part=len(list(self.path.glob('part_*.parquet')));self.limit=flush_rows
    def add(self,row):
        self.rows.append(row);self.count+=1
        if len(self.rows)>=self.limit:self.flush()
    def flush(self):
        if not self.rows:return
        p=self.path/f'part_{self.part:06d}.parquet'
        if p.exists():raise FileExistsError(p)
        pq.write_table(pa.Table.from_pylist(self.rows),str(p)+'.partial',compression='zstd')
        os.replace(str(p)+'.partial',p);self.part+=1;self.rows=[]

class Cost:
    """Each actual raw step gets an issued/completed binary pair, no JSON per step.

    An unmatched I is disclosed as uncertain/charged, never erased. Reset internal
    simulator work is outside control transitions and counted separately.
    """
    def __init__(self,path,category,cap,prior=0):
        self.path=Path(path);self.path.mkdir(parents=True,exist_ok=True)
        self.category=category;self.cap=int(cap);self.issued=int(prior);self.completed=int(prior)
        self.resets=0;self.creations=0;self.started=time.perf_counter()
        self.journal=(self.path/(category+'_control_journal.bin')).open('xb',buffering=0)
        self.calls=0;self.total_seconds=0.0
    def step(self,episode,action):
        return self.call(episode.step,action)
    def call(self,function,*args):
        if self.issued>=self.cap:raise RuntimeError('Environment transition cap exhausted: '+self.category)
        self.journal.write(b'I');self.issued+=1
        started=time.perf_counter()
        try:result=function(*args)
        except BaseException:
            self.journal.write(b'F');raise
        self.journal.write(b'C');self.completed+=1
        self.calls+=1;self.total_seconds+=time.perf_counter()-started
        return result
    def checkpoint(self,**extra):
        row={'category':self.category,'issued_charged':self.issued,'completed_transitions':self.completed,
            'resets':self.resets,'creations':self.creations,'wall_seconds':time.perf_counter()-self.started,
            'step_call_seconds':self.total_seconds,'step_calls':self.calls,**extra}
        save(self.path/(self.category+'_costs.json'),row,replace=True);return row
    def close(self):
        self.checkpoint();self.journal.close()

def primitive(x):
    if x is None or isinstance(x,(str,bool,int,float,np.generic,np.ndarray)):return True
    if isinstance(x,(tuple,list)):return all(primitive(v) for v in x)
    if isinstance(x,dict):return all(isinstance(k,(str,int)) and primitive(v) for k,v in x.items())
    return False

MODEL_ARRAYS=('body_pos','body_quat','site_pos','site_quat','geom_pos','geom_quat','geom_size','eq_data')

def capture_environment(episode):
    env=episode.raw;spec=mujoco.mjtState.mjSTATE_INTEGRATION
    state=np.empty(mujoco.mj_stateSize(env.model,spec),dtype=np.float64)
    mujoco.mj_getState(env.model,env.data,state,spec)
    attrs={k:copy.deepcopy(v) for k,v in vars(env).items() if primitive(v)}
    rng=env.__dict__.get('_np_random')
    return {'schema_version':SCHEMA,'state_kind':'diagnostic_state_pending_verification',
        'task_index':episode.task_index,'seed':episode.seed,'steps':episode.steps,'any_success':episode.any_success,
        'observation':episode.observation.copy(),'raw_observation':episode.last_raw_observation.copy(),
        'initial_state_hash':episode.initial_state_hash,'integration_spec':int(spec),'integration_state':state,
        'model_arrays':{k:getattr(env.model,k).copy() for k in MODEL_ARRAYS},'environment_attributes':attrs,
        'environment_rng':copy.deepcopy(rng.bit_generator.state) if rng is not None else None,
        'model_name':str(env.model_name),'frame_skip':int(env.frame_skip),'control_dt':float(env.dt),
        'wrapper_state':'none; explicit TaskEpisode collector','policy_internal_state':'feedforward SAC; none'}

def restore_environment(state,episode_class,counters):
    ep=episode_class(state['task_index'],state['seed'],counters);env=ep.raw
    for k,v in state['model_arrays'].items():getattr(env.model,k)[:]=v
    for k,v in state['environment_attributes'].items():setattr(env,k,copy.deepcopy(v))
    if state['environment_rng'] is not None:env.__dict__['_np_random'].bit_generator.state=copy.deepcopy(state['environment_rng'])
    mujoco.mj_setState(env.model,env.data,state['integration_state'],state['integration_spec'])
    mujoco.mj_forward(env.model,env.data)
    # Forward rebuilds derived fields; restore the integration inputs/warm start.
    mujoco.mj_setState(env.model,env.data,state['integration_state'],state['integration_spec'])
    ep.steps=state['steps'];ep.any_success=state['any_success'];ep.observation=state['observation'].copy()
    ep.last_raw_observation=state['raw_observation'].copy()
    return ep

def dump_snapshot(path,episode):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():return str(path)
    with Path(str(path)+'.partial').open('xb') as f:pickle.dump(capture_environment(episode),f,protocol=5)
    os.replace(str(path)+'.partial',path);return str(path)

class Physics:
    """Only validated data/model array reads, no observation/reward/RNG getters."""
    def __init__(self,episode):
        self.ep=episode;self.env=episode.raw;t=episode.task_index;m=self.env.model
        self.body_name=('drawer_link','drawer_link','obj','button')[t]
        self.offset=np.array(((0,-.16,0),(0,-.16,.05),(0,0,0),(0,-.193,0))[t],dtype=np.float64)
        self.bid=int(m.body(self.body_name).id)
        self.left=int(m.site('leftEndEffector').id);self.right=int(m.site('rightEndEffector').id)
        self.joint_name=('goal_slidey','goal_slidey',None,'btnbox_joint')[t]
        self.qpa=self.qva=None
        if self.joint_name:
            j=m.joint(self.joint_name);self.qpa=int(j.qposadr[0]);self.qva=int(j.dofadr[0])
        robot_names=('hand','rightclaw','leftclaw','rightpad','leftpad')
        self.robot_bodies={int(m.body(n).id) for n in robot_names}
        self.schema={'schema_version':SCHEMA,'task_index':t,'object_body':self.body_name,'object_point_offset_world_m':self.offset.tolist(),
            'joint_name':self.joint_name,'qpos_address':self.qpa,'qvel_address':self.qva,
            'tcp':'mean(leftEndEffector,rightEndEffector) site world xyz',
            'coordinates':'MuJoCo world xyz; metres, radians, seconds; quaternions wxyz',
            'object_cvel':'raw MuJoCo body cvel spatial velocity; no reinterpretation as object-point derivative',
            'timing':'after raw step, before learner update; contact at control-step endpoint only',
            'contact_sample_mode':'all endpoint contact geom pairs and distances; robot-object count identified by body IDs',
            'frame_skip':int(self.env.frame_skip),'physics_timestep':float(m.opt.timestep),
            'control_dt':float(self.env.dt),'geom_bodyid':m.geom_bodyid.tolist(),
            'geom_names':[m.geom(i).name or None for i in range(m.ngeom)],
            'body_names':[m.body(i).name or None for i in range(m.nbody)],
            'push_manipulation_joint':'unavailable as scalar: object is a free joint; raw qpos/qvel retained'}
    def sample(self):
        d=self.env.data;m=self.env.model
        left=d.site_xpos[self.left].copy();right=d.site_xpos[self.right].copy();tcp=(left+right)*.5
        obj=d.xpos[self.bid].copy()+self.offset;goal=self.env._target_pos.copy()
        contacts=np.array([[int(c.geom1),int(c.geom2),float(c.dist)] for c in d.contact[:d.ncon]],dtype=np.float64).reshape(-1,3)
        robot_object=0
        for a,b,_ in contacts:
            ba,bb=int(m.geom_bodyid[int(a)]),int(m.geom_bodyid[int(b)])
            robot_object+=int((ba in self.robot_bodies and bb==self.bid) or (bb in self.robot_bodies and ba==self.bid))
        return {'qpos':d.qpos.copy(),'qvel':d.qvel.copy(),'tcp':tcp,'gripper_width':float(np.linalg.norm(left-right)),
            'object_pos':obj,'object_quat':d.xquat[self.bid].copy(),'object_cvel':d.cvel[self.bid].copy(),
            'goal':goal,'tcp_object_distance':float(np.linalg.norm(tcp-obj)),
            'object_goal_distance':float(np.linalg.norm(obj-goal)),
            'joint_position':float(d.qpos[self.qpa]) if self.qpa is not None else np.nan,
            'joint_velocity':float(d.qvel[self.qva]) if self.qva is not None else np.nan,
            'simulation_time':float(d.time),'contacts':contacts,'robot_object_contact_pairs':robot_object}

class Trajectory:
    def __init__(self,path,metadata):
        self.path=Path(path);self.meta=metadata;self.rows=[];self.start=time.perf_counter()
        self.path.parent.mkdir(parents=True,exist_ok=True)
    def add(self,**row):self.rows.append(row)
    def flush(self):
        if not self.rows:return None
        compression_started=time.perf_counter()
        if self.path.exists():raise FileExistsError(self.path)
        keys=self.rows[0].keys();arrays={}
        for k in keys:
            if k=='contacts':continue
            values=[r[k] for r in self.rows]
            arrays[k]=np.asarray(values)
            if arrays[k].dtype==object:raise TypeError('Object array would break numerical schema: '+k)
        counts=np.array([len(r['contacts']) for r in self.rows],dtype=np.int64)
        arrays['contact_offsets']=np.r_[0,np.cumsum(counts)]
        arrays['contacts']=np.concatenate([r['contacts'] for r in self.rows],axis=0)
        with Path(str(self.path)+'.partial').open('xb') as f:np.savez_compressed(f,**arrays)
        os.replace(str(self.path)+'.partial',self.path)
        save(self.path.with_suffix('.json'),{**self.meta,'rows':len(self.rows),'trajectory':ref(self.path),
            'schema_version':SCHEMA,'seconds_including_rollout':time.perf_counter()-self.start,
            'compression_write_hash_seconds':time.perf_counter()-compression_started})
        return str(self.path)

class Video:
    def __init__(self,path,episode):
        import imageio.v2 as imageio
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.renderer=mujoco.Renderer(episode.raw.model,height=240,width=320)
        self.writer=imageio.get_writer(self.path,fps=20,codec='libx264',quality=7,macro_block_size=16)
        self.ep=episode;self.frames=[]
        self.render_encode_seconds=0.
    def frame(self,step):
        started=time.perf_counter()
        self.renderer.update_scene(self.ep.raw.data,camera='corner')
        self.writer.append_data(self.renderer.render().copy());self.frames.append(step)
        self.render_encode_seconds+=time.perf_counter()-started
    def close(self):
        self.writer.close();self.renderer.close()
        save(self.path.with_suffix('.json'),{'frame_to_episode_step':self.frames,'fps':20,'stride':5,
            'camera':'corner','width':320,'height':240,'playback_seconds_not_simulation_seconds':True,
            'render_encode_seconds':self.render_encode_seconds})
