# README 영상 공개 기록

사용자 요청에 따라 C/D 조건 설명과 BP/DC의 양방향 사례4쌍을 공개한다. 새 환경·정책·MuJoCo·학습·재표집은0이다.
MP4는 기존 고정 카메라 보조영상의 바이트 동일 사본이며 원래 rollout 중 영상은 그대로 로컬에 보존했다.
GIF는 압축한 미리보기다. 비교 쌍의 긴 구간에 맞춰 표시하되 짧은 정책의 관찰 종료 뒤는 실제 마지막 frame을 흐리게 하고 미측정으로 표시한다.
끝에1초를 더 보여주는 것은 표시용 hold이며 추가 학습·평가 시간이 아니다. 원래 step과 성공 판정은 수정하지 않았다.

| 과제 | 부모 | 미래 | 사례 | C 성공/step | D 성공/step |
|---|---:|---:|---:|---|---|
| BP | 41014 | N1 | 64 | 0/500 | 1/40 |
| BP | 41011 | N1 | 7 | 1/38 | 0/500 |
| DC | 41013 | N1 | 24 | 0/500 | 1/16 |
| DC | 41011 | N1 | 17 | 1/16 | 0/500 |

cases.json은원MP4/episode/result와배포사본의SHA256을보존한다. inputs의episode/result는동일사본이다.
original local source paths in those records refer to retained research assets; publishing these examples is not a full checkpoint/data backup.

이번게시에는69/71/72전체파일,체크포인트,추가연구실행을포함하지않는다. 원래66/68자료와결론은유지한다.
