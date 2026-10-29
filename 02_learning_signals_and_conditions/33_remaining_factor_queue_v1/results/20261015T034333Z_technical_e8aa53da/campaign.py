"""Frozen sequential queue for remaining candidate checks, with unique attempts."""
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
from datetime import datetime,timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parent
STAGES={'F05':REPO/'31_fixed_horizon_alignment_v1','F08':REPO/'32_dose_order_intervention_v1'}
PYTHON=REPO/'13_e0_e3_autonomous_queue_v1/.venv/Scripts/python.exe'
OFFLINE={'measurement':REPO/'30_exposure_experience_screening_v1/results/20261015T031302Z_measure_7e872da9',
         'analysis':REPO/'30_exposure_experience_screening_v1/results/20261015T031819Z_analysis_56a74006',
         'verification':REPO/'30_exposure_experience_screening_v1/results/20261015T032001Z_verify_85b6bf5c'}


def now():return datetime.now(timezone.utc).isoformat()
def stamp():return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(path,expected=None):
    if expected is not None and sha(path)!=expected:raise RuntimeError('Integrity: file hash '+str(path))
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8',newline='\n') as f:json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n')
def atomic(path,value):
    path=Path(path);temp=path.with_name(path.name+'.'+uuid.uuid4().hex[:8]+'.tmp');write(temp,value);os.replace(temp,path)
def reference(path):return {'path':str(Path(path).resolve()),'sha256':sha(path)}
def stage_hashes(directory):
    files=list(directory.glob('*.py'))+list(directory.glob('*.ps1'))+[directory/'requirements.txt',directory/'VERSION.json',directory/'protocol.json']
    for sub,pat in [('practice_allocation','*.py'),('configs','*.json'),('tests','*.py')]:files+=list((directory/sub).rglob(pat))
    return {p.relative_to(directory).as_posix():sha(p) for p in sorted(set(files)) if p.is_file()}
def ref(job,key):return {'from_job':job,'key':key}


def historical_exclusions(out):
    active=read(REPO/'13_e0_e3_autonomous_queue_v1/ACTIVE_CAMPAIGN.json');old=Path(active['campaign'])
    plan=read(old/'plan.json',read(old/'plan_integrity.json')['sha256']);banks={};audits={};hashes={};states=set();parameters=set();seeds=set()
    for job in plan['jobs']:
        marker=read(old/'completed'/(job['id']+'.json'));r=read(marker['result_ref']['path'],marker['result_ref']['sha256'])
        if r.get('bank'):banks[r['bank']['path']]=r['bank']
        if r.get('training_reset_audit'):audits[r['training_reset_audit']]=None
        if job['id']=='E3_C_s12_c200_base':
            request=read(Path(marker['result_ref']['path']).parent/'request.json')
            for b in request['all_banks']:banks[b['path']]=b
    for b in banks.values():
        data=read(b['path'],b['sha256']);hashes[b['path']]=b['sha256']
        for entries in data.values():
            for e in entries:states.add(e['initial_state_hash']);parameters.add(e['task_parameter_hash']);seeds.add(int(e['seed']))
    for version in ['02_p0_uniform_pretraining_v1','04_p0_allocation_branches_v1','06_p0_branch_replication_v1']:
        for pattern in ['**/train_episodes.csv','**/training_reset_audit.csv','**/initial_state_audit.csv']:
            for path in (REPO/version/'results').glob(pattern):audits[str(path)]=None
    for name in audits:
        path=Path(name)
        if not path.exists():raise RuntimeError('Missing historical training audit '+name)
        hashes[str(path)]=sha(path)
        with path.open(encoding='utf-8-sig',newline='') as f:
            for e in csv.DictReader(f):
                if e.get('initial_state_hash'):states.add(e['initial_state_hash'])
                if e.get('task_parameter_hash'):parameters.add(e['task_parameter_hash'])
                if e.get('seed'):seeds.add(int(e['seed']))
    path=out/'historical_forbidden.json';write(path,{'states':sorted(states),'parameters':sorted(parameters),'seeds':sorted(seeds)})
    write(out/'historical_source_hashes.json',hashes)
    return path,list(banks.values())


def validate_readiness():
    records=[]
    for stage,suites,critical in [('F05',['A','B','C'],['core.py','environment.py','learning.py','engine.py']),('F08',[None],['core.py','environment.py','learning.py','engine.py','schedules.py'])]:
        directory=STAGES[stage]
        for suite in suites:
            matches=[]
            for path in sorted((directory/'results').glob('*verify_implementation*/summary.json')):
                r=read(path)
                if r['status']=='completed' and (suite is None or r.get('suite')==suite):matches.append(path)
            if not matches:raise RuntimeError('No successful real-model preflight '+stage+str(suite))
            path=matches[-1];hashes=read(path.parent/'source_hashes.json')
            for name in critical:
                key='practice_allocation/'+name
                if hashes[key]!=sha(directory/key):raise RuntimeError('Critical implementation changed since preflight '+key)
            if stage=='F05' and hashes['diagnostics.py']!=sha(directory/'diagnostics.py'):raise RuntimeError('Diagnostics changed since preflight')
            records.append(reference(path))
    for name,path in OFFLINE.items():
        summary=read(path/'summary.json')
        if summary['status']!='completed':raise RuntimeError('Offline stage incomplete '+name)
        records.append(reference(path/'summary.json'))
    return records


def prepare(technical=False):
    readiness=validate_readiness()
    if not technical:
        prior=Path(read(HERE/'ACTIVE_TECHNICAL.json')['campaign'])
        receipt=read(prior/'COMPLETE.json');smoke=read(receipt['summary']['path'],receipt['summary']['sha256'])
        if smoke['status']!='completed' or not smoke['technical_smoke']:raise RuntimeError('End-to-end queue preflight not complete')
        if read(prior/'plan.json')['stage_hashes']!={k:stage_hashes(v) for k,v in STAGES.items()}:raise RuntimeError('Stage code changed since queue preflight')
        readiness.append(reference(prior/'COMPLETE.json'))
        math=read(HERE/'ANALYSIS_PREFLIGHT.json');checked=read(math['path'],math['sha256'])
        if checked['status']!='completed':raise RuntimeError('Analysis formula preflight not complete')
        for path,digest in checked['source_hashes'].items():
            if sha(REPO/path)!=digest:raise RuntimeError('Analysis source changed since preflight '+path)
        readiness.append(math)
    out=HERE/'results'/(stamp()+('_technical_' if technical else '_remaining_')+uuid.uuid4().hex[:8]);out.mkdir(parents=True)
    for path in HERE.glob('*.py'):shutil.copy2(path,out/path.name)
    write(out/'readiness.json',readiness)
    forbidden,oldbanks=historical_exclusions(out)
    manifest_path=REPO/'29_neural_plasticity_screening_v1/results/20261014T100947Z_measure_e6af8a96/snapshot_manifest.json'
    with (REPO/'29_neural_plasticity_screening_v1/results/20261014T102305Z_verify_delivery_16407d21/artifact_manifest.csv').open(encoding='utf-8-sig',newline='') as f:
        inventory={str((REPO/'29_neural_plasticity_screening_v1'/r['path']).resolve()):r['sha256'] for r in csv.DictReader(f)}
    manifest=read(manifest_path,inventory[str(manifest_path.resolve())])
    selected=[r for r in manifest if r['suite']=='A' and r['original_seed']==12 and r['checkpoint_step']==200000 and r['horizon']==0] if technical else manifest
    suites=['A'] if technical else ['A','B','C'];jobs=[]
    def add(jid,stage,**kw):
        if any(j['id']==jid for j in jobs):raise RuntimeError('Duplicate job')
        jobs.append({'id':jid,'stage':stage,**kw});return jid
    banks05={};banks08={}
    for s in suites:banks05[s]=add('F05_'+s+'_bank','F05',suite=s,original_seed=12,kind='bank',bank_seed=315000+ord(s)+(900 if technical else 0))
    for s in suites:banks08[s]=add('F08_'+s+'_bank','F08',suite=s,original_seed=12,kind='bank',bank_seed=328000+ord(s)+(900 if technical else 0),other_banks=[ref(b,'bank') for b in banks05.values()]+[ref(b,'bank') for b in banks08.values()])
    for e in selected:
        add('F05_'+e['id'],'F05',suite=e['suite'],original_seed=e['original_seed'],kind='measure',original_id=e['id'],parent=e['checkpoint'],bank=ref(banks05[e['suite']],'bank'))
    if not technical:
        a=add('F05_analysis','F05',kind='analysis');add('F05_verification','F05',kind='verify_analysis',analysis=ref(a,'result_ref'))
    for s in suites:
        parent=next(e['checkpoint'] for e in manifest if e['suite']==s and e['original_seed']==12 and e['checkpoint_step']==200000 and e['horizon']==0)
        for kind in (['outcome'] if technical else ['diagnostic','outcome']):add('F08_'+s+'_base_'+kind,'F08',suite=s,original_seed=12,kind='evaluate',parent=parent,bank=ref(banks08[s],'bank'),bank_kind=kind)
        import numpy as np
        for continuation in ([3801] if technical else [3801,3802,3803]):
            stream=int(np.random.SeedSequence([continuation,803,ord(s),12,200000]).generate_state(1)[0])
            for condition in (['dose4375'] if technical else read(STAGES['F08']/'protocol.json')['conditions']):
                prefix=f'F08_{s}_r{continuation}_{condition}';current=parent;previous=0
                for horizon in ([500,1000] if technical else [20000,40000]):
                    jid=add(prefix+'_t'+str(horizon),'F08',suite=s,original_seed=12,kind='train',condition=condition,continuation=continuation,
                            continuation_rng_seed=stream,parent=current,start_branch=previous==0,start_step=200000+previous,steps=horizon-previous,horizon=horizon,
                            all_banks=oldbanks+[ref(b,'bank') for b in list(banks05.values())+list(banks08.values())])
                    current=ref(jid,'checkpoint');previous=horizon
                add(prefix+'_outcome','F08',suite=s,original_seed=12,kind='evaluate',condition=condition,continuation=continuation,horizon=previous,parent=current,bank=ref(banks08[s],'bank'),bank_kind='outcome')
    if not technical:
        a=add('F08_analysis','F08',kind='analysis');add('F08_verification','F08',kind='verify_analysis',analysis=ref(a,'result_ref'))
    versions={k:stage_hashes(v) for k,v in STAGES.items()}
    for stage,files in versions.items():
        for name,digest in files.items():
            dest=out/'stage_sources'/stage/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(STAGES[stage]/name,dest)
            if sha(dest)!=digest:raise RuntimeError('Source snapshot mismatch')
    plan={'created_at':now(),'technical_smoke':technical,'jobs':jobs,'stage_hashes':versions,'controller_sha256':sha(Path(__file__)),
          'historical_forbidden':str(forbidden),'historical_forbidden_sha256':sha(forbidden),'offline':{k:reference(v/'summary.json') for k,v in OFFLINE.items()},
          'planned_training_steps':sum(j.get('steps',0) for j in jobs),'planned_F05_environment_steps':6000 if technical else 10752000,
          'maximum_attempts':3,'integrity_failure_stops':True,'scientific_effect_never_stops':True}
    write(out/'plan.json',plan);write(out/'plan_integrity.json',{'sha256':sha(out/'plan.json')});(out/'completed').mkdir()
    atomic(HERE/('ACTIVE_TECHNICAL.json' if technical else 'ACTIVE_CAMPAIGN.json'),{'campaign':str(out),'created_at':now()})
    print(str(out),flush=True);return out


def resolve(value,cam):
    if isinstance(value,dict) and 'from_job' in value:
        marker=read(cam/'completed'/(value['from_job']+'.json'));result=read(marker['result_ref']['path'],marker['result_ref']['sha256'])
        return marker['result_ref'] if value['key']=='result_ref' else result[value['key']]
    if isinstance(value,dict):return {k:resolve(v,cam) for k,v in value.items()}
    if isinstance(value,list):return [resolve(v,cam) for v in value]
    return value


def process_identity(pid):
    from ctypes import wintypes
    k=ctypes.windll.kernel32;k.OpenProcess.restype=wintypes.HANDLE
    k.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    k.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
    k.GetProcessTimes.argtypes=[wintypes.HANDLE,*[ctypes.POINTER(wintypes.FILETIME)]*4]
    k.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=k.OpenProcess(0x1000|0x100000,False,int(pid))
    if not handle:return None
    try:
        code=wintypes.DWORD()
        if not k.GetExitCodeProcess(handle,ctypes.byref(code)) or code.value!=259:return None
        times=[wintypes.FILETIME() for _ in range(4)]
        if not k.GetProcessTimes(handle,*[ctypes.byref(t) for t in times]):return None
        return (times[0].dwHighDateTime<<32)+times[0].dwLowDateTime
    finally:k.CloseHandle(handle)


def append_event(cam,event,**fields):
    with (cam/'events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps({'time':now(),'event':event,**fields},ensure_ascii=False)+'\n')


def finish_job(cam,plan,job,attempt):
    if job['kind'] in ['analysis','verify_analysis']:
        lines=(attempt/'stdout.log').read_text(encoding='utf-8-sig',errors='replace').splitlines();output=Path(lines[0].strip()) if lines else attempt/'missing'
        result_path=output/'summary.json';r=read(result_path)
        if r.get('status')!='completed':raise RuntimeError('Analysis/verification did not complete '+job['id'])
    else:
        result_path=attempt/'result.json';r=read(result_path)
        if r['id']!=job['id']:raise RuntimeError('Result job mismatch')
        if job['kind']=='measure':
            receipt=attempt/'trace_verified.json'
            if receipt.exists():
                vr=read(receipt);verified=read(vr['path'],vr['sha256'])
                if verified['status']!='completed':raise RuntimeError('Invalid trace verification receipt')
            else:
                label='trace_verification_'+uuid.uuid4().hex[:8]
                with (attempt/(label+'_stdout.log')).open('x',encoding='utf-8') as out, (attempt/(label+'_stderr.log')).open('x',encoding='utf-8') as err:
                    code=subprocess.call([str(PYTHON),'-B',str(STAGES['F05']/'verify_traces.py'),str(result_path)],cwd=REPO,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
                if code:raise RuntimeError('Integrity: diagnostic trace verification failed '+job['id'])
                target=Path((attempt/(label+'_stdout.log')).read_text(encoding='utf-8').splitlines()[0])/'summary.json'
                write(receipt,reference(target))
        if job['kind']=='bank':
            banks=[]
            for done in (cam/'completed').glob('*.json'):
                mr=read(done);existing=read(mr['result_ref']['path'],mr['result_ref']['sha256'])
                if existing.get('bank'):banks.append(existing['bank'])
            states=set();parameters=set();seeds=set()
            for b in banks+[r['bank']]:
                bank=read(b['path'],b['sha256'])
                for rows in bank.values():
                    for entry in rows:
                        if entry['initial_state_hash'] in states or entry['task_parameter_hash'] in parameters or entry['seed'] in seeds:raise RuntimeError('Integrity: new banks overlap')
                        states.add(entry['initial_state_hash']);parameters.add(entry['task_parameter_hash']);seeds.add(entry['seed'])
    target=cam/'completed'/(job['id']+'.json')
    if target.exists():raise RuntimeError('Completed job marker already exists')
    temporary=target.with_name(target.name+'.'+uuid.uuid4().hex[:8]+'.tmp')
    write(temporary,{'job':job['id'],'result_ref':reference(result_path),'attempt':str(attempt),'completed_at':now()});os.rename(temporary,target)
    append_event(cam,'job_completed',job=job['id'],result=str(result_path))


def final_report(cam,plan):
    cost_rows=[]
    for directory in STAGES.values():
        for path in (directory/'results'/cam.name).glob('**/costs.json'):
            value=read(path);cost_rows.append({'path':str(path),**value})
    steps=sum(r['costs']['environment_steps'] for r in cost_rows);updates=sum(r['costs']['train_iterations'] for r in cost_rows)
    record={'status':'completed','technical_smoke':plan['technical_smoke'],'jobs_completed':len(plan['jobs']),
            'actual_environment_steps_including_failed_attempts':steps,'actual_train_iterations_including_failed_attempts':updates,
            'worker_wall_seconds_sum':sum(r['wall_seconds'] for r in cost_rows),
            'worker_cpu_seconds_sum':sum(r['cpu_seconds'] for r in cost_rows),'costs':cost_rows,
            'note':'Technical preflights and analysis CPU costs retained in their separate run summaries; no GPU busy-time measurement.'}
    if plan['technical_smoke']:
        report='# 자동 실행기 기술 검증\n\n새 bank 생성, 500-step 진단, 두 학습 구간, checkpoint 복구와 평가를 실제 실행했다. 과학적 효과의 근거로 사용하지 않는다.\n'
    else:
        offline=read(plan['offline']['analysis']['path'],plan['offline']['analysis']['sha256'])
        r05=read(cam/'completed/F05_analysis.json');s05=read(r05['result_ref']['path'],r05['result_ref']['sha256'])
        r08=read(cam/'completed/F08_analysis.json');s08=read(r08['result_ref']['path'],r08['result_ref']['sha256'])
        report='# 미실행 후보 검증 완료 기록\n\n계획한 진단과 72개 통제 학습 분기를 모두 완료하고 각 단계 계산 검산을 통과했다.\n\n'
        for factor,d in offline['candidate_decisions'].items():report+=f"- {factor}: {d['comparator']} 대비 추가 선택 이득 {d['increment_pp']:+.3f}%p, 선별 통과 {d['operational_screen_pass']}.\n"
        report+=f"- F05 정합성: 주 추가 선택 이득 {s05['primary']['vs_base_pp']:+.3f}%p, 선별 통과 {s05['operational_screen_pass']}.\n"
        report+='- F08: 세 구성 각각 원래 seed12 한 개, 후속 반복3개의 강도·순서 대조를 완료했다. 개별 대조는 아래 상세 결과를 따른다.\n\n'
        report+=f"실행 worker의 실제 환경 비용은 실패 시도 포함 {steps:,} step, SAC iteration은 {updates:,}회다. 초기 기술 검사와 분석 비용은 별도 summary에 보존했다. 비용 포함 적응형 배분 G4는 실행하지 않았다.\n\n"
        report+=f"[F05 분석]({Path(r05['result_ref']['path']).parent.as_posix()}/report_ko.md) · [F08 분석]({Path(r08['result_ref']['path']).parent.as_posix()}/report_ko.md)\n"
        report+='\nF01/F04/F06/F07의 이전 판정은 v29 근거 기록을 유지한다. F02 sampling 인과 개입, 새 원래 seed의 독립 확인, 다른 benchmark 및 동일 총예산 실제 배분은 미실행이다.\n'
    report_path=cam/'report_ko.md'
    if report_path.exists():
        if report_path.read_text(encoding='utf-8')!=report:raise RuntimeError('Final report changed during recovery')
    else:
        with report_path.open('x',encoding='utf-8') as f:f.write(report)
    if (cam/'summary.json').exists():
        if read(cam/'summary.json')!=record:raise RuntimeError('Final summary changed during recovery')
    else:write(cam/'summary.json',record)
    atomic(cam/'STATUS.json',{'state':'completed','completed_at':now(),'jobs_completed':len(plan['jobs']),'jobs_total':len(plan['jobs']),'report':str(cam/'report_ko.md')})
    write(cam/'COMPLETE.json',{'summary':reference(cam/'summary.json'),'report':reference(report_path),'completed_at':now()})


def run_campaign(cam):
    import msvcrt
    cam=Path(cam).resolve();lock=(cam/'controller.lock').open('a+b')
    if lock.tell()==0:lock.write(b'0');lock.flush()
    lock.seek(0)
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:return 0
    plan=read(cam/'plan.json',read(cam/'plan_integrity.json')['sha256'])
    if (cam/'COMPLETE.json').exists():return 0
    if (cam/'STOPPED.json').exists():return 1
    # Prevent automatic sleep for this controller lifetime without changing power plans.
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    try:
        if sha(Path(__file__))!=plan['controller_sha256']:raise RuntimeError('Integrity: controller changed')
        for job in plan['jobs']:
            if (cam/'completed'/(job['id']+'.json')).exists():continue
            directory=STAGES[job['stage']]
            if stage_hashes(directory)!=plan['stage_hashes'][job['stage']]:raise RuntimeError('Integrity: stage source changed')
            jobroot=directory/'results'/cam.name/job['id'];jobroot.mkdir(parents=True,exist_ok=True)
            attempts=sorted(jobroot.glob('a*'))
            # Adopt an orphan from a previous controller, then preserve its result/error.
            if attempts and (attempts[-1]/'process.json').exists():
                old=read(attempts[-1]/'process.json');identity=old.get('identity')
                while identity is not None and process_identity(old['pid'])==identity:
                    atomic(cam/'STATUS.json',{'state':'running','job':job['id'],'worker_pid':old['pid'],'adopted':True,'jobs_completed':len(list((cam/'completed').glob('*.json'))),'jobs_total':len(plan['jobs']),'updated_at':now()});time.sleep(5)
                if (attempts[-1]/'result.json').exists() or (job['kind'] in ['analysis','verify_analysis'] and (attempts[-1]/'exit.json').exists() and read(attempts[-1]/'exit.json')['returncode']==0):
                    finish_job(cam,plan,job,attempts[-1]);continue
                if (attempts[-1]/'error.json').exists() and not read(attempts[-1]/'error.json').get('retryable',False):raise RuntimeError('Previous nonretryable failure '+job['id'])
            while len(attempts)<plan['maximum_attempts']:
                attempt=jobroot/(f'a{len(attempts)+1:02d}_'+uuid.uuid4().hex[:8]);attempt.mkdir();attempts.append(attempt)
                q=resolve(job,cam);q.update(output=str(attempt),technical_smoke=plan['technical_smoke'],source_hashes=plan['stage_hashes'][job['stage']],
                    historical_forbidden=plan['historical_forbidden'],historical_forbidden_sha256=plan['historical_forbidden_sha256'],worker_lock=str(cam/'worker.lock'))
                write(attempt/'request.json',q)
                if job['kind']=='analysis':cmd=[str(PYTHON),'-B',str(directory/'analyze.py'),'--measurement' if job['stage']=='F05' else '--campaign',str(cam)]
                elif job['kind']=='verify_analysis':cmd=[str(PYTHON),'-B',str(directory/'verify_analysis.py'),'--campaign',str(cam),'--analysis',str(Path(q['analysis']['path']).parent)]
                else:cmd=[str(PYTHON),'-u','-B',str(directory/'worker.py'),'--request',str(attempt/'request.json')]
                with (attempt/'stdout.log').open('x',encoding='utf-8') as stdout,(attempt/'stderr.log').open('x',encoding='utf-8') as stderr:
                    child=subprocess.Popen(cmd,cwd=REPO,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
                    write(attempt/'process.json',{'pid':child.pid,'identity':process_identity(child.pid),'started_at':now(),'command':cmd})
                    append_event(cam,'job_started',job=job['id'],pid=child.pid,attempt=str(attempt))
                    while child.poll() is None:
                        atomic(cam/'STATUS.json',{'state':'running','job':job['id'],'worker_pid':child.pid,'attempt':str(attempt),'jobs_completed':len(list((cam/'completed').glob('*.json'))),'jobs_total':len(plan['jobs']),'updated_at':now()});time.sleep(5)
                    code=child.returncode
                write(attempt/'exit.json',{'returncode':code,'ended_at':now()})
                if code==0:finish_job(cam,plan,job,attempt);break
                error=read(attempt/'error.json') if (attempt/'error.json').exists() else {'retryable':False}
                if not error.get('retryable',False):raise RuntimeError('Nonretryable technical failure '+job['id'])
                append_event(cam,'retryable_failure',job=job['id'],attempt=str(attempt))
            else:raise RuntimeError('Recovery attempts exhausted '+job['id'])
        final_report(cam,plan);return 0
    except BaseException as exc:
        failure={'state':'stopped_technical_failure','time':now(),'reason':str(exc),'traceback':traceback.format_exc()}
        write(cam/'STOPPED.json',failure);atomic(cam/'STATUS.json',failure);traceback.print_exc();return 1
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000);lock.close()


def main():
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest='command',required=True)
    pp=sub.add_parser('prepare');pp.add_argument('--technical',action='store_true')
    rr=sub.add_parser('run');rr.add_argument('--campaign',required=True)
    ss=sub.add_parser('status');ss.add_argument('--campaign')
    args=ap.parse_args()
    if args.command=='prepare':prepare(args.technical);return 0
    if args.command=='run':return run_campaign(args.campaign)
    cam=Path(args.campaign) if args.campaign else Path(read(HERE/'ACTIVE_CAMPAIGN.json')['campaign'])
    print(json.dumps(read(cam/'STATUS.json') if (cam/'STATUS.json').exists() else {'state':'prepared','campaign':str(cam)},indent=2,ensure_ascii=False));return 0


if __name__=='__main__':raise SystemExit(main())
