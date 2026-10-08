# P0 200k 출발점의 후속 seed 재현성 확인 v1

2026-10-08 사용자가 승인한 **15개 추가 분기**를 실행하는 독립 버전입니다.
P0 seed 901의 동일한 200k 전체 checkpoint에서 후속 seed **1903·1904·1905**를 사용합니다.
기존 발견용 seed 1901·1902의 10분기는 다시 학습하지 않고 고정된 비교 자료로 읽습니다.

**실행 상태:** 2026-10-08 12:05:54 KST에 CUDA 본 실행을 시작했습니다.
[실행 계획](results/20261008T030554Z_branch_replication_cuda_2c28c437/run/execution_plan.json)은
15분기·600k로 고정했고, 실행 소스 commit은 `f799ad5f81ccc9e4bee50b419192cb14bbd2e919`입니다.
12:07 KST에 [공통 출발점 200개 평가 사례의 동일성 검사](results/20261008T030554Z_branch_replication_cuda_2c28c437/run/baseline/discovery_comparison.json)를
통과한 뒤 `repeat_1903_U` 학습에 진입했습니다. 약 14:10 KST 종료 예상이며 시스템 부하에 따라 변동합니다.
이 문단은 시작 기록입니다. 완료 여부와 실제 비용은 실행 폴더의 `run_summary.json`으로 확인합니다.

| 항목 | 고정 조건 |
| --- | --- |
| 공유 정책 | 상태·task ID를 입력받는 SAC, 은닉층 256×256 |
| 출발점 | 원래 seed 901의 200k: 199,000 updates, replay 100k와 전체 학습 상태 |
| 배분 | U, F_DO, F_DC, F_WO, F_WC 다섯 개 |
| 후속 seed | 1903, 1904, 1905 |
| 분기당 학습 | 40k transitions, 40k SAC iterations, 500-step episode 80개 |
| 총 본 실험 학습 | 15분기, 600k transitions, 600k SAC iterations, 1,200 training episodes |
| 평가 | 공통 시작점 1회, 각 분기 추가 20k·40k에서 네 과제 각각 50개 사례 |
| 총 본 실험 평가 | `200 + 15 × 2 × 200 = 6,200 episodes`; 고유 초기 상태 200개 |
| 평가 transitions 상한 | 3.1M, 학습 포함 전체 환경 transitions 상한 3.7M |
| 전체 상태 저장 | 공통 200k 사본 1개, 분기별 220k·240k 각 1개: 총 31개 |
| 실행 | RTX 3070, 단일 worker가 seed별·후보별 순차 실행 |

U는 과제별 25%, 강조 배분은 해당 과제 62.5%와 나머지 각 12.5%를 새로 수집합니다.
매 4k 블록에서 정확한 episode 수를 지키며, 모든 분기가 같은 원래 전체 상태에서 시작합니다.
warm-up은 반복하지 않습니다. 분기 종료의 누적 model step은 240k, update 수는 239,000입니다.

02의 학습기 코어 다섯 모듈은 바이트 단위로 같은 로컬 사본입니다. 04의 실행기를 독립 복사해
세 개의 새 seed 및 발견용·확인용 분리 보고를 추가했습니다. 이전 버전 코드를 import하지 않습니다.
같은 CUDA·의존성 버전을 사용하며, 원래 P0 및 발견 실험의 파일·소스 hash를 실행 전후 확인합니다.

## 실행 전에 고정한 분석

기준은 [replication.json](configs/replication.json)에 저장하며 소스 hash와 함께 동결합니다.
사전 고정 선택은 Uniform=U, Failure=F_DO, Progress=F_WC입니다.

1. **주평가:** 추가 40k에서 각 강조 배분의 네 과제 평균 성공률 − 동일 후속 seed의 U 평균 성공률.
   시작점 대비 실제 개선과 과제별 손실도 함께 보고합니다.
2. **보조 관찰:** 40k의 DO 성공률에서 F_DC − F_DO의 방향과 크기.
3. **보조 관찰:** F_DO의 WC가 20k에서 시작점보다 낮아지고, 40k에서 시작점 이상으로 회복하는지.
   세 시점의 실제 성공률을 모두 보고하며 0%→100%라는 특정 수치의 재현만 요구하지 않습니다.

새 세 seed의 결과를 먼저 보고하고, 기존 두 seed와 분리한 뒤 전체 다섯 seed를 기술적으로 요약합니다.
각 반복의 결과, 평균, 최솟값·최댓값, U 대비 양수·0·음수 반복 수를 기록합니다.
이 범위는 신뢰구간이 아니며 통계적 유의성을 자동 판정하지 않습니다. 원래 사전학습 정책은
여전히 하나이고, 같은 평가 초기 상태를 반복 사용합니다. 과제 간 인과적 전이나 상태 의존적
최적 배분의 원인을 이 실험만으로 확정하지 않습니다. 성능이 좋아지는 것은 실행 성공 조건이 아닙니다.

## 검증과 비용

본 실행 전 새 폴더에서 CUDA 사전검증 10개 gate와 실제 200k 출발점의 실행기 smoke를 통과해야 합니다.
단위 검사는 예산, 복원, cohort 분리, 보조 대비, 평가 metadata 차이와 물리적 결과 차이를 검사합니다.
smoke는 기존 발견용 seed 1901에서 후보별 4k, 총 20k를 사용하고 공개 진단 과제당 2개만 평가합니다.
smoke 결과는 본 실험에 합산하지 않으며 결과 평가 bank의 정책 성능을 측정하지 않습니다.
사전검증과 smoke의 실제 비용은 각 실행 장부에 별도로 저장합니다.

[CUDA 사전검증](results/20261008T025609Z_cuda_4f86cee8/validation_report.md)은 10/10 gate를 통과했고,
포함된 단위 검사 13개도 모두 통과했습니다. 소스와 설정은 해당 실행의 snapshot/hash로 보존했습니다.

[실행기 smoke](results/20261008T025748Z_branch_smoke_cuda_c2669d8d/run/run_summary.json)도
5/5 분기를 완료했습니다. 별도 검증 비용은 학습 20k, 진단 평가 48 episodes,
평가 transitions 15,065, 총 경과 209.3초입니다. 본 실험 결과 bank는 사용하지 않았습니다.

본 실행 시작점은 기존 결과 bank에서 DO 6%, DC 100%, WO 4%, WC 84%, 평균 48.5%였습니다.
새 실행의 기준 평가를 다시 수행해 같은 초기 상태·성공·보상·episode 길이가 재현되는지 확인합니다.
평가 metadata의 `context`는 새 실험 이름이므로 원래 해시와 직접 비교하지 않고 실제 결과를 비교합니다.
새 seed의 reset 번호와 실제 초기 상태는 기존 발견용 반복 및 평가 bank와 분리되는지 검사합니다.

기존 10분기의 82분 14초를 기준으로 본 실행은 약 2시간으로 예상합니다. 이는 평가를 포함한
대략적 추정이며 사전검증·smoke·시스템 부하에 따른 변동은 별도입니다.
새 사전학습 seed, 새 평가 bank, 예산 연장, hyperparameter 변경은 이 단계에 포함하지 않습니다.

환경 준비 중 첫 pip 요청은 샌드박스 네트워크 제한(WinError 10013)으로 실패했고,
승인된 재시도에서 기존 버전과 같은 pinned 패키지를 새 `.venv`에 설치했습니다.

## 실행과 산출물

```powershell
.\.venv\Scripts\python.exe -u run_validation.py --device cuda
powershell -NoProfile -ExecutionPolicy Bypass -File .\launch_branches.ps1 -Smoke -Preflight results\<CUDA검증>
powershell -NoProfile -ExecutionPolicy Bypass -File .\launch_branches.ps1 -Preflight results\<CUDA검증> -RunnerValidation results\<smoke>\run
```

각 실행은 새로운 `results/<UTC>_<stage>_<ID>/`에 기록합니다. 기존 폴더와 checkpoint는
덮어쓰지 않으며 실행 당시 소스 사본, hash, 설정, 패키지, seed, 실제 비용과 실패를 보존합니다.
연구 실행에는 `frozen_replication_analysis_plan.json`, `discovery_provenance.json`,
`baseline/discovery_comparison.json`과 분기별 학습·평가·복원·reset 검증 기록이 남습니다.
완료 시 새 세 반복의 `allocation_comparison.csv`, 발견·확인·전체를 구분한 `cohort_summary.csv`,
`prespecified_secondary_contrasts.csv`, `replication_summary.json`을 생성합니다.
