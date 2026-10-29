"""Bounded sequential twenty-path baseline, no seed replacement or automatic retry."""
import argparse
import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path
from common import (ROOT,unique,atomic,reference,checked,frozen_inputs,read_csv,TOTAL_CAP,TECH_CAP)
from practice_allocation.core import source_hashes,utc_now,write_json
from practice_allocation.study_io import IntegrityError,source_snapshot,read_json

def technical_costs():
    rows=[]
    for path in sorted((ROOT/'results').glob('*_technical_*/costs.json')):
        value=read_json(path)
        rows.append({'reference':reference(path),**value})
    return rows

def prepare(verification):
    out=unique(ROOT/'results','baseline')
    source_snapshot(out)
    try:
        p,states,jobs=frozen_inputs()
        vpath=Path(verification).resolve()/'VERIFIED.json';v=read_json(vpath)
        summary=read_json(checked(v['summary']))
        if v['source_hashes']!=source_hashes() or summary['status']!='passed' or summary['failed_checks']:
            raise IntegrityError('Technical gate does not certify the current frozen implementation')
        tech=technical_costs();ts=sum(r['costs']['environment_steps'] for r in tech)
        if ts>TECH_CAP:raise IntegrityError('Cumulative technical cap exceeded')
        panels=read_json(checked(v['panels']))
        baseline=read_csv(ROOT/'inputs/baseline_rows.csv')
        if len(baseline)!=2000 or {(int(r['parent']),r['stage']) for r in baseline}!={(r,t) for r in range(41011,41016) for t in ('P','S')}:
            raise IntegrityError('Certified reusable baseline coverage incomplete')
        if any(not s.get('baseline_reuse',{}).get('certified',False) for s in states):
            raise IntegrityError('Baseline re-evaluation required: prepare a bounded explicit worker before launch')
        sizes=[read_json(Path(s['checkpoint']['path'])/'checkpoint_manifest.json')['bytes'] for s in states]
        reserve_bytes=max(8*1024**3,max(sizes)*100)
        if shutil.disk_usage(out).free<reserve_bytes:raise IntegrityError('Insufficient disk for eighty lossless checkpoints')
        plan={'version':ROOT.name,'created_at':utc_now(),'source_hashes':source_hashes(),
              'protocol':p,'verification':reference(vpath),'technical_costs':tech,'technical_steps':ts,
              'jobs':jobs,'states':states,'certified_panels':panels,
              'baseline_rows':reference(ROOT/'inputs/baseline_rows.csv'),
              'new_P_S_evaluation_steps':0,'reused_P_S_rows':2000,
              'job_training_steps':32000,'job_evaluation_cap':220000,'job_environment_cap':252000,
              'research_training_cap':640000,'research_evaluation_cap':4400000,
              'total_environment_cap':TOTAL_CAP,'automatic_retries':0,
              'storage_reserve_bytes':reserve_bytes,'sequential_workers':1}
        write_json(out/'plan.json',plan);write_json(out/'plan_integrity.json',reference(out/'plan.json'))
        for name in ('jobs','completed','launches'):(out/name).mkdir()
        atomic(out/'STATUS.json',{'status':'prepared','completed':0,'failed':0,'total':20,
                               'technical_steps':ts,'updated_at':utc_now()})
        atomic(ROOT/'ACTIVE_CAMPAIGN.json',{'campaign':str(out),'created_at':utc_now()})
        print(json.dumps({'campaign':str(out),'jobs':20,'technical_steps':ts,'baseline_reused':True}),flush=True)
    except BaseException as exc:
        write_json(out/'preparation_error.json',{'error':str(exc),'traceback':traceback.format_exc(),'new_environment_steps':0})
        raise

def run_campaign(cam):
    import msvcrt
    cam=Path(cam).resolve()
    lock=(cam/'controller.lock').open('a+b')
    if lock.tell()==0:lock.write(b'0');lock.flush()
    lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    # Keep this authorized bounded campaign awake without changing the power plan.
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    plan=read_json(checked(read_json(cam/'plan_integrity.json')))
    completed=[];failed=[];actual=plan['technical_steps'];training=0;evaluation=0
    status='running';error=None;unaccounted_reservation=0
    try:
        if plan['source_hashes']!=source_hashes():raise IntegrityError('Source changed after technical certification')
        if any((cam/'jobs').glob('*/*/request.json')):
            raise IntegrityError('This campaign already has attempts; no automatic resume or retry')
        for job in plan['jobs']:
            if source_hashes()!=plan['source_hashes']:raise IntegrityError('Frozen source changed during campaign')
            # Reserve the complete path before launching, independent of early-success savings.
            if actual+252000>TOTAL_CAP:raise IntegrityError('Global cap cannot reserve next approved path')
            attempt=unique(cam/'jobs'/job['id'],'a')
            request={ 'id':job['id'],'job':job,'output':str(attempt),'source_hashes':plan['source_hashes'],
                      'environment_cap':252000,
                      'certified_panel_fingerprint':plan['certified_panels'][str(job['parent'])]['fingerprint']}
            write_json(attempt/'request.json',request)
            atomic(cam/'STATUS.json',{'status':'running','current_job':job['id'],'attempt':str(attempt),
                     'completed':len(completed),'failed':len(failed),'total':20,
                     'actual_environment_steps_finished_plus_technical':actual,
                     'training_steps_finished':training,'evaluation_steps_finished':evaluation,
                     'updated_at':utc_now()})
            with (attempt/'stdout.log').open('x',encoding='utf-8') as stdout,(attempt/'stderr.log').open('x',encoding='utf-8') as stderr:
                proc=subprocess.Popen([sys.executable,'-B',str(ROOT/'worker.py'),'--request',str(attempt/'request.json')],
                              cwd=ROOT,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
                write_json(attempt/'process.json',{'pid':proc.pid,'started_at':utc_now()})
                code=proc.wait()
            costs_path=attempt/'costs.json'
            if not costs_path.is_file():
                # An unaccounted abrupt process exit consumes its full reservation; stop integrity work.
                unaccounted_reservation=252000
                raise IntegrityError('Worker exited without cost ledger; full path reserved conservatively')
            cost=read_json(costs_path);actual+=cost['costs']['environment_steps']
            training+=cost['training_steps'];evaluation+=cost['evaluation_steps']
            if actual>TOTAL_CAP:raise IntegrityError('Actual cumulative environment cap exceeded')
            if code==0 and (attempt/'result.json').is_file():
                result=read_json(attempt/'result.json')
                if result['status']!='completed' or result['training_steps']!=32000:
                    raise IntegrityError('Worker completion contract invalid')
                write_json(cam/'completed'/(job['id']+'.json'),reference(attempt/'result.json'))
                completed.append({'id':job['id'],'result':reference(attempt/'result.json'),'costs':reference(costs_path)})
            else:
                err=read_json(attempt/'error.json') if (attempt/'error.json').is_file() else {'type':'Unknown','message':'missing error'}
                failed.append({'id':job['id'],'attempt':str(attempt),'error':err,'costs':reference(costs_path)})
                # Numerical divergence is recorded without inventing results or replacing its seed.
                numerical=err['type']=='RuntimeError' and err['message'].startswith('Non-finite SAC diagnostics:')
                if not numerical:raise IntegrityError('Technical worker failure: '+job['id']+': '+err['message'])
            atomic(cam/'STATUS.json',{'status':'running','completed':len(completed),'failed':len(failed),
                  'total':20,'actual_environment_steps':actual,'training_steps':training,
                  'evaluation_steps':evaluation,'updated_at':utc_now()})
        status='completed' if not failed else 'completed_with_numerical_failures'
        write_json(cam/'completion_summary.json',{'status':status,'completed_at':utc_now(),
                'completed':completed,'failed':failed,'planned_jobs':20,
                'training_steps':training,'evaluation_steps':evaluation,
                'technical_steps':plan['technical_steps'],'total_environment_steps':actual,
                'reused_baseline_rows':2000,'scientific_interpretation':'pending complete paired analysis; no outcome-based progression'})
        analysis_command=[sys.executable,'-B',str(ROOT/'analyze_baseline.py'),'--campaign',str(cam)]
        if failed:analysis_command.append('--allow-incomplete')
        with (cam/'analysis_stdout.log').open('x',encoding='utf-8') as stdout,(cam/'analysis_stderr.log').open('x',encoding='utf-8') as stderr:
            code=subprocess.run(analysis_command,cwd=ROOT,stdout=stdout,stderr=stderr).returncode
        if code:
            status='research_completed_analysis_failed'
        else:
            analysis_path=None
            for line in (cam/'analysis_stdout.log').read_text(encoding='utf-8').splitlines():
                try:
                    payload=json.loads(line)
                    if 'analysis_dir' in payload:analysis_path=Path(payload['analysis_dir']).resolve()
                except (json.JSONDecodeError,TypeError):continue
            if analysis_path is None or analysis_path.parent!=(ROOT/'results').resolve() or not (analysis_path/'COMPLETE.json').is_file():
                raise IntegrityError('Analysis process did not return its exact completed output directory')
            write_json(cam/'analysis_result.json',{'analysis':str(analysis_path),'summary':reference(analysis_path/'summary.json')})
            with (cam/'verify_stdout.log').open('x',encoding='utf-8') as stdout,(cam/'verify_stderr.log').open('x',encoding='utf-8') as stderr:
                code=subprocess.run([sys.executable,'-B',str(ROOT/'verify_baseline.py'),'--analysis-dir',str(analysis_path)],cwd=ROOT,stdout=stdout,stderr=stderr).returncode
            if code:status='research_completed_analysis_verification_failed'
    except BaseException as exc:
        status='stopped_integrity_failure';error={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
        write_json(cam/'controller_error.json',error);traceback.print_exc()
    finally:
        atomic(cam/'STATUS.json',{'status':status,'completed':len(completed),'failed':len(failed),'total':20,
              'actual_environment_steps':actual,'training_steps':training,'evaluation_steps':evaluation,
              'unaccounted_attempt_reserved_upper_bound':unaccounted_reservation,
              'cumulative_environment_step_upper_bound':actual+unaccounted_reservation,
              'technical_steps':plan['technical_steps'],'updated_at':utc_now(),'error':error})
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1);lock.close()
    return 1 if error else 0

if __name__=='__main__':
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('--verification',required=True)
    r=sub.add_parser('run');r.add_argument('--campaign',required=True)
    a=ap.parse_args()
    if a.command=='prepare':prepare(a.verification)
    else:raise SystemExit(run_campaign(a.campaign))
