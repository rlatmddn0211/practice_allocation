"""Read-only validation and disposable import of v42's completed prefix."""
import json
import os
import shutil
import sys
import time
import traceback
import uuid
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.environ['PRACTICE_SUITE']='B'
from campaign import read,write,reference,import_predecessor,resolve,sha
from practice_allocation.study_io import source_snapshot


def main():
    out=ROOT/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_verify_handoff_')+uuid.uuid4().hex[:8]);out.mkdir(parents=True)
    source_snapshot(out);shutil.copy2(__file__,out/'verification_script.py');checks=[];started=time.perf_counter();inputs={}
    def check(name,value):
        checks.append({'name':name,'passed':bool(value)})
        if not value:raise AssertionError(name)
    def track(path):inputs[str(path)]=sha(path)
    try:
        old=Path(read(ROOT/'migration/handoff_intent.json')['predecessor_campaign'])
        track(old/'plan.json');track(old/'plan_integrity.json')
        plan=read(old/'plan.json',read(old/'plan_integrity.json')['sha256']);old_markers=sorted(p.name for p in (old/'completed').glob('*.json'))
        check('no parent or branch outcomes exist',not list((old/'jobs').rglob('evaluation_episodes.csv')))
        # Both OS locks must be free before reusing a finished worker's result.
        import msvcrt
        for name in ('controller.lock','worker.lock'):
            with (old/name).open('r+b') as lock:
                lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
            check('predecessor lock is free '+name,True)
        mock=out/'import';mock.mkdir();(mock/'completed').mkdir()
        imported=import_predecessor(old,mock,plan['jobs'])
        check('all 12 completed tasks retained',len(imported)==12)
        check('120k training reused',sum(j['training_steps'] for j in imported)==120000)
        check('5 evaluation banks reused',sum(j['id'].endswith('_bank') for j in imported)==5)
        check('orphan completion recovered',any(j['id']=='B_s41011_pretrain_120000' for j in imported))
        jobs={j['id']:j for j in plan['jobs']}
        for item in imported:
            attempt=Path(item['attempt']);expected=resolve(jobs[item['id']],old);request=read(attempt/'request.json')
            check('all resolved request inputs match '+item['id'],all(request[k]==v for k,v in expected.items()))
            for name,digest in plan['source_hashes'].items():
                check('source snapshot '+item['id']+' '+name,sha(attempt/'source_snapshot'/name)==digest)
            for name in ('request.json','result.json','costs.json','source_hashes.json'):track(attempt/name)
        bad=out/'changed_job_rejection';bad.mkdir();(bad/'completed').mkdir()
        changed=[{**plan['jobs'][0],'original_seed':-1}]
        rejected=False
        try:import_predecessor(old,bad,changed)
        except RuntimeError as exc:rejected='Cannot import changed job' in str(exc)
        check('changed job is rejected',rejected)
        check('old completed markers untouched',old_markers==sorted(p.name for p in (old/'completed').glob('*.json')))
        for name,digest in inputs.items():check('input unchanged '+name,sha(name)==digest)
        summary={'status':'completed','scientific_evidence':False,'inherited_training_steps':120000,'imported_jobs':len(imported)}
    except BaseException:
        summary={'status':'failed','scientific_evidence':False,'traceback':traceback.format_exc()};traceback.print_exc()
    summary.update(new_environment_steps=0,new_learner_updates=0,wall_seconds=time.perf_counter()-started,
                   checks_passed=sum(c['passed'] for c in checks),checks_failed=sum(not c['passed'] for c in checks))
    write(out/'checks.json',checks);write(out/'input_hashes.json',inputs);write(out/'summary.json',summary)
    print(str(out));print(json.dumps(summary,indent=2))
    return 0 if summary['status']=='completed' else 1


if __name__=='__main__':raise SystemExit(main())
