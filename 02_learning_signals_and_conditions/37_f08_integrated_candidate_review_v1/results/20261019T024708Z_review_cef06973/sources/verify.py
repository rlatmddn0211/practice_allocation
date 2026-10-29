"""Exact-count independent checks of the new descriptive tables; no simulator."""
import argparse
import csv
import hashlib
import json
import math
import shutil
import sys
import time
import traceback
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from fractions import Fraction as F
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write(p, x):
    with p.open('x', encoding='utf-8') as f:
        json.dump(x, f, indent=2, ensure_ascii=False)
        f.write('\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--analysis', required=True)
    args = parser.parse_args()
    ad = Path(args.analysis).resolve()
    start, cpu = time.perf_counter(), time.process_time()
    out = HERE/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_verify_'+uuid.uuid4().hex[:8])
    out.mkdir(parents=True)
    print(out, flush=True)
    (out/'sources').mkdir()
    src = [*HERE.glob('*.py'), HERE/'protocol.json']
    for p in src:
        shutil.copy2(p, out/'sources'/p.name)
    write(out/'source_hashes.json', {p.name: sha(p) for p in src})
    write(out/'runtime.json', {'python': sys.version, 'executable': sys.executable, 'argv': sys.argv, 'dependencies': 'standard library only'})
    checks, used, summary = [], {}, {'status': 'failed'}

    def check(name, ok):
        checks.append({'check': name, 'passed': bool(ok)})
        if not ok:
            raise AssertionError(name)

    def near(name, a, b):
        check(name, math.isclose(float(a), float(b), abs_tol=1e-9, rel_tol=1e-9))

    def read(p):
        used[str(p)] = sha(p)
        return json.loads(p.read_text(encoding='utf-8-sig'))

    def rows(p):
        used[str(p)] = sha(p)
        with p.open(encoding='utf-8-sig', newline='') as f:
            return list(csv.DictReader(f))

    try:
        cfg = read(HERE/'protocol.json')
        manifest = read(ad/'input_hashes.json')
        for rel, digest in manifest.items():
            snapshot = ad/'inputs'/(digest+Path(rel).suffix)
            check('retained input '+rel, sha(snapshot) == digest)
            if rel != 'README.md':
                check('frozen source still matches '+rel, sha(ROOT/rel) == digest)
        old = read(ad/'summary.json')
        check('completed analysis', old['status'] == 'completed' and old['checks_failed'] == 0)
        p = read(ROOT/'32_dose_order_intervention_v1/protocol.json')
        all_counts, parents, n = {}, {}, 0
        for r in rows(ad/'outcome_provenance.csv'):
            path = Path(r['path'])
            check('raw outcome hash '+r['id'], sha(path) == r['sha256'])
            rr = rows(path)
            counts = Counter()
            ids = set()
            for z in rr:
                key = (z['task'], int(z['episode_index']))
                check('distinct case', key not in ids)
                ids.add(key)
                counts[z['task']] += int(z['success'])
            check('400 outcomes', len(rr) == len(ids) == 400)
            n += len(rr)
            parts = r['id'].split('_')
            suite = parts[1]
            if parts[2] == 'base':
                parents[suite] = counts
            else:
                rep, cond = int(parts[2][1:]), '_'.join(parts[3:-1])
                all_counts[suite, cond, rep] = counts
        check('30000 raw rows', n == 30000)
        check('72 branch count records', len(all_counts) == 72)
        score = {k: F(sum(v.values()), 4) for k, v in all_counts.items()}
        parent_score = {k: F(sum(v.values()), 4) for k, v in parents.items()}
        for r in rows(ad/'branch_scores.csv'):
            key = (r['suite'], r['condition'], int(r['continuation']))
            near('macro exact count', r['macro_success_pp'], score[key])
            near('parent gain exact count', r['absolute_gain_pp'], score[key]-parent_score[key[0]])
            for task, count in all_counts[key].items():
                near('task exact count', r[task+'_success_pp'], count)
            near('worst loss', r['worst_task_drop_pp'], max(parents[key[0]][t]-all_counts[key][t] for t in p['suites'][key[0]]))
        for r in rows(ad/'condition_means.csv'):
            vals = [score[r['suite'], r['condition'], rep] for rep in p['continuations']]
            near('mean score', r['mean_macro_pp'], sum(vals)/3)
            near('mean gain', r['mean_gain_pp'], sum(vals)/3-parent_score[r['suite']])
            near('min score', r['min_macro_pp'], min(vals))
            near('max score', r['max_macro_pp'], max(vals))
            near('below parent', r['below_parent_branches'], sum(v < parent_score[r['suite']] for v in vals))
            for task in p['suites'][r['suite']]:
                near('task mean score', r[task+'_mean_success_pp'], F(sum(all_counts[r['suite'], r['condition'], rep][task] for rep in p['continuations']), 3))

        def difference(name, a):
            if name == 'dose81_minus25': return a('dose8125')-a('dose25')
            if name == 'dose4375_nonlinearity': return a('dose4375')-(2*a('dose25')+a('dose8125'))/3
            if name == 'dose625_nonlinearity': return a('dose625')-(a('dose25')+2*a('dose8125'))/3
            if name == 'forward_minus_reverse': return a('i_then_j')-a('j_then_i')
            if name == 'forward_minus_mixture': return a('i_then_j')-a('mixture')
            if name == 'reverse_minus_mixture': return a('j_then_i')-a('mixture')
            if name == 'alternate_minus_mixture': return a('alternate4k')-a('mixture')
            raise ValueError(name)

        for r in rows(ad/'contrast_review.csv'):
            s, name = r['suite'], r['contrast']
            diffs = [difference(name, lambda cond: score[s, cond, rep]) for rep in p['continuations']]
            near('exact contrast', r['mean_difference_pp'], sum(diffs)/3)
            for rep, d in zip(p['continuations'], diffs):
                near('exact repeat', r['r'+str(rep)+'_pp'], d)
            loo = [(sum(diffs)-d)/2 for d in diffs]
            near('leave one out min', r['min_leave_one_out_mean_pp'], min(loo))
            near('leave one out max', r['max_leave_one_out_mean_pp'], max(loo))
        for r in rows(ad/'contrast_task_means.csv'):
            s, task, name = r['suite'], r['task'], r['contrast']
            values = [difference(name, lambda c: F(all_counts[s, c, rep][task])) for rep in p['continuations']]
            near('task contrast exact', r['task_difference_pp'], sum(values)/3)
            near('macro contribution exact', r['macro_contribution_pp'], sum(values)/12)
        for r in rows(ad/'contrast_task_repeat.csv'):
            s, task, name, rep = r['suite'], r['task'], r['contrast'], int(r['continuation'])
            value = difference(name, lambda c: F(all_counts[s, c, rep][task]))
            near('repeat task contrast', r['task_difference_pp'], value)
            near('repeat task contribution', r['macro_contribution_pp'], value/4)
        for f in ['comparisons.csv', 'F07_reference_rules.csv', 'common_baseline_review.csv']:
            check('prior evidence preserved '+f, rows(ad/('prior_'+f)) == rows(ROOT/cfg['prior_review']/f))
        costs = rows(ad/'F08_cost_receipts.csv')
        for row in rows(ad/'F08_cost_summary.csv'):
            subset = [r for r in costs if r['kind'] == row['kind']]
            near('cost job counts', row['jobs'], len(subset))
            for field in ['environment_steps', 'train_iterations', 'wall_seconds', 'cpu_seconds']:
                near('cost sum '+field, row[field], sum(F(r[field]) for r in subset))
        summary.update({'status': 'completed', 'analysis': str(ad), 'raw_outcome_rows_recomputed': n,
                        'branch_scores_recomputed': 72, 'predefined_contrasts_recomputed': 21,
                        'prior_screens_verification_reused': True, 'bootstrap_reused_from_analysis': True,
                        'new_environment_steps': 0, 'new_learner_updates': 0, 'scientific_confirmation': False})
    except Exception:
        summary['traceback'] = traceback.format_exc()
        raise
    finally:
        summary.update({'wall_seconds': time.perf_counter()-start, 'cpu_seconds': time.process_time()-cpu,
                        'checks_passed': sum(c['passed'] for c in checks), 'checks_failed': sum(not c['passed'] for c in checks)})
        write(out/'input_hashes.json', used)
        write(out/'checks.json', checks)
        write(out/'summary.json', summary)


if __name__ == '__main__':
    main()
