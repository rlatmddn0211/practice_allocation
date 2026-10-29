# F02 실제 노출과 F03 성공 경험 검증

2026-10-15, 기존192개 checkpoint와 공식 학습 episode 기록을 이용한1차 검증을 완료했다. F02 주 지표의 추가 선택 이득은0.000%p, F03 최근 성공 경험 지표는−0.361%p였다. 두 지표 모두 이번 선별 기준을 통과하지 못했다.

[상세 결과](report_ko.md) · [고정 설정](protocol.json) · [분석](results/20261015T031819Z_analysis_56a74006/summary.json) · [독립 검산](results/20261015T032001Z_verify_85b6bf5c/summary.json)

코드는 이 버전 안에서 독립적이며, 기존 모델·replay·학습 결과는 읽기만 했다. 새 환경 실행과 학습 update는0이었다. 예측 결과를 보기 전에 지표·비교·선별 기준을 고정했지만 이미 관찰한 역사 자료의 탐색 분석이라는 한계는 남는다.

```powershell
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 30_exposure_experience_screening_v1/measure.py
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 30_exposure_experience_screening_v1/analyze.py --measurement <새_측정_폴더>
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 30_exposure_experience_screening_v1/verify.py --measurement <새_측정_폴더> --analysis <새_분석_폴더>
```

각 실행은 새 결과 디렉터리, 실행 소스 사본, 입력·소스 hash, 의존성 버전, 비용과 검사 기록을 남긴다. 과거 실행은 덮어쓰지 않는다.
