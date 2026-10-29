# First retention intervention: queued development experiment

Approved by the user on 2026-10-27 after the explicit scope/budget question.
This version is independent of frozen baseline64. Original C, stages2/3,
new parents, MT10/CW, and primitive/hierarchical interventions remain held.

40 paths:5 original parents41011–41015 ×2 new futures ×A/B/C/D. Every path
restores prefix4201's full208k state and continues BP625 for32k, preserving
original SAC replay, update count and schedule semantics. STOP is the S policy.
Research training1.28M; research evaluation at most8.8M; cumulative technical
cap20k; all-attempt total10.10M. No automatic retry or seed replacement.

| Arm | Treatment |
|---|---|
| A | Original SAC |
| B | Actor LR1.5e-4; critic and alpha stay3e-4; Adam moments preserved |
| C | Fixed S actor teacher on general training-episode observations |
| D | Same teacher/loss/strength on historical-success-episode observations |

C/D use KL(teacher||student), summed across action coordinates and averaged
over a256-observation preservation batch, coefficient1. The extra gradient is
combined into the same actor step. No extra environment, SAC, critic or
temperature updates are introduced. This is a specified development probe,
not a claim that coefficient1 is optimal or actual regularization is matched.

Memory selection uses only restored S replay and historical training labels.
Four tasks ×four fixed25k birth-age bins; per stratum use min(4,successful
episode count) unique episodes for D, the same unique-episode count from all
episodes for C, and32 unique observations/episode. With zero successful
episodes, both arms use the same general fallback. Report every stratum,
episode count, selected replay slot and birth step. Historical episode success
does not establish that the current S teacher succeeds there. There are no
evaluation-derived anchor observations or labels. The memory remains fixed.

P/S and outcome-blind E50/T20 cases are copied from64 with provenance. Score
T20 at+4k/+8k/+16k and E50 at+32k; save160 full checkpoints plus retention
sidecars containing frozen teacher, memory, private RNG and counters. Each
worker restores original S again after the technical tests.

Primary contrast is D−C; B−A/C−A/D−A are reported together. Report J/G/L and
same-case recovery R, with R a subset of G, J−JS=G−L. Equal task weights,
mean of two futures within parent, equal weight for five parents; all paths,
task/parent/future contributions and leave-parent-out sensitivity retained.
Case intervals resample the same indices across all arms/futures20,000 times.
These intervals are conditional on observed policies, not new-future coverage.

`deferred_queue.py` pins the exact64 campaign. It requires all20 paths,
completed analysis and independent verification before starting66's separate
technical gate. A passed gate permits prepare/run of these40 paths. Failed
upstream analysis, source change, missing ledger, failed integrity check or
exhausted cap prevents progression. There is no effect-direction gate and no
automatic enlargement based on results.

One known file-only exception is pinned explicitly:64's endpoint CSV length
summation raises TypeError because CSV lengths are strings. If and only if
all20 research paths pass their integrity audit and that exact analysis defect
occurs, independent67 reruns the same analysis with the single integer cast,
then independently verifies it. The failed64 analysis and unchanged64 sources
remain preserved. Any other analysis error blocks the queue. Recovery consumes
zero environment steps and does not repeat a learning or evaluation attempt.

This computer has Git Bash but no usable WSL installation or tmux executable.
The user approved the equivalent existing Windows detached queue mechanism;
no OS installation, restart or training-environment migration is performed.
The watcher is a hidden native Python process, keeps the machine awake while
running, and records its PID, source hashes, dependency status and output logs.
It survives terminal closure; a reboot or process termination requires review,
and never silently resumes or reruns an attempt. `STOP` in this directory or
the queue directory cancels pending stages; during research, worker stops at
an episode boundary and records partial costs.

No scientific outcome is available at queue creation. Read `ACTIVE_QUEUE.json`
and the referenced queue `STATUS.json` for actual execution state.
