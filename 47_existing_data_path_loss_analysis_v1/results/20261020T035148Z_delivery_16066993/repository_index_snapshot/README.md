# Robot practice allocation

사전학습된 공유 정책에 제한된 추가 연습을 배분할 때, 현재의 실패율과
추가 학습의 가치가 일치하는지

설계 기준: [로컬 파일럿 설계 v0.1](LOCAL_PRACTICE_ALLOCATION_PILOT_DESIGN_20261007.md).

## 현재 연구 질문과 후보 요인

현재 중심 질문은 **강한 고정 연습 방법을 넘어서는 선택 가치가 어떤 학습 상태에 존재하며,
그 가치를 알아내는 진단 비용을 회수할 수 있는가**입니다.
반복 가능한 선택 여지가 있는지, 결정 시점의 정보로 그 선택을 알아낼 수 있는지,
정보 획득 비용을 지불한 뒤에도 동일 총예산의 최종 전체 과제 성능이 높은지를 차례로 검증합니다.
기존 국소 학습·전이 신호의 예측 실패 분석은 이 세 질문의 근거와 후보 정보로 유지합니다.

현재의 세 가지 기본 후보 요인은 다음과 같습니다. 아직 최종 이득의 원인이나
유효한 배분 기준으로 확정된 것은 아닙니다.

| 후보 요인 | 측정하려는 것 |
|---|---|
| 학습 반응성 | 짧게 더 연습했을 때 해당 과제가 얼마나 개선되는가 |
| 다른 능력의 변화 | 그 연습으로 다른 과제의 성능이 얼마나 좋아지거나 떨어지는가 |
| 효과의 지속성 | 연습을 이어갈수록 개선 속도가 유지되는가, 포화되거나 역전되는가 |

검증은 **후보 요인 정의 → 의사결정 시점에 가능한 측정 → 새로운 출발 상태에서
최종 이득 예측 → 비용을 포함한 실제 배분 비교** 순서로 진행합니다.
예측력이 높아지는 것과 최종 성능이 좋아지는 것은 각각 확인합니다.
기존 탐색의 Uniform·실패율 기준과 구분해, 다음 연구는 강한 고정 방법 및
진단 정보를 무시하는 대조를 중심으로 비교합니다. 추가 학습 전 정책도 성능 유지의 참고점으로 둡니다.

## 추가 후보 1–8: 역할·검증 결과·해결 방향

2026-10-19 기준 예정한 후보 탐색 실행은 완료했습니다. 후보별로 무엇을 설명하려는지,
어떤 검증에서 무엇이 나왔는지, 다음에 무엇을 확인해야 하는지는
[후보별 상세 안내](38_candidate_factor_publication_v1/candidate_guide_ko.md)에 정리했습니다.
아래 해결 방향은 후속 검증 제안이며, 이미 효과가 확인된 해결책은 아닙니다.

| 후보 | 기여하려는 부분 | 실행한 검증 결과 | 해결을 위해 다음에 확인할 것 |
| --- | --- | --- | --- |
| ① 출발 성능·취약성 | 개선 여지와 다른 능력 손실 위험 구분 | 초과 성공 사례 교체 −0.074%p, 채택 보류 | 초기 성능을 유지하고 이른 손실 위험 지표의 새 상태 추가 가치 확인 |
| ② 실제 노출·replay 지연 | 수집한 연습이 업데이트에 반영되는 정도·지연 | 지연 관찰, 추가 선택 이득 0.000%p | 단순 배분·시간을 넘는 정보와 sampling 인과 대조를 분리 |
| ③ 유용한 경험·탐험 | 추가 연습으로 필요한 경험을 얻을 가능성 | 최근 성공 경험 −0.361%p, 목표 접근 보조 −0.352%p | 성공률·return 이후에도 남는 경험의 질을 구체화·검증 |
| ④ 업데이트 방향·크기 | 다른 과제에 대한 전이·손실 예측 | +0.065%p, 원래 seed 하나의 큰 손익 상쇄 | 짧은 실제 학습에서 방향의 지속과 큰 손실 예측을 확인 |
| ⑤ 목표 정합성·가치 | reward·critic 신호와 성공률 목표의 연결 | critic 0, 새 보정 −0.296%p, rollout 보조 +0.083%p | 현재 성공 설명과 미래 선택 가치를 분리하고 진단 비용 회수 확인 |
| ⑥ 가소성 | 새 경험에 적응할 수 있는 능력 | 주 +0.074%p, 정적 보조 +0.102%p, 소수 선택에 한정 | 복제 fitting이 실제 SAC 반응·새 상태 선택으로 이어지는지 확인 |
| ⑦ 신호 재현성·배분 차이 | 진단·추가 측정·기본 배분 유지의 판단 | 두 사례 주 규칙 +0.069%p, 진단 조건으로 유지 | 학습 변동·기본 배분 품질·진단 비용을 함께 평가 |
| ⑧ 강도·혼합·순서 | 비중·전환 주기·순서의 행동 구조 | B 교대−혼합 +5.833%p, 3/3 양수; A/C 우위 없음 | 새 원래 seed 재현 → 이른 예측 → 동일 총예산 실제 배분 비교 |

①–⑥은 각자 다른 기준모형에 지표를 추가한 선택 이득, ⑦은 별도 규칙과 고정 배분의 차이,
⑧은 실제 스케줄 대조입니다. 이 수치로 후보 순위를 매기지 않습니다.
위 표는 2026-10-19까지의 개발 자료 판정입니다. 2026-10-20 새 부모 5개의 후속 검증에서는
반복 가능한 부모별 일정 선택의 이득을 확인하지 못했습니다. 현재 최종 핵심 예측 요인은 선정하지 않았습니다.
[새 선택 가치 결과와 ①·⑦·⑧의 근거 갱신](45_stage1_selection_value_analysis_v1/evidence_record_ko.md),
[A 분석의 경로 차이·성공 상실·초반 신호 한계](47_existing_data_path_loss_analysis_v1/evidence_record_ko.md),
[1–8 기존 통합 원장](37_f08_integrated_candidate_review_v1/factor_status_ko.md)과
[공개 범위·재현 안내](38_candidate_factor_publication_v1/publication_scope_ko.md)를 함께 제공합니다.

2026-10-19 사용자 피드백을 반영한 최신 명세는 [43번 수정 설계](43_feedback_revised_selection_protocol_v1/research_protocol_ko.md)입니다.
**반복 가능한 선택 가치 → 같은 8k 상태에서 실제 유지·전환과 신호 식별 → 새 부모에서 진단 비용 회수**를 구분합니다.
교대−혼합 평균 우위만으로 전체 연구의 진행을 판정하지 않습니다.
[39번 원안](39_next_research_decision_plan_v1/research_plan_ko.md)과
[41번 최초 세 단계 설계](41_selection_value_three_stage_protocol_v1/research_protocol_ko.md)는 보존합니다.

첫 단계는 [44번 독립 수정 구현](44_selection_value_stage1_checkpoint36_v2/README.md)에서
**2026-10-20 04:44 KST에 245/245작업 완료**했습니다. 새 B 부모5개·후속 반복2개·BP/교대/혼합의
30분기와 부모 포함35개 정책 O100을 평가했습니다. 연구 학습2.2M·평가4.797719M으로 실제 환경 비용은6.997719M step입니다.
42번 완료 상태를 검증해 인계했으며 **36k 전체 checkpoint 30개**와 기존 결과를 보존합니다.
기술 검사 비용은 별도입니다.

[45번 상세 분석](45_stage1_selection_value_analysis_v1/report_ko.md)의 최종 평균은
BP 집중34.075%, 교대33.975%, 혼합33.000%입니다.
반복·평가 반쪽을 분리한 부모별 선택은 BP 대비 **−2.850%p**, 부모 제외 고정 방법 대비 **−1.500%p**였고,
부모를 완전히 제거한 뒤 고정 기준을 다시 선정해도 이득이 음수였습니다.
**사전 지정한 2단계 투자 기준은 미통과**입니다. 이는 같은8k 상태에서의 실제 전환 가치나
모든 적응형 선택의 부재를 증명한 결과가 아닙니다. 실행 완료·과학적 진행 판정·미실행 단계는 구분합니다.

2단계는 **잔여28k**와 점수 하나·26개 유한 규칙 후보를 사용하며, 조건부 개발 평가로 해석합니다.
3단계는 **진단 없는 고정 유지/전환·진단 기반 선택·진단 후 항상 유지/전환**의 다섯 방법을 비교합니다.
[피드백 항목별 채택 판단](43_feedback_revised_selection_protocol_v1/feedback_disposition_ko.md)에 작은 명세 보완과 실제 분석 변경을 구분했습니다.
2026-10-20 사용자 판단에 따라 **기존2·3단계 진입은 보류**합니다.예약된 후속 학습은 없습니다.

새 제안은 [46번 경로 변동·추가 학습 손실 설계](46_post_stage1_path_loss_design_v1/research_plan_ko.md)입니다.
동일 반복 내/다른 반복의 선택,평가 사례 불확실성,성공 획득·상실과 학습 로그를 **새 환경 step 없이** 먼저 분석하도록 정했습니다.
이후 필요한 경우에만 BP8k 정책10개 평가(상한2M),같은8k 상태에서 새 미래를 반복하는 지속/보존 비교,
조건부 전환 비교를 제안합니다.

2026-10-20 승인한 **A1–A3 기존 자료 분석은 [47번에서 완료](47_existing_data_path_loss_analysis_v1/report_ko.md)**했습니다.
같은 후속 반복의 다른 평가 사례로 선택을 채점하면 BP 대비 **+2.775%p**,
다른 후속 반복으로 옮기면 **−2.850%p**입니다.
41014의 BP–교대·BP–혼합 우열 반전은 45개 대비의 동시 평가 사례 구간 기준을 충족했습니다.
BP 집중의 평균 순변화 +0.375%p는 신규 성공 +5.750%p와 기존 성공 상실 −5.375%p의 합입니다.
반면 사전 TD 증가 점수의 수치 임계값은 BP 10경로 모두에서 ‘지속’으로 동일해,
초반 상태를 구분하는 규칙을 확보한 것은 아닙니다.
**새 환경 step·SAC update는 0**이며 B·C와 기존2·3단계는 미실행·미예약 상태입니다.
원래1단계의 관문 미통과는 유지합니다.

## 연구 경과와 근거

E0–E3는 후보를 세우는 탐색 근거입니다. B에서는 ButtonPress 고정 집중이 강했고,
C에서는 기존 능력의 손실이 중요했습니다. 현재까지의 질문 변화와 관찰·가설의 구분은
[연구 구체화 과정](22_candidate_factor_grounding_v1/research_development_ko.md)에 기록합니다.
실제 replay 노출, 탐험 경험, 업데이트 관계, 가치 추정, 가소성, 신호의 신뢰도와
배분 순서에 관한 [추가 후보 검토](22_candidate_factor_grounding_v1/candidate_factors_ko.md)는
기본 세 요인을 설명하거나 보완할 탐색 가설로 구분합니다.

각 후보의 측정·대조·탈락 기준과 최종 선정 절차는
[8개 후보 구체화 설계](23_candidate_factor_screening_design_v1/research_design_ko.md)에 있습니다.
기존 자료와 공통 진단에서 후보를 좁힌 뒤, 새 원래 seed의 예측 확인과
진단 비용을 포함한 실제 배분 검증을 거치는 제안입니다. 아래 기존 자료 분석과 별개로,
설계의 공통 4k 진단·새 seed 확인 실험은 아직 실행하지 않았습니다.

추가 후보 ⑦의 [신호 재현성 분석](24_signal_reliability_screening_v1/report_ko.md)은 완료했습니다.
기존 12개 출발 상태의 평가를 재분석했으며 새 학습·환경 평가는 없습니다.
신뢰도 규칙은 진단 조건으로 유지하되, 핵심 배분 요인으로의 승격은 보류했습니다.

⑤의 [critic 진단 1차 검증](26_critic_signal_screening_v1/report_ko.md)도 완료했습니다.
192개 기존 모델을 측정했으나, 두 critic 지표를 추가해도 주 비교 36건의 선택이 모두 같았고
추가 선택 이득은 0.00%p였습니다. 이번 critic 지표의 핵심 요인 채택은 보류합니다.

그 나머지의 [31번 독립 진단](31_fixed_horizon_alignment_v1/README.md)은
2026-10-15 19:07 KST에 192개 모델 측정·분석·독립 검산까지 완료했습니다.
동일 500-step return→성공 보정의 주 추가 선택 이득은 −0.296%p로 선별 미통과입니다.
가치 rollout 보조 비교는 +0.083%p지만 한 선택의 개선에 집중됐습니다.
보상으로 같은 평가 에피소드의 성공 여부를 설명하는 것과 미래 배분 이득을 예측하는 것은
구분해야 한다는 [새 근거와 한계](36_all_candidate_evidence_review_v1/report_ko.md)를 기록했습니다.

①의 [기존 성공 보존·사례 교체 검증](27_success_retention_screening_v1/report_ko.md)과
④의 [gradient·Adam 업데이트 검증](28_gradient_update_screening_v1/report_ko.md)도 완료했습니다.
과제별 성공률을 통제한 F01의 추가 선택 이득은 −0.074%p,
critic 진단까지 통제한 F04는 +0.065%p로 한 원래 seed에 한정됐습니다.
둘 모두 이번 지표의 핵심 요인 채택은 보류합니다. 새 환경 실행이나 원본 학습 상태 변경은 없습니다.

⑥의 [가소성 후보 검증](29_neural_plasticity_screening_v1/report_ko.md)도 완료했습니다.
192개 기존 모델에서 활성 구조와 복제 20회 학습 반응을 측정했습니다.
첫 업데이트 반응까지 통제한 주 추가 선택 이득은 +0.074%p로 한 원래 seed의 한 선택에
한정됐고, 별도 정적 지표는 +0.102%p였습니다. 이번 지표의 핵심 요인 채택은 보류합니다.
critic의 같은 replay 자료 적합이 다른 episode 자료의 개선으로 이어지지 않는 경우를
관찰했지만, 이를 보정한 비용 포함 배분 개선은 아직 확인하지 못했습니다.

② 실제 노출과 ③ 최근 성공 경험의 [추가 예측·선택 검증](30_exposure_experience_screening_v1/report_ko.md)도 완료했습니다.
기존 192개 checkpoint를 분석한 주 추가 선택 이득은 각각 0.000%p와 −0.361%p로,
이번 요약 지표의 채택은 보류합니다. 새 환경 step·학습 update는 0입니다.

후속 부분은 [33번 자동 실행기](33_remaining_factor_queue_v1/README.md)에서
2026-10-16 16:17:52 KST에 **424/424작업 완료**했습니다.
⑤의 새 진단 10.752M 환경 step과 분석·검산,
⑧의 [강도·순서 대조](32_dose_order_intervention_v1/README.md) 72분기·2.88M 추가 학습·분석·검산을 모두 마쳤습니다.
⑧은 구성 A/B/C의 기존 원래 seed 12·200k와 후속 seed 3801/3802/3803을 사용합니다.
실행 상태는 [활성 campaign](33_remaining_factor_queue_v1/ACTIVE_CAMPAIGN.json)에서 확인합니다.

8개 후보의 현재 결과와 판정은 [최신 후보별 근거 기록](37_f08_integrated_candidate_review_v1/factor_status_ko.md)에
모았습니다. 분석 완료·관찰 확인·효과 미검증을 구분하고, 불리한 결과와 한계,
출처·비용·다음 검증 조건을 함께 보존합니다. 현재 어느 추가 후보도 진단 비용을 포함한
실제 배분 개선 요인으로 최종 검증되지 않았습니다. [첫 근거 기록](25_candidate_factor_evidence_register_v1/README.md)도 보존합니다.

완료된 ①·②·③·④·⑥·⑦의 [종합 단서 검토](34_completed_factor_clue_review_v1/report_ko.md)에서는
측정 반복성과 최종 선택 가치의 간극, 작은 예측 차이로 바뀐 선택의 큰 손익,
일부 후보의 정보가 제한되는 출발 상태를 확인했습니다. 기존 판정을 유지하며,
후보별 다른 기준모형과 같은 과거 자료의 재사용을 구분했습니다. 새 학습·환경 평가는 없습니다.

⑤까지 완료한 뒤의 [전체 재검토](36_all_candidate_evidence_review_v1/report_ko.md)에서는
①–⑦의 결과와 ⑧의 진행 상태를 함께 정리했습니다. 새 보상 보정은 현재 에피소드의 성공
설명에서 21개 task/seed 비교 중 19개를 개선했지만, 최종 배분의 주 선택 이득은 음수였습니다.
서로 다른 여섯 주 비교에서 선택을 바꾼 조건의 합집합은 10/36개였습니다.
최종 핵심 요인은 아직 선정하지 않았으며, 이른 진단·새 원래 seed·동일 총예산 검증은 미완료입니다.

⑧ 완료 후의 [①–⑧ 통합 해석](37_f08_integrated_candidate_review_v1/report_ko.md)에서는
B의 4k 교대−혼합 차이 +5.833%p가 세 후속 반복 모두 양수였고,
중간 강도의 비선형 반응도 세 반복에서 양수임을 확인했습니다.
A/C에서는 같은 스케줄 우위가 재현되지 않았고, 큰 평균 차이 일부는 다른 과제의 급락에 민감했습니다.
구성별 원래 seed 하나의 개발 실험이므로 ⑧을 우선 추적할 조건 후보로 유지하며,
이를 예측하는 요인이나 비용 포함 배분 개선을 확정하지 않았습니다.

## 독립 버전

| 폴더 | 목적 | 실행 범위 |
| --- | --- | --- |
| [01_implementation_validation_v1](01_implementation_validation_v1/README.md) | 최초 구현과 재현성 검증 | CPU·CUDA 각각 10/10 검사 통과, P0 미실행 |
| [02_p0_uniform_pretraining_v1](02_p0_uniform_pretraining_v1/README.md) | P0 균등 사전학습 | seed 901·CUDA·400k 완료, 공개 진단 macro 61.25% |
| [03_p0_pretraining_analysis_v1](03_p0_pretraining_analysis_v1/README.md) | P0 결과와 구현·평가 자료 분석 | 과제별 성능·짝지은 변화·불확실성·실제 학습 노출 확인, 68/68 검사 통과 |
| [04_p0_allocation_branches_v1](04_p0_allocation_branches_v1/README.md) | 동일 200k 출발점의 추가 연습 배분 비교 | 5개 배분 × 후속 seed 1901·1902, 분기당 40k; 10/10 완료, 원자료 검사 367/367 통과 |
| [05_results_github_archive_v1](05_results_github_archive_v1/README.md) | 전체 실험 결과의 GitHub 보관 | 01~04와 저장소 문서 1,425개 파일, 모델 checkpoint 39개 포함; 5개 ZIP의 원본 SHA-256 대조 통과 |
| [06_p0_branch_replication_v1](06_p0_branch_replication_v1/README.md) | 같은 200k 출발점의 후속 seed 재현성 확인 | seed 1903·1904·1905 × 5개 배분 × 40k, 총 15분기·600k; 2026-10-08 14:14 KST 완료 |
| [07_p0_replication_analysis_v1](07_p0_replication_analysis_v1/README.md) | 새 세 반복의 독립 검증·결과 해석 | 원자료·출처 검사 1,127/1,127 통과; 새 세 반복을 우선 보고하고 기존 두 반복·전체 다섯 반복을 구분; 대화형 보고서와 PNG·SVG |
| [08_followup_experiment_design_v1](08_followup_experiment_design_v1/README.md) | 현재 관찰을 바탕으로 한 후속 실험 설계 | 동결한 E0~E4·선택적 R 설계; E0~E3 실행은 09~13에서 관리 |
| [09_fresh_evaluation_audit_v1](09_fresh_evaluation_audit_v1/README.md) | E0 새 평가 사례와 Failure 측정 점검 | 기존 부모·25분기 재평가, 학습 없이 평가 10,800회 |
| [10_independent_seed_checkpoint_study_v1](10_independent_seed_checkpoint_study_v1/README.md) | E1 독립 사전학습 seed와 시점 | 원래 seed 11·12·13, 200k·400k 출발, 90분기·4.80M 학습 |
| [11_fixed_target_donor_swap_v1](11_fixed_target_donor_swap_v1/README.md) | E2 목표 과제 수집량 고정 | E1 200k 재사용, DC/WO 배분 교환, 27분기·1.08M 학습 |
| [12_task_composition_study_v1](12_task_composition_study_v1/README.md) | E3 과제 구성 변경 | B·C 조합 각각 3개 원래 seed, 90분기·4.80M 학습 |
| [13_e0_e3_autonomous_queue_v1](13_e0_e3_autonomous_queue_v1/README.md) | 승인된 E0→E1→E2→E3 자동 실행 | 총 10.68M 학습·207분기·194,400 평가, 20k 저장과 무인 재시작 |
| [14_power_interruption_audit_v1](14_power_interruption_audit_v1/) | 전원 중단 시점과 보존 자료 감사 | 원래 자료를 바꾸지 않는 실행 이력 점검 |
| [15_verified_power_loss_recovery_v1](15_verified_power_loss_recovery_v1/) | 검증한 checkpoint에서 실행 복구 | 중단 시도 보존과 독립 복구 검사 |
| [16_e0_e2_results_analysis_v1](16_e0_e2_results_analysis_v1/) | 완료 E0–E2의 원자료 재계산 | 259개 분기 평가 행과 공개 규칙·donor 비교 |
| [17_e0_e2_detailed_research_report_v1](17_e0_e2_detailed_research_report_v1/README.md) | E0–E2 상세 연구 보고서 | 과제별 손익·seed 변동·horizon·선택 규칙·비용 |
| [18_practice_allocation_literature_review_v1](18_practice_allocation_literature_review_v1/README.md) | 기존 연구와 정밀 비교 | 핵심 12편과 인접 6편, 차별화 후보와 한계 |
| [19_budgeted_practice_research_feasibility_v1](19_budgeted_practice_research_feasibility_v1/README.md) | 국소 신호와 최종 성능 예측의 연구 가능성 | 기존 E1 재분석·단순 보정의 실패·비용 포함 검증안; 새 RL 실행 없음 |
| [20_e0_e2_github_publication_v1](20_e0_e2_github_publication_v1/README.md) | E0–E2 원자료와 전체 checkpoint 보관 | 112,800 평가 행, 18,123 원본 파일, 참조된 전체 checkpoint 323개 |
| [21_e3_completed_results_analysis_v1](21_e3_completed_results_analysis_v1/README.md) | 완료 E3의 원자료 검증과 연구 해석 | 90분기·81,600 평가 행·246개 전체 checkpoint 검증; 구성·seed별 손익과 선택 규칙 |
| [22_candidate_factor_grounding_v1](22_candidate_factor_grounding_v1/README.md) | 연구 구체화 과정과 후보 요인의 근거 | 기본 세 요인과 추가 후보의 측정 가능성·문헌 근거·검증 기준; 새 RL 실행 없음 |
| [23_candidate_factor_screening_design_v1](23_candidate_factor_screening_design_v1/README.md) | 8개 추가 후보의 측정과 최종 선정 설계 | 후보별 지표·통제·반증 기준, 독립 확인, 소형 진단과 비용 포함 배분 비교; 설계만 작성 |
| [24_signal_reliability_screening_v1](24_signal_reliability_screening_v1/README.md) | F07 신호의 재현성과 배분 차이 | 148,800개 기존 평가 행, 사례·후속 seed·시점 변동과 신뢰도 규칙 분석; 새 환경 step 0 |
| [25_candidate_factor_evidence_register_v1](25_candidate_factor_evidence_register_v1/README.md) | 후보별 결과·근거·판정 보존 | 8개 후보의 실행 상태와 과학적 판정, F02·F07 결과, 한계·다음 검증 조건·기록 양식 |
| [26_critic_signal_screening_v1](26_critic_signal_screening_v1/README.md) | F05 critic 진단의 추가 예측·선택 가치 | 기존 모델 192개·replay 1,572,864개 측정, 원래 seed 제외 비교; 추가 선택 이득 0.00%p, 새 환경 step 0 |
| [27_success_retention_screening_v1](27_success_retention_screening_v1/README.md) | F01 기존 성공의 상실·사례 교체 | 148,800개 기존 평가 행, 과제별 성능 통제 이후 추가 선택 이득 −0.074%p; 핵심 요인 채택 보류 |
| [28_gradient_update_screening_v1](28_gradient_update_screening_v1/README.md) | F04 task별 gradient·Adam 방향과 크기 | 192개 모델, gradient 24,576회·복제 Adam 12,288회; 주 추가 선택 이득 +0.065%p, 핵심 요인 채택 보류 |
| [29_neural_plasticity_screening_v1](29_neural_plasticity_screening_v1/README.md) | F06 활성 구조·복제 학습 적응성과 최종 선택 | 192개 모델·본 측정 복제 update 15,360회; 주 추가 선택 이득 +0.074%p, 정적 +0.102%p, 핵심 요인 채택 보류 |
| [30_exposure_experience_screening_v1](30_exposure_experience_screening_v1/README.md) | F02 실제 노출·F03 성공 경험의 추가 선택 가치 | 192개 checkpoint 분석 완료; 주 이득 0.000/−0.361%p, 독립 검산 13,196개 통과 |
| [31_fixed_horizon_alignment_v1](31_fixed_horizon_alignment_v1/README.md) | F05 동일 길이 목표 정합성·rollout 가치 진단 | 192개 모델·10.752M 환경 step 완료, 지속 학습 0; 주 보정 −0.296%p, 독립 검산 10,710개 통과 |
| [32_dose_order_intervention_v1](32_dose_order_intervention_v1/README.md) | F08 실제 수집 강도·순서 대조 | 72분기·2.88M 학습·9.495M 평가 step 완료; 144 checkpoint 독립 검산, B 교대−혼합 +5.833%p의 개발 근거 |
| [33_remaining_factor_queue_v1](33_remaining_factor_queue_v1/README.md) | 미실행 후보의 자동 진단·학습·분석·검산 | 2026-10-16 16:17:52 KST 424/424작업 완료; 본 campaign 환경 23.127M step |
| [34_completed_factor_clue_review_v1](34_completed_factor_clue_review_v1/README.md) | 완료 후보의 공통 단서·선택 변경 사례 검토 | 다섯 주 비교의 변경 조건 합집합 7/36, 작은 예측 차이의 큰 손익·critic 간극 사후 관계 검토; 판정 유지 |
| [35_remaining_factor_progress_audit_v1](35_remaining_factor_progress_audit_v1/README.md) | 진행률·무결성·완료 시간 중간점검 | 2026-10-15 13:52 KST 기준 ⑤ 30/192 검산 완료, 본 실행 오류 0; 실측 기반 시간 추정 |
| [36_all_candidate_evidence_review_v1](36_all_candidate_evidence_review_v1/README.md) | ⑤ 완료를 포함한 후보 전체 정밀 재검토 | 완료 ①–⑦의 증분·변경 사례·비용 검토, ⑤ 원시 진단 CSV 재검산; 최종 요인 채택 보류, ⑧ 진행 중 |
| [37_f08_integrated_candidate_review_v1](37_f08_integrated_candidate_review_v1/README.md) | ⑧ 완료 후 ①–⑧ 통합 해석 | 30,000개 O 기록·72분기·21대조 재검산; B의 교대·강도 비선형성, 다른 능력의 큰 손실과 반복 변동을 구분; 새 원래 seed·비용 포함 효과 미확인 |
| [38_candidate_factor_publication_v1](38_candidate_factor_publication_v1/README.md) | 후보별 역할·결과·해결을 위한 검증 방향의 GitHub 공개 | ①–⑧의 기여 대상·실제 측정·불리한 결과·다음 채택 조건 안내; 기존 코드·결과·근거 기록과 연결, 새 실험 없음 |
| [39_next_research_decision_plan_v1](39_next_research_decision_plan_v1/README.md) | 후보 검증 이후의 가설·단계별 진행/보류 판단 | B의 제한된 재현 32분기 제안, 이른 예측 실패의 직접 측정·강한 고정 기준·비용 포함 배분·적용 범위 확장; 미실행 |
| [40_research_progress_external_review_v1](40_research_progress_external_review_v1/README.md) | 지금까지의 연구를 외부 평가자에게 전달하는 종합 보고서 | 초기 설계부터 E0~E3·후보 ①~⑧·비용·부정적 결과·외부 설계 비평·미실행 후속안까지 17개 절로 종합; 새 실험 없음 |
| [41_selection_value_three_stage_protocol_v1](41_selection_value_three_stage_protocol_v1/README.md) | 선택 가치·결정 시점의 식별·진단 비용 회수를 분리한 수정 설계 | 39 원안 보존; 부모 5개·30분기, 공통 8k 실제 전환, 새 부모 동일 총예산 대조의 순차 판정 |
| [42_fixed_schedule_selection_value_v1](42_fixed_schedule_selection_value_v1/README.md) | 첫 단계의 고정 일정 비교와 반복 가능한 부모별 선택 여지 | 독립 SAC 구현·전체 상태 저장·원시 결과 자동 분석; 5개 새 부모, 30분기, 2.2M 학습 step |
| [43_feedback_revised_selection_protocol_v1](43_feedback_revised_selection_protocol_v1/README.md) | 피드백별 적합성 판단과 세 단계 수정 명세 | 36k 저장·부모 제외 재적합·잔여28k 규칙 개발·진단 후 항상 전환 및 진단 없는 고정 전환 대조 |
| [44_selection_value_stage1_checkpoint36_v2](44_selection_value_stage1_checkpoint36_v2/README.md) | 1단계 36k 저장과 수정 분석의 독립 실행 | 42번 완료 상태 인계, 30분기·동일 과학적 학습 예산 유지, 전체 부모 제외 재계산과 유한 규칙 명세 검증 |
| [45_stage1_selection_value_analysis_v1](45_stage1_selection_value_analysis_v1/README.md) | 완료1단계 결과와 독립 재집계 | 선택−BP −2.850%p,선택−부모 제외 고정 −1.500%p;진행 기준 미통과,과제별 손익·반복성·한계 기록 |
| [46_post_stage1_path_loss_design_v1](46_post_stage1_path_loss_design_v1/README.md) | 기존2·3단계 보류 후의 경로 변동·손실 연구 설계 | 기존 자료 분석0 step → 조건부8k 평가2M → 같은 상태의 미래 반복;설계만 완료,미실행·미예약 |
| [47_existing_data_path_loss_analysis_v1](47_existing_data_path_loss_analysis_v1/README.md) | 승인한 A1–A3 기존 자료 분석 | 동일/다른 반복 선택 +2.775/−2.850%p, 41014의 강한 반전, 성공 획득·상실과 로그 분석; TD 수치 규칙은 모두 지속, 신규 환경0, B/C 보류 |

완료한 구현은 보존합니다. 각 단계는
목적이 드러나는 새 폴더에 독립된 코드와
설정으로 관리합니다. 기존 버전의 코드에 의존하도록 import하지 않습니다.

각 실행 결과는 해당 버전의 `results/<UTC시각>_<장치>_<고유ID>/`에 저장합니다.
기존 실행이나 checkpoint를 덮어쓰지 않으며 실패한 실행도 남깁니다.
코드·설정·검증 요약은 Git으로 관리합니다. 2026-10-08 전체 결과 업로드 요청에 따라
대용량 checkpoint·replay·실행 당시 소스 사본과 실패한 실행도
[전체 결과 GitHub Release](https://github.com/rlatmddn0211/practice_allocation/releases/tag/experiment-results-2026-10-08-v1)에 보관합니다.
Release의 `00`~`04` ZIP 다섯 개를 같은 디렉터리에 풀면 원래 폴더 구조가 복원됩니다.
가상환경과 Python 캐시, Git 내부 파일, 실행 잠금 파일은 제외합니다.
원본 파일과 ZIP의 hash 목록은 [보관 manifest](05_results_github_archive_v1/results/20261008T023322Z_complete_archive_6169480e/archive_manifest.json)에 있습니다.

E0–E2 완료 결과의 별도 보관은 [20번 출판 안내](20_e0_e2_github_publication_v1/README.md)와
[E0–E2 Release](https://github.com/rlatmddn0211/practice_allocation/releases/tag/e0-e2-results-2026-10-13-v1)에 보관했습니다.
09–11의 원시 평가·학습 로그·소스 사본·모델·replay와 E0가 실제 평가한 과거 부모 checkpoint를 포함합니다.
완료 학습은 총 5.88M step, 평가는 112,800 episode입니다. 독립 원래 seed를 사용한 E1에서
DC 집중의 Uniform 대비 평균 차이는 +0.39%p였고, E2의 DO donor contrast는 −0.78%p였습니다.
특정 donor의 보편적 우월성이나 비용을 포함한 적응형 배분기의 성공을 입증한 결과가 아닙니다.
현재 근거와 후속 연구 기준은 [19번 연구 설계](19_budgeted_practice_research_feasibility_v1/research_plan_ko.md)에 있습니다.

E3도 2026-10-14 01:27:59 KST에 완료되어 E0–E3 전체 큐 1,051개 작업이 모두 끝났습니다.
B 조합의 ButtonPress 집중은 Uniform 대비 +5.86%p였고, 세 원래 seed에서 모두 이득이 있었습니다.
C 조합에서는 모든 배분의 평균이 출발점보다 낮았으며 큰 손실은 seed 13에 집중됐습니다.
배분별 결과와 비용·한계는 [E3 상세 분석](21_e3_completed_results_analysis_v1/report_ko.md)에 있습니다.

사용자가 2026-10-07에 승인한 P0 사전학습은 같은 날 15:59:45 KST에 완료했습니다.
400k 공개 진단은 DO 5%, DC 100%, WO 40%, WC 100%로 과제당 20개 초기 상태에서
평가한 결과입니다. 사전 규칙에 따라 첫 분기점은 200k로 고정되었습니다.
P0 결과의 해석과 제한사항은 [P0 상세 분석](03_p0_pretraining_analysis_v1/README.md)에
정리했습니다. 사용자 승인 후 같은 날 18:11:27 KST에 별도 버전에서 첫 10분기 실행을
시작해 19:33:42 KST에 완료했습니다. 추가 학습 400k와 결과 평가 4,200회를 수행했고,
두 후속 seed의 배분 순위는 달랐습니다. 학습·평가 프로토콜과 결과표는
[분기 실행 문서](04_p0_allocation_branches_v1/README.md)에 있습니다.

2026-10-08 승인된 다음 단계는 같은 출발점과 평가 bank에서 후속 seed 세 개를 추가하는
[재현성 확인 실험](06_p0_branch_replication_v1/README.md)입니다. 새 세 반복은 기존 발견용
두 반복과 구분해 보고하고, 전체 다섯 반복의 합산 결과는 기술적 요약으로 제시합니다.
CUDA 사전검증 10/10·단위 검사 13/13·실행기 smoke 5/5를 통과했고,
12:07 KST에 기존 출발점의 200개 평가 사례가 같은 결과를 내는지 확인한 뒤 첫 분기 학습을 시작했습니다.

15개 분기는 14:14:14 KST에 모두 완료했습니다. 새 세 반복의 40k 평균 성공률은
균등 49.00%, 서랍열기 집중 49.33%, 서랍닫기 집중 55.00%, 창문열기 집중 55.33%,
창문닫기 집중 54.17%입니다. 서랍닫기·창문열기 집중은 새 세 seed 모두에서 균등을 앞섰고,
실패율 규칙이 선택한 서랍열기 집중은 1승·2패였습니다. 이는 한 원래 seed의 한 출발점에
대한 결과이며 적응형 선택기의 효과를 입증하지 않습니다.
[완료 결과 분석](07_p0_replication_analysis_v1/README.md)에 반복된 관찰과 재현되지 않은 관찰,
과제별 변화, 비용, 검증 기록을 정리했습니다. 06의 대용량 모델·replay는 로컬 원본에
보존되며, 앞서 올린 00~04 Release ZIP에는 포함되지 않습니다.
