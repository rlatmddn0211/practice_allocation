"""Sequential immutable stage-1 campaign. Later scientific stages are gated."""
import argparse
import csv
import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

os.environ['PRACTICE_SUITE']='B'
from practice_allocation.core import source_hashes, derived_seed
from practice_allocation.study_io import source_snapshot
HERE=Path(__file__).resolve().parent; REPO=HERE.parent
PYTHON=REPO/'13_e0_e3_autonomous_queue_v1/.venv/Scripts/python.exe'


def now(): return datetime.now(timezone.utc).isoformat()
def unique(label): return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_')+label+'_'+uuid.uuid4().hex[:8]
def sha(path):
    with Path(path).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def read(path, expected=None):
    if expected is not None and sha(path)!=expected: raise RuntimeError('Integrity: '+str(path))
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def write(path, obj):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8',newline='\n') as f: json.dump(obj,f,indent=2,ensure_ascii=False,allow_nan=False); f.write('\n')
def atomic(path,obj):
    path=Path(path); temp=path.with_name(path.name+'.'+uuid.uuid4().hex[:8]+'.tmp'); write(temp,obj); os.replace(temp,path)
def reference(path): return {'path':str(Path(path).resolve()),'sha256':sha(path)}
def ref(jid,key): return {'from_job':jid,'key':key}


def historical_exclusions(out):
    old=Path(read(REPO/'33_remaining_factor_queue_v1/ACTIVE_CAMPAIGN.json')['campaign'])
    base=old/'historical_forbidden.json'; oldplan=read(old/'plan.json',read(old/'plan_integrity.json')['sha256'])
    data=read(base,oldplan['historical_forbidden_sha256'])
    states=set(data['states']); parameters=set(data['parameters']); seeds=set(data['seeds']); inputs={str(base):sha(base)}
    # Include all historical bank files and passive training reset audits, not model archives.
    for directory in sorted(REPO.iterdir()):
        if not directory.is_dir() or not directory.name[:2].isdigit() or int(directory.name[:2])>42: continue
        for path in (directory/'results').rglob('evaluation_banks.json'):
            bank=read(path); inputs[str(path)]=sha(path)
            for entries in bank.values():
                for e in entries:
                    states.add(e['initial_state_hash']); parameters.add(e['task_parameter_hash']); seeds.add(int(e['seed']))
        for path in (directory/'results').rglob('training_reset_audit.csv'):
            inputs[str(path)]=sha(path)
            with path.open(encoding='utf-8-sig',newline='') as f:
                for e in csv.DictReader(f):
                    states.add(e['initial_state_hash'])
                    if e.get('task_parameter_hash'): parameters.add(e['task_parameter_hash'])
                    if e.get('seed'): seeds.add(int(e['seed']))
    path=out/'historical_forbidden.json'; write(path,{'states':sorted(states),'parameters':sorted(parameters),'seeds':sorted(seeds)})
    write(out/'historical_input_hashes.json',inputs)
    return reference(path)


def import_predecessor(old, out, jobs):
    """Reuse verified completed jobs, including a worker that finished after controller handoff."""
    old=Path(old).resolve(); oldplan=read(old/'plan.json',read(old/'plan_integrity.json')['sha256'])
    if oldplan['technical_smoke']: raise RuntimeError('A technical run cannot supply scientific parents')
    oldjobs={j['id']:j for j in oldplan['jobs']}; imported=[]
    for job in jobs:
        jid=job['id']; marker=old/'completed'/(jid+'.json'); attempt=None
        if marker.exists():
            prior=read(marker); read(prior['result_ref']['path'],prior['result_ref']['sha256']); attempt=Path(prior['attempt'])
        else:
            attempts=sorted((old/'jobs'/jid).glob('a*'))
            if attempts:
                candidate=attempts[-1]
                if (candidate/'process.json').exists():
                    process=read(candidate/'process.json')
                    if process['identity'] is not None and process_identity(process['pid'])==process['identity']:
                        raise RuntimeError('Predecessor worker is still running; wait for its boundary checkpoint')
                if (candidate/'result.json').exists(): attempt=candidate
        if attempt is None: continue
        if job!=oldjobs[jid]: raise RuntimeError('Cannot import changed job '+jid)
        if job['kind']=='evaluate': raise RuntimeError('This pre-outcome amendment requires no produced parent/branch outcomes')
        if read(attempt/'source_hashes.json')!=oldplan['source_hashes']: raise RuntimeError('Predecessor job source differs')
        if read(attempt/'costs.json')['status']!='completed': raise RuntimeError('Predecessor attempt is incomplete')
        q=read(attempt/'request.json')
        if any(q.get(k)!=v for k,v in job.items() if k!='parent' and k not in ('all_banks','other_banks')):
            raise RuntimeError('Predecessor request does not match job')
        finish_job(out,job,attempt)
        imported.append({'id':jid,'attempt':str(attempt),'result':reference(attempt/'result.json'),
                         'training_steps':job.get('steps',0),'source_snapshot':str(attempt/'source_snapshot')})
    if not imported: raise RuntimeError('No reusable predecessor jobs')
    write(out/'imported_jobs.json',imported)
    return imported


def prepare(technical,predecessor=None):
    verification=read(HERE/'VERIFIED.json'); verified=read(verification['path'],verification['sha256'])
    if verified['status']!='completed' or read(Path(verification['path']).parent/'source_hashes.json')!=source_hashes():
        raise RuntimeError('Implementation validation is absent or stale')
    if not technical:
        prior=Path(read(HERE/'ACTIVE_TECHNICAL.json')['campaign'])
        done=read(prior/'COMPLETE.json'); report=read(done['summary']['path'],done['summary']['sha256'])
        if not report['technical_smoke'] or read(prior/'plan.json')['source_hashes']!=source_hashes():
            raise RuntimeError('End-to-end technical campaign missing or stale')
        if shutil.disk_usage(HERE).free<30_000_000_000: raise RuntimeError('Less than 30 GB checkpoint reserve')
    out=HERE/'results'/unique('technical' if technical else 'stage1'); out.mkdir(parents=True,exist_ok=False)
    source_snapshot(out); forbidden=historical_exclusions(out)
    p=read(HERE/'configs/research_protocol.json')['stage1']
    parents=[44999] if technical else p['original_seeds']; repeats=[44901] if technical else p['continuation_labels']
    pretrain=4000 if technical else p['pretraining_steps']; checkpoints=[500,1000] if technical else p['branch_checkpoint_horizons']
    jobs=[]; banks={}
    def add(jid,kind,seed,**kw):
        if any(j['id']==jid for j in jobs): raise RuntimeError('Duplicate job')
        jobs.append({'id':jid,'kind':kind,'original_seed':seed,**kw}); return jid
    for seed in parents:
        jid=add(f'B_s{seed}_bank','bank',seed,bank_seed=424200+seed,other_banks=[ref(b,'bank') for b in banks.values()]); banks[seed]=jid
    all_banks=[ref(b,'bank') for b in banks.values()]
    for seed in parents:
        prefix=f'B_s{seed}'; jid=add(prefix+'_init','init',seed); current=ref(jid,'checkpoint'); previous=0
        for end in ([4000] if technical else range(20000,pretrain+1,20000)):
            jid=add(prefix+'_pretrain_'+str(end),'train',seed,parent=current,start_step=previous,steps=end-previous,all_banks=all_banks)
            current=ref(jid,'checkpoint'); previous=end
        parent=current
        add(prefix+'_parent_O','evaluate',seed,parent=parent,bank=ref(banks[seed],'bank'),role='parent')
        for rep in repeats:
            stream=derived_seed(rep,420,seed)
            for condition in p['conditions']:
                current=parent; previous=0; tag=f'{prefix}_r{rep}_{condition}'
                for end in checkpoints:
                    jid=add(tag+'_t'+str(end),'train',seed,parent=current,parent_step=pretrain,start_step=pretrain+previous,
                        steps=end-previous,horizon=end,condition=condition,continuation=rep,continuation_rng_seed=stream,
                        start_branch=previous==0,all_banks=all_banks)
                    current=ref(jid,'checkpoint'); previous=end
                add(tag+'_O','evaluate',seed,parent=current,bank=ref(banks[seed],'bank'),role='branch',condition=condition,continuation=rep,horizon=previous)
    if not technical:
        assert sum(j.get('steps',0) for j in jobs)==2_200_000
        assert sum(j['kind']=='evaluate' for j in jobs)==35
        assert sum(j.get('role')=='branch' for j in jobs)==30
    (out/'completed').mkdir()
    imported=import_predecessor(predecessor,out,jobs) if predecessor and not technical else []
    inherited=sum(j['training_steps'] for j in imported)
    plan={'created_at':now(),'technical_smoke':technical,'jobs':jobs,'source_hashes':source_hashes(),
          'historical_forbidden':forbidden,'verification':verification,'maximum_attempts':3,
          'planned_training_steps':sum(j.get('steps',0) for j in jobs),'inherited_training_steps':inherited,
          'remaining_new_training_steps':sum(j.get('steps',0) for j in jobs)-inherited,
          'predecessor_campaign':str(Path(predecessor).resolve()) if predecessor else None,
          'imported_job_count':len(imported),'scientific_effect_never_stops_within_stage':True,
          'stage2_auto_training':False,'stage2_requires':'scientific gate, frozen intervention specification and technical validation'}
    write(out/'plan.json',plan); write(out/'plan_integrity.json',{'sha256':sha(out/'plan.json')})
    atomic(HERE/('ACTIVE_TECHNICAL.json' if technical else 'ACTIVE_CAMPAIGN.json'),{'campaign':str(out),'created_at':now()})
    print(str(out),flush=True)


def resolve(value,cam):
    if isinstance(value,dict) and 'from_job' in value:
        marker=read(cam/'completed'/(value['from_job']+'.json')); result=read(marker['result_ref']['path'],marker['result_ref']['sha256'])
        return result[value['key']]
    if isinstance(value,dict): return {k:resolve(v,cam) for k,v in value.items()}
    if isinstance(value,list): return [resolve(v,cam) for v in value]
    return value


def process_identity(pid):
    from ctypes import wintypes
    k=ctypes.windll.kernel32; k.OpenProcess.restype=wintypes.HANDLE
    k.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    k.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
    k.GetProcessTimes.argtypes=[wintypes.HANDLE,*[ctypes.POINTER(wintypes.FILETIME)]*4]; k.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=k.OpenProcess(0x1000|0x100000,False,int(pid))
    if not handle: return None
    try:
        code=wintypes.DWORD()
        if not k.GetExitCodeProcess(handle,ctypes.byref(code)) or code.value!=259: return None
        times=[wintypes.FILETIME() for _ in range(4)]
        if not k.GetProcessTimes(handle,*[ctypes.byref(t) for t in times]): return None
        return (times[0].dwHighDateTime<<32)+times[0].dwLowDateTime
    finally: k.CloseHandle(handle)


def finish_job(cam,job,attempt):
    result=read(attempt/'result.json')
    if result['id']!=job['id']: raise RuntimeError('Result identity mismatch')
    if result.get('checkpoint'):
        checkpoint=result['checkpoint']; directory=Path(checkpoint['path'])
        manifest=read(directory/'checkpoint_manifest.json',checkpoint['manifest_sha256'])
        for name,digest in manifest['files'].items():
            if sha(directory/name)!=digest: raise RuntimeError('Checkpoint file changed')
    if result.get('episodes_path') and sha(result['episodes_path'])!=result['episodes_sha256']: raise RuntimeError('Episode rows changed')
    target=cam/'completed'/(job['id']+'.json'); tmp=target.with_suffix('.'+uuid.uuid4().hex[:8]+'.tmp')
    write(tmp,{'result_ref':reference(attempt/'result.json'),'attempt':str(attempt),'completed_at':now()}); os.rename(tmp,target)


def run(cam):
    import msvcrt
    cam=Path(cam).resolve(); lock=(cam/'controller.lock').open('a+b')
    if lock.tell()==0: lock.write(b'0'); lock.flush()
    lock.seek(0)
    try: msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError: return 0
    if (cam/'COMPLETE.json').exists(): return 0
    if (cam/'STOPPED.json').exists(): return 1
    plan=read(cam/'plan.json',read(cam/'plan_integrity.json')['sha256'])
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    try:
        for job in plan['jobs']:
            marker=cam/'completed'/(job['id']+'.json')
            if marker.exists():
                saved=read(marker)['result_ref']; read(saved['path'],saved['sha256']); continue
            if (cam/'HANDOFF_REQUEST.json').exists():
                atomic(cam/'STATUS.json',{'state':'boundary_handoff_requested','next_job':job['id'],'updated_at':now()})
                return 0
            if source_hashes()!=plan['source_hashes']: raise RuntimeError('Frozen implementation changed')
            jobroot=cam/'jobs'/job['id']; jobroot.mkdir(parents=True,exist_ok=True); attempts=sorted(jobroot.glob('a*'))
            if attempts:
                previous=attempts[-1]
                if (previous/'process.json').exists():
                    process=read(previous/'process.json')
                    while process['identity'] is not None and process_identity(process['pid'])==process['identity']:
                        atomic(cam/'STATUS.json',{'state':'running','job':job['id'],'adopted':True,'worker_pid':process['pid'],'updated_at':now()}); time.sleep(5)
                if (previous/'result.json').exists(): finish_job(cam,job,previous); continue
                if (previous/'error.json').exists() and not read(previous/'error.json')['retryable']: raise RuntimeError('Previous nonretryable failure')
            while len(attempts)<plan['maximum_attempts']:
                attempt=jobroot/(f'a{len(attempts)+1:02d}_'+uuid.uuid4().hex[:8]); attempt.mkdir(); attempts.append(attempt)
                q=resolve(job,cam); q.update(output=str(attempt),technical_smoke=plan['technical_smoke'],source_hashes=plan['source_hashes'],
                    historical_forbidden=plan['historical_forbidden'],worker_lock=str(cam/'worker.lock'))
                write(attempt/'request.json',q)
                cmd=[str(PYTHON),'-u','-B',str(HERE/'worker.py'),'--request',str(attempt/'request.json')]
                with (attempt/'stdout.log').open('x',encoding='utf-8') as stdout,(attempt/'stderr.log').open('x',encoding='utf-8') as stderr:
                    child=subprocess.Popen(cmd,cwd=REPO,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
                    write(attempt/'process.json',{'pid':child.pid,'identity':process_identity(child.pid),'started_at':now(),'command':cmd})
                    while child.poll() is None:
                        atomic(cam/'STATUS.json',{'state':'running','job':job['id'],'worker_pid':child.pid,'attempt':str(attempt),
                               'jobs_completed':len(list((cam/'completed').glob('*.json'))),'jobs_total':len(plan['jobs']),'updated_at':now()})
                        time.sleep(5)
                    code=child.returncode
                write(attempt/'exit.json',{'returncode':code,'ended_at':now()})
                if code==0: finish_job(cam,job,attempt); break
                error=read(attempt/'error.json') if (attempt/'error.json').exists() else {'retryable':False}
                if not error['retryable']: raise RuntimeError('Nonretryable technical failure '+job['id'])
            else: raise RuntimeError('Recovery attempts exhausted '+job['id'])
        analysis=None
        if not plan['technical_smoke']:
            output=cam/unique('analysis')
            with (cam/(output.name+'_stdout.log')).open('x',encoding='utf-8') as stdout,(cam/(output.name+'_stderr.log')).open('x',encoding='utf-8') as stderr:
                code=subprocess.call([str(PYTHON),'-B',str(HERE/'analyze.py'),'--campaign',str(cam),'--output',str(output)],cwd=REPO,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
            if code: raise RuntimeError('Scientific analysis failed; all training retained')
            analysis=reference(output/'summary.json')
        costs=[]
        attempts=list((cam/'jobs').glob('*/a*'))
        if plan.get('predecessor_campaign'):
            attempts+=list((Path(plan['predecessor_campaign'])/'jobs').glob('*/a*'))
        for attempt in sorted(set(attempts)):
            if (attempt/'costs.json').exists(): costs.append({'attempt':str(attempt),**read(attempt/'costs.json'),'exact':True})
            else:
                progress=attempt/'progress.jsonl'; rows=progress.read_text(encoding='utf-8').splitlines() if progress.exists() else []
                last=json.loads(rows[-1]) if rows else {'costs':{'environment_steps':0,'train_iterations':0}}
                costs.append({'attempt':str(attempt),'costs':last['costs'],'exact':False,'status':'interrupted_lower_bound'})
        summary={'execution_status':'completed','technical_smoke':plan['technical_smoke'],'jobs_completed':len(plan['jobs']),
            'actual_environment_steps_recorded':sum(r['costs']['environment_steps'] for r in costs),
            'actual_update_iterations_recorded':sum(r['costs']['train_iterations'] for r in costs),
            'costs_exact':all(r['exact'] for r in costs),'costs':costs,'analysis':analysis,
            'next_stage':'Read scientific gate, freeze stage2 intervention and validate before new training'}
        target=cam/unique('completion'); write(target.with_suffix('.json'),summary)
        write(cam/'COMPLETE.json',{'summary':reference(target.with_suffix('.json')),'completed_at':now()})
        atomic(cam/'STATUS.json',{'state':'completed','jobs_completed':len(plan['jobs']),'jobs_total':len(plan['jobs']),'analysis':analysis,'updated_at':now()})
        return 0
    except BaseException as exc:
        failure={'state':'stopped_technical_failure','time':now(),'reason':str(exc),'traceback':traceback.format_exc()}
        if not (cam/'STOPPED.json').exists(): write(cam/'STOPPED.json',failure)
        atomic(cam/'STATUS.json',failure); traceback.print_exc(); return 1
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000); lock.close()


def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare'); p.add_argument('--technical',action='store_true'); p.add_argument('--predecessor')
    r=sub.add_parser('run'); r.add_argument('--campaign',required=True)
    s=sub.add_parser('status'); s.add_argument('--campaign')
    args=ap.parse_args()
    if args.command=='prepare': prepare(args.technical,args.predecessor); return 0
    if args.command=='run': return run(args.campaign)
    cam=Path(args.campaign) if args.campaign else Path(read(HERE/'ACTIVE_CAMPAIGN.json')['campaign'])
    print(json.dumps(read(cam/'STATUS.json') if (cam/'STATUS.json').exists() else {'state':'prepared','campaign':str(cam)},indent=2)); return 0


if __name__=='__main__': raise SystemExit(main())
