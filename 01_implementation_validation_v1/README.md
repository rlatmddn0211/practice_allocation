# 01 — 구현 검증 v1

이 폴더는 최초 로컬 파일럿의 독립된 구현입니다. 네 과제의 공유 SAC 학습기와
배분·replay·평가·checkpoint 경로를 실제 MetaWorld 환경에서 검증합니다.
이 단계의 성공률은 학습 효과의 연구 결과로 해석하지 않습니다.

## 검증 결과 — 2026-10-07

아래 두 실행은 현재 코드와 동일한 source hash를 사용하며 각 실행의 비용 장부와
최종 합계도 일치합니다. 이 구현은 검증 완료 버전으로 보존합니다.

| 장치 | 통과 | 경과 시간 | 연속 실행 대비 복원 후 파라미터 최대 차이 | 기록 |
| --- | --- | ---: | ---: | --- |
| CPU, 1 thread | 10/10 | 76.69초 | 0 | [검증 보고서](results/20261007T051026Z_cpu_ecd84d6c/validation_report.md) |
| RTX 3070, CUDA | 10/10 | 68.51초 | 0 | [검증 보고서](results/20261007T050854Z_cuda_900fa782/validation_report.md) |

각 실행은 실제 환경 transitions 34,963개, SAC iteration 5,503회, 평가 20 episodes를
사용했습니다. 주 학습 4,000 steps 외에 배분 fixture, 연속/복원 비교, 짧은 분기 및
평가 검사가 포함된 비용입니다. 평가 20회 중 4회는 성공 처리 검사용 scripted fixture입니다.
두 장치 사이의 학습 결과가 같다는 의미는 아닙니다.

첫 개발 실행에서는 `seed()`만 호출해도 reset 분포가 바뀐다고 가정한 오류가
검출되었습니다. `seeded_rand_vec=True`를 추가하고 서로 다른 task 파라미터와
동일 seed 재현성을 확인했습니다. 해당 [실패 기록](results/20261007T045520Z_cpu_e33dc072/preflight.json)과
중간 검증 기록도 보존합니다. 기존 결과 디렉터리를 다시 지정한 CLI 실행과
이미 존재하는 checkpoint 저장도 거부되는 것을 확인했습니다.

P0 사전학습과 10개 연구 분기는 아직 실행하지 않았습니다.

## 실행

저장소 루트에서 다음 명령을 실행합니다.

```powershell
python -m venv 01_implementation_validation_v1/.venv
./01_implementation_validation_v1/.venv/Scripts/python.exe -m pip install -r 01_implementation_validation_v1/requirements.txt
./01_implementation_validation_v1/.venv/Scripts/python.exe 01_implementation_validation_v1/run_validation.py --device cpu
```

CUDA용 PyTorch가 설치된 환경에서는 `--device cuda`로 같은 검증을 실행합니다.
장치는 명시적으로 기록하며 사용할 수 없는 CUDA를 CPU로 자동 대체하지 않습니다.
설정은 `configs/validation.json`입니다. Python 3.12와 의존성 버전을 고정했습니다.

이 PC에 만든 `.venv`는 기존 CUDA PyTorch를 재사용하기 위해
`python -m venv --system-site-packages ...`로 생성했습니다.
MetaWorld, SB3, Gymnasium은 버전 폴더 안에 설치했습니다.
전역 패키지는 변경하지 않았습니다. 실행 manifest는 실제 의존성 버전을 확인합니다.
완전히 별도의 환경이 필요하면 위 기본 명령으로 새 환경을 만들면 됩니다.

명시적인 결과 경로도 사용할 수 있지만 `results/` 안의 **존재하지 않는**
디렉터리여야 합니다. 기본값은 시각·장치·고유 ID로 새 디렉터리를 만듭니다.

## 검증 내용

1. 정확한 40k 배분, 블록 중간 scheduler 복원, replay 순환·균등 표본,
   시간 제한 bootstrap, 파일 덮어쓰기 거부 등 단위 검사.
2. 네 과제에서 목표와 one-hot 연결, 같은 seed의 동일 물리 상태와 행동 궤적,
   다른 seed의 서로 다른 task 파라미터.
3. 다섯 후보를 실제로 한 블록씩 실행: 총 20,000 환경 transitions.
   공식 scripted policy는 성공 후에도 학습 episode가 계속되는지 검사하는 fixture입니다.
4. 공개 진단 20회/과제, 결과 평가 50회/과제: 총 280개의 서로 다른 초기 상태.
5. 설계와 같은 256×256 공유 SAC, replay 100k, batch 256, warm-up 1k로
   균등 수집 4,000 steps와 실제 gradient update 3,000회.
6. 업데이트 후 episode 경계에서 전체 학습 상태 저장 및 기존 checkpoint 덮어쓰기 거부.
7. 공개 진단 bank 중 과제당 2회를 두 번 평가하고 전체 학습 상태·RNG 불변성 확인.
   별도의 scripted fixture 4회로 성공 집계와 성공 시 평가 조기 종료를 확인하며
   CSV의 `policy_type`으로 학습 정책의 평가와 구분.
8. 연속 1,000-step 학습과 저장 후 재개한 1,000-step 학습의 행동·관측·표본 인덱스·loss·
   replay·파라미터·optimizer·RNG 비교. 같은 실행 환경에서 bitwise equality를 요구합니다.
9. 기록 기능을 추가한 SAC의 실제 업데이트가 stock SB3 SAC와 동일한지 비교.
10. 모든 후보의 분기 초기 상태 동일성, 500-step 강조 분기의 warm-up 미재시작,
    새 경험의 batch 노출, episode 중간 checkpoint 거부 검사.

중간 검사가 실패하면 후속 검사를 중단하고 실패 이유와 이미 발생한 비용을 기록합니다.
CPU 검증과 CUDA 검증은 각 장치 내부의 재현성을 검사하며 장치 사이의 동일 궤적을
주장하지 않습니다. P0, 40k×10 분기, 60분기 확장은 실행하지 않습니다.

## 구현에서 고정한 선택

- MetaWorld 3.0.0의 기본 `v2` dense reward, 관측/보상 정규화 없음.
- 39개 목표 관측 상태에 과제 one-hot 4개를 붙인 43차원 입력. 행동은 4차원 `[-1, 1]`.
- actor와 두 critic을 네 과제가 공유. critic 입력은 상태 43 + 행동 4.
- 매 episode를 새 물리 환경에서 시작하고 공식 연속 reset 분포에서 샘플링.
  이 버전의 `reset(seed=...)`는 seed를 무시하므로 `seed()`와
  `seeded_rand_vec=True`, `_freeze_rand_vec=False`를 함께 명시합니다.
  해당 버전의 내부 API 사용은 `environment.py`에 한정합니다.
- 학습 성공으로 episode를 끝내지 않음. 500번째 step은 truncation으로 저장하며
  SAC target의 bootstrap을 유지. 평가에서는 첫 성공 시 중단 가능.
- SB3 `SAC.train()`을 그대로 호출하고 수집 루프만 직접 관리하여 저장 시점을
  transition 저장 및 예정된 gradient update 이후로 고정.
- 실제 TD error 기록은 업데이트에 사용된 tensor를 관찰하는 hook을 사용하며
  추가 난수 표본을 뽑지 않음. stock update와의 일치 여부를 별도로 검사.
- 체크포인트는 episode 경계에서만 지원. 다음 reset을 아직 수행하지 않은 상태를
  저장하므로 진행 중인 MuJoCo 시뮬레이션을 불완전하게 직렬화하지 않음.
- continuation repeat에서는 학습 상태를 복원한 뒤 후속 난수 스트림만 새로 지정.
  후보 간 동일 task의 k번째 방문은 같은 reset seed를 사용.

## 파일 구성과 결과

| 파일/폴더 | 역할 |
| --- | --- |
| `configs/validation.json` | 검증 설정과 SAC의 명시적 공통 설정 |
| `practice_allocation/core.py` | 설정, seed 계층, 배분 scheduler, hash |
| `practice_allocation/environment.py` | 실제 환경 초기화·입력·종료 검사 |
| `practice_allocation/learning.py` | 공식 SAC, 실제 replay·TD 진단 |
| `practice_allocation/engine.py` | 수집·업데이트·분기·전체 상태 복원 |
| `practice_allocation/evaluation.py` | 평가 bank와 학습 상태가 격리된 평가 |
| `practice_allocation/preflight.py` | 순차 검증과 비용·실패 기록 |
| `tests/test_contracts.py` | 재현성을 훼손할 수 있는 오류의 회귀 검사 |
| `results/<run>/preflight.json` | 전체 검증 결과와 미실행 항목 수 |
| `results/<run>/run_manifest.json` | 핵심 패키지 pin과 전체 설치 목록·코드 hash·장치·설정·seed·실제 비용 |
| `results/<run>/train_metrics.csv` | 실제 수집량, 실제 batch 구성, loss·TD·entropy |
| `results/<run>/eval_episodes.csv` | 초기 상태 hash를 포함한 episode별 평가 결과 |
| `results/<run>/cost_ledger.csv` | 검사별 실제 transition, update, reset, 평가와 시간 |
| `results/<run>/source_snapshot/` | 해당 실행이 사용한 코드 복사본, 로컬 보존 |
| `results/<run>/checkpoints/` | 모델·optimizer·replay·collector·RNG는 로컬 보존, manifest는 Git 관리 |

reset 내부의 물리 적분은 agent transition 수에 넣지 않고 reset 횟수와 경과 시간에
반영합니다. 설치 및 별도 개발 probe 비용은 검증 실행의 비용과 구분합니다.

참고 구현: [SB3 SAC](https://stable-baselines3.readthedocs.io/en/v2.7.1/modules/sac.html),
[MetaWorld](https://github.com/Farama-Foundation/Metaworld).
