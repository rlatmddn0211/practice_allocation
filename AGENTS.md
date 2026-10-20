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
- The user requested durable per-factor result records on 2026-10-14. After each
  candidate-factor analysis, record its execution status separately from its
  scientific conclusion, including effect sizes, baselines, uncertainty scope,
  original/continuation seeds, actual costs, source and input provenance,
  unfavorable or inconclusive findings, limitations, and next decision criteria.
  Use `25_candidate_factor_evidence_register_v1` as the first dated snapshot and
  record template. Preserve delivered records; put later evidence or corrections
  in a new numbered version linked to the prior record and update the root index.
  Do not label unmeasured factors as ineffective or completed analyses as proven
  allocation improvements. Recording a proposal does not authorize its execution.
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
- On 2026-10-19 the user authorized the sequential selection-value research
  direction: (1) five new B parents, two continuation repeats and BP/alternation/
  mixture (30 branches); (2) actual keep/switch branches from the same full 8k
  state and a simple rule only if selection differences are supported; (3) fresh
  parents with real diagnostic cost, a strong full-budget fixed comparator and
  an information-ignored comparator. Preserve proposal 39; use protocol 41 and
  independent stage-1 implementation 42. Do not use alternate-minus-mixture
  average advantage alone as the scientific progression gate. Later stages
  require their scientific gate and frozen, validated execution specifications;
  do not silently enlarge the samples or launch an unspecified stage-3 budget.
- Later on 2026-10-19 the user requested the detailed feedback amendments.
  Protocol 43 supersedes 41; implementation 44 supersedes 42 without editing
  frozen sources or discarding completed learning. Add full branch checkpoints
  at 36k without intermediate scoring, and fully refit the fixed comparator when
  removing a parent for sensitivity. Stage 2 targets the actual remaining 28k
  with one frozen score and finite rule family; its LOPO is conditional on F*/A*.
  Stage 3 includes both diagnostic always-keep/always-switch and both no-diagnostic
  fixed keep/fixed 8k-switch controls. Share paths only after validating full-state
  preservation and horizon independence, and commit the adaptive action before
  either future or any outcome is observed. Track physical cost separately from
  each method's 40k operational budget. Stage 3 sample size remains to be frozen.
- On 2026-10-20 the user accepted the stage-1 findings and explicitly put entry
  into the original stages 2 and 3 on hold. Treat stage 1 as completed with its
  investment gate not passed; do not relax its thresholds or expand seeds to
  force progression. Preserve the delivered version-45 evidence.
  The user requested a new research design prioritizing within-/across-repeat
  evaluation-case selection, paired evaluation uncertainty, success acquisition
  and loss, and existing training-log trajectories. Version 46 records this
  design, followed only conditionally by checkpoint evaluation and future
  replication from the same 8k learned state. It is a proposal, not authorization
  to execute or schedule new evaluation/training. Keep original stages 2/3 held
  unless the user explicitly changes that decision.
- Later on 2026-10-20 the user explicitly authorized only scope A of version 46:
  A1 within/across-repeat selection, A2 paired evaluation-case uncertainty, and
  A3 success acquisition/loss plus existing training-log trajectories.
  Implement and record this in independent version 47 using existing files only.
  No new environment steps, checkpoint policy evaluation, SAC updates, or queue
  reservations are authorized by scope A. B, C, and original stages 2/3 stay held.
- Following the completed A review, on 2026-10-20 the user endorsed execution
  of B solely to measure the net benefit and success retention after 8k.
  Evaluate the ten existing B/dose625 8k checkpoints (parents 41011-41015,
  continuations 4201/4202) on the same per-parent O100 cases, with no training.
  Use independent version 48 for the frozen evaluation and version 49 for
  analysis. Research evaluation is capped at 2,000,000 environment steps;
  necessary evaluation-integrity checks are separate and must be recorded.
  Link original-parent, 8k, and 40k outcomes at the case level and record all
  eight binary trajectories. Do not fit a selector, retune the TD thresholds,
  treat O100 as free online input, or infer prediction from shared-J8 change
  scores. Existing stage-1 failure and TD-rule degeneracy remain recorded.
  C and original stages 2/3 remain on hold; B does not authorize their execution.
- In the subsequent B review on 2026-10-20, the user recommended closing the
  current TD/candidate/action/horizon expansion and retaining A/B as completed
  development evidence. Version 50 records the existing-data concentration and
  task-scope supplement without changing frozen version 49. Preserve the
  distinction between measured realized stop/continue differences and unmeasured
  same-state expected continuation value; no superiority, equivalence, or
  noninferiority of fixed stop8 has been established.
  One new 32k BP future for all ten fixed 8k states is an optional separate
  proposal (320k training plus at most 2M final evaluation), not execution or
  queue authorization. Its state/RNG protocol, technical budget and numeric
  decision criteria remain to be frozen before any separately authorized run.
  Measuring future repeatability does not require an existing predictor.
  Keep C and original stages 2/3 held. Resource-saving fixed-stop research is a
  separate proposal, not a successful outcome to infer from current evidence.
- Later discussion narrowed the next research question to repetition of the
  32k BP continuation effect from the same ten 8k states. Version 51 prepares a
  prospective protocol and old-future choice tables, including crossed case
  halves to reduce shared-J8 measurement reuse. Treat its numeric investment
  gates and 10k technical environment cap as proposals, not user-approved
  experimental outcomes or execution authorization. It has no training queue.
  Latest completed experimental evidence remains versions 49/50; version 51 is
  a design/preparation record. Do not infer a validated deployable selector from
  its choices, which use old completed futures. Any authorized execution needs
  a separate implementation and state/RNG integrity verification first.
- On 2026-10-20 the user then explicitly authorized immediate execution of the
  version-51 same-state future replication proposal. Implement in independent
  version 52: all ten fixed BP 8k states, one new 32k future each (320k training),
  original per-parent O100 final evaluation (at most 2M steps), and necessary
  technical checks within the proposed cumulative 10k environment cap.
  Preserve the frozen choices, seed mapping and pre-outcome analysis criteria;
  certify exact full-state restoration and RNG-only replacement before research
  execution. Run the ten futures regardless of scientific direction; stop for
  integrity failures, with no automatic retries outside the caps. Preserve all
  attempts and full checkpoints. C and original stages 2/3 remain held.
