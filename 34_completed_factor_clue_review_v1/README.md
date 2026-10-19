# 완료 후보의 연구 단서 종합 검토

2026-10-15에 완료된 ①·②·③·④·⑥·⑦의 결과와 보조 비교를 함께 검토했다. 핵심 단서는 정밀하게 측정한 국소 신호와 최종 배분 가치 사이의 간극, 작은 예측 차이로 바꾼 선택의 큰 손익, 일부 후보를 구별하기 어려운 상태 분포다. 후보 채택 판정은 변경하지 않았다.

[종합 연구 보고서](report_ko.md) · [후보별 이전 판정](../33_remaining_factor_queue_v1/factor_status_ko.md) · [분석 범위](protocol.json)

이번 새 계산은 저장된 선택·예측·특징 표를 다시 읽어 기준모형별 증분과 모든 선택 변경을 확인했다. 다섯 주 비교가 각자의 기준 선택을 바꾼 조건의 합집합은 36개 중 7개였다. ④의 세 변경은 같은 원래 seed에서 −5.5/−11/+20%p였다. 관측된 상위 분기와 Greedy20의 점수 차이는 3.870%p로, 후보 지표의 작은 이득을 개선 여지 소진으로 해석하기 어렵다.

⑥의 critic 학습 자료 개선과 다른 자료 개선의 차이가 클수록 `|O40−D20|`도 큰지 한 가지 사후 관계를 추가 확인했다. 전체 Spearman은 0.0044이고 원래 seed별 부호가 달랐다. 이 간극 하나를 미래 오류의 예측 요인으로 채택하지 않는다. 모든 지표 탐색이나 예측기 재적합을 수행한 결과가 아니다.

- [비교·기준모형·MAE](results/20261015T040457Z_review_5155a6e3/comparisons.csv)
- [모든 변경 선택과 예측 차이](results/20261015T040457Z_review_5155a6e3/all_changed_choices.csv)
- [원래 seed·구성별 이득](results/20261015T040457Z_review_5155a6e3/increments_by_seed_group.csv)
- [관측된 선택 여지](results/20261015T040457Z_review_5155a6e3/observed_selection_headroom.csv)
- [critic 간극과 미래 차이의 사후 상관](results/20261015T040457Z_review_5155a6e3/critic_gap_descriptive_correlations.csv)
- [실행 요약·비용](results/20261015T040457Z_review_5155a6e3/summary.json)

분석은 wall 0.197초·CPU 0.047초, 새 환경 step·원본 및 복제 학습 update는 모두 0이다. 입력 파일 사본·hash, 실행 당시 코드·설정·의존성, 8,491개 검사 결과를 보존했다. 이 수는 과학적 효과의 표본 수가 아니다. 계산의 별도 검산은 새 `results/*_verify_*` 폴더에 기록한다.

대부분 같은 과거 E1·E3 자료를 재사용하므로 여섯 결과를 독립된 여섯 재현 실험으로 합치지 않는다. 원래 seed는 세 블록이며 192개 checkpoint도 독립 사전학습 반복이 아니다. 관측 최상위와의 차이에는 최댓값 선택 편향이 있고, 후속 40k를 이미 보고 고른 값을 실제로 실행 가능한 정책으로 해석하지 않는다. 진단 비용을 포함한 동일 총예산 개선도 검증하지 않았다.

⑤·⑧의 실행 코드·설정과 root pilot 설계는 유지했다. 이 검토의 후속 가설은 새 실험의 자동 실행 지시가 아니다.

```powershell
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B .\34_completed_factor_clue_review_v1\analyze.py
```

다시 실행하면 새로운 결과 폴더와 입력·소스 사본을 만들며 기존 실행을 덮어쓰지 않는다.
