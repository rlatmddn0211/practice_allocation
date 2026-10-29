# 39–52번 연구 진행·결과 GitHub 공개 기록

2026-10-20 사용자의 “변경사항들 깃허브에 push” 요청에 따른 공개 범위다.
실험 소스·설계·완료된 결과·불리한 결과·기술 검산을 함께 보존한다.

| 범위 | 내용 |
| --- | --- |
| 39–40 | 후속 연구 설계와 외부 평가용 종합 보고서 |
| 41–44 | 세 단계 설계·피드백 개정·1단계 실행 코드 및 완료 기록 |
| 45 | 새 부모 5개·30분기 결과와 선택 가치 관문 미통과 |
| 46–47 | 경로 변동·손실 연구 설계와 기존 자료 A 분석 |
| 48–49 | 기존 BP 8k 정책 평가와 B의 손실·회복 분석 |
| 50 | 사후 선택 여지의 부모 집중도·과제 범위 보조 분석 |
| 51 | 동일 8k 상태 미래 반복 명세와 사전에 고정한 선택표 |
| 52 | 승인된 새 미래 10개 실행 코드, 기술 검증 및 실행 시작 기록 |

완료 결과는 [45번](../../03_schedule_selection_value/45_stage1_selection_value_analysis_v1/report_ko.md),
[47번](../../04_stop_continue_value/47_existing_data_path_loss_analysis_v1/report_ko.md),
[49번](../../04_stop_continue_value/49_bp8k_late_value_analysis_v1/report_ko.md),
[50번](../../04_stop_continue_value/50_b_posthoc_concentration_review_v1/report_ko.md)을 참조한다.
52번의 새 과학적 결과는 이 공개 시점에 완료된 것으로 표시하지 않는다.
현재 학습은 그대로 계속하며, [상태 스냅샷](campaign52_snapshot.json)에 조회 시점의 상태를 보존했다.
이 스냅샷은 실시간 상태판이 아니다.

기존 `.gitignore`의 모델·replay·NPZ·소스 중복 사본·캐시 제외 규칙을 유지한다.
40번의 임시 브라우저 profile과 앱 내부 중복 offline export도 로컬에 보존한다.
일반 Git에는 코드, 보고서, 사례별 CSV, JSON 설정·검산·비용 기록, 그림 및 보고서 읽기 파일을 게시한다.
진행 중인 52번 본 실험의 `jobs/`와 실시간 실행기 stdout/stderr는 이번 stage 대상에서 제외한다.
새 분기의 최종 결과는 완료된 뒤 별도 공개해야 한다.

이 공개는 모든 checkpoint를 포함하는 전체 실행 환경 백업이 아니다.
과거 원자료에 남은 절대 경로와 hash는 수정하지 않는다.
다른 컴퓨터에서 전체 학습을 재실행하려면 경로 매핑과 로컬 보관 모델·replay가 필요하다.
각 동결 버전의 파일은 줄바꿈 변환 없이 Git에 저장해 기록된 SHA-256을 보존한다.

공개 검사는 `verify_publication.py`가 새 `results/` 폴더에 코드 사본·hash,
staged 파일 목록·bytes·SHA-256, 문서 링크 범위 및 실제 비용을 기록한다.
새 SAC 학습·환경 평가를 실행하는 검사가 아니다.
[검산 결과와 보관 범위의 제한](technical_notes_ko.md)을 함께 제공한다.
