# F05 동일 길이 목표 정합성과 rollout 가치 진단

기존192개 정책에서 새 사례의500-step 진단을 완료했다. 모든 새 진단은 원본 학습 상태를 보존했다. 아래는 기존40k 결과를 이용한 탐색 예측·선택 비교이며 새 원래 seed 확인이나 동일 총예산 온라인 실험이 아니다.

| 추가 지표 | 비교 기준 | 같은 반복 선택 이득 %p | 다른 반복 선택 이득 %p |
| --- | --- | ---: | ---: |
| RawReturn | SuccessBase | -0.935 | +0.259 |
| CalibratedReturn | SuccessBase | -0.296 | -0.352 |
| RolloutValue | RolloutBase | +0.083 | +0.306 |
| NearObject | SuccessBase | -0.352 | +0.028 |

주 비교 CalibratedReturn의 선별 기준 통과: False. 원래 seed11/12/13의 증분은 +0.083%p, +0.194%p, -1.167%p.

return→성공 보정은 각 평가 fold에서 제외한 원래 seed의 자료를 사용하지 않았다. task별 보상 단위를 표준화한 뒤 보정했고, 예측기는 같은 정보 시점의 성공률 기준과 비교했다.

RolloutValue는 고정 첫 행동에서 시작해500-step 보상·entropy와 할인된 current-Q tail을 합한 추정과 Q의 차이다. 소수 경로의 표준오차와 target scale을 기준 모형에 포함했다. 정확한 무한 길이 가치 정답으로 해석하지 않는다. tail 없는 민감도와 각 task의 표준오차는 별도 표에 보존했다.

NearObject는 task별 공식 near_object 도달 비율을 사용한 F03 보조 비교다. 과제마다 거리 기준이 다르고 일부 공식 grasp_success는 상수이므로 이를 보편적인 잡기 단계로 합치지 않았다.

실제 새 환경 진단 비용은10,752,000step이며 지속 학습 update는0회다. 같은 반복 선택을 실제로 재현할 때 성공/return 진단은 부모+5probe에서240k 평가step, 가치 진단은96k 평가step을 더 쓴다. 기존20k probe와 D 평가 비용도 별도다. 이번 진단을 값싼 온라인 특징으로 주장하지 않는다.

[모든 비교](planned_contrasts.csv) · [seed별 선택](selection_by_seed.csv) · [예측 오차](prediction_metrics.csv) · [조건부 구간](conditional_case_intervals.csv) · [task별 가치 추정](rollout_value_task_diagnostics.csv) · [반환 보정](held_seed_return_calibration.csv)

조건부 구간은 O 평가 사례만 재표집하고 정책·예측기·진단·선택은 고정한다. 학습 또는 모형 선택의 불확실성과 세 원래 seed 모집단의 효과를 포함하지 않는다.
