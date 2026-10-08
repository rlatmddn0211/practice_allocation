"""Lossless portable checkpoints and passive audits. No learner math changes."""
from __future__ import annotations

import csv
import json
import lzma
import pickle
import shutil
import time
from pathlib import Path

import numpy as np

from .core import (ROOT, SUITE, TASKS, ENV_NAMES, Config, capture_rng, restore_rng,
                   file_sha256, fingerprint, package_versions, source_hashes,
                   source_files, utc_now, write_json)
from .engine import Engine
from .learning import AuditedSAC, attach_logger


class IntegrityError(RuntimeError):
    pass


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def source_snapshot(output):
    for source in source_files():
        target = output / 'source_snapshot' / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    write_json(output / 'source_hashes.json', source_hashes())


def checkpoint_ref(directory):
    directory = Path(directory).resolve()
    return {'path': str(directory), 'manifest_sha256': file_sha256(directory / 'checkpoint_manifest.json')}


def save_portable(engine, directory):
    """All full learner/replay/collector/RNG state, compressed without rounding."""
    directory = Path(directory)
    collector = engine.boundary_state()
    directory.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    rng, before = capture_rng(), engine.fingerprints()
    engine.model.save(directory / 'model.zip')
    with lzma.open(directory / 'replay.pkl.xz', 'xb', preset=1) as stream:
        pickle.dump(engine.model.replay_buffer, stream, protocol=pickle.HIGHEST_PROTOCOL)
    with (directory / 'collector_and_rng.pkl').open('xb') as stream:
        pickle.dump({'config': engine.config.to_dict(), 'collector': collector, 'rng': rng}, stream,
                    protocol=pickle.HIGHEST_PROTOCOL)
    if engine.fingerprints() != before:
        raise IntegrityError('Saving changed the learner, collector, replay, or RNG.')
    files = {name: file_sha256(directory / name) for name in ['model.zip', 'replay.pkl.xz', 'collector_and_rng.pkl']}
    write_json(directory / 'checkpoint_manifest.json', {
        'schema_version': 2, 'codec': 'lzma-preset-1-lossless', 'created_at': utc_now(),
        'suite': SUITE, 'tasks': dict(zip(TASKS, ENV_NAMES)),
        'step': engine.model.num_timesteps, 'updates': engine.model._n_updates,
        'state_fingerprints': before, 'config_hash': fingerprint(engine.config.to_dict()),
        'packages': package_versions(), 'source_hashes': source_hashes(), 'files': files,
        'seconds': time.perf_counter() - started,
        'bytes': sum((directory / name).stat().st_size for name in files),
    })
    return checkpoint_ref(directory)


def load_portable(reference, config, costs, engine_class=Engine):
    directory = Path(reference['path'])
    path = directory / 'checkpoint_manifest.json'
    if file_sha256(path) != reference['manifest_sha256']:
        raise IntegrityError('Checkpoint manifest differs from the frozen input reference.')
    manifest = read_json(path)
    if manifest['schema_version'] not in (1, 2) or manifest['packages'] != package_versions():
        raise IntegrityError('Checkpoint dependency or schema mismatch.')
    if manifest.get('tasks', dict(zip(('DO', 'DC', 'WO', 'WC'),
                        ('drawer-open-v3', 'drawer-close-v3', 'window-open-v3', 'window-close-v3')))) != dict(zip(TASKS, ENV_NAMES)):
        raise IntegrityError('Task mapping differs from the parent checkpoint.')
    local = source_hashes()
    for name in ('learning.py', 'engine.py', 'environment.py', 'evaluation.py'):
        key = 'practice_allocation/' + name
        if manifest['source_hashes'][key] != local[key]:
            raise IntegrityError(f'Learner or environment implementation changed: {key}')
    for name, expected in manifest['files'].items():
        if Path(name).name != name or file_sha256(directory / name) != expected:
            raise IntegrityError(f'Checkpoint integrity failure: {name}')
    # Only repository-generated artifacts with a pinned manifest are accepted.
    with (directory / 'collector_and_rng.pkl').open('rb') as stream:
        state = pickle.load(stream)
    if fingerprint(state['config']) != manifest['config_hash']:
        raise IntegrityError('Parent configuration fingerprint differs.')
    metadata = {'version', 'diagnostic_bank_episodes_per_task', 'outcome_bank_episodes_per_task', 'bank_seed'}
    for name, value in config.to_dict().items():
        if name not in metadata and value != state['config'][name]:
            raise IntegrityError(f'Unexpected learner configuration change: {name}')
    model = AuditedSAC.load(directory / 'model.zip', device=config.device)
    if manifest['schema_version'] == 2:
        with lzma.open(directory / 'replay.pkl.xz', 'rb') as stream:
            model.replay_buffer = pickle.load(stream)
    else:
        model.load_replay_buffer(directory / 'replay.pkl')
    attach_logger(model)
    engine = engine_class(config, costs, model=model)
    engine.restore_boundary_state(state['collector'])
    restore_rng(state['rng'])
    if engine.fingerprints() != manifest['state_fingerprints']:
        raise IntegrityError('Restored full state differs from the checkpoint.')
    return engine


def load_banks(reference):
    path = Path(reference['path'])
    if file_sha256(path) != reference['sha256']:
        raise IntegrityError('Frozen evaluation bank changed.')
    return read_json(path)


def bank_sets(references):
    states, parameters, seeds = set(), set(), set()
    for reference in references:
        for entries in load_banks(reference).values():
            for row in entries:
                states.add(row['initial_state_hash'])
                parameters.add(row['task_parameter_hash'])
                seeds.add(row['seed'])
    return states, parameters, seeds


class AuditEngine(Engine):
    """Passive observation of resets; Engine.step and SB3.train remain unchanged."""
    audit_path = None
    forbidden = (set(), set(), set())

    def step(self):
        fresh = self.at_boundary
        record = super().step()
        if fresh:
            state = self.episode.initial_state
            parameter = fingerprint({key: state[key] for key in ('task', 'rand_vec', 'goal')})
            states, parameters, seeds = self.forbidden
            if (record['initial_state_hash'] in states or parameter in parameters or self.episode.seed in seeds):
                raise IntegrityError('Training reset overlaps a frozen evaluation bank.')
            if self.audit_path:
                row = {'step': record['step'], 'task': TASKS[record['task']], 'seed': self.episode.seed,
                       'initial_state_hash': record['initial_state_hash'], 'task_parameter_hash': parameter}
                new = not self.audit_path.exists()
                with self.audit_path.open('a', newline='', encoding='utf-8') as stream:
                    writer = csv.DictWriter(stream, fieldnames=list(row))
                    if new:
                        writer.writeheader()
                    writer.writerow(row)
        return record


def freeze_rules(current, previous=None, elapsed=None):
    rates = current['success_by_task']
    minimum = min(rates.values())
    worst = [task for task in TASKS if rates[task] == minimum]
    failure = 'F_' + worst[0] if len(worst) == 1 else 'U'
    progress, changes = 'U', None
    if previous is not None:
        changes = {task: (rates[task] - previous['success_by_task'][task]) / elapsed for task in TASKS}
        maximum = max(changes.values())
        best = [task for task in TASKS if abs(changes[task] - maximum) < 1e-15]
        if maximum > 0 and len(best) == 1:
            progress = 'F_' + best[0]
    return {'Failure': failure, 'Progress': progress, 'public_success': rates,
            'progress_per_training_step': changes, 'tie_policy': 'U',
            'frozen_before_branch_outcomes': True, 'created_at': utc_now()}
