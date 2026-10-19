"""Prespecified dose/order contrasts after ALL72 actual branches finish."""
import argparse
import traceback
from pathlib import Path
import numpy as np
from common import Run,HERE,save,table

CONTRASTS={
 'dose81_minus25':{'dose8125':1,'dose25':-1},
 'dose4375_nonlinearity':{'dose4375':1,'dose25':-2/3,'dose8125':-1/3},
 'dose625_nonlinearity':{'dose625':1,'dose25':-1/3,'dose8125':-2/3},
 'forward_minus_reverse':{'i_then_j':1,'j_then_i':-1},
 'forward_minus_mixture':{'i_then_j':1,'mixture':-1},
 'reverse_minus_mixture':{'j_then_i':1,'mixture':-1},
 'alternate_minus_mixture':{'alternate4k':1,'mixture':-1}}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--campaign',required=True);args=ap.parse_args();run=Run('analysis')
    try:
        p=run.read(HERE/'protocol.json');cam=Path(args.campaign);integ=run.read(cam/'plan_integrity.json');plan=run.read(cam/'plan.json',integ['sha256'])
        y={};base={};training_steps=0;evaluation_steps=0;provenance=[]
        for job in plan['jobs']:
            if job['stage']!='F08' or job['kind'] not in ['train','evaluate']:continue
            marker=run.read(cam/'completed'/(job['id']+'.json'));result=run.read(marker['result_ref']['path'],marker['result_ref']['sha256'])
            costs=run.read(Path(marker['result_ref']['path']).parent/'costs.json')
            if job['kind']=='train':
                run.check('complete20k training segment',costs['status']=='completed' and costs['costs']['train_iterations']==20000 and costs['costs']['environment_steps']==20000)
                training_steps+=20000;continue
            evaluation_steps+=costs['costs']['environment_steps']
            if job['bank_kind']!='outcome':continue
            run.hashed(result['episodes_path'],result['episodes_sha256']);rows=run.rows(result['episodes_path']);arr=np.zeros((4,100));seen=set()
            for row in rows:
                ti=p['suites'][job['suite']].index(row['task']);ix=int(row['episode_index'])
                run.check('unique case', (ti,ix) not in seen);seen.add((ti,ix));arr[ti,ix]=int(row['success'])
            run.check('400 binary outcome episodes',len(seen)==400 and np.isin(arr,[0,1]).all())
            run.check('macro agrees',abs(arr.mean()-result['evaluation']['macro_success'])<1e-12)
            if job.get('condition'):y[job['suite'],job['condition'],job['continuation']]=arr
            else:base[job['suite']]=arr
            provenance.append({'id':job['id'],'path':result['episodes_path'],'sha256':result['episodes_sha256']})
        run.check('all72 branches and3 parents',len(y)==72 and len(base)==3 and training_steps==2880000)
        table(run.out/'outcome_provenance.csv',provenance)
        cells=[]
        for (suite,condition,rep),arr in y.items():
            r={'suite':suite,'condition':condition,'continuation':rep,'macro_success_pp':float(arr.mean()*100),
               'absolute_gain_pp':float((arr-base[suite]).mean()*100),'worst_task_drop_pp':float((base[suite].mean(1)-arr.mean(1)).max()*100)}
            r.update({t+'_success_pp':float(arr[i].mean()*100) for i,t in enumerate(p['suites'][suite])});cells.append(r)
        table(run.out/'branch_scores.csv',cells);contrasts=[];per_repeat=[];rng=np.random.default_rng(p['bootstrap_seed'])
        for suite in p['suites']:
            # Shared case resamples for all contrasts; policies and continuations fixed.
            weights=rng.multinomial(100,np.full(100,.01),size=(5000,4))
            for name,coefficients in CONTRASTS.items():
                diffs=[sum(co*y[suite,cond,rep] for cond,co in coefficients.items()) for rep in p['continuations']]
                mean=sum(diffs)/3;point=float(mean.mean()*100);boot=np.einsum('dti,ti->d',weights,mean)/4
                points=[float(d.mean()*100) for d in diffs]
                for rep,value in zip(p['continuations'],points):per_repeat.append({'suite':suite,'contrast':name,'continuation':rep,'difference_pp':value})
                consistent=sum(v>0 for v in points) if point>=0 else sum(v<0 for v in points)
                contrasts.append({'suite':suite,'contrast':name,'difference_pp':point,'case_only_lo_pp':float(np.quantile(boot,.025)),
                    'case_only_hi_pp':float(np.quantile(boot,.975)),'same_sign_repeats':consistent,
                    'descriptive_lead':abs(point)>=1 and consistent>=2})
        table(run.out/'contrasts.csv',contrasts);table(run.out/'contrasts_by_repeat.csv',per_repeat)
        report=['# F08 강도와 순서 대조 결과','',
                '사전에 고정한 72분기를 모두 완료했다. A/B/C 각각 원래 seed 12 한 개의 개발 검증이며, 아래 구간은 고정된 정책의 평가 사례만 재표집했다. 원래 seed 일반화나 비용 포함 적응형 배분의 성공을 뜻하지 않는다.','',
                '| 구성 | 사전 대조 | 차이 %p | 사례 조건부 95% 구간 | 같은 방향 반복 |',
                '| --- | --- | ---: | --- | ---: |']
        for r in contrasts:report.append(f"| {r['suite']} | {r['contrast']} | {r['difference_pp']:+.3f} | [{r['case_only_lo_pp']:+.3f}, {r['case_only_hi_pp']:+.3f}] | {r['same_sign_repeats']}/3 |")
        report+=['','dose4375/625_nonlinearity는 양 끝 비중의 선형 보간과 실제 중간 비중의 차이다. 순서 대조는 총 수집량을 맞춘 실제 연속 학습이다. 학습 중 optimizer·replay·RNG를 전환 시점에 초기화하지 않았다.',
                 '',f'완료 분기 학습은 {training_steps:,} step, 이 단계의 초기·최종 평가 환경 실행은 {evaluation_steps:,} step이었다. 실패·기술 검사 비용은 campaign 실행 비용표에 별도로 포함한다.',
                 '', '[전체 분기 점수](branch_scores.csv) · [대조별 반복](contrasts_by_repeat.csv) · [출처](outcome_provenance.csv)',
                 '', '평균 절대 차이 1%p와 3반복 중 2반복 같은 방향은 후속 연구를 위한 기술적 표시다. 통계적 유의성이나 일반 효과 채택 기준으로 바꾸지 않는다.']
        with (run.out/'report_ko.md').open('x',encoding='utf-8') as f:f.write('\n'.join(report)+'\n')
        run.finish({'status':'completed','factor':'F08','campaign':str(cam),'branches':72,'original_seed_count':1,
                    'completed_training_steps':training_steps,'measured_evaluation_steps':evaluation_steps,'contrasts':contrasts,
                    'independent_confirmation':False,'cost_inclusive_adaptive_allocation_tested':False})
    except Exception:
        run.finish({'status':'failed','traceback':traceback.format_exc()});raise


if __name__=='__main__':main()
