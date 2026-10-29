# 59 — 새 미래 F3/F4 첫 확인 실험

2026-10-22 사용자가 58번의 고정 설계에 따른 기술검사와 첫 확인 묶음의 실행을 승인했다. 새 부모 확대는 이번 실행에 포함하지 않는다. [58번 통계 명세](../58_confirmation_prediction_preflight_v1/statistical_spec_ko.md)와 [예측 점검](../58_confirmation_prediction_preflight_v1/report_ko.md)을 보존한다.

| 항목 | 승인된 범위 |
|---|---|
| 출발 상태 | 기존 부모 41011–41015×prefix 4201/4202의 전체 8k 상태 10개 |
| 확인 미래 | 각 상태 F3·F4, 총 20개 |
| 일정·학습량 | 기존 BP dose625, 미래당 32k, 총 640k |
| 평가 | 기존 O100×4과제×20정책, 최대 4.0M step |
| 본 실험 상한 | 4.64M 환경 step |
| 기술검사 상한 | 모든 시도 합계 10k; 이번 기술검사 계획 최대 7k |
| 전체 상한 | 4.65M 환경 step |
| 실행·실패 | 단일 worker 순차 실행. 무결성 실패 시 중단, 자동 재시도 0 |

SAC·환경·평가·일정·checkpoint 코드는 52번에서 독립 복사했으며 바이트 동일성을 검사한다. 과거 버전에서 새 버전을 import하지 않고, 본 실행도 과거 버전의 Python 모듈을 import하지 않는다. 8k checkpoint에 저장된 Config와 의존성 버전을 유지한다.

## 고정 입력과 기술 관문

`inputs/protocol58.json`, `frozen_reference_predictions.csv`, `proposed_jobs.csv`, `state_manifest.json`을 원본 hash 그대로 복사했다. 프로토콜58의 실행 전 상태 표시는 과거 기록이며, **이번 실행 승인은 59번 protocol.json**에 별도로 기록한다. 분석의 모델·축소율·가중치·seeds·투자 기준은 바꾸지 않는다.

기술검사는 다음을 확인한다.

1. 모든 20개 F3/F4 분기에서 원래 8k의 네트워크·target·optimizer·entropy·replay·collector·일정 위치·누적 step을 정확하게 복원한다. 비난수 상태는 유지하고 지정한 활성 미래 난수만 바꾼다. 같은 상태의 F3/F4에서 보존된 시작 지문도 동일해야 한다. 환경 step은 0이다.
2. 미리 정한 한 상태에서 원래 난수로 500step씩 두 번 복원·학습해 행동·sample·loss trace와 전체 종료 지문이 일치하는지 확인한다. 비용 1k다.
3. 같은 한 상태의 F3와 F4 각각에서 1k 연속 학습과 500+저장·복원+500 학습의 trace·전체 종료 상태를 비교한다. 합계 4k다. 두 새 미래의 trace가 서로 및 원래 미래와 달라야 한다.
4. 원래 8k 정책을 새로 복원해 이미 평가한 사례 1개×4과제를 재현한다. 성공·return·길이·case seed·초기 상태 hash와 평가 전후 학습 상태 보존을 확인한다. 최대 2k다.

기술검사의 학습 결과는 본 실험으로 넘기지 않는다. 각 본 worker는 입력표의 원래 208k 전체 checkpoint를 다시 복원하고, 시작 환경 비용 0과 시작 지문을 기록한다. 저장·복원 비교용 기술 checkpoint는 연구 출발점으로 지정할 수 없다.

## 실행과 기록

기술검사를 통과한 동일 소스 지문만 campaign을 준비할 수 있다. 작업 순서는 원래 seed 570101로 고정한 CSV 순서다. F3·F4는 원래 같은 8k checkpoint에서 각각 시작하며 F3의 결과를 F4로 이어 학습하지 않는다. 절대 216k/224k/232k/240k에 전체 checkpoint를 무손실 저장한다. 총 80개이며 중간 정책 성능 평가는 없다.

`ACTIVE_CAMPAIGN.json`은 최신 campaign 위치만 가리킨다. 그 안의 `STATUS.json`, `jobs/*/*/progress.jsonl`, `costs.json`, `completed/`, 최종 `COMPLETE.json`으로 진행과 실제 비용을 확인한다. 모든 실행은 새 output 폴더와 실행 소스 snapshot/hash를 남기고, 실패·미완료 시도를 보존한다. 자동 재시도와 재부팅 후 자동 재시작 예약은 없다. 숨긴 background controller가 정해진 20개를 효과 방향과 무관하게 진행한다.

## 결과 해석

주 D는 새 F3/F4의 동일−교차 획득 중첩, G는 고정 M0−M1 Brier 오차다. 부모 안 DC·PU 적격 사례를 합쳐 평균하고 부모를 동일 가중한다. 주 예측 차이는 PU의49/548개 사례에 한정되며 DC의 G=0은 구조적 동일 예측이다. D와 G가 다른 과제에서 나오는 경우를 분리해 보고한다.

양의 조건부 근거와 투자 크기·견고성 기준을 따로 판정한다. 특정 M0 대비 개선을 모든 잠재 난이도 설명의 배제로 확대하지 않는다. 완료 결과의 과학적 분석은 고정 명세로 독립 후속 기록에 남긴다. 새 부모, C, 원래 2/3단계, 새 선택기·학습 알고리즘·원인 개입은 자동 실행하지 않는다.

이 README는 실행 전 동결 문서다. 현재 완료 여부는 기계 실행 기록을 확인한다. 시작 시점의 승인·범위는 [근거 기록](evidence_record_ko.md), 원본 복사 provenance는 `inputs/provenance.json`과 `inputs/copied_implementation.json`에 있다.
