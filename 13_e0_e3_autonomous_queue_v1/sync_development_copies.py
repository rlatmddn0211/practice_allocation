"""Development only: materialize files in each independent version before freeze."""
import shutil
from pathlib import Path
from campaign import REPO, STAGES

source=REPO/STAGES['E0']
files=['run_job.py','analyze_stage.py','verify_stage.py','practice_allocation/study_io.py']
for name in list(STAGES.values())[1:]:
    for relative in files:
        shutil.copy2(source/relative,REPO/name/relative)
print('Independent local copies materialized; no cross-version imports.')
