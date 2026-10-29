"""Synthetic end-to-end CSV tests. No policy/environment runs and no scientific evidence."""
import csv
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
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT)); os.environ['PRACTICE_SUITE']='B'
from practice_allocation.core import file_sha256,write_json,source_hashes
from practice_allocation.study_io import source_snapshot


def main():
    out=ROOT/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_verify_analysis_')+uuid.uuid4().hex[:8]); out.mkdir(parents=True)
    source_snapshot(out); shutil.copy2(__file__,out/'verification_script.py'); started=time.perf_counter(); checks=[]
    def check(name,value):
        checks.append({'name':name,'passed':bool(value)})
        if not value: raise AssertionError(name)
    status='completed'; error=None
    try:
        parents=[41011,41012,41013,41014,41015]; repeats=[4201,4202]; conditions=['dose625','alternate4k','mixture']
        for scenario in ('constant_fixed','repeatable_heterogeneity'):
            cam=out/scenario; cam.mkdir(); (cam/'completed').mkdir(); jobs=[]
            for p in parents:
                for rep,condition in [(None,'parent')]+[(r,c) for r in repeats for c in conditions]:
                    jid=f'{p}_{rep}_{condition}'; folder=cam/jid; folder.mkdir()
                    job={'id':jid,'kind':'evaluate','original_seed':p,'role':'parent' if rep is None else 'branch'}
                    if rep is not None: job.update(continuation=rep,condition=condition)
                    good='alternate4k' if scenario=='repeatable_heterogeneity' and p in parents[:2] else 'dose625'
                    count=50 if condition=='parent' else 75 if condition==good else 40 if condition=='mixture' else 50
                    path=folder/'episodes.csv'
                    with path.open('x',encoding='utf-8',newline='') as f:
                        w=csv.DictWriter(f,fieldnames=['task','episode_index','success']); w.writeheader()
                        for task in ('DO','DC','PU','BP'):
                            for i in range(100):
                                # Distribute successes across the two prespecified halves.
                                success=(i%50)<(count//2+(1 if i<50 and count%2 else 0))
                                w.writerow({'task':task,'episode_index':i,'success':int(success)})
                    result={'episodes_path':str(path),'episodes_sha256':file_sha256(path),'evaluation':{'macro_success':count/100}}
                    write_json(folder/'result.json',result)
                    write_json(cam/'completed'/(jid+'.json'),{'result_ref':{'path':str(folder/'result.json'),'sha256':file_sha256(folder/'result.json')}})
                    jobs.append(job)
            write_json(cam/'plan.json',{'technical_smoke':False,'synthetic_fixture_only':True,'jobs':jobs})
            write_json(cam/'plan_integrity.json',{'sha256':file_sha256(cam/'plan.json')})
            with (cam/'stdout.log').open('x',encoding='utf-8') as stdout,(cam/'stderr.log').open('x',encoding='utf-8') as stderr:
                code=subprocess.call([sys.executable,'-B',str(ROOT/'analyze.py'),'--campaign',str(cam),'--output',str(cam/'analysis')],stdout=stdout,stderr=stderr)
            check('analysis CLI completes '+scenario,code==0)
            summary=json.loads((cam/'analysis/summary.json').read_text(encoding='utf-8'))
            check('gate '+scenario,summary['stage2_investment_gate_pass']==(scenario=='repeatable_heterogeneity'))
            gains=summary['parent_choice_gains']['vs_BP_pp']
            check('independent expected choice gain '+scenario,gains==([25.0,25.0,0.0,0.0,0.0] if scenario=='repeatable_heterogeneity' else [0.0]*5))
            with (cam/'analysis/policy_scores.csv').open(encoding='utf-8-sig',newline='') as f:
                check('all 35 policies '+scenario,len(list(csv.DictReader(f)))==35)
            with (cam/'analysis/choice_crossfit.csv').open(encoding='utf-8-sig',newline='') as f:
                rows=list(csv.DictReader(f)); check('20 crossed decisions '+scenario,len(rows)==20)
        check('source remained unchanged',json.loads((out/'source_hashes.json').read_text(encoding='utf-8'))==source_hashes())
    except BaseException:
        status='failed'; error=traceback.format_exc(); traceback.print_exc()
    write_json(out/'checks.json',checks)
    summary={'status':status,'scientific_evidence':False,'synthetic_only':True,'new_environment_steps':0,
             'new_learner_updates':0,'checks_passed':sum(x['passed'] for x in checks),'checks_failed':sum(not x['passed'] for x in checks),
             'verification_script_sha256':file_sha256(out/'verification_script.py'),'wall_seconds':time.perf_counter()-started,'error':error}
    write_json(out/'summary.json',summary); print(str(out)); print(json.dumps(summary,indent=2))
    return 0 if status=='completed' else 1


if __name__=='__main__': raise SystemExit(main())
