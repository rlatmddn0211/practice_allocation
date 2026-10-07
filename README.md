# Robot practice allocation

사전학습된 공유 정책에 제한된 추가 연습을 배분할 때, 현재의 실패율과
추가 학습의 가치가 일치하는지

설계 기준: [로컬 파일럿 설계 v0.1](LOCAL_PRACTICE_ALLOCATION_PILOT_DESIGN_20261007.md).

## 독립 버전

| 폴더 | 목적 | 실행 범위 |
| --- | --- | --- |
| [01_implementation_validation_v1](01_implementation_validation_v1/README.md) | 최초 구현과 재현성 검증 | CPU·CUDA 각각 10/10 검사 통과, P0 미실행 |
| [02_p0_uniform_pretraining_v1](02_p0_uniform_pretraining_v1/README.md) | P0 균등 사전학습 | seed 901·CUDA·400k, 독립 검증 후 실행 |

완료한 구현은 보존합니다. 각 단계는
목적이 드러나는 새 폴더에 독립된 코드와
설정으로 관리합니다. 기존 버전의 코드에 의존하도록 import하지 않습니다.

각 실행 결과는 해당 버전의 `results/<UTC시각>_<장치>_<고유ID>/`에 저장합니다.
기존 실행이나 checkpoint를 덮어쓰지 않으며 실패한 실행도 남깁니다.
코드·설정·검증 요약은 Git으로 관리하고, 가상환경·대용량 checkpoint와
실행별 소스 복사본은 로컬에 보존합니다.

사용자가 2026-10-07에 P0 사전학습 실행을 승인했습니다. P0 실행기는
현재 버전의 사전검증 및 실행기 검증을 확인합니다. 첫 10분기는 별도 실행 단계입니다.
