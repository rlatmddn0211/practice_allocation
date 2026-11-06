"""Restore the first fixed ONSET 4k full state without any rollout or update."""
from __future__ import annotations
import sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from common import *
import argparse

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--campaign',type=Path,required=True);a=ap.parse_args();campaign=a.campaign.resolve()
    import pandas as pd
    plan=pd.read_csv(campaign/'execution_plan.csv').sort_values('execution_order')
    cell=plan[plan.arm=='ONSET'].iloc[0].cell_id
    attempt=Path(load(campaign/'jobs'/cell/'ACTIVE_ATTEMPT.json')['attempt'])
    full=attempt/'checkpoints/full/004000'
    if not (full/'COMPLETE.json').exists():raise RuntimeError('Wait for the predetermined first ONSET 4k full state')
    out=campaign/'verification'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_positive_resume_'+uuid.uuid4().hex[:8]);out.mkdir(parents=True,exist_ok=False)
    shutil.copy2(__file__,out/'source.py');started=time.perf_counter();cost=None;engine=None
    try:
        import pilot_runtime as rt
        rt.initialize_runtime();cost=rt.Cost(out/'costs','technical',0)
        engine=rt.restore_full(full,cost,out/'restored_state')
        r=engine.model.replay_buffer
        if r.pilot_archive_actual<=0 or int(r.archive_counts.sum())!=r.pilot_archive_actual:raise RuntimeError('Positive archive counts not preserved')
        if r.pilot_native_draws!=4000*256 or r.pilot_archive_actual+r.pilot_native_actual!=r.pilot_native_draws:raise RuntimeError('Draw/actual-use state differs')
        save(out/'FINAL_STATUS.json',dict(status='passed',selection_rule='first ONSET in fixed execution plan, earliest4k full checkpoint',
            cell_id=cell,checkpoint=str(full),source_checkpoint_manifest_sha256=sha(full/'checkpoint_manifest.json'),
            actual_model_loads=1,policy_forward=0,learning_updates=0,environment_transitions=0,environment_resets=0,
            archive_actual_preserved=r.pilot_archive_actual,native_actual_preserved=r.pilot_native_actual,
            exact_all_state_fingerprints=True,wall_seconds=time.perf_counter()-started))
        print(json.dumps(dict(output=str(out),status='passed',new_environment_steps=0)),flush=True)
    except BaseException as ex:
        save(out/'FAILED.json',dict(error=repr(ex),new_environment_steps=cost.issued if cost else 0));raise
    finally:
        if engine:engine.close()
        if cost:cost.close()

if __name__=='__main__':main()
