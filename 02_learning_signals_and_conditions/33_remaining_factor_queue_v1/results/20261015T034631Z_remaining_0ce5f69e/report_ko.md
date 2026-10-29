# 미실행 후보 검증 완료 기록

계획한 진단과 72개 통제 학습 분기를 모두 완료하고 각 단계 계산 검산을 통과했다.

- F02: CriticBase 대비 추가 선택 이득 +0.000%p, 선별 통과 False.
- F03: ExperienceBase 대비 추가 선택 이득 -0.361%p, 선별 통과 False.
- F05 정합성: 주 추가 선택 이득 -0.296%p, 선별 통과 False.
- F08: 세 구성 각각 원래 seed12 한 개, 후속 반복3개의 강도·순서 대조를 완료했다. 개별 대조는 아래 상세 결과를 따른다.

실행 worker의 실제 환경 비용은 실패 시도 포함 23,127,447 step, SAC iteration은 2,880,000회다. 초기 기술 검사와 분석 비용은 별도 summary에 보존했다. 비용 포함 적응형 배분 G4는 실행하지 않았다.

[F05 분석](C:/Users/SS/Projects/robot_practice_allocation/31_fixed_horizon_alignment_v1/results/20261015T100729Z_analysis_5fa7ae88/report_ko.md) · [F08 분석](C:/Users/SS/Projects/robot_practice_allocation/32_dose_order_intervention_v1/results/20261016T071742Z_analysis_3cb34e0e/report_ko.md)

F01/F04/F06/F07의 이전 판정은 v29 근거 기록을 유지한다. F02 sampling 인과 개입, 새 원래 seed의 독립 확인, 다른 benchmark 및 동일 총예산 실제 배분은 미실행이다.
