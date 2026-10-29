# F04 업데이트 방향·크기 검증

**192개 기존 모델의 gradient·Adam 가상 업데이트를 측정하고 40k 예측·선택까지 검증했다.** 주 비교의 추가 선택 이득은 +0.065%p로 원래 seed 하나에만 나타났고, 예측 오차는 소폭 증가했다. 핵심 배분 요인 채택은 보류한다.

- [상세 결과 보고서](report_ko.md)
- [F01·F04까지 반영한 최신 후보 기록](factor_status_ko.md)
- [분석 전 고정한 프로토콜](protocol.json)
- [본 측정](results/20261014T070936Z_measure_b6b065f3/summary.json), [주 분석](results/20261014T071540Z_analysis_d2e18cbf/summary.json)
- [실패한 검산과 정정 기록](technical_failures_ko.md)
- 함께 실행한 [F01 사례 교체 검증](../27_success_retention_screening_v1/report_ko.md)

## 독립 실행

```powershell
13_e0_e3_autonomous_queue_v1/.venv/Scripts/python.exe -B 28_gradient_update_screening_v1/measure.py --smoke
13_e0_e3_autonomous_queue_v1/.venv/Scripts/python.exe -B 28_gradient_update_screening_v1/verify_measurements.py <새 smoke 출력>
13_e0_e3_autonomous_queue_v1/.venv/Scripts/python.exe -B 28_gradient_update_screening_v1/measure.py
13_e0_e3_autonomous_queue_v1/.venv/Scripts/python.exe -B 28_gradient_update_screening_v1/analyze.py --measurement <새 본 측정 출력>
13_e0_e3_autonomous_queue_v1/.venv/Scripts/python.exe -B 28_gradient_update_screening_v1/verify_measurements.py <새 본 측정 출력>
13_e0_e3_autonomous_queue_v1/.venv/Scripts/python.exe -B 28_gradient_update_screening_v1/verify_analysis.py <새 분석 출력>
```

v13 가상환경은 패키지만 제공한다. 구현은 이 폴더에서 완결되며 다른 실험 버전의 Python 모듈을 import하지 않는다. v26 checkpoint 읽기·패널 선택·출처 검사와 v27 과제별 성능 기준선·선택 검증을 독립 복사했다. F05 대조 특징은 v26의 hash가 기록된 **측정 데이터**를 입력으로 사용한다.

원본 checkpoint와 평가 CSV는 D: campaign에 보존되어 있다. 각 실행의 입력 hash·경로, 소스 사본, 패키지 버전과 비용으로 재현할 수 있다. 모든 재실행은 새 고유 폴더를 만든다. 원본 학습 상태를 변경하지 않으며, 가상 업데이트는 복제한 파라미터·Adam 상태에만 수행한다.
