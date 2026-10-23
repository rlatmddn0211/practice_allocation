# 57 — 획득 패턴의 출발 상태 의존성: 독립 확인 계획

2026-10-22 사용자가 제안한 논문 방향을 **실행 전 설계와 참조 예측 준비**로 구체화했다. **새 학습·환경 평가0step, 실행 예약 없음.** 최신 완료 과학적 분석은 [56번](../56_same_vs_cross_state_overlap_v1/report_ko.md)이며,57번은 새 실험 결과가 아니다.

먼저 읽을 문서: **[한 장 명세](one_page_spec_ko.md)**.

- [수식·모형·평가·투자 기준](statistical_spec_ko.md)
- [논문 범위·문헌 경계](paper_scope_ko.md)
- [기계 판독 프로토콜](protocol.json)
- [준비 상태와 한계를 분리한 근거 기록](evidence_record_ko.md)

## 제안한 첫 묶음

기존10개8k 상태 × 새 미래2개 ×32k = **학습640k**. 최종20정책을 O100×4과제로 평가하여 **평가상한4M**, 본 환경 상한 **4.64M**. 별도 기술10k를 포함한 제안 상한은 **4.65Mstep**이다. 사전학습·prefix를 다시 만들지 않는다.

새 미래F3/F4만으로 동일−교차D를 계산한다. 참조F1/F2는 공통 사례 등급·상태별 단조반응 M0와 추가 사례 반응 M1의 예측을 만드는 데만 사용한다. DC·PU가 주 관심 범위이며 D의 분모는 기존4과제2,000슬롯을 유지한다. 설명 비교는 새 미래의 Brier 오차 하나로 판정한다.

제안 투자 문턱은 D≥0.10%p, Brier오차감소G≥0.001에 조건부 사례구간·부모 제외·두 새 미래별 양의G를 함께 요구한다. **검정력 보장이나 사용자 승인값은 아니며** 승인 전 수정은 새 결과를 보기 전에 근거와 함께 버전으로 남긴다. 새 부모 수는 아직 정하지 않았다.

## 준비 결과와 주의할 점

| 항목 | 준비 상태 |
|---|---|
| 공통 실패 사례 | 전체4과제1,247개; 주DC·PU548개 |
| 고정 예측행 | 전체2,494행; 주1,096행(사례×2상태) |
| 두 모형 예측이 다른 주 사례 | **49/548개**, 부모41011·41013·41015에 있음 |
| 기존 상태·신규seed 제안 | 20개 future root 모두 다르고 기존20개 root와 충돌 없음 |
| 원본 체크포인트·bank |10개 manifest 및 bank hash 확인; 모델 학습 실행 아님 |
| 독립 검산 |13,873개 검사 통과; 모든 예측을 유리수·단조 블록 전수열거로 재계산 |
| 새 과학적 결과 | 없음. 새 미래F3/F4는 생성하지 않았음 |

M0와M1이 같으면 해당 사례에서 설명 비교의 정보가 없다. 주분모548을49로 바꿔 이득을 크게 보이게 하지 않는다. 임의의 유리한 이진 결과까지 허용한 G의 대수적 상한은0.004721이며, **예상 성능·검정력·달성 가능한 연구 효과가 아니다**. 이 점검은 문턱이 계산상 불가능한지 확인한 것뿐이다.

## 보존된 실행

| 작업 | 기록 |
|---|---|
| 구문 확인 | [20261022T044937Z_syntax_07397dea](results/20261022T044937Z_syntax_07397dea/COMPLETE.json) |
| 참조 준비 | [20261022T044948Z_prepare_2b1bf98a](results/20261022T044948Z_prepare_2b1bf98a/receipt.json) |
| 독립 검산 | [20261022T045157Z_verify_e5355f1d](results/20261022T045157Z_verify_e5355f1d/COMPLETE.json) |

[고정 참조 예측 CSV](results/20261022T044948Z_prepare_2b1bf98a/frozen_reference_predictions.csv) · [제안 작업·seeds](results/20261022T044948Z_prepare_2b1bf98a/proposed_jobs.csv) · [적격 범위](results/20261022T044948Z_prepare_2b1bf98a/coverage.csv) · [모형 차이 지원 범위](results/20261022T044948Z_prepare_2b1bf98a/prediction_feasibility.csv)

예측 SHA256: `e0c34c7c0b010b767e51de6e6ea6d546e7f41d738511117238deabb803f35cc8`.
프로토콜 SHA256: `c6508598d1145905d09ac3fc696d674be62085724b6853d25f61f5d456722739`.

## 재현과 후속 실행 경계

저장소 루트에서 아래 명령은 **참조 파일 계산만** 수행한다. 매번 새 디렉터리에 source/input snapshot, hashes, runtime, 실패 기록을 남긴다. Python3.12.0·NumPy2.2.4로 준비했다.

```powershell
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 57_acquisition_state_dependence_confirmation_plan_v1\prepare.py
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 57_acquisition_state_dependence_confirmation_plan_v1\verify.py 57_acquisition_state_dependence_confirmation_plan_v1\results\20261022T044948Z_prepare_2b1bf98a
```

이 폴더에는 RL worker·실험 큐·자동 실행 스케줄러를 만들지 않았다. 실행을 별도로 승인받으면 다음 독립 번호에서 학습 구현과 전체 상태·RNG 기술 검증을 완료해야 한다.20개 본분기는 효과 방향과 관계없이 모두 실행하되 기술 무결성 실패·예산소진 시 중단한다. 재시도·새 부모·새 규칙을 자동 추가하지 않는다.

57번 전달 뒤 구현이나 명세 수정은 새 버전으로 기록한다. 이전45·54번 선택기 관문 미통과와 C·원래2/3단계 보류는 유지한다.
