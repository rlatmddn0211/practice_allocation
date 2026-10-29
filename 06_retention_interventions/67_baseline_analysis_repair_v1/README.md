# 64번 기준선 분석의 CSV 비용 합산 수리

2026-10-27. 기존 파일만 읽는 독립 분석 버전이다. 64번의 학습·평가·체크포인트·동결 소스를 변경하지 않는다.

64번 `analyze_baseline.py`는 CSV에서 읽은 `length` 문자열을 정수에 더해, 완료된 경로의 실제 평가 비용을 합산할 때 `TypeError: unsupported operand type(s) for +: 'int' and 'str'`가 발생한다. 이 오류는 합성40경로의 전체 입출력 검증에서 발견됐으며 학습 worker에는 영향을 주지 않는다.

67번은 64번의 분석·독립 검산 소스와 동결 입력을 독립 복사했다. 분석 소스의 변경은 다음 한 줄뿐이다.

```diff
-        evaluated = sum(row["length"] for row in worker_rows)
+        evaluated = sum(int(row["length"]) for row in worker_rows)
```

지표·사례 집합·seed·가중치·재표집·판정은 바꾸지 않는다. `verify_baseline.py`는 원본과 바이트가 같다. 동결 `protocol.json`의 버전 필드는 원래64번 실험을 가리키며 역사적 프로토콜을 다시 쓰지 않는다. 입력의 절대 checkpoint·평가 출처도 원래 위치를 유지한다. 과거 버전의 Python 모듈을 import하지 않는다.

```powershell
python analyze_baseline.py --campaign <64번_정확한_campaign> --allow-incomplete
python verify_baseline.py --analysis-dir <바로_반환된_67번_analysis_dir>
```

각 실행은 새 `results` 디렉터리, 소스 사본/hash, 입력 사본/hash, 실제 비용 출처를 남긴다. 실패한 시도도 보존한다. 미완료 경로는NA이며 완료된 경로만 선별해 전체 평균이나 확인 구간을 만들지 않는다. 실행 중 campaign을 읽은 부분 분석은 기술 점검이며 완성된 과학 결과가 아니다.

실제 새 환경 step·정책 rollout·SAC update는0이다. 요구 패키지는 Python3.12 및 NumPy2.2.4이다. 분석 완료는 효과 확인이나 신규 학습 승인과 다르다. 66번의 후속 실행은 별도 동결 프로토콜과 해당 큐의 기술·상류 무결성 조건을 따른다.

원본/수리 소스의 SHA-256과 정확한 차이는 [repair_provenance.json](repair_provenance.json), 상세 오류 범위는 [error_report_ko.md](error_report_ko.md)에 기록한다.
