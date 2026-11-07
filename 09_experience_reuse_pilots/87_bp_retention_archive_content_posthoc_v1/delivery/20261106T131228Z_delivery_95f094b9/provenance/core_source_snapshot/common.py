"""Immutable file-only provenance and shared87 analysis definitions."""
from __future__ import annotations
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import shutil
import sys
import time
import uuid
from datetime import datetime,timezone

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
V85=ROOT/'85_onset_reuse_pilot_v1'
CAMPAIGN=V85/'results/20261106T042248Z_onset_campaign_24d98d21'
ANALYSIS=CAMPAIGN/'analysis/20261106T111509Z_paired_3db89d3f'
PREP=V85/'results/20261106T040844Z_preparation_31c9735e'
ORIGINAL=ROOT/'81_basic_sac_observation_campaign_v1/results/20261102T085036Z_observation_8e858967'
SITE=ROOT/'13_e0_e3_autonomous_queue_v1/.venv/Lib/site-packages'
RUNS=['R01','R02','R03','R04','R05'];ARMS=['BASE','RANDOM_PRE','ONSET'];TIMES=[0,16000,32000,64000]
PAIRS=[('P-U','ONSET','RANDOM_PRE'),('P-B','ONSET','BASE'),('U-B','RANDOM_PRE','BASE')]
ZERO=dict(environment_creations=0,resets=0,environment_transitions=0,environment_restores=0,mujoco_forward=0,
    model_loads=0,policy_forwards=0,learning_updates=0,new_bootstrap_draws=0)
FORBIDDEN={'torch','mujoco','metaworld','gym','gymnasium','stable_baselines3','tensorflow','jax'}


def guard():
    def hook(event,args):
        if event=='import' and str(args[0]).split('.')[0] in FORBIDDEN:raise RuntimeError('File-only87 forbids '+str(args[0]))
    sys.addaudithook(hook)
    if FORBIDDEN&set(sys.modules):raise RuntimeError('Runtime/model modules already imported')


def utc():return datetime.now(timezone.utc).isoformat()
def clean(v):
    if isinstance(v,dict):return {str(k):clean(x) for k,x in v.items()}
    if isinstance(v,(tuple,list)):return [clean(x) for x in v]
    if isinstance(v,Path):return str(v)
    if hasattr(v,'tolist'):return clean(v.tolist())
    if isinstance(v,float) and not math.isfinite(v):return None
    return v
def save(p,value,replace=False):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists() and not replace:raise FileExistsError(p)
    tmp=p.with_name(p.name+'.partial')
    with tmp.open('x',encoding='utf-8',newline='\n') as f:json.dump(clean(value),f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    os.replace(tmp,p)
def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def new_output(role):
    out=HERE/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+role+'_'+uuid.uuid4().hex[:8]);out.mkdir(parents=True,exist_ok=False)
    snap=out/'source_snapshot';snap.mkdir()
    for p in HERE.iterdir():
        if p.is_file() and p.suffix in {'.py','.json','.md'} and not p.name.startswith('LATEST'):shutil.copy2(p,snap/p.name)
    save(out/'source_hashes.json',{p.name:sha(p) for p in snap.iterdir()})
    return out
class Inputs:
    def __init__(self):self.rows={};self.bytes_read=0
    def ref(self,p,role,expected=None):
        p=Path(p).resolve()
        if not p.is_file():raise FileNotFoundError(p)
        k=str(p)
        if k not in self.rows:
            self.rows[k]=dict(path=k,bytes=p.stat().st_size,sha256=sha(p),roles=[]);self.bytes_read+=p.stat().st_size
        r=self.rows[k]
        if role not in r['roles']:r['roles'].append(role)
        if expected is not None and expected!=r['sha256']:raise RuntimeError('Input hash differs '+k)
        return p
    def json(self,p,role):return load(self.ref(p,role))
    def parquet(self,p,role):
        import pandas as pd
        return pd.read_parquet(self.ref(p,role))
    def csv(self,p,role):
        import pandas as pd
        return pd.read_csv(self.ref(p,role))
    def arrays(self,p,role,fields=None,expected=None):
        import numpy as np
        with np.load(self.ref(p,role,expected),allow_pickle=False) as z:return {k:z[k].copy() for k in (fields or z.files)}
    def text(self,p,role,expected=None):return self.ref(p,role,expected).read_text(encoding='utf-8-sig')
    def flush(self,out):
        (Path(out)/'input_manifest.jsonl').write_text(''.join(json.dumps(clean(r),ensure_ascii=False)+'\n' for r in sorted(self.rows.values(),key=lambda x:x['path'])),encoding='utf-8')
class Checks:
    def __init__(self):self.rows=[]
    def add(self,name,ok,detail=''):
        self.rows.append(dict(check=name,passed=bool(ok),detail=str(detail)))
        if not ok:raise AssertionError(name+': '+str(detail))
    def flush(self,out):
        import pandas as pd
        pd.DataFrame(self.rows).to_csv(Path(out)/'verification_checks.csv',index=False)
def md(frame,digits=3):
    if len(frame)==0:return '해당 행 없음.'
    text=['| '+' | '.join(map(str,frame.columns))+' |','| '+' | '.join(['---']*len(frame.columns))+' |']
    for r in frame.itertuples(index=False,name=None):
        row=[]
        for v in r:
            if v is None or isinstance(v,float) and not math.isfinite(v):row.append('NA')
            elif isinstance(v,float):row.append(f'{v:.{digits}f}')
            else:row.append(str(v).replace('|','/'))
        text.append('| '+' | '.join(row)+' |')
    return '\n'.join(text)
