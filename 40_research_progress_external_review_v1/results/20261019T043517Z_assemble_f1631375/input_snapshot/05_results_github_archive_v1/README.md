# 실험 결과 전체 GitHub 보관 v1

2026-10-08 사용자의 전체 결과 업로드 요청을 위한 독립 보관 도구입니다.
01~04의 학습 코드와 결과를 읽어 실험별 ZIP으로 보관합니다. 학습이나 정책 평가는 수행하지 않습니다.

- 포함: 구현 검증과 실패 기록, 사전학습, 10개 분기, 분석 표·그림·로그, 모든 checkpoint,
  replay와 optimizer/RNG 상태, 실행 당시 소스 사본, 설정·패키지·비용·hash 기록.
- 가상환경, Python 캐시, Git 내부 파일, 실행 잠금 파일은 설치·실행용 파일이므로 제외합니다.
- 각 ZIP은 저장소 최상위에서 풀면 원래 폴더 구조를 복원합니다.
- GitHub 기본 소스 ZIP과 별개로 Release의 `00`~`04` ZIP 다섯 개를 내려받아야
  Git에서 제외했던 대용량 실험 상태까지 복원할 수 있습니다.

전체 보관 위치: [GitHub Release](https://github.com/rlatmddn0211/practice_allocation/releases/tag/experiment-results-2026-10-08-v1).
실험 결과와 해석은 [공개 설명](release_notes.md)에 정리했습니다.

`build_archive.py`는 실행마다 새로운 `results/<UTC>_complete_archive_<ID>/`를 만듭니다.
입력 파일별 SHA-256을 기록하고 ZIP을 다시 읽어 모든 파일을 원본과 대조합니다.
소스가 보관 중 바뀌었는지도 검사합니다. `archive_manifest.json`에는 전체 파일 목록과
원본·ZIP의 크기 및 hash가, `archive_verification.json`에는 검증 결과가 저장됩니다.
도구 소스 사본과 Python 버전을 기록하며 실패 결과도 보존합니다.

`github_release.py`는 기존 Git 인증을 사용하되 인증 값은 출력하거나 파일에 저장하지 않습니다.
설정된 저장소에 초안 Release를 만들고 각 자산의 GitHub SHA-256과 크기를 확인한 후 게시합니다.
같은 이름의 기존 자산이 다르면 덮어쓰지 않습니다. 게시 이력은 별도 결과 폴더의
`publication_receipt.json`과 `events.jsonl`에 기록합니다.

두 스크립트는 Python 표준 라이브러리만 사용합니다. 예시:

```powershell
C:\Python312\python.exe .\build_archive.py
C:\Python312\python.exe .\github_release.py inspect
C:\Python312\python.exe .\github_release.py publish --archive-run results\<보관실행> --target-commit <GitHub-main의-커밋>
```

Release API와 자산 digest 확인은 [GitHub 공식 문서](https://docs.github.com/en/rest/releases/assets#upload-a-release-asset)를 따릅니다.
