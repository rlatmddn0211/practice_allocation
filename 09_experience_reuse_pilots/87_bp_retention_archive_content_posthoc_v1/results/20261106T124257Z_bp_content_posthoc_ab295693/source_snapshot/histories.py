"""BP risk-set-fixed histories, paired effects and repetition from stored labels."""
from __future__ import annotations
import numpy as np
import pandas as pd
from common import *


def history(values):
    z=np.asarray(values,dtype=int);hits=np.flatnonzero(z);g=int(((z[:-1]==0)&(z[1:]==1)).sum());l=int(((z[:-1]==1)&(z[1:]==0)).sum())
    recovery=sum(z[i-1]==0 and z[i]==1 and bool(z[:i-1].any()) for i in range(1,4))
    first=int(hits[0]) if len(hits) else None
    initial=int(z[0]);final=int(z[-1]);pattern=''.join(map(str,z.tolist()))
    if initial:
        category='all_four_observed_success' if bool(z.all()) else ('observed_loss_then_final_recovery' if final else 'final_failure_after_initial_success')
    else:category='initial_failure_final_success' if final else ('observed_acquisition_then_final_failure' if len(hits) else 'never_observed_success')
    return dict(pattern=pattern,initial_success=initial,final_success=final,gain_events=g,loss_events=l,recovery_events=int(recovery),
        history_category=category,first_success_index=first,first_success_train_step=TIMES[first] if first is not None else None,
        subsequent_evaluation_opportunities=3-first if first is not None else None,
        loss_after_first_success=bool(l>0) if first is not None else None,
        all_observed_after_first_success=bool(z[first:].all()) if first is not None else None,
        case_auc=float(np.dot([.125,.25,.375,.25],z)))


def run(out,inputs,checks):
    e=inputs.parquet(ANALYSIS/'evaluation_outcomes.parquet','original85 all evaluation outcomes')
    h=inputs.parquet(ANALYSIS/'checkpoint_case_history.parquet','original85 common-case label histories')
    old_effects=inputs.csv(ANALYSIS/'paired_effects_by_parent_future.csv','original paired effects')
    old_intervals=inputs.csv(ANALYSIS/'task_tradeoffs.csv','reuse existing uncertainty, no new draws')
    bp=h[h.task_id=='BP'].copy();key=['parent_id','future_id','arm','physical_case_id']
    checks.add('BP480 arm histories unique',len(bp)==480 and not bp.duplicated(key).any())
    rows=[]
    for r in bp.to_dict('records'):
        z=[int(r[x]) for x in ['z0','z16','z32','z64']];d=history(z);d.update({k:r[k] for k in ['history_id','parent_id','future_id','arm','initial_case_id','physical_case_id']})
        d.update(z0=z[0],z16=z[1],z32=z[2],z64=z[3]);rows.append(d)
        checks.add('gain-loss telescoping '+r['history_id'],d['gain_events']-d['loss_events']==z[-1]-z[0])
        checks.add('loss-recovery telescoping '+r['history_id'],d['loss_events']-d['recovery_events']==max(z)-z[-1])
    histories=pd.DataFrame(rows)
    start=e[(e.task_id=='BP')&(e.relative_train_step==0)]
    checks.add('BP80 unique parent-case starts',len(start)==80 and not start.duplicated(['parent_id','physical_case_id']).any())
    checks.add('BP start74/6, reused148/12 per arm',int(start.success_any.sum())==74 and
        all((len(x)==160 and int(x.initial_success.sum())==148) for _,x in histories.groupby('arm')))
    wide=histories.pivot(index=['parent_id','future_id','initial_case_id','physical_case_id'],columns='arm',
        values=['pattern','case_auc','initial_success','final_success','history_category','first_success_train_step','subsequent_evaluation_opportunities'])
    wide.columns=[f'{arm}_{field}' for field,arm in wide.columns];wide=wide.reset_index()
    for r in wide.itertuples(index=False):checks.add('common initial label across three arms '+r.parent_id+'/'+r.future_id+'/'+r.initial_case_id,
        r.BASE_initial_success==r.ONSET_initial_success==r.RANDOM_PRE_initial_success)
    wide.to_parquet(out/'bp_160_paired_histories.parquet',index=False);wide.to_csv(out/'bp_160_paired_histories.csv',index=False)
    histories.to_parquet(out/'bp_arm_histories.parquet',index=False)
    patterns=histories.groupby(['arm','initial_success','pattern','history_category'],as_index=False).agg(histories=('history_id','size'))
    patterns.to_csv(out/'bp_history_pattern_counts.csv',index=False)
    acquisition=histories[histories.initial_success==0].groupby(['arm','first_success_train_step','subsequent_evaluation_opportunities'],dropna=False,as_index=False).agg(
        histories=('history_id','size'),final_successes=('final_success','sum'),histories_with_later_loss=('loss_after_first_success','sum'),recovery_events=('recovery_events','sum'))
    acquisition.to_csv(out/'bp_first_acquisition_opportunities.csv',index=False)
    arms=[]
    for keys,x in histories.groupby(['parent_id','future_id','arm']):
        parent,future,arm=keys;b=x.initial_success.to_numpy();y=x.final_success.to_numpy()
        r=dict(parent_id=parent,future_id=future,arm=arm,N=16,initial_successes=int(b.sum()),final_successes=int(y.sum()),
            gain_cases=int(((b==0)&(y==1)).sum()),loss_cases=int(((b==1)&(y==0)).sum()),
            kept_cases=int(((b==1)&(y==1)).sum()),auc=float(x.case_auc.mean()),
            all_four_observed_success=int((x.history_category=='all_four_observed_success').sum()),
            initial_success_final_recovery=int((x.history_category=='observed_loss_then_final_recovery').sum()),
            gain_events=int(x.gain_events.sum()),loss_events=int(x.loss_events.sum()),recovery_events=int(x.recovery_events.sum()))
        for t,col in zip(TIMES,['z0','z16','z32','z64']):r['J_'+str(t)]=float(x[col].mean());r['delta_from_start_'+str(t)]=float(x[col].mean()-b.mean())
        arms.append(r)
    arms=pd.DataFrame(arms);arms.to_csv(out/'bp_arm_parent_future.csv',index=False)
    pairs=[];case_pairs=[];point_rows=[]
    for parent in RUNS:
        for future in ['F01','F02']:
            for name,m,r in PAIRS:
                s=arms[(arms.parent_id==parent)&(arms.future_id==future)].set_index('arm');a=s.loc[m];b=s.loc[r]
                row=dict(parent_id=parent,future_id=future,contrast=name,method=m,reference=r,delta_auc=a.auc-b.auc,
                    final_delta_J=(a.final_successes-b.final_successes)/16,avoided_initial_loss=(b.loss_cases-a.loss_cases)/16,
                    delta_initial_failure_final_gain=(a.gain_cases-b.gain_cases)/16,
                    delta_all_four_success=(a.all_four_observed_success-b.all_four_observed_success)/16,
                    delta_initial_success_final_recovery=(a.initial_success_final_recovery-b.initial_success_final_recovery)/16,
                    method_initial_loss=int(a.loss_cases),reference_initial_loss=int(b.loss_cases),
                    method_final_recovery=int(a.initial_success_final_recovery),reference_final_recovery=int(b.initial_success_final_recovery))
                for t in TIMES:row['delta_J_'+str(t)]=a['J_'+str(t)]-b['J_'+str(t)]
                old=old_effects[(old_effects.parent_id==parent)&(old_effects.future_id==future)&(old_effects.contrast==name)&(old_effects.scope=='BP')].iloc[0]
                checks.add('original BP effect agrees '+parent+'/'+future+'/'+name,abs(row['delta_auc']-old.delta_auc)<1e-12 and abs(row['final_delta_J']-old.delta_final)<1e-12)
                checks.add('final acquisition-retention decomposition '+parent+'/'+future+'/'+name,
                    abs(row['final_delta_J']-row['avoided_initial_loss']-row['delta_initial_failure_final_gain'])<1e-12)
                pairs.append(row)
                hm=histories[(histories.parent_id==parent)&(histories.future_id==future)&(histories.arm==m)].set_index('physical_case_id')
                hr=histories[(histories.parent_id==parent)&(histories.future_id==future)&(histories.arm==r)].set_index('physical_case_id')
                for case,rm in hm.iterrows():
                    rr=hr.loc[case];ym=int(rm.final_success);yr=int(rr.final_success)
                    kind='method_only_final_success' if ym and not yr else 'reference_only_final_success' if yr and not ym else 'identical_four_time_history' if rm.pattern==rr.pattern else 'both_final_success_different_history' if ym else 'both_final_failure_different_history'
                    case_pairs.append(dict(parent_id=parent,future_id=future,contrast=name,method=m,reference=r,physical_case_id=case,
                        initial_case_id=rm.initial_case_id,initial_success=int(rm.initial_success),method_pattern=rm.pattern,reference_pattern=rr.pattern,
                        method_final=ym,reference_final=yr,case_type=kind,delta_case_auc=rm.case_auc-rr.case_auc))
                    for ti,(t,col) in enumerate(zip(TIMES,['z0','z16','z32','z64'])):
                        point_rows.append(dict(parent_id=parent,future_id=future,contrast=name,initial_case_id=rm.initial_case_id,
                            physical_case_id=case,relative_train_step=t,initial_success=int(rm.initial_success),method_success=int(rm[col]),reference_success=int(rr[col]),
                            case_type=kind,method_pattern=rm.pattern,reference_pattern=rr.pattern))
    pairs=pd.DataFrame(pairs);pairs.to_csv(out/'bp_paired_effects_parent_future.csv',index=False)
    parents=pairs.groupby(['parent_id','contrast'],as_index=False).mean(numeric_only=True);parents.to_csv(out/'bp_parent_effects.csv',index=False)
    overall=parents.groupby('contrast',as_index=False).mean(numeric_only=True);overall.to_csv(out/'bp_effect_summary.csv',index=False)
    lopo=[]
    for name,x in parents.groupby('contrast'):
        for parent in RUNS:lopo.append(dict(contrast=name,excluded_receiver=parent,**x[x.parent_id!=parent].drop(columns=['parent_id','contrast']).mean().to_dict()))
    pd.DataFrame(lopo).to_csv(out/'bp_lopo.csv',index=False)
    pd.DataFrame(case_pairs).to_parquet(out/'bp_case_contrasts.parquet',index=False);pd.DataFrame(point_rows).to_parquet(out/'bp_case_point_contrasts.parquet',index=False)
    case_pairs=pd.DataFrame(case_pairs)
    case_pairs.groupby(['contrast','initial_success','case_type'],as_index=False).agg(cases=('physical_case_id','size')).to_csv(out/'bp_case_type_counts.csv',index=False)
    loss_blocks=[]
    for r in histories.to_dict('records'):
        z=[r[c] for c in ['z0','z16','z32','z64']]
        for ti in range(1,4):
            if z[ti-1]!=1 or z[ti]!=0:continue
            recovery=next((j for j in range(ti+1,4) if z[j]),None)
            loss_blocks.append(dict(history_id=r['history_id'],parent_id=r['parent_id'],future_id=r['future_id'],arm=r['arm'],physical_case_id=r['physical_case_id'],initial_case_id=r['initial_case_id'],
                last_success_step=TIMES[ti-1],first_failed_step=TIMES[ti],first_recovered_step=TIMES[recovery] if recovery is not None else None,
                recovery_status='observed' if recovery is not None else 'not_observed_by64k',pattern=r['pattern']))
    pd.DataFrame(loss_blocks).to_parquet(out/'bp_loss_blocks.parquet',index=False)
    old_intervals[old_intervals.scope=='BP'].to_csv(out/'bp_original_uncertainty.csv',index=False)
    for name,retain,gain,total in [('P-B',32,8,40),('P-U',8,3,11)]:
        x=pairs[pairs.contrast==name]
        checks.add('user reference count decomposition '+name,np.isclose(x.avoided_initial_loss.sum()*16,retain) and
            np.isclose(x.delta_initial_failure_final_gain.sum()*16,gain) and np.isclose(x.final_delta_J.sum()*16,total))
    return dict(episodes=e,histories=histories,wide=wide,arms=arms,pairs=pairs,parents=parents,case_pairs=case_pairs)
