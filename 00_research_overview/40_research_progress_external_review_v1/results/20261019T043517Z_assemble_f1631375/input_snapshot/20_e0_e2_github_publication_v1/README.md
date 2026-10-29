# E0–E2 results publication

E0–E2 완료 결과와 재현에 필요한 원자료를 보관합니다. 학습 코드를 수정하거나 새 학습을 실행하지 않는 독립 출판 버전입니다.

2026-10-14 11:27 KST에 Release 공개를 완료했습니다. ZIP 5개, manifest, checksum 목록의 총 7개 asset 모두 GitHub 서버의 SHA-256과 크기가 로컬 원본과 일치합니다. 태그의 2026-10-13은 자료를 정리한 날짜이며 실제 게시 시각은 [게시 영수증](results/20261014T022410Z_github_publication_c84a33df/publication_receipt.json)에 기록했습니다.

- [GitHub Release](https://github.com/rlatmddn0211/practice_allocation/releases/tag/e0-e2-results-2026-10-13-v1)
- [원본·압축파일 SHA-256 manifest](results/20261013T105002Z_archive_d19752fc/archive_manifest.json)
- [검증 기록](results/20261013T105002Z_archive_d19752fc/verification.json)
- [전체 평가 112,800 episode CSV](results/20261013T105002Z_archive_d19752fc/portable_data/evaluation_episodes.csv)
- [완료 작업 592개 결과 JSON](results/20261013T105002Z_archive_d19752fc/portable_data/completed_results.json)
- [완료 작업별 실제 비용](results/20261013T105002Z_archive_d19752fc/portable_data/completed_job_costs.json)
- [E0–E2 상세 분석](../17_e0_e2_detailed_research_report_v1/README.md)
- [후속 연구의 가설과 예비 검증](../19_budgeted_practice_research_feasibility_v1/README.md)

## 보관 범위

| 파일 | 내용 |
| --- | --- |
| E0.zip | D 드라이브 09 단계의 전체 파일 |
| E1.zip | D 드라이브 10 단계의 전체 파일 |
| E2.zip | D 드라이브 11 단계의 전체 파일 |
| E0_parent_checkpoints.zip | E0가 평가한 기존 26개 전체 checkpoint와 원래 평가 bank |
| queue_provenance.zip | 동결 계획·실행 소스·E0–E2 완료 marker와 시도 이력 |

모델, optimizer, replay, collector와 RNG, 의존성 버전, 실행 소스 사본, 실패한 기술 검증/시도도 원본 그대로 포함합니다. 총 18,123개 파일, 참조된 전체 checkpoint 323개를 보관합니다. 중간 checkpoint도 포함한 수이며 독립 실행 수가 아닙니다. Python 캐시·가상환경·실행 lock과 진행 중인 E3 결과는 제외합니다. E0 부모 외에 참조하지 않은 과거 01–06의 모든 checkpoint를 다시 보관하는 범위는 아닙니다.

E0–E2에서 완료한 학습은 5.88M step, 평가는 112,800 episode입니다. 완료 작업의 wall time 합계는 약 42.27시간이며 대기 시간이나 중단된 시도의 전체 벽시계 시간을 뜻하지 않습니다. 재분석·자료 압축은 새 RL 실험으로 세지 않습니다.

## 복원과 검증

다섯 ZIP을 같은 새 디렉터리에 풉니다. `runs/`는 원래 D 드라이브의 `robot_practice_allocation_runs/`, `workspace/`는 원래 저장소 루트에 대응합니다. 원본 JSON의 절대 경로는 증거의 bytes와 hash를 보존하기 위해 수정하지 않았습니다. 다른 PC에서 분석할 때에는 manifest의 `path_mapping`과 각 파일의 `original_path` → `path` 대응을 사용합니다. 기존 스크립트가 요구하는 경로를 그대로 쓸 수 없다면 데이터를 이 대응으로 읽어야 하며, 원본 파일을 덮어써서 경로를 바꾸지 마십시오.

`portable_data/evaluation_episodes.csv`는 원래 episode 행에 job/stage/seed/배분 정보를 붙인 분석용 export입니다. 성공 횟수와 실제 step 합계를 각 원본 결과에 다시 대조했습니다. 16–19번 폴더의 CSV는 바로 읽을 수 있는 집계 결과입니다. 원본 코드의 전체 재실행은 기록된 dependency와 환경 경로를 복원해야 하므로 CSV 열람과 구분합니다.

빌더는 매번 새 `results/`에 기록합니다. 모든 압축 항목을 원본 SHA-256과 대조하고 checkpoint manifest의 파일 hash도 확인했습니다. 21,431개 검사 통과는 보관 무결성의 증거이며 과학적 가설의 증거가 아닙니다.

Git 자동 줄바꿈 변환으로 최초 staging 검사에서 104개 파일의 bytes가 달랐습니다. 원본 파일은 유지하고 `.gitattributes`의 보존 규칙을 적용해 다시 staging했습니다. [최종 검사](results/20261014T022108Z_git_bytes_2e327070/verification.json)에서 검토 대상 512개 파일의 Git blob이 원본과 모두 일치했습니다. 최초 실패 기록도 별도 디렉터리에 보존합니다.

`github_release.py`는 이 폴더 안에 독립 복사한 게시 도구입니다. 기존 버전을 import하지 않습니다. 로컬 credential helper를 사용하되 토큰을 출력하거나 저장하지 않습니다. GitHub에 이미 있는 다른 파일을 덮어쓰지 않고, draft에 업로드한 뒤 서버 SHA-256·크기를 대조한 후 공개합니다. 최종 게시 결과는 새 실행 폴더의 `publication_receipt.json`에 기록됩니다.
