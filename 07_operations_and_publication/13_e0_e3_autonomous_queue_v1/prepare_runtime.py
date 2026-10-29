"""Copy the already pinned local dependency distributions into a new venv."""
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from campaign import ROOT, REPO, sha

out=ROOT/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_runtime_'+uuid.uuid4().hex[:6])
out.mkdir(parents=True,exist_ok=False)
shutil.copy2(__file__,out/'source_snapshot.py')
source=REPO/'06_p0_branch_replication_v1/.venv/Lib/site-packages'
target=ROOT/'.venv/Lib/site-packages'
manifest={}
for name in ['metaworld','metaworld-3.0.0.dist-info','gymnasium','gymnasium-1.2.3.dist-info',
             'stable_baselines3','stable_baselines3-2.7.1.dist-info']:
    src,dst=source/name,target/name
    if not src.exists():
        raise RuntimeError('Missing pinned distribution: '+str(src))
    if dst.exists():
        raise RuntimeError('Runtime destination already exists: '+str(dst))
    shutil.copytree(src,dst)
    for file in src.rglob('*'):
        if file.is_file() and '__pycache__' not in file.parts:
            relative=file.relative_to(source)
            digest=sha(file)
            assert digest==sha(target/relative)
            manifest[relative.as_posix()]=digest
(out/'copied_dependency_hashes.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'files_verified':len(manifest),'output':str(out)}))
