# F05 critic 진단의 추가 예측 가치 검증

**2026-10-14, ⑤의 기존 checkpoint 기반 1차 검증 완료.** 과제별 정규화된 TD 잔차와
두 critic의 추정 차이를 추가해도 주 비교 36건의 배분 선택이 모두 기존 예측기와 같았다.
추가 선택 이득은 0.00%p였고, 최종 성공률 예측 오차는 6.361→6.389%p로 줄지 않았다.
현재 두 지표를 핵심 배분 요인으로 채택할 근거는 확보하지 못했다.

이 결과는 F05의 critic 진단 부분에 한정된다. 동일 길이 return과 성공률의 관계,
실제 가치 추정 오차, 4k 진단 및 비용 포함 온라인 배분의 검증은 별도다.

- [상세 결과와 판정](report_ko.md)
- [8개 후보의 최신 상태](factor_status_ko.md), [이전 근거 기록](../25_candidate_factor_evidence_register_v1/README.md)
- [고정한 분석 규약](protocol.json)
- [192개 모델 측정](results/20261014T062246Z_measure_10dac0ac/summary.json)
- [예측·선택 비교](results/20261014T062648Z_analysis_4a05b167/summary.json)
- [157만 transition 독립 재계산](results/20261014T062957Z_verify_measurements_61c9843d/summary.json)
- [특징·회귀·선택 독립 검증](results/20261014T062957Z_verify_analysis_d5cee918/summary.json)

## 범위

기존 E1 A 200k/400k와 E3 B/C 200k의 12개 출발 상태를 사용했다.
원래 seed는 11·12·13의 세 블록, 사전학습 이력은 9개다.
부모 12개와 5배분 × 3후속 seed × 12상태의 20k checkpoint 180개를 읽었다.
과제당 1,024 transition씩 두 개의 episode 분리 panel을 구성해 총 1,572,864개를 진단했다.
기존 평가 148,800 episode 행에서 이후 성능을 계산했다. 신규 학습·환경 평가·update는 0이다.

## 재현

Python 3.12와 [의존성](requirements.txt)을 사용한다. 이번 실행은 저장소의 기존
`13_e0_e3_autonomous_queue_v1/.venv/Scripts/python.exe`에 설치된 패키지를 사용했다.
다른 실험 버전의 Python 구현을 import하지 않는다. replay의 저장 클래스 이름만
일반 ReplayBuffer로 매핑하고, 복원된 전체 학습 상태와 replay hash를 원본 manifest와 대조한다.

```powershell
13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 26_critic_signal_screening_v1\measure.py --smoke
13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 26_critic_signal_screening_v1\measure.py
13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 26_critic_signal_screening_v1\verify_measurements.py <measurement-output-directory>
13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 26_critic_signal_screening_v1\analyze.py <measurement-output-directory>
13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 26_critic_signal_screening_v1\verify_analysis.py <analysis-output-directory>
```

각 실행은 새 `results/<UTC시각>_<단계>_<고유ID>`를 만들고 사용한 소스·설정·입력 hash·
의존성·비용·실패를 보존한다. 측정은 로컬의 원본 캠페인과 checkpoint를 필요로 한다.
출력된 transition 진단은 `raw/*.csv.gz`, 요약은 CSV, 실행 기록은 JSON이다.
재실행은 기존 출력 디렉터리를 덮어쓰지 않는다.
