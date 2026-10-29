# F07 신호의 재현성과 배분 차이

2026-10-14 완료. 기존 E1·E3의 12개 출발 상태와 148,800개 평가 행을 사용한 독립 분석 버전이다. 신규 학습·환경 평가·learner update는 없다.

**결론:** F07은 진단 의사결정 조건으로 유지하되 핵심 배분 요인으로 승격할 근거는 아직 부족하다. 과제당 두 사례에서는 선택이 불안정했고, 평가를 늘려도 후속 seed 변동과 시간별 순위 반전이 남았다. 사전 고정한 신뢰도 규칙의 개발 고정 배분 대비 이득은 두 사례 +0.07%p, 20사례 +0.45%p였으며, 20사례에서는 단순 차이 규칙보다 −0.27%p였다. 모두 비용을 차감하지 않은 탐색 결과다.

- [상세 연구 보고서](report_ko.md)
- [고정한 분석 규약](protocol.json)
- [분석 요약과 비용](results/20261014T053612Z_df5ecad4/summary.json)
- [독립 재계산 검증](results/20261014T053931Z_verify_f8038b92/summary.json)
- [최종 PNG·SVG 그림](results/20261014T054319Z_figures_39560e10/)

```powershell
python 24_signal_reliability_screening_v1/analyze.py
python 24_signal_reliability_screening_v1/verify_analysis.py <새 분석 결과 폴더>
python 24_signal_reliability_screening_v1/render_figures.py <새 분석 결과 폴더>
```

각 명령은 새로운 결과 폴더를 만들며 기존 결과를 덮어쓰지 않는다. 원자료는 현재 로컬 campaign manifest가 가리키는 저장소를 읽는다. 결과 CSV·분할 규약·입력 hash·실행 소스로 계산 경로를 추적할 수 있고, 전체 재실행에는 원본 episode CSV가 필요하다. 실행 의존성은 [requirements.txt](requirements.txt)에 기록했다. 어떤 스크립트도 기존 learner 코드를 import하지 않는다. 다음 후보의 구현·실험 변경은 별도 버전에서 관리한다.
