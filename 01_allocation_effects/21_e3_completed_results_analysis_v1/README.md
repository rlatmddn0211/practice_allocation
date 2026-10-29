# E3 completed results analysis

E3는 **2026-10-14 01:27:59 KST**에 완료됐습니다. B·C 조합의 90개 분기와 459개 작업이 모두 완료되어 E0–E3 전체 큐도 1,051/1,051 완료 상태입니다.

**B에서는 ButtonPress 집중의 이득이 일관적이지만 고정 배분으로 설명됩니다. C에서는 시험한 모든 배분의 평균이 출발점보다 낮고, 주로 seed 13의 망각이 평균을 끌어내립니다.** 두 결과 모두 비용을 포함한 적응형 선택기의 성공을 뜻하지 않습니다.

- [상세 결과와 연구 해석](report_ko.md)
- [검증된 분석 JSON](results/20261014T024817Z_ca372238/analysis.json)
- [배분별 전체 및 과제별 결과](results/20261014T024817Z_ca372238/allocation_summary.csv)
- [원래 seed별 결과](results/20261014T024817Z_ca372238/original_seed_effects.csv)
- [선택 규칙 비교](results/20261014T024817Z_ca372238/rule_summary.csv)
- [20k와 40k의 배분 순위](results/20261014T024817Z_ca372238/horizon_contexts.csv)
- [A 조합의 200k 출발점과 비교](results/20261014T024817Z_ca372238/composition_200k_comparison.csv)
- [배분 효과 PNG](results/20261014T025205Z_figures_e78210f9/allocation_effects.png) · [SVG](results/20261014T025205Z_figures_e78210f9/allocation_effects.svg)
- [과제별 성공률 PNG](results/20261014T025205Z_figures_e78210f9/task_success.png) · [SVG](results/20261014T025205Z_figures_e78210f9/task_success.svg)

독립 분석은 원시 평가 81,600개 행, 실행 소스, 짝지은 출발점과 continuation RNG, 평가 사례, 전체 checkpoint 246개와 파일 hash, 실제 배분량, 동결한 선택 규칙, 자동 보고서와의 일치를 확인했습니다. 15,226개 기술 검사 통과는 자료의 무결성 검증이며 과학적 효과에 대한 검정이 아닙니다. 독립 original seed는 조합마다 세 개이고, 각 seed의 continuation 세 개는 그 안에 묶여 있습니다.

분석은 `analyze.py`, 그림은 `plot_results.py`에 독립 구현했습니다. 이전 실험 코드를 import하거나 수정하지 않습니다. 각 실행은 새 결과 디렉터리를 만들고 소스 사본·hash·입력 hash를 보존합니다. 분석기는 Python 표준 라이브러리만, 그림은 기록된 Matplotlib 버전을 사용합니다. 새 RL 학습과 환경 평가는 모두 0입니다.

```powershell
C:\Python312\python.exe 21_e3_completed_results_analysis_v1\analyze.py
C:\Python312\python.exe 21_e3_completed_results_analysis_v1\plot_results.py --analysis <새로운분석경로>\analysis.json
C:\Python312\python.exe 21_e3_completed_results_analysis_v1\verify_report.py
```

`verify_report.py`는 이 보고서가 참조하는 고정된 분석·그림의 hash, 표의 수치, 로컬 링크와 수동 그림 검토 기록을 확인합니다. 검증 기록은 매번 새 `results/*_report_verification_*/`에 남기며 그림 생성 당시의 manifest는 수정하지 않습니다.

원본은 기존 D 드라이브 캠페인에 보존되어 있습니다. 이 분석의 입력 경로와 SHA-256은 [input_hashes.json](results/20261014T024817Z_ca372238/input_hashes.json)에 기록했습니다. 이전 E0–E2 GitHub Release의 보관 범위는 그대로이며 이 새 분석이 그 Release의 내용을 바꾸지는 않습니다.
