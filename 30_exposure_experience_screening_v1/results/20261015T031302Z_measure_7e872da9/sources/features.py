"""Two prespecified candidate groups; retrospective20k inputs only."""
from pathlib import Path
from collections import defaultdict
import numpy as np
from common import ROOT,table
from performance_controls import PROFILE,role

BASE=PROFILE+['reward_scale','target_scale','residual','gap']
EXP=BASE+['train_return_focus','train_return_other','history_age_focus','history_age_other']
GROUPS={'CriticBase':BASE,'F02':BASE+['exposure_gap','new_fraction'],
        'F02_expected':BASE+['expected_gap','expected_new_fraction'],
        'F02_age':BASE+['replay_age_focus','replay_age_other'],
        'ExperienceBase':EXP,'F03':EXP+['experience_focus','experience_other'],
        'F03_coverage':EXP+['coverage_focus','coverage_other'],
        'F03_both':EXP+['experience_focus','experience_other','coverage_focus','coverage_other'],
        'F03_unique':EXP+['unique_focus','unique_other']}


def build(run,p,parents,ys,lengths,splits,refs,measurement=None):
    if not measurement:raise ValueError('Measurement required')
    d=Path(measurement);summary=run.read(d/'summary.json')
    run.check('full completed measurement',summary['status']=='completed' and not summary['technical_smoke'] and summary['snapshots']==192)
    run.check('matching protocol',run.read(d/'sources/protocol.json')==p)
    manifest=run.read(d/'manifest.json');raw={}
    for r in manifest:
        raw[r['id']]=run.read(r['path'],r['sha256'])
        run.check('same evaluated checkpoint '+r['id'],raw[r['id']]['entry']['checkpoint']==refs[r['id']])
    inv=run.rows(ROOT/p['prior_artifact_manifest']);expected={str((ROOT/'29_neural_plasticity_screening_v1'/r['path']).resolve()):r['sha256'] for r in inv}
    path=ROOT/p['prior_features'];run.hashed(path,expected[str(path.resolve())]);old=run.rows(path)
    taskrows=defaultdict(dict)
    for r in run.rows(d/'task_features.csv'):taskrows[r['id']][r['task']]=r
    result=[]
    for previous in old:
        row={k:float(v) for k,v in previous.items() if k in BASE+['D20','target_D_remainder','O40','weight']}
        row.update({k:previous[k] for k in ['id','suite','allocation']})
        row.update({k:int(previous[k]) for k in ['original_seed','checkpoint_step','continuation']})
        jid=row['id'];tasks=p['suites'][row['suite']];ai=0 if row['allocation']=='U' else 1+tasks.index(row['allocation'][2:])
        bytask=taskrows[jid];exp=raw[jid]['exposure']
        row['exposure_gap']=0. if ai==0 else exp['collection_share'][ai-1]-exp['observed_share'][ai-1]
        row['expected_gap']=0. if ai==0 else exp['collection_share'][ai-1]-exp['expected_share'][ai-1]
        row['new_fraction']=exp['new_fraction'];row['expected_new_fraction']=exp['expected_new_fraction']
        for feature,column,transform in [('train_return','recent_return',lambda x:x),('history_age','oldest_episode_age',np.log1p),
                    ('experience','recent_success',lambda x:x),('unique','recent_unique',lambda x:x),
                    ('replay_age','mean_replay_age',lambda x:x),('coverage','raw_displacement',lambda x:x)]:
            vals=np.array([transform(float(bytask[t][column])) for t in tasks]);f,o=role(vals,ai)
            row[feature+'_focus']=f;row[feature+'_other']=o
        result.append(row)
    run.check('180 branch features',len(result)==180 and len({r['id'] for r in result})==180)
    rr=[r for v in taskrows.values() for r in v.values() if int(r['horizon'])==20000]
    diagnostic={'measurement':summary,'recent_task_rows':len(rr),
                'zero_success_experience_tasks':sum(float(r['recent_success'])==0 for r in rr),
                'all_success_experience_tasks':sum(float(r['recent_success'])==1 for r in rr),
                'unique_initial_state_counts':sorted({int(r['recent_unique']) for r in rr}),
                'max_expected_observed_sample_share_difference':max(abs(a-b) for v in raw.values() if v['exposure'] for a,b in zip(v['exposure']['observed_share'],v['exposure']['expected_share'])),
                'feature_standard_deviations':{k:float(np.std([r[k] for r in result])) for k in ['exposure_gap','new_fraction','expected_new_fraction','experience_focus','experience_other','unique_focus','unique_other']}}
    return result,diagnostic
