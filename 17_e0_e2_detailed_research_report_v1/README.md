# E0–E2 detailed research report v1

Completed E0–E2 results only. This version adds descriptive analysis and a Korean report; it does not change the learner, frozen protocol, prior versions, checkpoints, or the running E3 queue.

## Open and reproduce

- Local report: http://127.0.0.1:8717/
- Report application: `report_app/` (serve the entire `dist/` directory).
- Reviewed calculations: `results/20261013T052346Z_7e2f6a68/extended_analysis.json` and adjacent CSVs.
- Run `analyze.py` using Python 3.12. It uses the standard library, the frozen v16 validation outputs, and original E0–E2 completion/cost records. Every invocation creates a new result directory with input hashes and the executed source.
- `build_report.py` invokes the installed Data App runtime and retains a source snapshot and build logs for every attempt.
- `finalize_report.py` validates material narrative values and writes the finished report metadata.
- `verify_report.mjs` uses an isolated headless Chrome profile to inspect rendered components, numeric values, three charts at desktop/narrow widths, and checkpoint selection/reset. Every attempt retains screenshots and failures; it never attaches to the user's normal browser.

To serve after a restart, run from the repository root:

```powershell
& 'C:\Python312\python.exe' -m http.server 8717 --bind 127.0.0.1 --directory '.\17_e0_e2_detailed_research_report_v1\report_app\dist'
```

The optional `launch_report.ps1` may be blocked by the machine's PowerShell execution policy. The active preview was started using the standard Python HTTP server instead. No policy was changed. Browser validation initially failed under the process sandbox; the approved external-sandbox check used the same isolated profile workflow. All failed attempts are retained.

## Interpretation

E0's fresh-bank replication retains a DC-focus advantage from the single P0 seed-901 parent. E1's independent-parent primary effect is +0.39 percentage points with only 1/3 original seeds positive. E2's primary DO donor contrast is −0.78 points. Positive secondary patterns do not replace these primary contrasts.

Report original seeds as the inferential unit; checkpoints and continuation repeats are nested. E1 and E2 reuse the same three original seeds. Evaluation-case bootstrap intervals condition on trained policies. Cross-repeat selection is a retrospective diagnostic and does not include the cost of training candidate branches. Absolute gains, U-relative effects and maximum task deterioration are distinct quantities.

The script retains actual completed-job cost totals: 5.88M training steps, 112,800 evaluation episodes and about 42.27 summed job hours. Queue waiting, initial implementation checks and failed attempts are outside that completed-job sum. Financial cost was not measured. No new RL steps or evaluation episodes were used for this report.

After delivery this version is frozen under the repository working rules; subsequent changes should use a new numbered version.
