# 58 — 확인 실험 실행 전 보완과 고정 예측 점검

기존 57번의 수치 설계와 예측은 보존하면서 주장 범위, G의 구조적 가능성, 수식·가중치, 과학적 근거와 투자 판단의 분리를 보완했다. **추가 학습·정책 평가·실행 예약은 없다.**

- [한 장 명세](one_page_spec_ko.md)
- [실제 점검 보고서](report_ko.md)
- [상세 통계 명세](statistical_spec_ko.md)
- [논문 주장 범위](paper_scope_ko.md)
- [프로토콜](protocol.json)
- [고정 예측 CSV](inputs/frozen_reference_predictions.csv)
- [제안 작업·seeds CSV](inputs/proposed_jobs.csv)
- [근거 원장](evidence_record_ko.md)
- [외부 검토용 ZIP](review_bundle.zip): 위 문서·예측·원자료·검산 코드·결과와 파일별 hash를 함께 포함한다. 현재 58번 검토는 묶음 안에서 가능하며 이전 연구 기록으로 향하는 링크는 전체 저장소에서 확인한다.

주 G의 추가 예측은 PU의49/548개 사례에 한정된다. 전체 G 상한0.004720527, 최소 부모 제외 상한0.001231243으로 수치 문턱이 처음부터 불가능하지는 않지만 검정력을 보장하지 않는다. 독립 검산은 원래 PAVA 구현을 호출하지 않고 유리수 min–max 등위 회귀와 직접 제곱오차를 사용했다.

## 재현

저장소 루트에서 실행한다. 모든 실행은 새 결과 폴더와 소스·입력 snapshot/hash를 남긴다. Python 표준 라이브러리만 필요하다.

```powershell
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 58_confirmation_prediction_preflight_v1\audit.py
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 58_confirmation_prediction_preflight_v1\verify.py 58_confirmation_prediction_preflight_v1\results\20261022T053745Z_audit_b4458b32
```

`amend_protocol.py`는 새58의 프로토콜·입력을 한 번 생성한 기록이다. 이미 파일이 있으면 중지하므로 다시 실행해 덮어쓰지 않는다. 이후 변경은 새 번호 버전에 둔다. 이 폴더에는 RL 실행기나 큐가 없다.

기록: [수정 생성](results/20261022T053744Z_amend_fe554a64/COMPLETE.json), [예측 점검](results/20261022T053745Z_audit_b4458b32/COMPLETE.json), [독립 검산](results/20261022T053915Z_verify_a759a328/COMPLETE.json). 과학적 결과 원본은 [56번](../56_same_vs_cross_state_overlap_v1/report_ko.md), 이전 설계는 [57번](../57_acquisition_state_dependence_confirmation_plan_v1/one_page_spec_ko.md)에 보존한다.
