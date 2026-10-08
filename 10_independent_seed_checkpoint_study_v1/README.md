# E1 · 독립 사전학습 seed와 출발 시점

2026-10-08 승인된 E1 구현이다. [08의 실험 조건](../08_followup_experiment_design_v1/protocol.json)을 유지한다.

- 과제 A: DrawerOpen, DrawerClose, WindowOpen, WindowClose.
- 원래 seed 11·12·13을 각각 균등 배분 400k 사전학습한다.
- 공개 진단은 0·100k·200k·400k, 100 episode/과제다.
- 각 seed의 200k와 400k에서 U·F_DO·F_DC·F_WO·F_WC를 continuation 2101·2102·2103으로 각각 +40k 학습한다.
- 총 90분기, 새 학습 4.80M step, 평가 79,200 episode. +20k는 보조 평가, +40k가 주 평가다.

주 대비 F_DC−U는 같은 원래 seed 안에서 checkpoint와 continuation에 동일 가중치를 주고, 마지막에 원래 seed 3개를 동일 가중 평균한다. 개별 과제의 절대 개선·악화도 남긴다. Failure/Progress는 공개 진단만으로 분기 전에 동결한다. 전역·시점별 Fixed는 원래 seed 전체를 제외하는 LOSO로, 분기 결과를 쓰는 교차 continuation 선택은 사후 진단으로 명시한다.

수치가 낮거나 높다는 이유로 조건을 삭제하거나 사전학습 예산을 바꾸지 않는다. E2는 이 단계의 200k 전체 상태를 읽기 전용으로 가져간다. 모든 상태는 20k마다 무손실 압축한 새 체크포인트로 저장한다. 중단되면 완료된 작업부터 이어가며 중단된 한 작업은 최대 20k를 다시 수행할 수 있다.

이 폴더는 독립 구현이다. 기존 SAC·환경·평가 코어는 버전 06과 동일하며, 다른 실험 폴더의 코드를 import하지 않는다. 자동 실행과 재시작은 [13](../13_e0_e3_autonomous_queue_v1/README.md)이 담당한다.
