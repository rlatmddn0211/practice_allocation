"""Read-only scientific aggregation, independent of the frozen F08 implementation."""
import csv
import hashlib
import importlib.metadata
import json
import math
import os
import platform
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


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def save(path, value):
    with path.open('x', encoding='utf-8') as f:
        json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write('\n')


def table(path, rows):
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with path.open('x', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def main():
    start, cpu = time.perf_counter(), time.process_time()
    out = HERE/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_review_'+uuid.uuid4().hex[:8])
    out.mkdir(parents=True)
    print(out, flush=True)
    (out/'sources').mkdir()
    sources = [*HERE.glob('*.py'), HERE/'protocol.json']
    for p in sources:
        shutil.copy2(p, out/'sources'/p.name)
    save(out/'source_hashes.json', {p.name: sha(p) for p in sources})
    save(out/'runtime.json', {'python': sys.version, 'executable': sys.executable,
        'platform': platform.platform(), 'argv': sys.argv,
        'packages': {p: importlib.metadata.version(p) for p in ['numpy', 'matplotlib']}})
    inputs, checks, summary = {}, [], {'status': 'failed'}

    def check(name, ok):
        checks.append({'check': name, 'passed': bool(ok)})
        if not ok:
            raise AssertionError(name)

    def near(name, a, b):
        check(name, math.isclose(float(a), float(b), abs_tol=1e-9, rel_tol=1e-9))

    def pin(path, expected=None):
        path = Path(path)
        if not path.is_absolute():
            path = ROOT/path
        payload = path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if expected is not None:
            check('input digest '+str(path.relative_to(ROOT)), digest == expected)
        inputs[path.relative_to(ROOT).as_posix()] = digest
        dest = out/'inputs'/(digest+path.suffix)
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open('xb') as f:
                f.write(payload)
        return dest

    def read(path, expected=None):
        return json.loads(pin(path, expected).read_text(encoding='utf-8-sig'))

    def rows(path, expected=None):
        with pin(path, expected).open(encoding='utf-8-sig', newline='') as f:
            return list(csv.DictReader(f))

    try:
        import numpy as np
        cfg = read(HERE/'protocol.json')
        cam, ad, prior = [ROOT/cfg[k] for k in ['campaign', 'f08_analysis', 'prior_review']]
        p = read(ROOT/'32_dose_order_intervention_v1/protocol.json')
        plan = read(cam/'plan.json', read(cam/'plan_integrity.json')['sha256'])
        completed = read(cam/'COMPLETE.json')
        status, cs = read(cam/'STATUS.json'), read(cam/'summary.json')
        check('full campaign completed', status['state'] == cs['status'] == 'completed' and cs['jobs_completed'] == 424)
        original = read(ad/'summary.json')
        verify_old = read(ROOT/cfg['f08_verification']/'summary.json')
        check('original analysis and verification passed', original['checks_failed'] == verify_old['checks_failed'] == 0)
        check('144 checkpoint verification receipt', verify_old['full_checkpoints_verified'] == 144)
        for file, digest in plan['stage_hashes']['F08'].items():
            pin(ROOT/'32_dose_order_intervention_v1'/file, digest)
        for k in ['prior_review', 'prior_verification']:
            old = read(ROOT/cfg[k]/'summary.json')
            check('prior review successful '+k, old['status'] == 'completed' and old['checks_failed'] == 0)
        for file in ['comparisons.csv', 'F07_reference_rules.csv', 'common_baseline_review.csv']:
            retained = rows(prior/file)
            table(out/('prior_'+file), retained)
        for name in ['report_ko.md', 'factor_status_ko.md']:
            pin(ROOT/'36_all_candidate_evidence_review_v1'/name)
        pin(ROOT/'README.md')

        y, parent, identities, train, costs, provenance = {}, {}, {}, {}, [], []
        for job in plan['jobs']:
            if job['stage'] != 'F08' or job['kind'] not in ['train', 'evaluate', 'bank']:
                continue
            marker = read(cam/'completed'/(job['id']+'.json'))
            result = read(marker['result_ref']['path'], marker['result_ref']['sha256'])
            attempt = Path(marker['result_ref']['path']).parent
            cost = read(attempt/'costs.json')
            check('completed production job '+job['id'], cost['status'] == 'completed' and not cost['technical_smoke'])
            costs.append({'id': job['id'], 'kind': job['kind'], 'suite': job['suite'],
                'environment_steps': cost['costs']['environment_steps'], 'train_iterations': cost['costs']['train_iterations'],
                'wall_seconds': cost['wall_seconds'], 'cpu_seconds': cost['cpu_seconds'], 'path': str(attempt/'costs.json')})
            if job['kind'] == 'train':
                q = read(attempt/'request.json')
                rr = rows(attempt/'train_episodes.csv')
                check('40 full episodes '+job['id'], len(rr) == 40 and all(int(x['length']) == 500 for x in rr))
                check('20k segment '+job['id'], cost['costs']['environment_steps'] == cost['costs']['train_iterations'] == 20000)
                check('no switch reset '+job['id'], q['start_branch'] == (job['horizon'] == 20000))
                train.setdefault((job['suite'], job['condition'], job['continuation']), {})[job['horizon']] = (rr, q, result)
                continue
            if job['kind'] != 'evaluate':
                continue
            rr = rows(result['episodes_path'], result['episodes_sha256'])
            near('evaluation cost '+job['id'], sum(int(x['length']) for x in rr), cost['costs']['environment_steps'])
            if job['bank_kind'] != 'outcome':
                continue
            a = np.full((4, 100), -1, dtype=int)
            case_ids = {}
            for row in rr:
                task, index, success = row['task'], int(row['episode_index']), int(row['success'])
                ti = p['suites'][job['suite']].index(task)
                check('unique binary case '+job['id'], a[ti, index] == -1 and success in (0, 1))
                a[ti, index] = success
                case_ids[task, index] = (row['seed'], row['initial_state_hash'])
            check('complete outcome bank '+job['id'], len(rr) == 400 and (a >= 0).all())
            if job['suite'] in identities:
                check('matched physical cases '+job['id'], case_ids == identities[job['suite']])
            else:
                identities[job['suite']] = case_ids
            if job.get('condition'):
                key = (job['suite'], job['condition'], job['continuation'])
                check('unique branch '+str(key), key not in y)
                y[key] = a
            else:
                parent[job['suite']] = a
            provenance.append({'id': job['id'], 'path': result['episodes_path'], 'sha256': result['episodes_sha256']})
        check('all 72 branches and 3 parents', len(y) == len(train) == 72 and len(parent) == 3)
        allocations = []
        for (suite, cond, rep), segments in train.items():
            first, last = segments[20000], segments[40000]
            check('same branch checkpoint '+str((suite, cond, rep)), last[1]['parent'] == first[2]['checkpoint'])
            rr = first[0]+last[0]
            tasks, (i, j) = p['suites'][suite], p['pairs'][suite]
            counts = Counter(r['task'] for r in rr)
            if cond.startswith('dose'):
                focus, other = {'dose25': (20, 20), 'dose4375': (35, 15), 'dose625': (50, 10), 'dose8125': (65, 5)}[cond]
                expected = {t: focus if t == i else other for t in tasks}
            else:
                expected = {t: 30 if t in (i, j) else 10 for t in tasks}
                for b in range(10):
                    actual = Counter(r['task'] for r in rr[b*8:(b+1)*8])
                    target = {t: 1 for t in tasks}
                    if cond == 'mixture':
                        target[i] = target[j] = 3
                    else:
                        focal = (i if b < 5 else j) if cond == 'i_then_j' else (j if b < 5 else i) if cond == 'j_then_i' else (i if b % 2 == 0 else j)
                        target[focal] = 5
                    check('4k block quota '+str((suite, cond, rep, b)), actual == target)
            check('total task exposure '+str((suite, cond, rep)), counts == expected)
            for task in tasks:
                allocations.append({'suite': suite, 'condition': cond, 'continuation': rep, 'task': task, 'episodes': counts[task], 'steps': counts[task]*500})
        table(out/'outcome_provenance.csv', provenance)
        table(out/'training_allocations.csv', allocations)
        table(out/'F08_cost_receipts.csv', costs)

        parent_rows, branch, conditions = [], [], []
        old = {(r['suite'], r['condition'], int(r['continuation'])): r for r in rows(ad/'branch_scores.csv')}
        for suite, arr in parent.items():
            for ti, task in enumerate(p['suites'][suite]):
                parent_rows.append({'suite': suite, 'task': task, 'success_pp': float(arr[ti].sum()), 'macro_pp': float(arr.mean()*100)})
        for key, arr in y.items():
            suite, cond, rep = key
            r = {'suite': suite, 'condition': cond, 'continuation': rep,
                 'macro_success_pp': float(arr.mean()*100), 'absolute_gain_pp': float((arr-parent[suite]).mean()*100),
                 'worst_task_drop_pp': float((parent[suite].mean(1)-arr.mean(1)).max()*100)}
            r.update({t+'_success_pp': float(arr[n].sum()) for n, t in enumerate(p['suites'][suite])})
            for k, v in r.items():
                if k.endswith('_pp'):
                    near('branch metric '+str(key)+k, v, old[key][k])
            branch.append(r)
        for suite in p['suites']:
            for cond in p['conditions']:
                selected = [r for r in branch if r['suite'] == suite and r['condition'] == cond]
                r = {'suite': suite, 'condition': cond, 'parent_macro_pp': float(parent[suite].mean()*100),
                     'mean_macro_pp': statistics.mean(x['macro_success_pp'] for x in selected),
                     'mean_gain_pp': statistics.mean(x['absolute_gain_pp'] for x in selected),
                     'min_macro_pp': min(x['macro_success_pp'] for x in selected),
                     'max_macro_pp': max(x['macro_success_pp'] for x in selected),
                     'below_parent_branches': sum(x['absolute_gain_pp'] < -1e-9 for x in selected)}
                r.update({t+'_mean_success_pp': statistics.mean(x[t+'_success_pp'] for x in selected) for t in p['suites'][suite]})
                conditions.append(r)
        table(out/'parent_scores.csv', parent_rows)
        table(out/'branch_scores.csv', branch)
        table(out/'condition_means.csv', conditions)

        coeff = {
            'dose81_minus25': {'dose8125': 1, 'dose25': -1},
            'dose4375_nonlinearity': {'dose4375': 1, 'dose25': -2/3, 'dose8125': -1/3},
            'dose625_nonlinearity': {'dose625': 1, 'dose25': -1/3, 'dose8125': -2/3},
            'forward_minus_reverse': {'i_then_j': 1, 'j_then_i': -1},
            'forward_minus_mixture': {'i_then_j': 1, 'mixture': -1},
            'reverse_minus_mixture': {'j_then_i': 1, 'mixture': -1},
            'alternate_minus_mixture': {'alternate4k': 1, 'mixture': -1}}
        original_contrasts = {(r['suite'], r['contrast']): r for r in rows(ad/'contrasts.csv')}
        details, contrasts, task_means = [], [], []
        rng = np.random.default_rng(p['bootstrap_seed'])
        for suite in p['suites']:
            draws = rng.multinomial(100, np.full(100, .01), size=(5000, 4))
            for name, co in coeff.items():
                diffs = [sum(weight*y[suite, cond, rep] for cond, weight in co.items()) for rep in p['continuations']]
                points = [float(a.mean()*100) for a in diffs]
                avg = np.mean(diffs, axis=0)
                point = float(avg.mean()*100)
                bootstrap = np.sum(draws*avg[None], axis=(1, 2))/4
                lo, hi = [float(v) for v in np.quantile(bootstrap, [.025, .975])]
                orig = original_contrasts[suite, name]
                near('contrast '+suite+name, point, orig['difference_pp'])
                near('case CI lower '+suite+name, lo, orig['case_only_lo_pp'])
                near('case CI upper '+suite+name, hi, orig['case_only_hi_pp'])
                loo = [(sum(points)-v)/2 for v in points]
                r = {'suite': suite, 'contrast': name, 'mean_difference_pp': point,
                     'case_only_lo_pp': lo, 'case_only_hi_pp': hi,
                     'same_sign_repeats': sum(v > 1e-9 for v in points) if point >= 0 else sum(v < -1e-9 for v in points),
                     'min_repeat_pp': min(points), 'max_repeat_pp': max(points),
                     'min_leave_one_out_mean_pp': min(loo), 'max_leave_one_out_mean_pp': max(loo)}
                for rep, value, leave_out, arr in zip(p['continuations'], points, loo, diffs):
                    r['r'+str(rep)+'_pp'] = value
                    for ti, task in enumerate(p['suites'][suite]):
                        details.append({'suite': suite, 'contrast': name, 'continuation': rep, 'macro_difference_pp': value,
                            'mean_without_this_repeat_pp': leave_out, 'task': task, 'task_difference_pp': float(arr[ti].mean()*100),
                            'macro_contribution_pp': float(arr[ti].mean()*25)})
                for ti, task in enumerate(p['suites'][suite]):
                    task_means.append({'suite': suite, 'contrast': name, 'task': task,
                        'task_difference_pp': float(avg[ti].mean()*100), 'macro_contribution_pp': float(avg[ti].mean()*25)})
                contrasts.append(r)
        table(out/'contrast_review.csv', contrasts)
        table(out/'contrast_task_repeat.csv', details)
        table(out/'contrast_task_means.csv', task_means)

        cost_summary = []
        for kind in ['bank', 'train', 'evaluate']:
            subset = [r for r in costs if r['kind'] == kind]
            cost_summary.append({'kind': kind, 'jobs': len(subset), **{k: sum(r[k] for r in subset) for k in ['environment_steps', 'train_iterations', 'wall_seconds', 'cpu_seconds']}})
        table(out/'F08_cost_summary.csv', cost_summary)
        near('F08 training budget', sum(r['train_iterations'] for r in costs), 2880000)
        near('F08 evaluation steps', next(r['environment_steps'] for r in cost_summary if r['kind'] == 'evaluate'), original['measured_evaluation_steps'])
        for suite in p['suites']:
            near('task contributions sum '+suite, sum(r['macro_contribution_pp'] for r in task_means if r['suite'] == suite and r['contrast'] == 'forward_minus_reverse'), next(r['mean_difference_pp'] for r in contrasts if r['suite'] == suite and r['contrast'] == 'forward_minus_reverse'))
        summary.update({'status': 'completed', 'original_seed_count_per_suite': 1, 'original_seed': 12,
            'continuations': p['continuations'], 'raw_outcome_rows': 30000, 'raw_training_episode_rows': 5760,
            'branches': len(y), 'predefined_contrasts': len(contrasts),
            'parent_macro_pp': {s: float(a.mean()*100) for s, a in parent.items()},
            'below_parent_by_suite': {s: sum(r['absolute_gain_pp'] < -1e-9 for r in branch if r['suite'] == s) for s in p['suites']},
            'F08_costs': cost_summary,
            'prior_original_seeds': [11, 12, 13], 'prior_receipts_reused_not_new_replications': True,
            'original_checkpoint_hashes_reverified': False,
            'full_checkpoint_verification_reused': str(ROOT/cfg['f08_verification']/'summary.json'),
            'new_environment_steps': 0, 'new_persistent_updates': 0, 'new_cloned_updates': 0,
            'scientific_confirmation': False, 'cost_inclusive_policy_tested': False})
    except Exception:
        summary['traceback'] = traceback.format_exc()
        raise
    finally:
        summary.update({'wall_seconds': time.perf_counter()-start, 'cpu_seconds': time.process_time()-cpu,
                        'checks_passed': sum(c['passed'] for c in checks), 'checks_failed': sum(not c['passed'] for c in checks)})
        save(out/'input_hashes.json', inputs)
        save(out/'checks.json', checks)
        save(out/'summary.json', summary)


if __name__ == '__main__':
    main()
