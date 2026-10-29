"""Create a new immutable protocol from v41; never edits the predecessor."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
source=HERE.parent/'41_selection_value_three_stage_protocol_v1/protocol.json'
p=json.loads(source.read_text(encoding='utf-8'))
p.update(version=HERE.name,date='2026-10-19',supersedes_protocol='41_selection_value_three_stage_protocol_v1',
         predecessor_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
         amendment_timing='During first-parent pretraining, before any parent/branch O100 outcome was produced or inspected',
         feedback_disposition='All proposed corrections adopted; unchanged sample size, learner, F08 block rules and primary objective')
s=p['stage1'];s['branch_checkpoint_horizons']=[4000,8000,20000,36000,40000]
s['gate']['repeatable_margin_score']='Entire O100 equal-weight macro success for each parent and continuation, not either half'
s['fixed_selection']='For each target parent and selection half, equally average both continuations of each other parent, then equally average those parent means; ties BP, alternate4k, mixture'
s['aggregation']='Four crossed scores per parent (2 continuation directions x 2 half directions), then equal-weight parents; not 20 independent observations'
s['gate']['leave_one_parent_out_definition']='Remove that parent entirely, rerun parent-informed choices and leave-target-parent-out fixed-method selection within the remaining four parents, then recompute gains. BP remains prespecified.'
s['gate']['deleting_precomputed_parent_gains']='Secondary descriptive sensitivity only; not the progression gate'
s['checkpoint36_cost']='30 extra full snapshots; environment steps and intermediate evaluation episodes added: zero'
s['partial_block_rule']='Use the exact existing generated schedule prefix. No quota rebalancing, reshuffling, phase restart or RNG reset at 36k or another budget endpoint.'
s['pretraining_source_reuse']='Completed v42 banks and full pretraining states reused with hash-verified job lineage; an in-flight worker finishes its job before handoff'
s=p['stage2'];s.update(remaining_training_steps=28000,primary_total_training_horizon=36000,
    new_training_steps_if_keep_suffix_reused_exactly=280000,total_environment_steps_upper_if_keep_reused=4320000,
    future_continuations_per_8k_state_per_action=1,
    repeatability_unit='Two different 8k states from each original parent, each with one paired keep/switch future; not repeated future draws from one identical state',
    validation='Leave whole original parent out for threshold fitting and scoring, conditional on F*/A* and the development-state set selected using all stage1 parents',
    limitation='Stage1 support need not involve the globally top-two F*/A* pair. A negative stage2 result is limited to this pair and this diagnostic/rule family.',
    rule_family='26 explicitly frozen candidates: two constant actions plus twelve attainable-score boundaries in each direction',
    partial_block_rule='Keep the generated task order and terminate after exactly 28k extra steps, even in the middle of an 8k dose block. Record actual quotas; do not rebalance or reshuffle.',
    alternation_phase='A switch to alternate4k starts with BP phase. Its 28k suffix has 4 BP and 3 DO phases; it is not a same-total-quota contrast with mixture.',
    extra_32k_suffix='Not scheduled in this revision. Any extra training or O100 scoring at 32k requires a new pre-outcome specification and separate costs.')
s['diagnostic']['score']={
    'counts':'s_t in {0,1,2}: number of any-success episodes among two fixed-500-step cases for task t',
    'integer_q':'3*s_BP - s_DO - s_DC - s_PU',
    'score':'q/6 = success_rate_BP - mean(success_rate_DO, success_rate_DC, success_rate_PU)',
    'attainable_q':list(range(-6,7)),
    'number_of_attainable_scores':13,
    'interpretation':'One preselected B-specific candidate signal, not an established factor; definition stays fixed even if F* is not BP focus'}
s['rule_specification']={
    'directions':['switch when score is above threshold','switch when score is below threshold'],
    'threshold_numerators_over_12':list(range(-11,12,2)),
    'constants':['always_keep','always_switch'],
    'candidate_count':26,
    'exact_decision':'q is integer; compare 2*q to odd threshold numerator. Equality is impossible.',
    'objective':'Maximize equal-parent mean final macro success of selected 28k action; both states per parent have equal weight. Implement as integer total selected O100 successes because all cells have 400 episodes.',
    'tie_breaks':['fewer switches on fitting states','constant action before threshold rule','fixed candidate order: keep, switch, high thresholds descending, low thresholds ascending'],
    'fallback':'No successful selection gate: retain F* and do not claim an adaptive improvement. Missing or invalid diagnostic is a technical failure, not silently imputed.',
    'outer_validation':'For each of five parents, fit among the 26 candidates on the other four parents (8 states), then choose and score both held-out states. Aggregate two states within parent, then parents equally.',
    'sensitivity':'Remove one parent, rerun threshold fitting and leave-parent-out scoring among the remaining four parents. F*/A* are held fixed; this remains conditional development evaluation.',
    'final_freeze':'Only after the stage2 gate passes, fit once on all ten states and freeze rule ID, threshold, direction, source/input hashes before any fresh-parent result.'}
s['gate']={
    'type':'exploratory conditional-development investment gate; not independent full-pipeline confirmation',
    'repeatable_preferences':'At least one parent with keep minus switch >=2pp at both distinct 8k states, and another with switch minus keep >=2pp, using entire O100 at 28k suffix.',
    'heldout_information_gain':'LOPO rule mean must be positive against both always_keep and always_switch',
    'robustness':'Both gains remain positive under full parent-removal refitting',
    'constant_rule_result':'If always-switch is sufficient, report a fixed-switch schedule; do not claim state information value'}
s=p['stage3'];s['arms']={
    'fixed_keep_40k':{'common_training':8000,'fixed_training':32000,'diagnostic':0},
    'fixed_switch_40k':{'common_training':8000,'switched_training':32000,'diagnostic':0},
    'diagnostic_rule':{'common_training':8000,'diagnostic':4000,'selected_training':28000},
    'diagnostic_always_keep':{'common_training':8000,'diagnostic':4000,'fixed_training':28000},
    'diagnostic_always_switch':{'common_training':8000,'diagnostic':4000,'switched_training':28000}}
s['primary_effects']=['diagnostic_rule minus fixed_keep_40k','diagnostic_rule minus fixed_switch_40k']
s['information_effects']=['diagnostic_rule minus diagnostic_always_keep','diagnostic_rule minus diagnostic_always_switch']
s['diagnostic_opportunity_costs']=['diagnostic_always_keep minus fixed_keep_40k','diagnostic_always_switch minus fixed_switch_40k']
for key in ('primary_effect','information_effect','diagnostic_opportunity_cost'):s.pop(key,None)
s['scientific_success']='Predeclared practical effect and uncertainty criteria on both information comparisons and both full-budget fixed comparisons, on fresh parents. Do not select the weaker control after seeing fresh results.'
s['sharing']={
    'physical_training_per_parent_continuation':72000,
    'physical_diagnostic_per_parent_continuation':4000,
    'physical_operational_total_per_parent_continuation':76000,
    'logical_budget_per_method':40000,
    'logical_methods':5,
    'distinct_terminal_policies_per_parent_continuation':4,
    'outcome_evaluation_steps_upper_per_parent_continuation':800000,
    'parent_pretraining_steps':200000,
    'parent_outcome_steps_upper':200000,
    'conditions':['diagnostic leaves all learner/optimizer/replay/collector/RNG state unchanged','learner update rule does not depend on the chosen terminal horizon','both action futures begin from the exact same full 8k state','adaptive action and rule/source/diagnostic hashes are committed before either future is trained or any terminal score is inspected','selected 36k policy and common outcome bank are identical to the corresponding constant-action arm'],
    'execution':'Run common F*8k, pay D4k once, record adaptive choice, restore same 8k state for F*32k and A*32k; save suffix28k and suffix32k on both futures. Reuse corresponding 36k score for adaptive arm.',
    'budget_formula':'For N fresh parents and R continuation states per parent: 200000*N + 76000*N*R operational/research training+diagnosis, plus at most 200000*N + 800000*N*R research outcome steps.',
    'interpretation':'Counterfactual outcome sharing is valid only after the decision is committed; five logical arms are not five independent policy samples.'}
s['pending_before_execution']=['freeze fresh parent labels and sample size from stage2 variability and target precision','freeze practical-effect and family-of-four uncertainty procedure before new-parent outcomes','validate horizon independence, checkpoint reuse, diagnosis isolation and decision-before-futures integrity']
with (HERE/'protocol.json').open('x',encoding='utf-8') as f:json.dump(p,f,indent=2,ensure_ascii=False);f.write('\n')
target=HERE.parent/'44_selection_value_stage1_checkpoint36_v2/configs/research_protocol.json'
target.write_text(json.dumps(p,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(str(HERE/'protocol.json'))
