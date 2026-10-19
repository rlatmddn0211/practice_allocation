# 후보별 근거 기록 — 2026-10-15 ⑤ 완료 후

[33번 기록](../33_remaining_factor_queue_v1/factor_status_ko.md)과 [최초 기록](../25_candidate_factor_evidence_register_v1/README.md)을 보존한다. [전체 재검토](report_ko.md)는 과거 판정의 근거와 새 ⑤ 결과를 구분한다. 모든 수치는 탐색 결과이며 비용 포함 온라인 성공은 아직 없다.

| 후보 | 실행 상태 | 확인한 결과와 판정 | 남은 검증 |
| --- | --- | --- | --- |
| ① 초기 성능·취약성 | v27 분석 완료 | 초과 성공 사례 교체 −0.074%p, 채택 보류. 성능 profile은 필수 기준 | 실제 이른 진단의 추가 정보·새 원래 seed |
| ② 실제 학습 노출 | v30 분석 완료 | 주 증분 0.000%p. 노출 지연 존재와 추가 선택 가치를 구분 | 다른 노출 조건, sampling 인과 개입 |
| ③ 유용한 경험 | v30 및 v31 NearObject 보조 분석 완료 | 최근 성공 경험 −0.361%p; 공식 목표 접근 −0.352%p. 이번 표현 채택 보류 | 경험의 질을 조작한 대조, 새 초기 상태·짧은 진단 |
| ④ 업데이트 관계 | v28 분석 완료 | 주 +0.065%p는 한 원래 seed의 세 변경에서 발생. 채택 보류 | 선택 경계의 재현성·저비용 예측·인과 개입 |
| ⑤ 목표 정합성·가치 추정 | **v26 및 v31 측정·분석·검산 완료** | 기존 critic 0; 새 보정 −0.296%p. rollout 보조 +0.083%p, 소수 선택에 집중. 핵심 채택 보류 | 제한 rollout의 범위, 4k에서의 추가 가치·새 원래 seed·비용 포함 검증 |
| ⑥ 가소성 | v29 분석 완료 | 주 +0.074%p, 정적 보조 +0.102%p. 한 선택의 개선에 집중. 채택 보류 | 고정 목표 복제 fitting을 실제 학습으로 연결하는 검증 |
| ⑦ 신뢰도 | v24 분석 완료 | 주 +0.069%p, 진단 조건으로 유지. 작은 차이 규칙을 일관되게 넘지 못함 | 기본 배분 품질·진단 비용·새 seed에서의 신뢰도 규칙 |
| ⑧ 강도·혼합·순서 | v32 실제 학습 진행 중 | **효과 미판정** | 72개 분기와 사전 대조 전체·독립 검산 |

①②③④⑤⑥의 증분은 각자의 기준모형과 같은 반복의 36건 선택 비교다. ⑦은 과제당 두 사례·두 후속 반복의 20k로 다른 반복의 40k를 고르는 별도 규칙이며 고정 배분과의 차이다. 후보 순위로 합치지 않는다.

## ⑤의 새 완료 근거

- **환경·seed:** dense reward Meta-World 공유 SAC, A200/A400/B200/C200 × 원래 seed 11/12/13. A 후속 2101/2102/2103, B/C 2301/2302/2303. 12부모+180개 20k 정책.
- **측정:** 새 D20/task에서 deterministic 500-step, 같은 길이 성공·return; 두 초기 상태/task × 네 stochastic soft-value 경로. 원본 learner 불변. 보정식은 원래 seed 전체를 제외해서 적합.
- **주 결과:** CalibratedReturn−SuccessBase 같은 반복 −0.296%p, 다른 반복 −0.352%p. 같은 반복 세 원래 seed +0.083/+0.194/−1.167%p; A200/A400/B/C −1.333/0/−0.944/+0.722%p. 바뀐 여섯 선택 중 세 이득·세 손실. 선별 미통과.
- **불확실성:** 같은 반복의 고정 O 사례 95% 구간 [−0.704,+0.120]%p. 정책·진단·선택·모형 적합을 고정한 조건부 구간이며 새 seed 효과의 신뢰구간이 아님.
- **보조 결과:** RawReturn −0.935/+0.259%p, RolloutValue−RolloutBase +0.083/+0.306%p, NearObject −0.352/+0.028%p (같은/다른 반복). 보조 결과로 주 비교를 교체하지 않음.
- **현상:** 보상으로 같은 episode의 성공을 보정한 21 task/seed 비교 중 19개는 상수 기준보다 Brier 오차가 작음. 현재 성공 설명의 개선과 이후 선택 이득은 분리됨.
- **실제 비용:** 새 환경 10,752,000 step, 지속 update 0. 192개 본 측정 wall 합 21,641.75초·CPU 8,998.94초. 사전검사·bank·대기와 별도. 진단 trace 검산 192건/187,200항목의 성공 영수증 확인.
- **실패:** 본 측정 단계의 실패는 확인되지 않음. 기존 구현 사전검사의 두 실패는 [31번 이력](../31_fixed_horizon_alignment_v1/technical_failures_ko.md)에 보존. 이번 36번 검토 개발의 실패·정정은 [별도 이력](technical_notes_ko.md).
- **출처:** [동결 protocol](../31_fixed_horizon_alignment_v1/protocol.json), [원분석](../31_fixed_horizon_alignment_v1/results/20261015T100729Z_analysis_5fa7ae88/summary.json), [원검산](../31_fixed_horizon_alignment_v1/results/20261015T100734Z_verify_analysis_16d76b8c/summary.json), [측정 완료 영수증 목록](results/20261015T104602Z_review_0d1cb1b0/F05_measurement_receipts.csv), [이번 입력 hash](results/20261015T104602Z_review_0d1cb1b0/input_hashes.json).
- **판정:** 현재 보정·가치 지표는 핵심 요인 채택 보류. 가치 진단의 제한된 A200 양수 사례는 후속 가설로 보존. 추가 실행을 자동 승인하는 근거로 쓰지 않음.

## 이전 결과의 유지와 다음 판단

① [v27](../27_success_retention_screening_v1/report_ko.md), ②③ [v30](../30_exposure_experience_screening_v1/report_ko.md), ④ [v28](../28_gradient_update_screening_v1/report_ko.md), ⑤ critic [v26](../26_critic_signal_screening_v1/report_ko.md), ⑥ [v29](../29_neural_plasticity_screening_v1/report_ko.md), ⑦ [v24](../24_signal_reliability_screening_v1/report_ko.md)의 측정·비용·실패·불리한 결과와 한계를 유지한다. 해당 문서의 미완료 표기는 작성 시점의 역사 기록이며 최신 상태는 이 표를 따른다.

현재의 모든 후보가 이름 전체에 걸쳐 검증된 것은 아니다. 초기 설계의 공통 4k 진단, 지정된 상호작용, 구성 제외 검증, 새 원래 seed G3, 비용 포함 G4는 미완료다. ⑧은 구성별 원래 seed 12의 200k에서 후속 3801/3802/3803을 사용하는 72분기 대조로 계속 진행한다. 새 원래 seed의 확인과 구분한다.
