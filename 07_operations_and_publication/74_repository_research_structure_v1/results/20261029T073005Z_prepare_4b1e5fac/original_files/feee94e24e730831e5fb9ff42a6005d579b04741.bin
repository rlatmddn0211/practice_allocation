# E2 · 목표 과제 수집량을 고정한 donor 교환

E1의 원래 seed 11·12·13, 200k 전체 상태에서 시작한다. 새 continuation 표지 2201·2202·2203을 사용하며 배분끼리 같은 context의 난수 입력을 짝짓는다.

| 조건 | DO | DC | WO | WC |
|---|---:|---:|---:|---:|
| U | 2 | 2 | 2 | 2 |
| DC_plus_WO_minus | 2 | 3 | 1 | 2 |
| DC_minus_WO_plus | 2 | 1 | 3 | 2 |

표는 8 episode 블록당 개수다. 모든 조건에서 DO와 WC는 각각 +40k 중 10k다. 3 부모 × 3 조건 × 3 continuation = 27분기, 총 1.08M 학습 step과 22,800 평가 episode다.

주 대비는 +40k의 DO 성공률에서 DC 증가−WO 증가다. U 대비 차이, 시작 대비 gain, macro, 최악 과제, 최대 하락도 함께 기록한다. 이는 DC/WO 자원 교환 효과이며 독립적인 직접 전이 효과로 해석하지 않는다. DO 수집 개수가 같아도 정책 변화에 따라 방문 상태는 달라질 수 있다.

전체 learner·optimizer·entropy·replay·collector·RNG를 검증하여 가져오며 warm-up을 반복하지 않는다. `run_job.py`는 과제별 실제 수집량을 확인한다. 연구 코드는 이 폴더 안에 독립적으로 있고, [13 자동 큐](../13_e0_e3_autonomous_queue_v1/README.md)가 E1 완료 후 실행한다.
