"""Verify published85 numbers from stored arrays/labels; no environment/model/RNG execution."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np
import pandas as pd

PUBLIC='09_experience_reuse_pilots/85_onset_reuse_pilot_v1'
CAMPAIGN='results/20261106T042248Z_onset_campaign_24d98d21'
ANALYSIS='analysis/20261106T111509Z_paired_3db89d3f'
PREP='results/20261106T040844Z_preparation_31c9735e'


def verify(repository):
    repo=Path(repository).resolve();base=repo/PUBLIC;a=base/CAMPAIGN/ANALYSIS;p=base/PREP
    checks=[]
    def check(name,ok):
        checks.append(dict(check=name,passed=bool(ok)))
        if not ok:raise AssertionError(name)
    status=json.loads((a/'FINAL_STATUS.json').read_text(encoding='utf-8'))
    check('complete fixed design and budget',status['completed_branches']==30 and status['valid_evaluations']==6080
        and status['actual_issued']==status['actual_completed']==4964900 and status['actual_technical_steps']==4900)
    e=pd.read_parquet(a/'evaluation_outcomes.parquet');c=pd.read_csv(a/'cell_metrics.csv')
    check('6080 valid outcome rows',len(e)==6080 and bool(e.valid.all()))
    key=['parent_id','future_id','arm','task_id','relative_train_step','initial_case_id','physical_case_id']
    check('outcome keys unique',not e.duplicated(key).any())
    start=e[e.relative_train_step==0]
    check('320 shared starting rows, not repeated per arm/future',len(start)==320 and not start.duplicated(['parent_id','task_id','initial_case_id','physical_case_id']).any())
    times=np.array([0,16000,32000,64000]);weights=np.r_[np.diff(times)[0]/2,
        (np.diff(times)[:-1]+np.diff(times)[1:])/2,np.diff(times)[-1]/2]/64000
    check('trapezoid weights',np.array_equal(weights,[.125,.25,.375,.25]))
    for r in c.itertuples(index=False):
        initial=start[(start.parent_id==r.parent_id)&(start.task_id==r.task_id)]
        vals=[]
        for t in times:
            rows=initial if t==0 else e[(e.parent_id==r.parent_id)&(e.future_id==r.future_id)&(e.arm==r.arm)&(e.task_id==r.task_id)&(e.relative_train_step==t)]
            check('fixed16 physical cases at '+r.cell_id+'/'+r.task_id+'/'+str(t),len(rows)==16 and rows.physical_case_id.nunique()==16)
            check('physical panel matched at '+r.cell_id+'/'+r.task_id+'/'+str(t),set(rows.physical_case_id)==set(initial.physical_case_id))
            vals.append(float(rows.success_any.mean()))
        check('cell AUC and final '+r.cell_id+'/'+r.task_id,abs(np.dot(weights,vals)-r.auc)<1e-12 and vals[-1]==r.J_64000)
    effects=pd.read_csv(a/'paired_effects_by_parent_future.csv');parents=pd.read_csv(a/'parent_effects.csv')
    for r in effects[effects.scope.isin(['DO','DC','PU','BP'])].itertuples(index=False):
        q=c[(c.parent_id==r.parent_id)&(c.future_id==r.future_id)&(c.task_id==r.scope)].set_index('arm')
        check('paired effect '+r.parent_id+'/'+r.future_id+'/'+r.contrast+'/'+r.scope,
            abs(q.loc[r.method,'auc']-q.loc[r.reference,'auc']-r.delta_auc)<1e-12 and
            abs(q.loc[r.method,'J_64000']-q.loc[r.reference,'J_64000']-r.delta_final)<1e-12)
    for r in parents.itertuples(index=False):
        x=effects[(effects.parent_id==r.parent_id)&(effects.contrast==r.contrast)&(effects.scope==r.scope)]
        check('parent two-future mean '+r.parent_id+'/'+r.contrast+'/'+r.scope,len(x)==2 and
            abs(x.delta_auc.mean()-r.delta_auc)<1e-12 and abs(x.delta_final.mean()-r.delta_final)<1e-12)
    ordered=[];names=[]
    for contrast in ['P-U','P-B','U-B']:
        for scope in ['DO','DC','PU','BP','OTHER3','MACRO4']:
            rows=parents[(parents.contrast==contrast)&(parents.scope==scope)].set_index('parent_id').loc[['R01','R02','R03','R04','R05']]
            for metric in ['delta_auc','delta_final']:ordered.append(rows[metric].to_numpy());names.append((contrast,scope,metric))
    with np.load(a/'bootstrap_draws.npz',allow_pickle=False) as z:
        indices=z['parent_indices'];saved=z['contrasts'];actual=np.stack(ordered,axis=1)[indices].mean(axis=1)
    check('all20000 stored bootstrap draws reused without new RNG',indices.shape==(20000,5) and np.allclose(actual,saved,rtol=0,atol=1e-12))
    ranges=np.quantile(actual,[.025,.975],axis=0,method='linear');trade=pd.read_csv(a/'task_tradeoffs.csv')
    for j,(contrast,scope,metric) in enumerate(names):
        r=trade[(trade.contrast==contrast)&(trade.scope==scope)&(trade.metric==metric)].iloc[0]
        check('stored percentile summary '+contrast+'/'+scope+'/'+metric,abs(r.lower-ranges[0,j])<1e-12 and abs(r.upper-ranges[1,j])<1e-12)
    catalog=[json.loads(x) for x in (base/'PUBLICATION_FILE_MAP.jsonl').read_text(encoding='utf-8').splitlines()]
    paths={x['source']:repo/x['public_path'] for x in catalog}
    src=[json.loads(x) for x in (base/'SOURCE_EPISODE_MAP.jsonl').read_text(encoding='utf-8').splitlines()]
    detector_spec=importlib.util.spec_from_file_location('published85_detector',base/'detector.py')
    detector=importlib.util.module_from_spec(detector_spec);detector_spec.loader.exec_module(detector)
    cand=pd.read_parquet(p/'onset_candidates_and_exclusions.parquet').set_index('permanent_episode_id')
    win=pd.read_parquet(p/'archive_windows.parquet');eligible=0
    for r in src:
        with np.load(repo/r['public_path'],allow_pickle=False) as z:
            b=z['success_step'];sigma=int(np.flatnonzero(b)[0]+1);g=z['goal'][0];raw=z['obs_raw'][0,4:7]
            q0=raw[1]-g[1]-.19;h0=g+np.array([0,.19+q0,0]);h=np.vstack([h0,z['object_pos']])
            got=detector.detect(np.linalg.norm(h-g,axis=1),np.r_[q0,z['joint_position']],sigma)
        old=cand.loc[r['permanent_episode_id']];eligible+=got['eligible']
        check('detector eligibility '+r['permanent_episode_id'],bool(old.eligible)==got['eligible'])
        check('first detector candidate '+r['permanent_episode_id'],pd.isna(old.tau) if got['tau'] is None else old.tau==got['tau'])
    check('all31 source episodes and25 eligible reproduced',len(src)==31 and eligible==25)
    with np.load(p/'selected_window_arrays.npz',allow_pickle=False) as cache:
        for i,r in win.iterrows():
            with np.load(paths[r.trajectory_ref],allow_pickle=False) as z:
                check('pre-success32 transition support '+r.archive_window_id,int(r.end-r.start+1)==32 and r.end<r.sigma)
                for name in ['transition_id','obs_policy','action_executed','reward','next_obs_actual','terminated','truncated','bootstrap_mask']:
                    check('original selected array '+r.archive_window_id+'/'+name,np.array_equal(cache[f'{i:03d}_{name}'],z[name][int(r.start)-1:int(r.end)]))
    numeric=0
    for original,path in paths.items():
        if path.suffix!='.npz' or 'evaluation_transitions' not in path.parts:continue
        row=e[e.trajectory_ref==original]
        check('published numeric trajectory has one outcome '+path.name,len(row)==1)
        with np.load(path,allow_pickle=False) as z:
            check('published raw success and return '+path.name,int(z['success_step'].any())==row.iloc[0].success_any
                and abs(float(z['reward'].sum(dtype=np.float64))-row.iloc[0].episode_return)<1e-8)
        numeric+=1
    check('240 video-matched plus80 shared DO numeric episodes',numeric==320)
    media=pd.read_csv(base/'MEDIA_INDEX.csv');check('240 fixed videos present',len(media)==240 and all((repo/x).is_file() for x in media.video))
    use=pd.read_csv(a/'archive_usage_summaries.csv');tot=use[use.actual_train_step==1064000].groupby('arm').archive_actual_use.sum().to_dict()
    check('equal actual U/P archive use',tot=={'BASE':0,'ONSET':10227844,'RANDOM_PRE':10227844})
    return dict(status='passed',checks=len(checks),evaluation_rows=len(e),source_episodes=31,eligible_episodes=25,
        published_numeric_evaluation_episodes=numeric,videos=len(media),source_detector_reproduced=True,
        AUC_and_stored_bootstrap_reproduced=True,new_environment_steps=0,new_model_loads=0,new_policy_forwards=0,new_learning_updates=0,new_bootstrap_draws=0)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--repository',type=Path,required=True);args=ap.parse_args()
    print(json.dumps(verify(args.repository),ensure_ascii=False),flush=True)
