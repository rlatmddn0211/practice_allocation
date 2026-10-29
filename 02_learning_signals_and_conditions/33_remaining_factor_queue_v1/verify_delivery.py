"""Audit immutable evidence, launch state and scope without changing experiment code."""
import ast
import csv
import json
import re
import shutil
import sys
import time
import traceback
import uuid
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import campaign

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent

def main():
    out=HERE/'results'/(campaign.stamp()+'_verify_delivery_'+uuid.uuid4().hex[:8]);out.mkdir(parents=True)
    print(str(out),flush=True);started=time.perf_counter();cpu=time.process_time();checks=[];inventory={};error=None;details={}
    def keep(path):
        path=Path(path);key=path.relative_to(ROOT).as_posix();inventory[key]=campaign.sha(path)
    def check(name,ok):
        checks.append({'check':name,'passed':bool(ok)})
        if not ok:raise AssertionError(name)
    def read(path,expected=None):
        keep(path);return campaign.read(path,expected)
    try:
        dirs=[ROOT/name for name in ['30_exposure_experience_screening_v1','31_fixed_horizon_alignment_v1','32_dose_order_intervention_v1','33_remaining_factor_queue_v1']]
        sources=[];docs=[ROOT/'README.md',ROOT/'AGENTS.md']
        for d in dirs:
            for p in d.rglob('*'):
                if not p.is_file() or 'results' in p.relative_to(d).parts or '__pycache__' in p.parts:continue
                if p.suffix in ['.py','.ps1','.json','.md','.txt']:
                    keep(p)
                    if p.suffix=='.py':sources.append(p)
                    if p.suffix=='.md':docs.append(p)
                    if p.suffix in ['.py','.ps1','.json','.txt']:
                        dest=out/'source_snapshot'/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
        for p in sources:
            tree=ast.parse(p.read_text(encoding='utf-8-sig'),filename=str(p))
            for node in ast.walk(tree):
                if isinstance(node,(ast.Import,ast.ImportFrom)):
                    names=[x.name for x in node.names] if isinstance(node,ast.Import) else [node.module or '']
                    check('no cross-version code import '+p.name,all(not re.match(r'\d\d_',name) for name in names))
        for p in docs:
            keep(p)
            for target in re.findall(r'\]\(([^)]+)\)',p.read_text(encoding='utf-8-sig')):
                if re.match(r'https?://|app://|#',target):continue
                target=target.split('#')[0]
                check('document link '+p.name+' '+target,(p.parent/target).exists())
        keep(ROOT/'.gitattributes');keep(ROOT/'.gitignore')
        for name,path in campaign.OFFLINE.items():
            s=read(path/'summary.json');check('offline '+name+' completed',s['status']=='completed')
            for p in path.rglob('*'):
                if p.is_file():keep(p)
        offline=read(campaign.OFFLINE['analysis']/'summary.json')
        for factor,expected in [('F02',0.),('F03',-0.3611111111111111)]:
            r=offline['candidate_decisions'][factor]
            check('reported effect '+factor,abs(r['increment_pp']-expected)<1e-9 and not r['operational_screen_pass'])
        failed=[];preflight_costs=[]
        for d in dirs[1:3]:
            for p in sorted((d/'results').glob('*verify_implementation*/summary.json')):
                s=read(p);preflight_costs.append({'path':str(p),**{k:s[k] for k in ['status','costs','wall_seconds','cpu_seconds']}})
                if s['status']=='failed':failed.append(str(p.parent))
                for f in p.parent.rglob('*'):
                    if f.is_file() and f.suffix not in ['.npz','.xz','.zip','.pkl']:keep(f)
        check('both failed numerical checks preserved',len(failed)==2)
        ready=campaign.validate_readiness();check('four successful real-model gates plus offline',len(ready)==7)
        cam=Path(read(HERE/'ACTIVE_CAMPAIGN.json')['campaign'])
        plan=read(cam/'plan.json',read(cam/'plan_integrity.json')['sha256'])
        check('full run and source freeze',not plan['technical_smoke'] and plan['controller_sha256']==campaign.sha(HERE/'campaign.py'))
        for stage,d in campaign.STAGES.items():check('unchanged stage '+stage,campaign.stage_hashes(d)==plan['stage_hashes'][stage])
        counts=Counter(j['stage']+':'+j['kind'] for j in plan['jobs'])
        check('scope192 measurements72 branches',counts['F05:measure']==192 and counts['F08:train']==144 and counts['F08:evaluate']==78 and len(plan['jobs'])==424)
        check('planned exact budgets',plan['planned_training_steps']==2880000 and plan['planned_F05_environment_steps']==10752000)
        train=[j for j in plan['jobs'] if j['stage']=='F08' and j['kind']=='train']
        check('one original and three continuation seeds',set(j['original_seed'] for j in train)=={12} and set(j['continuation'] for j in train)=={3801,3802,3803})
        check('all technical gates recorded',len(read(cam/'readiness.json'))==9)
        for p in cam.iterdir():
            if p.is_file() and p.name not in ['STATUS.json','events.jsonl','controller.lock','worker.lock']:keep(p)
        technical=Path(read(HERE/'ACTIVE_TECHNICAL.json')['campaign']);ts=read(technical/'summary.json')
        check('seven end-to-end jobs complete',ts['status']=='completed' and ts['technical_smoke'] and ts['jobs_completed']==7)
        check('technical costs retained',ts['actual_environment_steps_including_failed_attempts']==10866 and ts['actual_train_iterations_including_failed_attempts']==1000)
        read(technical/'COMPLETE.json')
        math=read(HERE/'ANALYSIS_PREFLIGHT.json');ms=read(math['path'],math['sha256'])
        check('analysis preflight completed',ms['status']=='completed' and len(ms['checks'])==23)
        banksets=[set(),set(),set()];models=[]
        for p in (cam/'completed').glob('*.json'):
            mark=read(p);r=read(mark['result_ref']['path'],mark['result_ref']['sha256'])
            if r.get('bank'):
                bank=read(r['bank']['path'],r['bank']['sha256'])
                for entries in bank.values():
                    for e in entries:
                        for values,key in zip(banksets,['initial_state_hash','task_parameter_hash','seed']):
                            check('new banks disjoint '+key,e[key] not in values);values.add(e[key])
            if r.get('factor')=='F05_alignment' and r.get('kind')=='measure':
                check('full immutable diagnostic',r['learner_unchanged'] and r['new_environment_steps']==56000)
                receipt=read(Path(mark['attempt'])/'trace_verified.json');vr=read(receipt['path'],receipt['sha256'])
                check('full trace audit completed',vr['status']=='completed');models.append(r['original_id'])
        check('at least one full measurement and trace audit',len(models)>=1)
        status=campaign.read(cam/'STATUS.json');(out/'observed_status.json').write_text(json.dumps(status,indent=2),encoding='utf-8')
        age=(datetime.now(timezone.utc)-datetime.fromisoformat(status.get('updated_at',status.get('completed_at')))).total_seconds()
        check('queue making progress',status['state']=='running' and age<60 and not (cam/'STOPPED.json').exists())
        launch=sorted((cam/'launches').glob('*/launch.json'))[-1];lr=read(launch)
        check('launched controller alive',campaign.process_identity(lr['pid']) is not None)
        details={'campaign':str(cam),'jobs':dict(counts),'observed_completed_models':models,'technical_preflight_costs':preflight_costs,
                 'preflight_environment_steps_including_failures':sum(r['costs']['environment_steps'] for r in preflight_costs)+10866,
                 'preflight_updates_including_failures':sum(r['costs']['train_iterations'] for r in preflight_costs)+1000,
                 'first_powershell_launch_failure':'Default script policy rejected direct .ps1. Started with process-only ExecutionPolicy Bypass; system policy unchanged.'}
    except BaseException:error=traceback.format_exc()
    with (out/'artifact_manifest.csv').open('x',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['path','sha256']);w.writeheader();w.writerows({'path':k,'sha256':v} for k,v in sorted(inventory.items()))
    summary={'status':'failed' if error else 'completed','scientific_effect_verified':False,'checks_passed':sum(r['passed'] for r in checks),
             'checks_failed':sum(not r['passed'] for r in checks),'checks':checks,'details':details,'source_artifact_count':len(inventory),
             'new_environment_steps':0,'train_iterations':0,'wall_seconds':time.perf_counter()-started,'cpu_seconds':time.process_time()-cpu,
             'python':sys.version,'error':error}
    (out/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
    if error:raise RuntimeError(error)
    print(json.dumps({k:summary[k] for k in ['status','checks_passed','checks_failed','source_artifact_count']},indent=2),flush=True)

if __name__=='__main__':main()
