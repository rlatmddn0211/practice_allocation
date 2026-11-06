"""Korean report, standalone figures, provenance bundle and durable evidence record."""
from __future__ import annotations
import sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from common import *
guard_file_only()
import argparse
import zipfile
import numpy as np
import pandas as pd

def figures(analysis,prep,preparation_only=False):
    os.environ['MPLCONFIGDIR']=str(analysis/'.mplconfig')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    font=Path('C:/Windows/Fonts/malgun.ttf')
    if font.exists():font_manager.fontManager.addfont(str(font));plt.rcParams['font.family']='Malgun Gothic'
    plt.rcParams.update({'axes.unicode_minus':False,'font.size':9,'figure.dpi':140})
    dest=analysis/'figures';dest.mkdir(exist_ok=True);captions=[]
    def finish(fig,name,caption):
        fig.tight_layout();fig.savefig(dest/(name+'.png'),dpi=170,bbox_inches='tight');fig.savefig(dest/(name+'.svg'),bbox_inches='tight');plt.close(fig)
        captions.append(dict(file='figures/'+name+'.png',caption=caption))
    cand=pd.read_parquet(prep/'onset_candidates_and_exclusions.parquet');win=pd.read_parquet(prep/'archive_windows.parquet')
    eligible=cand[cand.eligible].sort_values('permanent_episode_id');positions=sorted(set([0,len(eligible)//2,len(eligible)-1]))
    selected=eligible.iloc[positions]
    save(analysis/'case_selection.json',dict(rule='eligible permanent episode IDs sorted; first/middle/last, no video/performance selection',
        selected=selected.permanent_episode_id.tolist(),posthoc_status='illustrations of fixed preparation rule, not independent confirmation'))
    fig,axes=plt.subplots(len(selected),2,figsize=(12,3*len(selected)),squeeze=False)
    for row,(_,r) in enumerate(selected.iterrows()):
        with np.load(r.trajectory_ref,allow_pickle=False) as z:
            g=z['goal'][0];h=np.vstack((np.array(r.h0),z['object_pos']));d=np.linalg.norm(h-g,axis=1)
            q=np.r_[r.q0,z['joint_position']];contact=z['robot_object_contact_pairs']
        w=win[win.permanent_episode_id==r.permanent_episode_id].set_index('arm');x=np.arange(len(d));stop=min(len(d)-1,int(r.sigma)+25)
        for col,y,label in [(0,d*1000,'목표 거리 (mm)'),(1,q*1000,'slide joint q (mm)')]:
            ax=axes[row,col];ax.plot(x[:stop+1],y[:stop+1],color='#24476b',lw=1)
            for arm,color in [('ONSET','#d77a32'),('RANDOM_PRE','#43a3a0')]:
                a=w.loc[arm];ax.axvspan(a.start-.5,a.end+.5,color=color,alpha=.25,label=arm)
            ax.axvline(r.tau,color='#b44b28',ls='--',label='tau');ax.axvline(r.sigma,color='black',ls=':',label='첫 공식 성공 sigma')
            ax.set(xlabel='제어 action 번호 t (1부터)',ylabel=label,title=f'{r.permanent_episode_id} (tau={int(r.tau)}, sigma={int(r.sigma)})')
            if row==0 and col==0:ax.legend(fontsize=7)
    finish(fig,'01_onset_windows','적격 ID 정렬의 처음/중간/마지막 3개. 원 제어 step, 단위 mm. x0 물체 위치는 고정 XML·goal·reset joint에서 산술 복원했다. W32=0.4초이며 P/U 모두 sigma 이전 원 전이32개다. 접촉은 적격 조건이 아니다.')
    counts=pd.read_csv(prep/'eligibility_by_donor.csv');ready=pd.read_csv(prep/'readiness_by_receiver.csv')
    fig,axes=plt.subplots(1,2,figsize=(11,4));xx=np.arange(5)
    axes[0].bar(xx,counts.eligible_episodes,color='#ce7b38',label='적격')
    axes[0].bar(xx,counts.successful_episodes-counts.eligible_episodes,bottom=counts.eligible_episodes,color='#c6ccd2',label='제외')
    axes[0].set(xticks=xx,xticklabels=counts.donor_run,ylabel='원 성공 에피소드 수',title='31개 성공 → 25개 적격');axes[0].legend()
    axes[1].bar(xx,ready.eligible_episodes,color='#447f9d');axes[1].axhline(8,color='black',ls='--',label='운영 최소8개')
    axes[1].set(xticks=xx,xticklabels=ready.parent_id,ylabel='자기 run 제외 적격 에피소드',title='LOO 지원 조건');axes[1].legend()
    finish(fig,'02_support_and_exclusions','독립 donor run5개의 성공 수와 적격 수, receiver별 LOO 지원. 운영 최소8개 및 2 donor×2개 조건은 검정력 보장이 아니다. 대표 제외 사유: onset 없음2개, W32가 첫 성공에 닿음4개.')
    if preparation_only:
        save(analysis/'figure_captions.json',captions)
        return captions
    curves=pd.read_csv(analysis/'learning_curves.csv');cells=pd.read_csv(analysis/'cell_metrics.csv');effects=pd.read_csv(analysis/'paired_effects_by_parent_future.csv')
    color={'BASE':'#666c75','RANDOM_PRE':'#279b96','ONSET':'#d47630'}
    fig,axes=plt.subplots(2,3,figsize=(12,7),sharex=True,sharey=True)
    for ax,parent in zip(axes.flat,['전체 동일 가중']+RUNS):
        part=curves[curves.task_id=='DO']
        if parent in RUNS:part=part[part.parent_id==parent]
        for arm in ['BASE','RANDOM_PRE','ONSET']:
            means=part[part.arm==arm].groupby('relative_train_step').success_rate.mean().sort_index()
            ax.plot(means.index/1000,means.values*100,marker='o',color=color[arm],label=arm)
        ax.set(title=parent,xlabel='추가 학습 (천 전이)',ylabel='DO success_any (%)',ylim=(-2,102));ax.grid(alpha=.2)
    axes[0,0].legend(fontsize=7)
    finish(fig,'03_do_learning_curves','4개 실제 평가 시점의 선형 연결. 원래 시작 분포의 고정16사례, 부모별 두 미래 동일 가중, 전체 부모5개 동일 가중. 연속 시간의 곡선이나 수렴 시점을 관측한 것은 아니다.')
    fig,axes=plt.subplots(1,2,figsize=(12,5),sharey=True)
    for ax,contrast in zip(axes,['P-U','P-B']):
        sub=effects[(effects.scope=='DO')&(effects.contrast==contrast)].sort_values(['parent_id','future_id'])
        yy=np.arange(len(sub));ax.axvline(0,color='gray',lw=1);ax.scatter(sub.delta_auc*100,yy,color='#427f9d')
        ax.set(yticks=yy,yticklabels=[r.parent_id+'/'+r.future_id for r in sub.itertuples()],xlabel='DO 정규화 AUC 차이 (%p)',title=contrast)
        ax.grid(axis='x',alpha=.2)
    finish(fig,'04_paired_parent_future_effects','5부모×2미래 대응 점추정 전체10개. 각 점은16개 동일 물리 사례 평가를 사용한다. 10개 독립 초기학습으로 세지 않는다. 부모 단위 bootstrap 범위는 본문 표의 별도 민감도 요약이다.')
    fig,axes=plt.subplots(1,3,figsize=(14,4));xx=np.arange(4)
    for j,arm in enumerate(['BASE','RANDOM_PRE','ONSET']):
        means=cells[cells.arm==arm].groupby('task_id')[['auc','J_64000']].mean().reindex(['DO','DC','PU','BP'])
        axes[0].bar(xx+(j-1)*.23,means.auc*100,width=.23,color=color[arm],label=arm)
        axes[1].bar(xx+(j-1)*.23,means.J_64000*100,width=.23,color=color[arm])
    retention=pd.read_csv(analysis/'retention_gain_loss.csv')
    for j,arm in enumerate(['BASE','RANDOM_PRE','ONSET']):
        means=retention[retention.arm==arm].groupby('task_id').L.mean().reindex(['DO','DC','PU','BP'])
        axes[2].bar(xx+(j-1)*.23,means*100,width=.23,color=color[arm])
    for ax,title in zip(axes,['정규화 AUC','+64k 성공률','초기 성공→최종 실패 / 전체16사례']):
        ax.set(xticks=xx,xticklabels=['DO','DC','PU','BP'],ylabel='전체 사례 비율 (%)',title=title)
    axes[0].legend(fontsize=7)
    finish(fig,'05_task_tradeoffs','네 과제별 전체 부모·미래 동일 가중 요약. 세 번째 패널은 전체16사례 분모의 상실이며 초기 성공 조건부 비율과 다르다. DO 초기 성공 수0이면 그 조건부 비율은 NA다.')
    uses=pd.read_parquet(analysis/'archive_usage_by_checkpoint.parquet');uses=uses[(uses.checkpoint==1064000)&(uses.arm!='BASE')]
    fig,axes=plt.subplots(1,2,figsize=(12,4))
    donor=uses.groupby(['arm','donor_run']).actor_sample_count.sum().unstack(fill_value=0)
    donor.plot(kind='bar',stacked=True,ax=axes[0],rot=0);axes[0].set(ylabel='실제 archive batch slot 사용 수',title='출처별 실제 사용 (critic과 각각 동일)')
    p=win[win.arm=='ONSET'].sort_values('permanent_episode_id')
    axes[1].bar(np.arange(len(p)),p.overlap_fraction*100,color='#5a8f9d');axes[1].set(xlabel='정렬된 적격 원 episode25개',ylabel='P/U 원 전이 중복률 (%)',title='고정32전이 창의 중복')
    finish(fig,'06_archive_exposure','최종 실제 actor/critic 사용량은 교체를 마친 batch 기준이며 critic 두 개로 배수 계산하지 않는다. archive draw는 새 환경 전이가 아니다. 중복은 허용했고 재추출하지 않았다.')
    save(analysis/'figure_captions.json',captions)
    return captions

def ledger(campaign):
    rows=[]
    for path in Path(campaign).rglob('*_control_journal.bin'):
        data=path.read_bytes();rows.append(dict(path=str(path),category=path.name.replace('_control_journal.bin',''),issued=data.count(b'I'),completed=data.count(b'C'),failed_markers=data.count(b'F')))
    for path in (BASE/'results').glob('*technical_validation*/costs/technical_control_journal.bin'):
        data=path.read_bytes();rows.append(dict(path=str(path),category='technical',issued=data.count(b'I'),completed=data.count(b'C'),failed_markers=data.count(b'F')))
    return pd.DataFrame(rows)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--analysis',type=Path,required=True);args=ap.parse_args();analysis=args.analysis.resolve();started=time.perf_counter()
    status=load(analysis/'FINAL_STATUS.json');campaign=Path(status['campaign']);prep=Path(status['preparation'])
    if status['status']!='complete':raise RuntimeError('Complete report requires complete valid comparisons; retain partial analysis separately')
    verification=Path(load(analysis/'LATEST_VERIFICATION.json')['output'])
    if load(verification/'FINAL_STATUS.json')['status']!='passed':raise RuntimeError('Independent verification not passed')
    report_source=analysis/'source_snapshot'/'finalize.py'
    if not report_source.exists():shutil.copy2(__file__,report_source)
    reference_context=Path(__file__).parent/'reference_context.json'
    if reference_context.exists():shutil.copy2(reference_context,analysis/'reference_context.json')
    captions=figures(analysis,prep)
    costs=ledger(campaign);costs.to_csv(analysis/'attempt_cost_ledger.csv',index=False)
    totals=costs.groupby('category')[['issued','completed']].sum();new_issued=int(costs.issued.sum());new_completed=int(costs.completed.sum())
    summary_cost=dict(original_campaign_cost_separate=6604850,new_issued=new_issued,new_completed=new_completed,new_cap=4970000,
        remaining=4970000-new_issued,technical=int(totals.loc['technical','issued']),technical_failed_retry_cap=10000,
        original_plus_new_bookkeeping_sum=6604850+new_issued,reset_internal_physics_not_in_environment_transition_count=True,
        category=totals.to_dict('index'),GPU_time_scope='job elapsed wall time, not kernel-only GPU time')
    save(analysis/'costs.json',summary_cost)
    cells=pd.read_csv(analysis/'cell_metrics.csv');effects=pd.read_csv(analysis/'paired_effects_by_parent_future.csv');parents=pd.read_csv(analysis/'parent_effects.csv')
    trade=pd.read_csv(analysis/'task_tradeoffs.csv');ret=pd.read_csv(analysis/'retention_gain_loss.csv');history=pd.read_parquet(analysis/'checkpoint_case_history.parquet')
    episodes=pd.read_parquet(analysis/'evaluation_outcomes.parquet');win=pd.read_parquet(prep/'archive_windows.parquet');cand=pd.read_parquet(prep/'onset_candidates_and_exclusions.parquet')
    ready=pd.read_csv(prep/'readiness_by_receiver.csv');counts=pd.read_csv(prep/'eligibility_by_donor.csv');signal=load(analysis/'operational_signal.json')
    cache_checks=[]
    cache_fields=['transition_id','obs_policy','action_executed','reward','next_obs_actual','terminated','truncated','bootstrap_mask']
    with np.load(prep/'selected_window_arrays.npz',allow_pickle=False) as cache:
        for key,part in win.groupby('permanent_episode_id'):
            if sha(Path(part.iloc[0].trajectory_ref))!=part.iloc[0].source_sha256:raise RuntimeError('Original source NPZ hash changed: '+key)
            with np.load(part.iloc[0].trajectory_ref,allow_pickle=False) as raw:
                for index,w in part.iterrows():
                    for name in cache_fields:
                        match=np.array_equal(cache[f'{index:03d}_{name}'],raw[name][int(w.start)-1:int(w.end)])
                        if not match:raise RuntimeError('Selected cache differs from frozen raw transition: '+key+'/'+w.arm+'/'+name)
                        cache_checks.append(dict(window_id=w.archive_window_id,field=name,exact=True))
    save(analysis/'archive_cache_integrity.json',dict(exact_original_array_checks=len(cache_checks),all_exact=True,
        selected_arrays_sha256=sha(prep/'selected_window_arrays.npz'),archive_window_manifest_sha256=sha(prep/'archive_windows.parquet'),
        selection_fixed_before_research=True,source_before_research_hash_receipt=str(prep/'input_manifest.jsonl')))
    def comp(contrast,scope,metric='delta_auc'):return trade[(trade.contrast==contrast)&(trade.scope==scope)&(trade.metric==metric)].iloc[0]
    primary=[]
    for contrast in ('P-U','P-B','U-B'):
        r=comp(contrast,'DO');primary.append(dict(비교=contrast,DO_AUC차이_pp=r.estimate*100,분위하한_pp=r.lower*100,분위상한_pp=r.upper*100,
            양의부모수=int(r.positive_parents),LOPO최소_pp=r.lopo_min*100,LOPO최대_pp=r.lopo_max*100))
    primary=pd.DataFrame(primary)
    task_table=cells.groupby(['task_id','arm']).agg(AUC=('auc','mean'),최종성공률=('J_64000','mean')).reset_index()
    task_table[['AUC','최종성공률']]*=100
    parent_table=parents[(parents.scope=='DO')&(parents.contrast.isin(['P-U','P-B','U-B']))].pivot(index='parent_id',columns='contrast',values='delta_auc')*100
    future_table=effects[(effects.scope=='DO')&(effects.contrast.isin(['P-U','P-B']))][['parent_id','future_id','contrast','delta_auc','delta_final']].copy()
    future_table[['delta_auc','delta_final']]*=100
    ret_table=ret.groupby(['task_id','arm']).agg(초기성공합=('initial_successes','sum'),최종성공합=('final_successes','sum'),획득합=('gain_cases','sum'),상실합=('loss_cases','sum'),G=('G','mean'),L=('L','mean')).reset_index()
    ret_table[['G','L']]*=100
    history_table=history.groupby(['task_id','arm'])[['gain_events','loss_events','recovery_events','histories_with_loss','histories_with_observed_recovery']].sum().reset_index()
    win['end_to_first_success_steps']=win.sigma-win.end
    win['includes_first_action']=(win.start==1).astype(int)
    content=win.groupby('arm').agg(에피소드수=('episode_id','size'),창시작평균=('start','mean'),첫성공까지평균잔여step=('end_to_first_success_steps','mean'),
        최초action포함창수=('includes_first_action','sum'),평균보상=('mean_reward','mean'),평균목표거리_m=('mean_goal_distance','mean'),평균접촉step=('related_endpoint_contact_steps','mean')).reset_index()
    do_geometry=episodes[episodes.task_id=='DO'].groupby(['arm','relative_train_step']).agg(
        에피소드수=('episode_id','size'),최소목표거리평균_mm=('minimum_goal_distance_m',lambda x:1000*x.mean()),
        최대목표진행평균_mm=('physical_goal_progress_max_m',lambda x:1000*x.mean()),최소joint평균_mm=('joint_min_m',lambda x:1000*x.mean())).reset_index()
    do_geometry.to_csv(analysis/'do_continuous_progress.csv',index=False)
    save(analysis/'effective_rng_streams.json',dict(
        planned_seed_manifest=str(prep/'seed_manifest.json'),
        effective_rules={
            'rollout_action':'keyed SHA256(pilot version, rollout_action stream seed, absolute env counter) mod(2**63-1); torch fork_rng restores learner RNG',
            'task_order':'new PCG64 state on original exhausted schedule; block/position/block count preserved',
            'reset_goal':'existing derived_seed(reset_goal role,20,task,original continued task_visit_index)',
            'native_replay':'legacy global NumPy RandomState seeded only from native_replay role; archive draws private',
            'learning_action':'original shared PyTorch actor/target stochastic update stream; separated from rollout using fork_rng',
            'archive_replacement':'independent private keyed PCG64 replacement/episode/offset fields per update and all256 slots',
            'evaluation':'original fixed per-case reset_seed/action_seed, isolated; newly derived future evaluation seed is unused',
            'logging_video':'deterministic frozen case IDs and frame stride; derived logging_video seed unused'},
        unused_planned_roles=['evaluation future-derived seed','logging_video seed'],no_claim_same_seed_same_trajectory=True))
    actual=load(campaign/'status.json');technical=Path(load(campaign/'campaign_config.json')['technical'])
    from compute_resources import summarize as summarize_resources
    resources=summarize_resources(campaign,technical,episodes,analysis)
    pu=comp('P-U','DO');pb=comp('P-B','DO');macro=comp('P-B','MACRO4');others=comp('P-B','OTHER3')
    ub=comp('U-B','DO')
    sign_details=[]
    for contrast in ('P-U','P-B'):
        subset=effects[(effects.scope=='DO')&(effects.contrast==contrast)]
        npos=int((subset.delta_auc>1e-12).sum());nzero=int((subset.delta_auc.abs()<=1e-12).sum());nneg=int((subset.delta_auc< -1e-12).sum())
        means=parents[(parents.scope=='DO')&(parents.contrast==contrast)]
        positive=means.loc[means.delta_auc>1e-12,'parent_id'].tolist();negative=means.loc[means.delta_auc< -1e-12,'parent_id'].tolist()
        sign_details.append(f"{contrast}: 미래별10개 대응값에서 양/0/음={npos}/{nzero}/{nneg}; 부모평균 양={positive}, 음={negative}.")
    if signal['status']=='nominal_pilot_signal_met':
        decision='정해 둔 목표·반복·보호 기준을 모두 충족했다. 같은 고정 선택 규칙의 후속 독립 확인을 제안할 파일럿 근거가 있다. 현재 규칙을 일반 우위 방법이나 기초동작으로 채택한 것은 아니다.'
    elif pu.estimate>=.02 and pb.estimate>=.02:
        decision='DO 평균 AUC는 두 비교에서 명목2%p 이상이지만 반복성 또는 다른 과제 보호 기준을 모두 충족하지 못했다. 현재 처치의 확대·개선 방법 채택은 보류하며, 충족하지 못한 기준과 부모별 반대 값을 먼저 보존한다.'
    elif abs(pu.estimate)<=1e-12 and abs(pb.estimate)<=1e-12:
        decision='두 주 비교의 DO AUC 점추정은0이다. 이 고정 detector·W32·대체율·예산·개발 패널에서는 onset 선택의 추가 가치와 순이익을 관측하지 못했다. 현재 처치의 확대는 보류한다. 모든 부모 값도0이면 bootstrap 범위는 퇴화할 수 있으며, 일반적인 효과 부재나 불확실성 부재를 뜻하지 않는다.'
    elif pu.estimate>0 and pb.estimate<0:
        decision='ONSET은 RANDOM_PRE보다 높은 점추정이지만 BASE보다 낮다. 현재 자료는 덜 불리한 개입의 가능성과 순이익을 구분하게 하며, 실제 개선 방법으로의 확대는 보류한다.'
    elif pu.estimate<=0 and ub.estimate>0:
        decision='RANDOM_PRE의 BASE 대비 점추정은 양수이지만 onset 선택의 추가 이득은 지지되지 않는다. 성공 이전 자료 재사용 자체와 onset 규칙의 가치를 구분하고, 이번 결과에서 승자를 골라 확인한 방법으로 제시하지 않는다. onset 경로 확대는 보류한다.'
    else:
        decision='두 주 비교와 반복성·보호 기준을 함께 보았을 때 명목 후속 신호 기준을 충족하지 못했다. 이 처치의 확대는 보류한다. 효과의 크기·부모/미래별 방향·분위 범위를 남기며 큰 연구 방향 전체의 부재를 주장하지 않는다.'
    discord=pd.read_csv(analysis/'paired_case_discordance.csv')
    exchanges=discord[(discord.contrast=='P-B')&(discord.initial_success==1)].groupby('task_id').agg(
        초기성공위험관측수=('risk_set_cases','sum'),추가상실_H=('reference_only','sum'),상실회피_B=('method_only','sum')).reset_index()
    other_summary=trade[(trade.contrast=='P-B')&(trade.metric=='delta_auc')][['scope','estimate','lower','upper']].copy()
    other_summary[['estimate','lower','upper']]*=100
    observations=[
        dict(id='source_support',observation='원 성공31개 중 적격25개, LOO25/20/20/16/19개',scope='existing DO training archive',scientific_effect='not measured by readiness',references=['source_success_episodes.parquet','onset_candidates_and_exclusions.parquet']),
        dict(id='onset_selection',observation=f'ONSET-RANDOM_PRE DO AUC {pu.estimate*100:+.4f}pp',estimate=pu.estimate,interval=[pu.lower,pu.upper],positive_parents=int(pu.positive_parents),references=['task_tradeoffs.csv','paired_effects_by_parent_future.csv'],limitations='fixed panel, overlapping LOO stores, one fixed random window'),
        dict(id='net_value',observation=f'ONSET-BASE DO AUC {pb.estimate*100:+.4f}pp',estimate=pb.estimate,interval=[pb.lower,pb.upper],positive_parents=int(pb.positive_parents),references=['task_tradeoffs.csv'],limitations='pre-existing archive conditional value, not source-inclusive convergence efficiency'),
        dict(id='tradeoffs',observation=f'ONSET-BASE four-task macro AUC {macro.estimate*100:+.4f}pp; other-three {others.estimate*100:+.4f}pp',references=['task_tradeoffs.csv','retention_gain_loss.csv'],limitations='not a noninferiority test')]
    (analysis/'phenomenon_register.jsonl').write_text(''.join(json.dumps(clean(x),ensure_ascii=False)+'\n' for x in observations),encoding='utf-8')
    qpath=BASE/'results/20261106T040755Z_initial_state_mapping_audit_44a7c57f'
    intro=f'''# DO 진행 시작 구간 재사용 파일럿 — 한국어 결과 보고서

## 1. 실제 완료 범위와 핵심 관측

본실험 30/30분기, 공통 시작 평가 5/5부모, 신규 평가 6,080/6,080에피소드를 완료했다. 신규 본학습은 네 과제 합계1,920,000전이이며 모든 분기는 같은 부모의 실제1M full 상태를 다시 복원했다. 81/82/84는 같은 과거 캠페인의 관측/사후분석이고, 이번85는 그 저장소를 활용한 새 추가학습 파일럿이다.

- 원 DO 성공31개에서 명목 검출기와 W32 경계를 통과한 적격25개를 확보했다. LOO별25/20/20/16/19개로 모든 준비 기준을 통과했다.
- DO AUC의 ONSET−RANDOM_PRE는 {pu.estimate*100:+.3f}%p, 부모 bootstrap 분위 범위 [{pu.lower*100:+.3f}, {pu.upper*100:+.3f}]%p다. 양의 부모는 {int(pu.positive_parents)}/5개다.
- ONSET−BASE는 {pb.estimate*100:+.3f}%p, 같은 범위 [{pb.lower*100:+.3f}, {pb.upper*100:+.3f}]%p다. 양의 부모는 {int(pb.positive_parents)}/5개다.
- 다른 세 과제 평균 AUC의 ONSET−BASE는 {others.estimate*100:+.3f}%p, 네 과제 macro는 {macro.estimate*100:+.3f}%p다.
- 사전 명목 운영 신호 판정: **{signal['status']}**. 이는 우위·일반화·방법 완성의 확증 판정이 아니다.

{decision}

{markdown(primary)}

위 범위는 부모5개의 구성 민감도를 나타내는 명목95% bootstrap 분위 범위다. 중첩된 고정 LOO 저장소와 기존 개발 패널에 조건화하며, 모집단95% 보장이나 독립 평가 사례 일반화를 뜻하지 않는다.

## 2. 기본 설정과 초기 좌표 매핑 정정

DO/DC/Push/BP의 기존 uniform 네 과제 SAC를 유지했다. 부모당 F01/F02, BASE/RANDOM_PRE/ONSET이며 분기64k는 네 과제 합계다. 원 batch256에서 DO slot만 독립 확률0.25로 archive 전이와 교체했다. 최종 같은 batch를 actor/critic/alpha가 사용했으며 별도 BC/KL, 추가 optimizer step, reward 변경, online replay 삽입, curriculum 및 상태 재시작은 없다. lr0.0003, gamma0.99, tau0.005, replay100k 및 원 timeout bootstrap을 유지했다.

처음에는 reset 반환 관측의 object X를 현재 물리 handle X로 사용해 적격9개로 계산했다. 이후 제외20개가 모두 첫 action의 X좌표 변화이고 joint는 사실상 정지한 점을 발견했다. 저장된 초기 물리 snapshot66개(평가16개, 사전 표집 훈련50개)의 모델 위치·integration qpos·고정 XML을 파일만으로 대조해, reset가 drawer 모델 X를 바꾼 뒤 반환 관측에는 이전 forward의 X가 남는 것을 확인했다. 원 관측을 실제 reset 물리 좌표와 혼동한 입력 매핑을 수정했다.

고정 slide의 실제 초기 handle은 `h0=goal+[0,0.19+q0,0]`이며 q0는 저장 reset Y와 XML에서 산술 복원했다. 실제 저장 reset qpos와의 최대 오차는9.365e-17m다. x1로 대체하지 않았으며 새 환경/forward를 실행하지 않았다. 명세가 허용한 단위·시점 매핑 오류 수정이고, 모든 문턱·창·원 obs/action/reward 및 이후 물리 표본은 유지했다. 수정 전 준비·독립 검산과 수정 근거는 별도 출력에 보존했다. 이 오류는 어떤 branch 학습 결과도 보기 전에 수정했다. 원81/82/84 보고서와 원 관측은 덮어쓰지 않았다.

과거 raw reset 거리 기준의 작은 진행에는 이 X 정렬 변화가 포함될 수 있어, 그것을 곧바로 drawer의 실제 개방 진행으로 읽지 않는다. 이번 DO 물리 진행 표는 위 산술 물리 x0 기준과 raw 관측 기준을 별도 열로 보존했다. 공식 성공 라벨은 변경하지 않았다.

같은 원1M 정책·사례의 신규 공통 +0 평가80회를 대조한 결과, 기존 raw reset 관측 기준5mm 진행은63/80, 물리적으로 일치하는 x0 기준은14/80이었다. 49회는 raw 기준에서만 진행으로 잡혔다. 따라서 이전63/80을 실제 서랍 진행의 빈도로 읽은 해석은 정정한다. 공식 성공0/80, 원 return/성공 라벨 및 원 보고서는 변하지 않는다. 정정 영수증은 campaign의 `verification/*_initial_geometry_*/correction_summary.json`과 개별80사례 표다.

실제로 적용한 난수 역할은 `effective_rng_streams.json`에 기록했다. rollout은 keyed PyTorch fork, native replay는 분리한 기존 NumPy 경로, learner actor/target action은 원 PyTorch update stream이다. 평가는 원 고정 case별 reset/action seed를 사용하고, 영상 표집은 고정 case와 stride를 따른다. 새로 파생해 둔 evaluation/logging seed는 이 결정론적 경로에서는 사용하지 않았다.

소스·좌표 정정 근거: `{qpath}`. 최신 유효 준비: `{prep}`. 기술 검증: `{technical}`. 모든 +0 평가의 성공·끝 성공·길이·return은 원1M 전체64사례와 정확히 일치했다.

## 3. 적격 자료와 무작위 대조의 내용

{markdown(counts)}

{markdown(ready[['parent_id','raw_LOO_successes','eligible_episodes','donor_runs_with_at_least_two','transitions_per_arm','mean_P_U_overlap_fraction']])}

검출 후보는 직전 joint 거의 정지, 첫 거리 감소, 8-action5mm 진행, 이후3개 표본에서2.5mm 이상 유지 및 joint 개방 방향 일치로 정의했다. 최초 후보 뒤 다른 후보로 바꾸지 않았다. 32전이는0.4초이며 전후 각16전이0.2초다. 대표 제외는 후보 없음2개와 창이 첫 공식 성공에 닿음4개다. 적격 자료만의 결과이며 느린/빠른/경계 진행 전체를 대표하지 않는다.

{markdown(content)}

같은 원 episode에 P/U 각각 고정 창 하나를 사용했다. U는 sigma 이전 창 시작점의 균일 추출이며 모든 prefix 전이의 동일 포함 확률을 뜻하지 않는다. P/U 중복은 허용하고 재추출하지 않았다. 부모별 donor 수와 시간·상태·행동·보상 분포가 함께 달라지는 선택 규칙 전체의 비교다. 원 성공 자료가 모든 현재 정책에 최적 행동이라는 가정은 하지 않았다.

고정 ID 정렬의 첫 대표 `R02:train:000251`은 선택된 초기 진행 뒤 다시 닫힌 위치 쪽으로 돌아갔다가, 이후의 더 큰 진행에서 첫 성공을 보인다(그림1). 따라서 이번 최초 onset가 항상 최종 성공으로 이어지는 마지막 진행의 시작인 것은 아니다. 이것만으로 해당 경험이 해롭거나 불필요하다고 판정하지 않으며, 성공 episode 내부에도 서로 다른 국소 경로가 포함된다는 내용상의 제한으로 남긴다. 이 사례를 이유로 episode를 제외하거나 다음 onset를 대신 선택하지 않았다.

## 4. 과제별 학습 곡선과 대응 효과

아래 AUC 및 최종 성공률은 %다. AUC는 [0.125,0.25,0.375,0.25] 가중이며 실제4시점 사이를 선형 연결한 요약이다.

{markdown(task_table)}

부모 안 두 미래, 이후 다섯 부모를 동일 가중했다. 부모별 DO AUC 차이(%p)는 다음과 같다.

{markdown(parent_table.reset_index())}

5부모×2미래의 모든 DO 대비(%p):

{markdown(future_table)}

{' '.join(sign_details)}

LOPO는 해당 receiver의 집계만 제외하며, 다른 receiver 저장소에 남아 있는 donor 자료까지 제거한 검증이 아니다. 부모 상태와 LOO 자료가 함께 달라지므로 차이를 출발 상태 하나의 원인으로 설명할 수 없다. 조건 차이에서 공통 +0 점수는 상쇄되며 시작 점수로 부모를 선택하지 않았다.

## 5. 다른 과제와 기존 성공의 유지·획득·상실

합계 분모는 각 task×arm의10개 부모×미래 패널, 160개의 대응 실행–사례 관측이다. 고유 물리 사례는 task당16개이고 독립 초기 학습기는5개다. G/L은 각 고정16사례를 분모로 한 평균 %p이며, 초기 성공 조건부 비율과 다르다.

{markdown(ret_table)}

ONSET−BASE의 task별 AUC 차이와 부모 bootstrap 분위 범위(%p):

{markdown(other_summary)}

초기 성공 중 BASE만 최종 성공한 추가 상실 H와 ONSET만 최종 성공한 상실 회피 B를 분리하면 다음과 같다. 이는 대응 실행–사례 합계이며 고유 물리 사례 수를 늘린 값이 아니다.

{markdown(exchanges)}

DO의 공통 시작 성공 수가0이면 초기 성공 유지/상실의 조건부 분모는0/NA다. 이를 능력 보존 성공으로 쓰지 않는다. DC/PU/BP 상실도 모두 보고했다. 여섯? 이번 사전 비교는 P−U/P−B/U−B 세 쌍이며 각 초기 성공/실패 집합의 양방향 불일치는 `paired_case_discordance.csv`에 모두 있다.

학습 checkpoint 사이 사건 수와 해당 이력 수:

{markdown(history_table)}

회복은 관측된 성공→실패 구간 후 재성공이며 영구 능력 회복이 아니다. 에피소드 내 목표 이탈과 학습 시점 사이 상실은 별도 열이다. 학습 시점 사이 정확한 발생 시점은 미측정이다. 소수 평가의 변화가 곧 영구 기능 소실을 뜻하지 않는다.

## 6. 노출 검산과 해석 범위

원 native draw와 교체 후 actual use를 구분했다. 같은 최종 batch의 actor/critic 사용은 각각1회이며 critic 두 개로 두 배 계산하지 않았다. P/U 대응 난수·교체 mask는 `paired_exposure_checks.csv`, 시점별 실제 누계와 출처는 `archive_usage_by_checkpoint.parquet`에 있다. 실제 학습 상태에서 관측된 loss/Q/alpha는 원 로그에 보존했고 새 진단 forward/backward는 하지 않았다.

DO의 연속 물리 진행 지표는 다음과 같다. 성공 여부는 이 평균값이나 반올림한 joint에서 역산하지 않고 원 공식 flag를 사용한다.

{markdown(do_geometry)}

정적 source/XML 기하에서 닫힌 handle–goal 거리는 약0.19m, slide joint 범위는[-0.16,0]m이며 명목 하한의 목표 거리는0.03m로 공식 성공 경계와 같다. 이는 완료 판정이 개방 끝 경계에 놓인다는 진단적 맥락이다. 실제 soft constraint와 endpoint 관측이 우선하며, 이 산술만으로 실패 원인이나 환경 오류를 확정하지 않는다.

물체 변화의 원인이 해당 action이라는 주장은 식별되지 않는다. onset의 위치, 상태 난도, 보상, 행동 내용 및 현재 정책과의 거리 등이 함께 달라질 수 있다. 구간 전이를 개별 표집했으므로 순서 학습이나 재사용 가능한 실행 스킬을 확인한 것이 아니다. 저장소 확보 비용을 이미 지불한 조건의 추가 재사용 가치이며, 종단 간 수렴 효율이나 다른 task의 보편적 선택 원리를 확인한 것도 아니다.

## 7. 운영 판정과 다음 결정

명목 기준의 개별 충족 여부:

{markdown(pd.DataFrame([dict(기준=k,충족=v) for k,v in signal['checks'].items()]))}

현재 다음 결정: {decision}

효과가 양수인 부모뿐 아니라 0·음수 부모/미래를 위 표에 모두 포함했다. 범위가0을 포함하는 것을 동등성·무해성으로 해석하지 않는다. 기준을 충족하더라도 고정 규칙의 후속 독립 확인을 검토할 신호이고, 충족하지 못했더라도 큰 연구 방향 전체의 부재를 뜻하지 않는다. 이번 검출기·W32·대체율0.25·1M 출발·64k 예산·고정 저장소/패널에서의 한계다.

후속을 자동 실행하지 않는다. 우선순위는 최대 다음3개다: (1) P−U와 P−B 및 다른 task의 손익을 함께 근거로 동일 고정 규칙을 새 학습 실행/미사용 초기조건에서 확인할 가치 판단, (2) 효과가 donor/receiver에 집중됐다면 자료 구성과 학습기 차이를 구분할 제한된 대조 설계, (3) 최초 진행과 이후 진행의 차이를 구분할 필요가 남는 경우에만 새로운 단일 대조를 별도 명세. 창·비중·seed sweep이나 새 모델은 이번 결과에 자동 추가하지 않는다.

## 8. 실제 비용·실패·저장·미측정

{markdown(totals.reset_index())}

신규 실제 issued/completed는 {new_issued:,}/{new_completed:,}, 총상한4,970,000, 잔여{4970000-new_issued:,}전이다. 기술/실패/재시도 공유10k 중 기술 {summary_cost['technical']:,}전이를 계상했다. 원 캠페인6,604,850은 추가 비용에 다시 넣지 않았으며 장부상 기존+신규 합계는{6604850+new_issued:,}다. archive 재사용 draw는 신규 환경 전이가 아니다. reset 내부 물리 계산·GPU kernel-only 시간은 환경 전이 수에 포함하지 않았으며 별도 미계측 항목이다. 프로세스 wall/CPU/메모리/I/O, checkpoint 저장 시간·크기와 최종 원자료 크기 목록은 실행/저장 영수증을 따른다.

정상 +0 및 본분기 큐의 실제 경과 시간은 {resources['normal_queue_elapsed_seconds']/3600:.3f}시간이다. 2개 작업을 병행했으며, 중첩되는 개별 작업 wall 합계는 {resources['normal_job_wall_seconds_sum']/3600:.3f}시간, 기록된 평가 에피소드 시간 합계는 {resources['recorded_evaluation_episode_wall_seconds_sum']/3600:.3f}시간이다. 이 시간들을 서로 더하지 않는다. GPU는 {', '.join(resources['gpu_devices'])}다. 호스트 프로세스별 최대 working set의 최대값은 {resources['max_individual_process_peak_working_set_bytes']/2**30:.3f}GiB이며 GPU VRAM이 아니다. 정상 작업의 OS I/O 읽기/쓰기 누계는 각각 {resources['normal_job_io_read_bytes_sum']/2**30:.3f}/{resources['normal_job_io_write_bytes_sum']/2**30:.3f}GiB다.

추가 full checkpoint {resources['full_checkpoint_writes']}회의 실제 저장 시간 합계는 {resources['full_checkpoint_write_seconds_sum']:.3f}초다. outer reset/환경 생성 및 step 호출 시간은 `compute_resources.json`, 개별 작업 wall/CPU/메모리/I/O는 `job_resource_costs.jsonl`에 수록했다. 평가 시간에는 영상과 I/O가 포함된다. 렌더링 단독 시간, GPU VRAM peak, kernel-only 시간, reset 내부 물리 계산량은 별도 분리 측정하지 않았다. 이 추가 집계도 저장 영수증만 읽었으며 환경/정책 실행은0이다.

4k마다 원 검증 형식의 추가 full 상태를 저장해 기술 여유 안에서 복구할 수 있는 경계를 확보했다. +16k/+32k light와 +64k full을 포함한다. 비검증 delta 형식을 도입하지 않았다. 기존 자료를 삭제하거나 덮어쓰지 않았다. 영상은 최종 정기 평가 중 원 패널의 과제별 사전2사례에만 붙이며 추가 rollout은 없다.

첫 ONSET 셀의 사전 고정4k full 상태는 양의 archive 사용 누계를 포함한 채 다시 로드해 전체 fingerprint 일치를 확인했다. 이 추가 저장 상태 검사는 정책 forward·환경 reset/step·학습 업데이트0이며, 실제 모델 로드1회와 계산 시간은 별도 영수증에 있다.

보조 파일 감사의 첫 시도에서는 현재 루트 AGENTS.md를 원81 당시 문서 hash와 동일해야 하는 런타임 자산처럼 검사해 실패했다. 이후 변경 가능한 작업 규칙/인덱스와 고정 구현·환경 자산을 구분해 차이를 기록했고, 원 참조463개의 구현·패키지 source·XML/mesh hash와 archive 행동 변환 검사를 통과했다. 이 파일 감사 실패와 수정 전 초기 좌표 준비 시도는 모두 보존했으며 신규 환경 비용은0이다. 이는 실패한 branch를 삭제하거나 seed를 바꾼 재실행이 아니다.

## 9. 재분석과 원본 참조

원 캠페인 `{CAMPAIGN}`. 새 캠페인 `{campaign}`. 고정 실행계획/seed/source는 그 루트, 원 branch 기록·체크포인트·평가 수치는 `jobs/<cell>/<attempt>`에 있다. 분석/검산은 파일 전용이며 모델 역직렬화·정책 forward·환경 reset/step·학습 업데이트 추가0이다.

재실행은 `analysis_tools/analyze.py --campaign <campaign>` → `analysis_tools/verify.py --analysis <new analysis>` → `analysis_tools/finalize.py --analysis <new analysis>` 순서다. 과거 결과를 덮어쓰지 않는 새 출력 ID가 필요하다. 코드·명세·입력 hash와 표/그림의 작은 ZIP을 제공하고, 대형 checkpoint·archive 원본·궤적·영상은 절대 경로와 hash로 연결한다.

참고 맥락: [Demo-SCORE](https://arxiv.org/html/2503.03707v2), [CUPID](https://proceedings.mlr.press/v305/agia25a.html), [SAC](https://arxiv.org/abs/1801.01290), [Meta-World 평가](https://metaworld.farama.org/evaluation/evaluation/). 자료 정제·replay 자체의 신규성을 주장하지 않으며 이 선행들의 완전 재현/대체 성능 비교도 아니다. 실행 권위는 실제 원 캠페인의 고정 코드/의존성/자산 hash다.
'''
    # Keep wording deterministic and remove a drafting marker before delivery.
    intro=intro.replace('여섯? 이번 사전 비교는','이번 사전 비교는')
    for c in captions:intro+='\n\n!['+c['caption']+']('+c['file']+')\n\n'+c['caption']+'\n'
    (analysis/'report_ko.md').write_text(intro,encoding='utf-8',newline='\n')
    (analysis/'readiness_report_ko.md').write_text('# 준비 결과\n\n'+markdown(counts)+'\n\n'+markdown(ready)+'\n\n초기 물리 좌표 매핑 수정 후 모든 receiver 자료 기준 통과. 원31성공→적격25. 기술4,900전이 통과. 수정 전 출력도 보존. 본문2절과 input manifest 참조.\n',encoding='utf-8')
    (analysis/'feature_mapping_and_detector.md').write_text('''# 물리 입력과 선택 규칙

- 원 환경 drawer-open-v3, reward v2. 공식 물체 기준점은 drawer_link world xpos+[0,-0.16,0] m.
- goal_slidey는 +world-Y slide joint, qpos/qvel 주소9. 개방 방향 s_goal=-1.
- reset 물리 h0는 goal+[0,0.19+q0,0]. q0는 저장 reset Y와 고정 XML에서 산술 복원하며 x1을 사용하지 않는다. raw reset X는 이전 forward 좌표로 남아 구분한다.
- t=1..L은 실제 action과 반환값. d_t=norm(h_t-goal), q_t는 같은 제어 endpoint의 저장 joint. 원 index와 원 정밀도를 유지한다.
- control_dt=.0125s=frame_skip5×physics_dt.0025s. W32=.4s, 전후16전이 각각.2s. 접촉은 endpoint 표본이고 필수 선택 조건이 아니다.
- 3점 중심 median은 offline detector에만 쓴다. 첫 tau 후보의 직전5점 joint 범위<=1mm, 첫 감소>=.1mm,8-action 진행>=5mm, 다음3점 각각>=2.5mm 유지, joint 방향 일치를 검사한다.
- 최초 후보가 부적격이면 다음 사건을 고르지 않는다. tau>=17, tau+15<sigma. 첫16 action의 실제 d0 대비5mm 진행은 제외한다. 32개 원 전이를 padding/연결/복제하지 않는다.
- U의 창 시작점은1..sigma-32 균일 정수, seed41031의 안정 SHA256/PCG64 파생. 공통 episode는 모든 receiver/future에서 같은 U 창을 사용한다. 중복을 허용한다.
- 원 obs43D와 task/goal, 실제 action, reward, next_obs와 timeout 처리 그대로다. 차원/구간을 위한 새 policy 입력이나 BC 손실은 없다.
- actual native/archive 사용량은 최종 batch 기준이며 원 native draw를 별도 기록한다. 최초 표집 후 교체된 native 전이는 실제 사용으로 세지 않는다.

전체 수치·예외 우선순위·seed·source hash는 protocol_resolved.json 및 preparation의 입력 영수증을 따른다. 평활과 이후 유지 확인은 온라인 관측 가능한 선택 신호가 아니다.
''',encoding='utf-8')
    evidence=dict(execution_status='complete',scientific_status=signal['status'],factor='fixed onset-centered successful DO pre-success replay selection',
        baselines=['BASE','RANDOM_PRE'],source_campaign=CAMPAIGN_ID,parent_ids=RUNS,original_seeds_reference=str(CAMPAIGN/'seed_manifest.json'),
        continuation_seeds_reference=str(prep/'seed_manifest.json'),effect_sizes=primary.to_dict('records'),uncertainty_scope=load(analysis/'bootstrap_summary.json')['confidence_scope'],
        actual_costs=summary_cost,unfavorable_inconclusive_findings_reference='all parent/future rows in paired_effects_by_parent_future.csv',
        limitations=['overlapping LOO archives','one fixed random window','old 16-case development panel','one starting step','selection rule not skill or causal action'],
        next_decision='No automatic expansion; nominal pilot signal and tradeoffs determine whether to propose independent confirmation')
    save(analysis/'candidate_factor_evidence_record.json',evidence)
    filelist=[]
    for p in sorted((campaign/'jobs').rglob('*')):
        if p.is_file() and 'source_snapshot' not in p.parts and p.name not in ('status.json','ACTIVE_ATTEMPT.json'):
            filelist.append(dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p)))
    (analysis/'large_artifact_references.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in filelist),encoding='utf-8')
    save(analysis/'storage_costs.json',dict(campaign_bytes=sum(r['bytes'] for r in filelist),files=len(filelist),
        checkpoint_schedules='every4k full;16k/32k light;64k full',raw_data_not_duplicated_in_bundle=True))
    with (analysis/'report_ko.md').open('a',encoding='utf-8') as report:
        report.write(f"\n\n원본 중복 압축 없이 참조하는 신규 job 산출물은 {len(filelist):,}개, 총 {sum(r['bytes'] for r in filelist)/2**30:.3f}GiB다. source_snapshot 중복과 캠페인 외부의 원 부모/archive는 이 합계에서 제외했다. 파일별 SHA256은 `large_artifact_references.jsonl`을 따른다.\n")
    bundle=analysis/'reproduction_bundle.zip'
    final={**status,'design_version':'85_onset_reuse_pilot_v1','scope':'fixed30-cell onset versus random-pre successful-DO replay pilot',
        'input_availability':dict(original_full_parents=5,original_successful_DO_episodes=31,eligible_DO_episodes=25,physical_evaluation_cases=64),
        'readiness':dict(all_five_receivers_passed=True,LOO_eligible_counts=[25,20,20,16,19],technical_passed=True),
        'completed_parents':5,'actual_issued':new_issued,'actual_completed':new_completed,
        'actual_train_steps':int(totals.loc['train','completed']),
        'actual_eval_steps':int(totals.loc['start_eval','completed']+totals.loc['post_eval','completed']),
        'actual_technical_steps':summary_cost['technical'],'budget_remaining':4970000-new_issued,
        'operational_signal_status':signal['status'],
        'report':str(analysis/'report_ko.md'),'figures':str(analysis/'figures'),'bundle':str(bundle),'costs':summary_cost,
        'report_ready_wall_seconds':time.perf_counter()-started,'verification':str(verification),'source_preparation':str(prep),
        'interpretation_limits':evidence['limitations'],'algorithm_failures':0,'missing_or_invalid':0}
    # Package the same final scientific/cost status that is delivered on disk.
    # Publish the campaign completion marker only after the bundle is durable.
    save(analysis/'FINAL_STATUS.json',final,replace=True)
    with zipfile.ZipFile(bundle,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for p in analysis.rglob('*'):
            if p.is_file() and p!=bundle and '.mplconfig' not in p.parts:
                z.write(p,p.relative_to(analysis).as_posix())
        for name in ['protocol_resolved.json','seed_manifest.json','state_manifest.json','loo_archive_manifest.json','archive_windows.parquet','source_success_episodes.parquet','onset_candidates_and_exclusions.parquet','input_manifest.jsonl']:
            z.write(prep/name,'preparation/'+name)
        z.write(prep/'selected_window_arrays.npz','preparation/selected_window_arrays.npz')
        z.write(campaign/'research_source_hashes.json','research_source_hashes.json')
        z.write(campaign/'execution_plan.csv','execution_plan.csv')
        z.write(campaign/'campaign_config.json','campaign_config.json')
        for p in (campaign/'source_snapshot').rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts:z.write(p,'research_source/'+p.relative_to(campaign/'source_snapshot').as_posix())
        for name in ['technical_checks.json','FINAL_STATUS.json']:
            z.write(technical/name,'technical/'+name)
        for name in ['mapping_conclusion.json','reset_physical_coordinate_mapping.csv']:
            z.write(qpath/name,'initial_mapping_audit/'+name)
        for name in ['seed_manifest.json','baseline_manifest.json','config_resolved.json','technical_certification.json']:
            z.write(CAMPAIGN/name,'original81/'+name)
        z.write(CAMPAIGN/'evaluation_cases/feature_schema_DO.json','original81/feature_schema_DO.json')
    save(analysis/'reproduction_receipt.json',dict(bundle=str(bundle),bytes=bundle.stat().st_size,sha256=sha(bundle)))
    save(analysis/'finalization_costs.json',dict(wall_seconds=time.perf_counter()-started,
        bundle_bytes=bundle.stat().st_size,new_environment_transitions=0,new_policy_forwards=0,new_learning_updates=0))
    save(campaign/'FINAL_STATUS.json',final,replace=True)
    save(BASE/'LATEST.json',dict(campaign=str(campaign),analysis=str(analysis),report=final['report'],bundle=str(bundle),status='complete',signal_status=signal['status']),replace=True)
    print(json.dumps(dict(report=final['report'],new_steps=new_issued,operational_signal=signal['status'])),flush=True)

if __name__=='__main__':main()
