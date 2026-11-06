"""Audit source assets and apply the exact detector before any new environment work."""
from __future__ import annotations
from common import *
guard_file_only()
import numpy as np
import pandas as pd
import xml.etree.ElementTree as ET
import psutil
from detector import detect, random_pre_start, derived_seed, synthetic_checks

def resolve(path):
    path=Path(path); return path if path.is_absolute() else ROOT/path

def main():
    out=new_output('preparation'); inputs=Inputs(); started=time.perf_counter(); checks=[]
    protocol=load(HERE/'protocol_resolved.json'); save(out/'protocol_resolved.json',protocol)
    save(out/'RUNNING_STATUS.json',dict(stage='file preparation',started=utc(),new_execution=ZERO_EXECUTION))
    save(out/'dependencies.json',dependencies())
    def check(name, passed, scope='', detail='', critical=True):
        row=dict(check=name,passed=bool(passed),scope=str(scope),detail=str(detail),critical=critical)
        checks.append(row)
        if critical and not passed: raise RuntimeError(name+': '+str(scope)+' '+str(detail))
    try:
        checks.extend(synthetic_checks())
        inputs.text(ROOT/'AGENTS.md','repository rules read before work')
        inputs.json(CAMPAIGN/'FINAL_STATUS.json','completed original campaign identity and original costs')
        baseline=inputs.json(CAMPAIGN/'baseline_manifest.json','pinned baseline packages/source references')
        config=inputs.json(CAMPAIGN/'config_resolved.json','original four-task SAC config')
        receipt=inputs.json(CAMPAIGN/'input_receipt.json','original source/XML asset hashes')
        inputs.json(CAMPAIGN/'protocol.json','original observation protocol')
        inputs.json(CAMPAIGN/'seed_manifest.json','original seeds; not reused as continuation streams')
        inputs.json(CAMPAIGN/'technical_certification.json','original tested runtime restoration scope')
        for path in [ROOT/'81_basic_sac_observation_campaign_v1/results/20261102T085036Z_observation_8e858967/analysis/20261103T000632Z_f77754/report_ko.md',
            ROOT/'82_basic_observation_exploratory_report_v1/results/20261103T000931Z_1c0dc354/report_ko.md',
            ROOT/'84_four_stage_observation_posthoc_v1/delivery/20261105T045701Z_delivery_9f3c1d2d/report_ko.md']:
            inputs.text(path,'prior report, source observations only, not independent evidence')
        expected={str(Path(r['path']).resolve()):r['sha256'] for r in receipt['files']}
        source_paths=[SITE/'metaworld/envs/sawyer_drawer_open_v3.py',SITE/'metaworld/sawyer_xyz_env.py',
            SITE/'gymnasium/envs/mujoco/mujoco_env.py',SITE/'metaworld/assets/sawyer_xyz/sawyer_drawer.xml',
            SITE/'metaworld/assets/objects/assets/drawer.xml',SITE/'metaworld/assets/objects/assets/drawer_dependencies.xml',
            SITE/'stable_baselines3/sac/sac.py',SITE/'stable_baselines3/common/buffers.py']
        for p in source_paths:
            digest=expected.get(str(p.resolve()),baseline.get('code_hashes',{}).get(str(p)))
            inputs.ref(p,'original source/XML text mapping',read_mode='UTF-8 source text',expected=digest)
        env_text=(SITE/'metaworld/envs/sawyer_drawer_open_v3.py').read_text(encoding='utf-8')
        check('source handle definition and DO goal verified', 'get_body_com("drawer_link")' in env_text and '[0.0, -0.16, 0.0]' in env_text and '-0.16 - self.maxDist' in env_text)
        xml=ET.parse(SITE/'metaworld/assets/objects/assets/drawer.xml')
        joint=xml.find(".//joint[@name='goal_slidey']")
        check('DO manipulation joint is +world-Y slide; opening reduces q',joint is not None and joint.attrib['type']=='slide' and joint.attrib['axis']=='0 1 0')
        s_goal=-1
        feature=inputs.json(CAMPAIGN/'evaluation_cases/feature_schema_DO.json','DO physical feature timing/coordinates')
        check('DO schema joint and control dt',feature['joint_name']=='goal_slidey' and feature['qpos_address']==9 and feature['control_dt']==.0125)
        inputs.json(CAMPAIGN/'schema/transition_schema.json','raw/policy/action/timeout and transition schema')
        evaluation=inputs.json(CAMPAIGN/'evaluation_cases/manifest.json','original 64-case physical panel; no evaluation labels used for archive')
        eval_cases=evaluation['cases']
        check('evaluation case count and physical uniqueness',len(eval_cases)==64 and len({r['physical_case_id'] for r in eval_cases})==64)
        # The recorded reset observation supplies x0's handle point. q0 is derived
        # from its Y coordinate using the fixed static slide kinematics, never x1.
        # Cross-check the derivation against recorded reset qpos in the DO bank.
        q0_errors=[]
        for c in eval_cases:
            if c['task_id']=='DO':
                state=c['initial_state']; q0=float(state['observation'][5]-state['goal'][1]-.19)
                q0_errors.append(abs(q0-state['qpos'][9]))
        check('reset q0 kinematic derivation checked against recorded eval x0 qpos',max(q0_errors)<=protocol['numeric_mapping_atol_float64'],detail=str(max(q0_errors)))
        states=[]
        for run in RUNS:
            full=CAMPAIGN/'runs'/run/'checkpoints/full/1000000'
            m=inputs.json(full/'checkpoint_manifest.json','1M full learner/replay/collector/RNG manifest')
            complete=inputs.json(full/'COMPLETE.json','original full checkpoint atomic completion marker')
            inputs.json(CAMPAIGN/'runs'/run/'COMPLETE.json','original run completion and task counters')
            check('parent full boundary counters',m['step']==1000000 and m['updates']==999000 and m['replay_size']==100000 and m['replay_pos']==0,run)
            check('parent full contains original model replay collector RNG',set(m['files'])=={'model.zip','replay.pkl','collector_and_rng.pkl'} and complete['environment_active'] is False,run)
            for name,digest in m['files'].items():inputs.ref(full/name,'original full payload, hash only, no deserialization',expected=digest)
            for relative,digest in m['source_hashes'].items():
                p=CAMPAIGN/'runs'/run/'source_snapshot'/relative
                inputs.ref(p,'exact source snapshot that generated full checkpoint',expected=digest)
            states.append(dict(parent_id=run,path=str(full),step=m['step'],updates=m['updates'],replay_size=m['replay_size'],replay_pos=m['replay_pos'],
                files=m['files'],state_fingerprints=m['state_fingerprints'],runtime_restore_status='not_run_before_readiness',field_completeness_status='format and source inspected; payloads hash-verified, not deserialized'))
        save(out/'state_manifest.json',states)
        source_rows=[]; candidates=[]; windows=[]; selected_arrays={}; trajectory_cache={}; mapping=[]
        positive_counts=[]
        for run in RUNS:
            base=CAMPAIGN/'runs'/run
            feature_run=inputs.json(base/'schema/env_feature_DO.json','training DO physical schema')
            check('train evaluation physical schema identical',feature_run==feature,run)
            eps=inputs.parts(base/'episodes','all original training episode summaries')
            check('episode IDs unique',not eps.episode_id.duplicated().any(),run)
            donor=eps[eps.task_id=='DO'].sort_values('episode_id')
            check('original DO population 500 complete episodes',len(donor)==500 and donor.episode_complete.all(),run)
            positive_counts.append(int(donor.success_any.sum()))
            for e in donor.itertuples(index=False):
                row=dict(donor_run=run,episode_id=int(e.episode_id),permanent_episode_id=f'{run}:train:{int(e.episode_id):06d}',
                    split_role=e.split_role,task_id=e.task_id,start_train_step=int(e.start_env_step),end_train_step=int(e.end_env_step),
                    episode_length=int(e.episode_length),success_any=int(e.success_any),episode_complete=bool(e.episode_complete),
                    trajectory_ref=str(resolve(e.trajectory_ref)),initial_state_hash=e.initial_state_hash)
                source_rows.append(row)
                if not bool(e.success_any): continue
                path=resolve(e.trajectory_ref); side=inputs.json(path.with_suffix('.json'),'DO successful training sidecar')
                inputs.ref(path,'DO successful complete original NPZ',expected=side['trajectory']['sha256'])
                z=inputs.npz(path,'DO success raw trans/state arrays for offline detector and archive mapping')
                L=len(z['episode_step']); key=row['permanent_episode_id']; trajectory_cache[key]=z
                check('positive trajectory identity and original training source',side['run_id']==run and side['episode_id']==e.episode_id and side['split_role']=='train' and side['task_id']=='DO',key)
                check('positive episode counters permanent IDs steps consecutive',L==500 and np.array_equal(z['episode_step'],np.arange(1,L+1)) and np.array_equal(z['env_step_total'],np.arange(e.start_env_step+1,e.end_env_step+1)) and np.array_equal(z['transition_id'],int(run[1:])*10000000+z['env_step_total']),key)
                check('positive episode source raw and summary labels agree',bool(z['success_step'].any()) and bool(np.isin(z['success_step'],[0,1]).all()) and int(z['success_step'].sum())==e.success_step_count,key)
                check('episode pre/post continuity exact',np.array_equal(z['next_obs_actual'][:-1],z['obs_policy'][1:]) and np.array_equal(z['next_obs_raw_actual'][:-1],z['obs_raw'][1:]),key)
                check('original policy observation and DO encoding preserved',np.array_equal(z['obs_policy'][:,:39],z['obs_raw'].astype(np.float32)) and np.array_equal(z['next_obs_actual'][:,:39],z['next_obs_raw_actual'].astype(np.float32)) and np.all(z['obs_policy'][:,-4:]==[1,0,0,0]) and np.all(z['next_obs_actual'][:,-4:]==[1,0,0,0]),key)
                check('original action and timeout mapping',z['action_executed'].shape==(L,4) and np.isfinite(z['action_executed']).all() and np.all(np.abs(z['action_executed'])<=1) and not z['terminated'].any() and np.array_equal(z['truncated'],np.arange(L)==L-1) and np.all(z['bootstrap_mask']==1),key)
                atol=protocol['numeric_mapping_atol_float64']
                h=z['object_pos']; g=z['goal']; q=z['joint_position']
                check('source object goal and joint columns align with raw samples',np.allclose(h,z['next_obs_raw_actual'][:,4:7],atol=atol,rtol=0) and np.allclose(g,z['next_obs_raw_actual'][:,-3:],atol=atol,rtol=0) and np.array_equal(q,z['qpos'][:,9]) and np.array_equal(g,np.repeat(g[:1],L,axis=0)),key)
                check('success geometry agrees with source',np.array_equal(z['success_step'],(np.linalg.norm(h-g,axis=1)<=.03).astype(int)),key)
                h0=z['obs_raw'][0,4:7].copy(); g0=z['obs_raw'][0,-3:].copy()
                q0=float(h0[1]-g0[1]-.19)
                all_h=np.vstack((h0,h)); all_q=np.r_[q0,q]
                d=np.linalg.norm(all_h-g0,axis=1)
                sigma=int(np.flatnonzero(z['success_step'])[0]+1)
                result=detect(d,all_q,sigma,s_goal=s_goal)
                reasons=list(result['reasons'])
                if e.end_env_step>1000000: reasons.append('after_cutoff')
                if not e.episode_complete or not np.all(z['validity_status']==1): reasons.append('corrupt_or_missing')
                result['reasons']=reasons; result['eligible']=not reasons
                c={**row,**result, 'primary_exclusion':next((x for x in protocol['exclusion_priority'] if x in reasons),None),
                    'exclusion_reasons':'|'.join(reasons),'q0':q0,'q0_status':'derived_from_saved_x0_handle_y_and_fixed_slide_XML_not_x1',
                    'd0':float(d[0]),'h0':h0.tolist(),'goal':g0.tolist(),'s_goal':s_goal,
                    'control_dt':feature['control_dt'],'window_seconds':32*feature['control_dt'],
                    'tau_seconds':result['tau']*feature['control_dt'] if result['tau'] is not None else None,
                    'video_available':e.video_ref is not None,'video_ref':e.video_ref,
                    'stored_reset_handle_x_minus_goal_x':float(h0[0]-g0[0])}
                candidates.append(c)
                mapping.append(dict(donor_run=run,episode_id=int(e.episode_id),q0=q0,d0=d[0],
                    reset_handle_goal_x_gap_m=h0[0]-g0[0],first_endpoint_handle_goal_x_gap_m=h[0,0]-g0[0],
                    max_h_y_vs_kinematic_q_residual_m=float(np.max(np.abs((h[:,1]-g[:,1]-.19)-q))),
                    max_signed_handle_displacement_m=float(-(h[:,1]-h[0,1]).min()),
                    joint_qpos_address_exact=True,raw_post_handle_exact=True))
                if result['eligible']:
                    j,seed=random_pre_start(protocol['user_design'],run,key,sigma)
                    bounds={'ONSET':(result['P_start'],result['P_end']),'RANDOM_PRE':(j,j+31)}
                    overlap=max(0,min(bounds['ONSET'][1],bounds['RANDOM_PRE'][1])-max(bounds['ONSET'][0],bounds['RANDOM_PRE'][0])+1)
                    for arm,(first,last) in bounds.items():
                        idx=np.arange(first-1,last,dtype=np.int64)
                        check('selected window exactly 32 pre-success original transitions',len(idx)==32 and first>=1 and last<sigma and len(np.unique(z['transition_id'][idx]))==32,key+'/'+arm)
                        winid=f'{key}:{arm}:{first:03d}-{last:03d}'
                        windows.append(dict(donor_run=run,episode_id=int(e.episode_id),permanent_episode_id=key,arm=arm,archive_window_id=winid,
                            start=first,end=last,length=32,tau=result['tau'],sigma=sigma,random_pre_seed=str(seed),overlap_transitions=overlap,
                            overlap_fraction=overlap/32,mean_reward=float(z['reward'][idx].mean()),
                            min_goal_distance=float(d[idx+1].min()),mean_goal_distance=float(d[idx+1].mean()),
                            mean_joint=float(q[idx].mean()),related_endpoint_contact_steps=int((z['robot_object_contact_pairs'][idx]>0).sum()),
                            first_transition_id=int(z['transition_id'][idx[0]]),last_transition_id=int(z['transition_id'][idx[-1]]),
                            trajectory_ref=str(path),source_sha256=side['trajectory']['sha256']))
                        for name in ('transition_id','obs_policy','action_executed','reward','next_obs_actual','terminated','truncated','bootstrap_mask'):
                            selected_arrays[f'{len(windows)-1:03d}_{name}']=z[name][idx].copy()
            print(json.dumps(dict(stage='detector',donor_run=run,successes=int(donor.success_any.sum()),eligible=sum(r['eligible'] for r in candidates if r['donor_run']==run))),flush=True)
        check('reported success count independently agrees with raw positives',positive_counts==[2,5,6,9,9],detail=str(positive_counts))
        pd.DataFrame(source_rows).to_parquet(out/'source_DO_training_episodes.parquet',index=False)
        pd.DataFrame([r for r in source_rows if r['success_any']]).to_parquet(out/'source_success_episodes.parquet',index=False)
        cand=pd.DataFrame(candidates); cand.to_parquet(out/'onset_candidates_and_exclusions.parquet',index=False)
        pd.DataFrame(mapping).to_csv(out/'physical_mapping_checks.csv',index=False)
        window_columns=['donor_run','episode_id','permanent_episode_id','arm','archive_window_id','start','end','length','tau','sigma','random_pre_seed','overlap_transitions','overlap_fraction','mean_reward','min_goal_distance','mean_goal_distance','mean_joint','related_endpoint_contact_steps','first_transition_id','last_transition_id','trajectory_ref','source_sha256']
        wins=pd.DataFrame(windows,columns=window_columns);wins.to_parquet(out/'archive_windows.parquet',index=False)
        if selected_arrays:
            with (out/'selected_window_arrays.npz').open('xb') as f:np.savez_compressed(f,**selected_arrays)
        summaries=[]; pools={}
        for run in RUNS:
            raw=cand[cand.donor_run!=run]; eligible=raw[raw.eligible]
            donors=eligible.groupby('donor_run').size().to_dict()
            selected=wins[wins.permanent_episode_id.isin(eligible.permanent_episode_id)]
            p=selected[selected.arm=='ONSET'];u=selected[selected.arm=='RANDOM_PRE']
            same_episode=set(p.permanent_episode_id)==set(u.permanent_episode_id)==set(eligible.permanent_episode_id)
            all_identical=bool(len(p)>0 and (p.overlap_transitions==32).all())
            enough=len(eligible)>=8; spread=sum(int(n)>=2 for n in donors.values())>=2
            supports_ok=bool(enough and spread and same_episode and not all_identical)
            row=dict(parent_id=run,raw_LOO_successes=len(raw),eligible_episodes=len(eligible),minimum_required=8,
                episode_shortfall=max(0,8-len(eligible)),donor_runs_with_at_least_two=sum(int(n)>=2 for n in donors.values()),
                donor_requirement=2,same_episode_P_U=same_episode,all_windows_identical=all_identical,
                transitions_per_arm=32*len(eligible),mean_P_U_overlap_fraction=float(p.overlap_fraction.mean()) if len(p) else None,
                archive_support_ready=supports_ok,full_payload_hashes_verified=True,runtime_full_and_case_restore_certified=False,
                ready_for_runtime_checks=supports_ok)
            summaries.append(row); pools[run]=dict(**row,donor_counts={r:int(donors.get(r,0)) for r in RUNS if r!=run},
                permanent_episode_ids=eligible.permanent_episode_id.tolist(),
                window_ids=selected.archive_window_id.tolist(),runtime_status='not_started_before_all_receivers_support_pass')
        readiness=pd.DataFrame(summaries); readiness.to_csv(out/'readiness_by_receiver.csv',index=False)
        save(out/'loo_archive_manifest.json',pools)
        counts=cand.groupby('donor_run').agg(successful_episodes=('episode_id','size'),eligible_episodes=('eligible','sum')).reindex(RUNS).reset_index()
        counts.to_csv(out/'eligibility_by_donor.csv',index=False)
        exclusions=cand[cand.primary_exclusion.notna()].groupby('primary_exclusion').size().rename('episodes').reset_index()
        exclusions.to_csv(out/'primary_exclusion_counts.csv',index=False)
        allreason=pd.DataFrame([dict(donor_run=r['donor_run'],episode_id=r['episode_id'],reason=reason) for r in candidates for reason in r['reasons']],columns=['donor_run','episode_id','reason'])
        allreason.to_csv(out/'all_exclusion_reasons.csv',index=False)
        # Seed identities and execution order are frozen even if support fails. No
        # seed creates a model or an environment, and no jobs are auto-queued here.
        seed_rows=[];plan=[]
        for run in RUNS:
            for future,root_seed in protocol['futures'].items():
                streams={s:derived_seed(protocol['user_design'],root_seed,run,s) for s in protocol['sampling_streams']}
                seed_rows.append(dict(parent_id=run,future_id=future,root_seed=root_seed,streams={k:str(v) for k,v in streams.items()}))
                for arm in protocol['arms']:
                    plan.append(dict(parent_id=run,future_id=future,arm=arm,cell_id=f'{run}_{future}_{arm}',additional_train_transitions=64000,status='not_started'))
        order=np.random.Generator(np.random.PCG64(53001)).permutation(len(plan))
        for i,ix in enumerate(order):plan[ix]['execution_order']=i+1
        pd.DataFrame(plan).sort_values('execution_order').to_csv(out/'execution_plan.csv',index=False)
        save(out/'seed_manifest.json',dict(algorithm='SHA256 first 64 bits little-endian then explicit NumPy PCG64; decimal strings preserve uint64',
            random_pre=41031,order=53001,bootstrap=54001,parent_future_streams=seed_rows))
        all_ready=bool(readiness.archive_support_ready.all())
        save(out/'readiness.json',dict(archive_support_all_receivers=all_ready,ready_for_runtime_checks=all_ready,
            research_execution_permitted_after_additional_runtime_checks=False,
            runtime_gate_status='pending' if all_ready else 'not_applicable_support_failed',
            raw_successes=positive_counts,eligible_by_donor=counts.eligible_episodes.astype(int).tolist(),
            receivers=pools,zero_execution=ZERO_EXECUTION))
        save(out/'technical_checks.json',dict(file_checks_complete=True,runtime_checks='pending' if all_ready else 'not_run_readiness_failed',checks=checks,new_execution=ZERO_EXECUTION))
        pd.DataFrame(checks).to_csv(out/'verification_checks.csv',index=False)
        save(out/'FINAL_STATUS.json',dict(design_version=protocol['design_version'],stage='preparation',
            status='ready_for_runtime_checks' if all_ready else 'readiness_failed_no_research_started',readiness=all_ready,
            completed_parents=0,completed_branches=0,planned_branches=30,completed_evaluations=0,
            operational_signal_status='unmeasured',new_execution=ZERO_EXECUTION,budget_remaining=4970000,output_paths=dict(preparation=str(out))))
        print(json.dumps(clean(dict(output=out,readiness=all_ready,donors=counts.to_dict('records'),receivers=summaries,exclusions=exclusions.to_dict('records'))),ensure_ascii=False),flush=True)
        save(HERE/'LATEST_PREPARATION.json',dict(output=out,status='ready_for_runtime_checks' if all_ready else 'readiness_failed'),replace=True)
    except BaseException as ex:
        save(out/'FAILED.json',dict(error=repr(ex),new_execution=ZERO_EXECUTION,at=utc()))
        pd.DataFrame(checks).to_csv(out/'verification_checks.csv',index=False)
        print(json.dumps(dict(output=str(out),error=repr(ex))),flush=True)
        raise
    finally:
        inputs.flush(out)
        proc=psutil.Process()
        save(out/'preparation_costs.json',dict(wall_seconds=time.perf_counter()-started,cpu=proc.cpu_times()._asdict(),memory=proc.memory_info()._asdict(),
            process_io=proc.io_counters()._asdict(),tracked_read_bytes=inputs.bytes_read,
            new_execution=ZERO_EXECUTION,original_campaign_cost_separate=6604850))

if __name__=='__main__': main()
