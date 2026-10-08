# Robot practice allocation

사전학습된 공유 정책에 제한된 추가 연습을 배분할 때, 현재의 실패율과
추가 학습의 가치가 일치하는지

설계 기준: [로컬 파일럿 설계 v0.1](LOCAL_PRACTICE_ALLOCATION_PILOT_DESIGN_20261007.md).

## 독립 버전

| 폴더 | 목적 | 실행 범위 |
| --- | --- | --- |
| [01_implementation_validation_v1](01_implementation_validation_v1/README.md) | 최초 구현과 재현성 검증 | CPU·CUDA 각각 10/10 검사 통과, P0 미실행 |
| [02_p0_uniform_pretraining_v1](02_p0_uniform_pretraining_v1/README.md) | P0 균등 사전학습 | seed 901·CUDA·400k 완료, 공개 진단 macro 61.25% |
| [03_p0_pretraining_analysis_v1](03_p0_pretraining_analysis_v1/README.md) | P0 결과와 구현·평가 자료 분석 | 과제별 성능·짝지은 변화·불확실성·실제 학습 노출 확인, 68/68 검사 통과 |
| [04_p0_allocation_branches_v1](04_p0_allocation_branches_v1/README.md) | 동일 200k 출발점의 추가 연습 배분 비교 | 5개 배분 × 후속 seed 1901·1902, 분기당 40k; 10/10 완료, 원자료 검사 367/367 통과 |
| [05_results_github_archive_v1](05_results_github_archive_v1/README.md) | 전체 실험 결과의 GitHub 보관 | 01~04와 저장소 문서 1,425개 파일, 모델 checkpoint 39개 포함; 5개 ZIP의 원본 SHA-256 대조 통과 |
| [06_p0_branch_replication_v1](06_p0_branch_replication_v1/README.md) | 같은 200k 출발점의 후속 seed 재현성 확인 | seed 1903·1904·1905 × 5개 배분 × 40k, 총 15분기·600k; 2026-10-08 14:14 KST 완료 |
| [07_p0_replication_analysis_v1](07_p0_replication_analysis_v1/README.md) | 새 세 반복의 독립 검증·결과 해석 | 원자료·출처 검사 1,127/1,127 통과; 새 세 반복을 우선 보고하고 기존 두 반복·전체 다섯 반복을 구분; 대화형 보고서와 PNG·SVG |
| [08_followup_experiment_design_v1](08_followup_experiment_design_v1/README.md) | 현재 관찰을 바탕으로 한 후속 실험 설계 | 동결한 E0~E4·선택적 R 설계; E0~E3 실행은 09~13에서 관리 |
| [09_fresh_evaluation_audit_v1](09_fresh_evaluation_audit_v1/README.md) | E0 새 평가 사례와 Failure 측정 점검 | 기존 부모·25분기 재평가, 학습 없이 평가 10,800회 |
| [10_independent_seed_checkpoint_study_v1](10_independent_seed_checkpoint_study_v1/README.md) | E1 독립 사전학습 seed와 시점 | 원래 seed 11·12·13, 200k·400k 출발, 90분기·4.80M 학습 |
| [11_fixed_target_donor_swap_v1](11_fixed_target_donor_swap_v1/README.md) | E2 목표 과제 수집량 고정 | E1 200k 재사용, DC/WO 배분 교환, 27분기·1.08M 학습 |
| [12_task_composition_study_v1](12_task_composition_study_v1/README.md) | E3 과제 구성 변경 | B·C 조합 각각 3개 원래 seed, 90분기·4.80M 학습 |
| [13_e0_e3_autonomous_queue_v1](13_e0_e3_autonomous_queue_v1/README.md) | 승인된 E0→E1→E2→E3 자동 실행 | 총 10.68M 학습·207분기·194,400 평가, 20k 저장과 무인 재시작 |

완료한 구현은 보존합니다. 각 단계는
목적이 드러나는 새 폴더에 독립된 코드와
설정으로 관리합니다. 기존 버전의 코드에 의존하도록 import하지 않습니다.

각 실행 결과는 해당 버전의 `results/<UTC시각>_<장치>_<고유ID>/`에 저장합니다.
기존 실행이나 checkpoint를 덮어쓰지 않으며 실패한 실행도 남깁니다.
코드·설정·검증 요약은 Git으로 관리합니다. 2026-10-08 전체 결과 업로드 요청에 따라
대용량 checkpoint·replay·실행 당시 소스 사본과 실패한 실행도
[전체 결과 GitHub Release](https://github.com/rlatmddn0211/practice_allocation/releases/tag/experiment-results-2026-10-08-v1)에 보관합니다.
Release의 `00`~`04` ZIP 다섯 개를 같은 디렉터리에 풀면 원래 폴더 구조가 복원됩니다.
가상환경과 Python 캐시, Git 내부 파일, 실행 잠금 파일은 제외합니다.
원본 파일과 ZIP의 hash 목록은 [보관 manifest](05_results_github_archive_v1/results/20261008T023322Z_complete_archive_6169480e/archive_manifest.json)에 있습니다.

사용자가 2026-10-07에 승인한 P0 사전학습은 같은 날 15:59:45 KST에 완료했습니다.
400k 공개 진단은 DO 5%, DC 100%, WO 40%, WC 100%로 과제당 20개 초기 상태에서
평가한 결과입니다. 사전 규칙에 따라 첫 분기점은 200k로 고정되었습니다.
P0 결과의 해석과 제한사항은 [P0 상세 분석](03_p0_pretraining_analysis_v1/README.md)에
정리했습니다. 사용자 승인 후 같은 날 18:11:27 KST에 별도 버전에서 첫 10분기 실행을
시작해 19:33:42 KST에 완료했습니다. 추가 학습 400k와 결과 평가 4,200회를 수행했고,
두 후속 seed의 배분 순위는 달랐습니다. 학습·평가 프로토콜과 결과표는
[분기 실행 문서](04_p0_allocation_branches_v1/README.md)에 있습니다.

2026-10-08 승인된 다음 단계는 같은 출발점과 평가 bank에서 후속 seed 세 개를 추가하는
[재현성 확인 실험](06_p0_branch_replication_v1/README.md)입니다. 새 세 반복은 기존 발견용
두 반복과 구분해 보고하고, 전체 다섯 반복의 합산 결과는 기술적 요약으로 제시합니다.
CUDA 사전검증 10/10·단위 검사 13/13·실행기 smoke 5/5를 통과했고,
12:07 KST에 기존 출발점의 200개 평가 사례가 같은 결과를 내는지 확인한 뒤 첫 분기 학습을 시작했습니다.

15개 분기는 14:14:14 KST에 모두 완료했습니다. 새 세 반복의 40k 평균 성공률은
균등 49.00%, 서랍열기 집중 49.33%, 서랍닫기 집중 55.00%, 창문열기 집중 55.33%,
창문닫기 집중 54.17%입니다. 서랍닫기·창문열기 집중은 새 세 seed 모두에서 균등을 앞섰고,
실패율 규칙이 선택한 서랍열기 집중은 1승·2패였습니다. 이는 한 원래 seed의 한 출발점에
대한 결과이며 적응형 선택기의 효과를 입증하지 않습니다.
[완료 결과 분석](07_p0_replication_analysis_v1/README.md)에 반복된 관찰과 재현되지 않은 관찰,
과제별 변화, 비용, 검증 기록을 정리했습니다. 06의 대용량 모델·replay는 로컬 원본에
보존되며, 앞서 올린 00~04 Release ZIP에는 포함되지 않습니다.
