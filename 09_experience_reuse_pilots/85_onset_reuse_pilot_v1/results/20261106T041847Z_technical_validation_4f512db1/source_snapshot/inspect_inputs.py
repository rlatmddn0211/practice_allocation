"""Initial inspection with immutable source snapshot and no runtime imports."""
from __future__ import annotations
from common import *
guard_file_only()
import pandas as pd
import numpy as np

def main():
    out = new_output('inspection'); inputs = Inputs(); started = time.perf_counter()
    save(out / 'dependencies.json', dependencies())
    try:
        rows = []
        for run in RUNS:
            base = CAMPAIGN / 'runs' / run
            episodes = inputs.parts(base / 'episodes', 'original complete training episode summaries')
            take = episodes[(episodes.task_id == 'DO') & episodes.success_any.astype(bool)]
            manifest = inputs.json(base / 'checkpoints/full/1000000/checkpoint_manifest.json', '1M full checkpoint metadata')
            rows.append(dict(run_id=run, all_episodes=len(episodes), DO_episodes=int((episodes.task_id=='DO').sum()), successful_DO=len(take),
                columns=list(episodes.columns), example=take.iloc[0].to_dict() if len(take) else None,
                checkpoint=dict(step=manifest['step'],updates=manifest['updates'],replay_size=manifest['replay_size'],replay_pos=manifest['replay_pos'])))
            if len(take):
                path = Path(take.iloc[0].trajectory_ref)
                side = inputs.json(path.with_suffix('.json'), 'successful training trajectory sidecar')
                z = inputs.npz(path, 'successful training trajectory schema inspection')
                rows[-1]['sidecar'] = side
                rows[-1]['array_schema'] = {k: dict(shape=v.shape, dtype=str(v.dtype)) for k,v in z.items()}
                rows[-1]['first_values'] = {k:z[k][:2].tolist() for k in ('obs_raw','obs_policy','next_obs_raw_actual','joint_position','object_pos','goal','success_step','episode_step','qpos')}
        save(out / 'inspection.json', rows)
        print(json.dumps(clean({'out':out,'runs':[{k:r[k] for k in ('run_id','successful_DO','checkpoint')} for r in rows],
            'episode_columns':rows[0]['columns'],'example_episode':rows[0]['example'],'sidecar':rows[0]['sidecar'],
            'array_schema':rows[0]['array_schema'],'first_values':rows[0]['first_values']}),ensure_ascii=False))
        save(out / 'FINAL_STATUS.json',dict(stage='file-only input inspection',status='complete',wall_seconds=time.perf_counter()-started,new_execution=ZERO_EXECUTION))
    except BaseException as ex:
        save(out / 'FAILED.json',dict(error=repr(ex),new_execution=ZERO_EXECUTION)); raise
    finally: inputs.flush(out)
    save(HERE / 'LATEST_INSPECTION.json',dict(output=out),replace=True)

if __name__ == '__main__': main()
