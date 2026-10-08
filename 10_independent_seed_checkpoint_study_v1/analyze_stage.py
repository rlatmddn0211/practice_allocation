"""Predeclared descriptive contrasts. Original seeds are the training units."""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import numpy as np

from practice_allocation.core import file_sha256, write_json
from practice_allocation.study_io import read_json, IntegrityError


def mean(values):
    return float(np.mean(list(values)))


def save_csv(path, rows):
    if not rows:
        return
    keys = list(dict.fromkeys(key for row in rows for key in row))
    with path.open('x', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def episode_arrays(result):
    path = Path(result['episodes_path'])
    if file_sha256(path) != result['episodes_sha256']:
        raise IntegrityError('Evaluation episode evidence changed before analysis.')
    with path.open(encoding='utf-8', newline='') as stream:
        rows = list(csv.DictReader(stream))
    groups = defaultdict(list)
    for row in rows:
        groups[row['task']].append((int(row['episode_index']), row['initial_state_hash'], int(row['success'])))
    return {task: sorted(values) for task, values in groups.items()}


def conditional_case_interval(pairs, task=None):
    """Shared case resampling across trained policies, not an original-seed CI."""
    if not pairs:
        return None
    matrices = defaultdict(list)
    hashes = {}
    for left, right in pairs:
        lhs, rhs = episode_arrays(left), episode_arrays(right)
        for label in ([task] if task else lhs):
            ids_l = [(index, digest) for index, digest, _ in lhs[label]]
            ids_r = [(index, digest) for index, digest, _ in rhs[label]]
            if ids_l != ids_r or (label in hashes and hashes[label] != ids_l):
                raise IntegrityError('A paired contrast uses different evaluation cases.')
            hashes[label] = ids_l
            matrices[label].append(np.array([v for _, _, v in lhs[label]]) - np.array([v for _, _, v in rhs[label]]))
    rng = np.random.default_rng(95399)
    draws = np.zeros(2000)
    for label, values in matrices.items():
        per_case = np.mean(values, axis=0)
        indices = rng.integers(0, len(per_case), size=(2000, len(per_case)))
        draws += per_case[indices].mean(axis=1) / len(matrices)
    return {'conditional_case_bootstrap_95_interval_pp': (100 * np.quantile(draws, [.025, .975])).tolist(),
            'resamples': 2000, 'meaning': 'Evaluation-case uncertainty conditional on these trained policies; not training-seed uncertainty.'}


def analyze(request, output):
    records = []
    for reference in request['analysis_inputs']:
        if file_sha256(Path(reference['path'])) != reference['sha256']:
            raise IntegrityError('A completed input result changed before analysis.')
        records.append(read_json(reference['path']))
    stage = request['stage']
    branches = [r for r in records if r.get('role') == 'branch']
    baselines = {(r['suite'], r['original_seed'], r['checkpoint_step']): r
                 for r in records if r.get('role') == 'baseline'}
    rules = {(r['suite'], r['original_seed'], r['checkpoint_step']): r['rules']
             for r in records if r['kind'] == 'rules'}
    indexed = {(r['suite'], r['original_seed'], r['checkpoint_step'], r['continuation_label'], r['horizon'], r['allocation']): r
               for r in branches}
    if len(indexed) != len(branches):
        raise IntegrityError('Duplicate branch evaluation cells.')
    branch_rows = []
    for result in branches:
        suite, seed, cp = result['suite'], result['original_seed'], result['checkpoint_step']
        evaluation = result['evaluation']
        baseline = baselines[(suite, seed, cp)]['evaluation']
        uniform = indexed[(suite, seed, cp, result['continuation_label'], result['horizon'], 'U')]['evaluation']
        rates = evaluation['success_by_task']
        row = {key: result[key] for key in ('suite', 'original_seed', 'checkpoint_step', 'continuation_label', 'horizon', 'allocation')}
        row.update(macro_success_pct=100*evaluation['macro_success'],
                   gain_pp=100*(evaluation['macro_success']-baseline['macro_success']),
                   extra_gain_vs_U_pp=100*(evaluation['macro_success']-uniform['macro_success']),
                   worst_task_success_pct=100*min(rates.values()),
                   maximum_task_drop_pp=100*max(0, max(baseline['success_by_task'][task]-value for task, value in rates.items())))
        row.update({task+'_success_pct':100*value for task,value in rates.items()})
        row.update({task+'_gain_pp':100*(value-baseline['success_by_task'][task]) for task,value in rates.items()})
        row.update({task+'_extra_gain_vs_U_pp':100*(value-uniform['success_by_task'][task]) for task,value in rates.items()})
        branch_rows.append(row)
    save_csv(output / 'branch_metrics.csv', branch_rows)

    contrasts, summary, pairs_by = [], [], defaultdict(list)
    suites = sorted({r['suite'] for r in branches})
    for suite in suites:
        allocation_names = list(dict.fromkeys(r['allocation'] for r in branches if r['suite'] == suite))
        specs = [(candidate, 'U', None) for candidate in allocation_names if candidate != 'U']
        if 'F_DC' in allocation_names and 'F_DO' in allocation_names:
            specs.append(('F_DC', 'F_DO', 'DO'))
        if stage == 'E2':
            specs.append(('DC_plus_WO_minus', 'DC_minus_WO_plus', 'DO'))
        for lhs, rhs, task in specs:
            name = lhs+' minus '+rhs+' / '+(task or 'macro')
            for key, left in indexed.items():
                s, seed, cp, repeat, horizon, candidate = key
                if s != suite or candidate != lhs:
                    continue
                right = indexed[(s, seed, cp, repeat, horizon, rhs)]
                field_l, field_r = left['evaluation'], right['evaluation']
                value = ((field_l['success_by_task'][task]-field_r['success_by_task'][task]) if task
                         else (field_l['macro_success']-field_r['macro_success']))
                cohort = 'replication_1903_1905' if stage == 'E0' and repeat >= 1903 else ('discovery_1901_1902' if stage == 'E0' else 'independent_pretraining')
                contrasts.append(dict(suite=suite, contrast=name, original_seed=seed, checkpoint_step=cp,
                                      continuation_label=repeat, horizon=horizon, cohort=cohort, difference_pp=100*value))
                pairs_by[(suite, name, horizon, cohort, task)].append((left, right))
    save_csv(output / 'paired_contrasts.csv', contrasts)
    groups = defaultdict(list)
    for row in contrasts:
        groups[(row['suite'], row['contrast'], row['horizon'], row['cohort'])].append(row)
        if stage == 'E0':
            groups[(row['suite'], row['contrast'], row['horizon'], 'combined_descriptive')].append(row)
    seed_rows = []
    for (suite, name, horizon, cohort), values in groups.items():
        by_seed = defaultdict(list)
        for value in values:
            by_seed[value['original_seed']].append(value['difference_pp'])
        effects = {seed: mean(items) for seed, items in by_seed.items()}
        for seed, effect in effects.items():
            seed_rows.append(dict(suite=suite, contrast=name, horizon=horizon, cohort=cohort, original_seed=seed, difference_pp=effect))
        summary.append(dict(suite=suite, contrast=name, horizon=horizon, cohort=cohort,
                            original_seed_count=len(effects), equal_seed_mean_pp=mean(effects.values()),
                            seed_min_pp=min(effects.values()), seed_max_pp=max(effects.values()),
                            positive_seed_count=sum(v>0 for v in effects.values())))
    cohort_order = {'replication_1903_1905':0, 'discovery_1901_1902':1, 'combined_descriptive':2}
    summary.sort(key=lambda row:(cohort_order.get(row['cohort'], 0), row['suite'], -row['horizon'], row['contrast']))
    save_csv(output / 'original_seed_contrasts.csv', seed_rows)
    save_csv(output / 'contrast_summary.csv', summary)
    primary_cases = []
    for (suite, name, horizon, cohort, task), pairs in pairs_by.items():
        is_primary = ((stage in ('E0', 'E1') and name == 'F_DC minus U / macro') or
                      (stage == 'E2' and name == 'DC_plus_WO_minus minus DC_minus_WO_plus / DO'))
        if horizon == 40000 and is_primary:
            primary_cases.append(dict(suite=suite, contrast=name, cohort=cohort, **conditional_case_interval(pairs, task)))

    selection = []
    if stage in ('E1', 'E3'):
        contexts = sorted({(r['suite'], r['original_seed'], r['checkpoint_step']) for r in branches})
        for suite, seed, cp in contexts:
            names = ['U'] + ['F_'+task for task in baselines[(suite, seed, cp)]['evaluation']['success_by_task']]
            repeats = sorted({r['continuation_label'] for r in branches if (r['suite'], r['original_seed'], r['checkpoint_step']) == (suite,seed,cp)})
            for horizon in (20000, 40000):
                def choose(pool):
                    scores = {candidate:mean(r['evaluation']['macro_success'] for r in pool if r['allocation']==candidate) for candidate in names}
                    return max(names, key=lambda candidate:scores[candidate])
                others = [r for r in branches if r['suite']==suite and r['original_seed']!=seed and r['horizon']==horizon]
                fixed_global = choose(others)
                fixed_time = choose([r for r in others if r['checkpoint_step']==cp])
                for repeat in repeats:
                    within = [r for r in branches if (r['suite'],r['original_seed'],r['checkpoint_step'],r['horizon']) == (suite,seed,cp,horizon) and r['continuation_label']!=repeat]
                    cross = choose(within)
                    choices = {'Uniform':'U', 'Failure':rules[(suite,seed,cp)]['Failure'], 'Progress':rules[(suite,seed,cp)]['Progress'],
                               'LOSO_global_fixed':fixed_global, 'LOSO_time_fixed':fixed_time, 'cross_repeat_diagnostic':cross}
                    if 'F_DC' in names:
                        choices['Fixed_DC'] = 'F_DC'
                    held_cross = indexed[(suite,seed,cp,repeat,horizon,cross)]['evaluation']['macro_success']
                    uniform = indexed[(suite,seed,cp,repeat,horizon,'U')]['evaluation']['macro_success']
                    for rule, candidate in choices.items():
                        score = indexed[(suite,seed,cp,repeat,horizon,candidate)]['evaluation']['macro_success']
                        selection.append(dict(suite=suite,original_seed=seed,checkpoint_step=cp,horizon=horizon,
                                              continuation_label=repeat,rule=rule,choice=candidate,macro_success_pct=100*score,
                                              extra_gain_vs_U_pp=100*(score-uniform),regret_to_cross_repeat_pp=100*(held_cross-score)))
        save_csv(output / 'held_out_rule_results.csv', selection)
        rule_groups = defaultdict(list)
        for row in selection:
            rule_groups[(row['suite'],row['horizon'],row['rule'],row['original_seed'])].append(row)
        save_csv(output / 'original_seed_rule_results.csv', [dict(suite=s,horizon=h,rule=r,original_seed=seed,
            extra_gain_vs_U_pp=mean(v['extra_gain_vs_U_pp'] for v in vals),
            regret_to_cross_repeat_pp=mean(v['regret_to_cross_repeat_pp'] for v in vals))
            for (s,h,r,seed),vals in rule_groups.items()])

    failure_audit = None
    if stage == 'E0':
        public = next(r for r in records if r.get('role')=='public')
        arrays = episode_arrays(public)
        rng = np.random.default_rng(95099)
        labels = list(arrays)
        scores = np.array([np.array([v for _,_,v in arrays[task]])[rng.integers(0,len(arrays[task]),size=(10000,20))].mean(axis=1) for task in labels])
        counts = defaultdict(int)
        for column in scores.T:
            lowest = np.flatnonzero(column==column.min())
            counts['F_'+labels[lowest[0]] if len(lowest)==1 else 'U'] += 1
        failure_audit = {'historical_frozen_failure': 'F_DO', 'new_100_case_rules':next(iter(rules.values())),
                         '20_case_bootstrap_choice_probability':{k:v/10000 for k,v in counts.items()},
                         'resamples':10000,'interpretation':'Measurement sensitivity from the new public bank; does not relabel the historical choice.'}
    report = {'stage':stage, 'branch_evaluations':len(branches), 'summaries':summary,
              'conditional_evaluation_uncertainty':primary_cases, 'failure_audit':failure_audit,
              'training_inference_unit':'original pretraining seed; checkpoints and continuation repeats nested',
              'limitations':['E0 has only one original parent.', 'Three new original seeds give limited training-variability evidence.',
                             'Cross-repeat choices use branch outcomes and are retrospective diagnostics, not deployable selectors.',
                             'E2 estimates resource substitution, not isolated direct transfer.',
                             'E3 uses custom MetaWorld subsets and does not identify a pure semantic-similarity effect.']}
    if stage == 'E3':
        report['A_200k_reference'] = request.get('suite_A_reference')
        reference=request['suite_A_reference']
        if file_sha256(Path(reference['path']))!=reference['sha256']:
            raise IntegrityError('E1 reference changed before E3 comparison.')
        original=read_json(reference['path'])
        original_dir=Path(original['analysis']).parent
        with (original_dir/'branch_metrics.csv').open(encoding='utf-8',newline='') as stream:
            reference_rows=[row for row in csv.DictReader(stream) if int(row['checkpoint_step'])==200000]
        composition=reference_rows+branch_rows
        grouped=defaultdict(list)
        for row in composition:
            if int(row['horizon'])==40000:
                grouped[(row['suite'],int(row['original_seed']),row['allocation'])].append(row)
        composition_summary=[]
        anchors=[]
        for (suite,seed,candidate),items in grouped.items():
            composition_summary.append(dict(suite=suite,original_seed=seed,allocation=candidate,
                macro_success_pct=mean(float(v['macro_success_pct']) for v in items),
                gain_pp=mean(float(v['gain_pp']) for v in items),
                extra_gain_vs_U_pp=mean(float(v['extra_gain_vs_U_pp']) for v in items)))
            if suite in ('B','C') and candidate in ('U','F_DO','F_PU','F_BP'):
                for task in ('DO','PU','BP'):
                    anchors.append(dict(suite=suite,original_seed=seed,allocation=candidate,task=task,
                        gain_pp=mean(float(v[task+'_gain_pp']) for v in items),
                        extra_gain_vs_U_pp=mean(float(v[task+'_extra_gain_vs_U_pp']) for v in items)))
        save_csv(output/'composition_original_seed_results.csv',composition_summary)
        save_csv(output/'shared_task_changes.csv',anchors)
        with (original_dir/'held_out_rule_results.csv').open(encoding='utf-8',newline='') as stream:
            previous_rules=[row for row in csv.DictReader(stream) if int(row['checkpoint_step'])==200000]
        save_csv(output/'composition_rule_results.csv',previous_rules+selection)
        report['composition_scope']='A uses E1 200k only. Compare within-suite effects and rules; B/C anchors are DO, PU, BP. Raw macro levels do not rank benchmarks.'
    write_json(output / 'analysis.json', report)
    lines = [f'# {stage} automatic analysis', '', 'All planned cells are retained, including floors, ceilings and negative effects.', '',
             'Units: percentage points. Training variability is reported across original seeds; evaluation cases are not extra training seeds.', '',
             '| Suite | Cohort | Contrast | Horizon | Original seeds | Mean pp | Seed range pp |', '|---|---|---|---:|---:|---:|---|']
    for row in summary:
        lines.append(f"| {row['suite']} | {row['cohort']} | {row['contrast']} | {row['horizon']} | {row['original_seed_count']} | {row['equal_seed_mean_pp']:.2f} | {row['seed_min_pp']:.2f} to {row['seed_max_pp']:.2f} |")
    lines += ['', 'See branch_metrics.csv for absolute gains and deterioration, paired_contrasts.csv for matched cells, and analysis.json for scope and conditional measurement uncertainty.', '',
              'No automatic claim of statistical significance is made. A favorable allocation does not by itself establish a need for an adaptive selector.']
    (output / 'REPORT.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return {'report':str(output / 'REPORT.md'), 'analysis':str(output / 'analysis.json'), 'completed_branch_evaluations':len(branches)}
