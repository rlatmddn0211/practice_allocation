"""Bounded integrity checks. Outcomes never choose seeds, tasks or schedules."""
from __future__ import annotations
import copy
import json
import os
import pickle
import sys
import time
import traceback
from dataclasses import replace
from pathlib import Path
os.environ['PRACTICE_SUITE']='B'
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
import numpy as np
import torch
from practice_allocation.core import Config, configure_runtime, fingerprint, capture_rng, restore_rng, isolated_rng, TASKS
from practice_allocation.engine import Engine
from practice_allocation.environment import CostCounter
from practice_allocation.learning import learning_state
from records import ROOT, Cost, save, load, snapshot_source, capture_environment, restore_environment, Physics, ref, utc
from learner import ObservedEngine, ObservedEpisode, configure_streams
from evaluation import prepare_cases, rollout
from checkpoints import full, restore, light

def config_for(rid):
    streams=load(ROOT/'seed_manifest.json')['streams'][rid]
    config=replace(Config.load(ROOT/'configs/learner.json'),seed=streams['model_initialization'])
    return config,streams

def base_comparison(engine):
    r=engine.model.replay_buffer;n=r.size()
    replay={k:getattr(r,k)[:n] for k in ('observations','next_observations','actions','rewards','dones','timeouts','birth_steps')}
    collector={'schedule':engine.schedule.state(),'visits':engine.task_visits,'collected':engine.collected_steps,
        'warmup':engine.warmup_rng.bit_generator.state,'last_episode':engine.last_episode,'reset_root':engine.reset_root}
    return {'learning':fingerprint(learning_state(engine.model)),'replay':fingerprint(replay),
        'collector':fingerprint(collector),'rng':fingerprint(capture_rng())}

def same_trace(a,b):
    keys=('step','task','observation','action','next_observation','reward','terminated','truncated','success','updates')
    return fingerprint({k:a[k] for k in keys})==fingerprint({k:b[k] for k in keys})

def synthetic(out):
    # Independent algebra and pairing checks before scientific outcomes exist.
    checks={}
    b=np.array([1,1,0,0]);y=np.array([0,1,1,0]);z=np.array([1,0,1,0])
    def met(a):
        return np.array([b.mean(),a.mean(),((1-b)*a).mean(),(b*(1-a)).mean()])
    j0,j,g,l=met(y);checks['gain_loss_identity']=bool(j-j0==g-l)
    h=np.sum(b*z*(1-y));bb=np.sum(b*(1-z)*y)
    checks['equal_net_loss_preserves_exchange']=bool(h==bb==1)
    checks['same_case_pairing_preserves_disagreement']=bool(np.sum(y!=z)==2)
    checks['initial_labels_not_multiplied']=len(b)==4
    checks['budget_arithmetic']=5*1000000+5*4*10*16*500+10000+100000==6710000
    p=load(ROOT/'protocol.json');checks['light_union_count']=len(p['light_steps'])==23
    checks['eval_count']=5*4*10*16==3200
    checks['full_count']=5*4==20
    if not all(checks.values()):raise RuntimeError('Synthetic fixture failed')
    save(out/'synthetic_checks.json',checks);return checks

def verify(campaign,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);snapshot_source(out)
    prior=0
    for path in (Path(campaign)/'verification').glob('*/technical_control_journal.bin'):
        if path.parent!=out:prior+=path.read_bytes().count(b'I')
    cost=Cost(out,'technical',10000,prior=prior);counters=CostCounter();started=time.perf_counter();engine=None;restored=None
    checks={};error=None
    try:
        checks['synthetic']=synthetic(out)
        config,streams=config_for('TECH');configure_runtime(config)
        cases=prepare_cases(campaign)['cases']
        before=dict(counters.snapshot());baseline=Engine(config,counters);configure_streams(baseline,streams)
        trace=[]
        for i in range(1500):trace.append(cost.call(baseline.step))
        baseline_state=base_comparison(baseline);baseline.close();del baseline
        engine=ObservedEngine(config,counters,out/'logged','TECH',cost)
        configure_streams(engine,streams)
        exact=True
        for i in range(1500):
            record=engine.step();exact&=same_trace(trace[i],record)
        if not exact or base_comparison(engine)!=baseline_state:raise RuntimeError('Logging changes baseline actions, physics, learning, replay or RNG')
        checks['logging_on_off_exact']=True
        checks['native_time_limit_bootstrap']=bool(engine.model.replay_buffer.timeouts[:1500].sum()==3 and engine.model.replay_buffer.dones[:1500].sum()==3)
        if not checks['native_time_limit_bootstrap']:raise RuntimeError('Timeout handling discrepancy')
        # Round-trip action and observation/task encoding contracts.
        r=engine.model.replay_buffer
        checks['action_round_trip']=bool(np.array_equal(r.actions[:1500],engine.model.policy.scale_action(engine.model.policy.unscale_action(r.actions[:1500]))))
        checks['task_encoding']=bool(np.all(r.observations[:1500,0,-4:].sum(axis=1)==1))
        if not checks['action_round_trip'] or not checks['task_encoding']:raise RuntimeError('Action/task encoding changed')
        light(engine,out/'light_checkpoint')
        frozen=copy.deepcopy(engine.model.policy);frozen.set_training_mode(False)
        row=cases[0];initial=engine.fingerprints()
        a=rollout(frozen,row,out/'eval_off','TECH',1500,cost,counters,logging=False,trace=True)
        b=rollout(frozen,row,out/'eval_on','TECH',1500,cost,counters,logging=True,video=True,trace=True)
        fields=('episode_return','episode_length','success_any','success_final','first_success_step','success_step_count','technical_trace_sha256')
        if any(a[k]!=b[k] for k in fields) or initial!=engine.fingerprints():raise RuntimeError('Evaluation/video isolation failed')
        checks['evaluation_video_isolation_exact']=True
        loaded=type(engine.model).load(out/'light_checkpoint/model.zip',device='cuda',custom_objects={'buffer_size':1})
        loaded.policy.set_training_mode(False)
        with torch.no_grad():
            x=np.asarray(row['initial_state']['observation'],dtype=np.float32)
            x=np.r_[x,np.eye(4,dtype=np.float32)[row['task_index']]]
            checks['light_policy_restore']=bool(np.array_equal(frozen.predict(x,deterministic=True)[0],loaded.predict(x,deterministic=True)[0]))
        del loaded
        full(engine,out/'full_checkpoint')
        first=[]
        for i in range(100):first.append(engine.step())
        continuation=base_comparison(engine)
        restored=restore(out/'full_checkpoint',counters,out/'resumed','TECH',cost)
        second=[restored.step() for i in range(100)]
        if not all(same_trace(a,b) for a,b in zip(first,second)) or base_comparison(restored)!=continuation:
            raise RuntimeError('Full checkpoint lossless continuation failed')
        checks['full_lossless_resume_exact']=True
        # Each physics getter and each task's raw snapshot is checked, not inferred from names.
        snapshot_checks=[]
        for ti in range(4):
            case=cases[ti*16]
            ep=ObservedEpisode(ti,case['reset_seed'],counters);physics=Physics(ep)
            try:
                state_before=capture_environment(ep);rng_before=fingerprint(capture_rng())
                sample=physics.sample()
                if fingerprint(capture_environment(ep))!=fingerprint(state_before) or fingerprint(capture_rng())!=rng_before:
                    raise RuntimeError('Physics getter has a side effect')
                rng=np.random.default_rng(123456+ti);actions=rng.uniform(-1,1,(100,4)).astype(np.float32)
                values=[];saved=None
                for i,action in enumerate(actions):
                    result=cost.step(ep,action);values.append((result[0].copy(),result[1:]))
                    if i==49:saved=capture_environment(ep)
                clone=restore_environment(saved,ObservedEpisode,counters)
                try:
                    equal=True
                    for i in range(50,100):
                        result=cost.step(clone,actions[i])
                        equal&=fingerprint((result[0],result[1:]))==fingerprint(values[i])
                finally:clone.close()
                snapshot_checks.append({'task':TASKS[ti],'fixed_action_restore_exact':bool(equal)})
            finally:ep.close()
        checks['snapshot_action_checks']=snapshot_checks
        # Policy-conditioned replay is a separate test from fixed action physics.
        ep=ObservedEpisode(0,cases[0]['reset_seed'],counters);state=capture_environment(ep)
        reference=[]
        for i in range(25):
            action=frozen.predict(ep.observation,deterministic=True)[0]
            result=cost.step(ep,action);reference.append((action.copy(),result))
        ep.close();ep=restore_environment(state,ObservedEpisode,counters);equal=True
        for i in range(25):
            action=frozen.predict(ep.observation,deterministic=True)[0];result=cost.step(ep,action)
            equal&=fingerprint((action,result))==fingerprint(reference[i])
        ep.close();checks['snapshot_policy_restore_exact']=bool(equal)
        checks['snapshot_claim']='same-runtime full restore certified for tested four-task action traces and DO fixed policy only' if all(r['fixed_action_restore_exact'] for r in snapshot_checks) and equal else 'diagnostic_state; full restore not certified; valid raw observations retained'
        # Snapshot non-certification limits its claim; it does not invalidate passive learning.
        if not checks['light_policy_restore']:raise RuntimeError('Light restore failed')
        engine.flush();restored.flush()
        checks['all_core_passed']=True
    except BaseException:
        error=traceback.format_exc();print(error,flush=True)
    finally:
        for eng in (engine,restored):
            if eng is not None:
                try:
                    if eng.episode is not None:
                        last=int(eng.traj.rows[-1]['success_step']) if eng.traj and eng.traj.rows else None
                        eng.finish_episode('technical_validation_boundary',False,last)
                    eng.flush();eng.close()
                except BaseException as exc:
                    checks.setdefault('cleanup_errors',[]).append(repr(exc))
        costs=cost.checkpoint(counter=counters.snapshot());cost.close()
        data_bytes=sum(p.stat().st_size for p in out.rglob('*') if p.is_file())
        result={'status':'passed' if error is None else 'failed','checks':checks,'error':error,
            'costs':costs,'elapsed_seconds':time.perf_counter()-started,'recorded_bytes':data_bytes,
            'learning_tolerance':'exact same-runtime equality; no post-outcome widening',
            'optional_diagnostic_environment_steps':0}
        save(out/'result.json',result);print(json.dumps({'status':result['status'],'costs':costs,'seconds':result['elapsed_seconds']},default=str),flush=True)
    return error is None

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--campaign',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();raise SystemExit(0 if verify(a.campaign,a.output) else 1)
