"""Independent scalar detector/readiness audit on saved numerical inputs only."""
from __future__ import annotations
from common import *
guard_file_only()
import argparse
import math
import statistics
import numpy as np
import pandas as pd
from sampler_contract import contract_checks
from analysis_contract import analysis_checks

def independent_detector(d,q,sigma):
    L=len(d)-1
    dt={t:statistics.median([d[t-1],d[t],d[t+1]]) for t in range(1,L)}
    qt={t:statistics.median([q[t-1],q[t],q[t+1]]) for t in range(1,L)}
    reasons=[]
    if any(d[0]-d[t]>=.005 for t in range(1,min(16,L)+1)):reasons.append('early_progress_without_context')
    candidates=[]
    for t in range(6,min(sigma-1,L-11)+1):
        before=[qt[x] for x in range(t-5,t)]
        if max(before)-min(before)>.001:continue
        if dt[t-1]-dt[t]<.0001:continue
        if dt[t-1]-dt[t+7]<.005:continue
        if any(dt[t-1]-dt[x]<.0025 for x in range(t+8,t+11)):continue
        candidates.append(t)
    tau=min(candidates) if candidates else None
    if tau is None:reasons.append('no_qualifying_onset')
    else:
        if -(qt[tau+7]-qt[tau-1])<=0:reasons.append('signal_inconsistent')
        if tau<17:reasons.append('left_window_incomplete')
        if tau+15>L:reasons.append('right_window_incomplete')
        if tau+15>=sigma:reasons.append('window_reaches_first_success')
    return tau,reasons

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--preparation',type=Path,required=True);args=ap.parse_args()
    prep=args.preparation.resolve();out=new_output('independent_verification');inputs=Inputs();checks=[];started=time.perf_counter()
    def ck(name,v,scope='',detail=''):
        checks.append(dict(check=name,passed=bool(v),scope=scope,detail=detail))
        if not v:raise AssertionError(name+': '+str(scope)+' '+str(detail))
    try:
        resolved=inputs.json(prep/'protocol_resolved.json','physical x0 mapping version')
        cand=inputs.parquet(prep/'onset_candidates_and_exclusions.parquet','preparation outputs under independent check')
        wins=inputs.parquet(prep/'archive_windows.parquet','fixed P U window metadata')
        receivers=inputs.parquet(prep/'source_success_episodes.parquet','complete positive episode population')
        ck('positive source IDs unique',not cand.permanent_episode_id.duplicated().any() and set(cand.permanent_episode_id)==set(receivers.permanent_episode_id))
        qas=[]
        for row in cand.itertuples(index=False):
            path=Path(row.trajectory_ref);z=inputs.npz(path,'independent reread of positive raw trajectory')
            h0_raw=[float(x) for x in z['obs_raw'][0,4:7]];g=[float(x) for x in z['goal'][0]]
            q0=h0_raw[1]-g[1]-.19
            h0=([g[0],g[1]+.19+q0,g[2]] if 'initial_physical_mapping' in resolved else h0_raw)
            h=[h0]+[list(map(float,x)) for x in z['object_pos']]
            d=[math.sqrt(sum((hi[i]-g[i])**2 for i in range(3))) for hi in h]
            q=[q0]+[float(x) for x in z['qpos'][:,9]]
            sigma=next(i for i,b in enumerate(z['success_step'],1) if b==1)
            tau,reasons=independent_detector(d,q,sigma)
            ck('scalar first candidate equals preparation',tau==(None if pd.isna(row.tau) else int(row.tau)),row.permanent_episode_id,str((tau,row.tau)))
            ck('scalar exclusions equal preparation',set(reasons)==set(row.exclusion_reasons.split('|') if row.exclusion_reasons else []),row.permanent_episode_id,str(reasons))
            ck('scalar eligibility equals preparation',(not reasons)==bool(row.eligible),row.permanent_episode_id)
            gconstant=all(np.array_equal(z['goal'][i],z['goal'][0]) for i in range(len(z['goal'])))
            ck('goal constant and first-success indexing',gconstant and sigma==row.sigma,row.permanent_episode_id)
            early_t=next((t for t in range(1,17) if d[0]-d[t]>=.005),None)
            first16_joint_range=max(q[:17])-min(q[:17])
            qas.append(dict(donor_run=row.donor_run,episode_id=row.episode_id,permanent_episode_id=row.permanent_episode_id,
                eligible=bool(row.eligible),primary_exclusion=row.primary_exclusion,
                first_early_5mm_step=early_t,detector_physical_d0_m=d[0],raw_d0_m=math.sqrt(sum((h0_raw[i]-g[i])**2 for i in range(3))),raw_d1_m=d[1],detector_d0_minus_d1_m=d[0]-d[1],
                first16_joint_range_m=first16_joint_range,initial_handle_x=h0[0],first_endpoint_handle_x=h[1][0],goal_x=g[0],
                x0_handle_to_goal_x_gap_m=h0[0]-g[0],x1_handle_to_goal_x_gap_m=h[1][0]-g[0],
                x0_to_x1_y_change_m=h[1][1]-h0[1],q0_to_q1_change_m=q[1]-q[0],
                initial_x_discontinuity_with_negligible_joint=bool(early_t==1 and abs(q[1]-q[0])<1e-6 and abs(h[1][1]-h0[1])<1e-6 and abs(h0[0]-g[0])>1e-6)))
            for win in wins[wins.permanent_episode_id==row.permanent_episode_id].itertuples(index=False):
                a,b=int(win.start),int(win.end)
                ck('window original 32 contiguous IDs, none at/after success',len(z['transition_id'][a-1:b])==32 and b<sigma and int(z['transition_id'][a-1])==win.first_transition_id and int(z['transition_id'][b-1])==win.last_transition_id,row.permanent_episode_id+'/'+win.arm)
        qa=pd.DataFrame(qas);qa.to_csv(out/'initial_signal_quality.csv',index=False)
        readiness=inputs.json(prep/'readiness.json','frozen receiver support counts')
        for run in RUNS:
            eligible=cand[(cand.donor_run!=run)&cand.eligible]
            counts=eligible.groupby('donor_run').size().to_dict();m=readiness['receivers'][run]
            ck('independent LOO episode and donor support',len(eligible)==m['eligible_episodes'] and all(int(counts.get(k,0))==v for k,v in m['donor_counts'].items()),run)
            ck('receiver excluded from pool',run not in set(eligible.donor_run),run)
            p=wins[(wins.arm=='ONSET')&wins.permanent_episode_id.isin(eligible.permanent_episode_id)]
            u=wins[(wins.arm=='RANDOM_PRE')&wins.permanent_episode_id.isin(eligible.permanent_episode_id)]
            ck('P U same source episodes and length support',set(p.permanent_episode_id)==set(u.permanent_episode_id)==set(eligible.permanent_episode_id) and p.length.sum()==u.length.sum()==32*len(eligible),run)
            independent=(len(eligible)>=8 and sum(n>=2 for n in counts.values())>=2 and not (len(p)>0 and (p.overlap_transitions==32).all()))
            ck('readiness truth value from exact operational minima',independent==m['archive_support_ready'],run)
        checks.extend(contract_checks());checks.extend(analysis_checks())
        # Preserve all 30 cells as unexecuted, never drop the receivers that lack support.
        plan=pd.read_csv(prep/'execution_plan.csv')
        ck('all thirty fixed cells retained without execution',len(plan)==30 and plan.cell_id.nunique()==30 and (plan.status=='not_started').all())
        save(out/'initial_signal_summary.json',dict(successful_episodes=len(qa),early_exclusions=int((qa.primary_exclusion=='early_progress_without_context').sum()),
            early_exclusions_first_step=int(((qa.primary_exclusion=='early_progress_without_context')&(qa.first_early_5mm_step==1)).sum()),
            early_exclusions_with_initial_x_discontinuity_and_negligible_joint=int(((qa.primary_exclusion=='early_progress_without_context')&qa.initial_x_discontinuity_with_negligible_joint).sum()),
            rule_changed=False,alternative_detector_run=False))
        save(out/'FINAL_STATUS.json',dict(status='passed',scope='independent scalar raw-data detector, LOO, window, sampler and AUC contracts',
            check_rows=len(checks),all_passed=all(r['passed'] for r in checks),preparation=str(prep),new_execution=ZERO_EXECUTION))
        print(json.dumps(clean(dict(out=out,checks=len(checks),all_passed=True,initial_signal_summary=load(out/'initial_signal_summary.json'))),ensure_ascii=False))
    except BaseException as ex:
        save(out/'FAILED.json',dict(error=repr(ex),new_execution=ZERO_EXECUTION));raise
    finally:
        inputs.flush(out);pd.DataFrame(checks).to_csv(out/'verification_checks.csv',index=False)
        save(out/'costs.json',dict(wall_seconds=time.perf_counter()-started,new_execution=ZERO_EXECUTION,tracked_read_bytes=inputs.bytes_read))
    save(HERE/'LATEST_VERIFICATION.json',dict(output=out,preparation=str(prep)),replace=True)

if __name__=='__main__':main()
