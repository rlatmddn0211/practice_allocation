# 88. BP 보존·경험 내용 사후분석87의 GitHub 게시

2026-11-07 사용자가 완료된87번 결과의 게시를 요청했다. 같은85 자료의 사후분석이며 새 실험이 아니다.

- `09_experience_reuse_pilots/87_bp_retention_archive_content_posthoc_v1`: 원문 보고서, 표, 그림9개, 분석·검산 코드, 명세·hash·비용·근거 기록, 재현 ZIP.
- `07_operations_and_publication/88_bp_retention_posthoc_publication_v1`: 게시 코드와 검증 영수증.

최신 원격main을 부모로 하는 별도 Git 객체 저장소에서 준비한다. 로컬 runtime의 HEAD/index와 기존 README/AGENTS 변경은 유지하며 원격의 재배치 트리를 runtime에 pull하지 않는다. 기존 공개 자료는 탐색 문서4개를 제외하고 동일 Git blob을 유지한다. 원87 파일은 모두 byte 그대로 옮기고, 현재 게시 상태는 별도 공개 안내에 명시한다.

전체 BP raw1,520개·모델·replay를 새로 올리지 않는다. 원래 공개된DO 성공 원수치·85평가라벨·사용량과87파생표로 가능한 범위를 독립 검산한다. 입력별 공개 여부를 명시하고 전체 학습 재개 가능성과 구분한다.

```text
python 88_bp_retention_posthoc_publication_v1/publish.py prepare --base-commit <현재 원격main SHA>
```

검증된 commit만 fast-forward push하며 force push를 하지 않는다. 게시 후 원격main을 확인해 `record-push`로 실제 게시 commit을 기록한다. 새 환경·모델·학습·bootstrap 실행은0이다. 과학적 결론이나 원85의DO 보류 판단을 바꾸지 않는다.

현재 게시 상태·링크·commit은 `LATEST.json`을 따른다. 기존87 보고서에 적힌 ‘게시하지 않았다’는 분석 완료 당시의 기록으로 보존하고, 이 별도 게시 버전에서 후속 요청을 기록한다.
