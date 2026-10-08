"""Real reduced queue with controller crash, adoption, locking and replay tests."""
from __future__ import annotations
import json
import argparse
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
import psutil
from campaign import ROOT, REPO, STAGES, P0, make_plan, ref, checkpoint, stamp, read, write, sha


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--storage-root',type=Path)
    args=parser.parse_args()
    storage=Path(args.storage_root or REPO).resolve()
    directory=storage/ROOT.name/'results'/(stamp()+'_queue_verification_'+uuid.uuid4().hex[:6])
    directory.mkdir(parents=True,exist_ok=False)
    (directory/'completed').mkdir()
    for source in ROOT.glob('*.py'):
        target=directory/'source_snapshot'/source.name
        target.parent.mkdir(exist_ok=True)
        shutil.copy2(source,target)
    plan=make_plan(technical=True,storage_root=storage)
    jobs=[]
    def add(job_id,stage,suite='A',seed=11,**fields):
        jobs.append(dict(id=job_id,stage=stage,suite=suite,original_seed=seed,**fields))
        return job_id
    bank=add('test_E0_bank','E0',seed=901,kind='bank',bank_seed=95951)
    add('test_E0_parent_eval','E0',seed=901,kind='evaluate',parent=checkpoint(P0/'checkpoints/step_000200000'),bank=ref(bank,'bank'),bank_kind='diagnostic',role='public',checkpoint_step=200000)
    init=add('test_E1_init','E1',kind='init')
    train=add('test_E1_train','E1',kind='train',parent=ref(init,'checkpoint'),start_step=0,steps=4000,allocation='U')
    public=add('test_E1_public','E1',kind='evaluate',parent=ref(train,'checkpoint'),bank=ref(bank,'bank'),bank_kind='diagnostic',role='public',checkpoint_step=4000)
    add('test_E1_rules','E1',kind='rules',current_public=ref(public,'result_ref'),previous_public=ref(public,'result_ref'),elapsed=4000,checkpoint_step=4000)
    donor=add('test_E2_donor','E2',kind='train',parent=ref(train,'checkpoint'),start_step=4000,steps=4000,allocation='DC_plus_WO_minus',start_branch=True,continuation_label=2299,continuation_rng_seed=81233,checkpoint_step=4000,horizon=4000)
    add('test_E2_eval','E2',kind='evaluate',parent=ref(donor,'checkpoint'),bank=ref(bank,'bank'),bank_kind='outcome',role='branch',checkpoint_step=4000,horizon=4000,allocation='DC_plus_WO_minus',continuation_label=2299)
    bankB=add('test_E3_B_bank','E3','B',kind='bank',bank_seed=95952)
    initB=add('test_E3_B_init','E3','B',kind='init')
    trainB=add('test_E3_B_train','E3','B',kind='train',parent=ref(initB,'checkpoint'),start_step=0,steps=4000,allocation='U')
    add('test_E3_B_eval','E3','B',kind='evaluate',parent=ref(trainB,'checkpoint'),bank=ref(bankB,'bank'),bank_kind='outcome',role='public',checkpoint_step=4000)
    plan['jobs']=jobs
    write(directory/'plan.json',plan)
    write(directory/'plan_integrity.json',{'sha256':sha(directory/'plan.json')})
    commands=[sys.executable,'-u',str(ROOT/'campaign.py'),'run','--campaign',str(directory)]
    controller=None
    logs=[]
    checks=[]
    def launch(name):
        log=(directory/(name+'.log')).open('xb')
        logs.append(log)
        return subprocess.Popen(commands,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    def wait_state(predicate, timeout=240):
        start=time.monotonic()
        while time.monotonic()-start<timeout:
            state=read(directory/'STATUS.json') if (directory/'STATUS.json').exists() else {}
            if state.get('state') in ('failed','integrity_failed'):
                raise RuntimeError(json.dumps(state))
            if predicate(state):
                return state
            time.sleep(2)
        raise TimeoutError('Queue test did not reach the required state.')
    try:
        controller=launch('controller_first')
        state=wait_state(lambda s:s.get('job')=='test_E1_train')
        duplicate=launch('controller_duplicate')
        assert duplicate.wait(timeout=30)==0
        checks.append('Second controller exits without launching a duplicate job')
        marker=directory/'completed/test_E1_init.json'
        digest_before=sha(marker)
        worker_pid=state['worker_pid']
        assert psutil.pid_exists(worker_pid)
        controller.terminate()
        controller.wait(timeout=30)
        assert psutil.pid_exists(worker_pid)
        controller=launch('controller_restarted')
        state=wait_state(lambda s:s.get('adopted_worker') is True or s.get('completed_jobs',0)>=4)
        checks.append('Interrupted controller adopts existing worker and retains completed job')
        assert sha(marker)==digest_before
        donor_state=wait_state(lambda s:s.get('job')=='test_E2_donor')
        failed_output=Path(donor_state['output'])
        psutil.Process(donor_state['worker_pid']).terminate()
        checks.append('Intentionally interrupted a worker to exercise a fresh retry directory')
        wait_state(lambda s:s.get('state')=='completed',timeout=900)
        assert controller.wait(timeout=30)==0
        for job in jobs:
            attempts=list((directory/'attempts'/job['id']).glob('*.json'))
            assert len(attempts)==(2 if job['id']=='test_E2_donor' else 1),job['id']
        assert failed_output.exists() and (failed_output/'request.json').exists()
        checks.append('Completed jobs run once; interrupted E2 worker retries once and failed output is retained')
        result=read(read(directory/'completed/test_E2_donor.json')['result_ref']['path'])
        assert result['collected_this_job']=={'DO':1000,'DC':1500,'WO':500,'WC':1000}
        checks.append('E2 imports E1 full state and exchanges donor counts with target counts fixed')
        assert subprocess.run(commands,capture_output=True,timeout=30).returncode==0
        checks.append('Completed campaign exits without any additional work')
        write(directory/'verification.json',{'passed':True,'checks':checks,'technical_only':True,'planned_smoke_training_steps':12000,'planned_smoke_evaluation_episodes':32})
        print(json.dumps({'passed':True,'directory':str(directory),'checks':checks}),flush=True)
    except BaseException as exc:
        write(directory/'verification.json',{'passed':False,'checks':checks,'error':str(exc),'technical_only':True})
        raise
    finally:
        for stream in logs:
            stream.close()


if __name__=='__main__':
    main()
