# DO 진행 시작 구간 재사용 파일럿 85

원81의 독립 R01–R05 1M full 상태와 다른 run의 DO 성공 훈련 자료를 사용하는
고정 30분기 파일럿이다. BASE / RANDOM_PRE / ONSET 각각 기존 네 과제 SAC를
64k 계속한다. 원 SAC batch의 DO slot만 확률0.25로 대체하며 BC 손실은 없다.

`ACTIVE_CAMPAIGN.json`과 그 campaign의 `status.json` / `RUNNING_STATUS.md`가
실제 진행 상태다. 실행 중인 셀이나 완료된 유효 셀을 새로 시작하지 않는다.
완료 후 보고서/재현 ZIP/효과값은 `LATEST.json`에서 찾는다.

준비 시 reset 반환 관측의 물체 X를 실제 reset 물리 위치와 혼동하는 문제를
찾았다. 기존16 평가+사전50 훈련 snapshot의 모델 위치·joint·고정 XML을 파일만으로
대조하여 실제 h0 매핑만 수정했다. 문턱/창/원 SAC 입력은 유지했고 수정 전 시도도
보존했다. 최종 적격25개, receiver별 LOO25/20/20/16/19개다.

기술4,900전이에서 다섯 부모 반복 복원, 원 sampler/대체율0, full 재개, P/U
난수 대응과 원 평가 일치/학습 격리를 통과했다. 정상 본실험4.96M, 기술/실패/재시도
공유10k, 신규 총상한4.97M이다. 추가 full을4k native block마다 저장한다.

런타임은 원 `13_e0_e3_autonomous_queue_v1/.venv/Scripts/python.exe`를 사용한다.
`baseline81/`은 원 run source snapshot의 정확한 복사본이며 이전 버전이 새 코드를
import하도록 변경하지 않았다. 본실험 중 root85 Python/명세와 이 복사본은 고정한다.

파일 전용 재분석:

```powershell
& '.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe' -X utf8 '85_onset_reuse_pilot_v1/analysis_tools/analyze.py' --campaign '<campaign>'
& '.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe' -X utf8 '85_onset_reuse_pilot_v1/analysis_tools/verify.py' --analysis '<new analysis>'
& '.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe' -X utf8 '85_onset_reuse_pilot_v1/analysis_tools/finalize.py' --analysis '<new analysis>'
```

자료 선택 규칙의 조건부 효용을 보는 파일럿이다. 독립 스킬, 행동 인과성,
모든 과제의 최적 구간, 저장소 수집 포함 종단 간 효율을 입증하는 설계가 아니다.
기존 개발 패널과 중첩 LOO 저장소의 한계를 유지하고, 부정·혼합·불확실 결과도 모두 보고한다.
