# 실제 실행된 대기 큐의 확인

2026-10-27 20:27 KST. 새 환경 step0, 새 연구 SAC update0.

최종 정적검사55개 및 큐14개/보존8개 그룹 단위검사, 분석 자체검산을 통과한
source를 사용했다. 정적 검사 산출물은
`../20261027T112559Z_static_18f76b79`에 보존한다.

`launch_queue.py`는 venv python.exe의 시작 PID10252와 watcher가 광고하는
실제 interpreter PID23312가 같을 것으로 가정해10초 뒤 RuntimeError를 냈다.
이것은 기존 실행의 PID 확인 실패이며 watcher의 실패가 아니다. 원인에 대한
범위는 Windows venv 중간 실행기와 실제 Python의 서로 다른 PID로 제한한다.

다음 근거로 **이미 실행된 큐를 확인했으며 재실행하지 않았다.**

- `process.json`의 실제 시작 명령과 PID10252를 보존했다.
- `stdout.log`는 정확한 큐 경로와 실제 PID23312를 반환했다.
- ACTIVE_QUEUE.json도 같은 경로와 PID23312를 가리켰다.
- Get-Process에서 PID23312의 Python과20:26:25 KST 시작 시각을 확인했다.
- 큐 STATUS는11:26:25Z 이후11:26:55Z에 갱신됐고 waiting_upstream,
  reason="64 remains running"이었다.
- stderr.log는 비어 있었다. 원래 launch claim, 실패한 런처와 동결 source를
  보존하며, 실제 큐 source pin을 변경하거나 다른 watcher를 시작하지 않았다.

실제 큐는 `../20261027T112625Z_deferred_1357e818`이다.
정확한64번20분기·파일 분석·독립 검산을 확인하고, 알려진 CSV 정수 변환 오류가
발생한 경우에만67번의 고정된 파일 분석·검산 복구를1회 실행한다. 그 뒤66번의
기술검사를 통과해야 승인된40개 보존 개입 분기를 실행한다.

과학적 결과는 아직 미측정이며, 예약/단위검사/정적검사는 보존 효과의 근거가 아니다.
