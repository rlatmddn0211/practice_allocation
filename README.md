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

완료한 구현은 보존합니다. 각 단계는
목적이 드러나는 새 폴더에 독립된 코드와
설정으로 관리합니다. 기존 버전의 코드에 의존하도록 import하지 않습니다.

각 실행 결과는 해당 버전의 `results/<UTC시각>_<장치>_<고유ID>/`에 저장합니다.
기존 실행이나 checkpoint를 덮어쓰지 않으며 실패한 실행도 남깁니다.
코드·설정·검증 요약은 Git으로 관리하고, 가상환경·대용량 checkpoint와
실행별 소스 복사본은 로컬에 보존합니다.

사용자가 2026-10-07에 승인한 P0 사전학습은 같은 날 15:59:45 KST에 완료했습니다.
400k 공개 진단은 DO 5%, DC 100%, WO 40%, WC 100%로 과제당 20개 초기 상태에서
평가한 결과입니다. 사전 규칙에 따라 첫 분기점은 200k로 고정되었습니다.
첫 10분기는 별도 실행 단계이며 아직 실행하지 않았습니다. 해석과 제한사항은
[P0 상세 분석](03_p0_pretraining_analysis_v1/README.md)에 정리했습니다.
