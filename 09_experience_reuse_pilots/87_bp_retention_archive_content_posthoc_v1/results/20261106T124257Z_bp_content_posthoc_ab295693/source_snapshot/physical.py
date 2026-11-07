"""Saved BP trajectories and frozen DO window contents; no simulator/model calls."""
from __future__ import annotations
import numpy as np
import pandas as pd
from common import *


def related_contacts(z,schema):
    contacts=z['contacts'];offsets=z['contact_offsets'];L=len(z['episode_step'])
    body=np.asarray(schema['geom_bodyid']);names=schema['body_names'];geom=schema['geom_names']
    robot={names.index(s) for s in ['hand','rightclaw','leftclaw','rightpad','leftpad']};obj=names.index(schema['object_body'])
    if len(contacts)==0:return np.zeros(L,dtype=int),[]
    a=contacts[:,0].astype(int);b=contacts[:,1].astype(int);ba=body[a];bb=body[b]
    mask=(np.isin(ba,list(robot))&(bb==obj))|((ba==obj)&np.isin(bb,list(robot)))
    steps=np.repeat(np.arange(1,L+1),np.diff(offsets));counts=np.bincount(steps[mask]-1,minlength=L)
    rows=[]
    for pair in np.unique(np.sort(np.c_[a[mask],b[mask]],axis=1),axis=0):
        k=mask&(((a==pair[0])&(b==pair[1]))|((b==pair[0])&(a==pair[1])))
        rows.append(dict(geom_a=int(pair[0]),geom_b=int(pair[1]),
            geom_a_name=geom[pair[0]] or 'unnamed_geom#'+str(pair[0]),geom_b_name=geom[pair[1]] or 'unnamed_geom#'+str(pair[1]),
            body_a=names[body[pair[0]]],body_b=names[body[pair[1]]],endpoint_contact_pair_samples=int(k.sum()),
            endpoint_steps_with_pair=int(np.unique(steps[k]).size),first_control_step=int(steps[k].min()),last_control_step=int(steps[k].max()),
            minimum_signed_contact_distance_m=float(contacts[k,2].min())))
    return counts,rows


def bp_metrics(z,q0,h0,config):
    b=z['success_step'];L=len(b);hits=np.flatnonzero(b);tau=int(hits[0]+1) if len(hits) else None
    err=np.abs(z['object_pos'][:,1]-z['goal'][:,1]);q=z['joint_position'];pressed=-(q-q0)
    dp=np.diff(np.r_[0.,pressed]);a=z['action_executed'].astype(float);tcp=z['tcp'];obj=z['object_pos'];dist=z['tcp_object_distance']
    delta_a=np.diff(a,axis=0);move=np.linalg.norm(a[:,:3],axis=1);contact=z['robot_object_contact_pairs']>0
    relative=tcp-obj
    r=dict(success_any=int(b.any()),episode_end_success=int(b[-1]),episode_return=float(z['reward'].sum()),first_success_step=tau,
        success_occupancy=float(b.mean()),minimum_button_axis_error_m=float(err.min()),final_button_axis_error_m=float(err[-1]),
        minimum_TCP_button_distance_m=float(dist.min()),mean_TCP_button_distance_m=float(dist.mean()),
        button_joint_min_m=float(q.min()),button_joint_max_m=float(q.max()),maximum_press_from_reset_m=float(pressed.max()),
        final_press_from_reset_m=float(pressed[-1]),positive_press_path_m=float(np.maximum(dp,0).sum()),return_press_path_m=float(np.maximum(-dp,0).sum()),
        actual_TCP_path_post1_to500_m=float(np.linalg.norm(np.diff(tcp,axis=0),axis=1).sum()),
        actual_button_path_reset_to500_m=float(np.linalg.norm(np.diff(np.vstack([h0,obj]),axis=0),axis=1).sum()),
        contact_endpoint_fraction=float(contact.mean()),contact_endpoint_samples=int(contact.sum()),
        first_related_contact_step=int(np.flatnonzero(contact)[0]+1) if contact.any() else None,
        mean_gripper_width_m=float(z['gripper_width'].mean()),move_command_norm_mean=float(move.mean()),
        move_command_change_mean=float(np.linalg.norm(delta_a[:,:3],axis=1).mean()),gripper_command_change_mean=float(np.abs(delta_a[:,3]).mean()),
        post_hit_observations=L-tau+1 if tau is not None else None,
        post_hit_success_occupancy=float(b[tau-1:].mean()) if tau is not None else None,
        reward_before_hit=float(z['reward'][:tau-1].sum()) if tau is not None else None,
        reward_hit=float(z['reward'][tau-1]) if tau is not None else None,
        reward_after_hit=float(z['reward'][tau:].sum()) if tau is not None else None,
        source_near_object_fraction=float(z['info_near_object'].mean()))
    for i,k in enumerate(['x','y','z']):
        r['action_'+k+'_mean']=float(a[:,i].mean());r['action_'+k+'_saturation_fraction']=float((np.abs(a[:,i])>=config['action_saturation_absolute']).mean())
        r['TCP_minus_button_'+k+'_mean_m']=float(relative[:,i].mean())
        r['actual_TCP_'+k+'_net_post1_to500_m']=float(tcp[-1,i]-tcp[0,i])
    r['gripper_command_mean']=float(a[:,3].mean());r['gripper_command_saturation_fraction']=float((np.abs(a[:,3])>=config['action_saturation_absolute']).mean())
    return r


def run(out,inputs,checks,hist):
    config=load(out/'analysis_config.json')
    schema_bp=inputs.json(ORIGINAL/'evaluation_cases/feature_schema_BP.json','fixed BP physical coordinates and contact identity')
    schema_do=inputs.json(ORIGINAL/'evaluation_cases/feature_schema_DO.json','fixed DO physical coordinates and contact identity')
    cases=inputs.json(ORIGINAL/'evaluation_cases/manifest.json','outcome-blind original physical case identities')['cases']
    case_map={r['initial_case_id']:r for r in cases}
    source_audit=CAMPAIGN/'verification/20261106T044100Z_assets_1c230ae0/input_manifest.jsonl'
    rows=[json.loads(s) for s in inputs.text(source_audit,'prior pinned source hashes').splitlines()]
    expected={r['path']:r['sha256'] for r in rows}
    source_names=['metaworld/envs/sawyer_button_press_v3.py','metaworld/envs/sawyer_drawer_open_v3.py','metaworld/assets/objects/assets/buttonbox.xml']
    for name in source_names:
        p=SITE/name;text=inputs.text(p,'fixed source/XML text; not imported',expected[str(p)])
        dst=out/'pinned_source_text'/Path(name).name;dst.parent.mkdir(exist_ok=True);dst.write_text(text,encoding='utf-8')
    metrics=[];bins=[];contacts=[]
    bp=hist['episodes'][hist['episodes'].task_id=='BP']
    checks.add('all BP1520 actual evaluation episodes',len(bp)==1520)
    fields=['episode_step','success_step','reward','action_executed','tcp','object_pos','goal','joint_position','joint_velocity',
        'tcp_object_distance','gripper_width','robot_object_contact_pairs','info_obj_to_target','info_near_object','contact_offsets','contacts','obs_raw','policy_version']
    for ix,r in enumerate(bp.to_dict('records')):
        z=inputs.arrays(r['trajectory_ref'],'BP actual numeric trajectory',fields,r['source_trajectory_sha256'])
        case=case_map[r['initial_case_id']];q0=float(case['initial_state']['qpos'][9]);h0=np.asarray(case['initial_state']['observation'][4:7])
        checks.add('BP complete500 steps and one policy '+r['trajectory_ref'],len(z['episode_step'])==500 and np.array_equal(z['episode_step'],np.arange(1,501)) and np.unique(z['policy_version']).size==1)
        checks.add('BP reset observation and physical identity '+r['trajectory_ref'],np.max(np.abs(z['obs_raw'][0]-np.asarray(case['initial_state']['observation'])))<=1e-8 and case['physical_case_id']==r['physical_case_id'])
        err=np.abs(z['object_pos'][:,1]-z['goal'][:,1]);counts,pairs=related_contacts(z,schema_bp)
        checks.add('BP official axis success rederived '+r['trajectory_ref'],np.array_equal((err<=.02).astype(int),z['success_step']) and np.max(np.abs(err-z['info_obj_to_target']))<=1e-8)
        checks.add('BP slide axis agrees with object displacement '+r['trajectory_ref'],np.max(np.abs(z['object_pos'][:,1]-h0[1]+z['joint_position']-q0))<=1e-8)
        checks.add('BP endpoint contact pairs match source '+r['trajectory_ref'],np.array_equal(counts,z['robot_object_contact_pairs']))
        meta={k:r[k] for k in ['parent_id','future_id','arm','relative_train_step','initial_case_id','physical_case_id','episode_id','trajectory_ref','video_ref','checkpoint_hash']}
        row={**meta,**bp_metrics(z,q0,h0,config)};metrics.append(row)
        checks.add('BP recomputed episode labels and return '+r['trajectory_ref'],row['success_any']==r['success_any'] and abs(row['episode_return']-r['episode_return'])<1e-8)
        for pair in pairs:contacts.append({**meta,**pair})
        for lo,hi in config['BP_time_bins']:
            s=slice(lo-1,hi);a=z['action_executed'][s];tcp=z['tcp'][s];obj=z['object_pos'][s]
            br=dict(**meta,control_start=lo,control_end=hi,minimum_axis_error_m=float(err[s].min()),mean_axis_error_m=float(err[s].mean()),
                mean_TCP_button_distance_m=float(z['tcp_object_distance'][s].mean()),success_fraction=float(z['success_step'][s].mean()),
                mean_joint_m=float(z['joint_position'][s].mean()),minimum_joint_m=float(z['joint_position'][s].min()),
                contact_endpoint_fraction=float((counts[s]>0).mean()),reward_sum=float(z['reward'][s].sum()),gripper_command_mean=float(a[:,3].mean()))
            for j,k in enumerate(['x','y','z']):br['action_'+k+'_mean']=float(a[:,j].mean());br['TCP_minus_button_'+k+'_mean_m']=float((tcp-obj)[:,j].mean())
            bins.append(br)
        if (ix+1)%400==0:print(json.dumps(dict(stage='BP raw trajectories',episodes=ix+1)),flush=True)
    metrics=pd.DataFrame(metrics);metrics.to_parquet(out/'bp_episode_physical_metrics.parquet',index=False)
    pd.DataFrame(bins).to_parquet(out/'bp_fixed_timebin_metrics.parquet',index=False);pd.DataFrame(contacts).to_parquet(out/'bp_contact_pair_summary.parquet',index=False)
    pair_phys=[];numeric=metrics.select_dtypes(include=np.number).columns.tolist()
    numeric=[c for c in numeric if c!='relative_train_step']
    for r in hist['case_pairs'].to_dict('records'):
        for t in TIMES[1:]:
            sub=metrics[(metrics.parent_id==r['parent_id'])&(metrics.future_id==r['future_id'])&(metrics.physical_case_id==r['physical_case_id'])&(metrics.relative_train_step==t)].set_index('arm')
            a=sub.loc[r['method']];b=sub.loc[r['reference']]
            d={**r,'relative_train_step':t,'method_trajectory_ref':a.trajectory_ref,'reference_trajectory_ref':b.trajectory_ref,
                'method_video_ref':a.video_ref,'reference_video_ref':b.video_ref}
            for col in numeric:d['method_'+col]=a[col];d['reference_'+col]=b[col];d['delta_'+col]=a[col]-b[col]
            pair_phys.append(d)
    pair_phys=pd.DataFrame(pair_phys);pair_phys.to_parquet(out/'bp_paired_physical_metrics.parquet',index=False)
    windows=inputs.parquet(PREP/'archive_windows.parquet','fixed50 windows without reselection')
    cand=inputs.parquet(PREP/'onset_candidates_and_exclusions.parquet','frozen eligibility and onset metadata')
    checks.add('fixed25 donor episodes,50 windows',len(windows)==50 and windows.permanent_episode_id.nunique()==25)
    transition_rows=[];window_rows=[];initial_rows=[];donor_contacts=[]
    for episode,part in windows.groupby('permanent_episode_id'):
        r=part.iloc[0];z=inputs.arrays(r.trajectory_ref,'original selected successful DO episode, full context',expected=r.source_sha256)
        goal=z['goal'][0];raw0=z['obs_raw'][0,4:7];q0=float(raw0[1]-goal[1]-.19);h0=goal+np.array([0,.19+q0,0])
        h=np.vstack([h0,z['object_pos']]);q=np.r_[q0,z['joint_position']];p=-q;d=np.linalg.norm(h-goal,axis=1)
        sigma=int(np.flatnonzero(z['success_step'])[0]+1);tau=int(r.tau);counts,pairs=related_contacts(z,schema_do)
        checks.add('DO source first sigma and contact identity '+episode,sigma==r.sigma and np.array_equal(counts,z['robot_object_contact_pairs']))
        checks.add('DO physical slide map all post samples '+episode,np.max(np.abs(h[:,1]-goal[1]-.19-q))<=1e-8 and np.max(np.abs(h[:,0]-goal[0]))<=1e-8)
        initial_rows.append(dict(source_episode_id=episode,donor_run=r.donor_run,q0_derived_m=q0,
            raw_reset_x_m=raw0[0],raw_reset_y_m=raw0[1],raw_reset_z_m=raw0[2],physical_h0_x_m=h0[0],physical_h0_y_m=h0[1],physical_h0_z_m=h0[2],
            first_post_action_x_m=h[1,0],first_post_action_y_m=h[1,1],first_post_action_z_m=h[1,2],initial_physical_goal_distance_m=d[0],initial_raw_observation_goal_distance_m=float(np.linalg.norm(raw0-goal)),
            physical_h0_status='derived exact frozen85 XML/resetY mapping; not x1',raw_training_arrays_modified=False))
        for pair in pairs:donor_contacts.append(dict(source_episode_id=episode,donor_run=r.donor_run,**pair))
        for wi,w in part.iterrows():
            a=int(w.start);e=int(w.end);t=np.arange(a,e+1);idx=t-1;pre=t-1;act=z['action_executed'][idx].astype(float)
            dp=p[t]-p[pre];tcp_pre=z['tcp'][pre-1] if np.all(pre>=1) else None
            checks.add('all fixed window pre-TCP actually observed '+w.archive_window_id,tcp_pre is not None)
            tcp=z['tcp'][idx];dtcp=tcp-tcp_pre;rel_pre=tcp_pre-h[pre];rel_post=tcp-h[t]
            da=act-z['action_executed'][idx-1];post=p[e+1:sigma+1]
            checks.add('exact pre-success32 support '+w.archive_window_id,len(idx)==32 and e<sigma and not z['success_step'][idx].any())
            base=dict(source_episode_id=episode,donor_run=w.donor_run,arm=w.arm,archive_window_id=w.archive_window_id,window_index=int(wi),
                window_start=a,window_end=e,tau=tau,sigma=sigma,trajectory_ref=w.trajectory_ref,source_sha256=w.source_sha256)
            local=[]
            for j,tj in enumerate(t):
                v=dict(**base,window_offset=j,episode_step=int(tj),archive_transition_id=int(z['transition_id'][idx[j]]),
                    goal_distance_pre_m=d[pre[j]],goal_distance_post_m=d[tj],opening_pre_m=p[pre[j]],opening_post_m=p[tj],
                    opening_from_initial_pre_m=p[pre[j]]-p[0],opening_increment_m=dp[j],opening_positive_m=max(dp[j],0),closing_positive_m=max(-dp[j],0),
                    move_command_norm=float(np.linalg.norm(act[j,:3])),gripper_command=act[j,3],goal_axis_command=-act[j,1],
                    actual_TCP_move_m=float(np.linalg.norm(dtcp[j])),actual_TCP_goal_axis_move_m=-dtcp[j,1],
                    action_xyz_change=float(np.linalg.norm(da[j,:3])),gripper_command_change=abs(da[j,3]),
                    reward=float(z['reward'][idx[j]]),contact_pair_samples=int(counts[idx[j]]),contact_endpoint=int(counts[idx[j]]>0),
                    TCP_handle_distance_pre_m=float(np.linalg.norm(rel_pre[j])),TCP_handle_distance_post_m=float(np.linalg.norm(rel_post[j])),
                    gripper_width_post_m=float(z['gripper_width'][idx[j]]),joint_velocity_post_m_per_s=float(z['joint_velocity'][idx[j]]),success_step=int(z['success_step'][idx[j]]))
                for k,axis in enumerate(['x','y','z']):
                    v['action_'+axis]=act[j,k];v['actual_TCP_'+axis+'_move_m']=dtcp[j,k]
                    v['TCP_minus_handle_'+axis+'_pre_m']=rel_pre[j,k];v['TCP_minus_handle_'+axis+'_post_m']=rel_post[j,k]
                    v['action_'+axis+'_saturated']=int(abs(act[j,k])>=config['action_saturation_absolute'])
                v['gripper_command_saturated']=int(abs(act[j,3])>=config['action_saturation_absolute'])
                local.append(v);transition_rows.append(v)
            net=float(p[e]-p[a-1]);positive=float(np.maximum(dp,0).sum());negative=float(np.maximum(-dp,0).sum())
            wr=dict(**base,transitions=32,window_seconds=.4,steps_to_first_success=sigma-e,
                opening_before_m=float(p[a-1]),opening_end_m=float(p[e]),net_opening_m=net,opening_path_m=positive,closing_path_m=negative,
                maximum_opening_in_window_m=float(p[a-1:e+1].max()),mean_goal_distance_pre_m=float(d[pre].mean()),mean_goal_distance_post_m=float(d[t].mean()),
                mean_opening_pre_m=float(p[pre].mean()),mean_move_command_norm=float(np.linalg.norm(act[:,:3],axis=1).mean()),mean_gripper_command=float(act[:,3].mean()),
                mean_goal_axis_command=float((-act[:,1]).mean()),mean_reward=float(z['reward'][idx].mean()),
                contact_endpoint_steps=int((counts[idx]>0).sum()),contact_pair_samples=int(counts[idx].sum()),actual_TCP_path_m=float(np.linalg.norm(dtcp,axis=1).sum()),
                actual_TCP_goal_axis_net_m=float((-dtcp[:,1]).sum()),mean_TCP_handle_pre_m=float(np.linalg.norm(rel_pre,axis=1).mean()),
                mean_TCP_handle_post_m=float(np.linalg.norm(rel_post,axis=1).mean()),mean_gripper_width_m=float(z['gripper_width'][idx].mean()),
                post_window_observations_through_sigma=len(post),post_endpoint_drawdown_m=max(0,float(p[e]-post.min())),
                post_larger_opening_m=float(post.max()-p[e]),post_total_opening_m=float(np.maximum(np.diff(np.r_[p[e],post]),0).sum()),
                post_total_closing_m=float(np.maximum(-np.diff(np.r_[p[e],post]),0).sum()),
                full_endpoint_net_gain_reversal=bool(post.min()<=p[a-1]+config['numerical_motion_atol_m']) if net>config['numerical_motion_atol_m'] else None,
                endpoint_gain_reversal_fraction=max(0,float(p[e]-post.min()))/net if net>config['numerical_motion_atol_m'] else None,
                post_context_is_reused=False)
            for k,axis in enumerate(['x','y','z']):wr['mean_action_'+axis]=float(act[:,k].mean());wr['actual_TCP_'+axis+'_net_m']=float(dtcp[:,k].sum())
            checks.add('DO directional path decomposition '+w.archive_window_id,abs(positive-negative-net)<=1e-8)
            window_rows.append(wr)
    transitions=pd.DataFrame(transition_rows);windows_content=pd.DataFrame(window_rows)
    checks.add('1600 unique selected window transitions',len(transitions)==1600 and not transitions.duplicated(['arm','source_episode_id','window_offset']).any())
    transitions.to_parquet(out/'do_transition_content.parquet',index=False);windows_content.to_parquet(out/'do_window_content.parquet',index=False)
    pd.DataFrame(initial_rows).to_csv(out/'do_initial_coordinate_mapping.csv',index=False);pd.DataFrame(donor_contacts).to_parquet(out/'do_source_contact_pairs.parquet',index=False)
    numeric_cols=windows_content.select_dtypes(include=np.number).columns.tolist()
    a=windows_content[windows_content.arm=='ONSET'].set_index('source_episode_id');b=windows_content[windows_content.arm=='RANDOM_PRE'].set_index('source_episode_id')
    delta=pd.DataFrame(index=a.index)
    for col in numeric_cols:
        if col in b:delta['P_minus_U_'+col]=a[col]-b[col]
    delta['donor_run']=a.donor_run;delta.reset_index().to_csv(out/'do_paired_window_content_differences.csv',index=False)
    print(json.dumps(dict(stage='physical analysis complete',BP_episodes=len(metrics),DO_episodes=25,DO_windows=len(windows_content))),flush=True)
    return dict(metrics=metrics,pair_metrics=pair_phys,windows=windows_content,transitions=transitions,schema_bp=schema_bp,schema_do=schema_do)
