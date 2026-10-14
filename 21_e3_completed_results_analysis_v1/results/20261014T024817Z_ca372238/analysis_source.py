"""Independent E3 audit and descriptive analysis; never starts an RL environment."""
from __future__ import annotations

import csv
import hashlib
import itertools
import json
import platform
import shutil
import statistics as st
import time
import traceback
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TASKS = {'B': ['DO', 'DC', 'PU', 'BP'], 'C': ['DO', 'PP', 'PU', 'BP']}
SEEDS = [11, 12, 13]
REPEATS = [2301, 2302, 2303]


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def save(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def table(path, rows):
    if not rows:
        return
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with path.open('x', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    started = time.perf_counter()
    output = HERE/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_')+uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    shutil.copy2(__file__, output/'analysis_source.py')
    inputs, checks = {}, []

    def check(name, condition):
        checks.append({'name': name, 'passed': bool(condition)})
        if not condition:
            raise AssertionError(name)

    def hashed(p):
        p = Path(p)
        actual = sha(p)
        if str(p) in inputs:
            check('input_stable:'+str(p), inputs[str(p)] == actual)
        inputs[str(p)] = actual
        return actual

    def read(p):
        hashed(p)
        return json.loads(Path(p).read_text(encoding='utf-8'))

    def csv_rows(p):
        hashed(p)
        with Path(p).open(encoding='utf-8', newline='') as f:
            return list(csv.DictReader(f))

    try:
        active = read(ROOT/'13_e0_e3_autonomous_queue_v1/ACTIVE_CAMPAIGN.json')
        campaign = Path(active['campaign'])
        status = read(campaign/'STATUS.json')
        plan = read(campaign/'plan.json')
        integrity = read(campaign/'plan_integrity.json')
        check('frozen_plan_hash', inputs[str(campaign/'plan.json')] == integrity['sha256'])
        check('campaign_completed', status['state'] == 'completed' and status['completed_jobs'] == status['total_jobs'] == 1051)
        planned = {j['id']: j for j in plan['jobs'] if j['stage'] == 'E3'}
        markers = sorted((campaign/'completed').glob('E3*.json'))
        check('all_459_planned_E3_jobs', {p.stem for p in markers} == set(planned) and len(markers) == 459)
        results, requests, folders, costs = {}, {}, {}, []
        checkpoints, packages = {}, []
        for marker_path in markers:
            marker = read(marker_path)
            p = Path(marker['result_ref']['path'])
            rec = read(p)
            key = rec['id']
            check('result_hash:'+key, inputs[str(p)] == marker['result_ref']['sha256'])
            check('planned_identity:'+key, all(rec[k] == planned[key][k] for k in ['id', 'stage', 'suite', 'kind', 'original_seed']))
            req = read(p.parent/'request.json')
            check('frozen_source_set:'+key, req['source_hashes'] == plan['sources']['E3'])
            check('not_a_smoke:'+key, req['technical_smoke'] is False)
            for name, digest in req['source_hashes'].items():
                source = p.parent/'source_snapshot'/name
                check('executed_source:'+key+':'+name, hashed(source) == digest)
            results[key], requests[key], folders[key] = rec, req, p.parent
            cost = read(p.parent/'costs.json')
            check('successful_cost_record:'+key, cost['success'] and not cost['technical_smoke'])
            costs.append({'id': key, 'suite': rec['suite'], 'kind': rec['kind'], **cost['costs'], 'wall_seconds': cost['wall_seconds']})
            if 'checkpoint' in rec:
                cp = Path(rec['checkpoint']['path'])
                manifest_path = cp/'checkpoint_manifest.json'
                manifest = read(manifest_path)
                check('checkpoint_manifest:'+key, inputs[str(manifest_path)] == rec['checkpoint']['manifest_sha256'])
                check('checkpoint_suite_order:'+key, manifest['suite'] == rec['suite'] and list(manifest['tasks']) == TASKS[rec['suite']])
                for name, digest in manifest['files'].items():
                    check('checkpoint_file:'+key+':'+name, hashed(cp/name) == digest)
                checkpoints[key] = manifest
                packages.append(manifest['packages'])
            if rec['kind'] == 'train':
                check('training_step_count:'+key, rec['step'] == req['start_step'] + req['steps'] and cost['costs']['environment_steps'] == req['steps'])
                check('collected_step_count:'+key, sum(rec['collected_this_job'].values()) == req['steps'])
                parent = Path(req['parent']['path'])/'checkpoint_manifest.json'
                check('parent_manifest:'+key, hashed(parent) == req['parent']['manifest_sha256'])
                par = json.loads(parent.read_text())
                check('parent_step:'+key, par['step'] == req['start_step'])
                counts = rec['collected_this_job']
                if rec['allocation'] == 'U':
                    check('uniform_collection:'+key, set(counts.values()) == {req['steps']//4})
                else:
                    focus = rec['allocation'][2:]
                    check('focus_collection:'+key, all(v == req['steps']*(5 if t == focus else 1)//8 for t, v in counts.items()))

        # Verify exact same original state and continuation RNG for all paired allocations.
        branch_starts = [r for r in requests.values() if r.get('start_branch')]
        check('90_branch_starts', len(branch_starts) == 90)
        for suite, seed, repeat in itertools.product(TASKS, SEEDS, REPEATS):
            group = [r for r in branch_starts if (r['suite'], r['original_seed'], r['continuation_label']) == (suite, seed, repeat)]
            check(f'paired_parent_and_rng:{suite}:{seed}:{repeat}', len(group) == 5 and len({r['parent']['manifest_sha256'] for r in group}) == 1 and len({r['continuation_rng_seed'] for r in group}) == 1)

        bank_lookup = {}
        for suite in TASKS:
            record = results[f'E3_{suite}_bank']
            path = Path(record['bank']['path'])
            bank = read(path)
            check('bank_hash:'+suite, inputs[str(path)] == record['bank']['sha256'])
            for label in ['diagnostic', 'outcome']:
                bank_lookup[suite, label] = {(e['task'], e['episode_index']): (e['seed'], e['initial_state_hash']) for e in bank[label]}
                check('bank_400_distinct_cases:'+suite+label, len(bank_lookup[suite, label]) == 400)
            check('disjoint_public_outcome:'+suite, not ({v[1] for v in bank_lookup[suite, 'diagnostic'].values()} & {v[1] for v in bank_lookup[suite, 'outcome'].values()}))

        metrics = {}
        total_episodes = 0
        for key, rec in results.items():
            if rec['kind'] != 'evaluate':
                continue
            suite = rec['suite']
            p = Path(rec['episodes_path'])
            episodes = csv_rows(p)
            check('evaluation_hash:'+key, inputs[str(p)] == rec['episodes_sha256'])
            counts = Counter(e['task'] for e in episodes)
            check('100_cases_per_task:'+key, dict(counts) == {t: 100 for t in TASKS[suite]})
            success = {t: sum(int(e['success']) for e in episodes if e['task'] == t) for t in TASKS[suite]}
            bank_kind = requests[key]['bank_kind']
            signatures = {(e['task'], int(e['episode_index'])): (int(e['seed']), e['initial_state_hash']) for e in episodes}
            check('matched_cases:'+key, signatures == bank_lookup[suite, bank_kind])
            check('valid_episode_outcomes:'+key, all(int(e['success']) in [0, 1] and 1 <= int(e['length']) <= 500 and (int(e['success']) == 1 or int(e['length']) == 500) for e in episodes))
            check('success_counts:'+key, success == rec['evaluation']['success_counts'])
            check('environment_steps:'+key, sum(int(e['length']) for e in episodes) == rec['evaluation']['environment_steps'])
            check('evaluation_did_not_change_learner:'+key, rec['evaluation_state_unchanged'])
            macro = st.mean(success.values())
            check('macro_recomputed:'+key, abs(macro-100*rec['evaluation']['macro_success']) < 1e-9)
            metrics[key] = {'macro': macro, **success}
            total_episodes += len(episodes)
        check('81600_recomputed_episodes', total_episodes == 81600)

        baseline, public, frozen, indexed = {}, {}, {}, {}
        for key, r in results.items():
            ctx = (r['suite'], r['original_seed'])
            if r.get('role') == 'baseline': baseline[ctx] = metrics[key]
            if r.get('role') == 'public': public[(*ctx, r['checkpoint_step'])] = metrics[key]
            if r['kind'] == 'rules': frozen[ctx] = r['rules']
            if r.get('role') == 'branch': indexed[(*ctx, r['continuation_label'], r['horizon'], r['allocation'])] = (r, metrics[key])
        expected = {(*x, a) for suite in TASKS for x in itertools.product([suite], SEEDS, REPEATS, [20000,40000]) for a in ['U']+['F_'+t for t in TASKS[suite]]}
        check('180_complete_branch_observations', set(indexed) == expected and len(indexed) == 180)
        branches = []
        for (suite, seed, repeat, h, a), (rec, m) in indexed.items():
            base = baseline[suite, seed]
            u = indexed[suite, seed, repeat, h, 'U'][1]
            row = {'suite': suite, 'original_seed': seed, 'checkpoint_step': 200000, 'continuation_label': repeat, 'horizon': h, 'allocation': a}
            for t in ['macro']+TASKS[suite]:
                row[t+'_pct'] = m[t]
                row[t+'_gain_pp'] = m[t]-base[t]
                row[t+'_vs_U_pp'] = m[t]-u[t]
            row['maximum_task_drop_pp'] = max(0, max(base[t]-m[t] for t in TASKS[suite]))
            branches.append(row)
        look = {(r['suite'], r['original_seed'], r['continuation_label'], r['horizon'], r['allocation']): r for r in branches}
        automatic_dir = folders['E3_analysis']
        automatic = csv_rows(automatic_dir/'branch_metrics.csv')
        check('automatic_row_count', len(automatic) == 180)
        for r in automatic:
            actual = look[r['suite'], int(r['original_seed']), int(r['continuation_label']), int(r['horizon']), r['allocation']]
            for left, right in [('macro_success_pct', 'macro_pct'), ('gain_pp', 'macro_gain_pp'), ('extra_gain_vs_U_pp', 'macro_vs_U_pp'), ('maximum_task_drop_pp','maximum_task_drop_pp')]+[(t+'_success_pct',t+'_pct') for t in TASKS[r['suite']]]:
                check('automatic_metric:'+str(tuple(actual[k] for k in ['suite','original_seed','continuation_label','horizon','allocation']))+':'+left, abs(float(r[left])-actual[right]) < 1e-8)

        allocation_summary, seed_effects, baselines, diagnostic_rules = [], [], [], []
        for suite in TASKS:
            tasks = TASKS[suite]
            names = ['U']+['F_'+t for t in tasks]
            for seed in SEEDS:
                baselines.append({'suite': suite, 'original_seed': seed, **{t+'_pct':v for t,v in baseline[suite,seed].items()}})
                now, prev = public[suite,seed,200000], public[suite,seed,100000]
                worst = [t for t in tasks if now[t] == min(now[k] for k in tasks)]
                improvement = {t: now[t]-prev[t] for t in tasks}
                best = [t for t in tasks if improvement[t] == max(improvement.values())]
                failure = 'F_'+worst[0] if len(worst) == 1 else 'U'
                progress = 'F_'+best[0] if len(best) == 1 and improvement[best[0]] > 0 else 'U'
                check(f'frozen_rules:{suite}:{seed}', frozen[suite,seed]['Failure'] == failure and frozen[suite,seed]['Progress'] == progress)
                rule_time = datetime.fromisoformat(frozen[suite,seed]['created_at'])
                check(f'rule_precedes_branch:{suite}:{seed}', all(rule_time < datetime.fromisoformat(r['completed_at']) for r in results.values() if r['kind']=='train' and r.get('checkpoint_step') == 200000 and r['suite']==suite and r['original_seed']==seed))
                diagnostic_rules.append({'suite':suite,'original_seed':seed,'Failure':failure,'Progress':progress,**{t+'_public_pct':now[t] for t in tasks}})
            for h, a in itertools.product([20000,40000], names):
                rs = [r for r in branches if (r['suite'],r['horizon'],r['allocation'])==(suite,h,a)]
                fields = [t+suffix for t in ['macro']+tasks for suffix in ['_pct','_gain_pp','_vs_U_pp']]+['maximum_task_drop_pp']
                by_seed = {s: [r for r in rs if r['original_seed']==s] for s in SEEDS}
                check(f'balanced_group:{suite}:{h}:{a}', all(len(v)==3 for v in by_seed.values()))
                vals = {s: st.mean(r['macro_vs_U_pp'] for r in by_seed[s]) for s in SEEDS}
                allocation_summary.append({'suite':suite,'horizon':h,'allocation':a,**{f:st.mean(st.mean(r[f] for r in by_seed[s]) for s in SEEDS) for f in fields},
                                           'positive_original_seeds':sum(v>1e-9 for v in vals.values()),'positive_continuations':sum(r['macro_vs_U_pp']>1e-9 for r in rs),**{f'seed_{s}_pp':v for s,v in vals.items()}})
                for s in SEEDS:
                    seed_effects.append({'suite':suite,'horizon':h,'allocation':a,'original_seed':s,**{f:st.mean(r[f] for r in by_seed[s]) for f in fields}})

        # Frozen rules and retrospective selectors. Exact ties prefer U then task order.
        decisions, horizon_contexts, reversals = [], [], []
        for suite in TASKS:
            names = ['U']+['F_'+t for t in TASKS[suite]]
            def choose(pool):
                scores = {a: st.mean(r['macro_pct'] for r in pool if r['allocation']==a) for a in names}
                return max(names, key=lambda a:scores[a])
            for seed in SEEDS:
                means = {h:{a:st.mean(look[suite,seed,r,h,a]['macro_pct'] for r in REPEATS) for a in names} for h in [20000,40000]}
                winners = {h:max(names,key=lambda a:means[h][a]) for h in means}
                horizon_contexts.append({'suite':suite,'original_seed':seed,'best_20k':winners[20000],'best_40k':winners[40000],
                                         'same_winner':winners[20000]==winners[40000],
                                         'best_40k_vs_U_pp':means[40000][winners[40000]]-means[40000]['U'],
                                         'selected_20k_at_40k_vs_U_pp':means[40000][winners[20000]]-means[40000]['U']})
                for a,b in itertools.combinations(names,2):
                    d20,d40=means[20000][a]-means[20000][b],means[40000][a]-means[40000][b]
                    reversals.append({'suite':suite,'original_seed':seed,'left':a,'right':b,'difference_20k_pp':d20,'difference_40k_pp':d40,'reversal':d20*d40<0,'both_over_2pp':abs(d20)>2 and abs(d40)>2})
                for h, repeat in itertools.product([20000,40000],REPEATS):
                    held_fixed=choose([r for r in branches if r['suite']==suite and r['original_seed']!=seed and r['horizon']==h])
                    cross=choose([r for r in branches if r['suite']==suite and r['original_seed']==seed and r['continuation_label']!=repeat and r['horizon']==h])
                    choices={'Uniform':'U','Failure':frozen[suite,seed]['Failure'],'Progress':frozen[suite,seed]['Progress'],
                             'LOSO_fixed':held_fixed,'cross_repeat_same_horizon':cross}
                    if 'F_DC' in names:choices['Fixed_DC']='F_DC'
                    if h==40000:
                        choices['cross_repeat_20k_to_40k']=choose([r for r in branches if r['suite']==suite and r['original_seed']==seed and r['continuation_label']!=repeat and r['horizon']==20000])
                    for rule,choice in choices.items():
                        value=look[suite,seed,repeat,h,choice]
                        decisions.append({'suite':suite,'original_seed':seed,'continuation_label':repeat,'horizon':h,'rule':rule,'choice':choice,'macro_pct':value['macro_pct'],'macro_gain_pp':value['macro_gain_pp'],'macro_vs_U_pp':value['macro_vs_U_pp']})
        rules=[]
        for suite,h,rule in sorted({(r['suite'],r['horizon'],r['rule']) for r in decisions}):
            rs=[r for r in decisions if (r['suite'],r['horizon'],r['rule'])==(suite,h,rule)]
            rules.append({'suite':suite,'horizon':h,'rule':rule,'macro_vs_U_pp':st.mean(r['macro_vs_U_pp'] for r in rs),
                          **{f'seed_{s}_pp':st.mean(r['macro_vs_U_pp'] for r in rs if r['original_seed']==s) for s in SEEDS}})
        prior_rules=csv_rows(automatic_dir/'held_out_rule_results.csv')
        rule_alias={'LOSO_global_fixed':'LOSO_fixed','LOSO_time_fixed':'LOSO_fixed','cross_repeat_diagnostic':'cross_repeat_same_horizon'}
        rule_lookup={(r['suite'],r['original_seed'],r['continuation_label'],r['horizon'],r['rule']):r for r in decisions}
        for r in prior_rules:
            k=(r['suite'],int(r['original_seed']),int(r['continuation_label']),int(r['horizon']),rule_alias.get(r['rule'],r['rule']))
            check('automatic_selector:'+str(k), rule_lookup[k]['choice']==r['choice'] and abs(rule_lookup[k]['macro_vs_U_pp']-float(r['extra_gain_vs_U_pp']))<1e-8)

        # Reference A is strictly E1 200k, with previously audited immutable input.
        a_path=ROOT/'16_e0_e2_results_analysis_v1/results/20261012T065024Z_70db8b08/branch_recomputed.csv'
        a_rows=csv_rows(a_path)
        check('frozen_A_reference',inputs[str(a_path)]=='6100a589c1f950ba55891299387f166b61c16fba973b452cc24987aef29e6ec2')
        a_rows=[r for r in a_rows if r['stage']=='E1' and int(r['checkpoint_step'])==200000 and int(r['horizon'])==40000]
        comparison=[]
        for a in ['U','F_DO','F_DC','F_WO','F_WC']:
            rs=[r for r in a_rows if r['allocation']==a]
            comparison.append({'suite':'A','allocation':a,'macro_pct':st.mean(float(r['macro_pct']) for r in rs),'macro_gain_pp':st.mean(float(r['macro_gain_pp']) for r in rs),'macro_vs_U_pp':st.mean(float(r['macro_vs_U_pp']) for r in rs)})
        comparison.extend({k:r[k] for k in ['suite','allocation','macro_pct','macro_gain_pp','macro_vs_U_pp']} for r in allocation_summary if r['horizon']==40000)

        interruptions=[]
        for attempt in sorted((campaign/'attempts').glob('E3*/*.json')):
            evidence=read(attempt)
            p=Path(evidence['output'])/'interruption.json'
            if p.exists():
                detail=read(p)
                interrupted_req=read(p.parent/'request.json')
                trace=csv_rows(p.parent/'train_metrics.csv')
                observed=max(int(r['step']) for r in trace)-interrupted_req['start_step']
                check('interrupted_lower_bound:'+evidence['job'],observed==detail['observed_training_steps_lower_bound'])
                interruptions.append({'job':evidence['job'],'attempt':evidence['attempt'],'observed_training_steps_lower_bound':observed,
                                      'unobserved_training_steps_upper_bound':detail['unobserved_training_steps_upper_bound'],
                                      'retained_output':evidence['output'],'recovery_succeeded':evidence['job'] in results})
        cost_summary={'completed_training_steps':sum(r['environment_steps'] for r in costs if r['kind']=='train'),
                      'completed_evaluation_episodes':sum(r['evaluation_episodes'] for r in costs),
                      'completed_environment_steps':sum(r['environment_steps'] for r in costs),
                      'completed_train_iterations':sum(r['train_iterations'] for r in costs),
                      'sum_completed_job_wall_hours':sum(r['wall_seconds'] for r in costs)/3600,
                      'interrupted_training_steps_lower_bound':sum(r['observed_training_steps_lower_bound'] for r in interruptions),
                      'interrupted_training_steps_upper_bound':sum(r['observed_training_steps_lower_bound']+r['unobserved_training_steps_upper_bound'] for r in interruptions)}
        check('planned_training_cost',cost_summary['completed_training_steps']==4800000)
        check('planned_evaluation_cost',cost_summary['completed_evaluation_episodes']==81600)
        check('consistent_package_versions',len({json.dumps(p,sort_keys=True) for p in packages})==1)
        tables={'branch_recomputed':branches,'allocation_summary':allocation_summary,'original_seed_effects':seed_effects,
                'baselines':baselines,'public_rules':diagnostic_rules,'rule_choices':decisions,'rule_summary':rules,
                'horizon_contexts':horizon_contexts,'pairwise_horizon_reversals':reversals,'composition_200k_comparison':comparison,'completed_job_costs':costs}
        for name,rows in tables.items():table(output/(name+'.csv'),rows)
        summary={'status':'verified','created_at':datetime.now(timezone.utc).isoformat(),'campaign_completed_at_utc':status['time'],
                 'campaign_completed_at_kst':datetime.fromisoformat(status['time']).astimezone(timezone(timedelta(hours=9))).isoformat(),
                 'completed_jobs':459,'branches':90,'branch_evaluations':180,'recomputed_evaluation_episodes':total_episodes,
                 'full_checkpoints_verified':len(checkpoints),'task_compositions':TASKS,'original_seeds':SEEDS,'continuation_labels':REPEATS,
                 'starting_checkpoint_steps':200000,'task_focus_fraction':0.625,'other_task_fraction':0.125,
                 'allocation_summary':allocation_summary,'baseline_by_seed':baselines,'rules':rules,'public_rules':diagnostic_rules,
                 'horizon_contexts':horizon_contexts,'rank_reversals':{s:{'pairs':sum(r['suite']==s for r in reversals),'reversals':sum(r['suite']==s and r['reversal'] for r in reversals)} for s in TASKS},
                 'costs':cost_summary,'interrupted_attempts':interruptions,'learner_packages':packages[0],
                 'analysis_python':platform.python_version(),'analysis_dependencies':'Python standard library only',
                 'checks_passed':len(checks),'analysis_wall_seconds':time.perf_counter()-started,'analysis_source_sha256':sha(Path(__file__)),
                 'new_training_steps':0,'new_evaluation_episodes':0,
                 'limits':['Original seed count is three per composition. Checkpoints and continuation repeats are nested.',
                           'Retrospective selectors share the fixed evaluation cases and do not charge diagnostic or offline preparation costs.',
                           'A/B/C differ in tasks and starting performance; B versus C is not a pure causal effect of semantic similarity.',
                           'No new claim of statistical significance or cross-benchmark generalization. The 20k-to-40k audit is post hoc.']}
        save(output/'analysis.json',summary)
        save(output/'input_hashes.json',inputs)
        save(output/'checks.json',checks)
        save(output/'campaign_status_snapshot.json',status)
        print(json.dumps({'output':str(output),'checks_passed':len(checks),'costs':cost_summary,'baseline':baselines,
                          'final':[r for r in allocation_summary if r['horizon']==40000],
                          'rules_40k':[r for r in rules if r['horizon']==40000],
                          'horizon_contexts':horizon_contexts,'interruptions':interruptions},ensure_ascii=False,indent=2))
    except Exception:
        save(output/'failure.json',{'traceback':traceback.format_exc(),'checks':checks,'inputs':inputs})
        raise


if __name__=='__main__':
    main()
