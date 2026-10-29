"""Launch the frozen watcher without a visible Windows terminal."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from deferred_queue import ROOT,source_hashes,sha,utc,exclusive_json,load

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--static-dir',required=True);a=ap.parse_args()
    verified=Path(a.static_dir).resolve()
    marker=load(verified/'COMPLETE.json');summary=load(verified/'summary.json')
    if marker['summary_sha256']!=sha(verified/'summary.json') or summary['status']!='passed':
        raise RuntimeError('Static source/input/unit verification is not passed')
    sources=source_hashes(ROOT)
    if sources!=load(verified/'source_hashes.json'):raise RuntimeError('Sources changed after static verification')
    out=ROOT/'results'/(time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'_launch_'+uuid.uuid4().hex[:8])
    (out/'source_snapshot').mkdir(parents=True)
    for name,h in sources.items():
        target=out/'source_snapshot'/(h[:20]+Path(name).suffix)
        if not target.exists():shutil.copy2(ROOT/name,target)
    exclusive_json(out/'source_hashes.json',sources)
    exclusive_json(ROOT/'results/LAUNCH_CLAIM.json',{'launch':str(out),'created_at':utc(),
        'static_dir':str(verified),'automatic_retry':False})
    command=[sys.executable,'-B',str(ROOT/'deferred_queue.py')]
    env={**os.environ,'PYTHONIOENCODING':'utf-8','PYTHONDONTWRITEBYTECODE':'1',
         'OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
    with (out/'stdout.log').open('x',encoding='utf-8') as stdout,(out/'stderr.log').open('x',encoding='utf-8') as stderr:
        proc=subprocess.Popen(command,cwd=ROOT,env=env,stdout=stdout,stderr=stderr,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    exclusive_json(out/'process.json',{'pid':proc.pid,'command':command,'started_at':utc(),
        'hidden_window':True,'static_verification':str(verified),'new_environment_steps_at_launch':0})
    for _ in range(40):
        if proc.poll() is not None:raise RuntimeError('Watcher exited; inspect retained launch logs')
        active=ROOT/'ACTIVE_QUEUE.json'
        if active.exists():
            value=load(active)
            if value.get('pid')==proc.pid:
                exclusive_json(out/'queue.json',value)
                print(json.dumps({'pid':proc.pid,'launch':str(out),**value},ensure_ascii=False),flush=True)
                return
        time.sleep(.25)
    raise RuntimeError('Watcher did not advertise its exact queue within10s; inspect logs before any manual intervention')
if __name__=='__main__':main()
