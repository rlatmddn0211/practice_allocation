"""Native, standard-library-only, single-dispatch continuation queue.

Waiting never imports an RL package or creates an environment. The immutable
64 campaign must finish its complete analysis and independent verification.
No predecessor source or state file is written by this module.
"""
from __future__ import annotations
import argparse
import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
POLL_SECONDS = 30
MAX_WAIT_SECONDS = 24 * 60 * 60

class Pending(RuntimeError): pass
class Rejected(RuntimeError): pass
class Cancelled(RuntimeError): pass

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def utc():return datetime.now(timezone.utc).isoformat()
def require(ok,message):
    if not ok:raise Rejected(message)
def load(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def exclusive_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
def atomic_json(path,value):
    path=Path(path);tmp=path.with_name(path.name+'.'+uuid.uuid4().hex[:8]+'.tmp')
    exclusive_json(tmp,value);os.replace(tmp,path)
def within(path,parent):
    try:Path(path).resolve().relative_to(Path(parent).resolve());return True
    except ValueError:return False

def source_files(root):
    root=Path(root)
    files=list(root.glob('*.py'))+list(root.glob('*.ps1'))+list(root.glob('*.md'))
    files += [root/name for name in ('requirements.txt','VERSION.json','protocol.json')]
    for folder,pattern in (('practice_allocation','*.py'),('configs','*.json'),('tests','*.py')):
        files+=list((root/folder).rglob(pattern))
    files+=list((root/'inputs').glob('*.json'))+list((root/'inputs').glob('*.csv'))
    return sorted(set(p for p in files if p.is_file()))
def source_hashes(root):
    root=Path(root);return {p.relative_to(root).as_posix():sha(p) for p in source_files(root)}
def check_source_pin(root,pin):require(source_hashes(root)==pin,'Deferred source/input/protocol changed after arming')

class Receipt:
    def __init__(self):self.files={}
    def read(self,path,expected=None):
        path=Path(path).resolve();h=sha(path)
        require(expected is None or h==expected,'Artifact SHA-256 mismatch: '+str(path))
        old=self.files.get(str(path));require(old is None or old==h,'Artifact changed during gate: '+str(path))
        self.files[str(path)]=h;return load(path)
    def ref(self,ref,parent=None):
        path=Path(ref['path']).resolve()
        if parent is not None:require(within(path,parent),'Artifact escaped pinned directory: '+str(path))
        return self.read(path,ref['sha256'])
    def binary(self,path,expected):
        path=Path(path).resolve();h=sha(path)
        require(h==expected,'Checkpoint/output bytes changed: '+str(path))
        self.files[str(path)]=h

def exact_stdout_path(path,key,parent):
    values=[]
    for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
        try:item=json.loads(line)
        except json.JSONDecodeError:continue
        if isinstance(item,dict) and key in item:values.append(Path(item[key]).resolve())
    require(len(set(values))==1,'Missing or ambiguous exact '+key+' in '+str(path))
    value=values[-1]
    require(value.parent==Path(parent).resolve(),'Unexpected output directory: '+str(value))
    return value

def complete_analysis(cam,receipt,plan,repair=None,override=None):
    link=override if override is not None else receipt.read(cam/'analysis_result.json')
    analysis=Path(link['analysis']).resolve();version=cam.parents[1]
    result_root=Path(repair['root']).resolve() if override is not None else version
    expected_sources=repair['source_hashes'] if override is not None else plan['source_hashes']
    if override is not None:
        require(override['repair_source_hashes']==expected_sources,'Repair certificate source pin mismatch')
        check_source_pin(result_root,expected_sources)
    require(analysis.parent==(result_root/'results').resolve(),'Analysis not in pinned version results')
    require(Path(link['summary']['path']).resolve()==analysis/'summary.json','Analysis summary reference/path mismatch')
    summary=receipt.ref(link['summary'],analysis)
    marker=receipt.read(analysis/'COMPLETE.json')
    require(marker['status']=='completed' and marker['summary_sha256']==link['summary']['sha256'],'Analysis completion/hash mismatch')
    require(not (analysis/'FAILED.json').exists(),'Analysis has retained failure marker')
    require(summary['execution_status']=='completed_file_only_analysis' and summary['completed_jobs']==20
            and summary['planned_jobs']==20 and Path(summary['campaign']).resolve()==cam,'Analysis is partial or belongs to another campaign')
    require(summary['analysis_new_environment_steps']==summary['analysis_SAC_updates']==0,'Analysis added learning/evaluation cost')
    require(summary['future_execution_authorized_by_analysis'] is False,'Analysis supplied an unintended progression authorization')
    checks=receipt.read(analysis/'checks.json');require(not checks.get('failed'),'Analysis failed checks')
    if override is None:
        verify=exact_stdout_path(cam/'verify_stdout.log','verification_dir',version/'results')
        receipt.binary(cam/'verify_stdout.log',sha(cam/'verify_stdout.log'))
    else:
        verify=Path(override['verification']).resolve()
        require(verify.parent==(result_root/'results').resolve(),'Repair verification escaped pinned results')
    complete=receipt.read(verify/'COMPLETE.json');vs=receipt.read(verify/'summary.json',complete['summary_sha256'])
    require(complete['status']=='completed' and vs['status']=='passed','Independent verification failed')
    require(vs['full_campaign'] is True and vs['self_test_only'] is False,'Verification is partial or only a self-test')
    require(vs['new_environment_steps']==vs['SAC_updates']==0,'Verification added environment steps')
    require(not (verify/'FAILED.json').exists(),'Verification has a retained failure marker')
    verified=receipt.read(verify/'verified_inputs.json')
    require(Path(verified['analysis']).resolve()==analysis and verified['summary_sha256']==link['summary']['sha256'],
            'Verification belongs to another analysis/summary')
    receipt.binary(analysis/'input_assets.json',verified['asset_receipt_sha256'])
    verify_sources=receipt.read(verify/'source_hashes.json')
    require(all(name in verify_sources and name in expected_sources and verify_sources[name]==expected_sources[name]
                for name in ('analyze_baseline.py','verify_baseline.py')),
            'Independent verification used unexpected source')
    return {'analysis':str(analysis),'analysis_summary':link['summary'],'verification':str(verify),
            'analysis_origin':'separate_pinned_file_only_repair' if override is not None else 'original64'}

def known_analysis_failure(cam,config,receipt):
    repair=config.get('analysis_repair')
    require(isinstance(repair,dict),'64 analysis failed and no separately pinned repair is authorized')
    require(not (cam/'analysis_result.json').exists(),'Unexpected original analysis-result artifact on known-failure route')
    path=cam/'analysis_stderr.log';receipt.binary(path,sha(path))
    stderr=path.read_text(encoding='utf-8-sig');lines=[line.strip() for line in stderr.splitlines() if line.strip()]
    expected_message=repair.get('known_error_message',"unsupported operand type(s) for +: 'int' and 'str'")
    expected_line=repair.get('known_source_line','evaluated = sum(row["length"] for row in worker_rows)').strip()
    source=cam.parents[1]/'analyze_baseline.py'
    require(lines and lines[-1]=='TypeError: '+expected_message and expected_line in lines
            and str(source.resolve()) in stderr,'64 failure does not exactly match the predeclared CSV-string sum TypeError')
    require(source.read_text(encoding='utf-8-sig').count(expected_line)==1,'Known failure expression/source mismatch')
    check_source_pin(Path(repair['root']),repair['source_hashes'])
    return {'expected_error':lines[-1],'expected_source_line':expected_line,
            'stderr_sha256':sha(path),'repair_root':str(Path(repair['root']).resolve()),
            'repair_source_hashes':repair['source_hashes']}

def validate_predecessor(config,allow_known_repair=False,analysis_override=None):
    """Return a complete, hash-linked receipt; Pending is the only polling case."""
    cam=Path(config['campaign']).resolve();receipt=Receipt()
    status_path=cam/'STATUS.json'
    if not status_path.exists():raise Pending('Waiting for pinned campaign status')
    status=receipt.read(status_path)
    if status.get('status') in ('prepared','running'):raise Pending('64 remains '+status['status'])
    needs_repair=status.get('status')=='research_completed_analysis_failed'
    require(status.get('status')=='completed' or (needs_repair and (allow_known_repair or analysis_override is not None)),
            '64 terminal state is not fully completed: '+str(status.get('status')))
    require(analysis_override is None or needs_repair,'External analysis override is permitted only for the known original analysis failure')
    require(status.get('completed')==20 and status.get('failed')==0 and status.get('total')==20 and status.get('error') is None,
            '64 terminal counts/error do not certify all twenty jobs')
    require(status.get('unaccounted_attempt_reserved_upper_bound',0)==0,'64 has unaccounted attempt costs')
    require(Path(config['plan_integrity']['path']).resolve()==cam/'plan_integrity.json','Pinned plan-integrity path mismatch')
    integrity=receipt.ref(config['plan_integrity'],cam)
    require(integrity==config['plan'],'Pinned plan and plan-integrity reference differ')
    require(Path(config['plan']['path']).resolve()==cam/'plan.json','Pinned plan path mismatch')
    plan=receipt.ref(config['plan'],cam)
    require(plan['source_hashes']==config['source_hashes'],'64 source pin differs from its campaign plan')
    version=cam.parents[1]
    for relative,h in plan['source_hashes'].items():
        source=version/relative;require(within(source,version),'Invalid source-relative path')
        receipt.binary(source,h)
    require(len(plan['jobs'])==config.get('expected_jobs',20)==20,'Unexpected predecessor job scope')
    expected={j['id']:j for j in plan['jobs']};require(len(expected)==20,'Duplicate predecessor planned jobs')
    completion=receipt.read(cam/'completion_summary.json')
    require(completion['status']=='completed' and completion['planned_jobs']==20 and not completion['failed']
            and len(completion['completed'])==20,'64 has failed/missing/numerically failed jobs')
    entries={item['id']:item for item in completion['completed']}
    require(set(entries)==set(expected) and len(entries)==20,'64 completion identities differ from plan')
    train=0;evaluation=0;physical=0
    for jid,job in expected.items():
        item=entries[jid];marker=receipt.read(cam/'completed'/(jid+'.json'))
        require(marker==item['result'],'Per-job completion marker differs from completion list')
        result=receipt.ref(item['result'],cam/'jobs'/jid);cost=receipt.ref(item['costs'],cam/'jobs'/jid)
        attempt=Path(item['result']['path']).parent
        require(Path(item['costs']['path']).parent==attempt,'Result/cost attempt mismatch')
        require(result['id']==jid and result['job']==job and result['status']=='completed','Unexpected completed worker identity')
        state=plan['states'][job['state_index']]
        require(result['state']==state,'Worker source state differs from frozen plan')
        require(cost['status']=='completed' and result['training_steps']==cost['training_steps']==32000,'Worker training incomplete')
        require(cost['costs']['train_iterations']==32000 and cost['costs']['evaluation_episodes']==440,'Worker update/case count incomplete')
        require(result['evaluation_steps']==cost['evaluation_steps'] and 0<=cost['evaluation_steps']<=220000,'Worker evaluation cost mismatch')
        require(cost['costs']['environment_steps']==cost['training_steps']+cost['evaluation_steps']<=252000,'Worker physical cost mismatch')
        request=receipt.read(attempt/'request.json');runtime=receipt.read(attempt/'runtime.json')
        require(request['job']==job and request['source_hashes']==plan['source_hashes']
                and Path(request['output']).resolve()==attempt,'Worker request provenance mismatch')
        require(runtime['source_hashes']==plan['source_hashes'] and runtime['job']==job,'Executed runtime source/job mismatch')
        start=receipt.read(attempt/'research_start_integrity.json');fork=receipt.read(attempt/'fork_integrity.json')
        sm=receipt.read(Path(state['checkpoint']['path'])/'checkpoint_manifest.json',state['checkpoint']['manifest_sha256'])
        require(start['restored_original_S_again'] is True and start['environment_steps_before_fork']==0
                and start['full_fingerprints']==sm['state_fingerprints'],'Worker did not restore original full S')
        require(fork['before']==fork['after'] and fork['preserved_visits_and_queue'] is True
                and fork['root_seed']==job['root_seed'] and fork['condition']==job['condition'],'Invalid collection-only fork provenance')
        require(len(result['checkpoints'])==4,'Missing full checkpoint')
        for checkpoint,end in zip(result['checkpoints'],(212000,216000,224000,240000)):
            cp=Path(checkpoint['path']).resolve();require(within(cp,attempt),'Checkpoint escaped worker attempt')
            manifest=receipt.read(cp/'checkpoint_manifest.json',checkpoint['manifest_sha256'])
            require(checkpoint['absolute_step']==manifest['step']==end and manifest['updates']==end-1000,'Checkpoint step/update mismatch')
            require(manifest['source_hashes']==plan['source_hashes'],'Checkpoint executed-source mismatch')
            for filename,h in manifest['files'].items():
                require(Path(filename).name==filename,'Unsafe checkpoint member name')
                receipt.binary(cp/filename,h)
            if 'telemetry_state' in checkpoint:receipt.binary(checkpoint['telemetry_state']['path'],checkpoint['telemetry_state']['sha256'])
        receipt.binary(result['episodes']['path'],result['episodes']['sha256'])
        train+=cost['training_steps'];evaluation+=cost['evaluation_steps'];physical+=cost['costs']['environment_steps']
    require(train==completion['training_steps']==status['training_steps']==640000,'Campaign training total mismatch')
    require(evaluation==completion['evaluation_steps']==status['evaluation_steps']<=4400000,'Campaign evaluation total mismatch')
    total=physical+plan['technical_steps']+plan.get('new_P_S_evaluation_steps',0)
    require(total==completion['total_environment_steps']==status['actual_environment_steps']<=6050000,'Campaign total cost mismatch')
    require(plan['technical_steps']<=10000,'Predecessor technical budget exceeded')
    known=known_analysis_failure(cam,config,receipt) if needs_repair else None
    if needs_repair and analysis_override is None:
        analysis={'requires_analysis_repair':True,'known_failure':known}
    else:
        analysis=complete_analysis(cam,receipt,plan,config.get('analysis_repair'),analysis_override)
    require(load(status_path)==status,'64 terminal status changed during completion audit')
    return {'status':'research_verified_needs_analysis_repair' if needs_repair and analysis_override is None else 'passed',
            'original_status':status['status'],'campaign':str(cam),'completed_jobs':20,'total_environment_steps':total,
            'plan':config['plan'],**analysis,'artifact_hashes':receipt.files,'checked_at':utc(),
            'scope':'Execution/integrity completion only; no scientific effect-direction gate'}

@contextlib.contextmanager
def queue_lock(path):
    """OS-released lock; separate permanent dispatch receipt prevents crash retries."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    stream=path.open('a+b')
    if stream.tell()==0:stream.write(b'0');stream.flush()
    stream.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except (OSError,BlockingIOError):
        stream.close();raise Rejected('Another deferred watcher owns the exclusive lock')
    try:yield
    finally:
        if os.name=='nt':
            import msvcrt
            stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(),fcntl.LOCK_UN)
        stream.close()

def claim_dispatch(path,value):
    try:exclusive_json(path,value)
    except FileExistsError:raise Rejected('Dispatch already claimed; automatic re-entry/retry is forbidden')

@contextlib.contextmanager
def keep_awake():
    """Hold only this process's Windows execution request; leave power plans alone."""
    native=None
    if os.name=='nt':
        import ctypes
        native=ctypes.windll.kernel32
        require(bool(native.SetThreadExecutionState(0x80000001)),'Could not establish Windows keep-awake request')
    try:yield
    finally:
        if native is not None:native.SetThreadExecutionState(0x80000000)

def validate_technical_marker(directory,pin):
    directory=Path(directory).resolve();v=load(directory/'VERIFIED.json');receipt=Receipt()
    summary=receipt.ref(v['summary'],directory)
    require(summary['status']=='passed' and not summary['failed_checks'] and v['source_hashes']==pin,
            'Downstream technical gate does not certify this frozen version')
    require(summary.get('source_hashes',pin)==pin,'Technical summary source differs from armed source')
    steps=summary.get('total_technical_environment_steps_all_attempts',summary.get('costs',{}).get('environment_steps',0))
    require(0<=steps<=20000,'Downstream cumulative technical environment cap exceeded')
    return v,summary

class DeferredQueue:
    def __init__(self,root=ROOT):
        self.root=Path(root).resolve();self.config_path=self.root/'inputs/upstream_campaign.json'
        require(self.config_path.is_file() and (self.root/'protocol.json').is_file(),'Frozen queue inputs/protocol are not ready')
        self.config=load(self.config_path);self.pin=source_hashes(self.root)
        require(self.config.get('schema_version')==1,'Unknown upstream pin schema')
        self.run=self.root/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_deferred_'+uuid.uuid4().hex[:8])
        (self.run/'source_snapshot').mkdir(parents=True,exist_ok=False)
        for relative,h in self.pin.items():
            target=self.run/'source_snapshot'/(h[:20]+Path(relative).suffix)
            if not target.exists():shutil.copy2(self.root/relative,target)
        exclusive_json(self.run/'source_hashes.json',self.pin)
        exclusive_json(self.run/'request.json',{'upstream':self.config,'upstream_config_sha256':sha(self.config_path),
            'source_hashes':self.pin,'python':sys.executable,'created_at':utc(),'poll_seconds':30,'max_wait_seconds':86400,
            'stop_policy':'STOP cancels waiting/new stages; active bounded child is allowed to finish, never controller-only killed.',
            'automatic_retries':0})
        print(json.dumps({'queue':str(self.run),'pid':os.getpid(),'created_at':utc()},ensure_ascii=False),flush=True)
    def status(self,status,**extra):
        atomic_json(self.run/'STATUS.json',{'status':status,'updated_at':utc(),'queue':str(self.run),**extra})
    def cancelled(self):return (self.root/'STOP').exists() or (self.run/'STOP').exists()
    def check_before_stage(self):
        if self.cancelled():raise Cancelled('STOP requested; no additional stage will start')
        check_source_pin(self.root,self.pin)
        repair=self.config.get('analysis_repair')
        if repair:check_source_pin(Path(repair['root']),repair['source_hashes'])
    def child(self,name,command):
        self.check_before_stage();folder=self.run/name;folder.mkdir()
        exclusive_json(folder/'request.json',{'command':command,'created_at':utc(),'source_hashes':self.pin})
        self.status(name+'_running',child_stage=name)
        with (folder/'stdout.log').open('x',encoding='utf-8') as out,(folder/'stderr.log').open('x',encoding='utf-8') as err:
            proc=subprocess.Popen(command,cwd=self.root,stdout=out,stderr=err,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            exclusive_json(folder/'process.json',{'pid':proc.pid,'started_at':utc(),'command':command})
            while proc.poll() is None:
                self.status(name+'_running',pid=proc.pid,cancel_pending=self.cancelled())
                time.sleep(POLL_SECONDS)
            code=proc.returncode
        exclusive_json(folder/'exit.json',{'returncode':code,'finished_at':utc()})
        require(code==0,name+' subprocess failed; no automatic retry')
        check_source_pin(self.root,self.pin)
        return folder
    def execute(self):
        claim=self.root/'results/DEFERRED_DISPATCH.json'
        with queue_lock(self.root/'results/deferred_queue.lock'),keep_awake():
            atomic_json(self.root/'ACTIVE_QUEUE.json',{'queue':str(self.run),'pid':os.getpid(),'started_at':utc()})
            require(not claim.exists(),'This version already dispatched a follow-up; no retry')
            deadline=time.monotonic()+MAX_WAIT_SECONDS
            self.status('waiting_upstream',wait_deadline_epoch=time.time()+MAX_WAIT_SECONDS)
            while True:
                self.check_before_stage()
                if time.monotonic()>=deadline:raise Cancelled('Twenty-four-hour wait limit reached without dispatch')
                try:receipt=validate_predecessor(self.config,allow_known_repair=bool(self.config.get('analysis_repair')));break
                except Pending as exc:
                    self.status('waiting_upstream',reason=str(exc),seconds_remaining=max(0,int(deadline-time.monotonic())))
                    time.sleep(POLL_SECONDS)
            exclusive_json(self.run/'upstream_completion_receipt.json',receipt)
            self.check_before_stage()
            if time.monotonic()>=deadline:raise Cancelled('Twenty-four-hour wait limit reached during completion verification')
            claim_dispatch(claim,{'queue':str(self.run),'upstream_receipt_sha256':sha(self.run/'upstream_completion_receipt.json'),
                'protocol_sha256':self.pin['protocol.json'],'claimed_at':utc(),'automatic_retry':False})
            if receipt.get('requires_analysis_repair'):
                repair=self.config['analysis_repair'];repair_root=Path(repair['root']).resolve()
                analysis_stage=self.child('upstream_file_only_analysis_repair',[sys.executable,'-B',
                    str(repair_root/repair.get('analysis_script','analyze_baseline.py')),'--campaign',self.config['campaign']])
                analysis=exact_stdout_path(analysis_stage/'stdout.log','analysis_dir',repair_root/'results')
                verify_stage=self.child('upstream_file_only_independent_verification',[sys.executable,'-B',
                    str(repair_root/repair.get('verification_script','verify_baseline.py')),'--analysis-dir',str(analysis)])
                verification=exact_stdout_path(verify_stage/'stdout.log','verification_dir',repair_root/'results')
                certificate={'analysis':str(analysis),'summary':{'path':str(analysis/'summary.json'),'sha256':sha(analysis/'summary.json')},
                    'verification':str(verification),'repair_source_hashes':repair['source_hashes'],
                    'new_environment_steps':0,'new_training_steps':0,'original64_not_modified':True,
                    'analysis_stdout':{'path':str(analysis_stage/'stdout.log'),'sha256':sha(analysis_stage/'stdout.log')},
                    'verification_stdout':{'path':str(verify_stage/'stdout.log'),'sha256':sha(verify_stage/'stdout.log')}}
                exclusive_json(self.run/'upstream_analysis_repair_certificate.json',certificate)
                receipt=validate_predecessor(self.config,analysis_override=certificate)
                exclusive_json(self.run/'upstream_repaired_completion_receipt.json',receipt)
                require(receipt['status']=='passed','Separate pure-data repair did not certify a complete predecessor')
            tech=self.child('technical',[sys.executable,'-B',str(self.root/'verify_implementation.py')])
            verified=exact_stdout_path(tech/'stdout.log','run',self.root/'results')
            v,summary=validate_technical_marker(verified,self.pin)
            exclusive_json(self.run/'technical_result.json',{'directory':str(verified),'marker_sha256':sha(verified/'VERIFIED.json'),
                'summary':v['summary']})
            prepared=self.child('prepare',[sys.executable,'-B',str(self.root/'campaign.py'),'prepare','--verification',str(verified)])
            campaign=exact_stdout_path(prepared/'stdout.log','campaign',self.root/'results')
            integrity=load(campaign/'plan_integrity.json');plan=Receipt().ref(integrity,campaign)
            protocol=load(self.root/'protocol.json')
            require(plan['source_hashes']==self.pin and len(plan['jobs'])==int(protocol.get('jobs',40))==40,
                    'Prepared downstream plan/source/job count differs from authorized forty jobs')
            exclusive_json(self.run/'prepared_campaign.json',{'campaign':str(campaign),'plan':integrity})
            self.child('campaign',[sys.executable,'-B',str(self.root/'campaign.py'),'run','--campaign',str(campaign)])
            status=load(campaign/'STATUS.json')
            require(status['status']=='completed' and status['completed']==40 and status['failed']==0,
                    'Downstream did not finish all forty jobs and analysis verification successfully')
            self.status('completed',campaign=str(campaign),completion_status=status)
            return 0

def main():
    queue=None
    try:
        queue=DeferredQueue();return queue.execute()
    except Cancelled as exc:
        if queue:queue.status('cancelled',reason=str(exc),automatic_retry=False)
        print(json.dumps({'status':'cancelled','reason':str(exc)},ensure_ascii=False));return 0
    except BaseException as exc:
        if queue:queue.status('blocked',error_type=type(exc).__name__,reason=str(exc),automatic_retry=False)
        print(json.dumps({'status':'blocked','reason':str(exc)},ensure_ascii=False));return 1

if __name__=='__main__':raise SystemExit(main())
