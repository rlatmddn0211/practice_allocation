# P0 추가 연습 배분 10분기 v1

2026-10-07 사용자가 승인한 분기 학습을 실행하는 독립 버전입니다. 출발점은
P0 seed 901의 **200k 전체 checkpoint**이며, 다섯 배분을 후속 학습 seed
**1901·1902**로 각각 40k steps 진행합니다. 전체 추가 학습은 400k steps입니다.

학습기·환경·평가 모듈은 02 버전에서 독립 복사했습니다. 이전 버전의 Python
코드를 import하지 않습니다. 신뢰된 로컬 P0 결과를 읽고, 파일 hash·학습기 소스의
동일성·설정·패키지·전체 상태 복원을 검증한 뒤 이 버전의 checkpoint로 보존합니다.
가중치, optimizer, entropy, replay, 수집기 및 RNG가 원래 상태와 일치해야 합니다.
설정에서 바뀌는 항목은 버전 식별자뿐입니다.

| 후보 | DO 서랍 열기 | DC 서랍 닫기 | WO 창문 열기 | WC 창문 닫기 |
| --- | ---: | ---: | ---: | ---: |
| U | 25% | 25% | 25% | 25% |
| F_DO | 62.5% | 12.5% | 12.5% | 12.5% |
| F_DC | 12.5% | 62.5% | 12.5% | 12.5% |
| F_WO | 12.5% | 12.5% | 62.5% | 12.5% |
| F_WC | 12.5% | 12.5% | 12.5% | 62.5% |

학습 episode는 성공 여부와 관계없이 500 steps입니다. 8개 episode마다 정해진
개수를 무작위 순서로 수집하며, 40k는 10블록입니다. 기존 warm-up을 반복하지 않아
분기마다 정확히 40,000 SAC iterations를 추가합니다. 200k의 199,000회에서 시작해
최종 239,000회가 됩니다. 모든 분기는 같은 출발 상태에서 복원됩니다.

2026-10-07 **18:11:27 KST**에 본 실행을 시작해 **19:33:42 KST에 10/10 분기를 완료**했습니다.
[프로세스 정보](results/20261007T091127Z_allocation_branches_cuda_64ec1ea7/process.json)와
[실행 계획](results/20261007T091127Z_allocation_branches_cuda_64ec1ea7/run/execution_plan.json)을 보존했습니다.
진행 로그는 같은 실행 폴더의 `stdout.log`, `run/progress.jsonl`이며,
[최종 실행 요약](results/20261007T091127Z_allocation_branches_cuda_64ec1ea7/run/run_summary.json)의
상태는 `completed`입니다. 전체 경과 시간은 **82분 14초**, 순수 학습 시간은 62분 7초입니다.
추가 학습 400,000 steps와 SAC iterations 400,000회, 결과 평가 4,200 episodes를 수행했습니다.
실제 평가 transitions는 1,174,989이며 학습을 합한 환경 transitions는 1,574,989입니다.
이 비용은 아래의 별도 사전검증·실행기 검증 비용을 포함하지 않습니다.

**완료 결과: 추가 40k의 네 과제 평균 성공률**

결과 평가 bank에서 공통 시작점은 **48.50%**입니다. 과제별로 DO 6%, DC 100%,
WO 4%, WC 84%이며 각각 50개 초기 상태에서 평가했습니다. P0의 공개 진단은
과제당 20개인 별도 bank이므로, 그때의 200k 평균 48.75%와 구분합니다.

| 배분 | 후속 seed 1901 | 후속 seed 1902 | 두 반복 평균 | 동일 seed의 U 대비 차이 평균 |
| --- | ---: | ---: | ---: | ---: |
| U 균등 | 57.50% | 50.50% | 54.00% | 0.00%p |
| F_DO 서랍 열기 강조 | 54.00% | 56.50% | 55.25% | +1.25%p |
| F_DC 서랍 닫기 강조 | 55.00% | 58.00% | 56.50% | +2.50%p |
| F_WO 창문 열기 강조 | 54.00% | 53.00% | 53.50% | −0.50%p |
| F_WC 창문 닫기 강조 | 57.00% | 56.00% | 56.50% | +2.50%p |

모든 분기는 40k에서 시작점보다 평균 성공률이 높았습니다. 그러나 seed 1901의
최고 배분은 U, seed 1902의 최고 배분은 F_DC로 순위가 달랐고, 두 반복 모두에서
U를 이긴 강조 배분은 없었습니다. 같은 원래 seed 901의 정책에서 이어진 두 반복이므로
평균 +2.50%p만으로 배분의 안정적인 우월성이나 다른 사전학습 seed로의 일반화를
주장할 수 없습니다. 한 반복에서 선택해 다른 반복에서 평가한 사후 진단에서도
U 대비 차이는 각각 0.00%p와 −2.50%p였습니다.

개선은 단조롭지 않았습니다. 예를 들어 F_DO는 추가 20k에서 평균이 28.50%·28.00%로
낮아졌고, 두 반복 모두 WC 성공률이 0%였다가 40k에서 100%로 회복했습니다.
최종 평균 개선과 과제별 유지·회복을 함께 살펴야 합니다.
[20k·40k 배분 비교 원자료](results/20261007T091127Z_allocation_branches_cuda_64ec1ea7/run/allocation_comparison.csv)와
[고정 규칙·반복 간 선택 요약](results/20261007T091127Z_allocation_branches_cuda_64ec1ea7/run/comparison_summary.json)을 보존했습니다.

같은 후속 seed에서는 과제별 방문 순번에 같은 reset seed를 사용합니다. 다른
배분은 방문 상태와 행동이 달라질 수 있습니다. 학습 후 실제 초기 상태 hash를
비교해 공통 reset이 일치하는지 검증합니다. 두 후속 seed는 독립적인 사전학습
정책 두 개가 아니라, 같은 원래 정책에서 이어지는 두 반복입니다.

**평가와 고정 선택 규칙**

P0에서 만들어 둔 결과 평가 bank를 그대로 사용합니다. 과제당 50개 초기 상태,
deterministic 행동, 공식 success 신호, 첫 성공 또는 500 steps에서 종료합니다.
공개 진단 bank와 결과 bank는 분리되어 있습니다.

- 기준 평가는 같은 200k 정책에 대해 한 번 수행하고 열 분기가 공유합니다.
- 각 분기는 추가 20k·40k에서 네 과제를 모두 평가합니다.
- 총 결과 평가 기록은 `200 + 10 × 2 × 200 = 4,200 episodes`입니다.
- 결과 평가의 최대 환경 transitions는 2.1M이며, 학습 400k와 별도로 집계합니다.
- 평가 전후 학습 상태·replay·수집기·RNG가 바뀌지 않았는지 확인합니다.

P0 공개 진단에서 고정한 추천은 Uniform=U, Failure=F_DO, Progress=F_WC입니다.
추천과 입력 hash를 결과 bank 평가 전에 저장하며 이후 결과로 수정하지 않습니다.

Primary는 **추가 40k에서 동일 후속 seed의 U 대비 macro 성공률 차이**입니다.
시작점 대비 절대 개선, 과제별 변화, 최대 성능 하락도 함께 계산합니다. U보다 덜
나빠진 것을 절대 개선으로 해석하지 않습니다. 두 반복을 서로 바꿔 후보 선택과
평가를 분리한 사후 진단도 기록하며, 동률은 U·F_DO·F_DC·F_WO·F_WC 순서로 풉니다.

**검증과 실행**

전용 `.venv`는 사전학습과 같은 패키지 버전을 사용합니다. 큰 시스템 패키지는
재사용할 수 있으나 실제 버전은 매 실행 manifest에 기록합니다.

```powershell
.\.venv\Scripts\python.exe -u run_validation.py --device cuda
.\.venv\Scripts\python.exe -u run_branches.py --smoke --preflight results\<CUDA검증>
powershell -NoProfile -ExecutionPolicy Bypass -File .\launch_branches.ps1 -Preflight results\<CUDA검증> -RunnerValidation results\<실행기검증>
```

본 실행에는 현재 코드·설정·패키지와 일치하는 CUDA 사전검증 10/10 및 실행기
검증 통과가 필요합니다. 실행기 검증은 실제 200k에서 다섯 후보를 각각 4k씩,
후속 seed 1901 하나로 시험합니다. **이 20k는 기술 검증 비용**이며, 공개 진단의
과제당 2개 초기 상태만 평가합니다. 해당 모델과 결과는 본 실험에 사용하지 않고,
본 실험은 다시 원래 200k에서 복원합니다.

- [CUDA 사전검증](results/20261007T090430Z_cuda_fba8321d/validation_report.md):
  10/10 통과. 포함된 단위 검사 9개도 통과했습니다.
- [분기 실행기 검증](results/20261007T090646Z_branch_smoke_cuda_88ace0fa/run/run_summary.json):
  5/5 후보, 총 20k steps 완료. 전체 상태 복원·배분·초기 상태·결과 집계 검사를 통과했고
  결과 평가 bank의 정책 점수는 사용하지 않았습니다.
- [완료 후 원자료 검증](results/20261007T165000Z_completion_audit/verification.json):
  367/367 검사 통과. 원래 P0와 실행 소스의 hash, 21개 전체 checkpoint의 파일,
  분기별 시작 상태·40k 학습·배분·replay 노출, 평가 4,200건, 비용과 비교 지표를
  대조했습니다. 평가에는 동일한 초기 상태 200개를 총 21회 사용했습니다.
  이 검증은 추가 학습·정책 평가 없이 수행했으며, 검사 통과 자체가 과학적 효과의 증거는 아닙니다.

숨겨진 Python 프로세스 하나가 열 분기를 순차 실행합니다. 실행 순서는 seed 1901의
U·F_DO·F_DC·F_WO·F_WC, 이어서 seed 1902의 동일 순서입니다. OS 파일 잠금으로
동일 버전의 중복 실행을 막습니다. 매 실행은 새로운 결과 폴더를 만들며 기존
실행이나 checkpoint를 덮어쓰지 않습니다. 오류가 발생하면 중단하고 실패 기록을
남깁니다. 미완료 분기를 성공 결과로 합산하지 않습니다.

**산출물**

| 파일 | 내용 |
| --- | --- |
| `process.json`, `stdout.log`, `stderr.log` | 백그라운드 실행 정보 및 출력 |
| `run/run_started.json`, `execution_plan.json` | 실제 설정·코드·패키지·seed·계획 |
| `parent_provenance.json` | 고정된 P0 원자료와 소스·checkpoint 검증 |
| `frozen_selection_rules.json` | 결과 평가 이전에 고정한 추천과 입력 hash |
| `initial_checkpoint/` | 200k 전체 상태를 이 버전에서 검증하여 보존한 사본 |
| `baseline/evaluation.json` | 열 분기가 공유하는 시작점 평가 |
| `progress.jsonl`, `stages/`, `cost_ledger.csv` | 진행 상태, 단계별 실제 비용, 오류 |
| `evaluation_episodes.csv` | 기준·20k·40k 평가의 개별 성공과 초기 상태 |
| `branches/repeat_<seed>_<candidate>/` | 분기별 학습 로그·평가·20k/40k checkpoint |
| `branch_started.json`, `branch_summary.json` | 복원 동일성, 배분·업데이트·replay 노출 |
| `training_reset_audit.json` | 실제 초기 상태의 후보 간 일치와 평가 bank 분리 |
| `allocation_comparison.csv`, `task_changes.csv` | 전체·과제별 절대 개선과 U 대비 차이 |
| `paired_success_changes.csv` | 같은 평가 초기 상태의 성공·실패 변화 |
| `frozen_rule_scores.csv`, `comparison_summary.json` | 고정 규칙 및 반복 간 선택 진단 |
| `run_summary.json`, `run_manifest.json` | 완료/실패 상태와 전체 비용 |

진행 속도는 **추가 학습 steps**와 완료된 학습 시간으로 계산합니다. 평가 시간은
별도이며 ETA의 `remaining_training_seconds_excluding_evaluation`에 포함되지 않습니다.
학습 batch 비중은 사전학습 누적 계수를 뺀 분기 중 실제 추출량으로 보고합니다.
추가 경험의 batch 비중과 replay 비중도 구분합니다.

대용량 checkpoint와 소스 스냅샷은 기존 규칙대로 로컬에 보존합니다. 결과 텍스트는
Git 줄바꿈 변환을 비활성화하여 기록된 hash와 파일 bytes를 유지합니다. 새 사전학습
조건이나 원래 seed의 확장은 이 실행에 포함하지 않습니다.
