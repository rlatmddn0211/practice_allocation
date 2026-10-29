# 64 — 같은 전체 학습 상태에서의 획득·상실·회복 기준선

2026-10-27 사용자는 기술 무결성 확인 후 20개 분기의 즉시 실행을 승인했다.
독립 구현은 59번 learner·환경을 복사하며 이전 버전 코드를 import하지 않는다.

부모41011–41015의 prefix4201 전체208k 상태(S)를 고정한다. 각 상태에서
32k를 UNIFORM(dose25) 또는 BP625(dose625)로 학습하고 미래 N1/N2를 짝짓는다.
원래200k 부모(P)는 출발 이력 비교점이다. 현재 단계는 다른 알고리즘이나 보존 개입의 효과 확인이 아니다.

전체 상태를212k·216k·224k·240k에서 보존한다. P/S/최종은 E50(과제당50),
중간세시점만 T20(과제당20, E50의 부분집합)로 평가한다. 기존 P/S는 실제 평가 출처·학습상태·bank·
물리 초기상태·평가/환경 코드가 일치할 때만 재사용한다. 성공시 최초성공 조기종료 계약 아래 length로
first-success step을 추론하며 실패는 미성공500-step censoring으로 기록한다.

입력 준비는 `prepare_inputs.py`가 모델/replay/환경 없이 수행한다. 매 실행은 새 결과 폴더에
실행소스·입력사본/hash·검사·의존성·0 환경비용을 남기며 기존 inputs를 덮어쓰지 않는다.
`inputs/state_manifest.json`, `inputs/jobs.json`, `inputs/evaluation_cases.json`,
`inputs/baseline_rows.csv` 및 부모별 case/episode 라벨 파일은 protocol에 hash로 고정한다.

보존된 과거 훈련episode 성공은 stochastic 수집정책의 이력이며, 현재S 정책 숙달이나 정확한
성공transition 라벨이 아니다. 실제 replay birth-step 조인은 기술 검증에서 별도로 확인해야 한다.

환경비용 총상한6.05M에는 학습640k, 새 평가최대4.4M, 필요시 P/S 재평가최대1M,
기술검사최대10k와 실패한 시도를 포함한다. 자동재시도는0이며 과학적 효과 방향으로 중단하지 않는다.
실행 완료·과학적 관측·후속 투자 판단은 [근거 원장](evidence_record_ko.md)에서 구분한다.
이전 보존개입 A/B/C/D, 새 부모, 원래C 및2/3단계는 이번 승인에 포함하지 않는다.
