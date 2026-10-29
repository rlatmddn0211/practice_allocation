"""One immutable stage-1 job; preserved SAC, real checkpoints and passive audits."""
import argparse
import csv
import json
import os
import time
import traceback
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--request', required=True)
    q = json.loads(Path(ap.parse_args().request).read_text(encoding='utf-8-sig'))
    os.environ['PRACTICE_SUITE'] = 'B'
    os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
    worker_lock = None
    if q.get('worker_lock'):
        import msvcrt
        worker_lock = Path(q['worker_lock']).open('a+b')
        if worker_lock.tell() == 0: worker_lock.write(b'0'); worker_lock.flush()
        while True:
            try:
                worker_lock.seek(0); msvcrt.locking(worker_lock.fileno(), msvcrt.LK_NBLCK, 1); break
            except OSError: time.sleep(5)
    from dataclasses import replace
    import numpy as np
    from practice_allocation.core import (ROOT, TASKS, Config, configure_runtime, runtime_manifest,
        write_json, source_hashes, derived_seed, fingerprint, file_sha256, utc_now)
    from practice_allocation.environment import CostCounter
    from practice_allocation.evaluation import build_banks, evaluate_model
    from practice_allocation.learning import learning_state
    from practice_allocation.study_io import (IntegrityError, AuditEngine, source_snapshot,
        load_portable, save_portable, load_banks, bank_sets)
    from practice_allocation.schedules import full_plan
    out = Path(q['output']); out.mkdir(parents=True, exist_ok=True)
    if (out/'runtime.json').exists() or (out/'result.json').exists():
        raise IntegrityError('An immutable attempt cannot be reused')
    source_snapshot(out)
    config = replace(Config.load(ROOT/'configs/learner.json'), seed=q['original_seed'],
                     bank_seed=q.get('bank_seed', 424200))
    if q['technical_smoke']: config = replace(config, outcome_bank_episodes_per_task=2)
    config.validate()
    costs = CostCounter(); engine = None; error = None; result = {}
    started = time.perf_counter(); cpu = time.process_time()
    def progress(**kw):
        with (out/'progress.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps({'time': utc_now(), 'costs': costs.snapshot(), **kw})+'\n')
    try:
        if source_hashes() != q['source_hashes']: raise IntegrityError('Frozen source changed')
        configure_runtime(config)
        write_json(out/'runtime.json', runtime_manifest(config, 'stage1_selection_value'))
        progress(event='start')
        if q['kind'] == 'bank':
            banks = build_banks(config, costs)
            ref = q['historical_forbidden']
            if file_sha256(Path(ref['path'])) != ref['sha256']: raise IntegrityError('Historical exclusions changed')
            old = json.loads(Path(ref['path']).read_text(encoding='utf-8'))
            forbidden = [set(old[k]) for k in ('states', 'parameters', 'seeds')]
            for dest, extra in zip(forbidden, bank_sets(q.get('other_banks', []))): dest.update(extra)
            for rows in banks.values():
                for e in rows:
                    if any(v in s for v, s in zip((e['initial_state_hash'], e['task_parameter_hash'], e['seed']), forbidden)):
                        raise IntegrityError('New evaluation bank overlaps history or another parent')
            write_json(out/'evaluation_banks.json', banks)
            result = {'bank': {'path': str(out/'evaluation_banks.json'), 'sha256': file_sha256(out/'evaluation_banks.json')}}
        else:
            engine = AuditEngine(config, costs) if q['kind'] == 'init' else load_portable(q['parent'], config, costs, AuditEngine)
            if q['kind'] in ('init', 'train'):
                counts = [0]*4
                if q['kind'] == 'train':
                    if engine.model.num_timesteps != q['start_step']: raise IntegrityError('Wrong checkpoint step')
                    if q.get('start_branch'):
                        learned = fingerprint(learning_state(engine.model))
                        engine.start_branch(q['condition'], q['continuation_rng_seed'])
                        if fingerprint(learning_state(engine.model)) != learned: raise IntegrityError('Branch changed learned state')
                    expected_condition = q.get('condition', 'U')
                    if engine.schedule.candidate != expected_condition: raise IntegrityError('Schedule differs')
                    engine.forbidden = bank_sets(q['all_banks']); engine.audit_path = out/'training_reset_audit.csv'
                    before = engine.collected_steps.copy()
                    for offset in range(0, q['steps'], 1000):
                        engine.train_steps(min(1000, q['steps']-offset), q['id'], out/'train_metrics.csv', episodes_path=out/'train_episodes.csv')
                        progress(event='training', step=engine.model.num_timesteps)
                    counts = (engine.collected_steps-before).tolist()
                    with (out/'train_episodes.csv').open(encoding='utf-8') as f: episodes = list(csv.DictReader(f))
                    actual = [TASKS.index(e['task']) for e in episodes]
                    if q.get('condition'):
                        order = full_plan(q['condition'], derived_seed(q['continuation_rng_seed'], 10), 'B')
                        first = (q['start_step']-q['parent_step'])//500
                        expected = order[first:first+q['steps']//500]
                        if actual != expected: raise IntegrityError('Episode order differs from schedule')
                    else:
                        expected = actual
                        if counts != [q['steps']//4]*4: raise IntegrityError('Pretraining is not uniform')
                    if counts != (np.bincount(expected, minlength=4)*500).tolist(): raise IntegrityError('Quota mismatch')
                    updates = max(0, q['start_step']+q['steps']-config.learning_starts)-max(0, q['start_step']-config.learning_starts)
                    if costs.train_iterations != updates or costs.environment_steps != q['steps']: raise IntegrityError('Update/environment budget mismatch')
                result = {'checkpoint': save_portable(engine, out/'checkpoint'), 'step': engine.model.num_timesteps,
                          'collected': dict(zip(TASKS, counts)), 'episode_order_verified': True}
            elif q['kind'] == 'evaluate':
                bank = load_banks(q['bank']); before = engine.fingerprints()
                evaluation = evaluate_model(engine.model, bank['outcome'], costs, out/'evaluation_episodes.csv', q['id'], context='stage1_selection_value')
                if engine.fingerprints() != before: raise IntegrityError('Evaluation changed training state')
                evaluation['purpose'] = 'technical smoke only' if q['technical_smoke'] else 'Final research scoring; no online feedback'
                result = {'evaluation': evaluation, 'evaluation_state_unchanged': True,
                          'episodes_path': str(out/'evaluation_episodes.csv'), 'episodes_sha256': file_sha256(out/'evaluation_episodes.csv')}
            else: raise IntegrityError('Unknown job kind')
        progress(event='complete')
    except BaseException as exc:
        error = {'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc(),
                 'retryable': isinstance(exc, OSError) and not isinstance(exc, FileExistsError)}
        write_json(out/'error.json', error); traceback.print_exc()
    finally:
        if engine is not None: engine.close()
        write_json(out/'costs.json', {'status': 'failed' if error else 'completed', 'costs': costs.snapshot(),
                   'wall_seconds': time.perf_counter()-started, 'cpu_seconds': time.process_time()-cpu,
                   'technical_smoke': q['technical_smoke'], 'gpu_busy_seconds': None})
    if error: return 1
    write_json(out/'result.json', {'id': q['id'], 'kind': q['kind'], 'original_seed': q['original_seed'],
        **{k: q[k] for k in ('condition', 'continuation', 'horizon', 'role') if k in q}, **result})
    return 0


if __name__ == '__main__': raise SystemExit(main())
