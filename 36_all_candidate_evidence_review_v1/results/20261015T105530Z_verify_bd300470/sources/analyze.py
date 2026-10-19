"""Independent aggregation of frozen candidate screens; no scientific model fitting."""
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
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
KEY = ['suite', 'original_seed', 'checkpoint_step', 'continuation', 'mode']


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def write(path, value):
    with path.open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def table(path, values):
    with path.open('x', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(values[0]))
        w.writeheader()
        w.writerows(values)


def key(row):
    return tuple(str(row[k]) for k in KEY)


def group(row):
    return row['suite'] + str(int(row['checkpoint_step']) // 1000)


def mean(rows, field):
    return math.fsum(float(r['weight']) * float(r[field]) for r in rows) / math.fsum(float(r['weight']) for r in rows)


def main():
    start, cpu = time.perf_counter(), time.process_time()
    out = HERE/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_review_'+uuid.uuid4().hex[:8])
    out.mkdir(parents=True)
    print(out, flush=True)
    inputs, checks, result = {}, [], {'status': 'failed'}
    source = [*HERE.glob('*.py'), HERE/'protocol.json']
    (out/'sources').mkdir()
    for p in source:
        shutil.copy2(p, out/'sources'/p.name)
    write(out/'source_hashes.json', {p.name: sha(p) for p in source})
    write(out/'runtime.json', {'python': sys.version, 'executable': sys.executable, 'argv': sys.argv, 'dependencies': 'Python standard library only'})

    def check(label, value):
        checks.append({'check': label, 'passed': bool(value)})
        if not value:
            raise AssertionError(label)

    def near(label, a, b):
        check(label, math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-9))

    def pin(path):
        path = Path(path)
        if not path.is_absolute():
            path = ROOT/path
        rel = path.relative_to(ROOT)
        payload = path.read_bytes()
        inputs[rel.as_posix()] = hashlib.sha256(payload).hexdigest()
        # Keep snapshots shallow enough for the Windows path-length limit.
        dest = out/'inputs'/(inputs[rel.as_posix()] + path.suffix)
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open('xb') as f:
                f.write(payload)
        return dest

    def read(path):
        return json.loads(pin(path).read_text(encoding='utf-8-sig'))

    def rows(path):
        with pin(path).open(encoding='utf-8-sig', newline='') as f:
            return list(csv.DictReader(f))

    try:
        protocol = read(HERE/'protocol.json')
        data, baseline, prediction_audits = {}, {}, []
        for name, directory in protocol['sources'].items():
            d = ROOT/directory
            summary = read(d/'summary.json')
            check('completed source '+name, summary['status'] == 'completed')
            for filename in ['protocol.json', 'report_ko.md']:
                p = d.parent.parent/filename
                if p.exists(): pin(p)
            for filename in ['source_hashes.json', 'input_hashes.json', 'case_splits.json']:
                if (d/filename).exists(): pin(d/filename)
            if name == 'F07':
                data[name] = {file: rows(d/(file+'.csv')) for file in ['horizon_pairs', 'selection_summary', 'contexts']}
                data[name]['summary'] = summary
                continue
            dd = {file: rows(d/(file+'.csv')) for file in ['features', 'predictions', 'prediction_metrics', 'selection_rows', 'selection_summary']}
            for metric in dd['prediction_metrics']:
                if 'O40_MAE_pp' not in metric:
                    metric['O40_MAE_pp'] = metric['held_original_seed_O40_MAE_pp']
            data[name] = dd
            feature = {r['id']: r for r in dd['features']}
            check('180 unique branches '+name, len(feature) == len(dd['features']) == 180)
            near('branch weights '+name, sum(float(r['weight']) for r in feature.values()), 1)
            pred = defaultdict(dict)
            for row in dd['predictions']:
                pred[row['method']][row['id']] = float(row['predicted40'])
                near('observed branch '+name+row['id'], row['observed_O40'], feature[row['id']]['O40'])
            for metric in dd['prediction_metrics']:
                method = metric['method']
                near('MAE '+name+method, math.fsum(float(r['weight'])*abs(pred[method][r['id']]-float(r['O40']))*100 for r in feature.values()), metric['O40_MAE_pp'])
            by_context = defaultdict(list)
            for r in feature.values():
                by_context[tuple(r[k] for k in KEY[:3])].append(r)
            selection = {(key(r), r['method']): r for r in dd['selection_rows']}
            check('unique choices '+name, len(selection) == len(dd['selection_rows']))
            for r in dd['selection_rows']:
                ctx = tuple(r[k] for k in KEY[:3])
                branches = by_context[ctx]
                chosen = next(f for f in branches if f['continuation'] == r['continuation'] and f['allocation'] == r['selected_allocation'])
                near('selected outcome '+name+str(key(r))+r['method'], 100*float(chosen['O40']), r['score_pp'])
                method = r['method']
                if method in pred:
                    allocations = list(dict.fromkeys(f['allocation'] for f in branches))
                    def val(a):
                        fs = [f for f in branches if f['allocation']==a and ((f['continuation']==r['continuation']) if r['mode']=='same_repeat' else (f['continuation']!=r['continuation']))]
                        return statistics.mean(pred[method][f['id']] for f in fs)
                    scores = {a: val(a) for a in allocations}
                    # Feature order is the frozen allocation order, Uniform then task order.
                    selected = next(a for a in allocations if scores[a] >= max(scores.values())-1e-12)
                    check('choice from frozen predictions '+name+str(key(r))+method, selected == r['selected_allocation'])
                if method in ['Uniform', 'Failure', 'Development_fixed', 'Greedy20']:
                    k = key(r), method
                    if k in baseline:
                        near('common score '+name+str(k), r['score_pp'], baseline[k]['score_pp'])
                        check('common selected allocation '+name+str(k), r['selected_allocation'] == baseline[k]['selected_allocation'])
                    else: baseline[k] = r
            for r in dd['selection_summary']:
                selected = [x for x in dd['selection_rows'] if x['mode']==r['mode'] and x['method']==r['method']]
                check('36 decisions '+name+r['mode']+r['method'], len(selected)==36)
                near('decision weights '+name+r['mode']+r['method'], sum(float(x['weight']) for x in selected), 1)
                near('summary score '+name+r['mode']+r['method'], mean(selected,'score_pp'), r['score_pp'])
            dd['pred_index'], dd['feature_index'], dd['contexts'] = pred, feature, by_context
            prediction_audits.append({'source': name, 'predictions': len(dd['predictions']), 'selection_rows': len(dd['selection_rows']), 'models': len(pred), 'branches':len(feature)})

        comparisons, subgroups, changes = [], [], []
        union = {'same_repeat': set(), 'cross_repeat': set()}
        for factor, source, method, comparator, role in protocol['comparisons']:
            dd = data[source]
            ix = {(key(r),r['method']):r for r in dd['selection_rows']}
            maes = {r['method']:float(r['O40_MAE_pp']) for r in dd['prediction_metrics']}
            for mode in ['same_repeat', 'cross_repeat']:
                selected=[]
                for r in dd['selection_rows']:
                    if r['method']!=method or r['mode']!=mode: continue
                    b=ix[key(r),comparator]
                    delta=float(r['score_pp'])-float(b['score_pp'])
                    changed=r['selected_allocation']!=b['selected_allocation']
                    selected.append(dict(r,increment=delta,changed=int(changed)))
                    if changed:
                        ctx=tuple(r[k] for k in KEY[:3]);branches=dd['contexts'][ctx]
                        byalloc=defaultdict(list)
                        for f in branches:
                            if (f['continuation']==r['continuation']) if mode=='same_repeat' else (f['continuation']!=r['continuation']):
                                byalloc[f['allocation']].append(dd['pred_index'][comparator][f['id']])
                        rank=sorted((statistics.mean(v) for v in byalloc.values()),reverse=True)
                        event={'factor':factor,'role':role,'source':source,'method':method,'comparator':comparator,**{k:r[k] for k in KEY},
                               'group':group(r),'before':b['selected_allocation'],'after':r['selected_allocation'],'before_score_pp':float(b['score_pp']),
                               'after_score_pp':float(r['score_pp']),'difference_pp':delta,'weight':float(r['weight']),
                               'weighted_contribution_pp':float(r['weight'])*delta,'baseline_prediction_margin_pp':100*(rank[0]-rank[1]),
                               'max_task_drop_reduction_pp':float(b['max_task_drop_pp'])-float(r['max_task_drop_pp'])}
                        changes.append(event)
                        if role=='primary': union[mode].add(key(r))
                positive=[float(r['weight'])*r['increment'] for r in selected if r['increment']>1e-10]
                negative=[float(r['weight'])*r['increment'] for r in selected if r['increment']<-1e-10]
                inc=mean(selected,'increment')
                comparisons.append({'factor':factor,'role':role,'source':source,'method':method,'comparator':comparator,'mode':mode,
                                    'increment_pp':inc,'changed_choices':sum(r['changed'] for r in selected),'decisions':len(selected),
                                    'positive_changes':len(positive),'negative_changes':len(negative),'tied_changes':sum(r['changed'] and abs(r['increment'])<1e-10 for r in selected),
                                    'positive_contribution_pp':math.fsum(positive),'negative_contribution_pp':math.fsum(negative),
                                    'without_largest_positive_contribution_pp':inc-max(positive,default=0),
                                    'score_pp':mean(selected,'score_pp'),'vs_greedy_pp':mean(selected,'score_pp')-mean([r for r in dd['selection_rows'] if r['mode']==mode and r['method']=='Greedy20'],'score_pp'),
                                    'base_MAE_pp':maes[comparator],'augmented_MAE_pp':maes[method]})
                for scope, parts in [('original_seed',['11','12','13']),('group',['A200','A400','B200','C200'])]:
                    for part in parts:
                        rr=[r for r in selected if (r['original_seed'] if scope=='original_seed' else group(r))==part]
                        subgroups.append({'factor':factor,'role':role,'mode':mode,'scope':scope,'part':part,'increment_pp':mean(rr,'increment'),'changed_choices':sum(r['changed'] for r in rr),'decisions':len(rr)})
        table(out/'comparisons.csv',comparisons);table(out/'increments_by_seed_group.csv',subgroups);table(out/'all_changed_choices.csv',changes)
        table(out/'recomputed_prediction_inventory.csv',prediction_audits)

        d=ROOT/protocol['sources']['F05_alignment']
        calibration=rows(d/'held_seed_return_calibration.csv')
        for r in calibration:
            r['Brier_improvement']=float(r['constant_Brier'])-float(r['Brier'])
        table(out/'return_calibration_review.csv',calibration)
        rollout=rows(d/'rollout_value_task_diagnostics.csv')
        rollout_summary=[]
        for task in ['ALL',*sorted({r['task'] for r in rollout})]:
            rr=[r for r in rollout if task=='ALL' or r['task']==task]
            rollout_summary.append({'task':task,'model_task_rows':len(rr),'median_normalized_Q_error':statistics.median(float(r['error']) for r in rr),
                'median_normalized_MC_SE':statistics.median(float(r['se']) for r in rr),'median_relative_tail':statistics.median(float(r['relative_tail']) for r in rr),
                'max_relative_tail':max(float(r['relative_tail']) for r in rr),'median_abs_error_change_without_tail':statistics.median(abs(float(r['error'])-float(r['tailfree_error'])) for r in rr)})
        table(out/'rollout_uncertainty_review.csv',rollout_summary)

        f07=data['F07'];hp=f07['horizon_pairs'];ss=f07['summary']
        near('F07 pair reversal count',sum(r['reversed']=='True' for r in hp),ss['observed_horizon_reversals'])
        near('F07 conditional robust count',sum(r['simultaneous_case_robust_reversal']=='True' for r in hp),ss['simultaneous_case_robust_reversals'])
        f07_selected=[r for r in f07['selection_summary'] if r['mode']=='cross_repeat_20_to_40' and r['cases_per_task'] in ['2','20']]
        check('F07 primary and n20 rows',len(f07_selected)==14)
        for expected in ss['primary_results']+ss['secondary_results_n20']:
            matched=next(r for r in f07_selected if r['method']==expected['method'] and int(r['cases_per_task'])==expected['cases_per_task'])
            near('F07 intended horizon '+matched['method']+matched['cases_per_task'],matched['score_pp'],expected['score_pp'])
        table(out/'F07_reference_rules.csv',f07_selected)

        base_rows=[]
        for mode in ['same_repeat','cross_repeat']:
            for method in ['Uniform','Failure','Development_fixed','Greedy20']:
                allrows=[r for (k,m),r in baseline.items() if m==method and r['mode']==mode]
                for part in ['ALL','A200','A400','B200','C200']:
                    rr=allrows if part=='ALL' else [r for r in allrows if group(r)==part]
                    base_rows.append({'mode':mode,'method':method,'group':part,'score_pp':mean(rr,'score_pp'),'absolute_gain_pp':mean(rr,'absolute_gain_pp'),
                                      'observed_hindsight_gap_pp':mean(rr,'hindsight_regret_pp'),'negative_gain_cells':sum(float(r['absolute_gain_pp'])<0 for r in rr),'cells':len(rr)})
        table(out/'common_baseline_review.csv',base_rows)

        active=read(ROOT/'33_remaining_factor_queue_v1/ACTIVE_CAMPAIGN.json');cam=Path(active['campaign'])
        plan=read(cam/'plan.json');status=read(cam/'STATUS.json');write(out/'observed_status.json',status)
        integrity=read(cam/'plan_integrity.json');check('campaign plan hash',sha(cam/'plan.json')==integrity['sha256'])
        stages={'F05':ROOT/'31_fixed_horizon_alignment_v1','F08':ROOT/'32_dose_order_intervention_v1'}
        for stage,base in stages.items():
            for name,expected in plan['stage_hashes'][stage].items():check('active source preserved '+stage+name,sha(base/name)==expected)
        receipts=[];total_env=0;wall=0.;cpu_cost=0.;trace_checks=0;trace_wall=0.;trace_cpu=0.
        for job in plan['jobs']:
            if job['stage']!='F05' or job['kind']!='measure':continue
            marker=read(cam/'completed'/(job['id']+'.json'));ref=marker['result_ref'];rec=read(ref['path'])
            check('measurement reference '+job['id'],sha(Path(ref['path']))==ref['sha256'])
            check('unchanged learner '+job['id'],rec['learner_unchanged'])
            attempt=Path(marker['attempt']);cost=read(attempt/'costs.json');trace=read(attempt/'trace_verified.json')
            for stem in ['episodes','mc']:
                check('raw diagnostic CSV '+job['id']+stem,sha(pin(rec[stem+'_path']))==rec[stem+'_sha256'])
            # Receipt references are inspected; the already verified raw trajectory archive is preserved, not replayed here.
            if 'path' in trace and 'sha256' in trace:
                check('trace receipt hash '+job['id'],sha(Path(trace['path']))==trace['sha256'])
                tr=read(trace['path']);trace_checks+=tr.get('checks_passed',0);trace_wall+=tr.get('wall_seconds',0);trace_cpu+=tr.get('cpu_seconds',0)
                check('trace verification complete '+job['id'],tr['status']=='completed' and tr['checks_failed']==0)
            else: raise ValueError('Unexpected trace receipt schema '+str(trace))
            total_env+=cost['costs']['environment_steps'];wall+=cost['wall_seconds'];cpu_cost+=cost['cpu_seconds']
            check('no F05 persistent training '+job['id'],cost['costs']['train_iterations']==0)
            receipts.append({'job':job['id'],'result':ref['path'],'result_sha256':ref['sha256'],'trace_receipt':str(attempt/'trace_verified.json'),'environment_steps':cost['costs']['environment_steps']})
        check('192 completed diagnostic receipts',len(receipts)==192)
        near('F05 environment total',total_env,10752000)
        table(out/'F05_measurement_receipts.csv',receipts)
        for jid in ['F05_analysis','F05_verification']:
            marker=read(cam/'completed'/(jid+'.json'));ref=marker['result_ref'];s=read(ref['path'])
            check('F05 finished and pinned '+jid,s['status']=='completed' and sha(Path(ref['path']))==ref['sha256'])
        result={'status':'completed','timestamp':datetime.now(timezone.utc).isoformat(),'scope':'Retrospective seven completed candidate screens; F08 status only',
                'comparisons':comparisons,'primary_changed_cell_union':{k:len(v) for k,v in union.items()},
                'return_calibration':{'cells':len(calibration),'cells_improved':sum(r['Brier_improvement']>0 for r in calibration),
                'episode_weighted_Brier':sum(int(r['episodes'])*float(r['Brier']) for r in calibration)/sum(int(r['episodes']) for r in calibration),
                'episode_weighted_constant_Brier':sum(int(r['episodes'])*float(r['constant_Brier']) for r in calibration)/sum(int(r['episodes']) for r in calibration),
                'note':'Held-original-seed contemporaneous episode success, not future improvement or allocation value.'},
                'F05_cost':{'measurement_environment_steps':total_env,'measurement_wall_seconds':wall,'measurement_CPU_seconds':cpu_cost,'trace_checks_previously_passed':trace_checks,'trace_verification_wall_seconds':trace_wall,'trace_verification_CPU_seconds':trace_cpu},
                'F07':{'reversed_pairs':sum(r['reversed']=='True' for r in hp),'conditional_robust_pairs':sum(r['simultaneous_case_robust_reversal']=='True' for r in hp),'pairs':len(hp)},
                'F08_status':status,'new_environment_steps':0,'new_persistent_updates':0,'new_cloned_updates':0,'independent_scientific_confirmation':False}
    except Exception:
        result.update(traceback=traceback.format_exc())
        raise
    finally:
        result.update(wall_seconds=time.perf_counter()-start,cpu_seconds=time.process_time()-cpu,checks_passed=sum(c['passed'] for c in checks),checks_failed=sum(not c['passed'] for c in checks))
        write(out/'input_hashes.json',inputs);write(out/'checks.json',checks);write(out/'summary.json',result)


if __name__=='__main__':main()
