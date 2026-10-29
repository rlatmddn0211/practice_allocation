"""Independent Decimal aggregations and SciPy rank check of the joint review."""
import argparse
import ast
import csv
import hashlib
import json
import re
import shutil
import sys
import time
import traceback
import uuid
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
import scipy
from scipy.stats import spearmanr

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
KEY=['suite','original_seed','checkpoint_step','continuation','mode']
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def rows(p):
    with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def key(r):return tuple(r[k] for k in KEY)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--review',required=True);args=ap.parse_args();review=Path(args.review)
    out=HERE/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_verify_'+uuid.uuid4().hex[:8]);out.mkdir(parents=True)
    print(str(out),flush=True);start=time.perf_counter();cpu=time.process_time();checks=[];inventory={};error=None
    def pin(p):inventory[str(Path(p).resolve())]=sha(p)
    def check(name,ok):
        checks.append({'check':name,'passed':bool(ok)})
        if not ok:raise AssertionError(name)
    def near(name,a,b):check(name,abs(float(a)-float(b))<1e-9)
    try:
        for p in HERE.iterdir():
            if p.is_file() and p.suffix in ['.py','.json','.md']:
                dest=out/'source_snapshot'/p.name;dest.parent.mkdir(exist_ok=True);shutil.copy2(p,dest);pin(p)
                if p.suffix=='.py':ast.parse(p.read_text(encoding='utf-8-sig'))
        for path,digest in read(review/'source_hashes.json').items():check('analysis source preserved',sha(HERE/path)==digest)
        for path,digest in read(review/'input_hashes.json').items():
            check('original input preserved',sha(ROOT/path)==digest);check('input snapshot exact',sha(review/'inputs'/path)==digest)
        for p in review.rglob('*'):
            if p.is_file():pin(p)
        summary=read(review/'summary.json');protocol=read(HERE/'protocol.json');check('analysis complete',summary['status']=='completed')
        check('no new learning or interaction',summary['new_environment_steps']==summary['persistent_learner_updates']==summary['clone_updates']==0)
        sources=summary['source_analyses'];expected_changes=set();primary_conditions=set()
        for r in rows(review/'comparisons.csv'):
            definition={**protocol['primary_comparisons'],**protocol['secondary_comparisons']}[r['factor']];dataset,method,baseline=definition
            raw=rows(ROOT/sources[dataset]/'selection_rows.csv');lookup={(key(x),x['method']):x for x in raw}
            chosen=[x for x in raw if x['method']==method and x['mode']==r['mode']];check('36 original decisions',len(chosen)==36)
            den=sum(Decimal(x['weight']) for x in chosen);inc=Decimal(0);risk=Decimal(0);better=worse=changed=0
            for x in chosen:
                b=lookup[key(x),baseline];delta=Decimal(x['score_pp'])-Decimal(b['score_pp']);inc+=Decimal(x['weight'])*delta
                risk+=Decimal(x['weight'])*(Decimal(b['max_task_drop_pp'])-Decimal(x['max_task_drop_pp']))
                better+=delta>Decimal('0.000000001');worse+=delta<Decimal('-0.000000001')
                if x['selected_allocation']!=b['selected_allocation']:
                    changed+=1;expected_changes.add((r['factor'],*key(x)))
                    if r['factor'] in protocol['primary_comparisons'] and r['mode']=='same_repeat':primary_conditions.add(key(x)[:4])
            near('independent Decimal weighted increment',inc/den,r['increment_pp']);near('independent task loss reduction',risk/den,r['mean_worst_task_drop_reduction_pp'])
            check('all positive negative changes counted',(changed,better,worse)==tuple(int(r[k]) for k in ['changed_choices','better_changes','worse_changes']))
        changed=rows(review/'all_changed_choices.csv')
        check('no omitted or added changed decision',expected_changes=={(r['factor'],*key(r)) for r in changed})
        check('union across own baselines',len(primary_conditions)==summary['results']['primary_changed_choice_union_count']==7)
        features=rows(ROOT/sources['F06']/'features.csv')
        for result in rows(review/'critic_gap_descriptive_correlations.csv'):
            rr=features
            if result['split']=='group':rr=[r for r in rr if r['suite']+str(int(r['checkpoint_step'])//1000)==result['part']]
            if result['split']=='original_seed':rr=[r for r in rr if r['original_seed']==result['part']]
            a=[float(r['critic_total20_train'])-float(r['critic_total20']) for r in rr];b=[abs(float(r['O40'])-float(r['D20']))*100 for r in rr]
            near('independent SciPy rank association',spearmanr(a,b).statistic,result['spearman']);check('descriptive sample count',len(rr)==int(result['dependent_branch_rows']))
        common=rows(ROOT/sources['F01']/'features.csv');bycontext={}
        for r in common:bycontext.setdefault(tuple(r[k] for k in KEY[:4]),[]).append(r)
        selected=rows(ROOT/sources['F01']/'selection_rows.csv')
        for r in rows(review/'observed_selection_headroom.csv'):
            ss=[x for x in selected if x['mode']==r['mode'] and x['method']==r['method'] and (r['group']=='all' or x['suite']+str(int(x['checkpoint_step'])//1000)==r['group'])]
            den=sum(Decimal(x['weight']) for x in ss)
            top=sum(Decimal(x['weight'])*max(Decimal(y['O40'])*100 for y in bycontext[key(x)[:4]]) for x in ss)/den
            near('hindsight top independently from five frozen branches',top,r['observed_hindsight_best_pp'])
        for doc in [HERE/'README.md',HERE/'report_ko.md']:
            for target in re.findall(r'\]\(([^)]+)\)',doc.read_text(encoding='utf-8')):
                if not re.match(r'https?://|#',target):check('local report citation exists',(doc.parent/target.split('#')[0]).exists())
        active=read(ROOT/'33_remaining_factor_queue_v1/ACTIVE_CAMPAIGN.json');cam=Path(active['campaign']);plan=read(cam/'plan.json')
        for stage,directory in [('F05','31_fixed_horizon_alignment_v1'),('F08','32_dose_order_intervention_v1')]:
            for name,digest in plan['stage_hashes'][stage].items():check('ongoing experimental code unchanged',sha(ROOT/directory/name)==digest)
        pin(HERE/'protocol.json');pin(ROOT/'README.md');pin(ROOT/'.gitattributes')
    except BaseException:error=traceback.format_exc()
    result={'status':'failed' if error else 'completed','review':str(review.resolve()),'checks':checks,
            'checks_passed':sum(c['passed'] for c in checks),'checks_failed':sum(not c['passed'] for c in checks),
            'wall_seconds':time.perf_counter()-start,'cpu_seconds':time.process_time()-cpu,'new_environment_steps':0,'learner_updates':0,
            'runtime':{'python':sys.version,'scipy':scipy.__version__},'error':error}
    (out/'artifact_hashes.json').write_text(json.dumps(inventory,indent=2),encoding='utf-8')
    (out/'summary.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    if error:raise RuntimeError(error)
    print(json.dumps({k:result[k] for k in ['status','checks_passed','checks_failed','wall_seconds']}),flush=True)

if __name__=='__main__':main()
