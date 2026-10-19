# F06 신경망 가소성 후보 검증

2026-10-14, 기존 E1·E3 자료에서 **현재 성능과 단기 학습 반응을 넘어 신경망의 추가 적응 능력이 최종 연습 선택에 도움이 되는지** 검증했다. 측정·분석·독립 계산 검산을 완료했다. 새 원래 seed 확인이나 비용을 포함한 온라인 배분 실험은 아니다.

주 지표의 추가 선택 이득은 **+0.074%p**, 선택 변경은 **1/36**이었다. 원래 seed 11/12/13의 이득은 0/+0.222/0%p로, 사전에 정한 선별 기준을 통과하지 못했다. 휴면 비율·표현 유효 rank의 별도 비교도 +0.102%p에 그쳤다. **이번 F06 지표의 핵심 요인 채택은 보류한다.**

- [상세 결과·해석](report_ko.md)
- [8개 후보의 최신 근거 기록](factor_status_ko.md)
- [결과를 보기 전 고정한 설정](protocol.json)
- [기술 실패와 복구](technical_failures_ko.md)
- [실행 결과 경로 목록](result_index.json)
- [주 분석 요약](results/20261014T101557Z_analysis_e77c6ebb/summary.json)
- [사전 비교별 증분](results/20261014T101557Z_analysis_e77c6ebb/planned_contrasts.csv)
- [측정 독립 검산](results/20261014T101558Z_verify_measurements_daa27e31/summary.json) · [예측·선택 독립 검산](results/20261014T101613Z_verify_analysis_30186f0e/summary.json)

기존 checkpoint 192개, 20k 분기 180개를 사용했다. 마지막 ReLU 층의 휴면 비율과 유효 rank를 측정하고, 저장된 Adam 상태까지 복제한 actor·critic을 각각 20회 업데이트했다. 다른 episode panel의 loss 감소를 첫 1회 반응과 이후 19회 반응으로 나눴다. 원본 학습 상태와 replay는 변경하지 않았다.

본 측정은 복제 optimizer step 15,360회, wall 322.60초였다. 실패·smoke·독립 검산까지 전달 감사 전 전체 실행은 복제 step **16,420회**, wall 합 362.30초, CPU 합 195.36초였다. 새 환경 step과 원본에 저장되는 학습 update는 모두 0이다. CUDA event 시간은 측정된 두 실행 구간만 합해 203.79초이며, 전체 GPU 사용 시간은 계측하지 않았다.

**재실행**

저장소 루트에서 아래 명령을 실행한다. 매번 고유한 새 결과 폴더와 실행 소스 사본을 만든다. 원본 campaign·모델·replay 경로와 v26의 검증된 측정 자료가 필요하다. Python 환경은 `requirements.txt`에 기록했고, 아래 경로는 이미 설치된 환경을 재사용하는 것이다. 코드 import는 이 버전 안에서 독립적이다.

```powershell
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 29_neural_plasticity_screening_v1/measure.py --smoke
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 29_neural_plasticity_screening_v1/measure.py
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 29_neural_plasticity_screening_v1/analyze.py --measurement <새_전체_측정_폴더>
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 29_neural_plasticity_screening_v1/verify_measurements.py <새_전체_측정_폴더>
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 29_neural_plasticity_screening_v1/verify_analysis.py <새_분석_폴더>
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 29_neural_plasticity_screening_v1/verify_delivery.py
```

`verify_delivery.py`는 이번 전달본의 고정 결과 목록과 문서 수치·링크·소스 hash를 검사한다. 새로운 연구 조건의 실행은 새 번호 버전으로 분리한다.
