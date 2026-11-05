"""Finish file-only interpretation after 81, without launching any learning."""
import argparse
import os
from pathlib import Path
import time
from analyze import ROOT,analyze,read,save,utc

p=argparse.ArgumentParser();p.add_argument('--campaign',type=Path,required=True);a=p.parse_args()
campaign=a.campaign.resolve();start=time.perf_counter();all_done_since=None
save(ROOT/'ACTIVE_INPUT.json',{'campaign':str(campaign),'pid':os.getpid(),'started_at':utc(),'new_environment_steps':0})
while True:
    if (campaign/'FINAL_STATUS.json').exists():break
    done=sum((campaign/'runs'/r/'COMPLETE.json').exists() for r in ('R01','R02','R03','R04','R05'))
    if done==5:
        if all_done_since is None:all_done_since=time.perf_counter()
        if time.perf_counter()-all_done_since>1800:break
    if (campaign/'TECHNICAL_FAILED.json').exists():break
    save(ROOT/'WAITING_STATUS.json',{'time':utc(),'stage':'waiting_for_frozen_observation_campaign','completed_runs':done,
        'wait_seconds':time.perf_counter()-start,'new_environment_steps':0},replace=True)
    time.sleep(30)
try:
    out=analyze(campaign)
    save(ROOT/'DELIVERY.json',{'completed_at':utc(),'result':str(out),'wait_seconds':time.perf_counter()-start,'new_environment_steps':0})
except BaseException:
    import traceback
    save(ROOT/'FAILED.json',{'time':utc(),'traceback':traceback.format_exc(),'new_environment_steps':0});raise
