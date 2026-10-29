"""Execute one immutable job. The queue starts a fresh process for every job."""
from __future__ import annotations

import argparse
import csv
import json
import os
import time
import traceback
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding='utf-8'))
    # One worker per campaign, including an orphan adopted after a controller restart.
    worker_lock = None
    if request.get('worker_lock'):
        import msvcrt
        worker_lock = Path(request['worker_lock']).open('a+b')
        if Path(request['worker_lock']).stat().st_size == 0:
            worker_lock.write(b'0')
            worker_lock.flush()
        while True:
            try:
                worker_lock.seek(0)
                msvcrt.locking(worker_lock.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                time.sleep(5)
        # OS releases the lock if the worker exits or is terminated.
    os.environ['PRACTICE_SUITE'] = request['suite']
    os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
    from dataclasses import replace
    import numpy as np
    from practice_allocation.core import (ROOT, TASKS, ENV_NAMES, ALLOCATIONS, Config,
        configure_runtime, runtime_manifest, write_json, utc_now, file_sha256, source_hashes)
    from practice_allocation.engine import Engine
    from practice_allocation.environment import CostCounter
    from practice_allocation.evaluation import build_banks, evaluate_model
    from practice_allocation.learning import learning_state
    from practice_allocation.core import fingerprint
    from practice_allocation.study_io import (IntegrityError, AuditEngine, read_json,
        source_snapshot, load_portable, save_portable, load_banks, bank_sets, freeze_rules)

    output = Path(request['output'])
    output.mkdir(parents=True, exist_ok=True)
    if (output / 'runtime.json').exists() or (output / 'result.json').exists():
        raise IntegrityError('An attempt output directory cannot be reused.')
    source_snapshot(output)
    config = replace(Config.load(ROOT / 'configs/learner.json'), seed=request['original_seed'],
                     bank_seed=request.get('bank_seed', 95001))
    if request.get('technical_smoke'):
        config = replace(config, diagnostic_bank_episodes_per_task=2, outcome_bank_episodes_per_task=2)
    config.validate()
    costs, engine, result, error = CostCounter(), None, None, None
    started = time.perf_counter()
    def progress(event, **extra):
        with (output / 'progress.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'time': utc_now(), 'event': event, 'costs': costs.snapshot(), **extra}) + '\n')
    try:
        if source_hashes() != request['source_hashes']:
            raise IntegrityError('Source changed after the campaign plan was frozen.')
        configure_runtime(config)
        write_json(output / 'runtime.json', runtime_manifest(config, request['stage']))
        kind = request['kind']
        progress('start', kind=kind)
        if kind == 'bank':
            banks = build_banks(config, costs)
            old_states, old_parameters, old_seeds = bank_sets(request.get('previous_banks', []))
            for path in request.get('previous_train_audits', []):
                with Path(path).open(encoding='utf-8', newline='') as stream:
                    for row in csv.DictReader(stream):
                        old_states.add(row['initial_state_hash'])
                        if row.get('task_parameter_hash'):
                            old_parameters.add(row['task_parameter_hash'])
                        if row.get('seed'):
                            old_seeds.add(int(row['seed']))
            for rows in banks.values():
                for row in rows:
                    if (row['initial_state_hash'] in old_states or row['task_parameter_hash'] in old_parameters or row['seed'] in old_seeds):
                        raise IntegrityError('New bank overlaps an earlier evaluation or training reset.')
            path = output / 'evaluation_banks.json'
            write_json(path, banks)
            result = {'bank': {'path': str(path), 'sha256': file_sha256(path)},
                      'cases_per_task': config.outcome_bank_episodes_per_task,
                      'disjoint_from_previous_banks_and_training': True}
        elif kind == 'rules':
            def public(reference):
                if file_sha256(Path(reference['path'])) != reference['sha256']:
                    raise IntegrityError('Public diagnostic input changed.')
                return read_json(reference['path'])['evaluation']
            current = public(request['current_public'])
            previous = public(request['previous_public']) if request.get('previous_public') else None
            result = {'rules': freeze_rules(current, previous, request.get('elapsed'))}
        elif kind == 'analysis':
            from analyze_stage import analyze
            result = analyze(request, output)
        else:
            if kind == 'init':
                engine = AuditEngine(config, costs)
            else:
                engine = load_portable(request['parent'], config, costs, AuditEngine)
            if kind in ('init', 'train'):
                if kind == 'train':
                    if engine.model.num_timesteps != request['start_step']:
                        raise IntegrityError('Training parent step differs from the planned boundary.')
                    if request.get('start_branch'):
                        learned = fingerprint(learning_state(engine.model))
                        engine.start_branch(request['allocation'], request['continuation_rng_seed'])
                        if learned != fingerprint(learning_state(engine.model)):
                            raise IntegrityError('Branch initialization changed learned state.')
                    engine.forbidden = bank_sets(request['all_banks'])
                    engine.audit_path = output / 'training_reset_audit.csv'
                    before = engine.collected_steps.copy()
                    total = request['steps']
                    if total % 4000:
                        raise IntegrityError('Training must contain complete allocation blocks.')
                    for index in range(0, total, 4000):
                        engine.train_steps(4000, request['id'], output / 'train_metrics.csv',
                                           episodes_path=output / 'train_episodes.csv')
                        progress('training', step=engine.model.num_timesteps)
                    counts = (engine.collected_steps - before).tolist()
                    expected = (np.array(ALLOCATIONS[engine.schedule.candidate]) * (total // 4000) * 500).tolist()
                    if counts != expected:
                        raise IntegrityError(f'Incorrect collection quotas: {counts} != {expected}')
                    if request['stage'] == 'E2' and counts[0] != counts[3]:
                        raise IntegrityError('E2 target/control task collection counts changed.')
                else:
                    counts = [0] * 4
                result = {'checkpoint': save_portable(engine, output / 'checkpoint'),
                          'step': engine.model.num_timesteps, 'collected_this_job': dict(zip(TASKS, counts)),
                          'training_reset_audit': str(output / 'training_reset_audit.csv') if kind == 'train' else None}
            elif kind == 'evaluate':
                banks = load_banks(request['bank'])
                before = engine.fingerprints()
                evaluation = evaluate_model(engine.model, banks[request['bank_kind']], costs,
                                            output / 'evaluation_episodes.csv', request['id'],
                                            context=request['stage'])
                evaluation['purpose'] = ('technical smoke; no scientific inference' if request.get('technical_smoke')
                                          else request['stage'] + ' ' + request['bank_kind'])
                if engine.fingerprints() != before:
                    raise IntegrityError('Evaluation changed training state or RNG.')
                result = {'evaluation': evaluation, 'evaluation_state_unchanged': True,
                          'episodes_path': str(output / 'evaluation_episodes.csv'),
                          'episodes_sha256': file_sha256(output / 'evaluation_episodes.csv')}
            else:
                raise IntegrityError(f'Unknown job kind: {kind}')
        progress('complete')
    except BaseException as exc:
        error = {'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc(),
                 'retryable': isinstance(exc, OSError) and not isinstance(exc, FileExistsError)}
        write_json(output / 'error.json', error)
        traceback.print_exc()
    finally:
        if engine is not None:
            engine.close()
        write_json(output / 'costs.json', {'costs': costs.snapshot(), 'wall_seconds': time.perf_counter() - started,
                   'success': error is None, 'technical_smoke': bool(request.get('technical_smoke'))})
    if error:
        return 1
    write_json(output / 'result.json', {'id': request['id'], 'stage': request['stage'], 'suite': request['suite'],
               'kind': request['kind'], 'original_seed': request['original_seed'], 'completed_at': utc_now(),
               **{key: request[key] for key in ('role', 'allocation', 'continuation_label', 'checkpoint_step', 'horizon') if key in request},
               **result})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
