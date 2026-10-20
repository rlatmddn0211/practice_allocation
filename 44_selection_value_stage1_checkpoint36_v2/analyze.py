"""Predeclared parent-clustered comparisons and retrospective, split-data choices."""
import argparse
import csv
import json
import os
import time
from pathlib import Path
import numpy as np
os.environ['PRACTICE_SUITE'] = 'B'
from practice_allocation.core import ROOT, write_json, file_sha256
from practice_allocation.study_io import source_snapshot

CONDITIONS = ['dose625', 'alternate4k', 'mixture']


def choose(values):
    return max(CONDITIONS, key=lambda c: values[c])


def choice_records(scores, parents, repeats):
    """scores[(parent, repeat, condition, half)] is macro percent, not a probability."""
    records = []
    for p in parents:
        for r in repeats:
            other = next(t for t in repeats if t != r)
            for h in (0, 1):
                selected = choose({c: scores[p, other, c, h] for c in CONDITIONS})
                fixed = choose({c: np.mean([scores[q, t, c, h] for q in parents if q != p for t in repeats]) for c in CONDITIONS})
                score = scores[p, r, selected, 1-h]
                records.append({'original_seed': p, 'heldout_continuation': r, 'selection_half': h,
                    'score_half': 1-h, 'selected': selected, 'leave_parent_out_fixed': fixed,
                    'selected_pp': score, 'vs_BP_pp': score-scores[p,r,'dose625',1-h],
                    'vs_fixed_pp': score-scores[p,r,fixed,1-h]})
    return records


def refit_sensitivity(scores, parents, repeats):
    """Remove each parent from both target scores AND fixed-method fitting."""
    rows=[]
    for excluded in parents:
        remaining=[p for p in parents if p!=excluded]
        rebuilt=choice_records(scores,remaining,repeats)
        for row in rebuilt:
            rows.append({'excluded_original_seed':excluded,**row})
    return rows


def gate(records, means, parents, repeats, scores):
    gains = {key: [float(np.mean([r[key] for r in records if r['original_seed']==p])) for p in parents]
             for key in ('vs_BP_pp', 'vs_fixed_pp')}
    preferences = []
    for i, a in enumerate(CONDITIONS):
        for b in CONDITIONS[i+1:]:
            positive = [p for p in parents if all(means[p,r,a]-means[p,r,b] >= 2 for r in repeats)]
            negative = [p for p in parents if all(means[p,r,b]-means[p,r,a] >= 2 for r in repeats)]
            preferences.append({'a': a, 'b': b, 'a_preferred_parents': positive, 'b_preferred_parents': negative,
                                'opposite_repeatable_preferences': bool(positive and negative)})
    passes = any(p['opposite_repeatable_preferences'] for p in preferences)
    refitted=refit_sensitivity(scores,parents,repeats)
    full_removal={key:[float(np.mean([r[key] for r in refitted if r['excluded_original_seed']==p])) for p in parents]
                  for key in ('vs_BP_pp','vs_fixed_pp')}
    deletion_only={key:[float(np.mean(values[:i]+values[i+1:])) for i in range(len(values))] for key,values in gains.items()}
    for key,values in gains.items():
        passes = passes and np.mean(values)>0 and all(value>0 for value in full_removal[key])
    return {'stage2_investment_gate_pass': bool(passes), 'parent_choice_gains': gains, 'pairwise_preferences': preferences,
            'full_parent_removal_refitted_means':full_removal,'deletion_of_precomputed_gains_secondary_only':deletion_only,
            'repeatability_margin_definition':'At least 2pp on the full O100 macro score in each continuation',
            'meaning': 'Exploratory investment criterion; neither statistical confirmation nor proof of absence',
            'next_state': 'stage2_specification_and_integrity_validation' if passes else 'inconclusive_or_fixed_sufficient_in_tested_scope'}


def table(path, rows):
    with path.open('x', encoding='utf-8-sig', newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--campaign',required=True); ap.add_argument('--output',required=True)
    args=ap.parse_args(); cam=Path(args.campaign); out=Path(args.output); out.mkdir(parents=True,exist_ok=False)
    source_snapshot(out); start=time.perf_counter(); input_hashes={}
    def read(path, expected=None):
        path=Path(path); value=file_sha256(path)
        if expected and value!=expected: raise RuntimeError('Input hash changed: '+str(path))
        input_hashes[str(path)]=value; return json.loads(path.read_text(encoding='utf-8-sig'))
    plan=read(cam/'plan.json',read(cam/'plan_integrity.json')['sha256'])
    protocol=read(ROOT/'configs/research_protocol.json')['stage1']
    if plan['technical_smoke']: raise RuntimeError('Technical data are not scientific evidence')
    parents=protocol['original_seeds']; repeats=protocol['continuation_labels']; scores={}; means={}; parent_scores={}; summaries=[]
    for job in plan['jobs']:
        if job['kind']!='evaluate': continue
        marker=read(cam/'completed'/(job['id']+'.json')); r=read(marker['result_ref']['path'],marker['result_ref']['sha256'])
        path=Path(r['episodes_path']); digest=file_sha256(path)
        if digest!=r['episodes_sha256']: raise RuntimeError('Outcome rows changed')
        input_hashes[str(path)]=digest
        with path.open(encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
        if len(rows)!=400 or len({(x['task'],int(x['episode_index'])) for x in rows})!=400: raise RuntimeError('Outcome coverage mismatch')
        if any(len([x for x in rows if x['task']==t])!=100 for t in ('DO','DC','PU','BP')): raise RuntimeError('Per-task outcome coverage mismatch')
        if any(int(x['success']) not in (0,1) or int(x['episode_index']) not in range(100) for x in rows): raise RuntimeError('Invalid outcome entry')
        task_scores={t:float(sum(int(x['success']) for x in rows if x['task']==t)) for t in ('DO','DC','PU','BP')}
        macro=sum(task_scores.values())/4; p=job['original_seed']
        if abs(macro-100*r['evaluation']['macro_success'])>1e-10: raise RuntimeError('Independent outcome recomputation failed')
        if job['role']=='parent': parent_scores[p]=macro
        else:
            rep=job['continuation']; cond=job['condition']; means[p,rep,cond]=macro
            for half in (0,1):
                scores[p,rep,cond,half]=sum(int(x['success']) for x in rows if int(x['episode_index'])//50==half)/2
        summaries.append({'original_seed':p,'continuation':job.get('continuation',''),'condition':job.get('condition','parent'),'macro_pp':macro,**task_scores})
    if len(means)!=30 or len(parent_scores)!=5: raise RuntimeError('Scientific cells missing')
    choices=choice_records(scores,parents,repeats); decision=gate(choices,means,parents,repeats,scores)
    comparisons=[]; rng=np.random.default_rng(424242)
    for a,b in [('alternate4k','dose625'),('mixture','dose625'),('alternate4k','mixture')]:
        vals=np.array([np.mean([means[p,r,a]-means[p,r,b] for r in repeats]) for p in parents])
        boot=vals[rng.integers(0,5,size=(10000,5))].mean(axis=1)
        comparisons.append({'method':a,'baseline':b,'mean_pp':float(vals.mean()),'parent_values_pp':json.dumps(vals.tolist()),
            'descriptive_parent_bootstrap_2_5':float(np.quantile(boot,.025)), 'descriptive_parent_bootstrap_97_5':float(np.quantile(boot,.975)),
            'positive_parents':int(sum(vals>0)), 'minimum_leave_one_parent_out_mean_pp':float(min(np.delete(vals,i).mean() for i in range(5)))})
    fixed=choose({c:float(np.mean([means[p,r,c] for p in parents for r in repeats])) for c in CONDITIONS})
    table(out/'policy_scores.csv',summaries); table(out/'choice_crossfit.csv',choices); table(out/'comparisons.csv',comparisons)
    table(out/'full_parent_removal_crossfit.csv',refit_sensitivity(scores,parents,repeats))
    summary={'execution_status':'completed','scientific_status':decision['next_state'], 'new_environment_steps':0,
             'original_seeds':parents,'continuations':repeats,'fixed_method_for_later_development':fixed,**decision,
             'uncertainty_scope':'Five parents; bootstrap is descriptive, not a powered confirmatory test. Crossfit uses expensive final information and ignores diagnostic cost.',
             'wall_seconds':time.perf_counter()-start}
    write_json(out/'input_hashes.json',input_hashes); write_json(out/'summary.json',summary)
    report='# 1단계 완료: 고정 일정과 선택 여지\n\n30분기와 부모 5개의 O100을 원시 행에서 재계산했다. 이 자료는 고정 일정의 비교이며 8k 실제 전환이나 비용 포함 선택의 검증이 아니다.\n\n'
    for row in comparisons: report+=f"- {row['method']} − {row['baseline']}: {row['mean_pp']:+.3f}%p; 부모별 차이 {row['parent_values_pp']}.\n"
    report+=f"\n탐색 진행 기준 통과: {decision['stage2_investment_gate_pass']}. 다음 상태: {decision['next_state']}. 다섯 부모의 제한과 불리한 결과를 포함한다.\n"
    report+='\n부모 유지 점수와 과제별 손익은 policy_scores.csv에 모두 보존했다. 2단계 실행 명세와 진단 규칙을 동결하기 전에는 다음 학습을 시작하지 않는다.\n'
    (out/'report_ko.md').write_text(report,encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__': main()
