"""Read-only completion review; no learner imports, rollouts or new bootstrap."""
import csv
import hashlib
import json
import shutil
import traceback
import uuid
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent
A=REPO/'66_retention_intervention_queue_v1/results/20261028T014720Z_analysis_0918111d'
AV=REPO/'66_retention_intervention_queue_v1/results/20261028T014738Z_verify_f207b31f'
B=REPO/'67_baseline_analysis_repair_v1/results/20261027T125938Z_analysis_9467d7b9'
BV=REPO/'67_baseline_analysis_repair_v1/results/20261027T130008Z_verify_e37dfa31'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):
    with Path(path).open('x',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def rows(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as stream:return list(csv.DictReader(stream))
def main():
    out=ROOT/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_review_'+uuid.uuid4().hex[:8])
    (out/'source_snapshot').mkdir(parents=True)
    sources={p.name:sha(p) for p in ROOT.iterdir() if p.suffix in ('.py','.md')}
    for name in sources:shutil.copy2(ROOT/name,out/'source_snapshot'/name)
    save(out/'source_hashes.json',sources)
    receipt={};checks=[]
    def capture(path):
        path=Path(path);receipt[str(path)]={'sha256':sha(path),'bytes':path.stat().st_size}
        return read(path) if path.suffix=='.json' else rows(path)
    def check(name,ok):
        checks.append({'name':name,'passed':bool(ok)})
        if not ok:raise AssertionError(name)
    try:
        summaries=[]
        for directory,verification,n in ((A,AV,40),(B,BV,20)):
            summary=capture(directory/'summary.json');marker=capture(directory/'COMPLETE.json')
            verify=capture(verification/'summary.json');vm=capture(verification/'COMPLETE.json')
            verified=capture(verification/'verified_inputs.json')
            check('analysis_summary_hash_'+str(n),marker['summary_sha256']==sha(directory/'summary.json'))
            check('verify_summary_hash_'+str(n),vm['summary_sha256']==sha(verification/'summary.json'))
            check('full_verified_'+str(n),verify['status']=='passed' and verify['full_campaign'] and not verify['self_test_only'])
            check('verification_exact_analysis_'+str(n),Path(verified['analysis']).resolve()==directory.resolve() and verified['summary_sha256']==sha(directory/'summary.json'))
            check('all_jobs_completed_'+str(n),summary['completed_jobs']==summary['planned_jobs']==n)
            check('file_only_'+str(n),summary['analysis_new_environment_steps']==summary['analysis_SAC_updates']==0)
            summaries.append(summary)
        intervention,baseline=summaries
        condition=intervention['primary']['conditions']
        for arm,c in condition.items():
            check('net_identity_'+arm,abs(c['J']-condition['STOP']['J']-c['G']+c['L'])<1e-10)
            check('recovery_is_gain_subset_'+arm,0<=c['recovery']<=c['G'])
        parents=capture(A/'parent_results.csv');tasks=capture(A/'task_contributions.csv')
        futures=capture(A/'future_results.csv');lopo=capture(A/'leave_one_parent_out.csv')
        pt={(int(r['parent']),r['condition']):r for r in parents}
        tt={(r['task'],r['condition']):r for r in tasks}
        ft={(int(r['future']),r['condition']):r for r in futures}
        pd={str(p):{contrast:float(pt[p,x]['J'])-float(pt[p,y]['J'])
            for contrast,x,y in (('D-C','D','C'),('D-A','D','A'))} for p in range(41011,41016)}
        td={task:{contrast:(float(tt[task,x]['J'])-float(tt[task,y]['J']))/4
            for contrast,x,y in (('D-C','D','C'),('D-A','D','A'))} for task in ('DO','DC','PU','BP')}
        fd={str(f):{contrast:float(ft[f,x]['J'])-float(ft[f,y]['J'])
            for contrast,x,y in (('D-C','D','C'),('D-A','D','A'))} for f in (1,2)}
        for contrast in ('D-C','D-A'):
            expected=intervention['primary']['contrasts'][contrast.replace('-','_minus_')]['J']
            check('parent_average_'+contrast,abs(sum(r[contrast] for r in pd.values())/5-expected)<1e-10)
            check('task_sum_'+contrast,abs(sum(r[contrast] for r in td.values())-expected)<1e-10)
        new_only={arm:c['G']-c['recovery'] for arm,c in condition.items()}
        for row in lopo:
            name=row['contrast'].replace('_minus_','-')
            if name in ('D-C','D-A'):
                expected=sum(x[name] for p,x in pd.items() if int(p)!=int(row['excluded_parent']))/4
                check('LOPO_'+row['excluded_parent']+'_'+name,abs(expected-float(row['J']))<1e-10)
        jobs=capture(REPO/'66_retention_intervention_queue_v1/inputs/jobs.json')
        protocol=capture(REPO/'66_retention_intervention_queue_v1/protocol.json')
        bjobs=capture(REPO/'64_gain_loss_recovery_baseline_v1/inputs/jobs.json')
        check('separate_future_sets',not {j['root_seed'] for j in jobs}&{j['root_seed'] for j in bjobs})
        costs={k:s['total_environment_steps_all_attempts'] for k,s in zip(('baseline','intervention'),summaries[::-1])}
        # summaries[::-1] is baseline,intervention. Keep each packet's physical ledger separate.
        total=sum(costs.values())
        record={'execution_status':'baseline20_and_intervention40_completed_and_independently_verified',
            'scientific_conclusion':'D exceeds C on observed policies; general superiority to stock A and gain noninferiority remain unestablished',
            'primary':intervention['primary'],'case_intervals':intervention['case_intervals'],
            'parent_contrasts_pp':pd,'task_macro_contributions_pp':td,'future_contrasts_pp':fd,
            'acquisition_excluding_P_to_S_recovery_pp':new_only,'original_parent_seeds':list(range(41011,41016)),
            'original_prefix_seed':4201,'actual_new_future_seed_jobs':jobs,
            'physical_cost_environment_steps':costs,'combined_environment_steps':total,
            'analysis_new_environment_steps':0,'analysis_new_SAC_updates':0,
            'negative_findings':['C loses acquisition relative to A','D-A interval includes zero',
                'D-A mean becomes zero without41014','D has lower DC success and higher DC loss than A/C',
                'D does not preserve all S successes; D acquisition without old-success recovery is lower than A'],
            'uncertainty_scope':intervention['uncertainty_scope'],
            'limitations':intervention['limitations']+['Historical-success anchors include shared general fallback where no successful training episodes exist.',
                'A and previous baseline BP625 have different futures; their score difference is not an intervention effect.'],
            'next_decision':'Inspect BP/41014-specific response and preservation exposure before specifying any independent confirmation; no automatic expansion.',
            'new_experiment_or_queue_authorized':False}
        save(out/'evidence_record.json',record)
        table='\n'.join(f"| {arm} | {c['J']:.2f} | {c['G']:.2f} | {c['L']:.2f} | {c['recovery']:.2f} |" for arm,c in condition.items())
        report=f'''# 기준선·첫 보존 개입 완료 결과

2026-10-28. 기준선20/20, 보존 비교40/40 모두 완료·실패0. 두 파일 분석의 독립 검산도 통과했다.
기준선은 알려진 CSV 문자열 합산 오류만67번에서 수리했으며64번 학습·평가·동결 소스는 보존했다.
보존 큐는2026-10-28 10:48 KST에 최종 완료를 기록했다. 이 검토는 새 환경 실행0이다.

## 핵심 결과

주비교 D−C에서 최종 성공률은+2.55%p이고 조건부 사례95% 구간은[+1.499,+3.650]%p다.
획득+1.40, 상실−1.15, 회복+0.90%p가 관측됐다. 성공 경험이 지원되는 곳에서 그 경험을
선택하는 보호 규칙은 이번 일반 경험 보호보다 유리했다.

| 조건 | 최종 성공률% | 획득G %p | 상실L %p | 회복R %p |
|---|---:|---:|---:|---:|
{table}

A=기본 SAC, B=actor 학습률 절반, C=일반 경험 보호, D=성공 episode 경험 우선 보호.
출발 S=35.80%. G/L/R은 전체 E50 사례 대비 기여량이며, 조건부 위험률이 아니다. **R은 G에 포함된다.**

## 기본 SAC보다 좋아졌는가

D−A는 최종 +1.10%p이나 구간 [−0.25,+2.45]로 총성능 우위를 확정하지 못했다.
상실은−1.35%p[−2.35,−0.35]였고 획득은−0.25%p[−1.15,+0.65]다.
회복은+0.40%p[+0.05,+0.80]였다. 개별 사례조건부 구간이며 다중비교 동시구간이 아니다.
획득의 비열등성이나 새로운 부모·미래에서의 총성능 우월성을 확인한 것은 아니다.

P/S 모두 실패였던 사례의 획득은 A 2.25, D 1.60%p다. 이것은 G에서 기존 성공의 회복 R을 뺀 기술량이며,
별도의 불확실성 분석을 추가하지 않았다. 따라서 D가 모든 새 성공 획득을 유지했다고 해석하지 않는다.
C는 A보다 획득 1.65%p 감소·상실 0.20%p 감소로 최종 1.45%p 낮았다. 보호 자체가 항상 유익하지 않았다.

## 어느 범위에서 나온 차이인가

D−C의 부모별 차이는 −0.25,+1.00,−2.25,+8.50,+5.75%p로 3/5 부모에서 양수다.
어느 부모 하나를 빼도 전체 차이는 양수 [+1.0625,+3.75]지만 모든 부모에서 일관된 것은 아니다.
D−A의 전체 +1.10%p는 41014를 제외하면 0이다. 미래별 D−C는 +2.8/+2.3,
D−A는 −0.9/+3.1%p로 기본 SAC 비교는 미래에 따라 방향이 바뀌었다.

D−C의 BP 최종 성공률 차이는 +11.8%p(전체 평균 기여 +2.95)였으나 DC는 −2.4%p(기여 −0.60)다.
D−A에서도 BP +5.2%p, DC −1.2%p다. 여러 과제에 고르게 적용되는 보존 효과로 확대하지 않는다.

D와 STOP은 평균 35.80%로 같지만, D는 3.65%p 획득과 3.65%p 상실이 상쇄됐다.
이는 같은 성공 집합의 완전 보존, 통계적 동등성, 중단보다 더 좋은 결과를 뜻하지 않는다.

## 앞선 기준선과 비용

별도의 기준선 새 미래에서는 STOP 35.80%, UNIFORM 31.65%, BP625 32.60%였다.
BP625−UNIFORM +0.95%p의 구간은 [−0.25,+2.10]이다. 두 지속 조건 모두 평균에서 상실이 획득보다 컸다.
이 BP625와 개입 실험 A는 서로 다른 미래를 사용했으므로 32.60→34.70을 방법 효과로 계산하지 않는다.

실제 비용은 기준선 3,660,612, 개입 7,218,140, 합계 {total:,} 환경 step이다.
각 상한 6.05M/10.10M 안이며, 실패·기술 시도와 평가를 포함한다. 기존 P/S 평가는 인증 후 재사용했다.

## 다음 판단

현재 남는 가장 구체적인 단서는 성공 관련 관측을 고르는 보호와 일반 관측 보호의 차이,
그리고 그 차이가 BP·일부 부모에 집중된다는 점이다. 기존 로그에서 실제 보호 노출·KL·업데이트의
차이를 확인해 비교 가설을 좁힐 수 있다. 이 검토로 보호 강도 재조정·새 부모·MT10·추가 학습은 예약하지 않았다.
부모 5개와 기존 E50에 대한 개발 결과이며, 새 확인 실험의 명세와 규모는 별도 판단으로 남긴다.

출처와 해시는 input_receipt.json, 원래 효과·seed·비용·불리한 결과는 evidence_record.json에 보존한다.
'''
        (out/'report_ko.md').write_text(report,encoding='utf-8')
        save(out/'input_receipt.json',receipt)
        save(out/'summary.json',{'status':'passed','checks':checks,'input_files':len(receipt),
            'new_environment_steps':0,'SAC_updates':0,'report_sha256':sha(out/'report_ko.md')})
        save(out/'COMPLETE.json',{'summary_sha256':sha(out/'summary.json'),'status':'completed'})
    except BaseException:
        save(out/'FAILED.json',{'traceback':traceback.format_exc(),'new_environment_steps':0});raise
    print(json.dumps({'review_dir':str(out),'checks':len(checks),'new_environment_steps':0},ensure_ascii=False))
if __name__=='__main__':main()
