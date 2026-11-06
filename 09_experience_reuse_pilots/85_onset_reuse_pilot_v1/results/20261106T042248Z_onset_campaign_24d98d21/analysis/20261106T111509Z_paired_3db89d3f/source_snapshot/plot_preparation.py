"""Render only the outcome-independent source-window/support figures for visual verification."""
from __future__ import annotations
import sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from common import *
guard_file_only()
import argparse
from finalize import figures

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--campaign',type=Path,required=True);a=ap.parse_args();campaign=a.campaign.resolve()
    prep=Path(load(campaign/'campaign_config.json')['preparation'])
    out=campaign/'verification'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_preparation_figures_'+uuid.uuid4().hex[:8]);out.mkdir(parents=True,exist_ok=False)
    shutil.copy2(__file__,out/'source.py');shutil.copy2(Path(__file__).parent/'finalize.py',out/'figure_source.py')
    started=time.perf_counter()
    try:
        result=figures(out,prep,preparation_only=True)
        save(out/'FINAL_STATUS.json',dict(status='rendered_pending_visual_review',figures=result,new_execution=ZERO_EXECUTION,wall_seconds=time.perf_counter()-started))
        print(json.dumps(dict(output=str(out),figures=len(result))),flush=True)
    except BaseException as ex:
        save(out/'FAILED.json',dict(error=repr(ex),new_execution=ZERO_EXECUTION));raise

if __name__=='__main__':main()
