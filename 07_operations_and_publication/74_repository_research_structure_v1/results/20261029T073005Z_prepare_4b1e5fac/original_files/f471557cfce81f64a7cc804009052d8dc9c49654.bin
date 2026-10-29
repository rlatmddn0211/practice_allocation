# E0 · 새 평가 사례와 Failure 규칙 점검

2026-10-08 승인된 E0 구현이다. 학습을 추가하지 않고 P0 seed 901의 200k 부모와 기존 25개 +40k 분기를 새 사례에서 평가한다. 기존 구현·체크포인트·평가 bank는 수정하지 않는다.

- 공개 진단 100회/과제에서 Failure 선택을 먼저 동결한다.
- 이후 부모와 25개 분기를 별도 outcome 100회/과제에서 평가한다.
- 총 학습 0 step, 평가 10,800 episode. seed 1903–1905를 먼저 보고하고 1901–1902와 합산 기술통계를 구분한다.
- 주 비교는 F_DC−U macro 성공률이다. 20개 공개 사례 재표집으로 Failure 선택의 측정 민감도를 보조 분석한다. 과거의 F_DO 선택을 소급 변경하지 않는다.

`run_job.py`가 독립 작업을 실행하며 `analyze_stage.py`가 원본 CSV를 검증하고 대비·불확실성·실패율 선택 보고서를 작성한다. 연구 코드는 이 폴더 안에 모두 있으며 다른 버전의 Python 코드를 import하지 않는다. `learning.py`, `engine.py`, `environment.py`, `evaluation.py`는 버전 06과 바이트가 같다. `core.py`는 명시적 과제 조합과 배분을 바인딩한다.

실행은 [13 자동 큐](../13_e0_e3_autonomous_queue_v1/README.md)가 담당한다. 입력 manifest, 실행 소스 사본/hash, 의존성, seed, 실제 비용, 실패 기록은 매번 새 `results/` 하위 폴더에 저장된다. 기술 검증 결과는 과학적 효과의 증거가 아니다.

```powershell
13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe 09_fresh_evaluation_audit_v1/verify_stage.py --suite A
```
