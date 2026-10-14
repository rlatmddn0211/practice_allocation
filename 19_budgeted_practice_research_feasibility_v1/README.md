# Budgeted practice research feasibility

2026-10-13 연구 질문 구체화와 기존 E1 자료의 사후 재분석입니다. 새로운 RL 학습이나 환경 평가는 실행하지 않았습니다.

- [연구 판단과 검증 설계](research_plan_ko.md)
- [검증된 재분석](results/20261013T104734Z_54c5eae6/summary.json)
- [출발 상태별 20k–40k 순위](results/20261013T104734Z_54c5eae6/context_horizon_ranking.csv)
- [다른 continuation 반복으로 평가한 선택 결과](results/20261013T104734Z_54c5eae6/cross_repeat_summary.csv)
- [공개 진단의 실제 환경 비용](results/20261013T104734Z_54c5eae6/public_diagnostic_costs.csv)

6개 출발 상태 중 최상위 배분이 일치한 것은 2개입니다. 다른 두 반복의 20k macro 성능으로 고른 배분은 남겨 둔 반복의 40k에서 Uniform 대비 평균 −1.69%p였습니다. 다른 original seed의 평균 20k→40k 변화를 더한 단순 보정은 −2.04%p로 개선되지 않았습니다. 이 결과는 비용을 포함한 온라인 배분 성능이 아닙니다.

독립 original seed는 3개이며, checkpoint 두 개와 continuation 세 개는 각각 그 안에 묶여 있습니다. 20k는 40k의 절반이므로 매우 짧은 국소 진단이라고 부를 수 없습니다. 현재 결과는 저비용 gradient 신호의 실패나 replay 지연의 인과적 효과를 입증하지 않습니다.

`python 19_budgeted_practice_research_feasibility_v1/analyze.py`는 기존 v16 자료와 완료된 E1 공개 평가 기록만 읽으며, 실행할 때마다 별도 결과 디렉터리를 만듭니다. Python 표준 라이브러리만 사용합니다. 실행 소스, 입력 SHA-256, 비용, 26개 검사 결과를 보존했습니다. D 드라이브의 원래 캠페인 경로가 필요한 원본 출처 감사이며, 타 장비에서의 자료 복원은 [v20 보관 안내](../20_e0_e2_github_publication_v1/README.md)를 참고하십시오.
