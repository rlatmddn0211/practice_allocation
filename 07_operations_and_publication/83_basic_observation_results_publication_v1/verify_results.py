"""Recompute published labels and histories using files only, without a model."""
import argparse
import json
from pathlib import Path
import pandas as pd

V81 = '81_basic_sac_observation_campaign_v1'
V82 = '82_basic_observation_exploratory_report_v1'
CAMPAIGN = '20261102T085036Z_observation_8e858967'
A81 = '20261103T000632Z_f77754'
A82 = '20261103T000931Z_1c0dc354'


def verify(root):
    root = Path(root)
    if (root / '08_basic_learning_observations').is_dir():
        root = root / '08_basic_learning_observations'
    campaign = root / V81 / 'results' / CAMPAIGN
    analysis = root / V82 / 'results' / A82
    status = json.loads((campaign / 'FINAL_STATUS.json').read_text(encoding='utf-8'))
    assert status['completed_runs'] == 5
    assert status['evaluation_episodes'] == 3200
    assert status['costs']['all_attempt'] == 6604850
    assert status['independent_arithmetic_verification_passed'] is True
    raw = pd.read_parquet(analysis / 'evaluation_outcomes.parquet')
    curves = pd.read_csv(analysis / 'learning_curves_all_runs.csv')
    histories = pd.read_csv(analysis / 'case_histories_all.csv', dtype={'history': str})
    assert len(raw) == 3200 and len(curves) == 200 and len(histories) == 320
    # Both independently saved analyses must contain the identical original rows.
    other = pd.read_parquet(campaign / 'analysis' / A81 / 'per_case_results.parquet')
    pd.testing.assert_frame_equal(raw, other)
    keys = ['run_id', 'task_id', 'checkpoint_id', 'initial_case_id']
    assert not raw.duplicated(keys).any()
    assert raw['success_any'].isin([0, 1, False, True]).all()
    assert raw['success_final'].isin([0, 1, False, True]).all()
    case_sets = {}
    checked = 0
    for row in curves.itertuples(index=False):
        group = raw[(raw.run_id == row.run_id) & (raw.task_id == row.task_id)
                    & (raw.checkpoint_id == row.checkpoint_id)]
        assert len(group) == row.N == 16
        assert int(group.success_any.sum()) == row.successes
        assert int(group.success_final.sum()) == row.final_successes
        assert abs(row.success_pct - 100 * row.successes / 16) < 1e-10
        cases = frozenset(group.physical_case_id)
        assert len(cases) == 16
        if row.task_id in case_sets:
            assert case_sets[row.task_id] == cases
        case_sets[row.task_id] = cases
        checked += 1
    assert len(set.union(*(set(x) for x in case_sets.values()))) == 64
    for row in histories.itertuples(index=False):
        group = raw[(raw.run_id == row.run_id) & (raw.task_id == row.task_id)
                    & (raw.initial_case_id == row.initial_case_id)].sort_values('checkpoint_id')
        bits = [int(x) for x in group.success_any]
        assert ''.join(map(str, bits)) == row.history and len(bits) == 10
        assert sum(a == 0 and b == 1 for a, b in zip(bits, bits[1:])) == row.observed_gain_events
        assert sum(a == 1 and b == 0 for a, b in zip(bits, bits[1:])) == row.observed_loss_events
    final = curves[curves.checkpoint_id == 1000000].groupby('task_id').success_pct.mean().to_dict()
    assert final == {'BP': 92.5, 'DC': 100.0, 'DO': 0.0, 'PU': 1.25}
    return dict(passed=True, checked_cells=checked, evaluation_rows=3200,
                histories=320, unique_physical_cases=64, final_success_pct=final,
                new_environment_steps=0, new_policy_forwards=0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repository', type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()
    print(json.dumps(verify(args.repository), ensure_ascii=False))
