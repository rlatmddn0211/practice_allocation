"""Retain the initial missing-dependency check and its subsequent resolution."""
import shutil
import uuid
from campaign import ROOT,REPO,stamp,write,sha
directory=ROOT/'results'/(stamp()+'_bootstrap_failure_record_'+uuid.uuid4().hex[:6])
directory.mkdir(parents=True,exist_ok=False)
source=REPO/'09_fresh_evaluation_audit_v1/verify_stage.py'
shutil.copy2(source,directory/'attempted_verify_stage.py')
write(directory/'failed_check.json',{'passed':False,'retrospective_record':True,
    'command':'C:\\Python312\\python.exe 09_fresh_evaluation_audit_v1/verify_stage.py --suite A',
    'error':'ModuleNotFoundError: No module named metaworld',
    'scope':'Failed during imports, before environment creation or model initialization',
    'environment_steps':0,'evaluation_episodes':0,'train_iterations':0,
    'attempted_script_sha256':sha(source),
    'resolution':'Created version 13 venv and copied the existing pinned local dependency distributions with file hash verification. pip check passed.'})
print(directory)
