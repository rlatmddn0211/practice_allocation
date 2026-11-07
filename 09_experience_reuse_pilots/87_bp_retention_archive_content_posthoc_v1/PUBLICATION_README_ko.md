# 87번 사후분석 — GitHub 공개 안내

[원문 한국어 보고서](delivery/20261106T131228Z_delivery_95f094b9/report_ko.md) · [그림 9개와 표](delivery/20261106T131228Z_delivery_95f094b9/) · [재현 ZIP](delivery/20261106T131228Z_delivery_95f094b9/reproduction_bundle.zip) · [BP 부모·미래별 표](delivery/20261106T131228Z_delivery_95f094b9/tables/bp_ten_matched_runs_summary.csv)

87은 [85번 파일럿](../85_onset_reuse_pilot_v1/PUBLICATION_README_ko.md)의 **같은 기록에 대한 사후분석**이다. 독립 실험을 추가하지 않았다. 2026-11-07 사용자의 게시 지시에 따라88에서 공개했다. 원 보고서·README·FINAL_STATUS의 ‘이번 분석에서는 게시하지 않았다’는 문장은2026-11-06 분석 완료 당시 기록이며, 그 원문과 hash를 보존했다. 현재 게시 상태는 이 안내와88 게시 영수증을 따른다.

| BP 지표 | ONSET−RANDOM_PRE | ONSET−BASE |
| --- | ---: | ---: |
| 정규화 AUC 차이 | +7.578%p | +12.031%p |
| 양수 부모 | 3/5 | 4/5 |
| 양수 부모×미래 | 6/10 | 9/10 |
| 최종 성공 순차 | +11/160 | +40/160 |

P-U AUC는 각 부모 안 두 미래에서 방향이 같지만 R03/R04에서는 둘 다 불리했다. R05를 빼도 P-U+2.930%p,P-B+6.152%p다. P-U 최종+11은 초기 성공 유지+8과 초기 실패 최종 성공+3이다. P의 초기 실패12이력은11개가16k,1개가32k에 처음 성공했다. P/U 실제 사용은 각10,227,844회로 episode-offset별로도 정확히 같지만 내용은 달랐다.

자료 특성의 서열은 약한 사후 후보이고, 부모 상태와 중첩 LOO 자료 구성을 분리하지 못했다. 기존16개 개발 물리 사례,독립 부모5개,부모 안 미래2개다. 새로운 보존 방법·공유 기초동작·인과적 자료 기여를 입증한 결과가 아니다. 원85 DO 주지표의 보류 판단과 불리한 Push 결과를 유지한다.

## 공개 범위와 원본 보존

- 원 보고서·그림9개(PNG/SVG)·표·설정·분석/독립검산 코드·source snapshot·비용·근거 기록·원 재현 ZIP을 byte 그대로 공개했다.
- BP160개 대응 이력×3arm,1,520에피소드의 파생 물리 지표,고정DO25에피소드/50창,실제사용과90개 시간 일치 연결행을 공개했다.
- 원87 경로↔공개 경로와SHA256: [PUBLICATION_FILE_MAP.jsonl](PUBLICATION_FILE_MAP.jsonl). 원 입력의 공개 여부: [PUBLIC_INPUT_AVAILABILITY.jsonl](PUBLIC_INPUT_AVAILABILITY.jsonl).
- 대형 raw/model/replay를 새로 복제하지 않았다. BP 원시1,520개 중 기존 공개 경로가 확인된 것은 60개다. 전체 BP raw에 대한 검산은 로컬87에서 수행했으며,공개된 파생표가 전체 raw의 다운로드 가능성을 뜻하지 않는다. 원DO25개는 기존85의31개 source subset에 포함되어 다시 올리지 않았다.
- Windows 절대 경로는 당시 출처다. 공개 자료만으로 원 SAC 학습 재개나 로컬87 전체 raw 분석을 그대로 실행할 수 있다고 주장하지 않는다.

## 공개 파일만으로 가능한 검산

저장소 전체를 확보한 뒤 Python과NumPy/pandas/Parquet 엔진으로 다음을 실행한다.

```text
python 07_operations_and_publication/88_bp_retention_posthoc_publication_v1/verify_public.py --repository .
```

원85 공개 라벨에서480개 BP이력·30개대비·사건을 다시 계산하고,이미 공개한25개DO원수치에서창·개방/닫힘을 검산한다. 원85의실제사용count에서각시점노출량과가중내용·90개시간연결을 확인하고원ZIP해시를대조한다. 새 환경 생성/reset/step/복원,모델 로드/forward,학습 및 새bootstrap draw는0이다. 전체 BP raw1520개를 공개 검산했다고 표현하지 않는다.

원래 로컬 재분석 방법과 자산 요구는 [delivery/20261106T131228Z_delivery_95f094b9/REPRODUCE.md](delivery/20261106T131228Z_delivery_95f094b9/REPRODUCE.md)에 보존했다. 이번 게시의 Git 트리는 현재 원격main 위에 추가하며 기존runtime checkout의HEAD/index와원본실험은유지한다.
