# E2 automatic analysis

All planned cells are retained, including floors, ceilings and negative effects.

Units: percentage points. Training variability is reported across original seeds; evaluation cases are not extra training seeds.

| Suite | Cohort | Contrast | Horizon | Original seeds | Mean pp | Seed range pp |
|---|---|---|---:|---:|---:|---|
| A | independent_pretraining | DC_minus_WO_plus minus U / macro | 40000 | 3 | -2.50 | -2.50 to -2.50 |
| A | independent_pretraining | DC_plus_WO_minus minus DC_minus_WO_plus / DO | 40000 | 3 | 20.00 | 20.00 to 20.00 |
| A | independent_pretraining | DC_plus_WO_minus minus U / macro | 40000 | 3 | 2.50 | 2.50 to 2.50 |
| A | independent_pretraining | DC_minus_WO_plus minus U / macro | 20000 | 3 | -2.50 | -2.50 to -2.50 |
| A | independent_pretraining | DC_plus_WO_minus minus DC_minus_WO_plus / DO | 20000 | 3 | 20.00 | 20.00 to 20.00 |
| A | independent_pretraining | DC_plus_WO_minus minus U / macro | 20000 | 3 | 2.50 | 2.50 to 2.50 |

See branch_metrics.csv for absolute gains and deterioration, paired_contrasts.csv for matched cells, and analysis.json for scope and conditional measurement uncertainty.

No automatic claim of statistical significance is made. A favorable allocation does not by itself establish a need for an adaptive selector.
