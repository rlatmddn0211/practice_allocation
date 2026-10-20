# 1단계: 강한 고정 일정과 부모별 선택 가치

[41번 세 단계 명세](../41_selection_value_three_stage_protocol_v1/research_protocol_ko.md)의 첫 단계 구현이다. 이전 구현은 보존하고 32번의 SAC·환경·checkpoint 코드를 이 폴더로 복사했다. 이전 버전의 Python 코드를 import하지 않으며, 설치된 의존성 환경만 13번 `.venv`를 재사용한다. 복사 출처·hash는 `VERSION.json`에 기록한다.

새 B 부모 41011–41015, 각 Uniform 200k. 후속 라벨 4201/4202마다 BP 집중·4k 교대·혼합을 각각 +40k 학습한다. 30분기, 2.2M 학습 step, 연구용 평가 포함 최대 9.2M 환경 step. 기술 검사는 별도 계상하며 과학적 근거가 아니다.

2026-10-19 **14:50:44 KST에 본 campaign을 시작했다.** 새 평가 사례 생성부터 순차 실행한다.
[동결 실행 계획](results/20261019T055015Z_stage1_c82b28ef/plan.json)과
[실시간 상태](results/20261019T055015Z_stage1_c82b28ef/STATUS.json)를 확인할 수 있다.

- [실제 SAC 복구·상태 보존 검사](results/20261019T054326Z_verify_ae5e8575/summary.json): 51/51 통과.
- [합성 CSV 분석 계약 검사](results/20261019T054704Z_verify_analysis_7f7f5c92/summary.json): 11/11 통과, 환경 실행 0.
- [자동 실행 흐름 검증](results/20261019T054526Z_technical_2e59086f/COMPLETE.json): 13/13 작업 완료.
- [검증 근거·실제 비용](results/20261019T055015Z_stage1_c82b28ef/readiness_evidence.json): 기술 검사 총 30,236 환경 step, SAC update 10,500회. 본 실험의 성능 결과로 사용하지 않는다.

첫 시작 명령은 Windows PowerShell 실행 정책으로 거부되어 학습 없이 종료됐다. 해당 [실패 기록](results/20261019T055015Z_stage1_c82b28ef/launches/blocked_d5eab8c5/failure.json)을 보존했다. 승인된 이번 실행 프로세스에만 정책 예외를 적용하여 백그라운드 시작에 성공했으며, 시스템 실행 정책은 변경하지 않았다.

사전학습 20k마다, 분기 4k/8k/20k/40k에서 무손실 전체 checkpoint를 보존한다. 각 작업은 새 attempt 폴더에서 실행하고 코드 snapshot·hash·runtime·실제 비용을 저장한다. 중단 시 이미 완료한 작업은 재실행하지 않으며, 미완료 작업만 새 attempt에서 최대 3회 복구한다. 무결성 실패는 자동 중지한다.

주 분석은 BP 대비 두 대안과, 후속 반복·평가 사례를 분리한 부모별 선택 가치다. 교대−혼합의 평균 우위만으로 적응형 연구 통과를 판정하지 않는다. 독립 단위는 부모 5개다. `analyze.py`는 모든 과학적 셀 완료 후 자동 실행되어 원시 평가 행에서 재계산하고 진행 조건을 기록한다.

2단계의 공통 8k 유지·전환과 3단계 비용 포함 비교는 이 실행기에 자동으로 포함하지 않는다. 첫 단계 결과가 나온 뒤 해당 단계의 실행 명세와 규칙을 동결하고 기술 검증을 거쳐 진행한다.

실행 상태는 `ACTIVE_CAMPAIGN.json`이 가리키는 campaign의 `STATUS.json`, 작업별 `progress.jsonl`과 `costs.json`으로 확인한다. 전원 중단 이후에는 `launch_queue.ps1`로 동일 campaign을 이어갈 수 있다. 재부팅 자동 시작 작업은 설치하지 않는다.
