"""Read numeric snapshot payloads without constructing/restoring an environment.

The allowlist excludes every policy, environment and simulator class. This audit
does not change the detector or select different episodes.
"""
from __future__ import annotations
from common import *
guard_file_only()
import argparse
import pickle
import importlib
import numpy as np
import pandas as pd

class NumericSnapshotReader(pickle.Unpickler):
    def find_class(self,module,name):
        allowed={('numpy','ndarray'),('numpy','dtype'),('numpy._core.multiarray','_reconstruct'),
            ('numpy.core.multiarray','_reconstruct'),('numpy._core.multiarray','scalar'),
            ('numpy.core.multiarray','scalar'),('numpy._core.numeric','_frombuffer'),
            ('numpy.core.numeric','_frombuffer')}
        if (module,name) not in allowed:raise pickle.UnpicklingError('Disallowed nonnumeric snapshot class '+module+'.'+name)
        return getattr(importlib.import_module(module),name)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--preparation',type=Path,required=True);a=ap.parse_args()
    prep=a.preparation.resolve();out=new_output('initial_state_mapping_audit');inputs=Inputs();started=time.perf_counter()
    rows=[];checks=[]
    def ck(name,v,scope):
        checks.append(dict(check=name,passed=bool(v),scope=scope))
        if not v:raise AssertionError(name+': '+scope)
    def read_snapshot(path):
        inputs.ref(path,'existing numeric environment snapshot; no model class, no restore')
        with path.open('rb') as f:return NumericSnapshotReader(f).load()
    def inspect(state,reference,scope,kind):
        spec=int(state['integration_spec'])
        # In this exact saved integration format, time precedes qpos; verify the
        # layout against original explicit qpos metadata, not a model execution.
        ck('saved integration state includes time and qpos',bool(spec&1) and bool(spec&2),scope)
        qpos=np.asarray(state['integration_state'][1:11],dtype=np.float64)
        if reference is not None:ck('integration qpos layout matches saved original initial qpos',np.array_equal(qpos,reference['qpos']),scope)
        g=np.asarray(state['environment_attributes']['_target_pos'],dtype=np.float64)
        raw=np.asarray(state['raw_observation'],dtype=np.float64)
        positions=np.asarray(state['model_arrays']['body_pos'])
        quats=np.asarray(state['model_arrays']['body_quat'])
        # IDs follow the pinned DO feature schema: drawer(33), anonymous(34),
        # drawercase_link(35), drawer_link(36); every ancestor has identity rotation.
        ck('slide body ancestors have identity orientation',np.all(quats[[33,34,35,36]]==[1,0,0,0]),scope)
        h=positions[[33,34,35,36]].sum(axis=0)+[0,qpos[9],0]+[0,-.16,0]
        h_from_goal=g+[0,.19+qpos[9],0]
        ck('XML kinematics and saved model positions recover same physical handle',np.allclose(h,h_from_goal,atol=1e-12,rtol=0),scope)
        q0_from_raw=float(raw[5]-g[1]-.19)
        ck('raw reset Y coordinate retains actual slide position',abs(q0_from_raw-qpos[9])<=1e-8,scope)
        rows.append(dict(scope=scope,kind=kind,q0_actual=float(qpos[9]),q0_derived=q0_from_raw,
            q0_abs_error=abs(q0_from_raw-qpos[9]),raw_reset_handle_x=float(raw[4]),
            XML_physical_handle_x=float(h[0]),goal_x=float(g[0]),
            raw_vs_XML_handle_error_m=float(np.linalg.norm(raw[4:7]-h)),
            raw_yz_vs_XML_error_m=float(np.linalg.norm(raw[5:7]-h[1:])),
            d0_raw_observation_m=float(np.linalg.norm(raw[4:7]-g)),
            d0_XML_saved_state_m=float(np.linalg.norm(h-g))))
    try:
        evaluation=inputs.json(CAMPAIGN/'evaluation_cases/manifest.json','recorded evaluation initial qpos and snapshot linkage')
        for c in evaluation['cases']:
            if c['task_id']!='DO':continue
            path=Path(c['snapshot']['path']);inputs.ref(path,'original fixed snapshot hash',expected=c['snapshot']['sha256'])
            inspect(read_snapshot(path),c['initial_state'],c['initial_case_id'],'evaluation_initial_state_mapping_only')
        episodes=inputs.parquet(prep/'source_DO_training_episodes.parquet','DO episode IDs, not outcome-based snapshot selection')
        for run in RUNS:
            do_ids=set(episodes.loc[episodes.donor_run==run,'episode_id'].astype(int))
            base=CAMPAIGN/'runs'/run/'environment_snapshots/train'
            for path in sorted(base.glob('*/000.pkl')):
                if int(path.parent.name) not in do_ids:continue
                inspect(read_snapshot(path),None,run+':'+path.parent.name,'prespecified_training_initial_snapshot')
        df=pd.DataFrame(rows);df.to_csv(out/'reset_physical_coordinate_mapping.csv',index=False)
        summary=dict(snapshots=len(df),evaluation_snapshots=int((df.kind=='evaluation_initial_state_mapping_only').sum()),
            training_snapshots=int((df.kind=='prespecified_training_initial_snapshot').sum()),
            raw_reset_x_disagrees_with_saved_model_kinematics=int((df.raw_vs_XML_handle_error_m>1e-8).sum()),
            max_q0_derivation_abs_error=float(df.q0_abs_error.max()),
            max_reset_YZ_disagreement_m=float(df.raw_yz_vs_XML_error_m.max()),
            physical_d0_min=float(df.d0_XML_saved_state_m.min()),physical_d0_max=float(df.d0_XML_saved_state_m.max()),
            conclusion='Returned reset observation contains stale drawer X from pre-randomization forward data; actual saved-model handle position is reconstructed algebraically from current goal and slide q0.',
            permitted_mapping_correction='Use physical h0=g+[0,0.19+q0,0] for detector d0 only. Preserve original replay obs and all detector constants. q0 comes from saved reset Y and fixed XML, never x1.')
        save(out/'mapping_conclusion.json',summary)
        save(out/'FINAL_STATUS.json',dict(status='passed',checks=len(checks),new_execution=ZERO_EXECUTION,numeric_environment_snapshots_read=len(df),model_or_environment_instantiated=False))
        print(json.dumps(clean(dict(out=out,summary=summary)),ensure_ascii=False))
    except BaseException as ex:
        save(out/'FAILED.json',dict(error=repr(ex),new_execution=ZERO_EXECUTION));raise
    finally:
        inputs.flush(out);pd.DataFrame(checks).to_csv(out/'verification_checks.csv',index=False)
        save(out/'costs.json',dict(wall_seconds=time.perf_counter()-started,new_execution=ZERO_EXECUTION))
    save(HERE/'LATEST_MAPPING_AUDIT.json',dict(output=out),replace=True)

if __name__=='__main__':main()
