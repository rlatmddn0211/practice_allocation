# F08 완료 후 후보 1–8 통합 해석

2026-10-19. ⑧의 72개 분기와 사전 대조 21개를 모두 검토하고, [36번의 ①–⑦ 기록](../36_all_candidate_evidence_review_v1/README.md)에 새 근거를 추가한 독립 버전이다. 이전 분석·학습·체크포인트는 보존했다.

- [연구 해석 보고서](report_ko.md)
- [최신 후보별 근거 기록](factor_status_ko.md)
- [모든 반복을 표시한 그림](results/20261019T024807Z_figure_e8001806/F08_all_branches.png) · [SVG](results/20261019T024807Z_figure_e8001806/F08_all_branches.svg)
- [구성·조건별 평균](results/20261019T024708Z_review_cef06973/condition_means.csv)
- [사전 대조 21개·반복별 차이·반복 하나 제외 민감도](results/20261019T024708Z_review_cef06973/contrast_review.csv)
- [과제별 기여](results/20261019T024708Z_review_cef06973/contrast_task_means.csv)
- [실행 요약](results/20261019T024708Z_review_cef06973/summary.json) · [독립 검산](results/20261019T024727Z_verify_8ec46ef7/summary.json)
- [프로토콜](protocol.json) · [기술 검토와 수정 이력](technical_notes_ko.md)

**판정:** 강도·순서를 바꾸면 결과가 달라지는 개발 실험의 근거를 확보했다. B의 교대−혼합과 중간 비중의 비선형 반응을 우선 추적한다. 원래 seed가 구성마다 하나이므로 범용 효과·최적 순서·새 예측 요인·비용 포함 배분 개선은 미확인이다.

이번 작업은 저장된 자료의 재계산과 문서화다. 새 환경 실행·학습 업데이트는 0이며 새 실험을 예약하지 않았다.

## 재실행

프로젝트 루트의 PowerShell에서 실행한다. 각 명령은 새 결과 폴더를 만들며 기존 결과를 덮어쓰지 않는다.

```powershell
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 37_f08_integrated_candidate_review_v1\analyze.py
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 37_f08_integrated_candidate_review_v1\verify.py --analysis <새 분석 폴더>
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 37_f08_integrated_candidate_review_v1\plot.py --analysis <새 분석 폴더>
```

분석은 Python·NumPy, 독립 검산은 표준 라이브러리, 그림은 Matplotlib를 사용한다. 버전·소스 snapshot/hash·입력 snapshot/hash·실제 비용은 각 실행 폴더에 보존한다. 이전 구현을 import하지 않는다.
