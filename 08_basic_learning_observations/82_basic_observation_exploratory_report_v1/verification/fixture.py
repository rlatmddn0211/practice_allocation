"""Small outcome-consistent synthetic fixture; no environment/model imports."""
import sys
from pathlib import Path
import shutil
import uuid
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from analyze import ROOT,analyze,save

source=ROOT.parent/'81_basic_sac_observation_campaign_v1/verification/report_fixture_eacaa9e2'
out=ROOT/'verification'/('fixture_'+uuid.uuid4().hex[:8]);out.mkdir()
for name in ('protocol.json','seed_manifest.json','baseline_manifest.json','config_resolved.json','input_receipt.json'):
    shutil.copy2(source/name,out/name)
save(out/'evaluation_cases/manifest.json',{'synthetic':True})
trajectories=[]
for success in (0,1):
    p=out/f'fixture_{success}.npz'
    np.savez_compressed(p,success_step=np.array([0,success]),action_executed=np.zeros((2,4)),
        object_pos=np.zeros((2,3)),tcp=np.zeros((2,3)),tcp_object_distance=np.ones(2),object_goal_distance=np.ones(2),
        robot_object_contact_pairs=np.array([0,1]));trajectories.append(str(p))
for rid in ('R01','R02','R03','R04','R05'):
    d=out/'runs'/rid/'evaluation_episodes';d.mkdir(parents=True)
    for p in (source/'runs'/rid/'evaluation_episodes').glob('*.parquet'):
        df=pd.read_parquet(p);df['trajectory_ref']=[trajectories[int(x)] for x in df.success_any]
        df['video_ref']=None;df.to_parquet(d/p.name,index=False)
    save(d.parent/'COMPLETE.json',{'synthetic':True})
save(out/'FIXTURE_ONLY.json',{'synthetic':True,'new_environment_steps':0,'new_policy_forwards':0})
print(analyze(out))
