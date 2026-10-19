# F05 동일 길이 목표 정합성과 rollout 가치 진단

2026-10-15 미실행 후보 검증 요청에 따른 독립 구현이다. [v26 critic 검증](../26_critic_signal_screening_v1/report_ko.md)은 보존하고, 당시 남았던 return·성공률 정합성과 제한 길이 가치 진단을 측정한다. 최종 결과는 실행 완료 후 자동 생성되며 시작을 효과 확인으로 해석하지 않는다.

**고정한 범위**

- 기존 A200k/A400k/B200k/C200k, 원래 seed 11/12/13의 부모 12개와 20k 모델 180개, 총 192개를 재사용한다. 새 학습 update는 0이다.
- 새 공통 진단 사례 20개/task에서 성공 이후에도 500 step을 끝까지 실행한다. 총 15,360 episode·7.68M 환경 step이다.
- 모델마다 2개 초기 상태/task × 4개 stochastic 경로로 Q와 soft rollout 추정의 차이를 측정한다. 총 6,144 episode·3.072M step이다.
- 전체 진단 비용은 **10.752M 환경 step**이다. bank 생성, 기술 검사, 실패 시도와 분석 비용도 별도로 기록한다.

첫 행동을 고정하고 이후 행동은 동결한 SAC 정책에서 표본화한다. 0번째 보상에는 entropy를 더하지 않고, 이후 discounted reward − alpha·logπ와 500 step 뒤의 16-action current-Q bootstrap을 계산한다. 할인된 tail, tail을 제외한 차이, 4개 경로 평균의 표준오차를 모두 보존한다. 현재 Q를 tail에 사용하는 유한 길이 추정이므로 정확한 무한 길이 가치의 정답이 아니다.

새 D의 현재·부모 성공률을 통제한 뒤 task별 return→성공률 보정의 추가 선택 가치를 주 비교로 삼는다. 보정과 예측기 모두 평가할 원래 seed 전체를 제외하고 적합한다. 기존 D50/O50 분리, 20k→40k 결과와 같은/다른 후속 반복 비교를 유지한다. rollout 오차는 추정 target 규모·표준오차까지 통제한 모형과 비교한다. 공식 `near_object` 도달은 F03 보조 결과다. `grasp_success`의 의미가 task마다 달라 범용 파지 지표로 합치지 않는다.

[프로토콜](protocol.json)에 특징·기준·사례 수·seed·비용을 고정했다. 기존 자료를 사용한 탐색 예측 검증이며, 공통 4k 진단이나 새 원래 seed 확인·동일 총예산 온라인 배분은 아니다. 주 선별 기준은 추가 선택 이득 +1%p 이상, 원래 seed 둘 이상 양수, 구성·시점 최소 −2%p 이상이다. 사례 bootstrap 구간은 정책·선택·모형을 고정한 조건부 구간이다.

**구현과 실행**

`practice_allocation/`은 v12의 학습기·환경·checkpoint 구현을 독립 복사했다. 다른 버전 코드를 import하지 않는다. `diagnostics.py`가 원시 500-step trace·episode 결과를 저장하고 `verify_traces.py`가 별도 식으로 검산한다. 진단 전후 learner·optimizer·replay·collector·RNG 지문이 같아야 완료로 인정한다. `analyze.py`와 `verify_analysis.py`는 전체 측정 이후 예측·선택·비용을 계산하고 독립 검산한다.

A/B/C 실제 모델의 기술 검사 각각 117개가 통과했다. 최초 A/B 검사의 합산 순서 차이로 인한 실패 2회도 [실패 기록](technical_failures_ko.md)에 보존했다. 기술 검사 통과는 과학적 효과의 근거가 아니다.

전체 실행은 [v33 실행기](../33_remaining_factor_queue_v1/README.md)가 관리한다. worker별 `request.json`, `runtime.json`, `source_snapshot/`, `source_hashes.json`, `costs.json`, `diagnostics/`를 보존하며 최종 분석 폴더에 `report_ko.md`를 생성한다. 큰 trace·checkpoint는 로컬에 보존한다.
