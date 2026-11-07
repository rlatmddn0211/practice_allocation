# 재분석 안내

원래 Windows runtime 프로젝트 루트는 `C:\Users\SS\Projects\robot_practice_allocation` 이다. source_snapshot과입력manifest의해시를먼저확인한다. Python은기존file-processing환경을사용하며torch/Meta-World/MuJoCo를import하지않는다.

```powershell
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -X utf8 87_bp_retention_archive_content_posthoc_v1\analyze.py --stage core
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -X utf8 87_bp_retention_archive_content_posthoc_v1\verify.py --analysis <새 core 출력 경로>
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -X utf8 87_bp_retention_archive_content_posthoc_v1\report.py --core <새 core 출력 경로>
.\13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe -X utf8 87_bp_retention_archive_content_posthoc_v1\finalize_delivery.py --delivery <새 delivery 출력 경로> --visual-review <실제로 확인한 PNG 해시 JSON>
```

이번core출력: `C:\Users\SS\Projects\robot_practice_allocation\87_bp_retention_archive_content_posthoc_v1\results\20261106T124257Z_bp_content_posthoc_ab295693`. 독립검산: `C:\Users\SS\Projects\robot_practice_allocation\87_bp_retention_archive_content_posthoc_v1\results\20261106T124257Z_bp_content_posthoc_ab295693\verification\20261106T124841Z_6a8af63a`.

모든실행은새폴더를만든다. 원캠페인·보고서·checkpoint는수정하지않는다. 파일만계산하고새환경전이·모델실행·난수draw는없다. bootstrap분위범위는원85요약을그대로참조한다. 새자료없이는새goal/parent의확증을재생성할수없다.

전달ZIP에는소형표·설정·코드·그림·핵심영수증만들어간다. 원본대형NPZ/영상/model은`provenance/core_input_manifest.jsonl`의실제경로+SHA256로연결한다. 환경상태pkl이나정책모델을분석실행시로드하지않는다. snapshot을새checkout에서재실행하려면code의common.py에기록된ROOT기준원본파일상대배치를보존하거나같은hash의원자료경로를명시적으로매핑해야한다. 원GitHub의group레이아웃을legacy runtime에pull하지않는다.
