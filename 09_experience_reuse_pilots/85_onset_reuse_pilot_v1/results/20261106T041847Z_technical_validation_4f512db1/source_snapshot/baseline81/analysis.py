"""Exploratory, file-only summaries with all runs and contrary observations."""
from __future__ import annotations
import itertools
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
import zipfile
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from records import ROOT, load, save, sha, ref, utc, append

TASKS=('DO','DC','PU','BP')

def read_parts(path,columns=None):
    files=sorted(Path(path).glob('part_*.parquet'))
    return pd.concat([pd.read_parquet(p,columns=columns) for p in files],ignore_index=True) if files else pd.DataFrame()

def markdown(frame,digits=2):
    if frame.empty:return '미측정: 유효 자료 없음.'
    columns=list(frame.columns)
    lines=['| '+' | '.join(map(str,columns))+' |','| '+' | '.join(['---']*len(columns))+' |']
    for row in frame.itertuples(index=False,name=None):
        values=[]
        for x in row:
            if pd.isna(x):values.append('NA')
            elif isinstance(x,(float,np.floating)):values.append(f'{x:.{digits}f}')
            else:values.append(str(x))
        lines.append('| '+' | '.join(values)+' |')
    return '\n'.join(lines)

def behavior(episodes):
    rows=[]
    for _,e in episodes.iterrows():
        path=e.get('trajectory_ref')
        if not isinstance(path,str) or not Path(path).exists():continue
        with np.load(path,allow_pickle=False) as z:
            success=z['success_step'].astype(int);action=z['action_executed'];obj=z['object_pos'];tcp=z['tcp']
            losses=int(np.sum((success[:-1]==1)&(success[1:]==0)))
            reacquisitions=0;seen=False;last=False
            for s in success:
                if s and not last and seen:reacquisitions+=1
                seen=seen or bool(s);last=bool(s)
            rows.append({'run_id':e['run_id'],'task_id':e['task_id'],'split_role':e['split_role'],
                'checkpoint_id':e.get('checkpoint_id'),'episode_id':str(e['episode_id']),
                'initial_case_id':e.get('initial_case_id'),'env_step_total':e.get('end_env_step',e.get('checkpoint_id')),
                'success_any':int(success.any()),'success_final':int(success[-1]),'success_step_fraction':float(success.mean()),
                'within_episode_success_exits':losses,'within_episode_observed_reentries':reacquisitions,
                'min_tcp_object_distance':float(z['tcp_object_distance'].min()),
                'min_object_goal_distance':float(z['object_goal_distance'].min()),
                'final_object_goal_distance':float(z['object_goal_distance'][-1]),
                'mean_action_norm':float(np.linalg.norm(action,axis=1).mean()),
                'action_saturation_fraction':float((np.abs(action)>.95).mean()),
                'mean_gripper_command':float(action[:,-1].mean()),
                'tcp_path_length':float(np.linalg.norm(np.diff(tcp,axis=0),axis=1).sum()),
                'object_path_length':float(np.linalg.norm(np.diff(obj,axis=0),axis=1).sum()),
                'endpoint_contact_fraction':float((z['robot_object_contact_pairs']>0).mean()),
                'trajectory_ref':path})
    return pd.DataFrame(rows)

def analyze(campaign,partial=False):
    campaign=Path(campaign);started=time.perf_counter()
    out=campaign/'analysis'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:6]);out.mkdir(parents=True,exist_ok=False)
    shutil.copy2(ROOT/'analysis.py',out/'analysis_source.py');shutil.copy2(ROOT/'verify_analysis.py',out/'verification_source.py')
    protocol=load(campaign/'protocol.json');runs=protocol['runs'];evals=[];trains=[];updates=[];usage_rows=[];completion=[]
    for rid in runs:
        p=campaign/'runs'/rid
        completion.append({'run_id':rid,'completed':(p/'COMPLETE.json').exists(),'failed':(p/'FAILED.json').exists()})
        e=read_parts(p/'evaluation_episodes')
        if not e.empty:evals.append(e)
        t=read_parts(p/'episodes')
        if not t.empty:trains.append(t)
        u=read_parts(p/'update_scalars')
        if not u.empty:
            u['window_end']=((u.env_step_total-1)//10000+1)*10000
            columns=[c for c in ('actor_loss','critic_loss','alpha_after','q1_mean','q2_mean','target_q_mean','actor_gradient_norm','critic_gradient_norm') if c in u]
            agg=u.groupby('window_end')[columns].mean().reset_index();agg['run_id']=rid;agg['updates']=u.groupby('window_end').size().values
            updates.append(agg);del u
        evicted=read_parts(p/'replay_usage/evicted');active=read_parts(p/'replay_usage/final_active')
        life=pd.concat([x for x in (evicted,active) if not x.empty],ignore_index=True) if not evicted.empty or not active.empty else pd.DataFrame()
        if not life.empty:
            if life.transition_id.duplicated().any():raise RuntimeError('Replay lifetime IDs duplicated')
            life['collection_window']=((life.collection_env_step-1)//100000).astype(int)
            for (task,window),g in life.groupby(['source_task_id','collection_window']):
                usage_rows.append({'run_id':rid,'task_id':task,'collection_window':int(window),'transitions':len(g),
                    'critic_uses':int(g.critic_sample_count.sum()),'actor_uses':int(g.actor_sample_count.sum()),
                    'never_sampled':int((g.critic_sample_count==0).sum()),'never_sampled_fraction':float((g.critic_sample_count==0).mean()),
                    'uses_mean':float(g.critic_sample_count.mean()),'uses_median':float(g.critic_sample_count.median()),
                    'uses_q95':float(g.critic_sample_count.quantile(.95)),'uses_max':int(g.critic_sample_count.max()),
                    'active_censored':int(g.active_censored.sum())})
            del life
    complete=pd.DataFrame(completion);complete.to_csv(out/'run_completion.csv',index=False)
    evaluation=pd.concat(evals,ignore_index=True) if evals else pd.DataFrame()
    training=pd.concat(trains,ignore_index=True) if trains else pd.DataFrame()
    if not evaluation.empty:
        keys=['run_id','task_id','initial_case_id','physical_case_id','checkpoint_id']
        if evaluation.duplicated(keys).any():raise RuntimeError('Duplicate evaluation keys')
        evaluation.to_parquet(out/'per_case_results.parquet',index=False)
        metrics=evaluation.groupby(['run_id','task_id','checkpoint_id']).agg(
            completed_episodes=('success_any','size'),success_any_rate=('success_any','mean'),
            success_final_rate=('success_final','mean'),return_mean=('episode_return','mean'),
            length_mean=('episode_length','mean'),first_success_median=('first_success_step','median')).reset_index()
        metrics['planned_episodes']=16;metrics.to_csv(out/'cell_metrics.csv',index=False)
        paired=[];histories=[]
        for (rid,task,case,physical),g in evaluation.groupby(['run_id','task_id','initial_case_id','physical_case_id']):
            d={int(r.checkpoint_id):int(r.success_any) for r in g.itertuples()}
            histories.append({'run_id':rid,'task_id':task,'initial_case_id':case,'physical_case_id':physical,
                'history':''.join(str(d[s]) if s in d else '?' for s in protocol['evaluation_steps']),
                'observations':len(d)})
        pd.DataFrame(histories).to_csv(out/'case_success_histories.csv',index=False)
        for rid,task in itertools.product(runs,TASKS):
            g=evaluation[(evaluation.run_id==rid)&(evaluation.task_id==task)]
            for a,b in zip(protocol['evaluation_steps'][:-1],protocol['evaluation_steps'][1:]):
                left=g[g.checkpoint_id==a].set_index(['initial_case_id','physical_case_id'])['success_any']
                right=g[g.checkpoint_id==b].set_index(['initial_case_id','physical_case_id'])['success_any']
                common=left.index.intersection(right.index);x=left.loc[common].to_numpy();y=right.loc[common].to_numpy();n=len(common)
                counts=[int(np.sum((x==u)&(y==v))) for u,v in ((1,1),(1,0),(0,1),(0,0))]
                row={'run_id':rid,'task_id':task,'checkpoint_from':a,'checkpoint_to':b,'planned_cases':16,'valid_pairs':n,
                    'retained_11':counts[0],'observed_loss_10':counts[1],'observed_gain_01':counts[2],'failed_00':counts[3],
                    'J_from':float(x.mean()) if n else None,'J_to':float(y.mean()) if n else None,
                    'G':counts[2]/n if n else None,'L':counts[1]/n if n else None}
                if n and abs(row['J_to']-row['J_from']-row['G']+row['L'])>1e-12:raise RuntimeError('Gain/loss identity')
                paired.append(row)
        pd.DataFrame(paired).to_csv(out/'paired_case_transitions.csv',index=False)
    else:metrics=pd.DataFrame();paired=[]
    if not training.empty:training.to_parquet(out/'training_episodes.parquet',index=False)
    upd=pd.concat(updates,ignore_index=True) if updates else pd.DataFrame();upd.to_csv(out/'learning_update_time_alignment.csv',index=False)
    usage=pd.DataFrame(usage_rows);usage.to_csv(out/'replay_collection_usage.csv',index=False)
    all_ep=pd.concat([x for x in (training,evaluation) if not x.empty],ignore_index=True) if not training.empty or not evaluation.empty else pd.DataFrame()
    beh=behavior(all_ep) if not all_ep.empty else pd.DataFrame()
    if not beh.empty:beh.to_parquet(out/'episode_behaviour.parquet',index=False)
    figures=out/'figures';figures.mkdir()
    if not metrics.empty:
        fig,axes=plt.subplots(2,2,figsize=(12,8),sharex=True,sharey=True)
        for ax,task in zip(axes.flat,TASKS):
            for rid in runs:
                g=metrics[(metrics.task_id==task)&(metrics.run_id==rid)].sort_values('checkpoint_id')
                ax.plot(g.checkpoint_id/1000,g.success_any_rate*100,marker='.',label=rid,alpha=.8)
            ax.set_title(task);ax.set_ylim(-3,103);ax.set_ylabel('Success (%)');ax.set_xlabel('Training transitions (k)');ax.grid(alpha=.2)
        axes[0,0].legend(ncol=3);fig.tight_layout();fig.savefig(figures/'learning_curves.png',dpi=150);plt.close(fig)
        fig,axes=plt.subplots(1,4,figsize=(15,13),sharey=True)
        for ax,task in zip(axes,TASKS):
            g=evaluation[evaluation.task_id==task].copy();g['row']=g.run_id+'/'+g.initial_case_id
            mat=g.pivot(index='row',columns='checkpoint_id',values='success_any').reindex(columns=protocol['evaluation_steps'])
            ax.imshow(mat,aspect='auto',vmin=0,vmax=1,cmap='RdYlGn',interpolation='nearest');ax.set_title(task)
            ax.set_xticks(range(10),[str(s//1000) for s in protocol['evaluation_steps']],rotation=90);ax.set_xlabel('Training (k)')
        axes[0].set_ylabel('All run/case pairs (5 x 16)');fig.tight_layout();fig.savefig(figures/'case_history_map.png',dpi=150);plt.close(fig)
        fig,axes=plt.subplots(2,2,figsize=(12,8))
        for ax,task in zip(axes.flat,TASKS):
            for rid in runs:
                g=metrics[(metrics.task_id==task)&(metrics.run_id==rid)]
                ax.plot(g.checkpoint_id/1000,100*(g.success_any_rate-g.success_final_rate),marker='.',label=rid)
            ax.set_title(task);ax.set_ylabel('Any success - final success (pp)');ax.set_xlabel('Training (k)');ax.grid(alpha=.2)
        fig.tight_layout();fig.savefig(figures/'within_episode_success_departure.png',dpi=150);plt.close(fig)
    if not usage.empty:
        fig,axes=plt.subplots(1,2,figsize=(12,4))
        for task in TASKS:
            g=usage[usage.task_id==task].groupby('collection_window')[['uses_mean','never_sampled_fraction']].mean()
            axes[0].plot((g.index+1)*100,g.uses_mean,marker='.',label=task)
            axes[1].plot((g.index+1)*100,g.never_sampled_fraction*100,marker='.',label=task)
        axes[0].set_ylabel('Mean critic uses per transition');axes[1].set_ylabel('Never sampled (%)')
        for ax in axes:ax.set_xlabel('Collection window end (k)');ax.legend();ax.grid(alpha=.2)
        fig.tight_layout();fig.savefig(figures/'replay_usage.png',dpi=150);plt.close(fig)
    if not upd.empty:
        fig,axes=plt.subplots(3,1,figsize=(11,9),sharex=True)
        for rid in runs:
            g=upd[upd.run_id==rid]
            for ax,col in zip(axes,('alpha_after','q1_mean','actor_loss')):ax.plot(g.window_end/1000,g[col],label=rid);ax.set_ylabel(col);ax.grid(alpha=.2)
        axes[0].legend(ncol=5);axes[-1].set_xlabel('Training transitions (k)');fig.tight_layout();fig.savefig(figures/'learning_statistics.png',dpi=150);plt.close(fig)
    from campaign import summarize_costs
    costs=summarize_costs(campaign)
    save(out/'costs.json',{**costs,'analysis_seconds_so_far':time.perf_counter()-started,
        'disk_bytes_campaign':sum(p.stat().st_size for p in campaign.rglob('*') if p.is_file()),
        'units':'steps, wall seconds, reset counts and bytes reported separately; no mixed-unit sum'})
    # Independent per-case arithmetic, not a second statistical sample.
    verify=subprocess.run([sys.executable,'-B',str(ROOT/'verify_analysis.py'),'--campaign',str(campaign),'--analysis',str(out)],capture_output=True,text=True)
    (out/'verification_stdout.log').write_text(verify.stdout+'\n'+verify.stderr,encoding='utf-8')
    if verify.returncode:partial=True
    findings=[]
    if not metrics.empty:
        for task in TASKS:
            g=metrics[(metrics.task_id==task)&(metrics.checkpoint_id==1000000)]
            findings.append({'phenomenon_id':'final_'+task,'execution_status':'measured' if len(g)==5 else 'partial',
                'observation':'original-initial-distribution performance on fixed observation panel',
                'task':task,'completed_runs':len(g),'success_mean':float(g.success_any_rate.mean()) if len(g) else None,
                'run_min':float(g.success_any_rate.min()) if len(g) else None,'run_max':float(g.success_any_rate.max()) if len(g) else None,
                'scope':'five fresh learning runs, shared sixteen physical cases for this task; exploratory',
                'contrary_cases':'all run/case histories and all checkpoint transitions retained',
                'competition':'policy, task difficulty, physical-case composition, learning randomness and replay exposure not causally separated',
                'next_confirmation':'only after a concrete pattern is identified; no follow-on method or run auto-selected'})
    save(out/'phenomenon_register.json',{'status':'exploratory_observation','entries':findings,
        'predefined_method_selected':False,'causal_mechanism_identified':False,'evidence_for_primitive_skill':'unmeasured',
        'all_paired_changes':'paired_case_transitions.csv','all_behavior_changes':'episode_behaviour.parquet',
        'posthoc_scope':'descriptive inspection only; no classifier, weight search or new model fitted'})
    report=['# 기본 SAC 관측 캠페인 보고서',
        '\n## 1. 실제 완료 범위와 핵심 관측\n',
        f"정상 완료 실행 {int(complete.completed.sum())}/5. 정기 평가 완료 {len(evaluation):,}/3,200 에피소드. "
        f"실제/보수적 계상 환경 전이 {costs['all_attempt']:,}/6,710,000. "+('일부 미완료·결측이 있으며 아래 범위로 한정한다.' if partial else '예정한 관측을 정상 완료했다.'),
        '\n이 캠페인은 하나의 기본 SAC 조건을 관측한다. 특정 방법의 우월성, 재시작 선택 효용, 공유 기초동작, 원인 또는 논문 기여를 확정하지 않는다. 성공률과 현상 발견 여부는 완료 조건이 아니다.',
        '\n'+markdown(complete),
        '\n## 2. 기본 설정과 평가·기록 규약\n',
        'Meta-World 3.0.0의 drawer-open-v3, drawer-close-v3, push-v3, button-press-v3; 보상은 v2. PU는 Push다. '
        '39개 환경 관측을 float32로 변환하고 4개 과제 one-hot을 붙인 43차원 정책 입력, 정규화 4차원 행동이다. '
        '분리된 actor와 double critic의 256/256 ReLU MLP, Adam, 학습률 0.0003, batch 256, replay 100,000, gamma 0.99, tau 0.005, 자동 entropy를 유지했다. '
        '과제별 head가 없는 공통 과제조건부 정책이다. 8에피소드 블록마다 과제별 두 에피소드를 독립 난수로 섞고, 에피소드당 500 전이를 수집한다. '
        'warm-up 1,000도 총량에 포함하며 이후 전이당 한 번의 stock SAC 업데이트를 수행한다. 총길이 의존 스케줄은 없다.',
        '\n각 과제 16개, 총 64개 물리 초기조건을 정책 결과 관측 전에 동결했다. 5개 독립 초기학습과 3,200개 반복 평가를 독립 표본으로 혼동하지 않는다. '
        '표준 MT10/MT50 전체 goal 평가가 아니다. 평가는 deterministic CUDA이며 최초 성공에서 중단하지 않고 원래 환경의 500-step truncation까지 기록한다. '
        '평가에서 학습·replay 삽입·정규화 갱신은 없다. autoreset은 사용하지 않는다. timeout bootstrap은 원래 구현을 유지한다.',
        '\n## 3. 과제별·실행별 결과\n']
    if not metrics.empty:
        final=metrics[metrics.checkpoint_id==1000000][['run_id','task_id','completed_episodes','success_any_rate','success_final_rate','return_mean']].copy()
        for col in ('success_any_rate','success_final_rate'):final[col]*=100
        report+=['최종 성공률의 단위는 %이며 각 실행·과제 분모는 표에 명시한다.\n',markdown(final),
            '\n![과제별 학습 곡선](figures/learning_curves.png)',
            '\n전체 시점과 미완료 범위는 cell_metrics.csv에 있다. CI는 이번 요약에서 계산하지 않았다. 개별 실행과 고정 패널에 대한 기술 결과이며 새 seed·새 goal 모집단의 보장으로 해석하지 않는다.']
    else:report+=['기술 검증 또는 준비 단계에서 중단되어 본학습 성능은 미측정이다.']
    report+=['\n## 4. 사례별 행동 변화\n']
    if paired:
        pairs=pd.DataFrame(paired);valid=pairs[pairs.valid_pairs>0]
        summary=valid.groupby('task_id').agg(valid_case_pair_observations=('valid_pairs','sum'),observed_gains=('observed_gain_01','sum'),observed_losses=('observed_loss_10','sum')).reset_index()
        report+=[markdown(summary), '\n위 건수는 같은 물리 사례의 반복 관측이며 고유 사례 수가 아니다. 모든 인접 시점에서 J 차이=획득−상실을 검산했다. '
            '한 번의 1→0을 영구 능력 소실로 부르지 않는다. 평가 사이의 정확한 최초 상실·회복 시점은 미측정이다.',
            '\n![공통 사례 이력](figures/case_history_map.png)']
    if not beh.empty:
        ev=beh[beh.split_role=='observation_eval'];departure=ev.groupby('task_id').agg(episodes=('success_any','size'),any_success=('success_any','sum'),any_but_not_final=('success_final',lambda x:0)).reset_index()
        departure['any_but_not_final']=[int(((ev.task_id==t)&(ev.success_any==1)&(ev.success_final==0)).sum()) for t in departure.task_id]
        report+=['\n에피소드 내 원시 성공 상태 이탈은 학습 시점 간 상실과 별도로 집계했다.\n',markdown(departure),
            '\n성공 이후 기록 가능한 범위에서의 실제 관측이다. 접촉은 제어 step 끝의 표본이며 중간 물리 substep 전체의 접촉을 측정한 것이 아니다.',
            '\n![에피소드 내 성공과 종점](figures/within_episode_success_departure.png)']
    report+=['\n## 5. 경험 사용과 학습 통계\n']
    if not usage.empty:
        agg=usage.groupby('task_id')[['transitions','critic_uses','actor_uses','never_sampled','active_censored']].sum().reset_index()
        report+=[markdown(agg),'\n각 critic_sample_count는 두 Q망을 사용하는 한 critic 업데이트 배치에서의 사용 횟수다. actor가 같은 배치를 실제 사용한 횟수는 별도 기록했다. '
            '활성 replay 항목의 사용량은 종료 시점에서 우측 절단된다. 250번째 배치 ID와 누적 횟수만으로 모든 배치를 복원했다고 주장하지 않는다.',
            '\n![경험 수집·사용](figures/replay_usage.png)']
    if not upd.empty:report+=['\n![학습 통계](figures/learning_statistics.png)',
        '\nloss·Q·alpha·gradient norm은 진단값이며 성공 보존이나 수행 능력의 대리 정답이 아니다. 원본 업데이트 스칼라는 각 실행 update_scalars, 분포는 update_summaries에 있다.']
    report+=['\n## 6. 반복 현상과 경쟁 설명\n',
        'phenomenon_register.json은 관측 범위와 경쟁 설명을 분리한다. 과제·seed 차이, 동일 사례의 성공 교체, 에피소드 내 성공 이탈, replay 사용의 수집 시기 차이를 각각 확인할 수 있다. '
        '전체 표와 반대·무변화 사례를 보존하며, 평균 개선만으로 공통 기초동작이나 특정 경험의 인과적 유용성을 선언하지 않는다. '
        '이 단계에서 예측 가능한 조건이나 개선 방법을 확보했다고 판정하지 않는다.',
        '\n## 7. 추가 진단\n',f"추가 진단 환경 전이: {costs['optional_diagnostic']:,}. 잔여 예산은 자동 소진하지 않았다. 진단 계획은 캠페인 diagnostic_plan.jsonl에 있다.",
        '\n## 8. 비용·기술 한계·미측정\n',
        f"본학습 {costs['train']:,}/5,000,000; 정기 평가 {costs['evaluation']:,}/1,600,000; 기술·무효·재시도 {costs['technical_invalid_retry']:,}/10,000; 추가 진단 {costs['optional_diagnostic']:,}/100,000. "
        f"완료가 확인되지 않은 issued 전이 {costs['uncertain_issued']:,}건도 보수적으로 상한에 계상했다.",
        '\n환경 전이는 실제 개별 환경의 action step이며 reset 내부 물리 계산과 구분한다. reset 횟수는 기술·평가 영수증과 각 실행 비용에 기록했다. '
        'reset 내부 solver/kernel 시간은 별도 직접 측정하지 않았다. GPU job 경과 시간은 kernel-only 시간으로 해석하지 않는다. '
        '분포 요약은 원래 텐서에서 추가 표집·backward 없이 계산했다. policy 행동의 sampled log probability는 기존 collection predict 경로에서 계산되지 않아 필수 전이 로그에 임의 생성하지 않았다.',
        '\n환경 snapshot은 technical_certification.json의 검증 범위로 제한한다. 그 범위를 벗어난 snapshot은 diagnostic_state이며 검증된 재시작 능력으로 부르지 않는다. '
        'light는 전체 재개용이 아니며 full은 완료 episode 뒤 일관된 학습 경계에서 model/replay/collector/RNG를 함께 저장했다.',
        '\n## 9. 후속 질문 후보\n',
        '반복 성공·실패 교체가 어떤 상태·행동 구간에서 나타나는가, 경험의 수집과 사용 시차가 실제 행동 변화와 어떻게 대응하는가를 현재 기록에서 더 좁힐 수 있다. '
        '상관만으로 원인을 정하거나 새 방법을 채택하지 않는다. 재시작, 복귀, 경험 선택, 스킬 발견은 이번에 실행·검증한 방법이 아니다. '
        '구체적인 관찰과 경쟁 설명을 구분할 필요가 생겼을 때만 별도 후속 명세를 작성한다.',
        '\n## 재분석 안내\n',
        'baseline_manifest/config_resolved/input_receipt/seed_manifest/protocol은 캠페인 루트에 있다. 원본 전이는 runs/Rxx의 training_transitions와 evaluation_transitions, '
        '영상은 videos, snapshot과 checkpoint는 해당 디렉터리에 있다. NPZ sidecar JSON에 원본 해시와 공통 식별자를 연결했다. '
        '정규화·좌표·시점·상태 지위는 schema 및 evaluation_cases의 feature_schema에 있다. 대형 원본은 재현 ZIP에 중복 포함하지 않는다.']
    if (campaign/'TECHNICAL_FAILED.json').exists():report+=['\n기술 장애 원문:\n\n'+load(campaign/'TECHNICAL_FAILED.json').get('error','상세 기술 영수증 참조')]
    (out/'report_ko.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
    # Stable references for all immutable large artifacts, without duplicating payloads.
    manifest=out/'artifact_hashes.jsonl'
    with manifest.open('x',encoding='utf-8') as f:
        for p in campaign.rglob('*'):
            if p.is_file() and out not in p.parents and p.name not in ('RUNNING_STATUS.md','status.json'):
                f.write(json.dumps(ref(p),ensure_ascii=False)+'\n')
    bundle=out/'reproduction_bundle.zip'
    with zipfile.ZipFile(bundle,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for p in out.rglob('*'):
            if p.is_file() and p!=bundle:z.write(p,'analysis/'+p.relative_to(out).as_posix())
        for p in (campaign/'source_snapshot').rglob('*'):
            if p.is_file():z.write(p,'source_snapshot/'+p.relative_to(campaign/'source_snapshot').as_posix())
        for name in ('protocol.json','baseline_manifest.json','config_resolved.json','seed_manifest.json','input_receipt.json','technical_certification.json','diagnostic_plan.jsonl'):
            p=campaign/name
            if p.exists():z.write(p,name)
    save(out/'COMPLETE.json',{'status':'partial' if partial else 'observations_completed','report':ref(out/'report_ko.md'),
        'bundle':ref(bundle),'completed_runs':int(complete.completed.sum()),'evaluation_episodes':len(evaluation),
        'costs':costs,'analysis_wall_seconds':time.perf_counter()-started,'new_analysis_environment_steps':0,
        'independent_arithmetic_verification_passed':verify.returncode==0})
    save(campaign/'LATEST_ANALYSIS.json',{'analysis':str(out),'report':ref(out/'report_ko.md'),'bundle':ref(bundle)},replace=True)
    save(campaign/'FINAL_STATUS.json',load(out/'COMPLETE.json'))
    return out

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--campaign',type=Path,required=True);p.add_argument('--partial',action='store_true');a=p.parse_args();print(analyze(a.campaign,a.partial))
