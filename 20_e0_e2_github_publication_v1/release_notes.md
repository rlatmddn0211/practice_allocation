Completed E0–E2 results from the frozen E0–E3 campaign, plus independent research analyses and a concrete budgeted-practice research proposal.

The main branch includes readable reports and CSV/JSON exports. This release supplies the complete E0–E2 run directories: raw evaluations, training logs, configurations, dependency versions, source snapshots, full model/optimizer/replay/collector/RNG checkpoints, and failed technical attempts. It also includes the 26 earlier full checkpoints evaluated by E0 and the original evaluation bank used for exclusion checks.

- E0: fresh evaluation of the fixed original state and 25 branches; 10,800 evaluation episodes.
- E1: original seeds 11/12/13, starting checkpoints 200k/400k, 90 branches; 4.80M training steps and 79,200 evaluation episodes.
- E2: fixed-target donor swaps, 27 branches; 1.08M training steps and 22,800 evaluation episodes.
- Total completed work: 5.88M training steps, 112,800 evaluation episodes, 592 completed jobs.
- 18,123 archived files and 323 referenced full checkpoints, including E0 parents. Intermediate checkpoints are included; 323 does not mean independent experimental runs.

Extract all five ZIP files into the same directory. `runs/` preserves the original D-drive experiment hierarchy; `workspace/` contains earlier evaluated parent checkpoints. Original records retain their original paths and bytes. `archive_manifest.json` maps all paths and records SHA-256 hashes. It also lists deliberate exclusions. Live E3 results, mutable queue state, environments, caches and lock files are not part of this release. Portable CSV/JSON exports and restoration instructions are in `20_e0_e2_github_publication_v1` on main.

Scientific interpretation: these are exploratory pilot results. The original independent-seed count is three in E1/E2. Continuation repeats and checkpoints are nested. A new retrospective audit finds that 20k and 40k allocation winners differ in four of six states; short-horizon cross-repeat selection and a simple average-drift correction do not outperform Uniform. This is not evidence of a successful cost-inclusive adaptive allocation method. No additional RL training was run to prepare this publication.

Every ZIP member was compared to its original SHA-256. Release publication checks GitHub's SHA-256 digest and byte count for every uploaded asset. See `SHA256SUMS.txt`, the archive manifest and the committed publication receipt.
