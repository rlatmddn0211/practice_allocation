"""Environment-free audit of the authorized intervention and deferred queue."""
import hashlib
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from deferred_queue import (source_hashes,source_files,sha,utc,exclusive_json,validate_predecessor,Pending)

def main():
    stamp=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())
    import uuid
    out=ROOT/'results'/(stamp+'_static_'+uuid.uuid4().hex[:8]);(out/'source_snapshot').mkdir(parents=True)
    hashes=source_hashes(ROOT)
    import shutil
    for name,h in hashes.items():
        dest=out/'source_snapshot'/(h[:20]+Path(name).suffix)
        if not dest.exists():shutil.copy2(ROOT/name,dest)
    exclusive_json(out/'source_hashes.json',hashes)
    checks=[];started=time.perf_counter()
    def check(name,ok):
        checks.append({'name':name,'passed':bool(ok)})
        if not ok:raise ValueError(name)
    def child(name,command):
        with (out/(name+'_stdout.log')).open('x',encoding='utf-8') as stdout,(out/(name+'_stderr.log')).open('x',encoding='utf-8') as stderr:
            env={**os.environ,'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1',
                 'PYTHONDONTWRITEBYTECODE':'1','PYTHONIOENCODING':'utf-8'}
            code=subprocess.run([sys.executable,'-B',*command],cwd=ROOT,env=env,stdout=stdout,stderr=stderr).returncode
        check(name+'_exit_zero',code==0)
    try:
        for name in hashes:
            if name.endswith('.py'):compile((ROOT/name).read_text(encoding='utf-8-sig'),name,'exec')
        check('all_python_sources_compile',True)
        read=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'))
        p=read(ROOT/'protocol.json');jobs=read(ROOT/'inputs/jobs.json');states=read(ROOT/'inputs/state_manifest.json')
        check('authorized_40_unique_jobs',len(jobs)==len({j['id'] for j in jobs})==40)
        check('complete_parent_arm_future_grid',{(j['parent'],j['arm'],j['future']) for j in jobs}=={(p,a,f) for p in range(41011,41016) for a in 'ABCD' for f in (1,2)})
        check('BP625_only_and_prefix4201',all(j['condition']=='dose625' and j['prefix_continuation']==4201 for j in jobs))
        check('budget_identity',40*(32000+220000)+20000==p['total_environment_cap']==10100000)
        check('ten_fresh_roots',len({j['root_seed'] for j in jobs})==10)
        audit=read(ROOT/'inputs/seed_collision_audit.json')
        check('no_prior_root_seed_collision',not set(audit['new_roots'])&set(audit['historical_root_seeds']))
        for key,h in p['input_hashes'].items():check('input_'+key,sha(ROOT/key)==h)
        for key,h in p['critical_source_hashes'].items():check('unchanged_original_learner_'+key,sha(ROOT/key)==h)
        check('fixed_states_five',len(states)==5 and [s['parent'] for s in states]==list(range(41011,41016)))
        for s in states:
            check('exact_source_checkpoint_'+str(s['parent']),sha(Path(s['checkpoint']['path'])/'checkpoint_manifest.json')==s['checkpoint']['manifest_sha256'])
            for key in ('selected_cases','episode_labels','bank'):
                check(str(s['parent'])+'_'+key,sha(s[key]['path'])==s[key]['sha256'])
        upstream=read(ROOT/'inputs/upstream_campaign.json')
        try:
            receipt=validate_predecessor(upstream,allow_known_repair=bool(upstream.get('analysis_repair')))
            exclusive_json(out/'upstream_completed_receipt.json',receipt)
        except Pending as exc:exclusive_json(out/'upstream_pending.json',{'reason':str(exc),'expected':True})
        child('queue_unit_tests',['test_deferred_queue.py'])
        child('retention_unit_tests',['test_retention_units.py'])
        child('analysis_self_test',['analyze_intervention.py','--self-test'])
        child('independent_analysis_self_test',['verify_intervention_analysis.py','--self-test'])
        check('source_unchanged_during_static_check',source_hashes(ROOT)==hashes)
        exclusive_json(out/'summary.json',{'status':'passed','checks':checks,'new_environment_steps':0,
            'research_SAC_updates':0,'wall_seconds':time.perf_counter()-started,'created_at':utc()})
        exclusive_json(out/'COMPLETE.json',{'status':'completed','summary_sha256':sha(out/'summary.json')})
    except BaseException:
        exclusive_json(out/'FAILED.json',{'checks':checks,'traceback':traceback.format_exc(),'new_environment_steps':0})
        raise
    print(json.dumps({'static_dir':str(out),'passed':True,'checks':len(checks),'new_environment_steps':0}))
if __name__=='__main__':main()
