"""Prespecified paired analysis of saved pilot outcomes; zero new policy/physics execution."""
from __future__ import annotations
import sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from common import *
guard_file_only()
import argparse
import math
import numpy as np
import pandas as pd
import psutil
from analysis_contract import fixed_panel_auc,analysis_checks
from provenance import PilotInputs

ARMS=['BASE','RANDOM_PRE','ONSET'];TASKS=['DO','DC','PU','BP'];TIMES=[0,16000,32000,64000]
PAIRS=[('P-U','ONSET','RANDOM_PRE'),('P-B','ONSET','BASE'),('U-B','RANDOM_PRE','BASE')]

def temporal_history(values):
    gains=losses=recoveries=0;events=[];seen=False;previous=None
    for i,b in enumerate(values):
        if not np.isfinite(b):seen=False;previous=None;continue
        if previous is not None:
            if previous==0 and b==1:
                gains+=1;kind='recovery' if seen else 'first_observed_gain'
                if seen:recoveries+=1
                events.append((i,kind))
            if previous==1 and b==0:losses+=1;events.append((i,'loss'))
        seen=seen or b==1;previous=b
    return gains,losses,recoveries,events

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--campaign',type=Path,required=True);args=ap.parse_args();campaign=args.campaign.resolve()
    started=time.perf_counter();out=campaign/'analysis'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_paired_'+uuid.uuid4().hex[:8])
    out.mkdir(parents=True,exist_ok=False);snap=out/'source_snapshot';snap.mkdir()
    for p in Path(__file__).parent.glob('*.py'):shutil.copy2(p,snap/p.name)
    for p in (BASE/'analysis_contract.py',BASE/'common.py'):shutil.copy2(p,snap/p.name)
    save(out/'source_hashes.json',{p.name:sha(p) for p in snap.iterdir()})
    inputs=PilotInputs(campaign);checks=analysis_checks();errors=[]
    def ck(name,truth,scope='',detail=''):
        checks.append(dict(check=name,passed=bool(truth),scope=str(scope),detail=str(detail)))
        if not truth:errors.append(dict(check=name,scope=str(scope),detail=str(detail)))
    try:
        campaign_cfg=inputs.json(campaign/'campaign_config.json','frozen resource and source locations')
        prep=Path(campaign_cfg['preparation']);protocol=inputs.json(prep/'protocol_resolved.json','fixed protocol and AUC interpretation')
        evaluation=inputs.json(CAMPAIGN/'evaluation_cases/manifest.json','fixed original development panel identities')
        cases=evaluation['cases'];case_map={r['initial_case_id']:r for r in cases}
        plan=pd.read_csv(campaign/'execution_plan.csv');inputs.ref(campaign/'execution_plan.csv','fixed thirty cells')
        adoption=[];raw_rows=[];usage=[];usage_summaries=[]
        for job in sorted((campaign/'jobs').iterdir()):
            if not job.is_dir() or not (job/'COMPLETE.json').exists():continue
            adopted=inputs.json(job/'COMPLETE.json','completed valid job adoption; no successful-attempt cherry-picking')
            adoption.append(adopted);attempt=Path(adopted['attempt'])
            for p in sorted((attempt/'evaluation_episodes').glob('part_*.parquet')):
                frame=inputs.parquet(p,'saved official evaluation outcomes')
                for r in frame.to_dict('records'):
                    r['attempt_path']=str(attempt);r['adopted_attempt_id']=attempt.name
                    r['parent_id']=r.get('parent_id',r['run_id'])
                    r['future_id']=r.get('future_id') or 'SHARED'
                    r['arm']=r.get('arm','SHARED_START')
                    raw_rows.append(r)
            if adopted['kind']=='branch':
                for relative in (0,16000,32000,64000):
                    point=attempt/'archive_usage'/f'{relative:06d}'
                    summary=inputs.json(point/'usage_summary.json','checkpoint-time actual final batch exposure')
                    usage_summaries.append(summary)
                    for p in sorted((point/'archive_usage').glob('part_*.parquet')):usage.append(inputs.parquet(p,'actual actor/critic archive usage'))
        save(out/'adopted_jobs.json',adoption)
        metrics=[];fields=['episode_step','transition_id','success_step','reward','object_pos','goal','joint_position',
            'robot_object_contact_pairs','tcp_object_distance','obs_raw','terminated','truncated','validity_status']
        for index,r in enumerate(raw_rows):
            path=Path(r['trajectory_ref']);side=inputs.json(path.with_suffix('.json'),'evaluation trajectory metadata')
            inputs.ref(path,'original numeric evaluation transitions',expected=side['trajectory']['sha256'])
            with np.load(path,allow_pickle=False) as z:arrays={k:z[k] for k in fields}
            b=arrays['success_step'];reward=arrays['reward'];n=len(b);complete=n==500 and np.array_equal(arrays['episode_step'],np.arange(1,501))
            valid=complete and bool(np.isin(b,[0,1]).all()) and bool((arrays['validity_status']==1).all())
            case=case_map[r['initial_case_id']]
            ck('case task and physical identity',r['physical_case_id']==case['physical_case_id'] and r['task_id']==case['task_id'],r['episode_id'])
            ck('complete episode and step continuity',valid,r['parent_id']+'/'+r['episode_id'])
            hit=np.flatnonzero(b==1);tau=int(hit[0]+1) if len(hit) else None
            success=int(len(hit)>0) if valid else None
            ck('success_any recomputation',success==r['success_any'],r['parent_id']+'/'+r['episode_id'])
            ck('return recomputation tolerance pre-fixed 1e-8 reward units',abs(math.fsum(reward)-r['episode_return'])<=1e-8,r['parent_id']+'/'+r['episode_id'])
            exits=int(((b[:-1]==1)&(b[1:]==0)).sum());entries=int(((b[:-1]==0)&(b[1:]==1)).sum())
            reentries=sum(b[t-1]==0 and b[t]==1 and bool(b[:t-1].any()) for t in range(1,n))
            ck('within-episode event identities',entries-exits==int(b[-1])-int(b[0]) and exits-reentries==int(bool(hit.size))-int(b[-1]),r['parent_id']+'/'+r['episode_id'])
            goal=arrays['goal'];obj=arrays['object_pos'];distance=np.linalg.norm(obj-goal,axis=1)
            raw_h0=arrays['obs_raw'][0,4:7];g0=goal[0]
            if r['task_id']=='DO':
                q0=float(raw_h0[1]-g0[1]-.19);physical_h0=g0+np.array([0,.19+q0,0])
                d0=float(np.linalg.norm(physical_h0-g0));d0_status='derived_from_saved_goal_and_fixed_slide_XML_reset_Y'
            else:d0=float(np.linalg.norm(raw_h0-g0));d0_status='recorded_reset_object_point; no extra coordinate correction assumed'
            metrics.append({**r,'valid':valid,'planned_episode_length':500,'actual_length':n,'recomputed_success_any':success,
                'recomputed_episode_end_success':int(b[-1]) if valid else None,'recomputed_return':math.fsum(reward),
                'recomputed_first_success_step':tau,'success_occupancy':float(b.mean()) if valid else None,
                'success_exit_events':exits,'success_reentry_events':reentries,'minimum_goal_distance_m':float(distance.min()),
                'physical_goal_progress_max_m':float((d0-distance).max()),'initial_goal_distance_m':d0,'initial_geometry_status':d0_status,
                'raw_obs_goal_progress_max_m':float((np.linalg.norm(raw_h0-g0)-distance).max()),
                'joint_min_m':float(np.nanmin(arrays['joint_position'])) if np.isfinite(arrays['joint_position']).any() else None,
                'joint_max_m':float(np.nanmax(arrays['joint_position'])) if np.isfinite(arrays['joint_position']).any() else None,
                'related_contact_steps':int((arrays['robot_object_contact_pairs']>0).sum()),
                'source_trajectory_sha256':side['trajectory']['sha256']})
            if (index+1)%800==0:print(json.dumps(dict(stage='saved evaluation metrics',episodes=index+1)),flush=True)
        episodes=pd.DataFrame(metrics)
        if episodes.empty:raise RuntimeError('No completed valid evaluation input is available')
        key=['parent_id','future_id','arm','task_id','relative_train_step','initial_case_id','physical_case_id']
        ck('original evaluation keys unique',not episodes.duplicated(key).any())
        episodes.to_parquet(out/'evaluation_outcomes.parquet',index=False)
        starts=episodes[episodes.relative_train_step==0].set_index(['parent_id','task_id','initial_case_id','physical_case_id'])
        ck('shared start key unique',not starts.index.duplicated().any())
        post=episodes[episodes.relative_train_step>0].set_index(key)
        cell_rows=[];histories=[];events=[];retention=[]
        for cell in plan.itertuples(index=False):
            for task in TASKS:
                labels=np.full((4,16),np.nan);episode_ids=np.empty((4,16),dtype=object)
                for c in (x for x in cases if x['task_id']==task):
                    col=c['case_index'];cid=c['initial_case_id'];pid=c['physical_case_id']
                    for ti,t in enumerate(TIMES):
                        ix=(cell.parent_id,task,cid,pid) if t==0 else (cell.parent_id,cell.future_id,cell.arm,task,t,cid,pid)
                        frame=starts if t==0 else post
                        if ix in frame.index:
                            row=frame.loc[ix]
                            if isinstance(row,pd.DataFrame):raise RuntimeError('Duplicate evaluation join')
                            if row['valid']:labels[ti,col]=row['success_any'];episode_ids[ti,col]=row['episode_id']
                            else:episode_ids[ti,col]=None
                        else:episode_ids[ti,col]=None
                    values=labels[:,col];g,l,rec,ev=temporal_history(values)
                    known=np.isfinite(values)
                    if known.all():
                        ck('checkpoint gain-loss identity',g-l==values[-1]-values[0],cell.cell_id+'/'+cid)
                        ck('checkpoint loss-recovery identity',l-rec==max(values)-values[-1],cell.cell_id+'/'+cid)
                    hid=f'{cell.cell_id}:{task}:{cid}'
                    histories.append(dict(history_id=hid,parent_id=cell.parent_id,future_id=cell.future_id,arm=cell.arm,task_id=task,
                        initial_case_id=cid,physical_case_id=pid,z0=values[0],z16=values[1],z32=values[2],z64=values[3],
                        gain_events=g,loss_events=l,recovery_events=rec,complete=bool(known.all()),
                        histories_with_gain=int(g>0),histories_with_loss=int(l>0),histories_with_observed_recovery=int(rec>0)))
                    for ti,kind in ev:events.append(dict(history_id=hid,event=kind,previous_relative_step=TIMES[ti-1],current_relative_step=TIMES[ti],
                        previous_episode_id=episode_ids[ti-1,col],current_episode_id=episode_ids[ti,col],interval_not_exact_event_time=True))
                auc=fixed_panel_auc(labels)
                row=dict(parent_id=cell.parent_id,future_id=cell.future_id,arm=cell.arm,task_id=task,cell_id=cell.cell_id,
                    complete=auc['complete'],auc=auc['auc'],auc_lower_bound=auc['auc_lower_bound'],auc_upper_bound=auc['auc_upper_bound'])
                for ti,t in enumerate(TIMES):
                    valid=np.isfinite(labels[ti]);row[f'N_{t}']=int(valid.sum());row[f'J_{t}']=float(labels[ti].mean()) if valid.all() else None
                cell_rows.append(row)
                if np.isfinite(labels[[0,3]]).all():
                    b,y=labels[0],labels[3];G=int(((b==0)&(y==1)).sum());L=int(((b==1)&(y==0)).sum());K=int(((b==1)&(y==1)).sum());F=int(((b==0)&(y==0)).sum())
                    retention.append(dict(parent_id=cell.parent_id,future_id=cell.future_id,arm=cell.arm,task_id=task,N=16,
                        initial_successes=int(b.sum()),final_successes=int(y.sum()),gain_cases=G,loss_cases=L,kept_cases=K,continued_failure_cases=F,
                        G=G/16,L=L/16,K=K/16,F=F/16,conditional_loss_rate=L/b.sum() if b.sum()>0 else None))
        cells=pd.DataFrame(cell_rows)
        for col in ['auc','auc_lower_bound','auc_upper_bound']+[f'J_{t}' for t in TIMES]:cells[col]=pd.to_numeric(cells[col],errors='coerce')
        cells.to_csv(out/'cell_metrics.csv',index=False)
        history=pd.DataFrame(histories);history.to_parquet(out/'checkpoint_case_history.parquet',index=False)
        pd.DataFrame(events).to_parquet(out/'learning_change_events.parquet',index=False)
        ret=pd.DataFrame(retention);ret.to_csv(out/'retention_gain_loss.csv',index=False)
        curves=cells.melt(id_vars=['parent_id','future_id','arm','task_id','cell_id'],value_vars=[f'J_{t}' for t in TIMES],var_name='point',value_name='success_rate')
        curves['relative_train_step']=curves.point.str.replace('J_','',regex=False).astype(int);curves.to_csv(out/'learning_curves.csv',index=False)
        effects=[];discord=[]
        for parent in RUNS:
            for future in ('F01','F02'):
                for name,method,reference in PAIRS:
                    for task in TASKS:
                        m=cells[(cells.parent_id==parent)&(cells.future_id==future)&(cells.arm==method)&(cells.task_id==task)].iloc[0]
                        r=cells[(cells.parent_id==parent)&(cells.future_id==future)&(cells.arm==reference)&(cells.task_id==task)].iloc[0]
                        effects.append(dict(parent_id=parent,future_id=future,contrast=name,method=method,reference=reference,scope=task,
                            delta_auc=m.auc-r.auc,delta_final=m.J_64000-r.J_64000,complete=bool(m.complete and r.complete)))
                        hm=history[(history.parent_id==parent)&(history.future_id==future)&(history.arm==method)&(history.task_id==task)].set_index('physical_case_id')
                        hr=history[(history.parent_id==parent)&(history.future_id==future)&(history.arm==reference)&(history.task_id==task)].set_index('physical_case_id')
                        pair=hm[['z0','z64']].join(hr[['z0','z64']],how='outer',lsuffix='_m',rsuffix='_r',validate='one_to_one')
                        ck('case method/reference join preserves all sixteen cases',len(pair)==16,parent+'/'+future+'/'+task+'/'+name)
                        for initial in (0,1):
                            p=pair[(pair.z0_m==initial)&(pair.z0_r==initial)];valid=p.z64_m.notna()&p.z64_r.notna();v=p[valid]
                            discord.append(dict(parent_id=parent,future_id=future,contrast=name,task_id=task,initial_success=initial,
                                risk_set_cases=len(p),valid_pairs=len(v),method_only=int(((v.z64_m==1)&(v.z64_r==0)).sum()),
                                reference_only=int(((v.z64_m==0)&(v.z64_r==1)).sum()),both_success=int(((v.z64_m==1)&(v.z64_r==1)).sum()),
                                both_failure=int(((v.z64_m==0)&(v.z64_r==0)).sum())))
        effects=pd.DataFrame(effects)
        extras=[]
        for keys,part in effects.groupby(['parent_id','future_id','contrast','method','reference']):
            for scope,tasks in [('OTHER3',['DC','PU','BP']),('MACRO4',TASKS)]:
                p=part[part.scope.isin(tasks)]
                extras.append(dict(zip(['parent_id','future_id','contrast','method','reference'],keys),scope=scope,
                    delta_auc=float(p.delta_auc.to_numpy(dtype=float).mean()),delta_final=float(p.delta_final.to_numpy(dtype=float).mean()),complete=bool(p.complete.all())))
        effects=pd.concat([effects,pd.DataFrame(extras)],ignore_index=True);effects.to_csv(out/'paired_effects_by_parent_future.csv',index=False)
        pd.DataFrame(discord).to_csv(out/'paired_case_discordance.csv',index=False)
        parents=effects.groupby(['parent_id','contrast','scope'],as_index=False).agg(
            delta_auc=('delta_auc',lambda x:x.mean(skipna=False)),delta_final=('delta_final',lambda x:x.mean(skipna=False)),complete=('complete','all'))
        parents.to_csv(out/'parent_effects.csv',index=False)
        complete_design=len(adoption)==35 and len(episodes)==6080 and cells.complete.all() and not errors
        summary=[];boot=None
        if complete_design:
            draws=np.random.Generator(np.random.PCG64(54001)).integers(0,5,size=(20000,5))
            ordered=[];names=[]
            for contrast in [p[0] for p in PAIRS]:
                for scope in TASKS+['OTHER3','MACRO4']:
                    p=parents[(parents.contrast==contrast)&(parents.scope==scope)].set_index('parent_id').loc[RUNS]
                    for metric in ('delta_auc','delta_final'):
                        ordered.append(p[metric].to_numpy());names.append((contrast,scope,metric))
            matrix=np.stack(ordered,axis=1);boot=matrix[draws].mean(axis=1);interval=np.quantile(boot,[.025,.975],axis=0,method='linear')
            np.savez_compressed(out/'bootstrap_draws.npz',parent_indices=draws.astype(np.uint8),contrasts=boot)
            for j,(contrast,scope,metric) in enumerate(names):
                values=matrix[:,j]
                summary.append(dict(contrast=contrast,scope=scope,metric=metric,estimate=float(values.mean()),
                    lower=float(interval[0,j]),upper=float(interval[1,j]),positive_parents=int((values>1e-12).sum()),zero_parents=int((np.abs(values)<=1e-12).sum()),negative_parents=int((values< -1e-12).sum()),
                    lopo_min=float(min(np.delete(values,i).mean() for i in range(5))),lopo_max=float(max(np.delete(values,i).mean() for i in range(5)))))
        tradeoffs=pd.DataFrame(summary,columns=['contrast','scope','metric','estimate','lower','upper','positive_parents','zero_parents','negative_parents','lopo_min','lopo_max']);tradeoffs.to_csv(out/'task_tradeoffs.csv',index=False)
        save(out/'bootstrap_summary.json',dict(performed=complete_design,seed=54001,replicates=20000,unit='parent; average two futures within parent',
            quantile_method='linear',confidence_scope='descriptive parent-composition sensitivity, fixed overlapping LOO archives and 16-case development panels; no population coverage guarantee',
            fixed_random_windows_conditioned_on=True,summary=summary))
        if complete_design:
            def item(contrast,scope,metric='delta_auc'):return next(r for r in summary if r['contrast']==contrast and r['scope']==scope and r['metric']==metric)
            pu=item('P-U','DO');pb=item('P-B','DO')
            signal_checks=dict(DO_PU_at_least_2pp=pu['estimate']>=.02-1e-12,DO_PB_at_least_2pp=pb['estimate']>=.02-1e-12,
                at_least_four_positive_parents_PU=pu['positive_parents']>=4,at_least_four_positive_parents_PB=pb['positive_parents']>=4,
                all_LOPO_PU_positive=pu['lopo_min']>1e-12,all_LOPO_PB_positive=pb['lopo_min']>1e-12,
                other_three_mean_at_least_minus1pp=item('P-B','OTHER3')['estimate']>=-.01-1e-12,
                each_other_task_at_least_minus3pp=all(item('P-B',t)['estimate']>=-.03-1e-12 for t in ('DC','PU','BP')),
                macro_four_nonnegative=item('P-B','MACRO4')['estimate']>=-1e-12,valid_complete_design=True)
            signal=dict(status='nominal_pilot_signal_met' if all(signal_checks.values()) else 'nominal_pilot_signal_not_met',checks=signal_checks)
        else:signal=dict(status='technically_incomplete_not_evaluable',checks={},missing_inputs_are_not_scientific_nulls=True)
        save(out/'operational_signal.json',signal)
        if usage:
            usage_frame=pd.concat(usage,ignore_index=True);usage_frame.to_parquet(out/'archive_usage_by_checkpoint.parquet',index=False)
        usage_summary=pd.DataFrame(usage_summaries);usage_summary.to_csv(out/'archive_usage_summaries.csv',index=False)
        if len(usage_summary):
            pair_checks=[]
            for parent in RUNS:
                for future in ('F01','F02'):
                    sub=usage_summary[(usage_summary.parent_id==parent)&(usage_summary.future_id==future)&(usage_summary.actual_train_step==1064000)]
                    p=sub[sub.arm=='ONSET'];u=sub[sub.arm=='RANDOM_PRE']
                    if len(p)==len(u)==1:
                        same=p.iloc[0].archive_draw_hash==u.iloc[0].archive_draw_hash and p.iloc[0].replacement_mask_hash==u.iloc[0].replacement_mask_hash
                        pair_checks.append(dict(parent_id=parent,future_id=future,common_draws_and_masks=same))
                        ck('complete P U actual primitive draws and masks correspond',same,parent+'/'+future)
            pd.DataFrame(pair_checks).to_csv(out/'paired_exposure_checks.csv',index=False)
        if errors:
            signal=dict(status='technically_incomplete_not_evaluable',checks={},verification_errors=errors)
            save(out/'operational_signal.json',signal,replace=True)
        save(out/'FINAL_STATUS.json',dict(status='complete' if complete_design and not errors else 'partial_or_verification_failure',
            completed_branches=sum(r['kind']=='branch' for r in adoption),planned_branches=30,completed_evaluations=len(episodes),planned_evaluations=6080,
            valid_evaluations=int(episodes.valid.sum()),operational_signal=signal,errors=errors,
            new_analysis_execution=ZERO_EXECUTION,analysis_output=str(out),campaign=str(campaign),preparation=str(prep)))
        print(json.dumps(dict(output=str(out),complete=complete_design,errors=len(errors),operational_signal=signal['status'])),flush=True)
    except BaseException as ex:
        save(out/'FAILED.json',dict(error=repr(ex),at=utc(),new_execution=ZERO_EXECUTION));raise
    finally:
        inputs.flush(out);pd.DataFrame(checks).to_csv(out/'verification_checks.csv',index=False)
        process=psutil.Process()
        save(out/'analysis_costs.json',dict(wall_seconds=time.perf_counter()-started,memory=process.memory_info()._asdict(),cpu=process.cpu_times()._asdict(),
            io=process.io_counters()._asdict(),new_execution=ZERO_EXECUTION,tracked_read_bytes=inputs.bytes_read))
    save(campaign/'LATEST_ANALYSIS.json',dict(output=str(out)),replace=True)

if __name__=='__main__':main()
