"""Prepared -> bounded certification -> five fixed runs -> file-only analysis."""
from __future__ import annotations
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
import uuid
from pathlib import Path
from datetime import datetime, timezone
os.environ['PRACTICE_SUITE']='B'
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
from records import ROOT, Cost, Table, save, load, ref, append, snapshot_source, check_source, utc

def worker(campaign,rid):
    from practice_allocation.core import configure_runtime, package_versions
    from practice_allocation.environment import CostCounter
    from learner import ObservedEngine, configure_streams
    from technical import config_for
    from checkpoints import light, full
    from evaluation import evaluate
    campaign=Path(campaign);out=campaign/'runs'/rid
    out.mkdir(parents=True,exist_ok=False)
    sources=snapshot_source(out);check_source(load(campaign/'source_hashes.json'))
    protocol=load(ROOT/'protocol.json');config,streams=config_for(rid);configure_runtime(config)
    save(out/'runtime.json',{'run_id':rid,'pid':os.getpid(),'started_at':utc(),'config':config.to_dict(),
        'streams':streams,'packages':package_versions(),'fresh_initialization':True,'parent_checkpoint':None,
        'parallel_jobs_planned':protocol['parallel_workers']})
    train=Cost(out/'costs','train',1000000);evaluation=Cost(out/'costs','evaluation',320000)
    counters=CostCounter();engine=None;started=time.perf_counter();error=None;eval_done=[];lights=[];fulls=[]
    def status(stage,**extra):
        step=engine.model.num_timesteps if engine else 0
        row={'run_id':rid,'stage':stage,'time':utc(),'pid':os.getpid(),'train_transitions':step,
            'actor_updates':engine.model._n_updates if engine else 0,'eval_checkpoints_completed':eval_done,
            'light_completed':lights,'full_completed':fulls,'elapsed_seconds':time.perf_counter()-started,
            'train_cost':train.completed,'evaluation_cost':evaluation.completed,**extra}
        save(out/'status.json',row,replace=True);append(out/'progress.jsonl',row)
        train.checkpoint(counter=counters.snapshot());evaluation.checkpoint()
        print(json.dumps(row,ensure_ascii=False),flush=True)
    try:
        engine=ObservedEngine(config,counters,out,rid,train);configure_streams(engine,streams)
        cases=load(campaign/'evaluation_cases/manifest.json')['cases']
        milestones=sorted(set(protocol['light_steps'])|set(protocol['evaluation_steps'])|set(protocol['full_steps']))
        for target in milestones:
            status('training',target=target)
            while engine.model.num_timesteps<target:
                engine.step()
                if engine.model.num_timesteps%5000==0:
                    engine.flush();status('training',target=target)
            if not engine.at_boundary:raise RuntimeError('Planned barrier is not an episode boundary')
            engine.flush();check_source(sources)
            if shutil.disk_usage(out).free<5000000000:raise RuntimeError('Less than 5GB free; no logs silently discarded')
            if target in protocol['light_steps']:
                status('saving_light');light(engine,out/'checkpoints/light'/f'{target:07d}');lights.append(target)
            if target in protocol['full_steps']:
                status('saving_full');full(engine,out/'checkpoints/full'/f'{target:07d}');fulls.append(target)
            if target in protocol['evaluation_steps']:
                status('evaluating');evaluate(engine,cases,out,target,evaluation);eval_done.append(target)
                status('evaluation_complete')
        active=Table(out/'replay_usage/final_active')
        r=engine.model.replay_buffer
        for i in range(r.size()):active.add(r.usage_row(i))
        active.flush();engine.flush()
        if train.completed!=1000000 or evaluation.completed!=320000:raise RuntimeError('Normal transition count mismatch')
        if engine.collected_steps.tolist()!=[250000]*4:raise RuntimeError('Original uniform quotas not preserved')
        if r.sampled_total!=999000*256:raise RuntimeError('Replay sample count mismatch')
        check_source(sources)
        save(out/'COMPLETE.json',{'run_id':rid,'completed_at':utc(),'train_transitions':train.completed,
            'evaluation_transitions':evaluation.completed,'evaluation_episodes':640,
            'evaluation_checkpoints':eval_done,'light_checkpoints':lights,'full_checkpoints':fulls,
            'actor_updates':engine.model._n_updates,'collected_by_task':dict(zip(('DO','DC','PU','BP'),engine.collected_steps.tolist())),
            'replay_sampled_total':r.sampled_total,'sampled_by_task':dict(zip(('DO','DC','PU','BP'),r.sampled_task_counts.tolist())),
            'runtime_seconds':time.perf_counter()-started,'checkpoint_parent':None,'source_hashes':ref(out/'source_hashes.json')})
        status('complete')
    except BaseException:
        error=traceback.format_exc();save(out/'FAILED.json',{'time':utc(),'error':error,
            'train':train.checkpoint(),'evaluation':evaluation.checkpoint()});print(error,flush=True)
        status('failed',error=error)
    finally:
        if engine is not None:
            try:
                if engine.episode is not None:
                    last=int(engine.traj.rows[-1]['success_step']) if engine.traj and engine.traj.rows else None
                    engine.finish_episode('technical_error' if error else 'campaign_budget',False,last)
                engine.flush();engine.close()
            except BaseException as exc:append(out/'cleanup_errors.jsonl',{'error':repr(exc),'time':utc()})
        train.close();evaluation.close()
    return 0 if error is None else 1

def new_campaign():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    path=ROOT/'results'/(stamp+'_observation_'+uuid.uuid4().hex[:8]);path.mkdir(parents=True,exist_ok=False)
    snapshot_source(path)
    for name in ('protocol.json','baseline_manifest.json','config_resolved.json','seed_manifest.json','input_receipt.json'):
        shutil.copy2(ROOT/name,path/name)
    save(ROOT/'ACTIVE_CAMPAIGN.json',{'campaign':str(path),'created_at':utc()},replace=False)
    (path/'diagnostic_plan.jsonl').touch(exist_ok=False)
    save(path/'status.json',{'stage':'prepared','created_at':utc(),'main_runs_completed':0,'environment_steps':0})
    save(path/'schema/transition_schema.json',{'schema_version':1,
        'layout':'episode-level immutable metadata JSON + per-transition numeric NPZ arrays; join by trajectory basename',
        'metadata_fields':['experiment_id','run_id','attempt_id','task_id','split_role','env_instance_id','episode_id','initial_case_id','checkpoint_id'],
        'array_fields':['transition_id','episode_step','env_step_total','actor_update_count','critic_update_count','policy_version',
            'obs_policy','obs_raw','action_executed','reward','next_obs_actual','next_obs_raw_actual','success_step','terminated','truncated','validity_status'],
        'time':'obs/action before raw step; next/reward/success/termination after step; physical features at returned control-step endpoint',
        'episode_step_start':1,'autoreset':'none; native final observation returned directly; reset is separate',
        'precision':{'obs_raw':'float64 original returned observation, including original environment clipping',
            'obs_policy':'float32 original learner input plus one-hot','physics':'original float64; no quantization',
            'action_executed':'float32 original normalized action','reward':'float64 returned scalar'},
        'action_source':{'0':'original uniform warm-up','1':'original stochastic SAC collection','2':'original deterministic evaluation'},
        'policy_distribution':'stored mean and log_std are pre-tanh; warm-up unavailable represented by NaN with action_source=0',
        'action_pre_transform':'collection action before original project scale/unscale round trip; same [-1,1] coordinates here',
        'sampled_action_log_prob':'unavailable in original collection predict path; no extra policy sampling to manufacture it',
        'success_flag':'noncumulative official task evaluate_state result at this returned state; episode success_any is separately accumulated',
        'bootstrap':'1-terminated; time-limit truncation handled by original SB3 timeout mask, never silently merged',
        'contacts':'ragged numerical rows [geom1,geom2,distance_m], addressed by contact_offsets; control endpoints only',
        'unavailable_joint':'Push free-object state retained in qpos/qvel; scalar manipulation joint is NaN and explicitly unavailable',
        'evaluation_data_use':'observation only; never training replay, calibration, task selection or policy inputs beyond normal eval'})
    return path

def summarize_costs(campaign):
    campaign=Path(campaign);result={'train':0,'evaluation':0,'technical_invalid_retry':0,'optional_diagnostic':0,'uncertain_issued':0}
    for p in campaign.rglob('*_control_journal.bin'):
        data=p.read_bytes();issued=data.count(b'I');complete=data.count(b'C')
        result['uncertain_issued']+=issued-complete
        category=p.name.split('_control_journal')[0]
        key='technical_invalid_retry' if category=='technical' else category
        result[key]=result.get(key,0)+issued
    result['all_attempt']=sum(result[k] for k in ('train','evaluation','technical_invalid_retry','optional_diagnostic'))
    result['control_steps_unit']='actual single-environment action transitions; unmatched issued attempts charged conservatively'
    return result

def campaign_run(campaign):
    campaign=Path(campaign);python=sys.executable;active={};pending=list(load(ROOT/'protocol.json')['runs']);failed=[];started=time.perf_counter()
    frozen=load(campaign/'source_hashes.json');check_source(frozen)
    verify_dir=campaign/'verification'/('v_'+datetime.now(timezone.utc).strftime('%H%M%S')+'_'+uuid.uuid4().hex[:6])
    verify_dir.parent.mkdir(parents=True,exist_ok=True)
    with (campaign/'technical_stdout.log').open('x',encoding='utf-8') as stream:
        code=subprocess.call([python,'-B',str(ROOT/'technical.py'),'--campaign',str(campaign),'--output',str(verify_dir)],stdout=stream,stderr=subprocess.STDOUT,cwd=ROOT.parent)
    if code:
        result=load(verify_dir/'result.json') if (verify_dir/'result.json').exists() else {'error':'Technical process failed before result'}
        save(campaign/'TECHNICAL_FAILED.json',result)
        from analysis import analyze
        analyze(campaign,partial=True)
        return 1
    receipt=load(verify_dir/'result.json')
    save(campaign/'technical_certification.json',{'receipt':ref(verify_dir/'result.json'),'snapshot_claim':receipt['checks']['snapshot_claim'],
        'core_passed':True,'actual_technical_environment_steps':summarize_costs(campaign)['technical_invalid_retry']})
    # Source remained fixed through certification; outcomes cannot change it.
    check_source(frozen)
    while pending or active:
        while pending and len(active)<2:
            rid=pending.pop(0);log=(campaign/(rid+'_stdout.log')).open('x',encoding='utf-8')
            p=subprocess.Popen([python,'-B',str(ROOT/'campaign.py'),'worker','--campaign',str(campaign),'--run',rid],
                cwd=ROOT.parent,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            active[rid]=(p,log)
        for rid,(p,log) in list(active.items()):
            if p.poll() is not None:
                log.close();del active[rid]
                if p.returncode!=0:failed.append(rid);pending=[]
        completed=[r for r in load(ROOT/'protocol.json')['runs'] if (campaign/'runs'/r/'COMPLETE.json').exists()]
        costs=summarize_costs(campaign)
        status={'time':utc(),'stage':'learning_evaluation' if active else 'analysis','active_runs':list(active),
            'pending_runs':pending,'completed_runs':completed,'failed_runs':failed,'costs':costs,'wall_seconds':time.perf_counter()-started}
        save(campaign/'status.json',status,replace=True)
        text='# 81번 기본 SAC 관측 캠페인\n\n'+f"시각: {status['time']}\n\n단계: {status['stage']}\n\n완료 실행: {len(completed)}/5\n\n진행: {', '.join(active)}\n\n실제/보수적 계상 전이: {costs['all_attempt']:,}/6,710,000\n"
        tmp=campaign/'RUNNING_STATUS.md.partial';tmp.write_text(text,encoding='utf-8');os.replace(tmp,campaign/'RUNNING_STATUS.md')
        if active:time.sleep(15)
    from analysis import analyze
    analyze(campaign,partial=bool(failed) or len(completed)!=5)
    return 1 if failed else 0

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','campaign','worker','analyze']);p.add_argument('--campaign',type=Path);p.add_argument('--run')
    a=p.parse_args()
    if a.mode=='prepare':print(new_campaign());return 0
    if a.mode=='worker':return worker(a.campaign,a.run)
    if a.mode=='analyze':
        from analysis import analyze
        analyze(a.campaign,partial=True);return 0
    return campaign_run(a.campaign)

if __name__=='__main__':raise SystemExit(main())
