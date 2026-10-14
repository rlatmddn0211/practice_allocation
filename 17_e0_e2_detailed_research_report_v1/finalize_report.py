"""Verify material report claims and finalize evidence metadata without retraining."""
import hashlib, json, math, shutil, sys, time, uuid
from pathlib import Path
from datetime import datetime, timezone

root=Path(__file__).resolve().parent
analysis=root/'results/20261013T052346Z_7e2f6a68/extended_analysis.json'
data=root/'report_app/src/data.json'
out=root/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_claims_'+uuid.uuid4().hex[:8])
out.mkdir(exist_ok=False)
shutil.copyfile(__file__,out/'source_snapshot.py')
start=time.perf_counter()
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
a=json.loads(analysis.read_text(encoding='utf-8'))
x=json.loads(data.read_text(encoding='utf-8'))
checks=[]
def near(name, actual, expected):
    assert math.isclose(actual,expected,abs_tol=.0051),(name,actual,expected)
    checks.append({'claim':name,'actual':actual,'reported':expected})
try:
    for stage,expected in [('E0',7.92),('E1',.39),('E2',-.78)]:
        near(stage+' primary',next(r['mean_pp'] for r in a['primary'] if r['stage']==stage),expected)
    e1={r['allocation']:r for r in a['e1'] if r['horizon']==40000}
    for alloc,expected in [('F_DO',-3.47),('F_DC',.39),('F_WO',1.46),('F_WC',-3.18)]:
        near('E1 '+alloc,e1[alloc]['macro_vs_U_pp'],expected)
    for s,expected in [(11,19.75),(12,-1.75),(13,-1.08)]:
        near('WO checkpoint interaction '+str(s),next(r['checkpoint_interaction_pp'] for r in a['checkpoint_interaction'] if r['seed']==s and r['allocation']=='F_WO'),expected)
    for t,expected in [('DO',6.11),('DC',.83),('WO',-2.11),('WC',-3.28)]:
        near('DC task contribution '+t,e1['F_DC'][t+'_vs_U_pp'],expected)
    for rule,expected in [('Failure',-3.88),('Progress',-2.43),('cross_repeat_diagnostic',3.57)]:
        near('E1 rule '+rule,next(r['gain_vs_U_pp'] for r in a['rules'] if r['rule']==rule and r['horizon']==40000),expected)
    e2={r['allocation']:r for r in a['e2'] if r['horizon']==40000}
    parent_DO=sum(r['DO_pct'] for r in a['baselines'] if r['stage']=='E2')/3
    near('E2 parent DO',parent_DO,7.67)
    assert all(r['DO_pct']<parent_DO for r in e2.values())
    near('E2 WO+ macro advantage',e2['DC_minus_WO_plus']['macro_vs_U_pp'],2.39)
    near('E2 DC+ macro advantage',e2['DC_plus_WO_minus']['macro_vs_U_pp'],-1.72)
    near('E2 WC exchange effect',e2['DC_minus_WO_plus']['WC_pct']-e2['DC_plus_WO_minus']['WC_pct'],10)
    assert sum(r['training_steps'] for r in a['costs'])==5880000
    assert sum(r['evaluation_episodes'] for r in a['costs'])==112800
    definitions={
      'primary':[{'label':'주 비교 차이 (%p)','definition':'E0: 확인용 continuation 1903–1905의 DC−U macro. E1: 독립 seed별 내부 평균 후 DC−U macro. E2: 같은 세 부모에서 DO 성공률 DC+−WO+. 서로 다른 측정 과제를 합산하지 않는다.'},
                 {'label':'조건부 평가 구간','definition':'2,000회 paired case bootstrap의 95% 구간. 공유 평가 사례를 함께 재표집하며 정책과 seed는 고정한다. 학습 seed 신뢰구간이 아니다.'}],
      'baselines':[{'label':'부모 성공률 (%)','definition':'해당 stage outcome bank의 과제별 100개 평가 사례에서 성공한 비율 × 100. macro는 과제 4개의 동일 가중 평균. E1/E2의 bank가 달라 같은 부모도 숫자가 다를 수 있다.'}],
      'rules':[{'label':'규칙의 U 대비 차이 (%p)','definition':'선택된 배분의 성공률에서 같은 부모·continuation·예산의 U를 뺀 뒤 중첩 반복을 평균. Failure/Progress는 public 진단만 사용. cross-repeat는 다른 두 continuation의 branch outcome을 사용하는 사후 진단으로 탐색 비용이 제외된다.'}],
      'rule_choices':[{'label':'개별 선택과 결과','definition':'각 부모 checkpoint와 평가 예산에 대해 각 규칙이 선택한 배분 및 held-out continuation 결과. 배분 선택에 쓰인 표본은 규칙별로 다르며 독립 학습 seed가 추가된 것이 아니다.'}],
      'risk':[{'label':'부모 대비 최대 과제 하락 (%p)','definition':'분기마다 max(0, max_task(parent_success − endpoint_success)) 계산. mean_maximum_task_drop_pp는 이 값의 평균, worst_drop_pp는 최대값이다. U 대비 차이가 아니다.'},
              {'label':'양수 분기 수','definition':'원래 seed 3개 × checkpoint 2개 × continuation 3개의 중첩 분기 18개 중 U 대비 macro 차이가 양수인 수. 독립 seed 수로 사용하지 않는다.'}],
      'diagnostics':[{'label':'Public 성공률 (%)','definition':'branch outcome과 분리된 과제별 public 사례 100개에서 측정. Failure는 최저 성공률 과제, 동률은 U. Progress는 최근 구간의 양의 성공률 증가/step 최대 과제, 동률 또는 양의 진전 없음은 U.'}],
      'checkpoint_interaction':[{'label':'출발 checkpoint 상호작용 (%p)','definition':'같은 원래 seed에서 (400k 출발 배분−U) − (200k 출발 배분−U). 두 출발점 모두 추가 40k 결과다. 기술적 사후 분해이며 독립 checkpoint 표본이 아니다.'}],
      'temporal':[{'label':'추가 예산별 상대 성능','definition':'같은 부모·배분·continuation의 추가 20k와 40k 결과. 각 시점은 같은 예산의 U와 비교한다. increment_20_to_40_pp는 두 시점 macro 절대 성공률의 차이다.'}],
      'e2_contrast':[{'label':'DO donor 비교 (%p)','definition':'동일 원래 seed와 예산에서 DO 성공률 DC+−WO+, continuation 3개 평균. DO/WC의 수집 step 수가 같으며 DC와 WO 예산을 교환한다. 직접 전이를 분리한 값이 아니다.'}]
    }
    for name,defs in definitions.items(): x['queries'][name]['source']['metricDefinitions']=defs
    x['buildStatus']='complete'
    data.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    record={'passed':True,'claims':checks,'source_sha256':sha(Path(__file__)),'analysis_sha256':sha(analysis),'snapshot_sha256':sha(data),
            'analysis_result':'results/20261013T052346Z_7e2f6a68','new_training_steps':0,'new_evaluation_episodes':0,
            'python':sys.version,'wall_seconds':time.perf_counter()-start}
    (out/'verification.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    print(json.dumps({'passed':True,'output':str(out),'claims':len(checks)}))
except BaseException as e:
    (out/'failure.json').write_text(json.dumps({'error':repr(e),'checks':checks},indent=2),encoding='utf-8')
    raise
