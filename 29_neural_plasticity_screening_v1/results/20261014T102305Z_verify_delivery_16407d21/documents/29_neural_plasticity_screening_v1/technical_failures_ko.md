# F06 기술 실패·복구 기록

2026-10-14 첫 smoke는 모델을 읽는 도중 중단됐다. 실패 디렉터리와 당시 소스는 보존했다.

| 실행 | 상태 | 원인·대응 |
| --- | --- | --- |
| [100703Z smoke](results/20261014T100703Z_smoke_6fb9c18d/summary.json) | 실패 | 개발 파일 `profile.py`가 Python 표준 라이브러리 `profile`과 충돌. torch→cProfile import에서 `AttributeError` |
| [100715Z smoke](results/20261014T100715Z_smoke_a19f937f/summary.json) | 완료 | 개발 파일을 `performance_controls.py`로 변경하고 새 출력 경로로 재실행 |
| [100933Z smoke 검산](results/20261014T100933Z_verify_measurements_69a80cb2/summary.json) | 완료 | 대표 두 모델에서 독립 목적식과 20회 복제 학습 재현 |

실패 시도는 wall 1.915초, CPU 1.438초, 복제 update 0회였다. 400개의 사전 검사를 통과한 뒤 import 예외가 발생했다. 따라서 `checks_failed=0`이 성공을 뜻하지 않으며 실행 상태 `failed`와 traceback을 함께 읽어야 한다. 원본 모델이나 replay 변경은 없었다.

파일 이름과 import만 수정했으며 후보 정의·예측 규칙·선별 기준을 바꾸지 않았다. 이전 실패 소스의 `profile.py`는 해당 실행의 `sources/`에 그대로 남겼다. 전체 측정·분석·최종 독립 검산에서는 실행 실패가 없었다.

각 실행의 소스 snapshot은 시작 시점의 파일을 기록하므로 이후 추가된 분석·검산·문서 파일이 초기 smoke snapshot에 없는 것은 정상이다. 실행당 source hash를 그 실행의 사본과 대조하며, 모든 과거 사본이 최종 개발 소스와 같다고 요구하지 않는다.
