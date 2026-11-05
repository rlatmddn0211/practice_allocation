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
- On 2026-10-23 the user requested the completed F3/F4 experiment results.
  Independent version 61 analyzes existing files against frozen protocol 58,
  preserving predictions, eligibility, weights, seeds and decision thresholds.
  Record technical completion separately from inconclusive D/G evidence and
  the investment gate not passed. Preserve the failed path-length analysis
  attempt and all successful analysis/independent verification snapshots.
  DC D=0 reflects degenerate observed event margins; DC G=0 reflects identical
  forecasts. Neither establishes universal absence of state information.
  New parents, C, original stages 2/3, selector tuning and causal interventions
  remain held and are not authorized by a request for existing results.
- On 2026-10-27 the user explicitly authorized the final twenty-branch baseline
  study of success retention/acquisition/loss/recovery. Implement independently in
  version 64 from parents41011--41015, only prefix4201's original208k full state:
  UNIFORM and BP625 collection, two new paired futures each,32k per branch.
  Preserve the original SAC/environment and exhausted8k shuffle-block semantics;
  do not restart warm-up, replay or optimizer. Freeze outcome-blind nested E50/T20
  banks and unused seed streams before technical execution. Certify full-state
  restoration, passive250-step telemetry and isolated1k probes by logging-on/off
  and lossless-resume checks within a cumulative10k technical environment cap.
  Total all-attempt environment cap is6.05M, training640k; reuse P/S evaluations
  only with full provenance/contract verification. Save80 full checkpoints at
  S+4k/8k/16k/32k, retain every failed attempt and its costs, no automatic retries
  or seed replacement. Complete all authorized paths regardless of scientific
  direction, stopping for integrity failure or exhausted caps. Analyze paired
  cases/parents/futures without treating twenty paths as twenty parents. This is
  development evidence, not a new selector or preservation efficacy test. New
  parents, MT10/CW expansion, preservation interventions and original stages2/3
  remain separate unexecuted stages requiring their own frozen scope.

- Later on2026-10-27 the user explicitly requested queuing the first retention
  intervention after baseline64, and approved the concrete forty-path proposal:
  five fixed prefix4201 S states, BP625 only, two new paired futures, four arms
  A stock SAC/B actor LR half/C general-memory fixed-S teacher preservation/
  D success-episode-memory identical preservation,32k each. Implement independently
  in66. Fixed forward teacher-to-current Gaussian KL coefficient1 in the same
  actor step; critic/alpha/RL replay unchanged. Match C/D task,25k birth-age bins,
  distinct-episode quotas and observations; use identical general fallback when
  no successful historical episode exists, and disclose support/teacher limits.
  Training1.28M, evaluation at most8.8M, cumulative technical20k, total all-attempt
  cap10.10M; no automatic retries or seed replacement. Wait for the exact pinned
  baseline64 campaign's20-path completion plus analysis/independent verification,
  then certify exact restore, RNG isolation, lambda-zero equivalence and lossless
  intervention resume before research. All research restores original S again.
  User approved the Windows detached-queue fallback because tmux/usable WSL is
  absent; do not install/reboot/migrate the running experiment to satisfy tmux.
  Preserve64 unchanged, every failed attempt, seeds, sources and physical costs.
  Record technical completion separately from scientific efficacy. This request
  does not authorize new parents, MT10/CW, primitive-skill interventions or the
  originally held C/stages2/3.
  During queue preparation, a string-valued CSV length summation defect was
  found in frozen64's post-completion analysis. Preserve64 and its eventual
  failed analysis. Independent67 contains only the integer-cast repair plus
  identical copied inputs and unchanged independent verifier. The66 dependency
  queue may recover this exact known file-only error once after all20 research
  paths pass full hash/restore/cost audits, and requires the repaired full
  analysis and independent verification before progression. No other failure,
  partial result, learning retry or evaluation rerun is licensed by this repair.

- On2026-10-28 the user's review of68 identified four existing-record followups.
  Independent69 records exposure/support/fallback, preservation strength and
  common-panel drift, paired case outcomes, and post-hoc D-B plus G-R intervals.
  It reads completed66 files only, reuses the frozen20k paired draws/multiplicities,
  and performs no new environment steps, policy scoring, neural forward pass,
  SAC updates, RNG draws, selector fitting, coefficient tuning or queue reservation.
  Preserve66/68 unchanged and all component attempts. Same task/age/index-level
  sampling counts do not mean matched effective constraints; gradient norms are
  not actual Adam updates. G-R means P0/S0/final1, not never-mastered ability.
  Keep case-conditioned intervals and post-outcome matched sets exploratory;
  do not infer general efficacy, noninferiority or shared primitive preservation.
  Functional phases, evaluation videos/action traces and per-update Adam norms
  were not found in these records; do not invent them or run new policy evaluation
  to fill them. New experiments and previously held stages stay separately held.

- On 2026-10-29 the user explicitly authorized preparation, implementation,
  technical validation, new diagnostic evaluation, analysis and Korean reporting
  for the existing BP/DC checkpoints. Independent71 uses all five fixed parents,
  both existing66 futures, all original E50 physical cases, final A/B/C/D plus
  common P/S (5,000 episodes if all P exist). No SAC updates, replay insertion,
  new training futures, coefficient changes or state-swap probes. Freeze physical
  case/checkpoint provenance, passive approach/contact/object-motion definitions,
  videos and analysis rules before comparison. Keep original deterministic CUDA
  evaluation, first-success stop and 500-control-step horizon. Main cap2.5M,
  separate technical/invalid/failed/retry cap50k, total2.55M across all attempts.
  Keep one append-only attempt/control-step ledger, original recordings, immutable
  source snapshots and failures. Valid logging-on technical rows may be adopted
  once as main; logging-off30 matched checks are technical costs. Stop affected
  evaluation for unexplained restore/logging/core measurement discrepancies.
  Analyze all methods and unfavorable DC results; paired20k physical-case draws
  remain conditional on existing five parents/two futures. Record event exposure,
  censoring and unknown capability separately. Natural-rollout associations do
  not establish functional ability, causal mediation or shared primitive retention.
  No follow-on experiment is launched or queued by this authorization.

- On 2026-10-29 the user requested organizing the published GitHub folders
  by related research questions. Independent74 maps all66 published version
  folders into eight topic groups; remote main is now 2208e99d4452288304d880a076cca5670b0eff96.
  The original local runtime checkout deliberately keeps its flat paths and
  original HEAD/index to preserve unpublished checkpoints/replay/venvs and
  existing README/AGENTS changes. Do not ordinary-pull/merge the reorganized
  remote tree over this runtime checkout. Future publications must start
  from current remote main and74 path_manifest, not this legacy local HEAD.
  Published code/data/media blobs are unchanged; link-edited documents have
  exact original blobs and path recovery routes. Use74 restore_legacy_layout.py
  into a new empty directory for published sources that expect flat siblings.
  This organization ran no new training/evaluation and published no additional
  untracked experiments. The direct push and remote main hash were verified.

- On 2026-10-29 the user explicitly authorized independent75 stored-action
  experience-reuse research: five original66 S0 full states, BP/DC targets,
  target-only R0 4k prefixes to form S1, then300 frozen8k cells
  (100development, choices locked,200confirmation in two new futures).
  Use only verified complete successful pre200k training episodes from
  the five collectors, original stored normalized actions/task/goal labels,
  shared archive and fixed actor-only BC batch64; no teacher replacement.
  BP/DC support passed; DO/Push lack20episodes and are excluded. Preserve
  all existing sources/assets; new physical Dev25/Confirm25 are disjoint
  from old evaluation and training archive usage. Freeze one technical
  lambda, seeds, rules and choices before confirmation; no retuning.
  Total all-attempt cap7.94M, technical/failed/invalid/duplicate cap50k.
  The +2pp and robustness gates are this new user-proposed investment
  rules, not prior approvals, power-derived thresholds or guarantees.
  Maintain issued/completed control-step journals and immutable attempts.
  Certify exact restores/R0 andlambda0/logging/resume before research.
  State/task-stage choices are limited rules, not a discovered primitive,
  causal mechanism, arbitrary-state retriever or unseen-task transfer.
  All original held stages remain separate. No automatic scope expansion.
  Read75/ACTIVE_CAMPAIGN.json and exact campaign progress/cell_index and
  COMPLETE/FAILED records for live status; do not launch duplicate work
  or modify75 frozen sources while the campaign is running.

- On 2026-10-30 the user explicitly authorized independent76 existing-file
  post-hoc analyses of completed75: BP state-specific candidate contrasts and
  BP/S0 acquisition/loss decomposition, input provenance, paired20k-case
  bootstrap for exactly21 specified estimands, independent arithmetic checks,
  Korean report and ZIP. Preserve75 sources, choices, seeds, gates and the
  original official judgment of hold. No training, environment reset/step,
  policy forward/scoring, model/replay restoration, new cases, source archive
  substitution, functional detector, broad correlations or follow-on queue.
  Reuse certified physical-case/panel-membership-atom dependence; never treat
  shared initial labels/futures/states as independent cases. All new intervals
  are individual exploratory conditional intervals, not preregistered tests or
  a new progression gate. Record execution separately from scientific findings,
  retain every analysis attempt/snapshot, expose unfavorable and missing data,
  and finish with zero new training/evaluation environment steps.

- On 2026-10-30 the user explicitly authorized independent77 extra-loss
  confirmation through preparation, technical certification, all research cells,
  analysis, independent verification and Korean reporting. Reuse the exact75
  five S0 states, ten target-specific S1 states and shared608-success-episode
  BP/DC archive; do not regenerate S1 or change stored actions, task encoding,
  actor-only dimension-mean MSE, batch64 or lambda0.3022954787919176.
  Exactly R0/RTask/RTaskFirst/RFirst, both targets and states, three new
  confirmation futures:240 eight-k cells,1.92M valid research training.
  Freeze fresh physical Eval25/Mid8, paired sampler fields, seeds, D1-D4,
  risk-set decomposition and physical-case bootstrap before outcomes.
  Normal cap6.13M plus technical/failed/invalid/duplicate50k, total6.18M
  all-attempt control steps. Preserve issued/completed journals and failures.
  Pass exact restoration, stock/lambda0 equivalence, logging/probe isolation
  and lossless resume before research; bounded technical repairs are allowed
  without performance selection or widening tolerances. Preserve75's hold
  and76 as same-data post-hoc evidence. No new selector, coefficient search,
  extra arms/parents/tasks/futures, primitive-skill claim or follow-on queue.
  Read77/ACTIVE_CAMPAIGN.json and its exact status/cell_index/COMPLETE/failure
  records; never launch duplicate work or alter frozen research sources.

- On 2026-11-02 the user requested77 results. Its exact campaign
  20261030T074222Z_campaign_caa6dbc8 completed all240 main cells,20 initial
  cells and8420 outcome rows on2026-10-30T20:53:57Z; actual all-attempt
  control cost3,360,521, technical7,072, failed execution attempts0.
  Independent78 is a saved-label result review only: preserve77's completed
  source/data/report/ZIP and75's hold. All four primary composition/state
  simultaneous case intervals include0; do not claim equivalence or reproduce
  the old large RTask extra loss/First mitigation. BP/S1 First arms have
  unfavorable auxiliary results, strongly parent-dependent; report them with
  their individual conditional uncertainty scope. No new training, evaluation,
  bootstrap draws, model/probe execution, seed expansion or follow-on queue.
  Use actual77 COMPLETE/analysis/verification and78 LATEST records for results;
  the old launch monitor's fixed science_status template is not a live
  scientific judgment and must not override completed analysis records.

- Later on2026-11-02 the user narrowed the immediate followup to completing
  three existing-record analyses through77. Independent79 reuses the original
  I_T/I_M estimates and case intervals, all parent/future/LOPO/case exchanges,
  and recorded pre-learning action mismatch, sampling exposure, gradients and
  probes. Focus BP/S1 parent41014 while including all opposite/unchanged/floor
  parents and matchedS0; do not explainS1 with anS0 overall mean. This is
  post-outcome exploratory interpretation, not a new confirmation. No new
  environment reset/step, learning/evaluation/model/replay/probe execution,
  bootstrap draws, classifier/threshold/weight search or queue. Preserve all
  frozen sources/results and75's hold. Finish with the observed phenomenon,
  its actual repetition scope and whether a measurable condition candidate
  remains. No forced candidate or automatic random-half/Last/lambda expansion.
  Cross-evaluating old/new models/panels remains a separately specified possible
  followup; this analysis does not authorize or schedule it.

  Completed79 on2026-11-02: extraction23881 and independent66360 arithmetic/
  provenance checks passed. I_T+1.60pp[-0.53,+4.00] and I_M+0.53pp[-1.87,+2.67]
  remain inconclusive state contrasts. BP/S1 mixedFirst extra loss concentrates
  in41014(+21.33pp), with41015 opposite(-4.00pp); dropping41014 changes the
  overall+3.47pp to-1.00pp. Initial mismatch, recorded exposure and average
  gradient/probe summaries did not identify a transferable condition beyond
  parent IDs. Keep First-condition expansion stopped; do not auto-run random
  halves, Last, strength tuning or cross-evaluation. The latter is an unexecuted
  optional question about model-family versus panel dependence only. New steps,
  policy forwards, model loads, bootstrap/sampler draws and follow-on queue0.
  Use79 LATEST and its preserved report/CSV/source/input hashes for evidence.

- Subsequent2026-11-02 user review requires contrast-specific interpretation.
  Independent80 preserves77/78/79 and checks saved BP/S1 labels/arithmetic only.
  MixedFirst-minus-R0 concentration in41014 must not be generalized to all
  adverse First contrasts. TaskFirst-minus-Task increases loss3.20pp with the
  original individual95% interval[0.80,5.60], remains+2.00pp without41014, and
  has future means+3.2/+8.0/-1.6pp. Parent means41011/41014/41015 are adverse;
  this is not three separately confirmed parent effects. On41015 both Task
  andTaskFirst still lose less thanR0. H requires initial success and finalR0
  success; no case H inall3 does not imply no First failure inall3. No original
  point/CI calculation error found; this is a scope clarification, not a new
  independent study. Stop expansion because no predictive/mitigation principle
  was obtained, not because all extra loss disappeared. Cross-evaluation stays
  optional/unexecuted. Preserve all held stages; no new environment steps,
  model/policy/probe execution, bootstrap/sampler draws or follow-on queue.
