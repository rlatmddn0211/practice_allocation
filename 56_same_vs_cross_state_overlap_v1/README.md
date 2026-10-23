# 56 — Same-state versus cross-state case overlap

기존 두 8k 상태의 공통 적격 사례를 맞춰 네 old/new 미래 쌍의 초과 중첩을 비교한 독립 분석 버전이다. **새 환경 step 0**. 이전55번과54번은 보존한다.

- [한국어 결과 보고서](report_ko.md)
- [해석 보완과 계산 전 고정한 명세](methods_addendum_ko.md)
- [근거 원장](evidence_record_ko.md)
- [분석 설정](analysis_config.json)

획득의 동일−교차 초과 중첩 차이 **+0.199%p**(조건부 사례구간 [+0.041,+0.357]), 상실 **−0.159%p**([−0.375,+0.054]). 성공률 개선 단위가 아니다. 획득 차이는3부모양수·2제로, DC·PU 기여95.9%. 상태와 연결된 구조의 탐색적 근거이며 특정 원인·선택기 효과는 미검증이다.

## 보존 실행

| 작업 | 결과 디렉터리 | 확인 |
|---|---|---|
| 주 분석 | [20261022T035037Z_analyze_9e4e0e84](results/20261022T035037Z_analyze_9e4e0e84/COMPLETE.json) | 입력·상태 기록106검사 |
| 독립 검산 | [20261022T035234Z_verify_fdfb3853](results/20261022T035234Z_verify_fdfb3853/COMPLETE.json) | 3,103검사, 모든 사례·부모 재표집 대조 |
| 그림 | [20261022T035334Z_make_figure_e15b9cd8](results/20261022T035334Z_make_figure_e15b9cd8/COMPLETE.json) | PNG 육안 확인, SVG 제공 |

## 재실행

저장소 루트 PowerShell에서 아래 명령을 각각 실행한다. 매번 새 결과 폴더를 만들고 코드·명세 snapshot/hash를 남긴다. 기존 결과를 덮어쓰지 않는다. 학습 환경이나 checkpoint 모델을 로드하지 않으며 NumPy를 사용하는 파일 분석이다. 그림은 Matplotlib도 사용한다.

```powershell
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 56_same_vs_cross_state_overlap_v1\run.py analyze
```

검산·그림 생성 시 마지막 인수는 점검할 주 분석 폴더다. 아래는 보존된 결과를 대상으로 한다.

```powershell
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 56_same_vs_cross_state_overlap_v1\run.py verify 56_same_vs_cross_state_overlap_v1\results\20261022T035037Z_analyze_9e4e0e84
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 56_same_vs_cross_state_overlap_v1\run.py make_figure 56_same_vs_cross_state_overlap_v1\results\20261022T035037Z_analyze_9e4e0e84
```

Python3.12.0 / NumPy2.2.4 / Matplotlib3.10.1. 각 실행 runtime에 실제 버전을 기록한다. 원본 평가 CSV·state manifest·checkpoint manifest 등 연결된 로컬 입력이 필요하다. 모델·replay 재학습은 하지 않는다. NPZ 재표집 배열은 로컬에 보존되며 저장소의 기존 대용량 파일 공개 규칙을 따른다.

이 버전은 결과와 검산을 전달한 뒤 동결한다. 이후 구현 변경은 새 번호 디렉터리에 둔다.
