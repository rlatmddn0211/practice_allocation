# 47 — 기존 자료로 확인한 학습 경로 차이와 성공 상실

2026-10-20, 사용자가 승인한 **A1–A3 분석만 완료**했다.
새 학습·새 정책 평가·환경 step·SAC update는 모두 **0**이다.
B·C와 기존 2·3단계는 실행하거나 예약하지 않았다.

- [결과와 해석](report_ko.md)
- [후보 요인별 근거 갱신](evidence_record_ko.md)
- [실행 설정](analysis_config.json)
- [사전 설계 46](../46_post_stage1_path_loss_design_v1/research_plan_ko.md)
- [이전 1단계 결과 45](../../03_schedule_selection_value/45_stage1_selection_value_analysis_v1/report_ko.md)
- [본분석 실행](LATEST_ANALYSIS.json), [독립 검산](LATEST_VERIFICATION.json)

| 분석 | 관찰 | 판정 범위 |
| --- | --- | --- |
| A1: 같은/다른 반복의 선택 | BP 대비 +2.775 / −2.850%p | 최종 정책들 사이의 차이는 다른 평가 사례에도 이어지지만, 다른 학습 반복으로 옮긴 선택은 실패 |
| A2: 짝지은 사례 불확실성 | 41014의 BP–교대, BP–혼합에서 강한 우열 반전 | 고정된 정책에 조건부인 평가 오차 분석; 두 비교 모두 같은 부모에서 나옴 |
| A3: 성공 획득·상실 | BP +5.750 −5.375 = +0.375%p | 작은 순변화 안에 큰 획득과 상실이 공존 |
| 초반 로그 입력 점검 | BP 10경로의 TD 증가 점수 모두 최소 수치 임계값 미만 | 사전 중단/지속 규칙의 수치 후보들이 모두 ‘지속’; 예측력 확보로 볼 수 없음 |

원래 1단계의 음성 결과와 진행 보류는 유지한다.
현재 경로를 연구할 근거는 생겼지만, 8k 상태의 예측 신호·중단의 이득·실제 전환 효과·비용 회수는 미검증이다.

재실행은 저장소 루트에서 다음 명령을 사용한다.
각 명령은 새 실행 폴더를 만들며 기존 출력이나 원자료를 덮어쓰지 않는다.

```powershell
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 47_existing_data_path_loss_analysis_v1\analyze.py
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 47_existing_data_path_loss_analysis_v1\verify.py
```

현재 버전의 코드는 CSV/JSON/NumPy 자료를 분석하고 그림을 저장한다.
학습 코드·시뮬레이터를 import하거나 정책 가중치를 불러오지 않는다.
`verify.py`는 `analyze.py`를 import하지 않고 계산과 입력 보존을 검산한다.
6개의 PNG/SVG 그림, 모든 부모·방법 쌍의 표, 원자료 정렬본, 20,000회 재표집 인덱스와 결과를 보존했다.
재표집 횟수나 기술 검사 수를 독립 실험 표본 수로 해석하지 않는다.

개발 중 최초 구문 오류 1건도
[실패 기록](results/20261020T033940Z_syntax_failure_68e9d998/failure.json)과 해당 소스로 보존했다.
