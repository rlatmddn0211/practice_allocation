# Implementation validation: failed

Device: cpu. Passed 1/10 planned gates.
Elapsed: 1.49 seconds. Environment transitions: 0.
SAC iterations: 0. Evaluation episodes: 0.

| Check | Result | Seconds |
| --- | --- | ---: |
| unit_contracts | PASS | 0.06 |
| environment_inputs_and_reset | FAIL | 0.12 |

This is a technical verification result. P0 and the ten research branches have not run.
Exact resume is tested on this runtime/device; cross-version or cross-device bitwise equality is not claimed.
Environment resets include internal simulator work that is counted as resets, not agent transitions.

See failure_traceback.txt. Failed and unattempted work is not reported as a pass.
