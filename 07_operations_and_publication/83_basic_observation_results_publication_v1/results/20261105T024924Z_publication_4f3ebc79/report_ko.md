# 81·82번 GitHub 공개 범위와 검증

게시 요청일: 2026-11-05. 학습·평가 완료일: 2026-11-03. 새 환경 전이·정책 forward는 0이다.

81의 다섯 실행과 3,200개 평가 및 82의 파일 분석을 게시한다. 모든 과제·실행·시점과 불리하거나 변화가 없는 결과를 포함한다. 75–80 등 다른 미게시 실험을 이 요청에 묶어 새로 공개하지 않는다.

## 게시한 자료

- 원문 한국어 보고서 2개, 집계 CSV/Parquet, 원 평가 라벨 3,200행, 학습 곡선·사례 이력 그림.
- 실제 실행 코드와 source snapshot, 고정 설정·seed·물리 평가 사례·schema, 기술·산술 검증 영수증.
- 사전 선정한 영상 400개, 동일 400에피소드의 원본 수치 NPZ와 sidecar, 영상별 frame/step 대응.
- 실행 완료·비용 기록과 original reproduction_bundle.zip 두 개.

## 로컬 보관 자료와 재현 범위

전체 훈련 전이, 나머지 평가 수치 궤적, model/optimizer/replay checkpoint 본체, 상세 업데이트·replay 사용 원장과 환경 snapshot 본체는 GitHub에 업로드하지 않았다. local_only_artifacts.jsonl의 availability와 해시 출처를 확인한다. 이 파일의 로컬 절대 경로는 공개 다운로드 URL이 아니다. 원문 artifact_hashes.jsonl은 원 분석 시점의 해시 기록이며 모든 보관 파일을 이번에 재검증했다는 뜻은 아니다.

이 공개본으로 원 평가 라벨·집계·사례 이력·공개 영상의 수치 궤적을 검산할 수 있다. 전체 학습의 재개 또는 원 분석 전체의 재실행에는 비공개 대형 원본과 원 runtime이 추가로 필요하다. 기존 Windows 절대 경로는 출처 기록으로 보존했으며 path_manifest_extension.json에서 게시 경로를 연결한다.

공개본 라벨 검산: 저장소 루트에서 Python으로 07_operations_and_publication/83_basic_observation_results_publication_v1/verify_results.py --repository . 를 실행한다. pandas와 Parquet 엔진이 필요하고 환경·모델을 실행하지 않는다.

## 검증

원문 보고서·ZIP 해시, 200개 평가 셀·3,200개 라벨·320개 사례 이력과 64개 고유 물리 사례, 모든 기존 게시 파일의 Git blob 보존, 새 공개 파일의 원본 SHA256, 영상·수치 대응 및 상대 링크를 검증한다. 이 검증은 게시 무결성 검증이며 새 과학적 실험이 아니다.

최종 성공률: DC 100%, BP 92.5%, DO 0%, Push 1.25%. 과제당 고정 16사례·5개 학습 실행에 조건화한 탐색 통계이며 신뢰구간을 산출하지 않았다. 기초동작·학습 개선·인과 원리를 확인했다는 결론을 추가하지 않는다.

기준 원격 커밋: 2208e99d4452288304d880a076cca5670b0eff96

[결과 목차](../../../../08_basic_learning_observations/README.md)
