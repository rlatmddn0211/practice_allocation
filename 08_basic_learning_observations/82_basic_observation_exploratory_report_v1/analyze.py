"""File-only observational synthesis; no policy/environment imports or execution."""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import uuid
import zipfile
import importlib.metadata
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
TASKS=['DO','DC','PU','BP']
def utc():return datetime.now(timezone.utc).isoformat()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def ref(p):return {'path':str(Path(p).resolve()),'sha256':sha(p),'bytes':Path(p).stat().st_size}
def save(p,x,replace=False):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists() and not replace:raise FileExistsError(p)
    tmp=p.with_name(p.name+'.partial');tmp.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8');os.replace(tmp,p)
def parts(path,columns=None):
    files=sorted(Path(path).glob('part_*.parquet'))
    return pd.concat([pd.read_parquet(p,columns=columns) for p in files],ignore_index=True) if files else pd.DataFrame()
def table(df):
    if df.empty:return '미측정: 유효 자료 없음.'
    rows=['| '+' | '.join(map(str,df.columns))+' |','| '+' | '.join(['---']*len(df.columns))+' |']
    for values in df.itertuples(index=False,name=None):
        cells=[]
        for v in values:
            if pd.isna(v):cells.append('NA')
            elif isinstance(v,(float,np.floating)):cells.append(f'{v:.3f}')
            else:cells.append(str(v))
        rows.append('| '+' | '.join(cells)+' |')
    return '\n'.join(rows)

def analyze(campaign,output=None):
    campaign=Path(campaign);started=time.perf_counter()
    fixture=(campaign/'FIXTURE_ONLY.json').exists()
    out=Path(output) if output else ROOT/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8])
    out.mkdir(parents=True,exist_ok=False)
    source=out/'source_snapshot';source.mkdir()
    for p in ROOT.glob('*.py'):shutil.copy2(p,source/p.name)
    save(out/'analysis_spec.json',{'scope':'same 81 campaign data, exploratory file-only synthesis; not a new independent experiment',
        'synthetic_fixture':fixture,
        'phenomena':['task/run learning heterogeneity','adjacent checkpoint gains/losses','observed multi-checkpoint recovery',
            'within-episode success departures/reentries','replay usage versus uniform-sampling opportunity','behavior/update alignment'],
        'selection':'all run/task/time results retained; posthoc extremes explicitly identified',
        'inference':'no p-value/CI search, classifier, selector or model fitting; no forced method or paper topic',
        'new_environment_steps':0,'new_model_forwards':0})
    inputs=[campaign/'protocol.json',campaign/'seed_manifest.json',campaign/'baseline_manifest.json',
            campaign/'config_resolved.json',campaign/'input_receipt.json',campaign/'evaluation_cases/manifest.json']
    protocol=read(campaign/'protocol.json');all_runs=protocol['runs'];eval_frames=[];completion=[];uses=[]
    for rid in all_runs:
        run=campaign/'runs'/rid
        completion.append({'run_id':rid,'normal_complete':(run/'COMPLETE.json').exists(),
            'failure_record':str(run/'FAILED.json') if (run/'FAILED.json').exists() else None})
        files=list((run/'evaluation_episodes').glob('part_*.parquet'));inputs+=files
        df=parts(run/'evaluation_episodes')
        if not df.empty:eval_frames.append(df)
        a=parts(run/'replay_usage/evicted');b=parts(run/'replay_usage/final_active')
        if not a.empty or not b.empty:
            life=pd.concat([x for x in (a,b) if not x.empty],ignore_index=True)
            if life.transition_id.duplicated().any():raise RuntimeError('Duplicate replay IDs')
            # Uniform replay expectation conditional on this FIFO insertion/update schedule.
            t=life.collection_env_step.to_numpy(dtype=np.int64)
            observed_end=int(read(run/'status.json')['train_transitions'])
            update_times=np.arange(1,observed_end+1,dtype=np.int64)
            weights=np.where(update_times>1000,256/np.minimum(update_times,100000),0.)
            cumulative=np.r_[0.,np.cumsum(weights)]
            last=np.minimum(t+99999,observed_end)
            expected=cumulative[last]-cumulative[t-1]
            life['expected_uniform_uses']=expected;life['collection_window']=(t-1)//100000
            for (task,window),g in life.groupby(['source_task_id','collection_window']):
                uses.append({'run_id':rid,'task_id':task,'collection_window':int(window),'transitions':len(g),
                    'critic_uses':int(g.critic_sample_count.sum()),'actor_uses':int(g.actor_sample_count.sum()),
                    'uniform_expected_uses':float(g.expected_uniform_uses.sum()),
                    'actual_over_expected':float(g.critic_sample_count.sum()/g.expected_uniform_uses.sum()) if g.expected_uniform_uses.sum()>0 else None,
                    'never_sampled':int((g.critic_sample_count==0).sum()),'active_censored':int(g.active_censored.sum()),
                    'use_q50':float(g.critic_sample_count.quantile(.5)),'use_q95':float(g.critic_sample_count.quantile(.95))})
            inputs+=list((run/'replay_usage/evicted').glob('*.parquet'))+list((run/'replay_usage/final_active').glob('*.parquet'))
            del life,a,b
    completion=pd.DataFrame(completion);completion.to_csv(out/'execution_status.csv',index=False)
    if not eval_frames:
        save(out/'PARTIAL.json',{'reason':'No valid evaluation outcomes','new_environment_steps':0});return out
    episodes=pd.concat(eval_frames,ignore_index=True)
    keys=['run_id','task_id','checkpoint_id','initial_case_id','physical_case_id']
    if episodes.duplicated(keys).any():raise RuntimeError('Duplicate scientific outcome keys')
    episodes.to_parquet(out/'evaluation_outcomes.parquet',index=False)
    metrics=episodes.groupby(['run_id','task_id','checkpoint_id']).agg(
        N=('success_any','size'),successes=('success_any','sum'),final_successes=('success_final','sum'),
        mean_return=('episode_return','mean'),mean_length=('episode_length','mean'),
        first_success_median=('first_success_step','median')).reset_index()
    metrics['success_pct']=100*metrics.successes/metrics.N
    metrics['final_success_pct']=100*metrics.final_successes/metrics.N
    metrics.to_csv(out/'learning_curves_all_runs.csv',index=False)
    risk=[];hist=[];recoveries=[];case_lookup={}
    for (rid,task,case,physical),g in episodes.groupby(['run_id','task_id','initial_case_id','physical_case_id']):
        labels={int(r.checkpoint_id):int(r.success_any) for r in g.itertuples()};case_lookup[(rid,task,case,physical)]=labels
        observed=[labels[s] if s in labels else None for s in protocol['evaluation_steps']]
        had_success=False;lost=False;recovered=False;losses=gains=0
        for x in observed:
            if x is None:continue
            if x==1:
                if lost:recovered=True
                had_success=True
            elif had_success:lost=True
        for a,b in zip(observed[:-1],observed[1:]):
            losses+=int(a==1 and b==0);gains+=int(a==0 and b==1)
        hist.append({'run_id':rid,'task_id':task,'initial_case_id':case,'physical_case_id':physical,
            'history':''.join('?' if x is None else str(x) for x in observed),'observed_gain_events':gains,
            'observed_loss_events':losses,'ever_successful':had_success,'success_then_later_failure':lost,
            'observed_recovery':recovered,'observed_checkpoints':len(labels)})
    histories=pd.DataFrame(hist);histories.to_csv(out/'case_histories_all.csv',index=False)
    for rid,task in [(r,t) for r in all_runs for t in TASKS]:
        cases={k:v for k,v in case_lookup.items() if k[:2]==(rid,task)}
        for a,b in zip(protocol['evaluation_steps'][:-1],protocol['evaluation_steps'][1:]):
            pairs=[(d[a],d[b]) for d in cases.values() if a in d and b in d]
            n=len(pairs);counts={p:pairs.count(p) for p in [(1,1),(1,0),(0,1),(0,0)]}
            row={'run_id':rid,'task_id':task,'from_step':a,'to_step':b,'planned_N':16,'valid_N':n,
                'retained':counts[(1,1)],'losses':counts[(1,0)],'gains':counts[(0,1)],'failed':counts[(0,0)],
                'G_pp':100*counts[(0,1)]/n if n else None,'L_pp':100*counts[(1,0)]/n if n else None,
                'net_pp':100*(counts[(0,1)]-counts[(1,0)])/n if n else None}
            risk.append(row)
    risk=pd.DataFrame(risk);risk.to_csv(out/'all_checkpoint_gain_loss.csv',index=False)
    # Within-episode histories are distinct from checkpoint-level changes.
    within=[]
    for e in episodes.itertuples():
        if not Path(e.trajectory_ref).exists():continue
        inputs.append(Path(e.trajectory_ref))
        with np.load(e.trajectory_ref,allow_pickle=False) as z:
            y=z['success_step']
            if int(y.any())!=int(e.success_any) or int(y[-1])!=int(e.success_final) or len(y)!=int(e.episode_length):
                raise RuntimeError('Saved episode summary differs from its original raw trajectory')
            exits=int(np.sum((y[:-1]==1)&(y[1:]==0)))
            seen=False;prev=False;returns=0
            for value in y:
                if value and not prev and seen:returns+=1
                prev=bool(value);seen|=prev
            action=z['action_executed']
            within.append({'run_id':e.run_id,'task_id':e.task_id,'checkpoint_id':e.checkpoint_id,
                'initial_case_id':e.initial_case_id,'physical_case_id':e.physical_case_id,
                'success_any':int(e.success_any),'success_final':int(e.success_final),'success_exits':exits,
                'observed_reentries':returns,'success_step_count':int(y.sum()),'length':len(y),
                'min_tcp_object_distance_m':float(z['tcp_object_distance'].min()),
                'min_object_goal_distance_m':float(z['object_goal_distance'].min()),
                'final_object_goal_distance_m':float(z['object_goal_distance'][-1]),
                'mean_action_norm':float(np.linalg.norm(action,axis=1).mean()),
                'mean_gripper_action':float(action[:,-1].mean()),'endpoint_contact_fraction':float((z['robot_object_contact_pairs']>0).mean()),
                'trajectory_ref':e.trajectory_ref,'video_ref':e.video_ref if isinstance(e.video_ref,str) else None})
    within=pd.DataFrame(within);within.to_parquet(out/'within_episode_observations.parquet',index=False)
    pd.DataFrame(uses).to_csv(out/'replay_usage_uniform_opportunity.csv',index=False)
    summary=[];phenomena=[]
    for task in TASKS:
        final=metrics[(metrics.task_id==task)&(metrics.checkpoint_id==1000000)]
        h=histories[histories.task_id==task];w=within[within.task_id==task]
        summary.append({'task':task,'completed_final_runs':len(final),'final_N':int(final.N.sum()),
            'mean_final_success_pct':float(final.success_pct.mean()) if len(final) else None,
            'min_run_success_pct':float(final.success_pct.min()) if len(final) else None,
            'max_run_success_pct':float(final.success_pct.max()) if len(final) else None,
            'case_run_histories':len(h),'histories_with_observed_loss':int((h.observed_loss_events>0).sum()),
            'histories_with_observed_recovery':int(h.observed_recovery.sum()),
            'within_episode_any_success':int(w.success_any.sum()),
            'within_episode_any_not_final':int(((w.success_any==1)&(w.success_final==0)).sum()),
            'within_episode_success_exit':int((w.success_exits>0).sum())})
        by_run=[]
        for rid in all_runs:
            g=metrics[(metrics.task_id==task)&(metrics.run_id==rid)]
            f=g[g.checkpoint_id==1000000]
            if len(f):by_run.append({'run_id':rid,'final_success_pct':float(f.success_pct.iloc[0]),
                'posthoc_max_success_pct':float(g.success_pct.max()),
                'posthoc_max_minus_final_pp':float(g.success_pct.max()-f.success_pct.iloc[0])})
        phenomena.append({'id':task+'_learning_and_exchange','execution_status':'analyzed' if len(final)==5 else 'partial',
            'scientific_conclusion':'exploratory finite-run observation; no causal mechanism or method superiority',
            'task':task,'per_run':by_run,'loss_case_run_count':int((h.observed_loss_events>0).sum()),
            'recovery_case_run_count':int(h.observed_recovery.sum()),
            'opposite_and_unchanged':'all gain/loss windows and all unchanged/successful/failed histories included in accompanying tables',
            'candidate_explanations':['policy learning variability','physical case heterogeneity','task difficulty','replay exposure and changing state visitation'],
            'unidentified':'state/action/experience usefulness and causal mechanism not separated',
            'next_minimal_check':'only after an explicit phenomenon is chosen; no automatic intervention or algorithm selection',
            'scope':'5 independent initializations on the fixed 16 physical cases per task, not 80 independent initial conditions',
            'posthoc_selection_note':'maximum checkpoint score is selected from observed outcomes and upward biased; descriptive only'})
    summary=pd.DataFrame(summary);summary.to_csv(out/'phenomena_summary.csv',index=False)
    # Concrete favorable/unfavorable/unchanged examples, selected posthoc and disclosed.
    examples=[]
    for task in TASKS:
        h=histories[histories.task_id==task]
        for kind,mask in [('loss_observed',h.observed_loss_events>0),('gain_observed',h.observed_gain_events>0),
                          ('unchanged_success',h.history.str.fullmatch('1+')),('unchanged_failure',h.history.str.fullmatch('0+'))]:
            g=h[mask].sort_values(['run_id','initial_case_id']).head(1)
            for row in g.to_dict('records'):
                row.update(example_kind=kind,selection_reason='posthoc lexicographically first within disclosed outcome category')
                examples.append(row)
    pd.DataFrame(examples).to_csv(out/'contrasting_case_examples.csv',index=False)
    primary=read(campaign/'LATEST_ANALYSIS.json') if (campaign/'LATEST_ANALYSIS.json').exists() else None
    inputs=list(dict.fromkeys(p.resolve() for p in inputs if p.exists()))
    with (out/'input_receipt.jsonl').open('x',encoding='utf-8') as f:
        for p in inputs:f.write(json.dumps(ref(p),ensure_ascii=False)+'\n')
    save(out/'phenomenon_register.json',{'entries':phenomena,'original_initialization_seeds':read(campaign/'seed_manifest.json')['streams'],
        'costs_ref':str(campaign/'FINAL_STATUS.json'),'new_environment_steps':0,'new_policy_forwards':0})
    # Independent count check from original outcomes, separate from grouped means.
    checkcount=0
    for r in metrics.itertuples():
        raw=[int(v) for k,d in case_lookup.items() if k[:2]==(r.run_id,r.task_id) for s,v in d.items() if s==r.checkpoint_id]
        if len(raw)!=r.N or sum(raw)!=r.successes:raise RuntimeError('Independent raw count verification failed')
        checkcount+=1
    save(out/'independent_counts.json',{'passed':True,'checked_cells':checkcount,'raw_outcomes':len(episodes),'new_environment_steps':0})
    complete_n=int(completion.normal_complete.sum());status='synthetic_fixture_completed' if fixture else ('observations_completed' if complete_n==5 and len(episodes)==3200 else 'partial_observations')
    report=['# 네 과제 기본 SAC 관측 — 탐색적 현상 정리',
        '\n## 1. 실제 완료 범위와 핵심 관측\n',
        f'정상 완료 {complete_n}/5 독립 초기학습 실행. 유효 정기 평가 {len(episodes):,}/3,200 에피소드. 이 분석은 81번의 같은 새 관측을 해석하며 별도의 독립 실험이 아니다.',
        '\n'+table(summary),
        '\n성공률은 원래 시작 상태의 고정 16사례 패널에서 측정했다. min/max는 독립 실행 사이의 관측 범위이며 신뢰구간이 아니다. '
        '사례×실행 이력 수와 고유 물리 사례 수를 구분한다. 원래 보고서와 성공/실패·무변화 사례를 모두 보존한다.',
        '\n## 2. 기본 학습과 평가·기록\n',
        '81번의 실제 baseline_manifest/config_resolved/protocol/source snapshot을 따른다. DO/DC/Push/BP, v3 환경/v2 보상, '
        '공통 과제조건부 기본 SAC만 사용했다. 8에피소드 블록마다 과제별 두 개를 섞는 기존 일정이며 새 curriculum·BC·KL·First·선택기를 넣지 않았다. '
        '각 실행 1M 전이는 네 과제 합계이며 warm-up을 포함한다. 초기 가중치와 학습 난수는 별도 생성했으며 과거 부모에서 분기하지 않았다.',
        '\n과거 루트 P0의 400k 설정은 다른 과제 구성인 suite A의 초기 구현 참고이며, 이번 네 과제 suite B의 직접 출처는 44번의 fresh 초기화·uniform 사전학습 코드와 이를 보존한 77번 복사본이다. '
        '44번 suite B의 과거 사전학습 길이는 200k이고 이번 1M은 사용자가 새로 정한 관측 예산이다. U 스케줄과 상수 학습률은 총길이에 의존하지 않는다. '
        '설치된 Meta-World wheel에서 VCS commit은 확인되지 않아 3.0.0 버전과 실제 소스/XML/모델 자산 해시로 고정했다.',
        '\n평가는 과제당 16개 초기조건을 공통 사용한 탐색 패널이다. 표준 Meta-World 전체 goal 성능으로 부르지 않는다. '
        '기존 deterministic CUDA 정책 경로를 사용하고, 이번 명세에 따라 최초 성공 이후에도 원래 환경의 정상 horizon까지 기록했다.',
        '\n## 3. 과제별·실행별 결과\n',
        table(metrics[metrics.checkpoint_id==1000000][['run_id','task_id','N','success_pct','final_success_pct','mean_return']]),
        '\n전체 checkpoint와 계획/완료 분모는 learning_curves_all_runs.csv에 있다. 일부 seed·과제를 제외해 본평균을 재구성하지 않았다.',
        '\n## 4. 사례별 행동 변화\n',
        '학습 시점 사이의 관측된 획득·상실과 한 에피소드 안의 목표 상태 이탈을 분리했다. '
        '각 인접 시점의 공통 유효 사례에서 G−L과 성공률 차이를 검산했다. 정확한 최초 능력 획득·상실 시점, 영구 능력 상실, 생애 최초 획득은 측정하지 않았다.',
        '\n'+table(histories.groupby(['task_id','run_id']).agg(histories=('history','size'),gain_events=('observed_gain_events','sum'),loss_events=('observed_loss_events','sum'),observed_recovery=('observed_recovery','sum')).reset_index()),
        '\n사례 예시는 결과를 본 뒤 정한 범주에서 ID 순으로 고른 기술 예시이며 빈도의 대표 표본이 아니다. '
        'contrasting_case_examples.csv에 선택 규칙과 반대/무변화 사례가 있고, 원래 trajectory/video 참조는 within_episode_observations.parquet에 있다.',
        '\n## 5. 경험 사용과 학습 통계\n',
        'replay_usage_uniform_opportunity.csv는 실제 사용 횟수와 기존 uniform FIFO replay에서 해당 전이가 표집될 수 있었던 기회를 함께 제시한다. '
        '기대 사용량은 삽입 시점, warm-up, buffer 포화 및 실제 종료 시점에 조건화한 산술값이다. '
        '최근 수집 자료의 작은 누적 사용량은 남은 표집 기회가 짧은 영향이 있으므로 자료가 무용하다는 뜻이 아니다. '
        '표집 횟수는 정책 개선 기여량이나 중요도 가중치가 아니다.',
        '\nloss/Q/alpha/gradient와 행동의 시간 정렬은 81번 learning_update_time_alignment 및 원본 업데이트 표에 있다. '
        '자연 실행의 요약값으로 원인을 확정하거나 예측기를 학습하지 않았다.',
        '\n## 6. 반복 현상과 경쟁 설명\n',
        table(summary[['task','case_run_histories','histories_with_observed_loss','histories_with_observed_recovery','within_episode_success_exit']]),
        '\n위 값이 0인 과제·실행도 그대로 남겼다. 반복 관측의 존재와 반복 범위를 구분한다. '
        '다른 checkpoint의 최고 성능을 고른 값과 최종 성능 차이는 선택된 기술통계이며 학습이 본질적으로 악화됐다는 독립 검정이 아니다. '
        '동일 사건을 관찰한 상태 구성, 평가 사례 난도, 정책 변화, 경험 노출은 경쟁 설명으로 남아 있다.',
        '\n## 7. 추가 진단\n',
        '이 파일 분석에서 신규 환경 reset/step, 정책 forward, 모델 로드, SAC 업데이트는 모두 0이다. '
        '81번의 추가 진단 여부와 비용은 해당 campaign의 diagnostic_plan 및 FINAL_STATUS를 따른다. 새 진단을 자동 실행하지 않았다.',
        '\n## 8. 비용·기술 한계·미측정\n',
        '본학습·평가·기술 비용은 81번 원장으로 연결한다. 이 분석의 비용은 파일 I/O·연산·저장 및 wall time이며 환경 전이에 더하지 않는다. '
        '64개 고유 초기조건과 5개 학습 실행을 3,200개 독립 표본으로 세지 않는다. '
        '이 보고서에서 사후 CI/검정 검색은 수행하지 않았다. 수치 궤적은 제어 step 끝의 물리 상태이며 모든 내부 substep을 측정한 것은 아니다. '
        'snapshot의 복원 주장은 원래 기술 영수증에 명시한 동일 runtime 검증 범위에 한정한다.',
        '\n## 9. 후속 질문 후보\n',
        '관측된 성공 교체가 특정 상태·행동의 변화와 반복해서 대응하는지, 에피소드 내 성공 이탈과 학습 시점 간 상실이 같은 사례에 집중되는지, '
        '경험 수집과 사용의 차이가 단순한 표집 기회 차이를 넘어 행동 변화와 연결되는지를 더 구체화할 수 있다. '
        '현재 기록은 후속 후보를 만들기 위한 자료다. 분기점 선택·복귀·기초동작·경험 선택 방법을 이번 결과만으로 채택하지 않는다.',
        '\n## 원본 및 재분석 위치\n',f'81번 campaign: {campaign}',
        f"\n81번 원 보고서: {primary['report']['path'] if primary else '원 분석 경로는 campaign/LATEST_ANALYSIS.json에서 확인'}",
        '\n입력 해시는 input_receipt.jsonl, 원 라벨은 evaluation_outcomes.parquet, 모든 사례 이력과 반대 사례는 동봉 CSV에 있다. '
        '대형 원 궤적·영상·checkpoint는 원래 위치를 참조하며 중복 ZIP하지 않는다.']
    if (campaign/'FINAL_STATUS.json').exists():
        final=read(campaign/'FINAL_STATUS.json');report.insert(4,'\n실제 비용: '+json.dumps(final.get('costs',{}),ensure_ascii=False))
    if fixture:report.insert(0,'**합성 fixture의 분석 동작 검사이며 실제 로봇 학습 결과가 아니다.**\n')
    (out/'report_ko.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
    bundle=out/'reproduction_bundle.zip'
    with zipfile.ZipFile(bundle,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for p in out.rglob('*'):
            if p.is_file() and p!=bundle:z.write(p,p.relative_to(out))
    save(out/'COMPLETE.json',{'status':status,'report':ref(out/'report_ko.md'),'bundle':ref(bundle),
        'analysis_wall_seconds':time.perf_counter()-started,'new_environment_steps':0,'new_neural_forwards':0,
        'packages':{n:importlib.metadata.version(n) for n in ('numpy','pandas','pyarrow')},'source_campaign':str(campaign)})
    if not fixture:save(ROOT/'LATEST.json',{'analysis':str(out),'report':ref(out/'report_ko.md'),'bundle':ref(bundle)},replace=True)
    return out

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--campaign',required=True);p.add_argument('--output');a=p.parse_args();print(analyze(a.campaign,a.output))
