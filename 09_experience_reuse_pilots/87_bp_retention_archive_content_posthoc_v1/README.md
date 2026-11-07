# 87. BP 보존과 DO 경험 내용·실제 사용의 사후분석

85번 완료 파일럿의 같은 기록을 분석한다. 새로운 독립 실험이 아니다.

- 실제 캠페인: `85_onset_reuse_pilot_v1/results/20261106T042248Z_onset_campaign_24d98d21`.
- 수치 추출: `results/20261106T124257Z_bp_content_posthoc_ab295693`.
- 독립 검산: 위 디렉터리의 `LATEST_VERIFICATION.json`.
- 최종 보고서·표·그림·ZIP: **[LATEST.json](LATEST.json)**에 기록된 delivery 경로.

수행 범위는 BP 160개 대응 이력과 부모·미래별 대비, 실제 BP 평가 1,520에피소드, 고정 DO 성공 25에피소드의 50개 창, 구간별 실제 최종 배치 사용량과 시간 순서를 지킨 효과 연결이다. 세 조건 모두와 반대·무변화 사례를 포함한다. 원 입력·코드·보고서는 보존한다.

새 환경 생성/reset/step/복원/렌더링, MuJoCo forward, 모델 로드/정책 forward, 학습 update, bootstrap draw는 모두 0이다. 네 과제의 손익, 고정 개발 패널, 중첩 LOO 및 상태–자료 구성의 얽힘을 보고한다. 특정 방법·기초동작·인과 설명을 확정하거나 후속 실험을 자동 예약하지 않는다.

재실행은 다음 순서다. 파일 처리에 기존 Python 환경을 사용하며 모델·물리 런타임을 import하지 않는다.

```powershell
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -X utf8 87_bp_retention_archive_content_posthoc_v1\analyze.py --stage core
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -X utf8 87_bp_retention_archive_content_posthoc_v1\verify.py --analysis <새 core 경로>
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -X utf8 87_bp_retention_archive_content_posthoc_v1\report.py --core <새 core 경로>
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -X utf8 87_bp_retention_archive_content_posthoc_v1\finalize_delivery.py --delivery <새 delivery 경로> --visual-review <실제로 확인한 PNG의 해시가 담긴 JSON>
```

각 실행은 고유 폴더와 실제 소스 snapshot/hash를 남긴다. 원본 대형 NPZ·영상·checkpoint는 재현 ZIP에 복사하지 않으며 입력 manifest의 경로·SHA256으로 연결한다. 이미지 검토는 기존 수치에서 만든 그림에 대한 것으로, 새로운 환경 렌더링이 아니다. 실패한 보고서 전달 시도와 이전 초안도 보존한다.

이번 요청은 기존 기록 분석의 실행 지시다. GitHub 게시나 새 학습의 실행 지시로 확대하지 않는다. 85의 원래 DO 진행 기준 미통과와 보류 판단은 유지한다.
