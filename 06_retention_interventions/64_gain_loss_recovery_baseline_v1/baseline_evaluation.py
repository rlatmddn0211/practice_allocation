"""Case-paired deterministic evaluation with first success and RNG isolation."""
import csv
from pathlib import Path
from common import reserve
from practice_allocation.core import TASKS, isolated_rng, fingerprint
from practice_allocation.environment import TaskEpisode
from practice_allocation.study_io import IntegrityError

FIELDS=['id','evaluation_id','context','policy_type','parent','condition','future','relative_step',
        'bank','task','episode_index','seed','initial_state_hash','task_parameter_hash',
        'success','first_success_step','return','length','termination_reason']

def evaluate(engine,bank,costs,path,meta,cap):
    path=Path(path)
    if not bank: raise IntegrityError('Empty evaluation set')
    modes={name:mod.training for name,mod in engine.model.policy.named_modules()}
    before=engine.fingerprints()
    rows=[]
    start_steps=costs.environment_steps
    try:
        with isolated_rng():
            with path.open('a',newline='',encoding='utf-8') as f:
                writer=csv.DictWriter(f,fieldnames=FIELDS)
                if f.tell()==0: writer.writeheader()
                for entry in bank:
                    reserve(costs,500,cap)
                    with TaskEpisode(entry['task_index'],entry['seed'],costs) as episode:
                        if episode.initial_state_hash!=entry['initial_state_hash']:
                            raise IntegrityError('Paired evaluation reset identity changed')
                        param=fingerprint({k:episode.initial_state[k] for k in ('task','rand_vec','goal')})
                        if param!=entry['task_parameter_hash']:
                            raise IntegrityError('Evaluation task/goal identity changed')
                        observation=episode.observation.copy()
                        total=0.0;first=None
                        for _ in range(500):
                            action,_=engine.model.predict(observation,deterministic=True)
                            observation,reward,_,truncated,info=episode.step(action)
                            total+=reward
                            if info['success']:
                                first=episode.steps;break
                            if truncated:break
                        costs.evaluation_episodes+=1
                        row={**meta,'evaluation_id':meta['id'],'context':'baseline_development',
                             'policy_type':'learned_sac','bank':entry['bank'],'task':entry['task'],
                             'episode_index':entry['episode_index'],'seed':entry['seed'],
                             'initial_state_hash':episode.initial_state_hash,'task_parameter_hash':param,
                             'success':int(first is not None),'first_success_step':first,
                             'return':total,'length':episode.steps,
                             'termination_reason':'first_success' if first is not None else 'horizon_500'}
                        writer.writerow(row);f.flush();rows.append(row)
    finally:
        for name,mod in engine.model.policy.named_modules():mod.training=modes[name]
    if before!=engine.fingerprints():
        raise IntegrityError('Evaluation changed model/optimizer/replay/collector/RNG')
    return {'episodes':len(rows),'environment_steps':costs.environment_steps-start_steps,
            'success_by_task':{t:(sum(r['success'] for r in rows if r['task']==t)/sum(r['task']==t for r in rows)
                                  if any(r['task']==t for r in rows) else None) for t in TASKS}}
