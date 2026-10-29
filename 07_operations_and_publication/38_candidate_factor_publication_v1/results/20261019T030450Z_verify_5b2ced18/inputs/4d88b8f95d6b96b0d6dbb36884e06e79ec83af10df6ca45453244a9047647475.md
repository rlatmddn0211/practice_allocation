# 후보별 근거 기록 — 2026-10-19 ⑧ 완료 후

[36번의 이전 기록](../36_all_candidate_evidence_review_v1/factor_status_ko.md)과 [25번 최초 기록](../25_candidate_factor_evidence_register_v1/README.md)을 보존한다. 실행 완료와 과학적 판정은 별도로 기록한다. 아래 “완료”는 실행한 운영 지표·대조의 완료이며, 후보의 모든 가능한 설명이나 비용 포함 배분 효과의 검증 완료를 뜻하지 않는다.

| 후보 | 실행 상태 | 현재 과학적 판정 | 이전 상세 근거·비용·제약 |
| --- | --- | --- | --- |
| ① 초기 성능·취약성 | v27 분석 완료 | 주 증분 −0.074%p, 채택 보류. ⑧의 다른 능력 손실을 기존 지표가 예측한 것은 아님 | [① 기록](../27_success_retention_screening_v1/report_ko.md) |
| ② 실제 노출 | v30 분석 완료 | 0.000%p. 수집량과 학습 노출의 차이는 존재; sampling 인과 개입 미실행 | [②③ 기록](../30_exposure_experience_screening_v1/report_ko.md) |
| ③ 유용한 경험 | v30·v31 보조 진단 완료 | 주 −0.361%p, NearObject −0.352%p. 이번 지표 채택 보류 | [②③ 기록](../30_exposure_experience_screening_v1/report_ko.md), [v31](../31_fixed_horizon_alignment_v1/results/20261015T100729Z_analysis_5fa7ae88/report_ko.md) |
| ④ 업데이트 관계 | v28 분석 완료 | +0.065%p, 큰 손익 상쇄·원래 seed 하나에 집중. 채택 보류 | [④ 기록](../28_gradient_update_screening_v1/report_ko.md) |
| ⑤ 목표 정합성·가치 | v26·v31 측정·분석·검산 완료 | 기존 critic 0, 새 보정 −0.296%p, rollout 보조 +0.083%p. 채택 보류 | [⑤ critic](../26_critic_signal_screening_v1/report_ko.md), [⑤ 완료 기록](../36_all_candidate_evidence_review_v1/factor_status_ko.md) |
| ⑥ 가소성 | v29 분석 완료 | 주 +0.074%p, 한 선택 개선에 집중. 채택 보류 | [⑥ 기록](../29_neural_plasticity_screening_v1/report_ko.md) |
| ⑦ 신뢰도 | v24 분석 완료 | 과제당 두 사례 주 규칙 +0.069%p. 진단 조건으로 유지, 핵심 채택 보류 | [⑦ 기록](../24_signal_reliability_screening_v1/report_ko.md) |
| ⑧ 강도·혼합·순서 | **v32 72분기·분석·독립 검산 완료** | **B 교대−혼합 +5.833%p, 3/3 양수; B 두 중간 비중 비선형 대조 3/3 양수. 조건 후보로 우선 유지. 독립 원래 seed·배분 효과 미검증** | [원분석](../32_dose_order_intervention_v1/results/20261016T071742Z_analysis_3cb34e0e/report_ko.md), [통합 해석](report_ko.md) |

①–⑥의 주 수치는 각자 기준모형과 같은 반복 36건의 선택 비교, ⑦은 별도 규칙과 고정 배분 비교다. ⑧은 실제 스케줄 대조이므로 숫자로 후보 순위를 매기지 않는다.

## ⑧ 완료 근거

- **실행:** 전체 campaign 2026-10-16 16:17:52 KST 완료. ⑧ A/B/C × 8조건 × 3후속 반복 = 72분기, 144학습 구간·full checkpoint. 생산 작업 완료 영수증의 실패는 0. [원검산](../32_dose_order_intervention_v1/results/20261016T071747Z_verify_analysis_3394c755/summary.json)
- **환경·seed:** dense reward Meta-World 공유 SAC, 기존 원래 seed 12·200k/구성. 후속 labels 3801/3802/3803과 파생 RNG stream은 같은 구성·반복의 8조건에서 짝지음. 과제 쌍 A DO/DC, B BP/DO, C PP/BP. 새 사전학습·독립 원래 seed는 없음.
- **측정·기준:** 40k 학습 후 fresh O100/task macro, 부모 정책 참고. 강도 25/43.75/62.5/81.25%; 순서 네 조건은 15k/15k/5k/5k 총량 동일. 사전 지정 대조 7개 × 3구성 모두 보고.
- **효과:** 교대−혼합 A −2.500, B +5.833, C −0.083%p. B 후속별 +4.50/+12.00/+1.00%p, 사례만의 95% 구간 [+4.583,+7.000]%p. B 43.75/62.5% 비중의 선형 보간 초과 +4.833/+6.083%p, 각각 세 반복 양수. [모든 대조](results/20261019T024708Z_review_cef06973/contrast_review.csv)
- **불리한·불확실한 결과:** B 순방향−역방향 +6.50%p지만 반복별 +9.75/−14.75/+24.50%p. A 집중 끝점 차이 −7.917%p는 큰 하락 반복 하나에 민감. C 강도 12분기의 PickPlace 성공률 모두 0%; 62.5% 한 분기의 ButtonPress 100→46%. C 19/24분기가 부모 미만, 8조건 평균 모두 부모 미만.
- **불확실성 범위:** 구성별 원래 seed 하나. 조건·과제쌍은 개발 자료로 선정. 고정 정책의 평가 사례 bootstrap만 사용하며 학습 seed·적합·사후 선택의 불확실성을 포함하지 않음. 21개 대조 다중 비교 보정 없음. 반복 하나 제외는 사후 기술적 민감도.
- **실제 비용:** 학습 2,880,000 step·SAC iteration, 평가 9,495,447 환경 step; bank 0 step. 학습/평가/bank wall 합 각각 57,410.03/17,601.69/82.02초, CPU 합 15,805.0625/7,043.15625/24.140625초. 기술 사전검사·분석·대기 비용과 별개이며 GPU busy time 미계측. [영수증](results/20261019T024708Z_review_cef06973/F08_cost_receipts.csv)
- **출처:** [동결 protocol](../32_dose_order_intervention_v1/protocol.json), [실행 계획](../33_remaining_factor_queue_v1/results/20261015T034631Z_remaining_0ce5f69e/plan.json), [O 원자료 경로·hash](results/20261019T024708Z_review_cef06973/outcome_provenance.csv), [전체 입력 hash](results/20261019T024708Z_review_cef06973/input_hashes.json), [분석 소스 hash](results/20261019T024708Z_review_cef06973/source_hashes.json). 원래 144 checkpoint 해시 검산은 v32 영수증 재사용, 이번에는 원시 평가·학습 episode·현재 실행 소스를 재확인.
- **새 검토 비용·실패:** 새 환경·학습 update 0. 본 분석 wall 6.367초·CPU 0.578초, 독립 검산 wall 0.277초·CPU 보고값 0.000초. 분석 검사 32,358/0, 독립 검산 33,842/0. 첫 그림의 설명문 겹침을 새 출력 폴더에서 수정했으며 이전 출력 보존. 탐색 중 경로·BOM 읽기 오류는 과학 실험 실패와 구분. [이력](technical_notes_ko.md)
- **다음 결정 기준:** B의 사전 대조·과제별 손익이 새 원래 seed에서도 반복되는지 확인할 것. 재현돼도 짧은 진단의 미래 예측과 비용 포함 배분을 별도 확인하기 전 핵심 요인으로 확정하지 않음. 후속 설계의 수치 기준은 실행 전 고정해야 하며 기존 탐색 기준을 확증 기준으로 바꾸지 않음.

## 기존 기록의 유지

①–⑦은 대부분 원래 seed 11/12/13, A200/A400/B200/C200의 12상태·9사전학습 이력을 재사용했다. 후속 A 2101/2102/2103, B/C 2301/2302/2303이다. v36의 효과 크기, 원래 seed별 결과, 조건부 구간, 비용, 실패 기록은 유지하며 이번 ⑧을 그 자료의 새 독립 원래 seed로 더하지 않는다.

특히 ⑤의 새 측정 10,752,000 환경 step·지속 update 0, ⑥의 본 복제 update 15,360회, 나머지 기존 자료 기반 분석의 추가 환경 비용을 ⑧과 혼동하지 않는다. 원래 각 분석 비용과 사전검사 비용은 위 상세 기록을 기준으로 한다. 이번에는 이전 자료의 선택 집계 재검산을 재사용했으며 모든 backward·simulator trace를 다시 실행하지 않았다.

계획한 후보 탐색 실행은 모두 끝났다. 공통 4k 진단 전체 패킷, 후보 상호작용, sampling 인과 개입, 구성 통째 제외 검증, G3 새 원래 seed, G4 동일 총예산 온라인 비교는 여전히 미실행이다. 제안의 기록은 후속 실행 승인으로 간주하지 않는다.
