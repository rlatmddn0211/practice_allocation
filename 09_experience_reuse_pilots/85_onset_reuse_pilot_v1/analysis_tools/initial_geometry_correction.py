"""Quantify the reset-coordinate correction on the already completed shared +0 panel."""
from __future__ import annotations
import sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from common import *
guard_file_only()
import argparse
import xml.etree.ElementTree as ET
import pandas as pd

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--campaign',type=Path,required=True);ap.add_argument('--analysis',type=Path,required=True);a=ap.parse_args()
    campaign=a.campaign.resolve();analysis=a.analysis.resolve()
    out=campaign/'verification'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_initial_geometry_'+uuid.uuid4().hex[:8]);out.mkdir(parents=True,exist_ok=False)
    shutil.copy2(__file__,out/'source.py');inputs=Inputs();started=time.perf_counter()
    try:
        table=inputs.parquet(analysis/'evaluation_outcomes.parquet','actual shared initial evaluation with unchanged original full policies')
        do=table[(table.task_id=='DO')&(table.relative_train_step==0)]
        if len(do)!=80 or not do.valid.all():raise RuntimeError('Require the complete fixed +0 DO80 panel')
        per=[]
        for run,part in do.groupby('parent_id'):
            raw=part.raw_obs_goal_progress_max_m>=.005;physical=part.physical_goal_progress_max_m>=.005
            per.append(dict(parent_id=run,N=16,official_successes=int(part.success_any.sum()),raw_reset_5mm_progress=int(raw.sum()),
                physical_reset_5mm_progress=int(physical.sum()),raw_only=int((raw&~physical).sum()),physical_only=int((physical&~raw).sum())))
        pd.DataFrame(per).to_csv(out/'per_parent_correction.csv',index=False)
        do[['parent_id','initial_case_id','physical_case_id','raw_obs_goal_progress_max_m','physical_goal_progress_max_m','minimum_goal_distance_m','joint_min_m','trajectory_ref']].to_csv(out/'all_initial_DO_cases.csv',index=False)
        xml=SITE/'metaworld/assets/objects/assets/drawer.xml';inputs.ref(xml,'pinned static joint geometry')
        joint=ET.parse(xml).find(".//joint[@name='goal_slidey']");limits=list(map(float,joint.attrib['range'].split()))
        geometry=dict(joint_type=joint.attrib['type'],joint_range_m=limits,world_axis=joint.attrib['axis'],
            nominal_closed_handle_goal_distance_m=.19,nominal_static_goal_distance_at_joint_lower_bound_m=abs(.19+limits[0]),
            official_DO_success_radius_m=.03,
            interpretation='Static source/XML geometry places the nominal success boundary at the joint lower limit. Actual soft constraints and returned endpoint distances remain authoritative; do not recreate labels from joint position or rounded numbers.')
        summary=dict(N=80,unique_physical_cases=16,parents=5,raw_reset_progress=sum(r['raw_reset_5mm_progress'] for r in per),
            physical_reset_progress=sum(r['physical_reset_5mm_progress'] for r in per),raw_only=sum(r['raw_only'] for r in per),
            official_successes=int(do.success_any.sum()),new_execution=ZERO_EXECUTION,threshold_m=.005,
            prior_reports_preserved=True,geometry=geometry)
        save(out/'correction_summary.json',summary);save(out/'FINAL_STATUS.json',dict(status='complete',new_execution=ZERO_EXECUTION))
        print(json.dumps(dict(output=str(out),summary=summary),ensure_ascii=False),flush=True)
    except BaseException as ex:
        save(out/'FAILED.json',dict(error=repr(ex),new_execution=ZERO_EXECUTION));raise
    finally:inputs.flush(out);save(out/'costs.json',dict(wall_seconds=time.perf_counter()-started,new_execution=ZERO_EXECUTION))

if __name__=='__main__':main()
