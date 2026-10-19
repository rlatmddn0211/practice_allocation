# 미실행 후보 검증 — 2026-10-15 실행 범위

사용자의 미실행 요소 검증 요청에 따라 F02의 추가 예측 가치, F03의 실제 경험·상태 범위, F05의 동일 길이 목표 정합성과 rollout 가치 진단, F08의 강도·순서 대조를 진행한다. 이전 01–29의 구현과 결과는 보존한다.

| 독립 버전 | 수행 범위 |
| --- | --- |
| [30](../30_exposure_experience_screening_v1/) | 기존 192개 checkpoint·학습 로그로 F02 노출과 F03 경험 지표를 측정하고 원래 seed 제외 예측·선택 검증 |
| [31](../31_fixed_horizon_alignment_v1/) | 기존 모델을 새 D 사례에서 동일 500-step 평가; 성공률·return 정합성과 entropy·tail을 맞춘 제한 길이 rollout 가치 진단 |
| [32](../32_dose_order_intervention_v1/) | v23에 정의한 F08 72분기·2.88M 추가 학습, 20k마다 전체 checkpoint, 새 공통 평가 bank |
| 33 | 검증한 실행을 순서대로 처리하고 각 단계 분석·비용·실패 기록까지 저장하는 실행기 |

**2026-10-15 12:46:53 KST에 본 실행을 시작했다.** [활성 campaign](ACTIVE_CAMPAIGN.json)의 424개 작업을 순차 실행한다. 현재 진행과 완료 여부는 [STATUS](results/20261015T034631Z_remaining_0ce5f69e/STATUS.json) 및 해당 campaign의 `COMPLETE.json`으로 판단한다. 실행 시작이나 smoke 통과를 과학적 검증 완료로 표시하지 않는다.

②·③의 [완료 분석](../30_exposure_experience_screening_v1/report_ko.md)은 주 추가 선택 이득 0.000%p / −0.361%p로 둘 다 채택 보류다. [최신 후보별 기록](factor_status_ko.md)에 이전 판정과 남은 한계를 함께 남겼다.

본 실행은 새 bank 6개 생성 → ⑤ 192개 모델 진단 → ⑤ 분석·독립 검산 → ⑧ 부모 평가 → 72분기 학습·최종 평가 → ⑧ 분석·독립 검산 → 종합 보고서 순서다. ⑤는 10.752M 환경 step·학습 0, ⑧은 2.88M 추가 학습이며 평가를 합친 환경 비용 상한 18M step이다. ⑧의 학습은 20k 두 구간으로 나누어 총 144개 전체 checkpoint를 보존한다.

각 측정의 원시 trace 검사를 통과해야 다음 작업으로 넘어간다. 단계별 분석 결과도 독립 검산을 통과해야 완료로 표시한다. 원래 seed 제외 적합과 대조식의 [23개 계산 검사](results/20261015T034333Z_analysis_preflight_e1982847/summary.json), A/B/C 진단 검사 각 117개, F08 실제 학습·복원 검사 163개, [자동 실행기 7작업 검증](results/20261015T034333Z_technical_e8aa53da/summary.json)이 통과했다. 마지막 검증은 실제 1,000 학습 update·10,866 환경 step을 사용했으며 과학적 효과 분석에는 섞지 않는다.

각 단계는 본 실행 전에 소스와 입력 checkpoint manifest·설정·seed·분석식을 고정했다. [실행 계획](results/20261015T034631Z_remaining_0ce5f69e/plan.json), [선행 검사](results/20261015T034631Z_remaining_0ce5f69e/readiness.json), [기존 평가·학습 사례 출처](results/20261015T034631Z_remaining_0ce5f69e/historical_source_hashes.json), [시작 기록](results/20261015T034631Z_remaining_0ce5f69e/launches/20261015T034653Z_a3476472/launch.json)을 보존한다. 실행 중 stage source가 바뀌거나 무결성 검사에 실패하면 중단 기록을 남긴다. 효과가 나쁘다는 이유로 중단하거나 조건을 바꾸지 않는다.

실행기는 창을 띄우지 않는 별도 Python 프로세스다. 대화가 끝난 뒤에도 진행하며 controller 수명 동안만 자동 절전을 막는다. 최초 `.ps1` 직접 실행은 Windows 실행 정책에 막혀, 새 PowerShell 프로세스에만 `-ExecutionPolicy Bypass`를 적용해 시작했다. 시스템 실행 정책은 바꾸지 않았다. 전원 종료 후 재개는 다음 명령을 사용한다. 이미 실행 중이면 controller 잠금으로 중복 실행을 막으며, 완료한 작업·checkpoint는 덮어쓰지 않는다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\33_remaining_factor_queue_v1\launch_queue.ps1
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B .\33_remaining_factor_queue_v1\campaign.py status
```

일시적인 I/O 오류는 실패 시도를 남기고 최대 3회까지 회복한다. 무결성 실패나 회복 소진 시 `STOPPED.json`에 이유를 기록한다. 미완료 20k 구간은 새 시도로 다시 실행하며 이미 완료한 20k 이후는 해당 전체 checkpoint에서 이어간다. 재부팅 후 자동 시작하는 OS 작업은 등록하지 않았다.

전체 완료 시 campaign에 `report_ko.md`, `summary.json`, `COMPLETE.json`을 생성한다. ⑤·⑧ 각각의 분석 폴더에는 상세 보고서, 모든 사전 비교·개별 반복 결과·구간·비용이 남는다. worker 실패까지 포함한 환경 step·학습 update·wall·CPU 합을 기록하고, 초기 기술 검사·분석 CPU 비용과 구분한다. GPU busy time은 측정하지 않는다. 실행 자료는 C 드라이브의 각 버전 `results/`에 저장하며 과거 D 드라이브 자료는 읽기만 한다.

첫 본 측정은 56,000 환경 step·학습 update 0, worker wall 117.61초로 완료했고 원시 trace 검산을 통과한 뒤 다음 모델로 자동 진행했다. 시작·전달 점검의 실패와 회복은 [기술 이력](technical_failures_ko.md)에 기록했다.

공통 4k 전체 진단·새 사전학습 seed G3·온라인 동일 총예산 G4·별도 benchmark는 이번 실행 범위에 포함하지 않는다. F02의 sampling 개입은 예측 선별과 구분하며 자동 추가하지 않는다. F05 rollout 비교는 유한 길이·소수 반복의 추정 오차를 기록하고 정확한 무한-horizon 가치의 정답으로 부르지 않는다.
