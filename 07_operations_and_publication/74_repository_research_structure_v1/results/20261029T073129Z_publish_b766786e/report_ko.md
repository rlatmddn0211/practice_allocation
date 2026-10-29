# GitHub 연구 폴더 정리 결과

기존 게시된 번호 폴더66개를 연구 질문별 큰 폴더8개로 정리했다. 번호와 버전명은 하위 폴더에서 유지한다.
새 학습·환경 평가는0이며 로컬 체크포인트·replay·venv·미게시 실험을 옮기거나 추가 공개하지 않았다.

| 큰 폴더 | 기존 버전 수 |
|---|---:|
| 연구 개요·문헌 (`00_research_overview`) | 3 |
| 배분 효과의 재현 (`01_allocation_effects`) | 13 |
| 학습 단서·조건 (`02_learning_signals_and_conditions`) | 16 |
| 일정 선택의 가치 (`03_schedule_selection_value`) | 6 |
| 중단·지속의 가치 (`04_stop_continue_value`) | 8 |
| 획득 사례의 반복성 (`05_acquisition_repeatability`) | 5 |
| 보존 개입·사례 영상 (`06_retention_interventions`) | 5 |
| 실행·검증·공개 (`07_operations_and_publication`) | 10 |

원래 게시 파일31,290개를 전부 경로 대응표에 기록했다. 문서의 이동 관련 링크131곳을 보정했다. 학습 코드·원자료·JSON·미디어의 blob은 유지하고, 수정 전 문서도 원문 blob으로 보존한다.
루트 README에는 연구 질문별 지도와 기존 C/D 설명·비교 영상8개를 유지했다. 각 큰 폴더에는 해당 기록 목록을 추가했다.

기존부터 없던 문서 링크는 document_link_changes.json에 별도 표시한다. 이번 정리로 해결했다고 주장하지 않는다.
동결된 대화형 보고서의 JSON 안에 남아 있는 과거main 출처 링크는 보존했다. 도구README에서 해당 여섯 대상의 새 게시 경로를 안내한다.
검증은 파일·경로·Git blob·문서 링크에 대한 것이다. 학습 또는 환경 실행 재현 검증은 하지 않았다.

기준 커밋: `987ddb5d2744be5a09e395e5a9d26638b178940d`
검증 대상 tree: `3cc623f811809cea9f38587012492ef78ac491cb`
검증 기록: `results/20261029T073045Z_verify_structure_7184476d/verification.json`
경로 대응표: `results/20261029T073005Z_prepare_4b1e5fac/path_manifest.json`

로컬의 원래 checkout은 실행 자산의 절대 경로를 위해 평면 구조로 유지한다. 원격 게시 구조와 의도적으로 다르므로 이 checkout에서 일반 pull/merge로 덮어쓰지 않는다. 다음 게시 작업은 최신 원격main을 기준으로 해야 한다.
정리된 clone에서 기존 평면 구조가 필요하면 restore_legacy_layout.py를 새 빈 경로에 실행한다. 이 도구는 공개 파일과 원문만 복원하며 미게시 런타임·가상환경·환경 재현까지 보장하지 않는다.
