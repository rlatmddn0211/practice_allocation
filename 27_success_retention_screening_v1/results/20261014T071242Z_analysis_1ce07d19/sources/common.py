"""Standalone read-only provenance and experiment IO for this independent screen."""
from __future__ import annotations
import csv
import hashlib
import importlib.metadata
import json
import platform
import shutil
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def save(path, data):
    with Path(path).open('x', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write('\n')

def table(path, rows):
    if not rows:
        return
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with Path(path).open('x', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)

def seed_for(*parts):
    return int(hashlib.sha256('|'.join(map(str, parts)).encode()).hexdigest()[:8],16)

class Run:
    def __init__(self, label):
        self.started, self.cpu = time.perf_counter(), time.process_time()
        self.out = HERE / 'results' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + label + '_' + uuid.uuid4().hex[:8])
        self.out.mkdir(parents=True, exist_ok=False)
        self.inputs, self.checks = {}, []
        sources = {}
        for p in list(HERE.glob('*.py')) + [HERE/'protocol.json', HERE/'requirements.txt']:
            if p.exists():
                dest=self.out/'sources'/p.name
                dest.parent.mkdir(exist_ok=True)
                shutil.copy2(p,dest)
                sources[p.name]=sha(dest)
        save(self.out/'source_hashes.json',sources)
        save(self.out/'runtime.json', {'python':sys.version,'executable':sys.executable,'platform':platform.platform(),
             'packages':{n:importlib.metadata.version(n) for n in ['torch','numpy','scipy','stable-baselines3','gymnasium']},
             'argv':sys.argv, 'new_environment_steps':0,'new_learner_updates':0})
        print(str(self.out),flush=True)

    def check(self, name, ok, detail=None):
        self.checks.append({'name':name,'passed':bool(ok),'detail':detail})
        if not ok:
            raise AssertionError(name + ': ' + str(detail))

    def hashed(self,path,expected=None):
        path=Path(path)
        value=sha(path)
        if expected is not None:
            self.check('hash matches: '+str(path),value==expected)
        if str(path) in self.inputs:
            self.check('input stable: '+str(path),value==self.inputs[str(path)])
        self.inputs[str(path)]=value
        return value

    def read(self,path,expected=None):
        self.hashed(path,expected)
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))

    def rows(self,path):
        self.hashed(path)
        with Path(path).open(encoding='utf-8-sig',newline='') as f:
            return list(csv.DictReader(f))

    def finish(self,summary):
        summary.update(wall_seconds=time.perf_counter()-self.started,cpu_seconds=time.process_time()-self.cpu,
                       checks_passed=sum(c['passed'] for c in self.checks), checks_failed=sum(not c['passed'] for c in self.checks),
                       new_environment_steps=0,new_learner_updates=0)
        save(self.out/'input_hashes.json',self.inputs)
        save(self.out/'checks.json',self.checks)
        save(self.out/'summary.json',summary)
        print(json.dumps(summary,ensure_ascii=False),flush=True)

def campaign(run):
    active=run.read(ROOT/'13_e0_e3_autonomous_queue_v1/ACTIVE_CAMPAIGN.json')
    path=Path(active['campaign'])
    integrity=run.read(path/'plan_integrity.json')
    plan=run.read(path/'plan.json',integrity['sha256'])
    return path,{j['id']:j for j in plan['jobs']}

def record(run,cam,planned,jid):
    marker=run.read(cam/'completed'/(jid+'.json'))
    path=Path(marker['result_ref']['path'])
    rec=run.read(path,marker['result_ref']['sha256'])
    run.check('planned '+jid,rec['id']==jid and rec['stage']==planned[jid]['stage'])
    return rec,path

def contexts(p):
    return [(s,n,c) for s in p['suites'] for n in p['original_seeds'] for c in p['checkpoints'][s]]

def prefix(ctx):
    s,n,c=ctx
    return f"{'E1' if s=='A' else 'E3'}_{s}_s{n}_c{c//1000}"

def allocations(p,s):
    return ['U']+['F_'+t for t in p['suites'][s]]

def context_weight(ctx):
    return (0.5 if ctx[0]=='A' else 1.0)/9
