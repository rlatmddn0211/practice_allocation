# 연구 질문에 따른 GitHub 폴더 정리

2026-10-29 사용자가 게시된 폴더를 연구 주제 구체화 과정과 비슷한 질문끼리 묶도록 요청했다.
정리 전 공개 HEAD의66개 번호 폴더만8개 큰 그룹에 분류한다. 기존 번호·버전명은 하위에서 유지한다.
미게시 로컬 실험·체크포인트·venv를 함께 올리지 않는다.

로컬 실행 자산은 예전 절대 경로를 사용하므로 옮기지 않는다. 별도의 bare Git 저장소에서
공개 tree만 준비·검산하고 원격main을 fast-forward한다. 원래 작업 저장소의 HEAD/index와
로컬 README/AGENTS 변경은 보존한다. 이 원래 로컬 checkout에서 일반 pull로
구조를 덮어쓰지 말고, 이후 게시도 원격 공개 HEAD와 이 경로 대응표를 기준으로 해야 한다.

학습 코드·JSON 출처·원자료·미디어 blob은 동일하게 유지한다. Markdown의 유효 링크 중
이동 때문에 바뀌는 경로만 게시용으로 보정한다. 링크를 바꾼 문서의 원문 blob은
실행 기록의 original_files에 별도 보관하고 전후 blob과 경로를 기록한다.
기존부터 없던 보관 링크는 이동 오류와 구분해 공개한다. 루트 파일럿 설계는 수정하지 않는다.

`restore_legacy_layout.py --repository <정리된 clone> --output <새 빈 경로>`는
공개된 파일의 원래 평면 배치와 수정 전 문서 bytes를 복원한다. 누락된 로컬 모델·replay·venv나
다른 PC의 절대 경로 환경까지 복원하거나 학습 재현을 인증하는 도구는 아니다.
출력 경로가 이미 있으면 덮어쓰지 않는다. 환경 실행·학습은0이다.

일부 동결된 대화형 보고서의 JSON에는 과거 `main` 경로의 출처 링크가 남아 있다.
이 JSON의 원문은 보존한다. 해당 여섯 대상의 새 게시 위치는 다음과 같다.

- [04 최초 분기 평가 CSV](https://github.com/rlatmddn0211/practice_allocation/blob/main/01_allocation_effects/04_p0_allocation_branches_v1/results/20261007T091127Z_allocation_branches_cuda_64ec1ea7/run/evaluation_episodes.csv)
- [06 반복 분기 평가 CSV](https://github.com/rlatmddn0211/practice_allocation/blob/main/01_allocation_effects/06_p0_branch_replication_v1/results/20261008T030554Z_branch_replication_cuda_2c28c437/run/evaluation_episodes.csv)
- [19 연구 타당성 계획](https://github.com/rlatmddn0211/practice_allocation/blob/main/00_research_overview/19_budgeted_practice_research_feasibility_v1/research_plan_ko.md)
- [21 E3 결과](https://github.com/rlatmddn0211/practice_allocation/blob/main/01_allocation_effects/21_e3_completed_results_analysis_v1/report_ko.md)
- [36 후보 요인 검토](https://github.com/rlatmddn0211/practice_allocation/blob/main/02_learning_signals_and_conditions/36_all_candidate_evidence_review_v1/report_ko.md)
- [37 강도·순서 통합 해석](https://github.com/rlatmddn0211/practice_allocation/blob/main/02_learning_signals_and_conditions/37_f08_integrated_candidate_review_v1/report_ko.md)

새 탐색 문서의 링크 보정과 동결 JSON 안의 역사적 출처 경로 보존을 구분한다.
