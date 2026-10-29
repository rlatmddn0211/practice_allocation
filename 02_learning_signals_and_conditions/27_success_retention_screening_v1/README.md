# F01 기존 성공의 보존과 사례 교체 검증

기존 성공률과 단기 변화에 가려진 사례 교체를 측정했지만, 이번 검증에서 추가 예측·배분 가치를 확인하지 못했다. **취약성 요약의 핵심 요인 채택은 보류**한다. 초기 과제별 성공률은 공통 기준으로 유지한다.

- [한국어 결과 보고서](report_ko.md)
- [분석 전 고정한 프로토콜](protocol.json)
- [주 분석 결과](results/20261014T071242Z_analysis_1ce07d19/summary.json)
- [이전 후보 기록](../26_critic_signal_screening_v1/factor_status_ko.md)
- 함께 요청한 [F04 gradient 검증](../28_gradient_update_screening_v1/README.md)

## 독립 실행

저장된 E1/E3 평가만 읽고 새 환경·학습을 실행하지 않는다. 구현은 이 폴더 안에서 완결되며 다른 실험 버전의 Python 코드를 import하지 않는다. `common.py`와 `outcomes.py`는 검증된 v26의 출처 검사·평가 읽기 코드를 독립 복사했다. 새 사례 교체 특징과 전체 과제 성능 기준선은 이 버전에서 구현했다.

```powershell
13_e0_e3_autonomous_queue_v1/.venv/Scripts/python.exe -B 27_success_retention_screening_v1/analyze.py
13_e0_e3_autonomous_queue_v1/.venv/Scripts/python.exe -B 27_success_retention_screening_v1/verify_analysis.py <새 분석 출력 폴더>
```

v13의 가상환경은 설치된 의존성만 제공한다. 재실행하려면 원본 campaign과 D: 평가 CSV가 필요하며 경로·SHA-256은 각 실행의 `input_hashes.json`에 있다. 실행마다 고유 폴더와 소스 사본을 남긴다. `results/20261014T070445Z_analysis_22e1ed52`는 Greedy20에 불필요한 부모 평가 비용을 포함했던 첫 계산으로 보존한다. 주 분석은 그 비용만 정정했으며 특징·예측·선택 결과는 같다.
