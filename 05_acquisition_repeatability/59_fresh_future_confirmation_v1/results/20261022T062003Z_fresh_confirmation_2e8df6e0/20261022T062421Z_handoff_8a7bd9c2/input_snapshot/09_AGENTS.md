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
- On 2026-10-22 the user endorsed shifting the central research question to
  case-level gain/loss repeatability across futures from the same full learned
  state, with observational conditions distinguished from causal interventions.
  Version 55 analyzes existing paired 0k/8k/old-future/new-future outcomes only:
  overlap against state/task/eligibility-specific event-count expectations and
  success-history risk contrasts within parent/prefix/task common support.
  Preserve version 54's failed selection-investment gate. Do not relabel its
  outcome as a successful selector. Hypotheses developed from these results are
  exploratory; raw overlap is not a causal mechanism or a gain/loss ranking.
  New policy evaluation, training, replay/order interventions, and original C
  or stages 2/3 require a separate specification and authorization. They are
  not launched or scheduled by this existing-data analysis.
- The subsequent 2026-10-22 feedback narrows the existing-data follow-up to a
  same-state versus cross-state overlap contrast in independent version 56.
  For each parent/task, restrict gains to cases failed by both 8k prefixes and
  losses to cases successful in both. Recompute all four old/new pairs on the
  identical common set; their mean same-minus-cross contrast is paired, not four
  independent repeats. Report support, event-count overlap bounds, parent/task
  contributions, uncertainty scope and actual future seed provenance.
  Preserve version 55 and add interpretation corrections in 56: label-randomized
  excess overlap can arise from heterogeneous case propensities; state association
  is not a causal component effect, and no loss excess is not non-repeatability.
  Keep the universal recent-success fragility explanation downgraded. This is
  existing-file analysis only; no new learning, evaluation, intervention, selector
  fitting or automatic progression is authorized. Preserve prior held stages.
- The next 2026-10-22 discussion narrows the prospective paper to starting-state
  dependence of success acquisition. Version 57 records the two-bundle proposal:
  first, two fresh 32k futures for every existing state, with reference-only
  frozen explanation predictions; second, conditionally, new parents with both
  reference and confirmation futures. DC/PU are the declared focus and the
  original four-task slot denominator is retained for the overlap contribution.
  Treat 57 as design/reference-file preparation only, not permission to launch
  or schedule the 20 proposed futures. Its numerical investment thresholds and
  4.65M total cap are proposals, not approved execution or scientific findings.
  New-parent count, budget and any pre-continuation boundary-condition definition
  remain to be fixed before that bundle. Preserve 56 as latest completed
  scientific analysis. No new selector, RL algorithm or causal intervention is
  required for the proposed empirical paper; keep all earlier held stages held.
- The subsequent pre-execution review is recorded independently in version 58.
  Preserve 57 and its predictions, model, seeds, weights, budgets and numeric
  investment thresholds. Limit any positive G claim to the specified reference
  0--4 grade/state-monotone M0; do not exclude all latent difficulty explanations
  or claim rank reversals/causal mechanisms. Audit fixed-prediction corrections,
  both mean invariants, and overall/leave-parent-out binary-label G bounds.
  Primary corrections occur only in 49 PU cases across three parents; DC and
  parents 41012/41014 have identical M0/M1 forecasts, not empirical null effects.
  Keep all 548 eligible cases in G and preserve its within-parent case-pooled
  weights. Distinguish positive conditional evidence below investment thresholds
  from inconclusive evidence, technical failure and unexecuted confirmation.
  This is existing-file preparation/audit only, not launch or scheduling approval.
  Version 56 remains the latest completed scientific analysis; retain all held
  stages and require a separate implementation for any authorized F3/F4 run.
- On 2026-10-22 the user explicitly authorized the first confirmation bundle
  after reading version 58: perform full-state restoration/RNG-only technical
  checks, then run all 20 frozen F3/F4 futures if they pass. Implement independently
  in version 59. Use the original ten 208k states, 32k BP continuation per future
  (640k total), original O100 final evaluation (at most 4M), cumulative technical
  cap 10k and total cap 4.65M. The first technical plan reserves at most 7k for
  both future IDs; all research workers must restore original states again.
  Preserve prediction/model/shrinkage/weights/seeds/job order and numeric gates.
  Keep zero automatic retry reserve, stop on integrity failure, retain all costs
  and attempts, and run every approved job regardless of scientific direction.
  This supersedes the earlier no-execution status for this first bundle only;
  do not edit the historical protocol58 authorization field. New parents, C,
  original stages 2/3, new selectors and causal interventions remain outside this
  authorization. Distinguish technical completion, scientific evidence and
  subsequent investment decisions in the eventual result record.
