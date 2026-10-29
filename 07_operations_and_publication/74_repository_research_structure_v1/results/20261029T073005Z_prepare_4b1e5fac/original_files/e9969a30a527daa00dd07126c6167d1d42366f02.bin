# E3 · 과제 구성 변경

승인된 B와 C 조합을 모두 실행한다. A의 비교 자료는 E1의 200k 결과다.

| 조합 | 과제 순서 |
|---|---|
| B | DrawerOpen, DrawerClose, Push, ButtonPress |
| C | DrawerOpen, PickPlace, Push, ButtonPress |

각 조합에서 원래 seed 11·12·13을 각각 균등 200k 사전학습한다. 공개 진단은 0·100k·200k이며, 200k에서 U와 각 과제 집중 배분을 continuation 2301·2302·2303으로 각각 +40k 진행한다. B·C 합계 90분기, 학습 4.80M step, 평가 81,600 episode다.

관측 39차원+과제 one-hot 4차원, SAC 네트워크·업데이트·dense reward·평가 방식은 유지한다. 과제 바인딩은 작업 프로세스 시작 전에 고정하여 서로 다른 조합의 상태가 섞이지 않도록 한다. 체크포인트 로더가 과제 이름과 one-hot 순서를 확인한다.

조합 안의 U 대비 이득, 절대 gain, 과제별 변화, 동결된 Failure/Progress, 원래 seed를 제외한 Fixed 및 교차 continuation 진단을 보고한다. C에서 Fixed DC라는 이름으로 PickPlace를 대신하지 않는다. 결과가 불리한 조합이나 seed를 제거하지 않으며 200k를 사후에 늘리지 않는다. B−C를 의미적 유사성의 순수 인과효과나 공식 MT10 결과라고 부르지 않는다.

자체 소스·설정·검증·결과 폴더를 갖는 독립 구현이다. [13 자동 큐](../13_e0_e3_autonomous_queue_v1/README.md)가 E2 이후 B·C를 모두 실행한다.
