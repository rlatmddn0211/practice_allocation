"""Create independent baseline implementation copies once; preserve provenance."""
import hashlib
import json
import shutil
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    run = ROOT / 'results' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_bootstrap_' + uuid.uuid4().hex[:8])
    run.mkdir(parents=True, exist_ok=False)
    (run / 'source_snapshot').mkdir()
    shutil.copy2(__file__, run / 'source_snapshot' / 'bootstrap.py')
    rows = []
    old = REPO / '59_fresh_future_confirmation_v1'
    for folder, pattern in [('practice_allocation','*.py'), ('configs','*.json')]:
        target = ROOT / folder
        target.mkdir(exist_ok=False)
        for src in sorted((old/folder).glob(pattern)):
            shutil.copy2(src, target/src.name)
            rows.append({'source':str(src),'target':str((target/src.name).relative_to(ROOT)), 'sha256':sha(src)})
    shutil.copy2(old/'requirements.txt',ROOT/'requirements.txt')
    rows.append({'source':str(old/'requirements.txt'),'target':'requirements.txt','sha256':sha(old/'requirements.txt')})
    value = {'version': ROOT.name, 'parent_implementation': old.name, 'copied_files':rows,
             'scope':'Independent same-S baseline; frozen learner/environment remain byte-identical; all new logic resides in this version.',
             'new_environment_steps':0, 'python':sys.version, 'bootstrap_sha256':sha(__file__)}
    (ROOT/'VERSION.json').write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    (run/'COMPLETE.json').write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    print(run)

if __name__ == '__main__':
    main()
