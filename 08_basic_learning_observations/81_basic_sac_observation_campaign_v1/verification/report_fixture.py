"""Synthetic full-shape report pipeline check; no environment/model execution."""
import sys
from pathlib import Path
import shutil
import uuid
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from records import ROOT,save,Table,sha
from analysis import analyze

out=ROOT/'verification'/('report_fixture_'+uuid.uuid4().hex[:8]);out.mkdir()
for name in ('protocol.json','config_resolved.json','baseline_manifest.json','input_receipt.json','seed_manifest.json'):
    shutil.copy2(ROOT/name,out/name)
(out/'source_snapshot').mkdir();shutil.copy2(__file__,out/'source_snapshot/report_fixture.py')
save(out/'FIXTURE_ONLY.json',{'synthetic':True,'new_environment_steps':0,'source_sha256':sha(__file__)})
p=out/'synthetic_trajectory.npz'
np.savez_compressed(p,success_step=np.array([0,1]),action_executed=np.zeros((2,4),dtype=np.float32),
    object_pos=np.zeros((2,3)),tcp=np.ones((2,3)),tcp_object_distance=np.ones(2),
    object_goal_distance=np.ones(2),robot_object_contact_pairs=np.array([0,1]))
steps=[0,10000,20000,50000,100000,200000,400000,600000,800000,1000000]
for ri in range(1,6):
    rid=f'R{ri:02d}';r=out/'runs'/rid;e=Table(r/'evaluation_episodes');t=Table(r/'episodes');u=Table(r/'update_scalars')
    for ti,task in enumerate(('DO','DC','PU','BP')):
        t.add({'run_id':rid,'task_id':task,'split_role':'train','episode_id':ti,'checkpoint_id':None,
            'initial_case_id':None,'end_env_step':500,'trajectory_ref':str(p)})
        for cp in steps:
            for case in range(16):
                success=(ri+ti+case+steps.index(cp))%2
                e.add({'run_id':rid,'task_id':task,'split_role':'observation_eval','episode_id':f'{cp}_{task}_{case}',
                    'checkpoint_id':cp,'initial_case_id':f'{task}_{case}','physical_case_id':f'physical_{task}_{case}',
                    'success_any':success,'success_final':success,'episode_return':float(success),
                    'episode_length':2,'first_success_step':2 if success else None,'trajectory_ref':str(p)})
    e.flush();t.flush()
    u.add({'env_step_total':1001,'actor_loss':1.,'critic_loss':2.,'alpha_after':.1,'q1_mean':1.,
        'q2_mean':1.,'target_q_mean':1.,'actor_gradient_norm':1.,'critic_gradient_norm':1.});u.flush()
    save(r/'COMPLETE.json',{'synthetic':True})
print(analyze(out,False))
