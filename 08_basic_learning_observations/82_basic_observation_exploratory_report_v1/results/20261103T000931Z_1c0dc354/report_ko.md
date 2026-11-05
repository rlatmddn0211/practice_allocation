# 네 과제 기본 SAC 관측 — 탐색적 현상 정리

## 1. 실제 완료 범위와 핵심 관측

정상 완료 5/5 독립 초기학습 실행. 유효 정기 평가 3,200/3,200 에피소드. 이 분석은 81번의 같은 새 관측을 해석하며 별도의 독립 실험이 아니다.

| task | completed_final_runs | final_N | mean_final_success_pct | min_run_success_pct | max_run_success_pct | case_run_histories | histories_with_observed_loss | histories_with_observed_recovery | within_episode_any_success | within_episode_any_not_final | within_episode_success_exit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DO | 5 | 80 | 0.000 | 0.000 | 0.000 | 80 | 3 | 0 | 3 | 3 | 3 |
| DC | 5 | 80 | 100.000 | 100.000 | 100.000 | 80 | 14 | 14 | 687 | 53 | 74 |
| PU | 5 | 80 | 1.250 | 0.000 | 6.250 | 80 | 9 | 0 | 10 | 7 | 8 |
| BP | 5 | 80 | 92.500 | 87.500 | 100.000 | 80 | 45 | 41 | 397 | 143 | 167 |

실제 비용: {"train": 5000000, "evaluation": 1600000, "technical_invalid_retry": 4850, "optional_diagnostic": 0, "uncertain_issued": 0, "all_attempt": 6604850, "control_steps_unit": "actual single-environment action transitions; unmatched issued attempts charged conservatively"}

성공률은 원래 시작 상태의 고정 16사례 패널에서 측정했다. min/max는 독립 실행 사이의 관측 범위이며 신뢰구간이 아니다. 사례×실행 이력 수와 고유 물리 사례 수를 구분한다. 원래 보고서와 성공/실패·무변화 사례를 모두 보존한다.

## 2. 기본 학습과 평가·기록

81번의 실제 baseline_manifest/config_resolved/protocol/source snapshot을 따른다. DO/DC/Push/BP, v3 환경/v2 보상, 공통 과제조건부 기본 SAC만 사용했다. 8에피소드 블록마다 과제별 두 개를 섞는 기존 일정이며 새 curriculum·BC·KL·First·선택기를 넣지 않았다. 각 실행 1M 전이는 네 과제 합계이며 warm-up을 포함한다. 초기 가중치와 학습 난수는 별도 생성했으며 과거 부모에서 분기하지 않았다.

과거 루트 P0의 400k 설정은 다른 과제 구성인 suite A의 초기 구현 참고이며, 이번 네 과제 suite B의 직접 출처는 44번의 fresh 초기화·uniform 사전학습 코드와 이를 보존한 77번 복사본이다. 44번 suite B의 과거 사전학습 길이는 200k이고 이번 1M은 사용자가 새로 정한 관측 예산이다. U 스케줄과 상수 학습률은 총길이에 의존하지 않는다. 설치된 Meta-World wheel에서 VCS commit은 확인되지 않아 3.0.0 버전과 실제 소스/XML/모델 자산 해시로 고정했다.

평가는 과제당 16개 초기조건을 공통 사용한 탐색 패널이다. 표준 Meta-World 전체 goal 성능으로 부르지 않는다. 기존 deterministic CUDA 정책 경로를 사용하고, 이번 명세에 따라 최초 성공 이후에도 원래 환경의 정상 horizon까지 기록했다.

## 3. 과제별·실행별 결과

| run_id | task_id | N | success_pct | final_success_pct | mean_return |
| --- | --- | --- | --- | --- | --- |
| R01 | BP | 16 | 93.750 | 75.000 | 3788.308 |
| R01 | DC | 16 | 100.000 | 100.000 | 4851.875 |
| R01 | DO | 16 | 0.000 | 0.000 | 1683.524 |
| R01 | PU | 16 | 0.000 | 0.000 | 22.621 |
| R02 | BP | 16 | 87.500 | 62.500 | 3524.794 |
| R02 | DC | 16 | 100.000 | 100.000 | 4854.726 |
| R02 | DO | 16 | 0.000 | 0.000 | 2256.566 |
| R02 | PU | 16 | 0.000 | 0.000 | 20.121 |
| R03 | BP | 16 | 100.000 | 87.500 | 4206.673 |
| R03 | DC | 16 | 100.000 | 93.750 | 4497.077 |
| R03 | DO | 16 | 0.000 | 0.000 | 2527.761 |
| R03 | PU | 16 | 6.250 | 0.000 | 28.512 |
| R04 | BP | 16 | 87.500 | 87.500 | 3786.983 |
| R04 | DC | 16 | 100.000 | 100.000 | 4866.875 |
| R04 | DO | 16 | 0.000 | 0.000 | 2497.348 |
| R04 | PU | 16 | 0.000 | 0.000 | 23.118 |
| R05 | BP | 16 | 93.750 | 56.250 | 677.526 |
| R05 | DC | 16 | 100.000 | 93.750 | 4581.250 |
| R05 | DO | 16 | 0.000 | 0.000 | 1440.763 |
| R05 | PU | 16 | 0.000 | 0.000 | 20.980 |

전체 checkpoint와 계획/완료 분모는 learning_curves_all_runs.csv에 있다. 일부 seed·과제를 제외해 본평균을 재구성하지 않았다.

## 4. 사례별 행동 변화

학습 시점 사이의 관측된 획득·상실과 한 에피소드 안의 목표 상태 이탈을 분리했다. 각 인접 시점의 공통 유효 사례에서 G−L과 성공률 차이를 검산했다. 정확한 최초 능력 획득·상실 시점, 영구 능력 상실, 생애 최초 획득은 측정하지 않았다.

| task_id | run_id | histories | gain_events | loss_events | observed_recovery |
| --- | --- | --- | --- | --- | --- |
| BP | R01 | 16 | 23 | 8 | 7 |
| BP | R02 | 16 | 22 | 8 | 6 |
| BP | R03 | 16 | 31 | 15 | 12 |
| BP | R04 | 16 | 21 | 7 | 5 |
| BP | R05 | 16 | 32 | 17 | 11 |
| DC | R01 | 16 | 16 | 0 | 0 |
| DC | R02 | 16 | 16 | 0 | 0 |
| DC | R03 | 16 | 2 | 0 | 0 |
| DC | R04 | 16 | 5 | 5 | 5 |
| DC | R05 | 16 | 17 | 9 | 9 |
| DO | R01 | 16 | 0 | 0 | 0 |
| DO | R02 | 16 | 0 | 0 | 0 |
| DO | R03 | 16 | 0 | 0 | 0 |
| DO | R04 | 16 | 1 | 1 | 0 |
| DO | R05 | 16 | 2 | 2 | 0 |
| PU | R01 | 16 | 2 | 2 | 0 |
| PU | R02 | 16 | 1 | 1 | 0 |
| PU | R03 | 16 | 3 | 2 | 0 |
| PU | R04 | 16 | 2 | 2 | 0 |
| PU | R05 | 16 | 2 | 2 | 0 |

사례 예시는 결과를 본 뒤 정한 범주에서 ID 순으로 고른 기술 예시이며 빈도의 대표 표본이 아니다. contrasting_case_examples.csv에 선택 규칙과 반대/무변화 사례가 있고, 원래 trajectory/video 참조는 within_episode_observations.parquet에 있다.

## 5. 경험 사용과 학습 통계

replay_usage_uniform_opportunity.csv는 실제 사용 횟수와 기존 uniform FIFO replay에서 해당 전이가 표집될 수 있었던 기회를 함께 제시한다. 기대 사용량은 삽입 시점, warm-up, buffer 포화 및 실제 종료 시점에 조건화한 산술값이다. 최근 수집 자료의 작은 누적 사용량은 남은 표집 기회가 짧은 영향이 있으므로 자료가 무용하다는 뜻이 아니다. 표집 횟수는 정책 개선 기여량이나 중요도 가중치가 아니다.

loss/Q/alpha/gradient와 행동의 시간 정렬은 81번 learning_update_time_alignment 및 원본 업데이트 표에 있다. 자연 실행의 요약값으로 원인을 확정하거나 예측기를 학습하지 않았다.

## 6. 반복 현상과 경쟁 설명

| task | case_run_histories | histories_with_observed_loss | histories_with_observed_recovery | within_episode_success_exit |
| --- | --- | --- | --- | --- |
| DO | 80 | 3 | 0 | 3 |
| DC | 80 | 14 | 14 | 74 |
| PU | 80 | 9 | 0 | 8 |
| BP | 80 | 45 | 41 | 167 |

위 값이 0인 과제·실행도 그대로 남겼다. 반복 관측의 존재와 반복 범위를 구분한다. 다른 checkpoint의 최고 성능을 고른 값과 최종 성능 차이는 선택된 기술통계이며 학습이 본질적으로 악화됐다는 독립 검정이 아니다. 동일 사건을 관찰한 상태 구성, 평가 사례 난도, 정책 변화, 경험 노출은 경쟁 설명으로 남아 있다.

## 7. 추가 진단

이 파일 분석에서 신규 환경 reset/step, 정책 forward, 모델 로드, SAC 업데이트는 모두 0이다. 81번의 추가 진단 여부와 비용은 해당 campaign의 diagnostic_plan 및 FINAL_STATUS를 따른다. 새 진단을 자동 실행하지 않았다.

## 8. 비용·기술 한계·미측정

본학습·평가·기술 비용은 81번 원장으로 연결한다. 이 분석의 비용은 파일 I/O·연산·저장 및 wall time이며 환경 전이에 더하지 않는다. 64개 고유 초기조건과 5개 학습 실행을 3,200개 독립 표본으로 세지 않는다. 이 보고서에서 사후 CI/검정 검색은 수행하지 않았다. 수치 궤적은 제어 step 끝의 물리 상태이며 모든 내부 substep을 측정한 것은 아니다. snapshot의 복원 주장은 원래 기술 영수증에 명시한 동일 runtime 검증 범위에 한정한다.

## 9. 후속 질문 후보

관측된 성공 교체가 특정 상태·행동의 변화와 반복해서 대응하는지, 에피소드 내 성공 이탈과 학습 시점 간 상실이 같은 사례에 집중되는지, 경험 수집과 사용의 차이가 단순한 표집 기회 차이를 넘어 행동 변화와 연결되는지를 더 구체화할 수 있다. 현재 기록은 후속 후보를 만들기 위한 자료다. 분기점 선택·복귀·기초동작·경험 선택 방법을 이번 결과만으로 채택하지 않는다.

## 원본 및 재분석 위치

81번 campaign: C:\Users\SS\Projects\robot_practice_allocation\81_basic_sac_observation_campaign_v1\results\20261102T085036Z_observation_8e858967

81번 원 보고서: C:\Users\SS\Projects\robot_practice_allocation\81_basic_sac_observation_campaign_v1\results\20261102T085036Z_observation_8e858967\analysis\20261103T000632Z_f77754\report_ko.md

입력 해시는 input_receipt.jsonl, 원 라벨은 evaluation_outcomes.parquet, 모든 사례 이력과 반대 사례는 동봉 CSV에 있다. 대형 원 궤적·영상·checkpoint는 원래 위치를 참조하며 중복 ZIP하지 않는다.
