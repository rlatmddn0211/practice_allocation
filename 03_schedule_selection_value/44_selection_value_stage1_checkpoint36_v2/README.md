# 1단계 수정 실행: 36k 전체 상태와 부모 제외 재적합

[43번 피드백 반영 명세](../43_feedback_revised_selection_protocol_v1/research_protocol_ko.md)의 독립 구현이다. [42번](../42_fixed_schedule_selection_value_v1/README.md)의 코드·실행 자료는 보존한다. 이전 Python 구현을 import하지 않고 이 폴더로 복사했으며, 설치된 의존성만 기존 13번 `.venv`를 재사용한다. 복사 출처 hash는 `VERSION.json`에 기록한다.

과학적 학습 셀은 새 B 부모41011–41015 × 후속4201/4202 × BP/교대/혼합의30분기로 유지한다. 사전학습 포함2.2M 학습 step, 연구용 평가 포함 최대9.2M 환경 step이다. 이미 완료한 평가 bank와 첫 부모의120k 전체 상태를 hash 검증 후 인계하여 같은 과학적 학습을 반복하지 않는다.

2026-10-19 **15:47:41 KST**에 수정 campaign을 시작했다. 완료 자료12건(bank5·초기 상태1·사전학습 구간6)을 인계했고,
첫 부모의120k부터 사전학습을 정상 재개했다. 신규 잔여 과학적 학습은2.08M step이며 36k 저장 작업30건을 추가해 전체 작업 수는245개다.
[동결 계획](results/20261019T064658Z_stage1_2cbbdd65/plan.json),
[원본 인계 기록](results/20261019T064658Z_stage1_2cbbdd65/imported_jobs.json),
[실시간 상태](results/20261019T064658Z_stage1_2cbbdd65/STATUS.json)를 제공한다.

검증 결과는 [실제 SAC·부분 블록 복구 등69/69](results/20261019T063827Z_verify_41e7992c/summary.json),
[합성 CSV 분석20/20](results/20261019T063806Z_verify_analysis_1938808f/summary.json),
[원본 인계·hash·요청 일치287/287](results/20261019T064358Z_verify_handoff_2eb1e550/summary.json),
[자동 실행13/13작업](results/20261019T064215Z_technical_3a844643/COMPLETE.json)이다.
이번 수정의 기술 검사 비용은 [33,396 환경 step·14,000 SAC update](results/20261019T064658Z_stage1_2cbbdd65/readiness_evidence.json)로 별도 기록했다.
기존42번의 기술 검사 비용도 원래 기록에 보존하며 과학적 성능 근거로 합치지 않는다.

- 분기 전체 상태 저장을 **4k/8k/20k/36k/40k**로 변경한다. 중간 성능 평가는 추가하지 않는다.
- BP의 기존8k 블록과 교대/혼합 일정을 유지한다. 부분 블록 저장·종료 때문에 quota나 RNG를 재설정하지 않는다.
- 2%p 반복 우열은 전체 O100 macro로 명시하고, 다른 부모의 두 반복을 동일 가중한다.
- 부모를 완전히 제외한 뒤 교차 선택과 고정 기준 선정을 **다시 계산**한다. 기존 이득에서 하나만 빼는 방식은 보조 결과로 분리한다.
- 향후2단계용 점수 하나·26개 유한 후보·적합 목적·동점·조건부 LOPO를 `selection_rule.py`에 순수 계산으로 명시했다. 이 검증은2단계 학습이나 과학적 효과 검증이 아니다.

`campaign.py prepare --predecessor <42번 campaign>`은 완료 marker와, 이전 실행기 종료 후 worker가 완료한 작업까지 검증해 인계한다. 기존 plan/source/checkpoint/request/cost hash를 연결하고 새 campaign의 완료 기록이 원본을 가리킨다. 미완료·내용 변경·결과 평가가 이미 생성된 작업은 이 사전 결과 수정 절차로 임의 수입하지 않는다.

현재 학습 상태는 `ACTIVE_CAMPAIGN.json`이 가리키는 `STATUS.json`과 작업별 `progress.jsonl`에서 확인한다. 앞선 실행기 종료는 수정 인계를 위한 조치이며 학습 실패나 성능에 따른 중단이 아니다. 원래42번의 결과를 덮어쓰지 않는다.

2·3단계는 아직 실행하지 않는다. 2단계는 잔여28k와 두 행동의36k 결과로 개발하며, 3단계는 진단 없는 유지/전환·진단 선택·진단 후 항상 유지/전환의 다섯 방법을 비교한다. 이후 명세·과학적 진행 조건·기술 검증이 충족된 뒤 진행한다.
