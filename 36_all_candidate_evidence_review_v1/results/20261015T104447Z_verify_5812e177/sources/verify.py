"""Verify review arithmetic and F05 raw diagnostic summaries without importing analysis code."""
import csv
import hashlib
import json
import math
import re
import statistics
import sys
import time
import traceback
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent


def main():
    start,cpu=time.perf_counter(),time.process_time()
    src=Path(sys.argv[1]).resolve()
    out=HERE/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_verify_'+uuid.uuid4().hex[:8])
    out.mkdir(parents=True);print(out,flush=True)
    checks=[];result={'status':'failed','review':str(src)}
    def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
    def rows(p):
        with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
    def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    def check(label,ok):
        checks.append({'check':label,'passed':bool(ok)})
        if not ok:raise AssertionError(label)
    def near(label,a,b):check(label,abs(float(a)-float(b))<1e-9)
    def save(p,obj):
        with p.open('x',encoding='utf-8') as f:json.dump(obj,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n')
    (out/'sources').mkdir()
    for p in [*HERE.glob('*.py'),HERE/'protocol.json']:(out/'sources'/p.name).write_bytes(p.read_bytes())
    save(out/'source_hashes.json',{p.name:digest(p) for p in [*HERE.glob('*.py'),HERE/'protocol.json']})
    save(out/'runtime.json',{'python':sys.version,'executable':sys.executable,'argv':sys.argv,'dependencies':'Python standard library only'})
    try:
        summary=load(src/'summary.json');protocol=load(HERE/'protocol.json');inputs=load(src/'input_hashes.json')
        check('review completed',summary['status']=='completed' and summary['checks_failed']==0)
        for name,h in load(src/'source_hashes.json').items():
            check('actually run source '+name,digest(src/'sources'/name)==h)
            check('source unchanged '+name,digest(HERE/name)==h)
        for name,h in inputs.items():
            check('retained input '+name,digest(src/'inputs'/(h+Path(name).suffix))==h)
            if name.endswith('/STATUS.json'):continue
            check('original frozen input '+name,digest(ROOT/name)==h)
        comp=rows(src/'comparisons.csv');changes=rows(src/'all_changed_choices.csv')
        key=lambda r:tuple(r[k] for k in ['suite','original_seed','checkpoint_step','continuation','mode'])
        bysource={}
        for name,d in protocol['sources'].items():
            if name=='F07':continue
            bysource[name]=rows(ROOT/d/'selection_rows.csv')
        for c in comp:
            selected=[r for r in bysource[c['source']] if r['mode']==c['mode'] and r['method']==c['method']]
            base={key(r):r for r in bysource[c['source']] if r['method']==c['comparator']}
            total=Decimal(0);weight=Decimal(0);changed=0;gains=0;losses=0
            actual_events=[]
            for r in selected:
                b=base[key(r)];delta=Decimal(r['score_pp'])-Decimal(b['score_pp']);w=Decimal(r['weight'])
                total+=w*delta;weight+=w
                if r['selected_allocation']!=b['selected_allocation']:
                    changed+=1;actual_events.append(key(r))
                    gains+=delta>Decimal('1e-9');losses+=delta<Decimal('-1e-9')
            near('independent Decimal increment '+c['factor']+c['mode'],total/weight,c['increment_pp'])
            near('changed count '+c['factor']+c['mode'],changed,c['changed_choices'])
            near('positive count '+c['factor']+c['mode'],gains,c['positive_changes'])
            near('negative count '+c['factor']+c['mode'],losses,c['negative_changes'])
            output_events=[key(r) for r in changes if r['factor']==c['factor'] and r['mode']==c['mode']]
            check('all and only changed events '+c['factor']+c['mode'],sorted(actual_events)==sorted(output_events))
        for mode in ['same_repeat','cross_repeat']:
            eventkeys={key(r) for r in changes if r['role']=='primary' and r['mode']==mode}
            near('primary event union '+mode,len(eventkeys),summary['primary_changed_cell_union'][mode])

        # Recalculate F05 held-seed calibration from all raw episodes, independently of features.py.
        diag=[];mc_by=defaultdict(list)
        receipts=rows(src/'F05_measurement_receipts.csv')
        for rec in receipts:
            rr=load(Path(rec['result']));seed=int(rr['original_seed'])
            episodes=rows(Path(rr['episodes_path']));mcs=rows(Path(rr['mc_path']))
            check('80 raw deterministic episodes '+rr['original_id'],len(episodes)==80)
            check('32 raw MC episodes '+rr['original_id'],len(mcs)==32)
            for r in episodes:diag.append((seed,rr['original_id'],r['task'],float(r['return500']),float(r['success'])))
            for r in mcs:mc_by[rr['original_id'],r['task']].append(r)
        near('15360 deterministic episodes',len(diag),15360)
        near('6144 MC episodes',sum(len(v) for v in mc_by.values()),6144)
        calpath=ROOT/protocol['sources']['F05_alignment']/'calibrations.json'
        cal=load(calpath);calrows=rows(src/'return_calibration_review.csv');brier_rows=[]
        for r in calrows:
            held=int(r['held_original_seed']);task=r['task'];ff=cal[str(held)][task]
            train=[x for x in diag if x[0]!=held and x[2]==task];test=[x for x in diag if x[0]==held and x[2]==task]
            check('no held seed calibration IDs '+str(held)+task,set(ff['train_ids'])=={x[1] for x in train})
            mu=statistics.fmean(x[3] for x in train);var=statistics.fmean((x[3]-mu)**2 for x in train)
            sd=math.sqrt(var) if var>1e-24 else 1.;intercept=statistics.fmean(x[4] for x in train)
            cov=statistics.fmean((x[3]-mu)*(x[4]-intercept) for x in train)
            # Univariate penalized normal equation expressed in original return units.
            slope=(cov/sd)/(1+var/(sd*sd))
            for field,value in [('mean',mu),('scale',sd),('intercept',intercept),('slope',slope)]:near('calibration '+str(held)+task+field,value,ff[field])
            vals=[max(0.,min(1.,intercept+slope*(x[3]-mu)/sd)) for x in test]
            brier=statistics.fmean((p-x[4])**2 for p,x in zip(vals,test));constant=statistics.fmean((intercept-x[4])**2 for x in test)
            near('Brier from episodes '+str(held)+task,brier,r['Brier']);near('constant Brier '+str(held)+task,constant,r['constant_Brier'])
            brier_rows.append((len(test),brier,constant))
        near('weighted calibrated Brier',sum(n*b for n,b,c in brier_rows)/sum(n for n,b,c in brier_rows),summary['return_calibration']['episode_weighted_Brier'])
        near('weighted constant Brier',sum(n*c for n,b,c in brier_rows)/sum(n for n,b,c in brier_rows),summary['return_calibration']['episode_weighted_constant_Brier'])
        near('all 21 comparisons',sum(b<c for n,b,c in brier_rows),summary['return_calibration']['cells_improved'])
        diagrows=rows(ROOT/protocol['sources']['F05_alignment']/'rollout_value_task_diagnostics.csv')
        for r in diagrows:
            rr=mc_by[r['id'],r['task']];scale=max(1.,math.sqrt(statistics.fmean(float(x['soft_return'])**2 for x in rr)))
            errors=[];ses=[];tailfree=[]
            for case in ['0','1']:
                sub=[x for x in rr if x['episode_index']==case];values=[float(x['soft_return']) for x in sub]
                check('four action streams '+r['id']+r['task']+case,len(values)==4)
                q=float(sub[0]['q_min']);errors.append(abs(q-statistics.fmean(values))/scale)
                ses.append(statistics.stdev(values)/math.sqrt(len(values))/scale)
                tailfree.append(abs(q-statistics.fmean(float(x['tail_free_return']) for x in sub))/scale)
            for field,value in [('error',statistics.fmean(errors)),('se',statistics.fmean(ses)),('tailfree_error',statistics.fmean(tailfree)),('relative_tail',statistics.fmean(abs(float(x['discounted_tail'])) for x in rr)/scale),('scale',math.log1p(scale))]:
                near('raw MC summary '+r['id']+r['task']+field,value,r[field])
        for r in rows(src/'rollout_uncertainty_review.csv'):
            rr=[x for x in diagrows if r['task']=='ALL' or x['task']==r['task']]
            near('tail median '+r['task'],statistics.median(float(x['relative_tail']) for x in rr),r['median_relative_tail'])
            near('tail max '+r['task'],max(float(x['relative_tail']) for x in rr),r['max_relative_tail'])

        # The running job is allowed to advance; only its frozen sources must stay identical.
        active=load(ROOT/'33_remaining_factor_queue_v1/ACTIVE_CAMPAIGN.json');plan=load(Path(active['campaign'])/'plan.json')
        for stage,d in [('F05','31_fixed_horizon_alignment_v1'),('F08','32_dose_order_intervention_v1')]:
            for name,h in plan['stage_hashes'][stage].items():check('live experiment source '+stage+name,digest(ROOT/d/name)==h)
        for name in ['README.md','report_ko.md','factor_status_ko.md']:
            p=HERE/name
            if not p.exists():continue
            for target in re.findall(r'\]\(([^)]+)\)',p.read_text(encoding='utf-8')):
                if target.startswith(('http:','https:','#')):continue
                check('report link '+name+target,(p.parent/target.split('#')[0]).exists())
        result={'status':'completed','review':str(src),'review_summary_sha256':digest(src/'summary.json'),'raw_F05_deterministic_episodes':len(diag),
                'raw_F05_MC_episodes':sum(len(v) for v in mc_by.values()),'calibration_cells':len(calrows),'MC_model_task_cells':len(diagrows),
                'scope':'All retained inputs hashed; contrasts independently aggregated; F05 current-episode calibration and MC summary recomputed from CSV; no full trace replay or scientific predictor retuning.',
                'new_environment_steps':0,'new_persistent_updates':0,'new_cloned_updates':0}
    except Exception:
        result.update(traceback=traceback.format_exc());raise
    finally:
        result.update(wall_seconds=time.perf_counter()-start,cpu_seconds=time.process_time()-cpu,checks_passed=sum(r['passed'] for r in checks),checks_failed=sum(not r['passed'] for r in checks))
        save(out/'checks.json',checks);save(out/'summary.json',result)


if __name__=='__main__':main()
