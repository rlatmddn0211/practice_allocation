# 기본 SAC 관측 캠페인의 실제 자산·설정 감사

2026-11-02. 실제 로컬 프로젝트와 기존 13번 Python/CUDA 환경에 접근했다.
검증된 기본 학습을 확인할 수 있었으며 다른 벤치마크나 가중치로 대체하지 않았다.
5개 학습은 새 초기화이며 과거 부모·S0/S1·성공 archive를 초기 학습 자료로 쓰지 않는다.

## 기본 학습 출처

- 77번에 보존된 core/environment/learning/engine/schedules를 새 81번에 그대로 복사했다.
- 네 과제 suite B는 DO/DC/PU/BP이며 PU는 Push다.
- 44번 worker의 fresh AuditEngine 초기화와 U 사전학습 경로를 대조했다.
  직접 확인한 추가 소스·해시는 verification/fresh_suite_B_source_supplement.json에 있다.
- 원래 루트 P0(02번)는 suite A의 400k 연구다. 이는 네트워크/초기화/기본 파라미터
  참고이며 이번 suite B의 과제 구성 출처로 혼동하지 않는다. 44번 suite B의 과거
  사전학습은 200k이고, 이번 1M은 사용자가 지정한 별도 운영 예산이다.
- U는 8개의 500-step 에피소드마다 과제별 두 개를 섞는다. 총길이에 따른 일정 변화가 없다.
  상수 학습률 0.0003, batch256, replay100000, warm-up1000, gamma0.99, tau0.005,
  자동 entropy와 전이당 하나의 SAC 업데이트를 유지한다.

## 실제 환경

Python3.12.0, torch2.5.1+cu121, gymnasium1.2.3, mujoco3.5.0,
metaworld3.0.0, stable-baselines3.2.7.1. NVIDIA RTX3070 8GiB.
실제 설치 경로는 input_receipt와 baseline_manifest에 있다. 설치된 Meta-World
배포본의 direct_url/VCS commit은 없으므로 소스/XML/모델 자산의 SHA256을 고정했다.
최신 main 문서는 참고로만 읽었고 설치본을 업그레이드하지 않았다.

실제 환경 키는 drawer-open-v3, drawer-close-v3, push-v3, button-press-v3이며
원래 adapter의 reward_function_version=v2를 유지한다. 실제 수집 환경은 wrapper나
autoreset 없는 새 TaskEpisode다. policy 입력은 원래 반환된 39D 관측을 float32로
변환한 값과 4D task one-hot, 행동은 정규화된 4D 값이다. 원래 환경 관측에는
Meta-World 자체 clipping이 포함되며, 정책 입력/float64 원시 반환 관측을 함께 저장한다.

실제 설치본 _get_obs가 _prev_obs를 변경함을 읽고 확인했다. 로거는 그 함수를
추가 호출하지 않고 reset/step의 반환 배열을 복사한다. 종료 관측은 직접 반환되며
다음 에피소드 reset 관측과 혼동하는 autoreset 경로가 없다. timeout bootstrap은
기본 SB3의 처리 그대로다.

## 명시적인 이번 운영 차이

기존 평가 adapter는 첫 성공 시 종료했으나 이번 사용자의 관측 규약은 정상 종료까지
계속 기록하는 것이다. 환경 자체는 성공으로 terminated를 반환하지 않으므로 원래
500 제어 step까지 기록한다. 성공 판정은 공식 원시 success의 any 집계이며 final은
별도 기록한다. 이는 처치/학습 변경이 아닌 이번 평가 관측 규약의 명시적 변경이다.

64개 초기조건은 정책 성공 라벨을 보기 전에 동결했다. 실제 물리 상태와 goal/관측
해시로 반복 재현했고, 공통 패널 manifest에 초기 상태·seed·snapshot을 연결했다.
표준 Meta-World 전체 goal 평가를 수행한 것이 아니다.

## 기술 검증과 복원 지위

verification/v_085050_3699ab/result.json에서 로깅 on/off의 실제 행동·관측·보상·종료,
학습 파라미터/optimizer/replay/RNG가 정확히 일치했다. full checkpoint의 100-step
재개와 light 정책 로드, 평가·영상 격리도 통과했다. 네 과제의 50-step 고정 행동열
snapshot 재현 및 DO의 25-step 고정 정책 재실행이 같은 runtime에서 정확히 일치했다.
다른 정책·상태·장비까지 보편적으로 완벽한 복원을 보장한 것은 아니다.
기술 비용은 4850 환경 전이이며 실패한 환경 실행은 없다. 합성 코드/보고서 검산은
환경 step0이고 과학적 효과의 증거가 아니다.

## 보조 기록과 접근 범위

68/71/77/79 보고서가 실제 존재함을 확인하고 읽었다. 초기 가까운 파일명 추측은
존재하지 않아 input_receipt가 추적한 실제 results 경로로 읽었다. 과거의 효과·부모
집중·First 해석을 새 관측의 과제/seed 선택이나 완료 기준으로 쓰지 않았다.

WMI 디스크 조회는 권한이 거부되어 사용하지 않았다. 허용된 파일시스템의 실제
disk_usage에서 약106GB 여유를 확인했고 기술 저장량과 현재 원본 크기로 점검했다.
정상 저장 예상 상한45GB이며 과거 자료 삭제나 별도 자원 증설을 하지 않는다.
AC 절전 설정은 이미 무기한이며 전원 계획을 변경하지 않았다.

## 실행과 분석 연결

81번은 학습·평가·원본 기록과 기본 분석을 수행한다. 82번은 81번이 끝난 후
그 원본만 읽는 탐색 해석이며 새로운 독립 실험이 아니다. 81번 동결 소스는
82번을 import하지 않는다. 새로운 환경 전이·모델/선택기 학습을 추가하지 않는다.
진행 상태는 RUNNING_STATUS.md/status.json, 실제 최종 결과는 FINAL_STATUS.json,
원 보고서는 LATEST_ANALYSIS.json으로 추적한다. 82번의 실제 보고서는 해당 LATEST.json이다.
