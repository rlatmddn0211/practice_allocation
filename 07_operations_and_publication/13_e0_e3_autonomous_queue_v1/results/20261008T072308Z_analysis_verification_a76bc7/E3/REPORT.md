# E3 automatic analysis

All planned cells are retained, including floors, ceilings and negative effects.

Units: percentage points. Training variability is reported across original seeds; evaluation cases are not extra training seeds.

| Suite | Cohort | Contrast | Horizon | Original seeds | Mean pp | Seed range pp |
|---|---|---|---:|---:|---:|---|
| B | independent_pretraining | F_BP minus U / macro | 40000 | 3 | 0.00 | 0.00 to 0.00 |
| B | independent_pretraining | F_DC minus F_DO / DO | 40000 | 3 | 1.67 | -1.00 to 4.00 |
| B | independent_pretraining | F_DC minus U / macro | 40000 | 3 | 1.67 | -1.00 to 4.00 |
| B | independent_pretraining | F_DO minus U / macro | 40000 | 3 | 0.00 | 0.00 to 0.00 |
| B | independent_pretraining | F_PU minus U / macro | 40000 | 3 | 0.00 | 0.00 to 0.00 |
| B | independent_pretraining | F_BP minus U / macro | 20000 | 3 | 0.00 | 0.00 to 0.00 |
| B | independent_pretraining | F_DC minus F_DO / DO | 20000 | 3 | 1.67 | -1.00 to 4.00 |
| B | independent_pretraining | F_DC minus U / macro | 20000 | 3 | 1.67 | -1.00 to 4.00 |
| B | independent_pretraining | F_DO minus U / macro | 20000 | 3 | 0.00 | 0.00 to 0.00 |
| B | independent_pretraining | F_PU minus U / macro | 20000 | 3 | 0.00 | 0.00 to 0.00 |
| C | independent_pretraining | F_BP minus U / macro | 40000 | 3 | 0.00 | 0.00 to 0.00 |
| C | independent_pretraining | F_DO minus U / macro | 40000 | 3 | 0.00 | 0.00 to 0.00 |
| C | independent_pretraining | F_PP minus U / macro | 40000 | 3 | 1.67 | -1.00 to 4.00 |
| C | independent_pretraining | F_PU minus U / macro | 40000 | 3 | 0.00 | 0.00 to 0.00 |
| C | independent_pretraining | F_BP minus U / macro | 20000 | 3 | 0.00 | 0.00 to 0.00 |
| C | independent_pretraining | F_DO minus U / macro | 20000 | 3 | 0.00 | 0.00 to 0.00 |
| C | independent_pretraining | F_PP minus U / macro | 20000 | 3 | 1.67 | -1.00 to 4.00 |
| C | independent_pretraining | F_PU minus U / macro | 20000 | 3 | 0.00 | 0.00 to 0.00 |

See branch_metrics.csv for absolute gains and deterioration, paired_contrasts.csv for matched cells, and analysis.json for scope and conditional measurement uncertainty.

No automatic claim of statistical significance is made. A favorable allocation does not by itself establish a need for an adaptive selector.
