# 55 — 사례별 성공 획득·상실의 미래 간 반복성

2026-10-22, 기존 자료 분석 완료. [연구 질문](research_question_ko.md), [상세 결과](report_ko.md),
[후보별 근거 갱신](evidence_record_ko.md).

중심 질문을 **동일한 전체 학습 상태에서 같은 규칙·예산으로 추가 학습할 때 무엇을 얻고 잃는지가
미래 간에 얼마나 반복되는가**로 고정했다. 그 반복성과 관련된 조건을 관찰하는 일과
학습 조건을 바꿔 원인을 검증하는 일을 구분한다. 54번 선택기 투자 기준 미통과는 유지한다.

| 사건 | 두 미래의 공통 사건 수 | 상태·과제별 사건 수를 맞춘 기대 중첩 | 초과 중첩 |
| --- | ---: | ---: | ---: |
| 8k 성공의 상실 | 148 | 147.698 | +0.302 |
| 8k 실패에서 성공 획득 | 62 | 46.759 | +15.241 |

획득의 초과 중첩은 부모 4개에서 양수·1개에서 0이고, 모든 부모 제거에서도 양수다.
상실의 높은 원시 중첩률은 주어진 상태·과제별 상실량만으로 대부분 기대되는 수준이었다.
이를 상실이 무작위라는 증명이나 획득이 본질적으로 더 반복 가능하다는 법칙으로 해석하지 않는다.

사용자가 제시한 성공 이력별 상실률은 일치했다. 다만 같은 부모·중간 상태·과제의 두 집단을
비교한 뒤 부모를 동일 가중하면 위험 차이는 기존 미래 +3.440, 새 미래 +8.895%p다.
부모별 방향과 가중치 민감도가 커서 보편적인 성공 이력 효과로 채택하지 않는다.

분석은 부모 5개·중간 상태 10개·고유 평가 사례 2,000개에서 나온 상태×사례 관측 4,000건을 쓴다.
모델·환경 실행 없이 새 환경 step·SAC 업데이트 **0**이다. 기존 52번 학습 비용을 중복 합산하지 않는다.

```powershell
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 55_casewise_gain_loss_repeatability_v1\analyze.py
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 55_casewise_gain_loss_repeatability_v1\verify.py <새_분석_결과_폴더>
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 55_casewise_gain_loss_repeatability_v1\make_figure.py <새_분석_결과_폴더> <새_검산_결과_폴더>
```

- [설정](analysis_config.json), [분석 요약](results/20261022T031427Z_analysis_a137ba0b/summary.json).
- [상태·과제별 중첩](results/20261022T031427Z_analysis_a137ba0b/overlap_by_state_task.csv), [성공 이력별 분모·상실](results/20261022T031427Z_analysis_a137ba0b/history_by_state_task.csv).
- [부모별 중첩](results/20261022T031427Z_analysis_a137ba0b/overlap_by_parent.csv), [과제별 중첩](results/20261022T031427Z_analysis_a137ba0b/overlap_by_task.csv).
- [부모별 조건 내 위험 차이](results/20261022T031427Z_analysis_a137ba0b/history_matched_by_parent.csv), [부모 제거](results/20261022T031427Z_analysis_a137ba0b/leave_one_parent_out.csv).
- [독립 검산](results/20261022T031646Z_verification_801c7f5f/summary.json): 집합·유리수와 사례 빈도 방식으로 재계산, 934건 통과.
- [PNG](results/20261022T031904Z_figure_cbbb15da/casewise_repeatability.png), [SVG](results/20261022T031904Z_figure_cbbb15da/casewise_repeatability.svg).

첫 분석 명령은 실행 전 구문 오류로 종료됐다. [실패 기록](results/20261022T031426Z_parse_failure_dee35bfe/FAILED.json)과
실행 소스를 보존하고 새 결과 폴더에서 수정본을 실행했다. 실패 과정의 환경 비용도 0이다.
이 버전은 이전 구현을 import하지 않는다. Python 3.12.0·NumPy 2.2.4, 그림은 Matplotlib 3.10.1을 사용했다.
대용량 재표집 NPZ·소스 사본은 로컬 보존하며, 입력은 54번 자료 및 해시로 연결된 49·52번 원시 CSV다.
추가 학습·정책 평가·개입 실험은 실행하거나 예약하지 않았다.
