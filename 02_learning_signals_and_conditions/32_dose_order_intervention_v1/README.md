# F08 연습 강도와 순서의 실제 학습 대조

[v23 개발 검증 설계](../23_candidate_factor_screening_design_v1/research_design_ko.md)의 F08 실험을 독립 구현했다. 기존 구현·출발 checkpoint는 보존한다. 2026-10-15 미실행 후보 검증 요청에 따라 [v33](../33_remaining_factor_queue_v1/README.md)이 F05 측정·검산 다음에 자동 실행한다.

**규모: 3개 task 구성 × 8개 조건 × 후속 seed 3개 = 72분기, 각 40k, 총 2.88M 추가 학습 step.** 각 구성의 기존 원래 seed 12·200k 전체 checkpoint에서 시작한다. 새 사전학습은 없다. 후속 seed는 3801/3802/3803이며 실제 RNG seed의 파생식을 프로토콜·요청 파일에 기록한다.

| 구성 | 과제 | 순서 대조 i / j |
| --- | --- | --- |
| A | DrawerOpen, DrawerClose, WindowOpen, WindowClose | DrawerOpen / DrawerClose |
| B | DrawerOpen, DrawerClose, Push, ButtonPress | ButtonPress / DrawerOpen |
| C | DrawerOpen, PickPlace, Push, ButtonPress | PickPlace / ButtonPress |

| 조건 | 실제 수집 규칙 |
| --- | --- |
| dose25 / dose4375 / dose625 / dose8125 | i 과제 비중 25 / 43.75 / 62.5 / 81.25%; 나머지 세 과제에 균등 배분 |
| i_then_j | 앞 20k는 i 집중, 뒤 20k는 j 집중 |
| j_then_i | 반대 순서 |
| alternate4k | i와 j 집중을 4k마다 교대 |
| mixture | 매 4k block에 i 3회, j 3회, 나머지 각 1회 |

학습 episode는 500 step이다. 순서 네 조건은 총 80 episode 중 i 30, j 30, 나머지 각 10회로 총 수집량을 맞춘다. 전환 시 optimizer·replay·RNG를 초기화하지 않는다. 강도 조건은 16-episode block을 고정 quota로 섞는다. 20k와 40k에 lossless replay를 포함한 전체 checkpoint를 새 폴더에 저장한다.

구성마다 과거 학습·평가 및 F05와 겹치지 않는 새 D20/O100 사례를 생성한다. 부모 D·O와 모든 최종 O를 평가한다. O는 task당 100개로 조건·반복에 공통이며 첫 성공 또는 500 step까지 실행한다. 초기 D 240회, 부모·최종 O 30,000회, **평가 포함 환경 비용 상한은 18M step**이다. 실제 step·wall·CPU·실패 비용은 따로 집계한다. GPU busy time은 계측하지 않는다.

강도 양 끝 차이, 중간 두 강도의 선형 보간 대비 차이, 정방향−역방향 및 각 순서−혼합의 사전 대조를 모두 보고한다. 평균만으로 좋은 조건을 고르지 않고 후속 반복 3개의 차이를 함께 남긴다. 사례 bootstrap은 고정 정책·고정 반복에 한정한다. **원래 seed는 구성당 한 개**이고 task 쌍도 이전 관찰을 참고해 선택했으므로 독립 확인이나 일반적인 순서 효과를 주장하지 않는다.

[프로토콜](protocol.json)에 설정·seed·대조·회복 규칙을 고정했다. 실제 모델의 기술 검사 [163개](results/20261015T030924Z_verify_implementation_5baa7378/summary.json)가 통과했다. 모든 quota·순서·저장 복원과 학습/평가 상태 보존을 확인했고, 이 검사에는 실제 학습 1,500 update·환경 2,629 step이 들었다. smoke는 효과 증거가 아니다.

`worker.py`가 학습·평가를 수행하고 `analyze.py`가 72분기 완료 후 전체 결과를 기록한다. `verify_analysis.py`가 144개 전체 checkpoint hash, 실제 episode quota·순서·사례 일치·대조와 구간을 검산한다. 효과 방향으로 분기를 중단하지 않는다. 기술 무결성 실패는 중단 기록을 남기며, 일시적 I/O 실패는 새 시도 폴더에서 최대 3회까지 회복한다.
