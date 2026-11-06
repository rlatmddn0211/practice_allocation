# 85번 GitHub 공개 범위와 재현 안내

[원문 결과 보고서](results/20261106T042248Z_onset_campaign_24d98d21/analysis/20261106T111509Z_paired_3db89d3f/report_ko.md) · [핵심 그림](results/20261106T042248Z_onset_campaign_24d98d21/analysis/20261106T111509Z_paired_3db89d3f/figures/03_do_learning_curves.png) · [부모·미래별 대응표](results/20261106T042248Z_onset_campaign_24d98d21/analysis/20261106T111509Z_paired_3db89d3f/paired_effects_by_parent_future.csv) · [원 재현 ZIP](results/20261106T042248Z_onset_campaign_24d98d21/analysis/20261106T111509Z_paired_3db89d3f/reproduction_bundle.zip)

85는 원81의 다섯 실제1M full 학습기를 복원해 두 미래×세 조건을64k씩 계속한 새 파일럿이다. BASE/RANDOM_PRE/ONSET의 기존 네 과제 SAC를 비교했다. 81/82/84는 같은 원 관측 캠페인의 기록·사후분석이다. 이번 게시가84나 다른 미게시 실험을 추가 공개한 것은 아니다.

| 조건 | DO 정규화 AUC | 최종 DO 성공 |
|---|---:|---:|
| BASE |0.547%|1/160|
| RANDOM_PRE |3.125%|11/160|
| ONSET |1.875%|4/160|

ONSET−RANDOM_PRE는−1.250%p, 고정 저장소·개발 패널의 부모 bootstrap 분위 범위[-1.875,−0.547]이다. 부모 평균4개는 음수,1개는0이다. ONSET−BASE는+1.328%p[-0.469,+3.828]이고, 최종 ONSET 성공4건은 모두R04/F01이다. 명목 후속 신호 기준을 충족하지 않아 현재 onset 처치의 확대는 보류했다. BP 이득과 Push 손해도 원 보고서에 함께 제시했다. 일반적인 우위나 재사용 가능한 기초동작을 입증한 결과가 아니다.

초기 물리 X와 reset 반환 관측의 이전 X를 혼동한 측정 오류를 고쳤다. 원1M 정책/사례 +0의 DO5mm 진행은 raw 기준63/80에서 물리 x0 기준14/80으로 정정된다. 공식 성공0/80과 원 관측·옛 보고서는 그대로다. detector 문턱·창·SAC 입력을 바꾸지 않았고 branch 결과를 보기 전에 매핑을 수정했다.

## 공개한 자료

- 원문 보고서, 표·그림6개,6,080개 평가 라벨/에피소드 지표, 모든 부모·미래·조건의 결과와 고정 bootstrap draw.
- 실제 코드와 source snapshot, 설정·seed·원본 hash, 준비 실패/정정·기술 및 독립 검산·비용 원장.
- 결과와 무관하게 사전 고정한 최종 영상240개, 같은240에피소드의 NPZ·sidecar·frame/step 대응. [영상 목록](MEDIA_INDEX.csv).
- 초기 좌표 정정 검산을 위한 공통 +0 DO80개 원 수치 궤적.
- 적격25개와 제외6개를 포함한 원 DO 성공31개 원 수치 에피소드, 선정창과 cache. [원 경로↔공개 경로](SOURCE_EPISODE_MAP.jsonl).

원 보고서·코드·표·영상·NPZ·원 ZIP의 bytes는 유지했다. Windows 절대 경로는 출처이며 공개 다운로드 URL이 아니다. [공개 파일 경로·크기·SHA256](PUBLICATION_FILE_MAP.jsonl)이 원 경로를 연결한다. 이 게시 과정의 새 환경·정책·학습 실행은0이다.

## 로컬 보관 자료와 한계

모델/optimizer/replay checkpoint 본체, 전체 훈련 전이, 나머지 평가 원 전이, 상세 update/native replay 기록과 환경 snapshot 본체는 로컬 보관이다. [명시적 미게시 목록](LOCAL_ONLY_ARTIFACTS.jsonl)과 원본[해시 목록](results/20261106T042248Z_onset_campaign_24d98d21/analysis/20261106T111509Z_paired_3db89d3f/large_artifact_references.jsonl)을 따른다. 이 로컬 경로를 누구나 다운로드할 수 있다고 해석하지 않는다. 다섯 원1M full 상태도 준비 state_manifest에 hash가 있으나 본체는 GitHub에 없다.

공개 자료만으로 전체 평가 라벨의 AUC·대응 효과·저장 bootstrap,31개 source의 detector·window/cache와 공개320개 평가 원 궤적을 파일만으로 검산할 수 있다. 전체 SAC 학습 재개 및 원 분석 전체를 그대로 재실행하려면 로컬 대형 자료와 고정 runtime이 필요하다. 공개 소스를 원 flat 경로로 복구할 때는74/83/86 path manifest를 함께 사용한다. 원 코드의 절대/상대 경로를 임의로 새 경로와 같다고 가정하지 않는다.

저장소 루트에서 Python과 NumPy/pandas/Parquet 엔진을 사용해 다음 파일 전용 검산을 실행한다.

```text
python 07_operations_and_publication/86_onset_reuse_results_publication_v1/verify_public.py --repository .
```

새 환경 생성/reset/step, 모델 역직렬화/forward, 학습 및 새 bootstrap draw를 수행하지 않는다. 신규 본실험 비용은4,964,900전이(학습1.92M,평가3.04M,기술4,900)로4.97M 상한 이내다. 원81비용6,604,850은 별도로 보존한다.
