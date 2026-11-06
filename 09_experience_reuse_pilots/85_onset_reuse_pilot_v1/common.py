"""File-only preparation utilities; importing this module does not load a policy or simulator."""
from __future__ import annotations
import hashlib
import importlib.metadata
import io
import json
import os
import shutil
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CAMPAIGN_ID = '20261102T085036Z_observation_8e858967'
CAMPAIGN = ROOT / '81_basic_sac_observation_campaign_v1/results' / CAMPAIGN_ID
SITE = ROOT / '13_e0_e3_autonomous_queue_v1/.venv/Lib/site-packages'
RUNS = ['R01', 'R02', 'R03', 'R04', 'R05']

def guard_file_only():
    forbidden = {'torch', 'mujoco', 'metaworld', 'gym', 'gymnasium', 'stable_baselines3', 'tensorflow', 'jax'}
    def hook(event, args):
        if event == 'import' and str(args[0]).split('.')[0] in forbidden:
            raise RuntimeError('File-only preparation forbids runtime/model import: ' + str(args[0]))
    sys.addaudithook(hook)

def utc(): return datetime.now(timezone.utc).isoformat()
def clean(value):
    if isinstance(value, dict): return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [clean(v) for v in value]
    if isinstance(value, Path): return str(value)
    if hasattr(value, 'tolist'): return clean(value.tolist())
    if isinstance(value, float) and not __import__('math').isfinite(value): return None
    return value

def save(path, value, replace=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not replace: raise FileExistsError(path)
    tmp = path.with_name(path.name + '.partial')
    with tmp.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(clean(value), f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n'); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)

def load(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path):
    with Path(path).open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()
def digest_bytes(data): return hashlib.sha256(data).hexdigest()

def new_output(role):
    out = HERE / 'results' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + role + '_' + uuid.uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    snapshot = out / 'source_snapshot'; snapshot.mkdir()
    for path in HERE.iterdir():
        if path.is_file() and path.suffix in ('.py', '.json', '.md') and not path.name.startswith('LATEST'):
            shutil.copy2(path, snapshot / path.name)
    if (HERE/'baseline81').exists():
        shutil.copytree(HERE/'baseline81',snapshot/'baseline81',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    save(out / 'source_hashes.json', {p.relative_to(snapshot).as_posix(): {'sha256': sha(p), 'bytes': p.stat().st_size} for p in snapshot.rglob('*') if p.is_file()})
    return out

class Inputs:
    def __init__(self): self.rows = {}; self.bytes_read = 0
    def ref(self, path, role, read_mode='hash_only', expected=None):
        path = Path(path).resolve()
        if not path.exists():
            self.rows[str(path)] = dict(path=str(path), exists=False, role=role)
            return None
        actual = sha(path); self.bytes_read += path.stat().st_size
        if str(path) not in self.rows:
            self.rows[str(path)] = dict(path=str(path), exists=True, bytes=path.stat().st_size,
                sha256=actual, roles=[], read_modes=[], campaign_id=CAMPAIGN_ID)
        row = self.rows[str(path)]
        if row['sha256'] != actual: raise RuntimeError('Input changed: ' + str(path))
        if role not in row['roles']: row['roles'].append(role)
        if read_mode not in row['read_modes']: row['read_modes'].append(read_mode)
        if expected is not None:
            row['expected_sha256'] = expected; row['hash_matches_expected'] = actual == expected
            if actual != expected: raise RuntimeError('Input hash mismatch: ' + str(path))
        return row
    def json(self, path, role):
        self.ref(path, role, 'JSON text'); return load(path)
    def text(self, path, role):
        self.ref(path, role, 'UTF-8 text'); return Path(path).read_text(encoding='utf-8-sig')
    def parquet(self, path, role, columns=None):
        import pandas as pd
        self.ref(path, role, 'Parquet numerical/metadata'); return pd.read_parquet(path, columns=columns)
    def parts(self, path, role):
        import pandas as pd
        files = sorted(Path(path).glob('part_*.parquet'))
        return pd.concat([self.parquet(p, role) for p in files], ignore_index=True) if files else pd.DataFrame()
    def npz(self, path, role):
        import numpy as np
        self.ref(path, role, 'NPZ allow_pickle=False')
        with np.load(path, allow_pickle=False) as z: return {k: z[k].copy() for k in z.files}
    def flush(self, out):
        (Path(out) / 'input_manifest.jsonl').write_text(''.join(json.dumps(clean(v), ensure_ascii=False) + '\n' for _, v in sorted(self.rows.items())), encoding='utf-8')

def dependencies():
    return {'python': sys.version, 'executable': sys.executable,
        'packages': {name: importlib.metadata.version(name) for name in ('numpy', 'pandas', 'pyarrow', 'matplotlib', 'psutil')}}

def markdown(frame, digits=3):
    if len(frame) == 0: return '해당 행 없음.'
    rows = ['| ' + ' | '.join(map(str, frame.columns)) + ' |', '| ' + ' | '.join(['---'] * len(frame.columns)) + ' |']
    for vals in frame.itertuples(index=False, name=None):
        cells = []
        for v in vals:
            if v is None or (isinstance(v, float) and not __import__('math').isfinite(v)): cells.append('NA')
            elif isinstance(v, float): cells.append(f'{v:.{digits}f}')
            else: cells.append(str(v).replace('|', '/'))
        rows.append('| ' + ' | '.join(cells) + ' |')
    return '\n'.join(rows)

ZERO_EXECUTION = dict(environment_creations=0, resets=0, train_transitions=0, eval_transitions=0,
    technical_transitions=0, issued_transitions=0, completed_transitions=0,
    policy_model_loads=0, replay_deserializations=0, policy_forwards=0, learning_updates=0)
