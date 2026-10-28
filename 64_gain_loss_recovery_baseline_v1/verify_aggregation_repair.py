"""Finish the retained technical gate after a return-only empty-task aggregation fix.

This is not a replay of the training experiments. Prior exact train/resume traces
are reused only after proving byte equality of every executed source except the
single final summary expression, which never feeds the learner or evaluation.
"""
import argparse
import json
import time
import traceback
from pathlib import Path
from common import (ROOT,TECH_CAP,unique,reference,checked,frozen_inputs,config_for,load_state,
                    case_bank,read_csv,close_engine,verify_input_files)
from baseline_evaluation import evaluate
from practice_allocation.core import configure_runtime,source_hashes,write_json,file_sha256,utc_now
from practice_allocation.environment import CostCounter
from practice_allocation.study_io import IntegrityError,source_snapshot,read_json

OLD="'success_by_task':{t:sum(r['success'] for r in rows if r['task']==t)/sum(r['task']==t for r in rows) for t in TASKS}}"
NEW="'success_by_task':{t:(sum(r['success'] for r in rows if r['task']==t)/sum(r['task']==t for r in rows)\n                                  if any(r['task']==t for r in rows) else None) for t in TASKS}}"

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--prior',required=True);args=ap.parse_args()
    prior=Path(args.prior).resolve()
    out=unique(ROOT/'results','technical_repair');source_snapshot(out)
    checks=[];costs=CostCounter();engine=None;error=None;start=time.perf_counter()
    previous=sum(read_json(path)['costs']['environment_steps'] for path in (ROOT/'results').glob('*_technical_*/costs.json'))
    start_sources=source_hashes()

    def check(name,ok,details=None):
        checks.append({'name':name,'passed':bool(ok),'details':details})
        if not ok:raise IntegrityError(name)

    try:
        for source in (out/'source_snapshot').glob('*.py'):
            compile(source.read_text(encoding='utf-8-sig'),str(source),'exec')
        check('repaired_sources_compile',True)
        old=read_json(prior/'summary.json');oldchecks=[json.loads(s) for s in (prior/'checks.jsonl').read_text(encoding='utf-8').splitlines()]
        check('prior_expected_summary_only_failure',old['status']=='failed' and old['error']['type']=='ZeroDivisionError'
              and old['error']['message']=='division by zero' and not old['failed_checks'])
        expected_names={'all_restore_checks_zero_environment_steps','dose25_logging_trace_exact','dose25_logging_full_state_exact',
              'dose25_resume_trace_exact','dose25_resume_full_state_exact','dose625_logging_trace_exact','dose625_logging_full_state_exact',
              'dose625_resume_trace_exact','dose625_resume_full_state_exact','new_futures_not_duplicate',
              'technical_training_cost_exact','known_evaluation_preserves_full_state'}
        check('prior_training_restore_and_rng_certificates_passed',expected_names<={r['name'] for r in oldchecks if r['passed']})
        check('prior_actual_training_cost_6500',old['costs']['train_iterations']==6500)
        original_map=read_json(prior/'source_snapshot_map.json')
        differences=[]
        for relative,entry in original_map.items():
            snapshot=prior/entry['snapshot']
            check('prior_snapshot_hash_'+relative,file_sha256(snapshot)==entry['sha256'])
            current=ROOT/relative
            if file_sha256(current)!=entry['sha256']:
                differences.append(relative)
                check('only_return_aggregation_expression_changed',relative=='baseline_evaluation.py' and
                      OLD in snapshot.read_text(encoding='utf-8') and
                      current.read_text(encoding='utf-8')==snapshot.read_text(encoding='utf-8').replace(OLD,NEW))
        check('exactly_one_existing_source_changed',differences==['baseline_evaluation.py'])
        check('only_repair_verifier_added',set(source_hashes())-set(original_map)=={'verify_aggregation_repair.py'})
        check('repair_fits_remaining_cap',previous+500<=TECH_CAP,{'previous_all_attempts':previous,'maximum_new':500})
        # The formerly failing call had already completed its rollout and written
        # the row. Validate that retained row separately; do not erase the failure.
        retained=read_csv(prior/'known_S_repeat.csv');known=read_csv(prior/'known_S.csv')
        check('retained_repeat_rollout_exact',len(retained)==1 and all(retained[0][k]==known[0][k]
              for k in ('success','length','return','initial_state_hash','seed')))
        p,states,jobs=frozen_inputs();state=states[0]
        configure_runtime(config_for(state));engine=load_state(state,costs)
        before=engine.fingerprints()
        bank=case_bank(state,'E50');case=next(r for r in bank if r['task']==retained[0]['task'] and
                  r['episode_index']==int(retained[0]['episode_index']))
        result=evaluate(engine,[case],costs,out/'known_S_repeat.csv',{'id':'aggregation_repair_known_S',
              'parent':state['parent'],'condition':'STOP','future':0,'relative_step':0},TECH_CAP-previous)
        observed=read_csv(out/'known_S_repeat.csv')[0]
        check('single_case_rollout_unchanged_after_fix',all(observed[k]==retained[0][k]
              for k in ('success','length','return','initial_state_hash','seed')))
        check('unobserved_tasks_are_NA_not_zero',result['success_by_task'][case['task']]==float(observed['success']) and
              all(value is None for task,value in result['success_by_task'].items() if task!=case['task']))
        check('evaluation_preserves_full_state_after_fix',engine.fingerprints()==before)
        check('repair_has_no_training',costs.train_iterations==0)
        for known_state in states:
            verify_input_files(known_state)
        check('all_five_original_inputs_unchanged',True)
        check('source_unchanged_during_repair',source_hashes()==start_sources)
        check('total_all_attempts_within_cap',previous+costs.environment_steps<=TECH_CAP)
        close_engine(engine);engine=None
        write_json(out/'inherited_evidence.json',{'prior_summary':reference(prior/'summary.json'),
             'prior_checks':reference(prior/'checks.jsonl'),'all_forks':reference(prior/'all_forks.json'),
             'prior_source_snapshot_map':reference(prior/'source_snapshot_map.json'),
             'scope':'All unchanged train/restore/RNG/logging/resume code is certified by retained exact prior traces. Only a post-rollout task-summary expression changed; that expression is verified by a fresh isolated exact case.'})
    except BaseException as exc:
        error={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
        write_json(out/'error.json',error);traceback.print_exc()
    finally:
        try:close_engine(engine)
        except BaseException as exc:
            if error is None:error={'type':type(exc).__name__,'message':str(exc)}
        write_json(out/'checks.json',checks)
        write_json(out/'costs.json',{'status':'failed' if error else 'completed','costs':costs.snapshot(),
             'previous_technical_environment_steps':previous,'wall_seconds':time.perf_counter()-start,'scientific_effect_test':False})
        write_json(out/'summary.json',{'status':'failed' if error else 'passed','checks':len(checks),
             'failed_checks':[c for c in checks if not c['passed']],'error':error,'source_hashes':source_hashes(),
             'costs':costs.snapshot(),'inherited_prior_technical_checks':len(oldchecks) if 'oldchecks' in locals() else 0,
             'total_technical_environment_steps_all_attempts':previous+costs.environment_steps})
    if not error:
        write_json(out/'VERIFIED.json',{'summary':reference(out/'summary.json'),
             'panels':reference(prior/'certified_panels.json'),'source_hashes':source_hashes(),
             'inherited_evidence':reference(out/'inherited_evidence.json'),'created_at':utc_now()})
    print(json.dumps({'run':str(out),'passed':error is None,'previous':previous,'costs':costs.snapshot()}),flush=True)
    return 1 if error else 0

if __name__=='__main__':raise SystemExit(main())
