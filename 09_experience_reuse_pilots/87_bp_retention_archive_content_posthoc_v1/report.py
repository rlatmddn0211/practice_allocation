"""Deliver the saved-file87 analyses; neither simulator nor model is imported."""
from __future__ import annotations
import argparse
import shutil
import time
from common import *

guard()
import numpy as np
import pandas as pd

COLORS={'BASE':'#617388','RANDOM_PRE':'#d99027','ONSET':'#7956b5'}
PCOLORS=dict(zip(RUNS,['#176a89','#c28122','#33866a','#b75362','#8056aa']))
SHORT={'BASE':'B','RANDOM_PRE':'U','ONSET':'P'}
TYPES={
 'method_only_final_success':'P만 최종 성공',
 'reference_only_final_success':'대조만 최종 성공',
 'both_final_success_different_history':'둘 다 최종 성공·중간 이력 다름',
 'identical_four_time_history':'네 시점 이력 동일',
 'both_final_failure_different_history':'둘 다 최종 실패·중간 이력 다름'}


def table(frame,rename=None,scale=None,digits=3):
    f=frame.copy()
    for c,s in (scale or {}).items():f[c]*=s
    if rename:f=f.rename(columns=rename)
    return md(f,digits)


class Delivery:
    def __init__(self,core):
        self.start=time.perf_counter();self.core=Path(core).resolve();self.inputs=Inputs();self.checks=Checks()
        self.out=HERE/'delivery'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_delivery_'+uuid.uuid4().hex[:8])
        self.out.mkdir(parents=True,exist_ok=False);(self.out/'tables').mkdir();(self.out/'code').mkdir()
        self.started=utc();self.figures=[]
        self.verification=self.inputs.json(self.core/'LATEST_VERIFICATION.json','independent verification pointer')
        self.checks.add('independent scalar verification passed',self.verification['status']=='passed')
        vp=Path(self.verification['output'])
        self.ver_status=self.inputs.json(vp/'FINAL_STATUS.json','independent verification result')
        self.checks.add('independent verification is passed',self.ver_status['status']=='passed')
        for p in HERE.iterdir():
            if p.is_file() and p.suffix in {'.py','.json','.md'} and not p.name.startswith('LATEST'):
                shutil.copy2(p,self.out/'code'/p.name)
        save(self.out/'source_hashes.json',{str(p.relative_to(self.out)):sha(p) for p in sorted((self.out/'code').iterdir())})
        (self.out/'provenance').mkdir()
        for p in self.core.iterdir():
            if p.is_file() and p.suffix in {'.csv','.parquet'}:
                shutil.copy2(self.inputs.ref(p,'core derived table; preserved copy'),self.out/'tables'/p.name)
        for name in ['input_manifest.jsonl','analysis_costs.json','source_hashes.json','analysis_config.json','FINAL_STATUS.json']:
            shutil.copy2(self.inputs.ref(self.core/name,'core extraction provenance'),self.out/'provenance'/('core_'+name))
        shutil.copytree(self.core/'source_snapshot',self.out/'provenance/core_source_snapshot')
        shutil.copytree(self.core/'pinned_source_text',self.out/'provenance/pinned_source_text')
        shutil.copytree(vp,self.out/'verification/independent')
        self.data={}

    def read(self,name):
        if name not in self.data:
            self.data[name]=self.inputs.parquet(self.core/name,'delivery derived input') if name.endswith('.parquet') else self.inputs.csv(self.core/name,'delivery derived input')
        return self.data[name]

    def setup_plot(self):
        os.environ['MPLCONFIGDIR']=str(self.out/'.mplconfig')
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        self.plt=plt
        plt.rcParams.update({'font.family':'Malgun Gothic','axes.unicode_minus':False,
            'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none',
            'savefig.dpi':160,'figure.facecolor':'white','axes.facecolor':'white'})
        (self.out/'figures').mkdir()

    def figure(self,fig,name,caption):
        for ext in ['png','svg']:fig.savefig(self.out/'figures'/(name+'.'+ext),bbox_inches='tight')
        self.plt.close(fig);self.figures.append(dict(id=name,caption=caption,png='figures/'+name+'.png',svg='figures/'+name+'.svg'))

    def derived_tables(self):
        h=self.read('bp_arm_histories.parquet');arm=self.read('bp_arm_parent_future.csv')
        pair=self.read('bp_paired_effects_parent_future.csv');parent=self.read('bp_parent_effects.csv')
        window=self.read('do_window_content.parquet');cum=self.read('actual_cumulative_exposure_features.csv')
        interval=self.read('actual_interval_exposure_features.csv');case=self.read('bp_case_contrasts.parquet')
        risk=[]
        for a in ARMS:
            g=h[h.arm==a];b=g[g.initial_success==1];f=g[g.initial_success==0]
            risk.append(dict(arm=a,initial_success_histories=len(b),all_four_success=int((b.pattern.astype(str)=='1111').sum()),
                loss_then_final_recovery=int((b.history_category=='observed_loss_then_final_recovery').sum()),
                final_loss=int((1-b.final_success).sum()),initial_failure_histories=len(f),
                initial_failure_final_success=int(f.final_success.sum()),initial_failure_acquired_final_failed=int(((f.gain_events>0)&(f.final_success==0)).sum()),
                never_observed_success=int((f.gain_events==0).sum()),gain_events=int(g.gain_events.sum()),loss_events=int(g.loss_events.sum()),recovery_events=int(g.recovery_events.sum())))
        self.risk=pd.DataFrame(risk);self.risk.to_csv(self.out/'tables/bp_fixed_initial_risk_summary.csv',index=False)
        acq=self.read('bp_first_acquisition_opportunities.csv').copy()
        for c in ['histories_with_later_loss']:
            acq[c]=acq[c].replace({'False':0,'True':1,False:0,True:1}).astype(int)
        self.acq=acq;acq.to_csv(self.out/'tables/bp_first_acquisition_opportunities_normalized.csv',index=False)
        rows=[]
        for (p,f),g in arm.groupby(['parent_id','future_id']):
            r=dict(parent_id=p,future_id=f,initial_success=int(g.initial_successes.iloc[0]))
            for a in ARMS:
                q=g[g.arm==a].iloc[0]
                r[SHORT[a]+'_final_successes']=int(q.final_successes)
                for t in [16000,32000,64000]:r[SHORT[a]+'_change_from_start_'+str(t)+'_pp']=100*q['delta_from_start_'+str(t)]
            for contrast in ['P-U','P-B','U-B']:
                q=pair[(pair.parent_id==p)&(pair.future_id==f)&(pair.contrast==contrast)].iloc[0]
                for k in ['delta_auc','final_delta_J','avoided_initial_loss','delta_initial_failure_final_gain','delta_J_16000','delta_J_32000']:
                    r[contrast+'_'+k+'_pp']=100*q[k]
            rows.append(r)
        self.ten=pd.DataFrame(rows);self.ten.to_csv(self.out/'tables/bp_ten_matched_runs_summary.csv',index=False)
        self.parent_summary=parent.pivot(index='parent_id',columns='contrast',values='delta_auc').reindex(RUNS).reset_index()
        self.parent_summary.to_csv(self.out/'tables/bp_parent_auc_summary.csv',index=False)
        means=window.groupby('arm').agg(episodes=('source_episode_id','size'),net_opening_m=('net_opening_m','mean'),opening_path_m=('opening_path_m','mean'),
            closing_path_m=('closing_path_m','mean'),mean_goal_distance_pre_m=('mean_goal_distance_pre_m','mean'),mean_goal_axis_command=('mean_goal_axis_command','mean'),
            mean_gripper_command=('mean_gripper_command','mean'),mean_TCP_handle_pre_m=('mean_TCP_handle_pre_m','mean'),
            mean_reward=('mean_reward','mean'),contact_endpoint_steps=('contact_endpoint_steps','mean'),
            window_start_median=('window_start','median'),steps_to_first_success_median=('steps_to_first_success','median'),
            post_endpoint_drawdown_m=('post_endpoint_drawdown_m','mean'),post_larger_opening_m=('post_larger_opening_m','mean')).reset_index()
        self.window_means=means;means.to_csv(self.out/'tables/do_all25_window_content_summary.csv',index=False)
        source=window[window.arm=='ONSET'].copy()
        source['positive_net_window']=source.net_opening_m>1e-8
        source['full_gain_reversal']=source.full_endpoint_net_gain_reversal.map(lambda v:bool(v) if pd.notna(v) else False)
        self.source_summary=source.groupby('donor_run').agg(eligible_episodes=('source_episode_id','size'),positive_net_windows=('positive_net_window','sum'),
            full_gain_reversal_before_sigma=('full_gain_reversal','sum'),mean_net_opening_m=('net_opening_m','mean'),mean_post_drawdown_m=('post_endpoint_drawdown_m','mean')).reset_index()
        self.source_summary.to_csv(self.out/'tables/do_donor_context_summary.csv',index=False)
        self.weights=cum[cum.interval_end==64000].groupby('arm').mean(numeric_only=True).reset_index()
        self.weights.to_csv(self.out/'tables/actual_final_exposure_summary_equal_parent_future.csv',index=False)
        self.uses=interval.groupby(['arm','interval_start','interval_end']).agg(total_uses=('actual_uses','sum'),mean_uses_per_update=('uses_per_actor_update','mean'),
            mean_repeat_draw_fraction=('repeat_draw_fraction','mean'),minimum_unique_episodes=('unique_episodes','min'),maximum_unique_episodes=('unique_episodes','max')).reset_index()
        self.uses.to_csv(self.out/'tables/actual_use_interval_summary.csv',index=False)
        l=self.read('exposure_BP_effect_linkage.parquet')
        self.link_parent=l[(l.contrast=='P-U')&(l.interval_end==64000)].groupby('parent_id').mean(numeric_only=True).reindex(RUNS).reset_index()
        fields=['parent_id','BP_delta_AUC0_to_end','BP_delta_J_end','cumulative_delta_opening_positive_m','cumulative_delta_closing_positive_m',
            'cumulative_delta_goal_distance_pre_m','cumulative_delta_goal_axis_command','cumulative_delta_gripper_command','cumulative_delta_contact_endpoint',
            'DO_delta_J_end','PU_delta_J_end','DC_delta_J_end']
        self.link_parent[fields].to_csv(self.out/'tables/content_BP_linkage_parent_summary.csv',index=False)
        task=self.inputs.csv(ANALYSIS/'task_tradeoffs.csv','original85 all-task outcomes; no new uncertainty calculation')
        task.to_csv(self.out/'tables/original85_task_tradeoffs.csv',index=False);self.tradeoff=task
        selections=[]
        for contrast in ['P-U','P-B']:
            for typ,g in case[case.contrast==contrast].groupby('case_type'):
                r=g.sort_values(['delta_case_auc','parent_id','future_id','initial_case_id']).iloc[len(g)//2].to_dict()
                selections.append({**r,'selection_rule':'upper middle after case-AUC delta and parent/future/case order; all categories retained','selection_is_posthoc':True})
        self.selected=pd.DataFrame(selections);self.selected.to_csv(self.out/'tables/selected_BP_numeric_cases.csv',index=False)
        save(self.out/'case_selection.json',{'rule':load(HERE/'analysis_config.json')['illustrations'],'BP':selections,
            'DO_context_examples':['R02:train:000251','R04:train:000679',str(source.sort_values('source_episode_id').iloc[len(source)//2].source_episode_id)],
            'DO_context_rule':'all25 population first; show every full endpoint-gain reversal and nonpositive-net counterexample, plus ID-middle example',
            'video_availability_changes_selection':False})
        phys=self.read('bp_episode_physical_metrics.parquet');refs=[]
        for r in selections:
            for armname in [r['method'],r['reference']]:
                m=phys[(phys.parent_id==r['parent_id'])&(phys.future_id==r['future_id'])&(phys.arm==armname)&(phys.initial_case_id==r['initial_case_id'])]
                for v in m.to_dict('records'):
                    video=v['video_ref'];avail=isinstance(video,str) and bool(video) and Path(video).is_file()
                    refs.append({k:v[k] for k in ['parent_id','future_id','arm','relative_train_step','initial_case_id','episode_id','trajectory_ref','video_ref']}|dict(
                        contrast=r['contrast'],case_type=r['case_type'],video_available=avail,video_sha256=sha(Path(video)) if avail else None,
                        video_viewed_in87=False,video_generated_in87=False))
        pd.DataFrame(refs).drop_duplicates().to_csv(self.out/'selected_existing_video_and_trajectory_refs.csv',index=False)
        physical=self.read('bp_paired_physical_metrics.parquet');q=physical[(physical.relative_train_step==64000)&physical.contrast.isin(['P-U','P-B'])]
        self.physical_groups=q.groupby(['contrast','case_type']).agg(N=('initial_case_id','size'),
            axis_error_difference_m=('delta_minimum_button_axis_error_m','mean'),TCP_distance_difference_m=('delta_minimum_TCP_button_distance_m','mean'),
            endpoint_contact_fraction_difference=('delta_contact_endpoint_fraction','mean'),
            success_occupancy_difference=('delta_success_occupancy','mean'),final_press_difference_m=('delta_final_press_from_reset_m','mean')).reset_index()
        self.physical_groups.to_csv(self.out/'tables/BP_final_physical_differences_by_case_type.csv',index=False)
        self.final_physical=phys[phys.relative_train_step==64000].groupby('arm').agg(
            episodes=('episode_id','size'),success_any_count=('success_any','sum'),
            conditional_first_success_step_median=('first_success_step','median'),
            success_occupancy_mean=('success_occupancy','mean'),episode_end_success_count=('episode_end_success','sum')).reset_index()
        self.final_physical.to_csv(self.out/'tables/BP_final_all_case_physical_summary.csv',index=False)
        recovery_case=self.selected[(self.selected.contrast=='P-U')&(self.selected.case_type=='both_final_success_different_history')].iloc[0]
        self.recovery_physical=phys[(phys.parent_id==recovery_case.parent_id)&(phys.future_id==recovery_case.future_id)&
            (phys.initial_case_id==recovery_case.initial_case_id)&phys.arm.isin([recovery_case.method,recovery_case.reference])&
            (phys.relative_train_step>0)][['parent_id','future_id','initial_case_id','arm','relative_train_step','success_any','first_success_step',
                'minimum_button_axis_error_m','minimum_TCP_button_distance_m','contact_endpoint_samples','success_occupancy','episode_end_success']]
        self.recovery_physical.to_csv(self.out/'tables/BP_selected_recovery_physical_summary.csv',index=False)
        self.checks.add('148/12 shared initial risk histories',bool((self.risk.initial_success_histories==148).all() and (self.risk.initial_failure_histories==12).all()))
        self.checks.add('case groups preserve both directions',int(((case.contrast=='P-U')&(case.case_type=='method_only_final_success')).sum())==16 and int(((case.contrast=='P-U')&(case.case_type=='reference_only_final_success')).sum())==5)

    def bp_arrays(self,row):
        return self.inputs.arrays(row.trajectory_ref,'selected existing BP numerical plot only',
            fields=['episode_step','object_pos','goal','tcp_object_distance','joint_position','action_executed','success_step','robot_object_contact_pairs'])

    def plots(self):
        plt=self.plt;arm=self.read('bp_arm_parent_future.csv');pair=self.read('bp_paired_effects_parent_future.csv')
        fig=plt.figure(figsize=(15,9));gs=fig.add_gridspec(2,5,height_ratios=[1,1.4])
        for j,p in enumerate(RUNS):
            ax=fig.add_subplot(gs[0,j])
            for a in ARMS:
                g=arm[(arm.parent_id==p)&(arm.arm==a)];y=[100*g['J_'+str(t)].mean() for t in TIMES]
                ax.plot(np.asarray(TIMES)/1000,y,'o-',color=COLORS[a],label=SHORT[a],lw=1.8)
            ax.set(title=p,xlabel='추가 학습 전이 (천)',ylim=(-3,104));ax.set_xticks([0,16,32,64]);ax.grid(alpha=.17)
            if j==0:ax.set_ylabel('BP success_any (%)');ax.legend(ncol=3,fontsize=8,loc='lower left')
        ax=fig.add_subplot(gs[1,:]);labels=[p+'/'+f for p in RUNS for f in ['F01','F02']];y=np.arange(10)
        for contrast,offset,color in [('P-U',-.13,'#7956b5'),('P-B',.13,'#1b8791')]:
            x=pair[pair.contrast==contrast].set_index(['parent_id','future_id']).loc[[(p,f) for p in RUNS for f in ['F01','F02']]]
            ax.scatter(100*x.delta_auc,y+offset,label=contrast,color=color,s=46)
        ax.axvline(0,color='#888',lw=.8);ax.set(yticks=y,yticklabels=labels,xlabel='BP 정규화 AUC 대응 차이 (%p)');ax.invert_yaxis();ax.legend();ax.grid(axis='x',alpha=.17)
        fig.suptitle('BP 반복 범위 — 다섯 부모·각 두 미래, 기존 16개 물리 사례',fontsize=14);fig.tight_layout(rect=[0,0,1,.96])
        self.figure(fig,'01_BP_repetition','상단은 부모 안 두 미래 평균 성공률, 하단은10개 부모×미래 대응 AUC. 각 점의 평가 분모16이며 독립 부모는5개. 선은 네 관측 시점의 연결이고 연속 학습 경로가 아니다. B=BASE,U=RANDOM_PRE,P=ONSET.')

        h=self.read('bp_arm_histories.parquet');fig,axes=plt.subplots(1,3,figsize=(13,14),sharey=True)
        from matplotlib.colors import ListedColormap
        for ax,a in zip(axes,ARMS):
            g=h[h.arm==a].sort_values(['parent_id','future_id','initial_case_id'])
            ax.imshow(g[['z0','z16','z32','z64']].to_numpy(),aspect='auto',interpolation='nearest',cmap=ListedColormap(['#e9ecef',COLORS[a]]),vmin=0,vmax=1)
            ax.set(title=a,xticks=range(4),xticklabels=['0','16k','32k','64k'])
            for n in range(16,160,16):ax.axhline(n-.5,color='white',lw=1.7)
            ax.set_yticks(np.arange(10)*16+7.5);ax.set_yticklabels([p+'/'+f for p in RUNS for f in ['F01','F02']]);ax.set_xlabel('추가 학습 전이')
        axes[0].set_ylabel('160개 대응 이력: 각 묶음 안 BP_E00–E15')
        fig.suptitle('BP 네 시점 성공 이력 — 색: 성공, 회색: 실패; 결측 없음',fontsize=14);fig.tight_layout(rect=[0,0,1,.97])
        self.figure(fig,'02_BP_all160_histories','각 arm160행의 동일 parent/future/case 순서. 초기148성공/12실패는 부모별 공통 초기 관측을 두 미래에 재사용한 수이며 고유 물리 사례는16개다.1111은 네 평가에서 관측된 성공이고 평가 사이의 보존을 뜻하지 않는다.')

        fig,axes=plt.subplots(1,2,figsize=(13,5))
        r=self.risk.set_index('arm').loc[ARMS];bottom=np.zeros(3)
        for c,label,color in [('all_four_success','네 관측 모두 성공','#459b86'),('loss_then_final_recovery','중간 상실·최종 회복','#e8b45f'),('final_loss','최종 상실','#c76474')]:
            vals=r[c].to_numpy();axes[0].bar(np.arange(3),vals,bottom=bottom,color=color,label=label)
            for j,v in enumerate(vals):axes[0].text(j,bottom[j]+v/2,str(v),ha='center',va='center',fontsize=11)
            bottom+=vals
        axes[0].set(xticks=range(3),xticklabels=['B','U','P'],ylabel='초기 성공 이력 수 /148',title='고정된 초기 성공 집합');axes[0].legend(fontsize=8,loc='lower left')
        for j,a in enumerate(ARMS):
            g=self.acq[self.acq.arm==a];v=[int(g[g.first_success_train_step==t].histories.sum()) for t in TIMES[1:]]
            axes[1].bar(np.arange(3)+(j-1)*.24,v,width=.22,color=COLORS[a],label=SHORT[a])
            for i,k in enumerate(v):axes[1].text(i+(j-1)*.24,k+.1,str(k),ha='center',fontsize=9)
        axes[1].set(xticks=range(3),xticklabels=['16k\n이후 평가 2회','32k\n이후 평가 1회','64k\n이후 평가 0회'],ylabel='최초 관측 획득 이력 /초기 실패12',title='획득 시점과 이후 관측 기회');axes[1].legend();axes[1].set_ylim(0,13)
        fig.tight_layout();self.figure(fig,'03_BP_retention_acquisition','왼쪽148/arm은 초기 성공 고정집합, 오른쪽12/arm은 초기 실패 고정집합. U의2이력은 끝까지 성공 미관측. P16k획득11중2이력은 중간 상실 뒤 회복했다.64k최초 획득의 이후 유지는 미측정이다.')

        phys=self.read('bp_episode_physical_metrics.parquet');sel=self.selected[self.selected.contrast=='P-U'].set_index('case_type')
        kinds=['method_only_final_success','reference_only_final_success','both_final_success_different_history','identical_four_time_history']
        fig,axes=plt.subplots(4,4,figsize=(18,12))
        for i,typ in enumerate(kinds):
            s=sel.loc[typ]
            for a in [s.method,s.reference]:
                q=phys[(phys.parent_id==s.parent_id)&(phys.future_id==s.future_id)&(phys.arm==a)&(phys.initial_case_id==s.initial_case_id)&(phys.relative_train_step==64000)].iloc[0]
                z=self.bp_arrays(q);t=z['episode_step'];color=COLORS[a];label=SHORT[a]
                axes[i,0].plot(t,1000*np.abs(z['object_pos'][:,1]-z['goal'][:,1]),color=color,label=label,lw=1.1)
                axes[i,1].plot(t,1000*z['tcp_object_distance'],color=color,lw=1.1)
                hits=t[z['robot_object_contact_pairs']>0];axes[i,1].scatter(hits,np.full(len(hits),4 if a=='ONSET' else 0),color=color,s=1,alpha=.35)
                axes[i,2].plot(t,z['action_executed'][:,1],color=color,lw=.6,alpha=.7)
                axes[i,3].plot(t,z['action_executed'][:,3],color=color,lw=.6,alpha=.7)
            axes[i,0].axhline(20,color='#777',lw=.7,ls='--');axes[i,0].set_ylabel(s.parent_id+'/'+s.future_id+'/'+s.initial_case_id+'\n'+TYPES[typ]+'\nP'+str(s.method_pattern)+' / U'+str(s.reference_pattern),fontsize=8)
            for ax in axes[i]:ax.set_xlim(1,500);ax.grid(alpha=.13)
        for ax,title in zip(axes[0],['공식 버튼축 오차 (mm)','TCP–버튼 거리 (mm)·접촉 표본','세계 Y action 명령','gripper action 명령']):ax.set_title(title,fontsize=10)
        for ax in axes[-1]:ax.set_xlabel('실제 제어 action 번호 (1–500)')
        axes[0,0].legend();fig.suptitle('BP 최종 평가의 대응 궤적 — 유형별 중앙 사례, 반대·동일 이력 포함',fontsize=14)
        fig.tight_layout(rect=[0,0,1,.97]);self.figure(fig,'04_BP_paired_raw_paths','모든160사례를 분류한 뒤 각 유형의 AUC차 중앙 사례를 선택했다. P-U,+64k,동일 물리 초기조건. 버튼축 오차는post-action 세계Y오차,20mm선은 고정 공식 성공 기준. TCP거리는m→mm 변환,하단 접촉 점은제어endpoint 표본이다. action은[-1,1]정규화 명령이며 물체 변위나 인과 기여가 아니다.영상 유무로 사례를 교체하지 않았다.')

        w=self.read('do_window_content.parquet');fig,axes=plt.subplots(1,3,figsize=(16,8))
        eps=sorted(w.source_episode_id.unique());yy=np.arange(25)
        for a,off in [('ONSET',-.12),('RANDOM_PRE',.12)]:
            q=w[w.arm==a].set_index('source_episode_id').loc[eps]
            for ax,c in zip(axes,['net_opening_m','closing_path_m','post_endpoint_drawdown_m']):ax.scatter(1000*q[c],yy+off,s=29,color=COLORS[a],label=SHORT[a])
        for ax,title in zip(axes,['재사용 창의 순개방량 (mm)','재사용 창의 닫힘 누적량 (mm)','창 끝→첫 성공의 최대 되돌림 (mm)']):
            ax.set(yticks=yy,yticklabels=eps,title=title,ylim=(24.7,-.7));ax.axvline(0,color='#aaa',lw=.6);ax.grid(axis='x',alpha=.15)
        axes[0].legend();fig.suptitle('고정 DO 성공25에피소드 전수 — P/U 창과 재사용 밖 이후 맥락',fontsize=14);fig.tight_layout(rect=[0,0,1,.96])
        self.figure(fig,'05_DO_all25_contents','각32전이 창의 시작 직전부터끝까지p=-q의변화를집계.양수=개방,음수=닫힘.세번째열은창밖첫성공까지의맥락이며학습에재사용되지않았다.초기좌표는85정정물리h0를사용했고원SAC관측은수정하지않았다.원본q/m자료의표시만mm로변환했다.')

        examples=load(self.out/'case_selection.json')['DO_context_examples'];fig,axes=plt.subplots(3,2,figsize=(14,10))
        for i,ep in enumerate(examples):
            q=w[w.source_episode_id==ep];first=q.iloc[0]
            z=self.inputs.arrays(first.trajectory_ref,'selected25 DO existing numeric context for illustration',fields=['episode_step','joint_position','action_executed'],expected=first.source_sha256)
            t=z['episode_step'];end=int(first.sigma);ix=t<=end
            axes[i,0].plot(t[ix],-1000*z['joint_position'][ix],color='#344b60',lw=1.1)
            axes[i,1].plot(t[ix],-z['action_executed'][ix,1],color='#344b60',lw=.7)
            for a in ['ONSET','RANDOM_PRE']:
                row=q[q.arm==a].iloc[0]
                for ax in axes[i]:ax.axvspan(row.window_start,row.window_end,alpha=.2,color=COLORS[a],label=SHORT[a]);ax.axvline(row.tau,color='#777',ls=':',lw=.8)
            for ax in axes[i]:ax.axvline(end,color='#3b9374',ls='--',lw=.8);ax.set_xlim(1,end);ax.grid(alpha=.15)
            axes[i,0].set_ylabel(ep+'\n개방량 p=-q (mm)');axes[i,1].set_ylabel('DO 목표축 명령 = -action_Y')
        axes[0,0].legend();axes[0,0].set_title('원 물리 진행·고정 창·첫 성공');axes[0,1].set_title('명령과 실제 진행은 별도 측정')
        for ax in axes[-1]:ax.set_xlabel('원 제어 action 번호 (첫 공식 성공까지)')
        fig.tight_layout();self.figure(fig,'06_DO_context_and_fixed_windows','모든 전수 집계 후 선택: 완전 되돌림R02:000251,창순개방음수R04:000679,정렬ID중앙사례.색은원래고정P/U창32개,회색점선은tau,녹색점선은첫성공sigma.이는경로맥락예시이며창밖자료를재사용했다고뜻하지않는다.신규검출·창선택·환경실행없음.')

        inte=self.read('actual_interval_exposure_features.csv');fig,axes=plt.subplots(2,2,figsize=(13,9))
        labels=['0–16k','16–32k','32–64k'];xx=np.arange(3)
        for j,a in enumerate(['ONSET','RANDOM_PRE']):
            g=inte[inte.arm==a].groupby('interval_end').mean(numeric_only=True).reindex(TIMES[1:])
            axes[0,0].plot(xx,g.uses_per_actor_update,'o-',color=COLORS[a],lw=2,label=SHORT[a])
            for ax,c,scale in [(axes[0,1],'opening_positive_m',1000),(axes[1,0],'goal_axis_command',1),(axes[1,1],'contact_endpoint',100)]:
                ax.plot(xx,scale*g[c],'o-',color=COLORS[a],label=SHORT[a])
        for ax,title in zip(axes.flat,['실제 archive 사용 /actor update','사용량 가중 개방방향 변위 /draw (mm)','사용량 가중 DO 목표축 action','사용량 가중 접촉 endpoint (%)']):
            ax.set(xticks=xx,xticklabels=labels,title=title);ax.grid(alpha=.16);ax.legend()
        fig.suptitle('저장소와 실제 사용의 구분 — 부모·미래별 가중 후 동일 비중 평균',fontsize=14);fig.tight_layout(rect=[0,0,1,.96])
        self.figure(fig,'07_actual_interval_exposure','각부모×미래×arm에서누적actual최종배치사용량의차분을먼저계산했다.뒤32k구간은길이가두배이므로update당량을보였다.P/U episode-offset사용량은정확히대응하며실제다른내용을같은횟수로사용했다.BASE는archive0,조건부내용평균NA.연속선은3구간요약이고개별전이의인과효과가아니다.')

        link=self.read('exposure_BP_effect_linkage.parquet');q=link[(link.contrast=='P-U')&(link.interval_end==64000)]
        fig,axes=plt.subplots(1,2,figsize=(13,6))
        for p in RUNS:
            g=q[q.parent_id==p]
            for f,marker in [('F01','o'),('F02','^')]:
                r=g[g.future_id==f].iloc[0];axes[0].scatter(1000*r.cumulative_delta_opening_positive_m,100*r.BP_delta_AUC0_to_end,color=PCOLORS[p],marker=marker,s=65)
                axes[1].scatter(100*r.BP_delta_AUC0_to_end,100*r.BP_delta_J_end,color=PCOLORS[p],marker=marker,s=65)
            m=g.mean(numeric_only=True);axes[0].annotate(p,(1000*m.cumulative_delta_opening_positive_m,100*m.BP_delta_AUC0_to_end),xytext=(4,4),textcoords='offset points',fontsize=9,color=PCOLORS[p])
        for ax in axes:ax.axhline(0,color='#aaa',lw=.7);ax.grid(alpha=.16)
        axes[1].axvline(0,color='#aaa',lw=.7)
        axes[0].set(xlabel='0–64k 실제 사용한 P-U 개방 변위 차이 (mm/draw)',ylabel='BP P-U 정규화 AUC 차이 (%p)',title='자료 특징과 효과: 같은 부모의 두 미래')
        axes[1].set(xlabel='BP P-U AUC 차이 (%p)',ylabel='BP P-U 최종 성공률 차이 (%p)',title='곡선 이득과 최종 이득의 구분')
        for p in RUNS:axes[1].scatter([],[],color=PCOLORS[p],label=p)
        axes[1].legend(fontsize=9);fig.suptitle('설명 후보: 개방방향 노출차와 BP 효과 — 사후 기술, 예측 규칙 없음',fontsize=14)
        fig.text(.5,-.02,'● F01, ▲ F02. 독립 부모5개; LOO 저장소 중첩. 회귀·문턱·새 검정 없음.',ha='center',fontsize=10)
        fig.tight_layout();self.figure(fig,'08_content_effect_linkage','각점은부모×미래,노출은해당64k까지실제사용된자료만포함.부모상태와LOO저장소가함께달라져내용효과를분리하지못한다.부모평균의정렬은다수요약을살핀뒤발견한약한후보이고5부모에서추정한선택규칙이아니다.R05/F02는AUC양수지만최종P-U음수다.')

        s=sel.loc['both_final_success_different_history'];fig,axes=plt.subplots(3,3,figsize=(14,10))
        for i,ttrain in enumerate(TIMES[1:]):
            for a in [s.method,s.reference]:
                r=phys[(phys.parent_id==s.parent_id)&(phys.future_id==s.future_id)&(phys.arm==a)&(phys.initial_case_id==s.initial_case_id)&(phys.relative_train_step==ttrain)].iloc[0]
                z=self.bp_arrays(r);t=z['episode_step'];color=COLORS[a]
                axes[i,0].plot(t,1000*np.abs(z['object_pos'][:,1]-z['goal'][:,1]),color=color,label=SHORT[a],lw=1)
                axes[i,1].plot(t,1000*z['tcp_object_distance'],color=color,lw=1)
                axes[i,2].plot(t,z['action_executed'][:,1],color=color,lw=.7,alpha=.75)
            axes[i,0].axhline(20,color='#777',ls='--',lw=.7);axes[i,0].set_ylabel('+'+str(ttrain//1000)+'k\n축 오차 (mm)')
            for ax in axes[i]:ax.set_xlim(1,500);ax.grid(alpha=.15)
        for ax,title in zip(axes[0],['버튼 목표축 진행','TCP–버튼 거리 (mm)','세계 Y action 명령']):ax.set_title(title)
        axes[0,0].legend();fig.suptitle(s.parent_id+'/'+s.future_id+'/'+s.initial_case_id+' — P '+str(s.method_pattern)+' / U '+str(s.reference_pattern),fontsize=14)
        for ax in axes[-1]:ax.set_xlabel('각 평가의 원 제어 action 번호')
        fig.tight_layout(rect=[0,0,1,.96]);self.figure(fig,'09_BP_recovery_observation_paths','P-U공통최종성공·이력상이유형의정해진중앙사례.R01/F01/BP_E00:P1011,U1001.16k둘실패,32kP회복/U실패,64k둘회복.동일초기조건에서서로다른정책의자연궤적이며이후방문상태까지같은대조가아니다.상실·회복의정확한학습step은미측정이다.')

    def report(self):
        h=self.read('bp_arm_histories.parquet');pair=self.read('bp_paired_effects_parent_future.csv');w=self.read('do_window_content.parquet')
        phys=self.read('bp_episode_physical_metrics.parquet');unc=self.read('bp_original_uncertainty.csv')
        lopo=self.read('bp_lopo.csv');pp=self.read('bp_parent_effects.csv');link=self.link_parent
        seeds81=self.inputs.json(ORIGINAL/'seed_manifest.json','original independent initialization seeds; read only')
        seeds85=self.inputs.json(CAMPAIGN/'seed_manifest.json','frozen follow-on seeds and archive window seed; no draws')
        save(self.out/'provenance/seed_provenance.json',{'original81':seeds81,'continuations85':seeds85,'new_seed_or_bootstrap_draws':0})
        definitions='''# 87번 지표·시점·분모 규약

이 분석은85번의 같은 기록을 다시 계산한 사후 탐색이다. P=ONSET,U=RANDOM_PRE,B=BASE. BC 손실이 아니라SAC 최종배치의DO slot을archive로대체한처치다.

- BP history의z0,z16,z32,z64는+0,+16k,+32k,+64k에서500action동안한번이라도관측된공식success의OR다.원시success는현재상태flag다.
- 160=5부모×2미래×16사례,독립부모5,고유물리사례16,초기평가는80부모×사례관측을두미래/세arm이공유한다. 초기성공74/80,초기실패6/80이반복표에서148/12가된다.
- AUC=[.125,.25,.375,.25]·J. 부모안두미래평균뒤부모동일비중. pp는0..1차이×100.1111은네관측시점성공이며그사이의유지를증명하지않는다.
- gain/loss는인접원평가점0→1/1→0사건.이전성공후실패블록이끝나는0→1만recovery.사건수와그사건을겪은이력수는별개다.
- 초기성공의최종유지=모든네관측성공+관측상실후최종성공.두집단의합차이를보존구성으로분해하며개별사례의인과적상실예방으로부르지않는다.
- 처음획득16/32/64k의남은평가기회는2/1/0.마지막획득은이후유지미측정이다.
- BP공식목표오차=abs(버튼Y-goalY),≤.02m. qnegative가누름방향,물체세계+Y. DOqnegative가개방방향,세계-Y.같은joint부호가같은행동기능을뜻하지않는다.
- T_t의action은obs_(t-1)에서생성,저장physics는action후x_t.제어t1..500,control_dt=.0125s. BP TCP이동총량은실제저장post1→post500의499links만계산한다.초기TCP를raw관측으로추정하지않는다.
- DO물리초기q0=raw_reset_handleY-goalY-.19,h0=goal+[0,.19+q0,0].85정정mapping그대로이며원reset관측·실제h0·x1별도저장,원SAC입력수정없음.
- DO개방량p=-q(m).창[a,e]순개방=p_e-p_(a-1),개방path=sum(max(Δp,0)),닫힘path=sum(max(-Δp,0)).순개방=개방path-닫힘path.
- 창이후맥락은e+1..sigma첫성공.끝기준되돌림=max(0,p_e-min(p_post));추가진행=max(p_post)-p_e.전체순개방되돌림은창net>1e-8m이며이후p<=p_(a-1)+1e-8m인경우.1e-8은수치0허용오차이며좋은행동의성능문턱이아니다.
- 실제사용n_j=C_j(end)-C_j(start).P/U원episode+offset별n_j동일검증.노출평균=sum(n_j*feature_j)/sum(n_j).해당시점이후사용량을앞시점결과에붙이지않는다. actor/critic실제사용count를각각보고하며critic2개때문에2배로세지않는다.
- 반복draw비율=1-고유전이수/총사용수.입력의경험수가증가했다는뜻이아니다.사용량가중변위는원자료변위의재표집평균으로새로실행한물체이동량이아니다.
- actionXYZ명령,gripper명령,실제TCP/물체변위는별도다.접촉은body/geom식별된제어endpoint표본이며내부substep접촉부재를뜻하지않는다.
- 원85의부모bootstrap분위범위만복사한다.이번새bootstrap/pvalue/선택모델/threshold탐색없음.중첩LOO와기존16개개발사례에조건화한탐색이다.
'''
        (self.out/'metric_definitions.md').write_text(definitions,encoding='utf-8')
        uncertainties=unc[unc.contrast.isin(['P-U','P-B'])][['contrast','metric','estimate','lower','upper']]
        ten=self.ten[['parent_id','future_id','initial_success','B_final_successes','U_final_successes','P_final_successes',
            'P-U_delta_auc_pp','P-B_delta_auc_pp','P-U_final_delta_J_pp','P-B_final_delta_J_pp']]
        timing=pair[pair.contrast.isin(['P-U','P-B'])].groupby('contrast')[['delta_J_16000','delta_J_32000','delta_J_64000']].mean().reset_index()
        initialrisk=self.risk[['arm','all_four_success','loss_then_final_recovery','final_loss','initial_failure_final_success','initial_failure_acquired_final_failed','never_observed_success']]
        event=self.risk[['arm','gain_events','loss_events','recovery_events']]
        content=self.window_means[['arm','net_opening_m','opening_path_m','closing_path_m','mean_goal_distance_pre_m','mean_goal_axis_command','mean_gripper_command','mean_TCP_handle_pre_m','mean_reward','contact_endpoint_steps']]
        exposure=self.weights[['arm','goal_distance_pre_m','opening_positive_m','closing_positive_m','goal_axis_command','gripper_command','reward','contact_endpoint','TCP_handle_distance_pre_m']]
        linkage=link[['parent_id','BP_delta_AUC0_to_end','BP_delta_J_end','cumulative_delta_opening_positive_m','cumulative_delta_closing_positive_m',
            'cumulative_delta_goal_axis_command','cumulative_delta_gripper_command','cumulative_delta_contact_endpoint']]
        trade=self.tradeoff[(self.tradeoff.scope.isin(['DO','DC','PU','BP','MACRO4']))&(self.tradeoff.metric=='delta_auc')]
        trade=trade.pivot(index='scope',columns='contrast',values='estimate').reindex(['DO','DC','PU','BP','MACRO4']).reset_index()
        types=self.read('bp_case_type_counts.csv');types=types[types.contrast.isin(['P-U','P-B'])]
        post=w.groupby('arm').agg(episodes=('source_episode_id','size'),mean_post_drawdown_m=('post_endpoint_drawdown_m','mean'),max_post_drawdown_m=('post_endpoint_drawdown_m','max'),
            mean_additional_opening_m=('post_larger_opening_m','mean')).reset_index()
        positive=w[w.net_opening_m>1e-8].groupby('arm').size().to_dict()
        full=w.groupby('arm').full_endpoint_net_gain_reversal.apply(lambda s:sum(bool(x) for x in s if pd.notna(x))).to_dict()
        method_only=self.physical_groups[self.physical_groups.case_type.isin(['method_only_final_success','reference_only_final_success'])]
        representative=self.selected[['contrast','case_type','parent_id','future_id','initial_case_id','method_pattern','reference_pattern']]
        figure_text='\n\n'.join('!['+r['id']+']('+r['png']+')\n\n'+r['caption'] for r in self.figures)
        initseeds='、'.join(p+'='+str(seeds81['streams'][p]['model_initialization']) for p in RUNS)
        from presentation import render_report
        report=render_report(self,locals(),table,TYPES)
        (self.out/'report_ko.md').write_text(report,encoding='utf-8')
        self.register()
        save(self.out/'figure_captions.json',self.figures)
        missing=[
            dict(item='BP success/history/raw physical endpoints',status='complete',scope='1520 episodes; 160 paired histories x3 arms',impact='none'),
            dict(item='DO fixed window physical content',status='complete',scope='25 donor episodes;50 windows;1600 window transitions',impact='none'),
            dict(item='actual final-batch usage by interval',status='complete',scope='38400 interval-transition rows;60 exposure rows;90 paired linkage rows',impact='none'),
            dict(item='initial BP TCP',status='not_inferred',scope='reset physical TCP site not separately saved',impact='TCP path only post1 to post500; do not infer from a different observation point'),
            dict(item='contact during all MuJoCo substeps',status='unmeasured',scope='only control endpoint contact samples',impact='no contact sample does not establish no substep contact'),
            dict(item='selected case videos',status='limited_to_original_selection',scope='saved final videos only; selected unavailable videos not regenerated',impact='numeric analysis population unchanged; videos referenced, not viewed in87'),
            dict(item='same-state actor/Q/gradient analysis',status='out_of_scope',scope='no model load/forward/backward',impact='no direct parameter/mechanism claim'),
            dict(item='independent new-case confirmation / causal archive contribution',status='unmeasured',scope='same85 development panel and overlapping LOO pools',impact='exploratory conditional findings only')]
        pd.DataFrame(missing).to_csv(self.out/'missingness_and_diagnostics.csv',index=False)

    def register(self):
        facts=[
          ('BP_repeat','P-U BP AUC+7.578pp;3/5 parents,6/10 future pairs positive;same sign across both futures within each parent.',
           'R03/R04 negative in both futures; R05/F02 final P-U negative despite positive AUC.','bp_ten_matched_runs_summary.csv','Fixed-state/pool-specific response; archive content and learner state confounded.'),
          ('BP_preservation','P-B final+40=initial-success retention+32 plus initial-failure final gain+8;P-U+11=+8+3.',
           'P still has20 initial-success histories with observed loss and final recovery.','bp_fixed_initial_risk_summary.csv','More all-observed success and some recovery; individual causal prevention unmeasured.'),
          ('BP_acquisition','P initial failures:11/12 first observed successful16k,1/12 at32k;12/12 final success.',
           'Two early gains have intermediate loss/recovery; U3 and B2 first gains only64k have no later evaluation.','bp_first_acquisition_opportunities_normalized.csv','Not a final-time-only acquisition artifact; generalization unmeasured.'),
          ('BP_physical','P-U final method-only16 vs reference-only5; opposing goal-axis and natural TCP paths are visible.',
           'P-B reference-only1 gets closer in TCP yet fails; identical labels can have different paths.','BP_final_physical_differences_by_case_type.csv','Goal-specific actuation and approach differ; proximity/contact not functional proof.'),
          ('DO_content','P/U same25 episodes:mean net opening63.23/32.21mm;P24/25 net positive,U11/25.',
           'R04:train:000679 P net-1.608mm; R02:train:000251 is sole full endpoint-gain reversal among24 positive P windows.','do_window_content.parquet','Full selection-rule content differs; first local onset is not always net progress or useful skill.'),
          ('actual_use','Each P/U total10227844 actual archive uses,exact matched episode-offset counts;weighted positive opening2.013/1.117mm per draw.',
           'BASE has0 archive use; P/U BP effect directions differ across parents despite common content direction.','actual_interval_exposure_features.csv','Amount difference excluded for P-U; contents, native omissions and induced learning trajectories remain.'),
          ('content_condition_candidate','Positive-parent AUC means have larger P-U positive-opening exposure difference than two negative-parent means in these5 records.',
           'Posthoc among many summaries;n5;R05F02 AUC/final reversal;LOO overlaps and parent state changes jointly.','content_BP_linkage_parent_summary.csv','Weak ordinal candidate only; no fitted threshold or transferable prediction rule.'),
          ('task_tradeoff','Original85 P-U DO AUC-1.250pp,Push-1.953pp despite BP+7.578pp.',
           'P-B DO estimate positive but original progression criterion failed.','original85_task_tradeoffs.csv','Task tradeoff persists; no universal experience rule or onset expansion authorization.')]
        rows=[]
        for name,fact,contrary,evidence,explanation in facts:
            rows.append(dict(id=name,observation=fact,execution_status='completed_existing_files',scientific_status='exploratory_conditional',
                metric_and_definition='metric_definitions.md and referenced table',scope='original85 fixed30 branches;5 parents;2 futures;16 BP physical cases;25 eligible DO donor episodes',
                evidence_table='tables/'+evidence,opposite_or_unchanged=contrary,possible_explanation=explanation,
                unresolved='learner state versus LOO archive;native batch replacement and full shared-network learning;new cases/futures unmeasured',
                next_minimum_check='Hold learner fixed and vary matched archive composition if separately specified; no automatic execution',
                why_not_executed='Current authorization is file-only posthoc; environment/model/learning execution prohibited',
                selection='post-outcome, same85 data',derived=True,independent_confirmation=False,new_execution=ZERO))
        (self.out/'phenomenon_register.jsonl').write_text(''.join(json.dumps(clean(r),ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
        save(self.out/'candidate_factor_evidence_record.json',dict(
            version='87',execution_status='completed_existing_files',scientific_conclusion='BP response repeats within fixed parent/pool but varies across parents; content condition is weak and exploratory',
            primary_effects=dict(BP_AUC_P_U_pp=7.578125,BP_AUC_P_B_pp=12.03125,BP_final_P_U_cases=11,BP_final_P_B_cases=40),
            baselines=['RANDOM_PRE','BASE'],uncertainty_scope='Reuse original85 nominal parent-bootstrap ranges;5 parents and overlapping LOO;fixed16 development cases;no new draws',
            seeds=dict(original_initialization_manifest=str(ORIGINAL/'seed_manifest.json'),continuation_manifest=str(CAMPAIGN/'seed_manifest.json'),F01_root=52001,F02_root=52002,new_draws=0),
            actual_costs='analysis_costs.json; all new environment/model/learning counts0',source_and_input_provenance=['input_manifest.jsonl','provenance/core_input_manifest.jsonl','source_hashes.json'],
            unfavorable=['P-U AUC negative R03/R04','R05 F02 final P-U negative','P-B AUC negative R01','DO/Push P-U AUC negative'],
            limitations=['same85 posthoc evidence, no independent confirmation','learner state and LOO composition jointly differ','world axes DO/BP opposite','no direct policy/critic/gradient or individual data causal attribution'],
            next_decision_criteria='No new gate. First isolate state versus archive composition; independently confirm BP question before general method claims.',
            prior_record=str(ANALYSIS/'candidate_factor_evidence_record.json'),automatic_followup_authorized=False))

    def finish(self):
        import importlib.metadata
        import psutil
        self.checks.add('runtime/model modules absent at finish',not (FORBIDDEN&set(sys.modules)))
        self.checks.add('nine nonempty figure pairs',len(self.figures)==9 and all((self.out/r['png']).stat().st_size>1000 and (self.out/r['svg']).stat().st_size>1000 for r in self.figures))
        self.inputs.flush(self.out);self.checks.flush(self.out)
        shutil.copy2(HERE/'analysis_config.json',self.out/'analysis_config.json')
        save(self.out/'dependencies.json',dict(python=sys.version,packages={p:importlib.metadata.version(p) for p in ['numpy','pandas','pyarrow','matplotlib','psutil']},forbidden_runtime_modules_imported=[]))
        proc=psutil.Process();cost=dict(started_utc=self.started,finished_utc=utc(),delivery_wall_seconds=time.perf_counter()-self.start,
            delivery_memory=proc.memory_info()._asdict(),delivery_io=proc.io_counters()._asdict(),delivery_cpu=proc.cpu_times()._asdict(),
            tracked_delivery_input_bytes=self.inputs.bytes_read,core_costs=load(self.core/'analysis_costs.json'),
            independent_verification_costs=load(Path(self.verification['output'])/'costs.json'),
            historical_preliminary_history_audit=str(HERE/'results/20261106T123520Z_history_audit_ad3921d1/analysis_costs.json'),
            source_campaign_environment_steps_not_recounted=4964900,new_execution=ZERO,
            cost_units='wall seconds/CPU seconds/OS read-write bytes/working-set bytes are separate; not GPU kernel time')
        save(self.out/'analysis_costs.json',cost)
        status=dict(version='87_bp_retention_archive_content_posthoc_v1',status='analysis_complete_pending_file_delivery_review',
            stages={k:dict(status='complete',reason=v) for k,v in {
                'BP_repetition':'10 parent-future and5 parent means,all3 comparisons,LOPO and full160 paired histories',
                'BP_histories_and_performance':'480 arm histories;1520 complete BP evaluations;all760000 endpoints source-verified',
                'fixed_DO_content':'25 episodes;50 frozen windows;1600 transition contents;corrected physical x0 and post-window context',
                'actual_use_and_effect_linkage':'38400 usage rows;60 interval exposures;90 time-respecting comparison links'}.items()},
            independent_confirmation=False,source_campaign=str(CAMPAIGN),core_analysis=str(self.core),verification=str(self.verification['output']),
            missingness='missingness_and_diagnostics.csv',new_execution=ZERO,
            scientific_status='Exploratory BP signal with adverse parents and task tradeoffs; no transferable condition or primitive established',
            next_experiment_launched=False,publication_performed=False,output=str(self.out))
        save(self.out/'FINAL_STATUS.json',status)
        commands=f'''# 재분석 안내

원래 Windows runtime 프로젝트 루트는 `{ROOT}` 이다. source_snapshot과입력manifest의해시를먼저확인한다. Python은기존file-processing환경을사용하며torch/Meta-World/MuJoCo를import하지않는다.

```powershell
.\\13_e0_e3_autonomous_queue_v1\\.venv\\Scripts\\python.exe -X utf8 87_bp_retention_archive_content_posthoc_v1\\analyze.py --stage core
.\\13_e0_e3_autonomous_queue_v1\\.venv\\Scripts\\python.exe -X utf8 87_bp_retention_archive_content_posthoc_v1\\verify.py --analysis <새 core 출력 경로>
.\\13_e0_e3_autonomous_queue_v1\\.venv\\Scripts\\python.exe -X utf8 87_bp_retention_archive_content_posthoc_v1\\report.py --core <새 core 출력 경로>
.\\13_e0_e3_autonomous_queue_v1\\.venv\\Scripts\\python.exe -X utf8 87_bp_retention_archive_content_posthoc_v1\\finalize_delivery.py --delivery <새 delivery 출력 경로> --visual-review <실제로 확인한 PNG 해시 JSON>
```

이번core출력: `{self.core}`. 독립검산: `{self.verification['output']}`.

모든실행은새폴더를만든다. 원캠페인·보고서·checkpoint는수정하지않는다. 파일만계산하고새환경전이·모델실행·난수draw는없다. bootstrap분위범위는원85요약을그대로참조한다. 새자료없이는새goal/parent의확증을재생성할수없다.

전달ZIP에는소형표·설정·코드·그림·핵심영수증만들어간다. 원본대형NPZ/영상/model은`provenance/core_input_manifest.jsonl`의실제경로+SHA256로연결한다. 환경상태pkl이나정책모델을분석실행시로드하지않는다. snapshot을새checkout에서재실행하려면code의common.py에기록된ROOT기준원본파일상대배치를보존하거나같은hash의원자료경로를명시적으로매핑해야한다. 원GitHub의group레이아웃을legacy runtime에pull하지않는다.
'''
        (self.out/'REPRODUCE.md').write_text(commands,encoding='utf-8')
        save(HERE/'LATEST_DELIVERY_PENDING.json',dict(output=str(self.out),status=status['status']),replace=True)
        print(json.dumps(dict(output=str(self.out),status=status['status'],figures=len(self.figures)),ensure_ascii=False),flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--core',required=True);args=parser.parse_args()
    d=Delivery(args.core)
    try:
        d.derived_tables();d.setup_plot();d.plots();d.report();d.finish()
    except BaseException as exc:
        import traceback
        d.inputs.flush(d.out);d.checks.flush(d.out)
        save(d.out/'FAILED.json',dict(error=repr(exc),traceback=traceback.format_exc(),new_execution=ZERO,elapsed_seconds=time.perf_counter()-d.start))
        raise

if __name__=='__main__':main()
