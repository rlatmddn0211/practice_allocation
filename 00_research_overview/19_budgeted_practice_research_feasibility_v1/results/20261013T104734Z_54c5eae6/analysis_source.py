"""Post-hoc horizon/selection audit. Standard library only; never trains an RL policy."""
from __future__ import annotations

import csv
import hashlib
import itertools
import json
import math
import platform
import shutil
import statistics as st
import time
import traceback
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
INPUT = ROOT / '16_e0_e2_results_analysis_v1/results/20261012T065024Z_70db8b08'
EXPECTED_BRANCH_HASH = '6100a589c1f950ba55891299387f166b61c16fba973b452cc24987aef29e6ec2'
ALLOCATIONS = ['U', 'F_DO', 'F_DC', 'F_WO', 'F_WC']
SEEDS = [11, 12, 13]
REPEATS = [2101, 2102, 2103]
TASKS = ['DO', 'DC', 'WO', 'WC']


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def table(path, rows):
    with path.open('x', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def ranks(values):
    return [1 + sum(y < x for y in values) + (sum(y == x for y in values) - 1) / 2 for x in values]


def correlation(xs, ys):
    x, y = ranks(xs), ranks(ys)
    dx, dy = [a - st.mean(x) for a in x], [a - st.mean(y) for a in y]
    den = math.sqrt(sum(a*a for a in dx) * sum(b*b for b in dy))
    return sum(a*b for a, b in zip(dx, dy)) / den if den else None


def choose(scores):
    # Fixed priority only breaks exact ties; Uniform wins if tied for the maximum.
    return max(ALLOCATIONS, key=lambda a: scores[a])


def main():
    start = time.perf_counter()
    run = HERE / 'results' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:8])
    run.mkdir(parents=True, exist_ok=False)
    shutil.copy2(__file__, run / 'analysis_source.py')
    inputs = {}
    checks = []

    def check(name, condition):
        checks.append({'name': name, 'passed': bool(condition)})
        if not condition:
            raise AssertionError(name)

    def read(p):
        inputs[str(p)] = digest(p)
        return json.loads(p.read_text(encoding='utf-8'))

    try:
        source = INPUT / 'branch_recomputed.csv'
        inputs[str(source)] = digest(source)
        check('immutable_v16_branch_hash', inputs[str(source)] == EXPECTED_BRANCH_HASH)
        with source.open(encoding='utf-8', newline='') as f:
            raw = list(csv.DictReader(f))
        rows = []
        for row in raw:
            if row['stage'] != 'E1':
                continue
            rows.append({k: (v if k in ['id', 'stage', 'allocation'] else float(v)) for k, v in row.items()})
        check('balanced_E1_180_observations', len(rows) == 180)
        lookup = {(int(r['original_seed']), int(r['checkpoint_step']), int(r['continuation_label']), int(r['horizon']), r['allocation']): r for r in rows}
        expected_keys = set(itertools.product(SEEDS, [200000, 400000], REPEATS, [20000, 40000], ALLOCATIONS))
        check('unique_complete_factorial', set(lookup) == expected_keys and len(lookup) == len(rows))
        check('macro_equal_task_weighting', all(abs(r['macro_pct'] - st.mean(r[t+'_pct'] for t in TASKS)) < 1e-9 for r in rows))
        check('uniform_relative_gain_zero', all(abs(r['macro_vs_U_pp']) < 1e-9 for r in rows if r['allocation'] == 'U'))

        def mean(s, cp, h, a, field='macro_vs_U_pp', repeats=REPEATS):
            return st.mean(lookup[s, cp, r, h, a][field] for r in repeats)

        contexts, comparisons, focus = [], [], []
        for s, cp in itertools.product(SEEDS, [200000, 400000]):
            early = {a: mean(s, cp, 20000, a) for a in ALLOCATIONS}
            late = {a: mean(s, cp, 40000, a) for a in ALLOCATIONS}
            a20, a40 = choose(early), choose(late)
            contexts.append({'original_seed': s, 'checkpoint_step': cp, 'spearman_20_to_40': correlation(list(early.values()), list(late.values())),
                             'best_20k': a20, 'best_40k': a40, 'same_best': a20 == a40,
                             'selected_at_20k_gain_at_40k_pp': late[a20], 'best_observed_40k_gain_pp': late[a40],
                             'descriptive_selection_gap_pp': late[a40] - late[a20]})
            for a, b in itertools.combinations(ALLOCATIONS, 2):
                d20, d40 = early[a] - early[b], late[a] - late[b]
                comparisons.append({'original_seed': s, 'checkpoint_step': cp, 'allocation_a': a, 'allocation_b': b,
                                    'difference_20k_pp': d20, 'difference_40k_pp': d40,
                                    'strict_reversal': d20*d40 < 0,
                                    'both_margins_over_2pp': abs(d20) > 2 and abs(d40) > 2})
            for a in ALLOCATIONS[1:]:
                own = a[2:]
                own_gain = mean(s, cp, 40000, a, own+'_vs_U_pp')
                macro = late[a]
                focus.append({'original_seed': s, 'checkpoint_step': cp, 'allocation': a,
                              'own_task_vs_U_pp': own_gain, 'macro_vs_U_pp': macro,
                              'other_tasks_contribution_to_macro_pp': macro-own_gain/4,
                              'own_positive_macro_negative': own_gain > 0 and macro < 0})

        decisions = []
        for s, cp, held in itertools.product(SEEDS, [200000, 400000], REPEATS):
            others = [r for r in REPEATS if r != held]
            other_seeds = [t for t in SEEDS if t != s]
            e = {a: mean(s, cp, 20000, a, repeats=others) for a in ALLOCATIONS}
            l = {a: mean(s, cp, 40000, a, repeats=others) for a in ALLOCATIONS}
            drift = {a: st.mean(mean(t, cp, 40000, a) - mean(t, cp, 20000, a) for t in other_seeds) for a in ALLOCATIONS}
            own = {a: (0 if a == 'U' else mean(s, cp, 20000, a, a[2:]+'_vs_U_pp', others)) for a in ALLOCATIONS}
            fixed = {a: st.mean(mean(t, cp, 40000, a) for t in other_seeds) for a in ALLOCATIONS}
            scoring = {'Uniform': {a: int(a == 'U') for a in ALLOCATIONS},
                       'short_20k_macro': e, 'long_40k_macro_reference': l,
                       'short_20k_own_task_only': own,
                       'short_20k_plus_other_seed_drift': {a: e[a]+drift[a] for a in ALLOCATIONS},
                       'other_seed_checkpoint_fixed': fixed}
            for rule, scores in scoring.items():
                selected = choose(scores)
                decisions.append({'rule': rule, 'original_seed': s, 'checkpoint_step': cp,
                                  'heldout_continuation': held, 'selected': selected,
                                  'test_40k_vs_U_pp': lookup[s, cp, held, 40000, selected]['macro_vs_U_pp']})
        summaries = []
        for rule in sorted({d['rule'] for d in decisions}):
            ds = [d for d in decisions if d['rule'] == rule]
            item = {'rule': rule, 'mean_vs_U_pp': st.mean(d['test_40k_vs_U_pp'] for d in ds),
                    'positive_decisions': sum(d['test_40k_vs_U_pp'] > 0 for d in ds), 'decisions': len(ds)}
            item.update({f'seed_{s}_pp': st.mean(d['test_40k_vs_U_pp'] for d in ds if d['original_seed'] == s) for s in SEEDS})
            summaries.append(item)
        check('18_nested_decisions_per_rule', all(s['decisions'] == 18 for s in summaries))
        reference = next(s for s in summaries if s['rule'] == 'long_40k_macro_reference')
        check('independent_replication_of_v17_reference', abs(reference['mean_vs_U_pp'] - 3.5694444444444446) < 1e-9)

        # Only completed E1 public measurements, never E3. Charge fresh measurements
        # at their actual environment steps; already-existing logs can be sunk inputs.
        active = read(ROOT / '13_e0_e3_autonomous_queue_v1/ACTIVE_CAMPAIGN.json')
        campaign = Path(active['campaign'])
        costs = []
        for p in sorted((campaign / 'completed').glob('E1*_pub*.json')):
            marker = read(p)
            q = Path(marker['result_ref']['path'])
            rec = read(q)
            check('result_hash_'+rec['id'], digest(q) == marker['result_ref']['sha256'])
            if rec['checkpoint_step'] not in [200000, 400000]:
                continue
            check('public_role_'+rec['id'], rec['role'] == 'public')
            ev = rec['evaluation']
            costs.append({'original_seed': rec['original_seed'], 'checkpoint_step': rec['checkpoint_step'],
                          'evaluation_episodes': ev['episodes'], 'environment_steps': ev['environment_steps'],
                          'environment_step_fraction_of_40k': ev['environment_steps']/40000,
                          'recorded_evaluation_seconds': ev['seconds']})
        check('six_public_starting_state_costs', len(costs) == 6)
        strict = [p for p in comparisons if p['difference_20k_pp'] != 0 and p['difference_40k_pp'] != 0]
        material = [p for p in comparisons if p['both_margins_over_2pp']]
        summary = {
            'status': 'verified', 'analysis_type': 'post_hoc_exploratory_no_new_RL',
            'independent_original_seeds': 3, 'nested_starting_states': 6,
            'tie_priority': ALLOCATIONS, 'contexts': contexts,
            'rank_reversals': {'all_pairs': len(comparisons), 'non_tied_pairs': len(strict),
                               'non_tied_reversals': sum(p['strict_reversal'] for p in strict),
                               'pairs_with_both_absolute_differences_over_2pp': len(material),
                               'reversals_with_both_absolute_differences_over_2pp': sum(p['strict_reversal'] for p in material)},
            'same_winner_contexts': sum(c['same_best'] for c in contexts),
            'own_positive_macro_negative_context_allocations': sum(f['own_positive_macro_negative'] for f in focus),
            'selection_rules': summaries,
            'public_evaluation_cost': {'min_steps': min(c['environment_steps'] for c in costs),
                                       'max_steps': max(c['environment_steps'] for c in costs),
                                       'mean_steps': st.mean(c['environment_steps'] for c in costs)},
            'cost_caveat': 'Selection rules use outcomes retrospectively on the same evaluation bank. Probe training, measurement and offline calibration costs are NOT charged. They are not deployment results.',
            'short_probe_cost_per_state': {'one_repeat_five_allocations_steps': 100000, 'two_repeats_five_allocations_steps': 200000},
            'limits': ['No cheap 0.5k-4k response checkpoints in these data.', 'No switching-policy outcome can be synthesized from static branches.',
                       'Continuation holdout does not hold out the evaluation cases or original state.', 'All hypotheses are post hoc; no confirmatory p-values.',
                       'A public measurement already present before the decision can be a common sunk input; a fresh measurement must be charged.'],
            'training_steps_run': 0, 'evaluation_episodes_run': 0, 'wall_seconds': time.perf_counter()-start,
            'python': platform.python_version(), 'dependencies': 'Python standard library only', 'source_sha256': digest(Path(__file__))}
        for name, values in [('context_horizon_ranking', contexts), ('pairwise_rank_reversals', comparisons),
                             ('focus_vs_global', focus), ('cross_repeat_choices', decisions),
                             ('cross_repeat_summary', summaries), ('public_diagnostic_costs', costs)]:
            table(run / (name+'.csv'), values)
        save(run/'summary.json', summary)
        save(run/'input_hashes.json', inputs)
        save(run/'checks.json', checks)
        print(json.dumps({'run': str(run), 'checks_passed': len(checks), 'contexts': contexts, 'rank_reversals': summary['rank_reversals'],
                          'selection_rules': summaries, 'public_cost': summary['public_evaluation_cost']}, ensure_ascii=False, indent=2))
    except Exception:
        save(run/'failure.json', {'traceback': traceback.format_exc(), 'checks': checks, 'inputs': inputs})
        raise


if __name__ == '__main__':
    main()
