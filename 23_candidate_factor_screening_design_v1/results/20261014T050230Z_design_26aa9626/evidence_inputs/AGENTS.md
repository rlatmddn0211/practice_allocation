# Repository working rules

- Preserve the root pilot design unless the user asks for a design revision.
- Keep each experiment implementation self-contained in a clearly numbered,
  descriptive directory, such as `01_implementation_validation_v1`.
- Once an implementation has been validated and delivered, treat that directory
  as a frozen version. Subsequent implementation or experimental changes belong
  in a new directory. Do not make old versions import code from newer versions.
- During development, each verification run must use a new output directory and
  retain a snapshot/hash of the source it actually ran. Preserve failed runs.
- Do not overwrite existing run directories or checkpoints.
- Record configuration, dependency versions, source hashes, seeds, actual costs,
  and failed checks. A smoke test is not evidence of a scientific effect.
- The user authorized P0 uniform pretraining on 2026-10-07 after implementation
  validation. Keep the ten research branches as a separate execution stage.
- The user explicitly authorized the ten research branches on 2026-10-07.
  Run them in an independent version from the fixed P0 seed-901 200k checkpoint:
  five allocations, two continuation seeds, 40k additional steps each.
  New pretraining conditions and additional original seeds remain separate stages.
- The user explicitly authorized the replication stage on 2026-10-08:
  continue from the same fixed P0 seed-901 200k checkpoint with new continuation
  seeds 1903, 1904, 1905, all five allocations, and 40k additional steps per branch
  (15 branches, 600k steps). Keep version 06 independent, preserve the original
  learner and evaluation bank, and report these three repeats separately from
  discovery seeds 1901/1902 before a combined descriptive summary.
- The user explicitly authorized E0 through E3 on 2026-10-08, including
  implementation and unattended sequential execution through E3. Follow the
  frozen protocol in version 08: fresh evaluation, independent original seeds
  11/12/13, fixed-target donor swaps, and task compositions B/C. Implement stages
  independently in versions 09/10/11/12 and orchestrate them in version 13.
  Run all approved cells regardless of scientific effect direction; stop only
  for technical integrity failures or exhausted recovery attempts. Optional R
  and E4 are not authorized by this instruction. Use immutable full checkpoints
  every 20k with lossless replay compression; retain interrupted attempts.
