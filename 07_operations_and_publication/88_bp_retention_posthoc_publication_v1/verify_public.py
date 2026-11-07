"""Arithmetic checks of published87 tables against original85 labels/counts/DO arrays."""
from __future__ import annotations
import argparse,io
import numpy as np
import pandas as pd
from common import *


def verify(repository,delivery_name,base_store=None,base_ref=None):
    repo=Path(repository);directory=PUBLIC+'/delivery/'+delivery_name;checks=[]
    def data(path):
        p=repo/path
        if p.is_file():return p.read_bytes()
        if base_store and base_ref:return git(base_store,'show',base_ref+':'+path)
        raise FileNotFoundError('Required published file '+path)
    def frame(path):
        b=io.BytesIO(data(path));return pd.read_parquet(b) if path.endswith('.parquet') else pd.read_csv(b)
    def check(name,ok):
        checks.append(dict(name=name,passed=bool(ok)))
        if not ok:raise AssertionError(name)
    original=frame(A85+'/checkpoint_case_history.parquet');original=original[original.task_id=='BP']
    h=frame(directory+'/tables/bp_arm_histories.parquet')
    keys=['parent_id','future_id','arm','physical_case_id'];cols=['z0','z16','z32','z64']
    a=original.set_index(keys).sort_index();b=h.set_index(keys).sort_index()
    check('480 BP histories match original85 labels and keys',a.index.equals(b.index) and len(b)==480 and np.array_equal(a[cols],b[cols]))
    events={};initial={};final={}
    for arm,g in b.reset_index().groupby('arm'):
        gain=loss=recovery=0
        for z in g[cols].to_numpy(dtype=int).tolist():
            gg=sum(x==0 and y==1 for x,y in zip(z[:-1],z[1:]));ll=sum(x==1 and y==0 for x,y in zip(z[:-1],z[1:]));rr=0
            for k in range(1,4):rr+=int(z[k-1]==0 and z[k]==1 and any(z[:k-1]))
            check('telescoping '+arm+str(len(checks)),gg-ll==z[-1]-z[0] and ll-rr==max(z)-z[-1])
            gain+=gg;loss+=ll;recovery+=rr
        events[arm]=[gain,loss,recovery];initial[arm]=int(g.z0.sum());final[arm]=int(g.z64.sum())
    check('shared initial148 and final105/134/145',set(initial.values())=={148} and final=={'BASE':105,'ONSET':145,'RANDOM_PRE':134})
    check('observed gain/loss/recovery events',events=={'BASE':[32,75,20],'ONSET':[34,37,22],'RANDOM_PRE':[34,48,24]})
    effects=frame(directory+'/tables/bp_paired_effects_parent_future.csv');weight=np.array([.125,.25,.375,.25])
    for row in effects.to_dict('records'):
        m=b.loc[(row['parent_id'],row['future_id'],row['method'])][cols].to_numpy(dtype=float).mean(axis=0)
        r=b.loc[(row['parent_id'],row['future_id'],row['reference'])][cols].to_numpy(dtype=float).mean(axis=0)
        check('all30 paired effects '+row['parent_id']+row['future_id']+row['contrast'],abs(float((m-r)@weight)-row['delta_auc'])<1e-12 and abs(m[-1]-r[-1]-row['final_delta_J'])<1e-12)
    # Raw successful DO episodes were already published with85; no duplicate upload.
    source_map={r['original_path']:r['public_path'] for r in map(json.loads,data(V85+'/SOURCE_EPISODE_MAP.jsonl').decode('utf-8').splitlines())}
    windows=frame(directory+'/tables/do_window_content.parquet');check('frozen25 episodes50 windows',len(windows)==50 and windows.source_episode_id.nunique()==25)
    for path,g in windows.groupby('trajectory_ref'):
        payload=data(source_map[path]);check('original DO raw SHA256 '+g.source_episode_id.iloc[0],hashlib.sha256(payload).hexdigest()==g.source_sha256.iloc[0])
        with np.load(io.BytesIO(payload),allow_pickle=False) as raw:
            q=raw['joint_position'];sigma=int(np.flatnonzero(raw['success_step'])[0]+1)
            for row in g.to_dict('records'):
                lo=int(row['window_start']);hi=int(row['window_end']);p=-q[lo-2:hi];dp=np.diff(p)
                pos=float(np.maximum(dp,0).sum());neg=float(np.maximum(-dp,0).sum());net=float(p[-1]-p[0])
                check('32 pre-success original samples '+row['archive_window_id'],len(dp)==32 and hi<sigma and sigma==row['sigma'])
                check('raw directional path decomposition '+row['archive_window_id'],abs(pos-row['opening_path_m'])<1e-10 and abs(neg-row['closing_path_m'])<1e-10 and abs(net-row['net_opening_m'])<1e-10)
    native=frame(A85+'/archive_usage_by_checkpoint.parquet');native=native[native.arm!='BASE']
    actual=frame(directory+'/tables/actual_transition_usage_by_interval.parquet')
    counts=['parent_id','future_id','arm','source_episode_id','window_offset','archive_transition_id']
    for end in [16000,32000,64000]:
        hi=native[native.checkpoint==1000000+end].set_index(counts).actor_sample_count.sort_index()
        saved=actual[actual.interval_end==end].set_index(counts).cumulative_actor_use.sort_index()
        check('as-of actual counts match original85 at'+str(end),hi.index.equals(saved.index) and np.array_equal(hi,saved))
    check('actual counts each10227844',all(int(actual[actual.arm==arm].interval_actor_use.sum())==10227844 for arm in ['ONSET','RANDOM_PRE']))
    features=['opening_positive_m','closing_positive_m','goal_axis_command','gripper_command','reward','contact_endpoint']
    summaries=frame(directory+'/tables/actual_interval_exposure_features.csv').set_index(['parent_id','future_id','arm','interval_start','interval_end'])
    for keys,g in actual.groupby(['parent_id','future_id','arm','interval_start','interval_end']):
        n=g.interval_actor_use.to_numpy(dtype=float);summary=summaries.loc[keys]
        check('final-batch weighted content '+str(keys),all(abs(float(n@g[f]/n.sum())-summary[f])<1e-10 for f in features))
    link=frame(directory+'/tables/exposure_BP_effect_linkage.parquet')
    check('all90 links respect exposure cutoff',len(link)==90 and (link.interval_end==link.exposure_latest_allowed_train_step).all())
    receipt=json.loads(data(directory+'/reproduction_receipt.json'))
    check('original reproduction bundle byte-identical',hashlib.sha256(data(directory+'/reproduction_bundle.zip')).hexdigest()==receipt['sha256'])
    status=json.loads(data(directory+'/FINAL_STATUS.json'));check('original four stages complete withzero new runtime',status['status']=='complete' and all(x['status']=='complete' for x in status['stages'].values()) and not any(status['new_execution'].values()))
    check('no simulator/model library imported',not (FORBIDDEN&set(sys.modules)))
    return dict(status='passed',checks=checks,original_label_histories=480,matched_histories=160,DO_episodes=25,
        actual_exposure_rows=len(summaries),time_respecting_links=len(link),
        scope='Public original85 labels/counts and already-published25 DO arrays;derived87 tables;bundle hash',
        limitation='Full1520 BP raw trajectories were verified locally during87 extraction;most raw BP arrays remain local, not rechecked by this public verifier',new_execution=ZERO)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--repository',default='.');ap.add_argument('--delivery-name',default='20261106T131228Z_delivery_95f094b9')
    a=ap.parse_args();r=verify(a.repository,a.delivery_name)
    print(json.dumps({k:v for k,v in r.items() if k!='checks'},ensure_ascii=False,indent=2))
