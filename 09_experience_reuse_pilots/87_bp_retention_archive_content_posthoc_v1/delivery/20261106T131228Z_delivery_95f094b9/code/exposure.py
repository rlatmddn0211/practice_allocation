"""Checkpoint-difference actual final-batch use and time-respecting BP linkage."""
from __future__ import annotations
import numpy as np
import pandas as pd
from common import *

FEATURES=['goal_distance_pre_m','goal_distance_post_m','opening_pre_m','opening_from_initial_pre_m','opening_increment_m',
    'opening_positive_m','closing_positive_m','goal_axis_command','action_x','action_y','action_z','move_command_norm','gripper_command',
    'actual_TCP_move_m','actual_TCP_goal_axis_move_m','actual_TCP_x_move_m','actual_TCP_y_move_m','actual_TCP_z_move_m',
    'action_xyz_change','gripper_command_change','reward','contact_endpoint','contact_pair_samples','TCP_handle_distance_pre_m',
    'TCP_handle_distance_post_m','gripper_width_post_m','joint_velocity_post_m_per_s',
    'TCP_minus_handle_x_pre_m','TCP_minus_handle_y_pre_m','TCP_minus_handle_z_pre_m']


def weighted(x,counts):
    n=np.asarray(counts,dtype=float);total=float(n.sum());row=dict(actual_uses=int(total))
    if total==0:
        row.update({f:np.nan for f in FEATURES});row.update(unique_transitions=0,unique_episodes=0,repeat_draw_fraction=np.nan,max_episode_share=np.nan)
        return row
    for f in FEATURES:row[f]=float(np.dot(n,x[f])/total)
    used=x.loc[n>0];row['unique_transitions']=int(used.archive_transition_id.nunique());row['unique_episodes']=int(used.source_episode_id.nunique())
    row['repeat_draw_fraction']=1-row['unique_transitions']/total
    temp=pd.DataFrame(dict(episode=x.source_episode_id,n=n)).groupby('episode').n.sum();row['max_episode_share']=float(temp.max()/total)
    return row


def run(out,inputs,checks,hist,phys):
    use=inputs.parquet(ANALYSIS/'archive_usage_by_checkpoint.parquet','actual archive actor/critic cumulative counts at fixed four checkpoints')
    summaries=inputs.csv(ANALYSIS/'archive_usage_summaries.csv','native draw versus actual use, original paired hashes')
    pair_hash=inputs.csv(ANALYSIS/'paired_exposure_checks.csv','original private draw/mask correspondences')
    checks.add('all10 original paired exposure hashes passed',len(pair_hash)==10 and pair_hash.common_draws_and_masks.all())
    key=['parent_id','future_id','arm','source_episode_id','window_offset','archive_transition_id']
    checks.add('actual cumulative usage keys unique',not use.duplicated(key+['checkpoint']).any())
    checks.add('actor and critic actual use agree',np.array_equal(use.actor_sample_count,use.critic_sample_count))
    checks.add('BASE actual archive use zero',int(use[use.arm=='BASE'].actor_sample_count.sum())==0)
    nonbase=use[use.arm!='BASE'].sort_values(key+['checkpoint']).copy()
    offsets=nonbase.pivot(index=['parent_id','future_id','checkpoint','source_episode_id','window_offset'],columns='arm',values='actor_sample_count')
    checks.add('P/U exact episode-offset cumulative draws match',not offsets.isna().any().any() and np.array_equal(offsets.ONSET,offsets.RANDOM_PRE))
    rows=[]
    for keys,x in nonbase.groupby(key,sort=False):
        x=x.sort_values('checkpoint');c=x.actor_sample_count.to_numpy();q=x.checkpoint.to_numpy()-1000000
        checks.add('four checkpoints monotonic actual use '+str(keys),np.array_equal(q,TIMES) and c[0]==0 and bool((np.diff(c)>=0).all()))
        base=dict(zip(key,keys))
        for i in range(1,4):rows.append(dict(**base,interval_start=TIMES[i-1],interval_end=TIMES[i],
            interval_actor_use=int(c[i]-c[i-1]),interval_critic_use=int(c[i]-c[i-1]),cumulative_actor_use=int(c[i])))
    intervals=pd.DataFrame(rows)
    features=phys['transitions'].copy();join=['arm','source_episode_id','window_offset','archive_transition_id']
    cols=join+['donor_run','archive_window_id']+FEATURES
    joined=intervals.merge(features[cols],on=join,how='left',validate='many_to_one',indicator=True)
    checks.add('actual use joins every immutable source transition',len(joined)==len(intervals) and bool((joined._merge=='both').all()))
    joined=joined.drop(columns='_merge');checks.add('receiver absent from all LOO used sources',bool((joined.parent_id!=joined.donor_run).all()))
    joined.to_parquet(out/'actual_transition_usage_by_interval.parquet',index=False)
    interval_features=[];cumulative_features=[];source_weights=[];donor_weights=[]
    for keys,x in joined.groupby(['parent_id','future_id','arm','interval_start','interval_end']):
        parent,future,arm,lo,hi=keys;base=dict(parent_id=parent,future_id=future,arm=arm,interval_start=lo,interval_end=hi,
            interval_env_steps=hi-lo,interval_actor_updates=hi-lo)
        r={**base,**weighted(x,x.interval_actor_use)};r['uses_per1000_train_transitions']=r['actual_uses']/(hi-lo)*1000;r['uses_per_actor_update']=r['actual_uses']/(hi-lo);interval_features.append(r)
        c={**base,**weighted(x,x.cumulative_actor_use)};c['uses_per1000_train_transitions']=c['actual_uses']/hi*1000;cumulative_features.append(c)
        for episode,e in x.groupby('source_episode_id'):
            source_weights.append(dict(**base,source_episode_id=episode,donor_run=e.donor_run.iloc[0],actual_uses=int(e.interval_actor_use.sum()),
                share=float(e.interval_actor_use.sum()/r['actual_uses'])))
        for donor,e in x.groupby('donor_run'):
            donor_weights.append(dict(**base,donor_run=donor,actual_uses=int(e.interval_actor_use.sum()),share=float(e.interval_actor_use.sum()/r['actual_uses'])))
        old=summaries[(summaries.parent_id==parent)&(summaries.future_id==future)&(summaries.arm==arm)].set_index('actual_train_step')
        expected=int(old.loc[1000000+hi,'archive_actual_use']-old.loc[1000000+lo,'archive_actual_use'])
        checks.add('interval actual use matches native/archive accounting '+str(keys),expected==r['actual_uses'])
    interval_features=pd.DataFrame(interval_features);cumulative_features=pd.DataFrame(cumulative_features)
    interval_features.to_csv(out/'actual_interval_exposure_features.csv',index=False);cumulative_features.to_csv(out/'actual_cumulative_exposure_features.csv',index=False)
    pd.DataFrame(source_weights).to_parquet(out/'actual_episode_weights_by_interval.parquet',index=False)
    pd.DataFrame(donor_weights).to_csv(out/'actual_donor_weights_by_interval.csv',index=False)
    # Baseline has no archive exposure: conditional content means remain NA.
    baseline=[]
    for parent in RUNS:
        for future in ['F01','F02']:
            for lo,hi in zip(TIMES[:-1],TIMES[1:]):baseline.append(dict(parent_id=parent,future_id=future,arm='BASE',interval_start=lo,interval_end=hi,actual_uses=0,content_status='not_applicable_no_archive_replacement'))
    pd.DataFrame(baseline).to_csv(out/'baseline_no_archive_exposure.csv',index=False)
    linkage=[];h=hist['histories'];allcells=inputs.csv(ANALYSIS/'cell_metrics.csv','other-task point tradeoffs at matching checkpoints')
    for parent in RUNS:
        for future in ['F01','F02']:
            for lo,hi in zip(TIMES[:-1],TIMES[1:]):
                ii=TIMES.index(hi)
                for name,m,r in PAIRS:
                    row=dict(parent_id=parent,future_id=future,contrast=name,method=m,reference=r,interval_start=lo,interval_end=hi,
                        exposure_latest_allowed_train_step=hi,N_BP=16)
                    for role,arm in [('method',m),('reference',r)]:
                        x=h[(h.parent_id==parent)&(h.future_id==future)&(h.arm==arm)];z=x[['z0','z16','z32','z64']].to_numpy(dtype=int);b=z[:,0];prefix=z[:,:ii+1];y=prefix[:,-1]
                        row[role+'_J_end']=float(y.mean());row[role+'_J_previous']=float(z[:,ii-1].mean())
                        row[role+'_initial_loss_end']=int(((b==1)&(y==0)).sum())
                        row[role+'_initial_success_no_observed_loss']=int(((b==1)&prefix.all(axis=1)).sum())
                        row[role+'_initial_success_recovered_end']=int(((b==1)&(y==1)&(~prefix.all(axis=1))).sum())
                        row[role+'_initial_failure_success_end']=int(((b==0)&(y==1)).sum())
                        row[role+'_initial_failure_first_success_at_end']=sum(int(zj[0]==0 and zj[ii]==1 and not zj[:ii].any()) for zj in z)
                        dt=np.diff(np.asarray(TIMES[:ii+1]));row[role+'_AUC0_to_end']=float(np.sum(dt*(prefix[:,:-1].mean(axis=0)+prefix[:,1:].mean(axis=0))/2)/hi)
                        for scope,frame in [('interval',interval_features),('cumulative',cumulative_features)]:
                            f=frame[(frame.parent_id==parent)&(frame.future_id==future)&(frame.arm==arm)&(frame.interval_end==hi)]
                            if arm=='BASE':
                                row[scope+'_'+role+'_actual_uses']=0
                                for feature in FEATURES:row[scope+'_'+role+'_'+feature]=np.nan
                            else:
                                checks.add('linkage exposure observed only through endpoint',len(f)==1 and f.iloc[0].interval_end==hi)
                                f=f.iloc[0];row[scope+'_'+role+'_actual_uses']=int(f.actual_uses)
                                for feature in FEATURES:row[scope+'_'+role+'_'+feature]=float(f[feature])
                    row['BP_delta_J_end']=row['method_J_end']-row['reference_J_end']
                    row['BP_delta_J_interval_change']=(row['method_J_end']-row['method_J_previous'])-(row['reference_J_end']-row['reference_J_previous'])
                    row['BP_delta_AUC0_to_end']=row['method_AUC0_to_end']-row['reference_AUC0_to_end']
                    row['BP_avoided_initial_loss_end']=(row['reference_initial_loss_end']-row['method_initial_loss_end'])/16
                    row['BP_delta_initial_gain_end']=(row['method_initial_failure_success_end']-row['reference_initial_failure_success_end'])/16
                    for scope in ['interval','cumulative']:
                        for feature in FEATURES:row[scope+'_delta_'+feature]=row[scope+'_method_'+feature]-row[scope+'_reference_'+feature]
                    for task in ['DO','PU','DC']:
                        q=allcells[(allcells.parent_id==parent)&(allcells.future_id==future)&(allcells.task_id==task)].set_index('arm')
                        row[task+'_delta_J_end']=float(q.loc[m,'J_'+str(hi)]-q.loc[r,'J_'+str(hi)])
                    linkage.append(row)
    linkage=pd.DataFrame(linkage);linkage.to_parquet(out/'exposure_BP_effect_linkage.parquet',index=False);linkage.to_csv(out/'exposure_BP_effect_linkage.csv',index=False)
    stability=[]
    for parent in RUNS:
        for hi in TIMES[1:]:
            part=linkage[(linkage.parent_id==parent)&(linkage.interval_end==hi)&(linkage.contrast=='P-U')].set_index('future_id')
            for f in FEATURES:
                field='cumulative_delta_'+f;a=part.loc['F01',field];b=part.loc['F02',field]
                stability.append(dict(parent_id=parent,interval_end=hi,feature=f,P_U_feature_F01=a,P_U_feature_F02=b,
                    absolute_future_feature_gap=abs(a-b),BP_delta_J_F01=part.loc['F01','BP_delta_J_end'],BP_delta_J_F02=part.loc['F02','BP_delta_J_end'],
                    BP_delta_AUC_F01=part.loc['F01','BP_delta_AUC0_to_end'],BP_delta_AUC_F02=part.loc['F02','BP_delta_AUC0_to_end']))
    pd.DataFrame(stability).to_csv(out/'feature_and_effect_future_stability.csv',index=False)
    checks.add('all90 time-respecting comparison links',len(linkage)==90 and bool((linkage.exposure_latest_allowed_train_step==linkage.interval_end).all()))
    print(json.dumps(dict(stage='exposure and linkage complete',interval_transition_rows=len(joined),exposure_rows=len(interval_features),linkage_rows=len(linkage))),flush=True)
    return dict(interval=interval_features,cumulative=cumulative_features,linkage=linkage,source_weights=pd.DataFrame(source_weights),donor_weights=pd.DataFrame(donor_weights))
