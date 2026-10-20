# 1단계 결과: 고정 일정, 반복성, 선택 가치

2026-10-20 KST. [43번 동결 설계](../43_feedback_revised_selection_protocol_v1/research_protocol_ko.md)에 따른
[44번 실험](../44_selection_value_stage1_checkpoint36_v2/README.md)의 독립 재집계와 해석이다.
기존 실행·분석 파일은 수정하지 않았다. 새 학습·환경 평가는 0 step이다.

**실행은 완료됐지만 사전 지정한 2단계 투자 기준은 통과하지 못했다.**
평균 성공률은 BP 집중 34.075%, 교대 33.975%, 혼합 33.000%다.
반복과 평가 사례를 나누어 부모별 방법을 선택하면 BP 고정보다 −2.850%p,
다른 부모에서 고른 고정 방법보다 −1.500%p였다.
이는 현재 B·200k 부모·40k 추가 학습·세 방법의 결과이며, 같은 8k 상태에서의 실제 전환이나 진단 비용 회수를 시험한 결과는 아니다.

- [상세 해석](report_ko.md)
- [F01·F07·F08 관련 근거 갱신과 다음 판단 조건](evidence_record_ko.md)
- [기계 판독 결과](results/20261020T023142Z_review_9f071dae/summary.json)
- [부모별 결과](results/20261020T023142Z_review_9f071dae/parent_scores.csv)
- [반복별 방법 차이](results/20261020T023142Z_review_9f071dae/repeat_pair_differences.csv)
- [원자료·설정·실행 입력 hash](results/20261020T023142Z_review_9f071dae/input_hashes.json)
- [무결성·계산 확인](results/20261020T023142Z_review_9f071dae/checks.json)

`analyze.py`는 245개 작업 기록과 35개 정책의 14,000개 평가 행을 읽고,
집계·교차 선택·부모 제거 후 재적합·진행 기준을 독립 계산한다.
973개 무결성·계산 검사를 통과했다. 검사 개수는 효과의 근거 수가 아니다.
분석에는 표준 라이브러리만 사용하며 과거 구현을 import하지 않는다.

재실행:

```powershell
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B .\45_stage1_selection_value_analysis_v1\analyze.py
```

매번 새 `results/<UTC>_review_<id>`에 입력 hash와 실제 실행 소스 사본을 보존한다.
`LATEST_REVIEW.json`은 최신 실행을 가리키는 탐색용 포인터다.
첫 개발 실행 `20261020T023002Z_review_a85862ce`도 보존했다.
그 후 포인터 갱신만 재실행 가능하게 수정했으며 수치와 과학적 판정은 동일하다.
초기 콘솔 읽기의 cp949 출력 오류는 UTF-8 재읽기로 해결했으며 실험 실패와 구분한다.

2·3단계 학습이나 추가 실험 예약은 이 분석에서 수행하지 않았다.
