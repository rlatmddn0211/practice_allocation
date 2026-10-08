# E0 automatic analysis

All planned cells are retained, including floors, ceilings and negative effects.

Units: percentage points. Training variability is reported across original seeds; evaluation cases are not extra training seeds.

| Suite | Cohort | Contrast | Horizon | Original seeds | Mean pp | Seed range pp |
|---|---|---|---:|---:|---:|---|
| A | replication_1903_1905 | F_DC minus F_DO / DO | 40000 | 1 | 6.00 | 6.00 to 6.00 |
| A | replication_1903_1905 | F_DC minus U / macro | 40000 | 1 | 6.00 | 6.00 to 6.00 |
| A | replication_1903_1905 | F_DO minus U / macro | 40000 | 1 | 0.00 | 0.00 to 0.00 |
| A | replication_1903_1905 | F_WC minus U / macro | 40000 | 1 | 0.00 | 0.00 to 0.00 |
| A | replication_1903_1905 | F_WO minus U / macro | 40000 | 1 | 0.00 | 0.00 to 0.00 |
| A | discovery_1901_1902 | F_DC minus F_DO / DO | 40000 | 1 | 5.00 | 5.00 to 5.00 |
| A | discovery_1901_1902 | F_DC minus U / macro | 40000 | 1 | 5.00 | 5.00 to 5.00 |
| A | discovery_1901_1902 | F_DO minus U / macro | 40000 | 1 | 0.00 | 0.00 to 0.00 |
| A | discovery_1901_1902 | F_WC minus U / macro | 40000 | 1 | 0.00 | 0.00 to 0.00 |
| A | discovery_1901_1902 | F_WO minus U / macro | 40000 | 1 | 0.00 | 0.00 to 0.00 |
| A | combined_descriptive | F_DC minus F_DO / DO | 40000 | 1 | 5.60 | 5.60 to 5.60 |
| A | combined_descriptive | F_DC minus U / macro | 40000 | 1 | 5.60 | 5.60 to 5.60 |
| A | combined_descriptive | F_DO minus U / macro | 40000 | 1 | 0.00 | 0.00 to 0.00 |
| A | combined_descriptive | F_WC minus U / macro | 40000 | 1 | 0.00 | 0.00 to 0.00 |
| A | combined_descriptive | F_WO minus U / macro | 40000 | 1 | 0.00 | 0.00 to 0.00 |

See branch_metrics.csv for absolute gains and deterioration, paired_contrasts.csv for matched cells, and analysis.json for scope and conditional measurement uncertainty.

No automatic claim of statistical significance is made. A favorable allocation does not by itself establish a need for an adaptive selector.
