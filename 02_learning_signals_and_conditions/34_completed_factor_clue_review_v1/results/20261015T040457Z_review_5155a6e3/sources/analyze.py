"""Read-only joint review of completed screens; all comparisons are descriptive."""
import csv
import hashlib
import json
import math
import shutil
import statistics
import sys
import time
import traceback
import uuid
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
PATHS={
 'F01':'27_success_retention_screening_v1/results/20261014T071242Z_analysis_1ce07d19',
 'F04':'28_gradient_update_screening_v1/results/20261014T071540Z_analysis_d2e18cbf',
 'F06':'29_neural_plasticity_screening_v1/results/20261014T101557Z_analysis_e77c6ebb',
 'F02_F03':'30_exposure_experience_screening_v1/results/20261015T031819Z_analysis_56a74006',
 'F07':'24_signal_reliability_screening_v1/results/20261014T053612Z_df5ecad4'}
KEY=['suite','original_seed','checkpoint_step','continuation','mode']
TASKS={'A':['DO','DC','WO','WC'],'B':['DO','DC','PU','BP'],'C':['DO','PP','PU','BP']}
def key(r):return tuple(r[k] for k in KEY)
def context(r):return tuple(r[k] for k in KEY[:4])
def group(r):return r['suite']+str(int(r['checkpoint_step'])//1000)
def weighted(rows,field):return math.fsum(float(r['weight'])*float(r[field]) for r in rows)/math.fsum(float(r['weight']) for r in rows)
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def ranks(a):
    result=[0.]*len(a);ix=sorted(range(len(a)),key=a.__getitem__);i=0
    while i<len(a):
        j=i+1
        while j<len(a) and a[ix[j]]==a[ix[i]]:j+=1
        for t in ix[i:j]:result[t]=(i+j-1)/2
        i=j
    return result
def spearman(x,y):
    x=ranks(x);y=ranks(y);mx=statistics.mean(x);my=statistics.mean(y)
    xx=math.fsum((v-mx)**2 for v in x);yy=math.fsum((v-my)**2 for v in y)
    return math.fsum((a-mx)*(b-my) for a,b in zip(x,y))/math.sqrt(xx*yy) if xx*yy>0 else None
def table(path,rows):
    if not rows:raise ValueError('Empty table '+str(path))
    with path.open('x',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def write(path,data):
    with path.open('x',encoding='utf-8') as f:json.dump(data,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n')

def main():
    out=HERE/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_review_'+uuid.uuid4().hex[:8]);out.mkdir(parents=True)
    print(str(out),flush=True);start=time.perf_counter();cpu=time.process_time();inputs={};checks=[];details={};error=None
    for p in [*HERE.glob('*.py'),HERE/'protocol.json']:
        dest=out/'sources'/p.name;dest.parent.mkdir(exist_ok=True);shutil.copy2(p,dest)
    write(out/'source_hashes.json',{p.name:sha(p) for p in [*HERE.glob('*.py'),HERE/'protocol.json']})
    write(out/'runtime.json',{'python':sys.version,'executable':sys.executable,'command':sys.argv,'dependencies':'Python standard library only'})
    def check(name,ok):
        checks.append({'check':name,'passed':bool(ok)})
        if not ok:raise AssertionError(name)
    def near(name,a,b):check(name,math.isclose(float(a),float(b),rel_tol=1e-9,abs_tol=1e-9))
    def pin(path):
        path=Path(path);rel=path.relative_to(ROOT);inputs[rel.as_posix()]=sha(path);dest=out/'inputs'/rel
        if not dest.exists():dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)
        return path
    def rows(path):
        with pin(path).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
    def read(path):return json.loads(pin(path).read_text(encoding='utf-8-sig'))
    try:
        p=read(HERE/'protocol.json');data={}
        for name,d in PATHS.items():
            directory=ROOT/d;summary=read(directory/'summary.json')
            check('source analysis completed '+name,summary['status']=='completed')
            pin(directory.parent.parent/'report_ko.md')
            if name=='F07':
                for filename in ['horizon_pairs.csv','selection_summary.csv','selection_by_original_seed.csv','contexts.csv']:rows(directory/filename)
                continue
            data[name]={k:rows(directory/(k+'.csv')) for k in ['selection_rows','features','predictions','prediction_metrics','selection_summary']}
            check('180 unique branch feature rows '+name,len(data[name]['features'])==180 and len({r['id'] for r in data[name]['features']})==180)
            check('branch weights sum1 '+name,abs(math.fsum(float(r['weight']) for r in data[name]['features'])-1)<1e-12)
        comparison_rows=[];changed=[];all_primary_changed=set();seed_group=[]
        for factor,(dataset,method,baseline) in {**p['primary_comparisons'],**p['secondary_comparisons']}.items():
            dd=data[dataset];selection={(key(r),r['method']):r for r in dd['selection_rows']};ff={r['id']:r for r in dd['features']}
            bycontext=defaultdict(list)
            for r in ff.values():bycontext[context(r)].append(r)
            preds={(r['method'],r['id']):float(r['predicted40']) for r in dd['predictions']}
            maes={r['method']:float(r['O40_MAE_pp']) for r in dd['prediction_metrics']}
            for m in [method,baseline]:near('recomputed prediction MAE '+factor+m,math.fsum(float(r['weight'])*abs(preds[m,r['id']]-float(r['O40']))*100 for r in ff.values()),maes[m])
            for mode in ['same_repeat','cross_repeat']:
                rr=[r for r in dd['selection_rows'] if r['method']==method and r['mode']==mode];check('36 comparable decisions '+factor+mode,len(rr)==36)
                augmented=[];baserows=[]
                for r in rr:
                    b=selection[key(r),baseline];g=selection[key(r),'Greedy20'];same=bycontext[context(r)]
                    matched=[f for f in same if f['allocation']==r['selected_allocation']];check('one chosen actual branch',len(matched)==1)
                    near('selected O from frozen branch',r['score_pp'],float(matched[0]['O40'])*100)
                    weights=[float(r['weight']),float(b['weight'])];near('equal decision weight',*weights)
                    one=dict(r,increment=float(r['score_pp'])-float(b['score_pp']),risk_reduction=float(b['max_task_drop_pp'])-float(r['max_task_drop_pp']))
                    augmented.append(one);baserows.append(b)
                    dif=r['selected_allocation']!=b['selected_allocation'];margins={}
                    for mm in [baseline,method]:
                        pool=[f for f in ff.values() if f['suite']==r['suite'] and f['original_seed']==r['original_seed'] and f['checkpoint_step']==r['checkpoint_step'] and ((f['continuation']==r['continuation']) if mode=='same_repeat' else (f['continuation']!=r['continuation']))]
                        names=['U']+['F_'+t for t in TASKS[r['suite']]]
                        values=[statistics.mean(preds[mm,f['id']] for f in pool if f['allocation']==a) for a in names]
                        chosen=next(i for i,v in enumerate(values) if v>=max(values)-1e-12)
                        observed=b if mm==baseline else r
                        check('chosen argmax from frozen predictions',names[chosen]==observed['selected_allocation'])
                        ss=sorted(values,reverse=True);margins[mm]=100*(ss[0]-ss[1])
                    if dif:
                        row={k:r[k] for k in KEY};row.update(factor=factor,primary=factor in p['primary_comparisons'],baseline=baseline,method=method,
                           baseline_choice=b['selected_allocation'],new_choice=r['selected_allocation'],baseline_score_pp=float(b['score_pp']),new_score_pp=float(r['score_pp']),
                           increment_pp=one['increment'],weight=float(r['weight']),weighted_increment_pp=one['increment']*float(r['weight']),
                           baseline_top2_predicted_margin_pp=margins[baseline],new_top2_predicted_margin_pp=margins[method],
                           baseline_max_task_drop_pp=float(b['max_task_drop_pp']),new_max_task_drop_pp=float(r['max_task_drop_pp']),risk_reduction_pp=one['risk_reduction'])
                        changed.append(row)
                        if factor in p['primary_comparisons'] and mode=='same_repeat':all_primary_changed.add(context(r))
                avg=weighted(augmented,'increment');source=next(x for x in dd['selection_summary'] if x['method']==method and x['mode']==mode)
                near('recomputed aggregate selected score',weighted(rr,'score_pp'),source['score_pp'])
                comparison_rows.append({'factor':factor,'primary':factor in p['primary_comparisons'],'mode':mode,'method':method,'baseline':baseline,
                    'increment_pp':avg,'score_pp':weighted(rr,'score_pp'),'baseline_score_pp':weighted(baserows,'score_pp'),
                    'vs_greedy_pp':weighted(rr,'vs_greedy_pp'),'changed_choices':sum(x['selected_allocation']!=y['selected_allocation'] for x,y in zip(rr,baserows)),
                    'better_changes':sum(x['increment']>1e-10 for x in augmented),'worse_changes':sum(x['increment']<-1e-10 for x in augmented),
                    'mean_worst_task_drop_reduction_pp':weighted(augmented,'risk_reduction'),
                    'method_MAE_pp':maes[method],'baseline_MAE_pp':maes[baseline]})
                for split,parts in [('original_seed',['11','12','13']),('group',['A200','A400','B200','C200'])]:
                    for part in parts:
                        ss=[r for r in augmented if (r['original_seed'] if split=='original_seed' else group(r))==part]
                        seed_group.append({'factor':factor,'mode':mode,'split':split,'part':part,'increment_pp':weighted(ss,'increment'),'risk_reduction_pp':weighted(ss,'risk_reduction')})
        table(out/'comparisons.csv',comparison_rows);table(out/'all_changed_choices.csv',changed);table(out/'increments_by_seed_group.csv',seed_group)
        # Common outcomes and simple decisions must agree across all four prior pipelines.
        anchor=data['F01'];aa={r['id']:r for r in anchor['features']};selected_anchor={(key(r),r['method']):r for r in anchor['selection_rows']}
        for name,dd in data.items():
            for r in dd['features']:
                for field in ['D20','target_D_remainder','O40','weight']:near('same branch information '+name,aa[r['id']][field],r[field])
            for r in dd['selection_rows']:
                if r['method'] in ['Uniform','Failure','Development_fixed','Greedy20']:
                    b=selected_anchor[key(r),r['method']];check('same common-baseline choice',b['selected_allocation']==r['selected_allocation']);near('same common-baseline score',b['score_pp'],r['score_pp'])
        headroom=[]
        for mode in ['same_repeat','cross_repeat']:
            for method in ['Uniform','Failure','Development_fixed','Greedy20','Profile']:
                rr=[r for r in anchor['selection_rows'] if r['mode']==mode and r['method']==method]
                for part in ['all','A200','A400','B200','C200']:
                    ss=rr if part=='all' else [r for r in rr if group(r)==part]
                    headroom.append({'mode':mode,'method':method,'group':part,'score_pp':weighted(ss,'score_pp'),
                      'observed_hindsight_gap_pp':weighted(ss,'hindsight_regret_pp'),'observed_hindsight_best_pp':weighted(ss,'score_pp')+weighted(ss,'hindsight_regret_pp')})
        table(out/'observed_selection_headroom.csv',headroom)
        # One post-hoc diagnostic link, preserving negative as well as positive associations.
        gg=[]
        for r in data['F06']['features']:
            gg.append({k:r[k] for k in ['id','suite','original_seed','checkpoint_step','continuation','allocation']}|{
                'critic_train_other_gap':float(r['critic_total20_train'])-float(r['critic_total20']),
                'abs_O40_minus_D20_pp':abs(float(r['O40'])-float(r['D20']))*100})
        table(out/'critic_gap_and_future_discrepancy.csv',gg);corr=[]
        for split,parts in [('all',['all']),('group',['A200','A400','B200','C200']),('original_seed',['11','12','13'])]:
            for part in parts:
                ss=gg if split=='all' else [r for r in gg if (group(r) if split=='group' else r['original_seed'])==part]
                corr.append({'split':split,'part':part,'dependent_branch_rows':len(ss),'spearman':spearman([r['critic_train_other_gap'] for r in ss],[r['abs_O40_minus_D20_pp'] for r in ss])})
        table(out/'critic_gap_descriptive_correlations.csv',corr)
        for name,extra in [('F01','paired_task_cases.csv'),('F04','gradient_stability_summary.csv'),('F06','dynamic_summary.csv')]:rows(ROOT/PATHS[name]/extra)
        cases=rows(ROOT/PATHS['F01']/'paired_task_cases.csv')
        details={'primary_changed_choice_union_count':len(all_primary_changed),'primary_changed_choice_union':[list(k) for k in sorted(all_primary_changed)],
          'total_decision_cells_per_method':36,'no_turnover_freedom_task_rows':sum(float(r['excess_capacity'])==0 for r in cases),'task_rows':len(cases),
          'primary_comparisons':[r for r in comparison_rows if r['primary']],'critic_gap_correlations':corr,
          'greedy_observed_headroom':next(r for r in headroom if r['mode']=='same_repeat' and r['method']=='Greedy20' and r['group']=='all')}
    except BaseException:error=traceback.format_exc()
    write(out/'input_hashes.json',inputs);write(out/'checks.json',checks)
    summary={'status':'failed' if error else 'completed','exploratory':True,'independent_replication':False,'source_analyses':PATHS,'results':details,
      'wall_seconds':time.perf_counter()-start,'cpu_seconds':time.process_time()-cpu,'new_environment_steps':0,'persistent_learner_updates':0,'clone_updates':0,
      'checks_passed':sum(c['passed'] for c in checks),'checks_failed':sum(not c['passed'] for c in checks),'error':error}
    write(out/'summary.json',summary)
    if error:raise RuntimeError(error)
    write(HERE/('RUN_'+out.name+'.json'),{'path':str(out),'summary_sha256':sha(out/'summary.json')})
    print(json.dumps({'status':'completed','wall_seconds':summary['wall_seconds'],'checks':summary['checks_passed'],
        'primary_changed_choice_union':len(all_primary_changed),'critic_gap_correlations':corr},indent=2),flush=True)

if __name__=='__main__':main()
