# 후보 ①–⑧ 전체 근거 재검토

2026-10-15. 사용자의 요청으로 완료된 후보 검증을 다시 검토했다. [종합 연구 보고서](report_ko.md)와 [최신 후보별 기록](factor_status_ko.md)에 ⑤의 완료 결과까지 반영했다. [이전 34번 검토](../34_completed_factor_clue_review_v1/report_ko.md)는 당시의 기록으로 보존한다.

①–⑦의 완료된 측정·탐색 분석을 다뤘고, 진행 중인 ⑧은 상태만 확인했다. 후보의 이름 전체를 반증하거나 최종 요인을 선정한 작업은 아니다. 새로운 학습·환경 평가·예측기 탐색·실험 예약은 없다.

- [검토 규약](protocol.json): 사후 종합 검토임을 명시하고 기존 주 비교·보조 비교를 유지했다.
- [최종 재계산](results/20261015T104602Z_review_0d1cb1b0/summary.json): 6개 분석 묶음의 모든 저장 예측·선택과 공통 기준을 대조하고 F07을 별도로 점검했다.
- [최종 독립 검산](results/20261015T105530Z_verify_bd300470/summary.json): 9,054개 검사 통과. 실제 원시 CSV·보정식·완료 영수증과 대조했고, 재사용한 기존 검증의 범위를 명시했다.
- [비교 전체](results/20261015T104602Z_review_0d1cb1b0/comparisons.csv), [원래 seed·구성별 증분](results/20261015T104602Z_review_0d1cb1b0/increments_by_seed_group.csv), [선택 변경 전체](results/20261015T104602Z_review_0d1cb1b0/all_changed_choices.csv).
- [보상·현재 성공 대응](results/20261015T104602Z_review_0d1cb1b0/return_calibration_review.csv), [가치 rollout의 추정 범위](results/20261015T104602Z_review_0d1cb1b0/rollout_uncertainty_review.csv).
- [실패·정정 이력](technical_notes_ko.md): 실패 및 교체된 검토 출력도 보존했다.

⑤의 15,360개 deterministic episode와 6,144개 MC episode CSV에서 보정값과 가치 진단 요약을 별도 코드로 다시 계산한다. 기존 학습 코드를 import하지 않고, 원본 checkpoint와 현재 실행기의 소스를 바꾸지 않는다. 원래 10.752M step의 시뮬레이션이나 전체 trajectory 재검산을 재실행한 것은 아니다. 기존 trace 검증 영수증 192개를 대조했다.

```powershell
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 36_all_candidate_evidence_review_v1\analyze.py
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 36_all_candidate_evidence_review_v1\verify.py <새 검토 결과 폴더>
```

실행마다 새로운 폴더에 실제 소스·입력 사본·SHA-256·Python 버전·실제 CPU/wall 비용을 남긴다. 원본 실험 비용과 이번 검토 비용은 구분한다. 새 환경 step과 지속/복제 학습 update는 모두 0이다.
