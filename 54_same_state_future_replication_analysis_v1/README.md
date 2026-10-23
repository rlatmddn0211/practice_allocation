# 54 — 동일 8k 상태의 미래 반복 결과

2026-10-22 분석 완료. [상세 보고서](report_ko.md), [후보별 근거 기록](evidence_record_ko.md).

52번의 새 미래 10개는 2026-10-20 21:04:58 KST에 모두 완료됐다.
51번에서 고정한 과거 미래 기반 선택은 새 미래에서 항상 중단보다 **+0.775%p**,
항상 지속보다 **+2.625%p** 좋았다. 그러나 중단 대비 최소 +1%p와 부모 집중도 기준을
충족하지 못해 **후속 투자 기준은 미통과**다. 양의 조건부 결과와 미통과 판정을 함께 기록한다.

이 선택표는 과거의 완성된 미래를 이용하므로 실제 8k 시점의 선택기가 아니다.
부모 5개·중간 상태 10개·상태당 미래 2개이며, 새로운 부모 확인이나 전환 실험은 수행하지 않았다.

| 항목 | 결과 |
| --- | ---: |
| 항상 8k 중단 | 34.725% |
| 새 미래에서 항상 40k 지속 | 32.875% |
| 사전 고정 선택, 반대 평가 반쪽에서 채점 | 35.500% |
| 조건부 사례 재표집 공동 하한: 중단/지속 대비 | +0.075 / +1.925%p |
| 중단 대비 양의 부모별 기여 중 41015 비중 | 84.375% |
| 41015 제외 후 중단 대비 | +0.125%p |
| 본 실행 환경 step | 1,705,201 |
| 기술 검사 포함 환경 step | 1,709,716 |
| 이번 분석의 새 환경 step | 0 |

재현 명령은 저장소 루트에서 실행한다. 매번 새로운 결과 폴더를 생성한다.

```powershell
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 54_same_state_future_replication_analysis_v1\analyze.py
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 54_same_state_future_replication_analysis_v1\verify.py <새_분석_결과_폴더>
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 54_same_state_future_replication_analysis_v1\make_figure.py <새_분석_결과_폴더> <새_검산_결과_폴더>
```

- [설정](analysis_config.json): 51의 분석 기준과 52의 입력 hash 고정.
- [본분석](results/20261022T021845Z_analysis_98fe07c3/summary.json), [기계 판독 판정](results/20261022T021845Z_analysis_98fe07c3/decision_record.json).
- [독립 검산](results/20261022T021906Z_verification_8656944c/summary.json): 원시 CSV를 별도 유리수·정수 집계로 재계산하고 20,000 사례 재표집 벡터도 대조.
- [그림 PNG](results/20261022T022048Z_figure_c2fd5be1/future_replication.png), [SVG](results/20261022T022048Z_figure_c2fd5be1/future_replication.svg).
- [원 실행](../52_same_state_future_replication_v1/README.md), [사전 명세](../51_same_state_future_investment_protocol_v1/protocol.json), [직전 근거](../50_b_posthoc_concentration_review_v1/report_ko.md).

이 버전은 이전 구현을 import하지 않는다. 분석은 NumPy와 표준 라이브러리, 그림은 Matplotlib을 쓴다.
학습 상태 파일은 해시만 확인하며 모델을 로드하지 않는다. 대용량 checkpoint와 재표집 NPZ,
실행 소스 사본은 로컬 보존 대상이다. 재현에는 49·51·52번 원자료와 로컬 checkpoint가 필요하다.
현재 TD 규칙 조정, C, 원래 2·3단계와 replay 개입은 새로 실행하거나 예약하지 않았다.
