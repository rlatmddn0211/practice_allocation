"""Readable Korean report template and table formatting, without runtime imports."""
from common import *


def render_report(d,v,table,types):
    def t(name,rename=None,scale=None,digits=3):return table(v[name],rename,scale,digits)
    values={
      'UTC':utc(),'ORIGINAL':str(ORIGINAL),'CAMPAIGN':str(CAMPAIGN),'ANALYSIS':str(ANALYSIS),'CORE':str(d.core),'INITSEEDS':v['initseeds'],
      'TEN':t('ten',{'parent_id':'부모','future_id':'미래','initial_success':'시작성공','B_final_successes':'B최종','U_final_successes':'U최종','P_final_successes':'P최종','P-U_delta_auc_pp':'P-U AUC','P-B_delta_auc_pp':'P-B AUC','P-U_final_delta_J_pp':'P-U최종','P-B_final_delta_J_pp':'P-B최종'}),
      'PARENT':table(d.parent_summary,{'parent_id':'부모'},{'P-U':100,'P-B':100,'U-B':100}),
      'TIMING':t('timing',{'contrast':'대비','delta_J_16000':'+16k','delta_J_32000':'+32k','delta_J_64000':'+64k'},{'delta_J_16000':100,'delta_J_32000':100,'delta_J_64000':100}),
      'UNCERTAINTY':t('uncertainties',{'contrast':'대비','metric':'지표','estimate':'차이%p','lower':'하한','upper':'상한'},{'estimate':100,'lower':100,'upper':100}),
      'RISK':t('initialrisk',{'arm':'조건','all_four_success':'초기성공:1111','loss_then_final_recovery':'초기성공:상실후최종회복','final_loss':'초기성공:최종실패','initial_failure_final_success':'초기실패:최종성공','initial_failure_acquired_final_failed':'초기실패:획득후최종실패','never_observed_success':'초기실패:계속실패'},digits=0),
      'EVENT':t('event',{'arm':'조건','gain_events':'획득사건','loss_events':'상실사건','recovery_events':'회복사건'},digits=0),
      'ACQUISITION':table(d.acq,{'arm':'조건','first_success_train_step':'최초획득step','subsequent_evaluation_opportunities':'남은평가기회','histories':'이력수','final_successes':'최종성공','histories_with_later_loss':'획득후상실이력','recovery_events':'회복사건'},digits=0),
      'PHYSICAL':table(v['method_only'][['contrast','case_type','N','axis_error_difference_m','TCP_distance_difference_m','endpoint_contact_fraction_difference']].replace({'case_type':types}),
        {'contrast':'대비','case_type':'최종유형','N':'건수','axis_error_difference_m':'최소축오차차mm','TCP_distance_difference_m':'최소TCP거리차mm','endpoint_contact_fraction_difference':'접촉step비중차%p'},
        {'axis_error_difference_m':1000,'TCP_distance_difference_m':1000,'endpoint_contact_fraction_difference':100},2),
      'REPRESENTATIVE':table(v['representative'].replace({'case_type':types}),{'contrast':'대비','case_type':'유형','parent_id':'부모','future_id':'미래','initial_case_id':'사례','method_pattern':'P이력','reference_pattern':'대조이력'},digits=0),
      'FINAL_PHYSICAL':table(d.final_physical,{'arm':'조건','episodes':'에피소드수','success_any_count':'한번이상성공','conditional_first_success_step_median':'성공시최초도달중앙step','success_occupancy_mean':'전체성공step비중%','episode_end_success_count':'종료시성공'},
        {'success_occupancy_mean':100}),
      'TRIAD':table(d.recovery_physical[['arm','relative_train_step','first_success_step','minimum_button_axis_error_m','minimum_TCP_button_distance_m','contact_endpoint_samples','success_occupancy','episode_end_success']],
        {'arm':'조건','relative_train_step':'추가학습step','first_success_step':'첫성공action','minimum_button_axis_error_m':'최소목표축오차mm','minimum_TCP_button_distance_m':'최소TCP거리mm','contact_endpoint_samples':'접촉step/500','success_occupancy':'성공step비중%','episode_end_success':'종료시성공'},
        {'minimum_button_axis_error_m':1000,'minimum_TCP_button_distance_m':1000,'success_occupancy':100}),
      'CONTENT':t('content',{'arm':'창','net_opening_m':'순개방mm','opening_path_m':'개방path mm','closing_path_m':'닫힘path mm','mean_goal_distance_pre_m':'목표거리mm','mean_goal_axis_command':'DO목표축명령','mean_gripper_command':'gripper명령','mean_TCP_handle_pre_m':'TCP-손잡이mm','mean_reward':'reward/전이','contact_endpoint_steps':'접촉step/32'},
        {'net_opening_m':1000,'opening_path_m':1000,'closing_path_m':1000,'mean_goal_distance_pre_m':1000,'mean_TCP_handle_pre_m':1000}),
      'POST':t('post',{'arm':'창','episodes':'에피소드','mean_post_drawdown_m':'끝기준평균되돌림mm','max_post_drawdown_m':'최대되돌림mm','mean_additional_opening_m':'이후평균추가개방mm'},
        {'mean_post_drawdown_m':1000,'max_post_drawdown_m':1000,'mean_additional_opening_m':1000}),
      'DONOR':table(d.source_summary,{'donor_run':'출처','eligible_episodes':'적격수','positive_net_windows':'P순개방양수','full_gain_reversal_before_sigma':'P완전되돌림','mean_net_opening_m':'평균순개방mm','mean_post_drawdown_m':'평균되돌림mm'},
        {'mean_net_opening_m':1000,'mean_post_drawdown_m':1000}),
      'USES':table(d.uses,{'arm':'조건','interval_start':'시작','interval_end':'끝','total_uses':'10분기실제사용합','mean_uses_per_update':'update당평균','mean_repeat_draw_fraction':'반복draw비율','minimum_unique_episodes':'최소episode수','maximum_unique_episodes':'최대episode수'},digits=4),
      'EXPOSURE':t('exposure',{'arm':'조건','goal_distance_pre_m':'목표거리mm','opening_positive_m':'개방방향mm/draw','closing_positive_m':'닫힘방향mm/draw','goal_axis_command':'DO목표축명령','gripper_command':'gripper명령','reward':'reward','contact_endpoint':'접촉step%','TCP_handle_distance_pre_m':'TCP-손잡이mm'},
        {'goal_distance_pre_m':1000,'opening_positive_m':1000,'closing_positive_m':1000,'contact_endpoint':100,'TCP_handle_distance_pre_m':1000}),
      'LINKAGE':t('linkage',{'parent_id':'부모','BP_delta_AUC0_to_end':'BP AUC차','BP_delta_J_end':'BP최종차','cumulative_delta_opening_positive_m':'개방노출차mm/draw','cumulative_delta_closing_positive_m':'닫힘노출차mm/draw','cumulative_delta_goal_axis_command':'목표축명령차','cumulative_delta_gripper_command':'gripper차','cumulative_delta_contact_endpoint':'접촉비중차%p'},
        {'BP_delta_AUC0_to_end':100,'BP_delta_J_end':100,'cumulative_delta_opening_positive_m':1000,'cumulative_delta_closing_positive_m':1000,'cumulative_delta_contact_endpoint':100},4),
      'TRADEOFF':t('trade',{'scope':'과제/동일비중평균'},{'P-U':100,'P-B':100,'U-B':100}),
      'FIGURES':v['figure_text']}
    result=d.inputs.text(HERE/'report_template_ko.md','readable Korean report template')
    for key,value in values.items():result=result.replace('@@'+key+'@@',value)
    d.checks.add('all report template fields resolved','@@' not in result)
    return result
