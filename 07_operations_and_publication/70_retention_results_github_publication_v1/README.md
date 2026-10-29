# 68번 결과와 직접 근거의 GitHub 게시

2026-10-28 사용자의 요청에 따라68번 결과 보고서와 직접 근거64·66·67을 게시한다.
61·62·63·65·69와 과거52/59의 추가 콘솔 기록은 이번 게시 범위에 넣지 않는다.

- [68번 최종 해석 보고서](../../06_retention_interventions/68_retention_intervention_result_review_v1/results/20261028T072607Z_review_323af171/report_ko.md)
- [68번 근거 원장](../../06_retention_interventions/68_retention_intervention_result_review_v1/results/20261028T072607Z_review_323af171/evidence_record.json)
- [66번 보존 개입 원래 분석](../../06_retention_interventions/66_retention_intervention_queue_v1/results/20261028T014720Z_analysis_0918111d/report_ko.md)
- [66번 독립 검산](../../06_retention_interventions/66_retention_intervention_queue_v1/results/20261028T014738Z_verify_f207b31f/summary.json)
- [64번 기준선의 복구된 분석](../../06_retention_interventions/67_baseline_analysis_repair_v1/results/20261027T125938Z_analysis_9467d7b9/report_ko.md)
- [기준선 독립 검산](../../06_retention_interventions/67_baseline_analysis_repair_v1/results/20261027T130008Z_verify_e37dfa31/summary.json)

보고서·CSV·명세·실제 seeds·실행 소스·비용·완료 및 실패 기록·원래 재표집 NPZ 네 파일을 포함한다.
모델·replay·보존 sidecar·중복 source snapshot·대용량 원시 계측 JSONL은 로컬에 보관한다.
전체 학습 상태 백업이나 다른 컴퓨터에서 기존 검산 절차 전체의 즉시 재실행을 보장하는 게시가 아니다.
절대 원본 경로와 해시는 출처로 보존하며, 새 컴퓨터에서는 입력 경로 매핑이 필요하다.

기존 동결 구현과 보고서는 수정하지 않는다. Git의 줄바꿈 변환으로 실험 지문이 달라지지 않도록
해당 버전 경로에 -text를 적용하고, stage된 바이트를 원본 해시와 대조한다.
작업 폴더의 최신 README·AGENTS는 유지하고, index에는 현재 게시 범위의 내용만 반영한다.

이 게시에서는 학습·환경 평가·과학적 재분석을 수행하지 않는다. 각 준비·검증은 고유 결과
디렉터리와 실행 소스 사본/해시, 파일 명세를 남기며 실패한 기록도 유지한다.
