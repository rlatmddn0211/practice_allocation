# 준비 결과

| donor_run | successful_episodes | eligible_episodes |
| --- | --- | --- |
| R01 | 2 | 0 |
| R02 | 5 | 5 |
| R03 | 6 | 5 |
| R04 | 9 | 9 |
| R05 | 9 | 6 |

| parent_id | raw_LOO_successes | eligible_episodes | minimum_required | episode_shortfall | donor_runs_with_at_least_two | donor_requirement | same_episode_P_U | all_windows_identical | transitions_per_arm | mean_P_U_overlap_fraction | archive_support_ready | full_payload_hashes_verified | runtime_full_and_case_restore_certified | ready_for_runtime_checks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R01 | 29 | 25 | 8 | 0 | 4 | 2 | True | False | 800 | 0.214 | True | True | False | True |
| R02 | 26 | 20 | 8 | 0 | 3 | 2 | True | False | 640 | 0.217 | True | True | False | True |
| R03 | 25 | 20 | 8 | 0 | 3 | 2 | True | False | 640 | 0.214 | True | True | False | True |
| R04 | 22 | 16 | 8 | 0 | 3 | 2 | True | False | 512 | 0.168 | True | True | False | True |
| R05 | 22 | 19 | 8 | 0 | 3 | 2 | True | False | 608 | 0.248 | True | True | False | True |

초기 물리 좌표 매핑 수정 후 모든 receiver 자료 기준 통과. 원31성공→적격25. 기술4,900전이 통과. 수정 전 출력도 보존. 본문2절과 input manifest 참조.
