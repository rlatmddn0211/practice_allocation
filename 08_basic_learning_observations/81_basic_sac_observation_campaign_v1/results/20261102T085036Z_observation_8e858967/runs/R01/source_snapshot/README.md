# 기본 SAC 관측 캠페인 81

사용자가 지정한 다섯 독립 초기학습 실행, DO/DC/Push/BP 네 과제,
실행당 총 1,000,000 실제 환경 전이를 관측한다. 제안 방법이나 선택기를
추가하지 않는다. 이전 버전은 변경하거나 새 버전을 import하게 만들지 않는다.

기본 코드는 77번의 보존된 stock SAC/Engine 복사본이며, suite B의 fresh
초기화와 U 스케줄은 기존 10번/44번 및 원래 P0 구현과 대조했다.
기존 checkpoint를 초기 가중치로 사용하지 않는다. 주어진 운영 수치들은
이번 관측 규약이며 검정력 보장이 아니다.

실행 환경은 기존 13번 .venv의 Python/CUDA/라이브러리를 재사용한다.
패키지나 벤치마크를 업그레이드하지 않는다.

## 재현 순서

1. prepare.py는 기본 소스 복사, 자산 해시와 운영 규약을 생성한다. 이미 준비된
   파일은 덮어쓰지 않는다.
2. campaign.py prepare는 고유 결과 디렉터리와 소스 snapshot을 만든다.
3. campaign.py campaign --campaign 경로는 누적 10k 안의 기술 검사 후
   동결한 R01~R05를 두 프로세스씩 수행하고, 파일 분석과 한국어 보고서까지 수행한다.
4. status.json/RUNNING_STATUS.md는 진행 상태이며 결과를 판정하는 기준이 아니다.
5. 최종 보고서는 LATEST_ANALYSIS.json의 실제 경로로 확인한다.

## 기록과 단위

모든 전이는 에피소드별 numerical NPZ와 JSON sidecar로 연결한다.
sidecar의 experiment/run/attempt/task/split/episode/case/checkpoint 상수와
NPZ의 행별 counter를 합치면 공통 분석 schema가 된다. 원본 float64 물리/환경
관측과 실제 float32 정책 입력을 구분한다. 시간 번호는 행동 이후 episode_step=1부터다.
success는 현재 반환 상태의 공식 판정이며, success_any는 별도 누적 집계다.

본실험 train transition_id=run_ordinal*10,000,000+수집 순번이며 replay 슬롯과
독립이다. 평가 ID는 같은 run namespace의 1,000,001 이후에 평가시점/사례/step을
결합한다. 기술·무효 시도는 자체 출력/attempt namespace에 보존되며 본자료에 합치지 않는다.

원래 SAC는 하나의 배치를 actor와 두 critic에 사용한다. critic_sample_count는
배치 사용 횟수이며 두 critic 수로 곱하지 않는다. 표집 RNG는 원래 NumPy 경로,
수집과 SAC stochastic action은 원래 PyTorch learner stream의 결합을 유지한다.
250번째 업데이트의 상세 batch ID와 항목별 누적 count는 모든 배치의 복원을 뜻하지 않는다.

사전 선택한 평가 사례당 영상은 정기 평가 자체에 붙이며 별도 rollout을 하지 않는다.
원시 endpoint 접촉은 물리 substep의 전체 접촉 이력이 아니다. snapshot은 실제 기술
영수증의 동일 runtime 복원 검증 범위만 주장한다. light는 분석용, full은 완료 episode
경계의 learner/replay/collector/RNG를 함께 보존한 재개용이다.

## 범위와 한계

평가는 과제당 16개 초기조건의 탐색 패널이며 표준 MT10/MT50 전체 평가가 아니다.
원래 평가와 달리 이번에는 정상 500-step 종료까지 성공 이후 행동도 기록한다.
다섯 seed와 64 물리 사례, 3,200 반복 에피소드를 독립 표본으로 혼동하지 않는다.
loss/Q/접촉/반복 동작은 기초동작이나 인과적 유용성을 입증하지 않는다.
후속 학습 개입·선택기·world model·추가 과제는 실행하지 않는다.

## 공식 참고

- https://metaworld.farama.org/evaluation/evaluation/
- https://github.com/Farama-Foundation/Metaworld/blob/main/metaworld/sawyer_xyz_env.py
- https://gymnasium.farama.org/main/api/vector/autoreset/
- https://mujoco.readthedocs.io/en/stable/programming/simulation.html
- https://proceedings.neurips.cc/paper_files/paper/2021/hash/f514cec81cb148559cf475e7426eed5e-Abstract.html

공개 main 문서는 참고이며 실행 source/XML은 input_receipt의 설치본 해시로 고정한다.
