"""Verify that Git preserves the exact experiment/report bytes before publication."""
import hashlib
import io
import json
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
run = HERE/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_git_bytes_')+uuid.uuid4().hex[:8])
run.mkdir(parents=True, exist_ok=False)
shutil.copy2(__file__, run/'verification_source.py')
paths = subprocess.check_output(['git', 'diff', '--cached', '--name-only', '-z'], cwd=ROOT).decode().split('\0')
paths = [p for p in paths if p and p[:2].isdigit() and 13 <= int(p[:2]) <= 20]
raw = subprocess.check_output(['git', 'cat-file', '--batch'], input=''.join(':'+p+'\n' for p in paths).encode(), cwd=ROOT)
stream = io.BytesIO(raw)
checks = []
for p in paths:
    object_id, kind, length = stream.readline().decode().strip().split(' ')
    data = stream.read(int(length))
    assert stream.read(1) == b'\n'
    expected = hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
    actual = hashlib.sha256(data).hexdigest()
    checks.append({'path': p, 'git_blob': object_id, 'bytes': len(data), 'sha256': actual, 'matches_original': expected == actual})
passed = all(c['matches_original'] for c in checks)
result = {'status': 'passed' if passed else 'failed', 'files': len(checks), 'checks': checks,
          'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'training_steps': 0, 'evaluation_episodes': 0,
          'purpose': 'Byte equality between staged Git blobs and original frozen artifacts; excludes this newly created verification record.'}
with (run/'verification.json').open('x', encoding='utf-8', newline='\n') as f:
    json.dump(result, f, indent=2)
    f.write('\n')
print(json.dumps({'status': result['status'], 'files': len(checks), 'run': str(run)}, indent=2))
if not passed:
    raise SystemExit(1)
