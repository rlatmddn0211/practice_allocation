"""Atomic, exact baseline-format full checkpoints and analysis-only light saves."""
from __future__ import annotations
import os
import pickle
import time
from pathlib import Path
from practice_allocation.core import Config, capture_rng, restore_rng, fingerprint, package_versions, source_hashes
from practice_allocation.engine import save_checkpoint
from practice_allocation.learning import attach_logger
from learner import ObservationSAC, ObservedEngine
from records import save, load, ref, Table, sha

def light(engine,path):
    path=Path(path);path.mkdir(parents=True,exist_ok=False)
    tmp=path/'model.partial.zip';engine.model.save(tmp);os.replace(tmp,path/'model.zip')
    save(path/'manifest.json',{'kind':'light_analysis_only','model':ref(path/'model.zip'),
        'env_step_total':engine.model.num_timesteps,'actor_update_count':engine.model._n_updates,
        'normalization':'none','replay_included':False,'complete_training_resume':False,
        'parameters':'actor, critics, target, alpha, model configuration; SB3 archive also preserves optimizer entries',
        'policy_internal_state':'feedforward; no hidden state or action queue'})

def full(engine,path):
    path=Path(path);tmp=path.with_name(path.name+'.partial')
    if path.exists() or tmp.exists():raise FileExistsError(path)
    engine.flush();started=time.perf_counter()
    # The original, already validated model.zip/replay.pkl/collector_and_rng.pkl format.
    save_checkpoint(engine,tmp)
    usage=Table(tmp/'active_replay_usage')
    r=engine.model.replay_buffer
    for i in range(r.size()):usage.add(r.usage_row(i))
    usage.flush()
    save(tmp/'COMPLETE.json',{'kind':'full_boundary_checkpoint','environment_active':False,
        'boundary':'native completed 500-step episode, SAC update completed, before next reset',
        'required_state':'model/optimizers/alpha/replay/slot metadata/schedule/collector/RNG from same barrier',
        'seconds':time.perf_counter()-started,'checkpoint_manifest_sha256':sha(tmp/'checkpoint_manifest.json')})
    path.parent.mkdir(parents=True,exist_ok=True);os.replace(tmp,path)

def restore(path,counters,out,run_id,cost,logging=True):
    path=Path(path)
    if not (path/'COMPLETE.json').exists():raise RuntimeError('Incomplete full checkpoint')
    manifest=load(path/'checkpoint_manifest.json')
    if manifest['packages']!=package_versions() or manifest['source_hashes']!=source_hashes():raise RuntimeError('Checkpoint dependency/source changed')
    for name,digest in manifest['files'].items():
        if sha(path/name)!=digest:raise RuntimeError('Checkpoint integrity failure: '+name)
    with (path/'collector_and_rng.pkl').open('rb') as f:state=pickle.load(f)
    config=Config(**state['config']);config.validate()
    model=ObservationSAC.load(path/'model.zip',device=config.device)
    model.load_replay_buffer(path/'replay.pkl');attach_logger(model)
    engine=ObservedEngine(config,counters,out,run_id,cost,model=model,logging=logging)
    engine.restore_boundary_state(state['collector']);restore_rng(state['rng'])
    if engine.fingerprints()!=manifest['state_fingerprints']:raise RuntimeError('Full training-state restoration differs')
    return engine
