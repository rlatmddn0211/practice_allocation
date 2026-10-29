"""Sequential CUDA checks with wrapper snapshots even when imports fail."""
import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from campaign import ROOT, REPO, STAGES, stage_hashes, stamp, write

directory=ROOT/'results'/(stamp()+'_all_stage_verification_'+uuid.uuid4().hex[:6])
directory.mkdir(parents=True,exist_ok=False)
shutil.copy2(__file__,directory/'source_snapshot.py')
results=[]
for stage,suite in [('E0','A'),('E1','A'),('E2','A'),('E3','B'),('E3','C')]:
    implementation=REPO/STAGES[stage]
    start_hashes=stage_hashes(implementation)
    write(directory/f'{stage}_{suite}_source_hashes.json',start_hashes)
    for relative in start_hashes:
        target=directory/'source_snapshot'/stage/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(implementation/relative,target)
    print(f'Running {stage} suite {suite}',flush=True)
    with (directory/f'{stage}_{suite}.log').open('xb') as log:
        proc=subprocess.run([sys.executable,str(implementation/'verify_stage.py'),'--suite',suite],stdout=log,stderr=subprocess.STDOUT,cwd=REPO)
    final_hashes=stage_hashes(implementation)
    result={'stage':stage,'suite':suite,'exit_code':proc.returncode,'source_unchanged':start_hashes==final_hashes}
    results.append(result)
    print(json.dumps(result),flush=True)
    if proc.returncode or start_hashes!=final_hashes:
        write(directory/'verification.json',{'passed':False,'results':results})
        raise SystemExit(1)
write(directory/'verification.json',{'passed':True,'results':results,'technical_only':True})
print(json.dumps({'passed':True,'directory':str(directory)}),flush=True)
