# 실행기 시작·전달 검사 이력

실험 코드·원자료의 실패와 실행 환경·상태 점검의 실패를 구분한다. 실패한 결과 폴더를 지우거나 완료 결과로 바꾸지 않는다.

1. `launch_queue.ps1` 직접 실행은 Windows의 기본 PowerShell 실행 정책에 거절됐다. 파일은 실행되지 않았고 학습·평가 비용은 0이었다. 별도 PowerShell 프로세스의 `-ExecutionPolicy Bypass`로 2026-10-15 12:46:53 KST에 시작했으며 시스템 실행 정책은 바꾸지 않았다. [성공한 시작 기록](results/20261015T034631Z_remaining_0ce5f69e/launches/20261015T034653Z_a3476472/launch.json)을 보존한다.
2. [최초 전달 검사](results/20261015T035102Z_verify_delivery_d9cbf792/summary.json)는 첫 본 측정의 완료 marker가 생기기 직전에 실행되어 `at least one full measurement and trace audit` 조건이 실패했다. 실제 실험 worker나 trace 검산의 실패는 아니며 controller는 계속 진행했다. 03:51:04 UTC에 첫 측정·검산 완료 marker를 확인한 뒤 같은 검사 코드로 새 출력 폴더에서 재검사했다. 검사 자체의 환경 step·학습 update는 0이다.

⑤의 초기 A/B 수치 합산 검사 실패 2회는 [v31 기록](../31_fixed_horizon_alignment_v1/technical_failures_ko.md)에 별도로 보존했다. 본 실험의 향후 실패는 각 시도의 `error.json`·`costs.json`과 campaign의 `events.jsonl`·`STOPPED.json`에 기록된다.
