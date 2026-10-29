"""Read-only source checkpoint; retain a unique compression feasibility audit."""
import hashlib
import json
import lzma
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
out = ROOT / 'results' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_storage_check_' + uuid.uuid4().hex[:8])
out.mkdir(parents=True, exist_ok=False)
shutil.copy2(__file__, out / 'source_snapshot.py')
source = ROOT.parent / '02_p0_uniform_pretraining_v1/results/20261007T060310Z_p0_cuda_50621c50/run/checkpoints/step_000200000/replay.pkl'
started = time.perf_counter()
data = source.read_bytes()
compressed = lzma.compress(data, preset=1)
assert lzma.decompress(compressed) == data
report = dict(source=str(source), source_sha256=hashlib.sha256(data).hexdigest(), raw_bytes=len(data), xz_bytes=len(compressed), seconds=time.perf_counter()-started, free_bytes=shutil.disk_usage(ROOT).free, source_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
(out / 'audit.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report))
