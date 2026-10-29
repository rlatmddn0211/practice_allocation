"""Read-only E3 replay exposure audit, independent of every RL implementation."""
import csv
import hashlib
import itertools
import json
import platform
import shutil
import statistics
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TASKS = {'B': ['DO', 'DC', 'PU', 'BP'], 'C': ['DO', 'PP', 'PU', 'BP']}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    started = time.perf_counter()
    output = HERE / 'results' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_replay_') + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    shutil.copy2(__file__, output / 'audit_source.py')
    hashes, checks, rows = {}, [], []

    def read(path):
        hashes[str(path)] = sha(path)
        return path.read_text(encoding='utf-8')

    def check(name, valid):
        checks.append({'name': name, 'passed': bool(valid)})
        if not valid:
            raise AssertionError(name)

    def save(name, data):
        with (output / name).open('x', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    try:
        active = json.loads(read(ROOT / '13_e0_e3_autonomous_queue_v1/ACTIVE_CAMPAIGN.json'))
        campaign = Path(active['campaign'])
        plan = json.loads(read(campaign / 'plan.json'))
        integrity = json.loads(read(campaign / 'plan_integrity.json'))
        check('frozen_plan', hashes[str(campaign / 'plan.json')] == integrity['sha256'])
        for relative in ['practice_allocation/learning.py', 'practice_allocation/engine.py']:
            path = ROOT / '12_task_composition_study_v1' / relative
            read(path)
            check('frozen_instrumentation:' + relative, hashes[str(path)] == plan['sources']['E3'][relative])

        def job(key):
            marker = json.loads(read(campaign / 'completed' / (key + '.json')))
            path = Path(marker['result_ref']['path'])
            result = json.loads(read(path))
            check('result_hash:' + key, hashes[str(path)] == marker['result_ref']['sha256'] and result['id'] == key)
            records = list(csv.DictReader(read(path.parent / 'train_metrics.csv').splitlines()))
            check('endpoint:' + key, int(records[-1]['step']) == result['step'])
            manifest_path = Path(result['checkpoint']['path']) / 'checkpoint_manifest.json'
            manifest = json.loads(read(manifest_path))
            check('manifest:' + key, hashes[str(manifest_path)] == result['checkpoint']['manifest_sha256'])
            check('updates_match:' + key, int(records[-1]['updates']) == manifest['updates'])
            return result, records[-1]

        for suite, seed in itertools.product(TASKS, [11, 12, 13]):
            _, parent = job(f'E3_{suite}_s{seed}_pre200')
            for repeat, allocation in itertools.product([2301, 2302, 2303], ['U'] + ['F_' + t for t in TASKS[suite]]):
                previous = parent
                for horizon in [20000, 40000]:
                    key = f'E3_{suite}_s{seed}_c200_r{repeat}_{allocation}_t{horizon//1000}'
                    result, end = job(key)
                    check('buffer_size:' + key, int(end['replay_size']) == 100000)
                    delta = {t: int(end['sampled_' + t]) - int(previous['sampled_' + t]) for t in TASKS[suite]}
                    collected = {t: int(end['collected_' + t]) - int(previous['collected_' + t]) for t in TASKS[suite]}
                    check('collected:' + key, collected == result['collected_this_job'] and sum(collected.values()) == 20000)
                    check('sampled_batch_count:' + key, sum(delta.values()) == 20000 * 256 and all(v >= 0 for v in delta.values()))
                    cumulative = {t: int(end['sampled_' + t]) - int(parent['sampled_' + t]) for t in TASKS[suite]}
                    focus = allocation[2:] if allocation != 'U' else None
                    rows.append({'suite': suite, 'original_seed': seed, 'continuation_label': repeat,
                                 'allocation': allocation, 'interval_start': horizon - 20000, 'interval_end': horizon,
                                 'sampled_total': sum(delta.values()),
                                 'focus_collection_pct': 100 * collected[focus] / sum(collected.values()) if focus else None,
                                 'focus_sampled_pct': 100 * delta[focus] / sum(delta.values()) if focus else None,
                                 'cumulative_focus_sampled_pct': 100 * cumulative[focus] / sum(cumulative.values()) if focus else None,
                                 **{t + '_sampled_pct': 100 * delta[t] / sum(delta.values()) for t in TASKS[suite]}})
                    previous = end
        check('all_180_training_intervals', len(rows) == 180)
        summaries = []
        for horizon in [20000, 40000]:
            group = [r for r in rows if r['interval_end'] == horizon and r['allocation'] != 'U']
            check('72_focus_intervals:' + str(horizon), len(group) == 72)
            summaries.append({'interval_start': horizon - 20000, 'interval_end': horizon, 'focus_branches': len(group),
                              'collection_pct': statistics.mean(r['focus_collection_pct'] for r in group),
                              'mean_sampled_pct': statistics.mean(r['focus_sampled_pct'] for r in group),
                              'min_sampled_pct': min(r['focus_sampled_pct'] for r in group),
                              'max_sampled_pct': max(r['focus_sampled_pct'] for r in group),
                              'mean_cumulative_sampled_pct': statistics.mean(r['cumulative_focus_sampled_pct'] for r in group)})
        with (output / 'replay_exposure.csv').open('x', encoding='utf-8', newline='') as f:
            fields = list(dict.fromkeys(k for r in rows for k in r))
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        save('analysis.json', {'status': 'verified', 'created_at': datetime.now(timezone.utc).isoformat(),
                              'summary': summaries, 'checks_passed': len(checks), 'input_hashes': hashes,
                              'source_sha256': sha(Path(__file__)), 'python': platform.python_version(),
                              'dependencies': 'Python standard library only', 'new_training_steps': 0,
                              'new_evaluation_episodes': 0, 'wall_seconds': time.perf_counter() - started,
                              'interpretation': 'Actual cumulative sampled counters were differenced at full interval boundaries. Exposure is not gradient magnitude or evidence that replay lag causes performance differences. E3 has one replay size, so it cannot identify a causal effect of replay capacity.',
                              'input_audit_notes': 'Earlier exploratory reads of config.py and configs/base.json found no such files; configuration is defined in core.py and stored in frozen configs. No inputs changed.'})
        save('checks.json', checks)
        print(json.dumps({'output': str(output), 'checks_passed': len(checks), 'summary': summaries}, indent=2))
    except Exception:
        save('failure.json', {'traceback': traceback.format_exc(), 'checks': checks, 'input_hashes': hashes})
        raise


if __name__ == '__main__':
    main()
