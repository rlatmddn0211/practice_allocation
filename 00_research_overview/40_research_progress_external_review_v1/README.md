# 연구 진행 종합 보고서 · 외부 평가용

평가자에게 전달할 본문은 **[research_progress_report_ko.md](research_progress_report_ko.md)** 한 파일이다. 대화나 저장소를 먼저 읽지 않아도 연구 과정·실험·결과·한계·현재 판단을 검토할 수 있도록 작성했다. 2026-10-19 기준, 17개 절과 15개 표, 약 3만 자다.

포함 범위는 초기 설계·구현 검증, P0, 최초 발견·후속 반복, E0~E3, 질문의 변화와 문헌 비교, 기본 세 요인과 추가 후보 ①~⑧, 완료된 본 실행의 비용, 전원 중단·복구, 외부 Deep Research 평가, 39번 미실행 제안과 필요한 수정이다. 16절에는 외부 평가자가 판단해 줄 쟁점을 넣었다.

## 읽기와 전달

- 외부 평가용 단일 문서: [종합 보고서](research_progress_report_ko.md)
- 같은 내용의 웹 보기: [로컬 미리보기](http://127.0.0.1:8740/)
- 서버 없이 전달할 수 있는 [단일 HTML 읽기 파일](research_progress_report_ko.html)
- 미리보기 실행 파일: [report_app/dist/index.html](report_app/dist/index.html). 이 파일은 같은 `dist`의 snapshot sidecar와 함께 HTTP로 제공한다.
- [근거 조립·검산 코드](assemble_report.py), [외부 출처 확인 범위](external_sources.json), [검산된 데이터와 출처 snapshot](reviewed_snapshot.json)

미리보기는 이 컴퓨터에서 서버가 실행되는 동안 사용할 수 있다. 외부 평가에 업로드할 때는 Markdown 본문을 전달하면 된다. 본문에 핵심 결과표·정의·비용·한계가 모두 들어 있어 로컬 링크를 열 필요가 없다. 공개 저장소 출처 링크는 추가 검토용이다.

## 이번 작업의 범위

새 학습·환경 진단·복제 update는 모두 0이다. 이전 실험의 재학습이나 기존 bootstrap 재실행을 하지 않았다. 핵심 CSV와 본 실행 영수증을 읽어 주요 수치·표·비용 합계를 대조했다. 실험 설계 승인이나 GitHub 추가 게시를 수행하지 않았다. 기존 01~39의 전달된 자료와 루트 파일럿 설계는 보존했다.

## 검증과 보존

최종 수치 검산은 [20261019T044214Z_assemble_3021ca9b](results/20261019T044214Z_assemble_3021ca9b/summary.json)의 157개 검사를 통과했다. 독립 폴더에 실제 입력 사본·SHA-256·보고서와 실행 코드 사본을 보존했다. [비용 원장](results/20261019T044214Z_assemble_3021ca9b/completed_cost_ledger.json)의 본 실행 합계는 학습 14,960,000, 평가·진단 78,276,809, 전체 환경 93,236,809 step이다. 기술 사전검사·중단 시도·분석 비용을 제외한 범위다.

[최종 빌드](results/20261019T044215Z_build_d32bbe25/build.json)와 [화면 검증](results/20261019T044215Z_browser_997b92de/verification.json)을 보존했다. 화면 검증은 37개 검사와 7개 캡처를 남겼고, 17개 절·15개 논리 표·전체 표 행, 주요 수치, 일반/좁은 화면에서 페이지 넘침과 브라우저 예외를 확인했다. 캡처 중 일반 화면의 요약·후보 표와 좁은 화면의 ⑧을 직접 확인했다. 자동 검산 통과 수는 과학적 효과의 증거가 아니다.

실패도 보존했다. 첫 조립은 기존 CSV 조건명을 `alternate`로 찾다가 실제 `alternate4k`와 달라 중단됐다. 수정 뒤 새 폴더에서 재검산했다. 첫 브라우저 시도는 샌드박스의 Chrome GPU 프로세스 종료로 실패했다. 허용된 외부 실행에서는 서술용 Markdown renderer가 표를 지원하지 않는 점을 검출했다. 본문을 공용 `RichNarrative`, 표를 공용 `DataTable`로 분리해 고쳤으며 긴 표도 모든 행이 표시되도록 구성했다. 다음 독립 검증이 통과했다. 앱 내부 브라우저를 자동으로 여는 도구는 세션에 없어, localhost 서버와 독립 headless Chrome으로 확인했다.

## 재조립

완료된 보고서는 이 버전으로 보존한다. 이후 내용 수정은 새 번호 버전으로 만든다. 아래 명령은 현재 자료를 다시 조립·검증할 때 사용하는 명령이며 각 실행은 새 `results/` 폴더를 만든다.

```powershell
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 40_research_progress_external_review_v1\assemble_report.py
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B 40_research_progress_external_review_v1\build_report.py
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -B -m http.server 8740 --bind 127.0.0.1 --directory 40_research_progress_external_review_v1\report_app\dist
node 40_research_progress_external_review_v1\verify_report.mjs
```

빌드는 설치된 data-analytics 1.0.11의 보호된 공용 runtime을 사용한다. 앱 ID는 `report:ca09e9e1-9219-44cc-9565-7ff2ccbbc193`으로 고정했다. 브라우저 검증은 사용자의 일반 브라우저와 분리된 임시 프로필만 사용한다.
