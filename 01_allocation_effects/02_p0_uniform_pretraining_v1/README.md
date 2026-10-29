# P0 균등 사전학습 v1

공유 SAC 정책 하나로 DO·DC·WO·WC를 균등하게 사전학습합니다.
`01_implementation_validation_v1`의 검증된 학습기를 독립 복사했으며,
이전 버전의 코드나 checkpoint를 가져와 학습을 시작하지 않습니다.

## 이번 실행

2026-10-07 15:03:10 KST에 P0 실행을 시작했습니다.
학습 전 공개 평가를 마친 뒤 같은 프로세스에서 400k 학습을 진행합니다.

- [최종 CUDA 사전검증](results/20261007T054900Z_cuda_5f792813/validation_report.md): 10/10 통과.
- [실행기 검증](results/20261007T060132Z_runner_smoke_cuda_bee7ea02/run/run_summary.json):
  8,000 steps, 7,000 updates, 전체 상태 저장·복원 2회, 공개 평가 격리 검사 통과.
- [P0 실행 정보](results/20261007T060310Z_p0_cuda_50621c50/process.json),
  [고정 설정과 실행 manifest](results/20261007T060310Z_p0_cuda_50621c50/run/run_started.json).
- 로컬 진행 로그: `results/20261007T060310Z_p0_cuda_50621c50/stdout.log` 및
  `run/progress.jsonl`. 종료 결과는 같은 `run/`의 `run_summary.json`에 기록됩니다.

중간 검증과 프로세스 생성 실패 기록도 보존합니다. 첫 생성 실패는 Windows의
중복 Path/PATH 환경변수로 발생했고, 실행기 안에서 처리한 뒤 새 실행으로 확인했습니다.

## 고정한 실험

| 항목 | 설정 |
| --- | --- |
| 시작 | seed 901, 새 무작위 초기화 |
| 장치 | CUDA, RTX 3070, 학습 프로세스 1개 |
| 학습량 | 총 400,000 transitions, 과제당 100,000 |
| 배분 | 4,000-step 블록마다 과제별 500-step episode 2개 |
| 정책 | 공유 actor 1개, 공유 critic 2개, 은닉층 256·256 |
| SAC | batch 256, replay 100k, lr 3e-4, gamma .99, tau .005, 자동 entropy |
| 업데이트 | 첫 1,000 steps warm-up 이후 transition당 1회; 최종 399,000회 |
| 공개 진단 | 0·100k·200k·400k, 매번 과제별 고정 20 episodes |
| 전체 상태 저장 | 200k·400k, episode 종료 및 업데이트 완료 직후 |
| 결과 bank | 과제당 50개 초기 상태만 생성; P0에서는 점수를 평가하지 않음 |

관측은 목표가 보이는 39차원 상태와 4차원 task ID, 행동은 4차원입니다.
기본 v2 dense reward를 그대로 쓰며 관측·보상 정규화는 없습니다.
학습 episode는 성공해도 500 steps를 채우고 시간 제한에서 bootstrap합니다.
평가는 첫 성공 또는 500 steps에서 끝냅니다.
공개 평가 최대 비용은 160,000 transitions이며 학습 비용과 별도로 기록합니다.

200k에서 두 과제 이상에 성공과 실패가 모두 있으면 해당 checkpoint를 선택합니다.
그렇지 않으면 400k에 같은 규칙을 적용합니다. P0는 400k까지 완료합니다.
둘 다 조건을 만족하지 않으면 분기를 보류합니다. Failure·Progress 추천과
입력 hash를 공개 진단만으로 저장합니다. 연구용 10분기는 별도 실행 단계입니다.

## 검증과 실행

전용 `.venv`는 검증 버전과 같은 패키지 버전을 사용합니다.
설치 시 시스템의 큰 패키지를 재사용할 수 있으나 실제 해석된 버전을 기록합니다.

```powershell
python -m venv --system-site-packages .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -u run_validation.py --device cuda
.\.venv\Scripts\python.exe -u run_pretraining.py --smoke --preflight results\<검증실행>
powershell -NoProfile -ExecutionPolicy Bypass -File .\launch_pretraining.ps1 -Preflight results\<검증실행> -RunnerValidation results\<실행기검증>
```

8k smoke는 별도 결과 폴더에서 두 번의 전체 저장·복원과 세 번의 평가를 수행합니다.
본 P0는 현재 소스·설정·패키지와 일치하는 10/10 사전검증 및 smoke 통과를 요구합니다.
기술 검증에서 학습한 모델은 P0에 사용하지 않습니다.
위 명령의 실행 정책은 해당 PowerShell 프로세스에만 적용됩니다.

백그라운드 실행은 숨겨진 프로세스로 시작하며 실행마다 새 `results/<시각>_p0_cuda_<ID>/`
폴더를 만듭니다. `process.json`에 실행 경로가 있고 `stdout.log`와 `stderr.log`가
출력됩니다. 실제 Python PID는 `run/run_started.json` 또는 `run/progress.jsonl`에 있습니다.
현재 버전에서 중복 P0 실행은 OS 파일 잠금으로 차단합니다.

## 기록

- `run_started.json`, `resolved_config.json`, `execution_plan.json`: 실행 전 고정 정보.
- `source_snapshot/`: 실제 소스 복사본. 실행 중 코드·설정을 수정하지 않습니다.
- `train_metrics.csv`: 매 250 steps의 loss, entropy, TD error, 수집·batch 과제 구성.
- `train_episodes.csv`: 모든 학습 episode의 task, 성공, return, 길이, 초기 상태 hash.
- `progress.jsonl`: 단계 전환 및 4k 블록 감사 기록. append 방식입니다.
- `diagnostic_episodes.csv`, `diagnostics/`: 공개 평가의 episode별 결과와 요약.
- `evaluation_banks.json`: 공개·결과 bank의 서로 다른 물리적 초기 상태.
- `checkpoints/`: 모델·optimizer·entropy·replay·수집기·RNG 전체 상태와 파일 hash.
- `restore_verification.json`: 각 checkpoint를 실제 복원한 뒤 전체 상태 일치 확인.
- `stages/`, `cost_ledger.csv`: 단계별 시간과 실제 transition·update·reset 비용.
- `selectors/`, `selected_checkpoint.json`: 공개 진단으로 동결한 선택 근거.
- `run_summary.json`, `run_manifest.json`: 완료 또는 실패 상태. 오류 시 traceback 보존.

완성된 결과와 checkpoint는 덮어쓰지 않습니다. 가상환경, 소스 복사본,
대용량 checkpoint는 로컬에 보존하며 코드·설정·텍스트 결과는 Git으로 관리합니다.
구현 검증의 성공과 연구 가설의 성공은 구분합니다.
