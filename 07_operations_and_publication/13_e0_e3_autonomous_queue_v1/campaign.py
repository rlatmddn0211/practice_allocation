"""Frozen E0-E3 DAG and durable sequential Windows queue."""
from __future__ import annotations

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

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
STAGES = {'E0':'09_fresh_evaluation_audit_v1', 'E1':'10_independent_seed_checkpoint_study_v1',
          'E2':'11_fixed_target_donor_swap_v1', 'E3':'12_task_composition_study_v1'}
P0 = REPO / '02_p0_uniform_pretraining_v1/results/20261007T060310Z_p0_cuda_50621c50/run'
DISCOVERY = REPO / '04_p0_allocation_branches_v1/results/20261007T091127Z_allocation_branches_cuda_64ec1ea7/run'
REPEATS = REPO / '06_p0_branch_replication_v1/results/20261008T030554Z_branch_replication_cuda_2c28c437/run'
LABELS = {'A':['DO','DC','WO','WC'], 'B':['DO','DC','PU','BP'], 'C':['DO','PP','PU','BP']}


def now():
    return datetime.now(timezone.utc).isoformat()


def stamp():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def atomic(path, value):
    path = Path(path)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex[:8] + '.tmp')
    write(temp, value)
    os.replace(temp, path)


def stage_hashes(directory):
    files = sorted(directory.glob('*.py')) + sorted(directory.glob('*.ps1'))
    files += [directory/'requirements.txt', directory/'VERSION.json']
    for sub, pattern in [('practice_allocation','*.py'),('configs','*.json'),('tests','*.py')]:
        files += sorted((directory/sub).rglob(pattern))
    return {path.relative_to(directory).as_posix():sha(path) for path in files if path.is_file()}


def ref(job, key):
    return {'from_job':job, 'key':key}


def checkpoint(path):
    return {'path':str(path), 'manifest_sha256':sha(path/'checkpoint_manifest.json')}


def stream_seed(stage, suite, original, cp, repeat):
    import numpy as np
    return int(np.random.SeedSequence([repeat, 701, int(stage[1:]), ord(suite), original, cp]).generate_state(1)[0])


def make_plan(technical=False,storage_root=None):
    jobs = []
    ids = set()
    def add(job_id, stage, suite='A', seed=901, **fields):
        if job_id in ids:
            raise ValueError('Duplicate job ID: '+job_id)
        ids.add(job_id)
        jobs.append(dict(id=job_id, stage=stage, suite=suite, original_seed=seed, **fields))
        return job_id
    parent = checkpoint(P0/'checkpoints/step_000200000')
    bank0 = add('E0_bank', 'E0', kind='bank', bank_seed=95001)
    public0 = add('E0_public', 'E0', kind='evaluate', parent=parent, bank=ref(bank0,'bank'), bank_kind='diagnostic', role='public', checkpoint_step=200000)
    add('E0_rules', 'E0', kind='rules', current_public=ref(public0,'result_ref'), checkpoint_step=200000)
    add('E0_baseline', 'E0', kind='evaluate', parent=parent, bank=ref(bank0,'bank'), bank_kind='outcome', role='baseline', checkpoint_step=200000)
    for repeat in [1903,1904,1905,1901,1902]:
        for allocation in ['U','F_DO','F_DC','F_WO','F_WC']:
            run = REPEATS if repeat >= 1903 else DISCOVERY
            endpoint = checkpoint(run/f'branches/repeat_{repeat}_{allocation}/checkpoints/extra_040000')
            add(f'E0_r{repeat}_{allocation}', 'E0', kind='evaluate', parent=endpoint, bank=ref(bank0,'bank'), bank_kind='outcome',
                role='branch', checkpoint_step=200000, continuation_label=repeat, allocation=allocation, horizon=40000)
    add('E0_analysis', 'E0', kind='analysis')

    parents, publics, bankids = {}, {}, {}
    def pretrains(stage, suites, steps, bank_seeds):
        for suite, bank_seed in zip(suites,bank_seeds):
            bank_id = add(f'{stage}_{suite}_bank', stage, suite, 11, kind='bank', bank_seed=bank_seed)
            bankids[(stage,suite)] = bank_id
            for seed in [11,12,13]:
                prev = add(f'{stage}_{suite}_s{seed}_init', stage, suite, seed, kind='init')
                publics[(stage,suite,seed,0)] = add(f'{stage}_{suite}_s{seed}_pub0', stage, suite, seed,
                    kind='evaluate', parent=ref(prev,'checkpoint'), bank=ref(bank_id,'bank'), bank_kind='diagnostic', role='public', checkpoint_step=0)
                for step in range(20000, steps+1, 20000):
                    prev = add(f'{stage}_{suite}_s{seed}_pre{step//1000}', stage, suite, seed, kind='train',
                               parent=ref(prev,'checkpoint'), start_step=step-20000, steps=20000, allocation='U')
                    parents[(stage,suite,seed,step)] = prev
                    if step in (100000,200000,400000):
                        publics[(stage,suite,seed,step)] = add(f'{stage}_{suite}_s{seed}_pub{step//1000}', stage, suite, seed,
                            kind='evaluate', parent=ref(prev,'checkpoint'), bank=ref(bank_id,'bank'), bank_kind='diagnostic', role='public', checkpoint_step=step)
    def branches(stage, suites, checkpoints, repeats, donor=False):
        for suite in suites:
            bank_id = bankids[(stage,suite)]
            for seed in [11,12,13]:
                for cp in checkpoints:
                    parent_stage = 'E1' if stage=='E2' else stage
                    parent_id = parents[(parent_stage,suite,seed,cp)]
                    prefix = f'{stage}_{suite}_s{seed}_c{cp//1000}'
                    if stage != 'E2':
                        previous_cp = 100000 if cp==200000 else 200000
                        add(prefix+'_rules', stage, suite, seed, kind='rules', checkpoint_step=cp,
                            current_public=ref(publics[(stage,suite,seed,cp)],'result_ref'),
                            previous_public=ref(publics[(stage,suite,seed,previous_cp)],'result_ref'), elapsed=cp-previous_cp)
                    add(prefix+'_base', stage, suite, seed, kind='evaluate', parent=ref(parent_id,'checkpoint'),
                        bank=ref(bank_id,'bank'), bank_kind='outcome', role='baseline', checkpoint_step=cp)
                    allocations = ['U','DC_plus_WO_minus','DC_minus_WO_plus'] if donor else ['U']+['F_'+t for t in LABELS[suite]]
                    for repeat in repeats:
                        for allocation in allocations:
                            short = {'DC_plus_WO_minus':'DCplus','DC_minus_WO_plus':'WOplus'}.get(allocation,allocation)
                            branch = prefix+f'_r{repeat}_{short}'
                            previous = parent_id
                            for horizon in [20000,40000]:
                                previous = add(branch+f'_t{horizon//1000}', stage, suite, seed, kind='train',
                                    parent=ref(previous,'checkpoint'), start_step=cp+horizon-20000, steps=20000,
                                    start_branch=horizon==20000, continuation_label=repeat,
                                    continuation_rng_seed=stream_seed(stage,suite,seed,cp,repeat), allocation=allocation,
                                    checkpoint_step=cp, horizon=horizon)
                                add(branch+f'_e{horizon//1000}', stage, suite, seed, kind='evaluate', parent=ref(previous,'checkpoint'),
                                    bank=ref(bank_id,'bank'), bank_kind='outcome', role='branch', checkpoint_step=cp,
                                    continuation_label=repeat, allocation=allocation, horizon=horizon)
        add(stage+'_analysis', stage, suites[0], 11, kind='analysis')
    pretrains('E1',['A'],400000,[95101])
    branches('E1',['A'],[200000,400000],[2101,2102,2103])
    bankids[('E2','A')] = add('E2_A_bank','E2','A',11,kind='bank',bank_seed=95201)
    branches('E2',['A'],[200000],[2201,2202,2203],donor=True)
    pretrains('E3',['B','C'],200000,[95301,95302])
    branches('E3',['B','C'],[200000],[2301,2302,2303])
    counts = {}
    for stage in STAGES:
        selected = [j for j in jobs if j['stage']==stage]
        counts[stage] = dict(training_steps=sum(j.get('steps',0) for j in selected),
                            evaluation_episodes=400*sum(j['kind']=='evaluate' for j in selected),
                            branches=sum(j.get('start_branch',False) for j in selected), jobs=len(selected))
    expected = {'E0':(0,10800,0),'E1':(4800000,79200,90),'E2':(1080000,22800,27),'E3':(4800000,81600,90)}
    for stage, values in expected.items():
        if tuple(counts[stage][key] for key in ('training_steps','evaluation_episodes','branches')) != values:
            raise ValueError('Budget differs from approved protocol: '+stage)
    if len(ids) != len(jobs):
        raise ValueError('Job identifiers must be unique.')
    seen = set()
    def dependencies(value):
        if isinstance(value,dict):
            if 'from_job' in value:
                yield value['from_job']
            else:
                for child in value.values():
                    yield from dependencies(child)
        elif isinstance(value,list):
            for child in value:
                yield from dependencies(child)
    for job in jobs:
        if any(dep not in seen for dep in dependencies(job)):
            raise ValueError('Non-topological job dependency: '+job['id'])
        seen.add(job['id'])
    return {'schema':1,'authorized_at':'2026-10-08','created_at':now(),'status':'authorized_E0_through_E3',
            'storage_root':str(Path(storage_root or REPO).resolve()),
            'protocol_sha256':sha(REPO/'08_followup_experiment_design_v1/protocol.json'),
            'stage_directories':STAGES,'sources':{s:stage_hashes(REPO/d) for s,d in STAGES.items()},
            'controller_sources':{p.name:sha(p) for pattern in ('*.py','*.ps1','requirements.txt') for p in ROOT.glob(pattern)},
            'counts':counts,'jobs':jobs,'original_seeds':[11,12,13],
            'technical_smoke':technical,'success_gates':False,'optional_R_E4_included':False,
            'maximum_attempts_per_job':3,'minimum_free_bytes':1500000000,
            'checkpoint_policy':'Full lossless state every 20k; exclusive attempt directories; no old output deletion.',
            'recovery':'Resume completed jobs; retry interrupted atomic job from its immutable parent (at most 20k repeated training).'}


class QueueLock:
    def __init__(self,path):
        self.path, self.stream = Path(path), None
    def __enter__(self):
        import msvcrt
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open('a+b')
        if self.path.stat().st_size==0:
            self.stream.write(b'0')
            self.stream.flush()
        self.stream.seek(0)
        try:
            msvcrt.locking(self.stream.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            self.stream.close()
            return False
        return True
    def __exit__(self,*_):
        if self.stream and not self.stream.closed:
            import msvcrt
            self.stream.seek(0)
            msvcrt.locking(self.stream.fileno(),msvcrt.LK_UNLCK,1)
            self.stream.close()


def alive(identity):
    import psutil
    try:
        proc = psutil.Process(identity['pid'])
        return proc.is_running() and abs(proc.create_time()-identity['process_created'])<.01
    except psutil.Error:
        return False


def resolve(value, completed):
    if isinstance(value,dict):
        if 'from_job' in value:
            return completed[value['from_job']][value['key']]
        return {k:resolve(v,completed) for k,v in value.items()}
    if isinstance(value,list):
        return [resolve(v,completed) for v in value]
    return value


def validate_completed(marker):
    path = Path(marker['result_ref']['path'])
    if sha(path) != marker['result_ref']['sha256']:
        raise RuntimeError('Immutable completed result changed: '+str(path))
    result = read(path)
    if 'checkpoint' in result:
        ref_data = result['checkpoint']
        manifest = Path(ref_data['path'])/'checkpoint_manifest.json'
        if sha(manifest) != ref_data['manifest_sha256']:
            raise RuntimeError('Completed checkpoint manifest changed.')
    if 'episodes_path' in result and sha(result['episodes_path']) != result['episodes_sha256']:
        raise RuntimeError('Completed evaluation episodes changed.')
    return {**result,'result_ref':marker['result_ref']}


def run(campaign):
    campaign = Path(campaign).resolve()
    with QueueLock(campaign/'controller.lock') as acquired:
        if not acquired:
            print('Campaign controller is already active.',flush=True)
            return 0
        plan = read(campaign/'plan.json')
        if sha(campaign/'plan.json') != read(campaign/'plan_integrity.json')['sha256']:
            raise RuntimeError('Frozen campaign plan changed.')
        existing = read(campaign/'STATUS.json') if (campaign/'STATUS.json').exists() else {}
        if existing.get('state') in ('completed','integrity_failed','failed'):
            print('Campaign is terminal: '+existing['state'],flush=True)
            return 0
        for stage,directory in STAGES.items():
            if stage_hashes(REPO/directory) != plan['sources'][stage]:
                atomic(campaign/'STATUS.json',{'state':'integrity_failed','time':now(),'message':'Frozen implementation changed: '+stage})
                return 1
        for relative,digest in plan.get('controller_sources',{}).items():
            if sha(ROOT/relative)!=digest:
                atomic(campaign/'STATUS.json',{'state':'integrity_failed','time':now(),'message':'Frozen queue source changed: '+relative})
                return 1
        if os.name=='nt':
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
        started = time.perf_counter()
        completed = {}
        for path in sorted((campaign/'completed').glob('*.json')):
            marker = read(path)
            completed[marker['id']] = validate_completed(marker)
        old_bank = {'path':str(P0/'evaluation_banks.json'),'sha256':sha(P0/'evaluation_banks.json')}
        def event(name,**extra):
            with (campaign/'events.jsonl').open('a',encoding='utf-8') as stream:
                stream.write(json.dumps({'time':now(),'event':name,**extra},ensure_ascii=False)+'\n')
        def status(state,**extra):
            atomic(campaign/'STATUS.json',{'state':state,'time':now(),'controller_pid':os.getpid(),
                    'completed_jobs':len(completed),'total_jobs':len(plan['jobs']),'planned_costs':plan['counts'],**extra})
        event('controller_started',pid=os.getpid())
        try:
            for index,job in enumerate(plan['jobs']):
                if job['id'] in completed:
                    continue
                if (campaign/'STOP_AFTER_JOB').exists():
                    status('stopped_by_user',next_job=job['id'])
                    return 0
                while shutil.disk_usage(plan['storage_root']).free < plan['minimum_free_bytes']:
                    if (campaign/'STOP_AFTER_JOB').exists():
                        status('stopped_by_user',next_job=job['id'])
                        return 0
                    status('waiting_for_disk_space',job=job['id'],free_bytes=shutil.disk_usage(plan['storage_root']).free)
                    time.sleep(30)
                attempts = campaign/'attempts'/job['id']
                attempts.mkdir(parents=True,exist_ok=True)
                done = False
                previous_attempts = sorted(attempts.glob('*.json'))
                for number in range(1,plan['maximum_attempts_per_job']+1):
                    identity_path = attempts/f'{number:02}.json'
                    intent_path = attempts/f'{number:02}.launch_intent'
                    if not identity_path.exists() and intent_path.exists():
                        import psutil
                        intent = read(intent_path)
                        recovered = dict(intent, pid=-1, process_created=0)
                        # Recover the tiny launch-to-PID-record window without a duplicate worker.
                        for proc in psutil.process_iter(['pid','cmdline','create_time']):
                            args = proc.info['cmdline'] or []
                            if str(Path(intent['output'])/'request.json') in args:
                                recovered.update(pid=proc.pid,process_created=proc.info['create_time'])
                                break
                        write(identity_path,recovered)
                    if identity_path.exists():
                        identity = read(identity_path)
                        output = Path(identity['output'])
                        # Recover a result completed just before a controller interruption.
                        while alive(identity):
                            status('running',stage=job['stage'],job=job['id'],worker_pid=identity['pid'],attempt=number,
                                   output=str(output),adopted_worker=True)
                            time.sleep(10)
                    else:
                        output = Path(plan['storage_root'])/STAGES[job['stage']]/'results'/campaign.name/job['id']/f'a{number:02}_{uuid.uuid4().hex[:6]}'
                        output.mkdir(parents=True,exist_ok=False)
                        request = resolve(job,completed)
                        request.setdefault('bank_seed',{'E0':95001,'E1':95101,'E2':95201,'E3':95301 if job['suite']=='B' else 95302}[job['stage']])
                        banks = [old_bank]+[r['bank'] for r in completed.values() if r['kind']=='bank']
                        request.update(output=str(output),source_hashes=plan['sources'][job['stage']],all_banks=banks,
                                       technical_smoke=plan['technical_smoke'],worker_lock=str(campaign/'worker.lock'))
                        if job['kind']=='bank':
                            request['previous_banks'] = banks
                            request['previous_train_audits'] = [str(P0/'train_episodes.csv')]
                            request['previous_train_audits'] += [str(p) for root in (DISCOVERY,REPEATS) for p in (root/'branches').glob('*/train_episodes.csv')]
                            request['previous_train_audits'] += [r['training_reset_audit'] for r in completed.values() if r.get('training_reset_audit')]
                        if job['kind']=='analysis':
                            request['analysis_inputs'] = [r['result_ref'] for r in completed.values() if r['stage']==job['stage']]
                            if job['stage']=='E3':
                                request['suite_A_reference'] = completed['E1_analysis']['result_ref']
                        write(output/'request.json',request)
                        write(intent_path,{'output':str(output),'job':job['id'],'attempt':number,'created_at':now()})
                        event('job_started',id=job['id'],attempt=number,output=str(output))
                        # Open separate immutable stdout/stderr logs for every attempt.
                        with (output/'stdout.log').open('xb') as stdout, (output/'stderr.log').open('xb') as stderr:
                            env = dict(os.environ)
                            env.update(PYTHONUNBUFFERED='1',PYTHONHASHSEED='0',CUBLAS_WORKSPACE_CONFIG=':4096:8',
                                       OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
                            process = subprocess.Popen([sys.executable,'-u',str(REPO/STAGES[job['stage']]/'run_job.py'),
                                                        '--request',str(output/'request.json')],
                                                       cwd=REPO/STAGES[job['stage']],stdout=stdout,stderr=stderr,env=env,
                                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                        import psutil
                        identity = {'pid':process.pid,'process_created':psutil.Process(process.pid).create_time(),
                                    'output':str(output),'job':job['id'],'attempt':number,'created_at':now()}
                        write(identity_path,identity)
                        while process.poll() is None:
                            status('running',stage=job['stage'],job=job['id'],worker_pid=process.pid,attempt=number,output=str(output))
                            time.sleep(5)
                    if (output/'result.json').exists():
                        result = read(output/'result.json')
                        if result['id']!=job['id'] or not (output/'costs.json').exists():
                            raise RuntimeError('Worker result identity/cost ledger is incomplete.')
                        ledger=read(output/'costs.json')
                        expected_episodes=(8 if plan['technical_smoke'] else 400) if job['kind']=='evaluate' else 0
                        if ledger['costs']['evaluation_episodes']!=expected_episodes:
                            raise RuntimeError('Evaluation episode budget differs from the frozen job.')
                        if job['kind']=='train' and (ledger['costs']['environment_steps']!=job['steps'] or result['step']!=job['start_step']+job['steps']):
                            raise RuntimeError('Training cost or final step differs from the frozen job.')
                        marker = {'id':job['id'],'completed_at':now(),
                                  'result_ref':{'path':str(output/'result.json'),'sha256':sha(output/'result.json')}}
                        completed[job['id']] = validate_completed(marker)
                        write(campaign/'completed'/(job['id']+'.json'),marker)
                        event('job_completed',id=job['id'],attempt=number)
                        done = True
                        break
                    error = read(output/'error.json') if (output/'error.json').exists() else {'type':'InterruptedProcess','retryable':True,
                              'message':'Worker exited without a completion record; partial output retained. Actual interrupted costs may be a lower bound.'}
                    if error['type']=='InterruptedProcess' and not (output/'interruption.json').exists():
                        last_step=job.get('start_step',0)
                        metrics=output/'train_metrics.csv'
                        if metrics.exists():
                            with metrics.open(encoding='utf-8',newline='') as stream:
                                for row in csv.DictReader(stream):
                                    try:
                                        last_step=max(last_step,int(row['step']))
                                    except (ValueError,KeyError,TypeError):
                                        pass
                        lower_bound=last_step-job.get('start_step',last_step)
                        write(output/'interruption.json',{'detected_at':now(),'error':error,'observed_training_steps_lower_bound':lower_bound,
                              'unobserved_training_steps_upper_bound':249 if job['kind']=='train' and metrics.exists() else job.get('steps',0),
                              'evaluation_cost_may_be_incomplete':job['kind']=='evaluate'})
                    event('job_failed',id=job['id'],attempt=number,error=error)
                    if not error.get('retryable'):
                        status('integrity_failed',stage=job['stage'],job=job['id'],error=error,output=str(output))
                        return 1
                    time.sleep(min(10*number,30))
                if not done:
                    status('failed',stage=job['stage'],job=job['id'],message='Three attempts exhausted; retained all failed outputs.')
                    return 1
            if plan['technical_smoke']:
                status('completed',scope='technical queue verification; no scientific inference')
                event('technical_queue_completed')
                return 0
            costs = {'environment_creations':0,'resets':0,'environment_steps':0,'train_iterations':0,'evaluation_episodes':0}
            total_seconds, failed, incomplete = 0.0, [], []
            for path in sorted((campaign/'attempts').glob('*/*.json')):
                identity = read(path)
                cost_path = Path(identity['output'])/'costs.json'
                if cost_path.exists():
                    ledger = read(cost_path)
                    for name,value in ledger['costs'].items():
                        costs[name] += value
                    total_seconds += ledger['wall_seconds']
                    if not ledger['success']:
                        failed.append(identity)
                else:
                    incomplete.append(identity)
            write(campaign/'campaign_summary.json',{'completed_at':now(),'planned_costs':plan['counts'],
                  'measured_costs_completed_and_caught_failures':costs,'sum_worker_wall_seconds':total_seconds,
                  'failed_attempts':failed,'interrupted_attempts_with_incomplete_cost_counters':incomplete,
                  'reports':{s:completed[s+'_analysis'] for s in STAGES},'scientific_success_gate_used':False})
            status('completed',reports={s:completed[s+'_analysis']['report'] for s in STAGES})
            event('campaign_completed',controller_session_seconds=time.perf_counter()-started)
            return 0
        finally:
            if os.name=='nt':
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command',choices=['prepare','run','status'])
    parser.add_argument('--campaign',type=Path)
    parser.add_argument('--storage-root',type=Path)
    args = parser.parse_args()
    if args.command=='prepare':
        plan = make_plan(storage_root=args.storage_root)
        signoff_path=ROOT/'VALIDATION.json'
        if not signoff_path.exists():
            raise RuntimeError('Prepare requires a completed validation signoff.')
        signoff=read(signoff_path)
        if signoff['sources']!=plan['sources'] or not signoff['passed']:
            raise RuntimeError('Validation does not cover the current frozen stage implementations.')
        for evidence in signoff['evidence']:
            if sha(evidence['path'])!=evidence['sha256'] or not read(evidence['path'])['passed']:
                raise RuntimeError('Validation evidence is missing, changed, or failed.')
        plan['validation']={'path':str(signoff_path),'sha256':sha(signoff_path)}
        directory = Path(plan['storage_root'])/ROOT.name/'results'/(stamp()+'_e03_'+uuid.uuid4().hex[:6])
        directory.mkdir(parents=True,exist_ok=False)
        (directory/'completed').mkdir()
        write(directory/'plan.json',plan)
        write(directory/'plan_integrity.json',{'sha256':sha(directory/'plan.json')})
        for relative in plan['controller_sources']:
            path=ROOT/relative
            dest = directory/'source_snapshot'/path.name
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(path,dest)
        atomic(ROOT/'ACTIVE_CAMPAIGN.json',{'campaign':str(directory),'created_at':now()})
        atomic(directory/'STATUS.json',{'state':'prepared','counts':plan['counts'],'jobs':len(plan['jobs']),'time':now()})
        print(json.dumps({'campaign':str(directory),'counts':plan['counts'],'jobs':len(plan['jobs'])}))
        return 0
    campaign = args.campaign or Path(read(ROOT/'ACTIVE_CAMPAIGN.json')['campaign'])
    if args.command=='status':
        print(json.dumps(read(campaign/'STATUS.json'),indent=2,ensure_ascii=False))
        return 0
    try:
        return run(campaign)
    except BaseException as exc:
        traceback.print_exc()
        atomic(campaign/'STATUS.json',{'state':'integrity_failed','time':now(),'error':type(exc).__name__,'message':str(exc)})
        return 1


if __name__=='__main__':
    raise SystemExit(main())
