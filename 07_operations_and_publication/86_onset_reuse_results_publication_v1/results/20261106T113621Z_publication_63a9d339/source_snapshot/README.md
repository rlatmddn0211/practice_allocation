# 85번 onset 경험 재사용 결과 게시

2026-11-06 사용자가 완료된85번 실험 결과의 GitHub 게시를 요청했다.
원격 최신 main과74/83의 게시 경로 규약을 기준으로 별도 Git 객체 저장소에서
준비한다. 기존 runtime checkout의 HEAD/index와 원본 결과는 유지한다.

- `09_experience_reuse_pilots/85_onset_reuse_pilot_v1`: 원 보고서·표·그림·코드·명세·검산과 재현 ZIP.
- 사전 고정 최종 영상240개와 같은 에피소드 수치 기록, 시작 DO80개 수치 기록.
- 원 DO 성공31개 수치 에피소드 및 선정창: detector와 선택 자료를 파일만으로 검산 가능.
- 모델·optimizer·replay 본체와 나머지 대형 원본은 로컬 보관·해시 참조로 구분한다.

84나 다른 미게시 실험을 함께 게시하지 않는다. 새 환경·모델·학습 실행은0이다.
`publish.py prepare --base-commit <remote SHA>`로 고유 준비 결과를 만들고,
검증한 commit만 원격 main에 fast-forward push한다. force push를 사용하지 않는다.
`verify_public.py --repository <repository>`는 공개된 라벨·AUC·저장 bootstrap
draw·detector·cache·일부 원 궤적을 파일만으로 검산한다. 새 bootstrap draw도 없다.

게시 상태와 원격 commit은 `LATEST.json`을 따른다.
