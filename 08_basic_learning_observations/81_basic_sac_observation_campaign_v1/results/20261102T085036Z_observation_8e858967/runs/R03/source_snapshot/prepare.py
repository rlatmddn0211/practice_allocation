"""Prepare an independent observation campaign without resetting an environment."""
from __future__ import annotations
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
BASE = PROJECT / '77_success_reuse_extra_loss_confirmation_v1'

def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as f:
        json.dump(value, f, indent=2, ensure_ascii=False); f.write('\n')

def seed(*parts):
    return int.from_bytes(hashlib.sha256('|'.join(map(str, parts)).encode()).digest()[:4], 'big')

def main():
    sources = []
    for name in ('__init__.py', 'core.py', 'environment.py', 'learning.py', 'engine.py', 'schedules.py'):
        src = BASE / 'practice_allocation' / name
        dst = ROOT / 'practice_allocation' / name
        dst.parent.mkdir(exist_ok=True)
        if not dst.exists(): shutil.copy2(src, dst)
        if sha(src) != sha(dst): raise RuntimeError('Baseline copy differs: ' + name)
        sources.append((src, 'unchanged baseline implementation copy'))
    (ROOT/'configs').mkdir(exist_ok=True)
    suites = BASE/'configs/suites.json'
    if not (ROOT/'configs/suites.json').exists(): shutil.copy2(suites, ROOT/'configs/suites.json')
    config = json.loads((BASE/'configs/learner.json').read_text())
    config.update(version=ROOT.name)
    write(ROOT/'configs/learner.json', config)
    sources += [(BASE/'configs/learner.json', 'actual SAC hyperparameters'),
                (suites, 'actual suite B task mapping'), (PROJECT/'AGENTS.md', 'repository rules'),
                (PROJECT/'02_p0_uniform_pretraining_v1/configs/pretraining.json', 'original initialization/hyperparameter reference'),
                (PROJECT/'02_p0_uniform_pretraining_v1/practice_allocation/pretraining.py', 'original uniform schedule/length reference'),
                (PROJECT/'10_independent_seed_checkpoint_study_v1/run_job.py', 'fresh independent original-seed initialization reference')]
    deps = ['numpy','torch','gymnasium','mujoco','metaworld','stable-baselines3','pandas','pyarrow','imageio','imageio-ffmpeg','matplotlib']
    import metaworld, stable_baselines3, gymnasium
    mw = Path(metaworld.__file__).parent
    for p in sorted(mw.rglob('*')):
        if p.is_file() and p.suffix in ('.py','.xml','.stl','.STL','.obj','.png'):
            sources.append((p,'installed Meta-World source/model asset'))
    for p in [Path(stable_baselines3.__file__).parent/'sac/sac.py',
              Path(stable_baselines3.__file__).parent/'common/buffers.py',
              Path(stable_baselines3.__file__).parent/'sac/policies.py',
              Path(gymnasium.__file__).parent/'envs/mujoco/mujoco_env.py']:
        sources.append((p,'installed learner/environment dependency source'))
    auxiliary = []
    for number in (68,71,77,79):
        dirs = list(PROJECT.glob(f'{number:02d}_*'))
        found = []
        for d in dirs:
            for p in d.rglob('report_ko.md'):
                if 'source_snapshot' not in str(p) and 'input_snapshot' not in str(p):
                    found.append(p)
        for p in found: sources.append((p,'auxiliary prior report; not pooled with new runs'))
        auxiliary.append({'number':number,'reports':[str(x) for x in found], 'available':bool(found)})
    rows = [{'path':str(p.resolve()),'bytes':p.stat().st_size,'sha256':sha(p),'role':role} for p,role in sources]
    write(ROOT/'input_receipt.json',{'created_at':datetime.now(timezone.utc).isoformat(),
        'files':rows,'auxiliary_reports':auxiliary,'environment_steps':0})
    roles = ('model_initialization','training_action_and_update','replay','schedule','environment','warmup_action','record_selection')
    streams = {}
    occupied = set()
    for rid in ['R01','R02','R03','R04','R05','TECH']:
        streams[rid] = {}
        for role in roles:
            n=0
            while True:
                value=seed(ROOT.name,rid,role,n)
                if value not in occupied:break
                n+=1
            streams[rid][role]=value;occupied.add(value)
    eval_cases=[]
    for ti, task in enumerate(('DO','DC','PU','BP')):
        for i in range(16):
            eval_cases.append({'task_id':task,'task_index':ti,'case_index':i,
                'initial_case_id':f'{task}_E{i:02d}','reset_seed':seed(ROOT.name,'evaluation_case',task,i),
                'action_seed':seed(ROOT.name,'evaluation_action',task,i,0),
                'video':i<2})
    write(ROOT/'seed_manifest.json',{'algorithm':'SHA256 UTF-8 pipe joined fields; first 4 bytes big endian; deterministic collision counter',
        'streams':streams,'evaluation_cases':eval_cases,
        'coupling':{'training_action_and_update':'one original PyTorch learner stream for collection actions and SAC stochastic update actions; preserved',
        'replay':'NumPy global stream; environment and schedule use separate generators',
        'episode_reset':'original SeedSequence([environment_role_seed,20,task_index,task_visit])',
        'evaluation':'deterministic CUDA actions; evaluation case/action seed independent of run/checkpoint'}})
    evaluation=[0,10000,20000,50000,100000,200000,400000,600000,800000,1000000]
    light=sorted(set(range(0,1000001,50000))|set(evaluation))
    assert len(light)==23
    protocol={'experiment_id':ROOT.name,'scope':'one baseline condition; exploratory observational campaign',
        'authorization':'user execution prompt; 5 independent fresh initializations, all four suite-B tasks',
        'runs':['R01','R02','R03','R04','R05'],'tasks':['DO','DC','PU','BP'],'suite':'B',
        'train_transitions_per_run':1000000,'evaluation_steps':evaluation,'evaluation_cases_per_task':16,
        'light_steps':light,'full_steps':[0,200000,600000,1000000],
        'caps':{'training':5000000,'evaluation':1600000,'technical_invalid_retry':10000,'optional_diagnostic':100000,'all_attempt':6710000},
        'schedule':'unchanged U: shuffled 8-episode blocks, exactly 2 episodes per task; 500 steps per episode',
        'update':'unchanged stock SAC, warmup included in training budget, one actor/critic update after transition >1000',
        'evaluation':'same deterministic CUDA policy; continue until native truncation at 500, unlike prior first-success stop; explicit new observational rule',
        'case_scope':'64 outcome-blind common physical initial cases; not standard full Meta-World evaluation',
        'transition_log':'all control-step train/evaluation/diagnostic transitions; per-episode lossless NPZ numeric chunks',
        'updates_log':'scalar loss/alpha/counters every update; full sampled Q/TD distribution summaries every 250 updates',
        'replay_log':'exact lifetime per-slot generation counts; every 250th batch transition IDs; no claim to reconstruct all batches',
        'gradient_norm_interval':250,'snapshots_interval':50,'video':{'case_indices':[0,1],'width':320,'height':240,'stride':5,'fps':20,'camera':'corner'},
        'snapshot_status':'diagnostic_state until same-runtime action and policy restore certified; no reset-training intervention',
        'analysis':'descriptive all-run/task/checkpoint curves, paired case transitions, behavior/replay/update alignment, phenomena plus contrary cases; no forced method choice',
        'optional_diagnostic':'write plan first; no optimizer updates; do not exhaust unused budget',
        'technical_tolerance':{'learning_atol':0.0,'learning_rtol':0.0,'physics_atol':0.0,'physics_rtol':0.0},
        'normal_episodes':3200,'normal_light_checkpoints':115,'normal_full_checkpoints':20,'normal_videos':400,
        'parallel_workers':2,'automatic_new_seeds':False,'automatic_learning_retry':False}
    write(ROOT/'protocol.json',protocol)
    write(ROOT/'config_resolved.json',{'learner':config,'suite':'B','task_mapping':json.loads(suites.read_text())['B'],
        'normalization':'no observation/reward normalization; raw 39D float64 -> policy 39D float32 plus task one-hot',
        'schedule_depends_on_total_length':False,'learning_rate_schedule':'constant 0.0003',
        'original_p0_length':400000,'this_campaign_length':1000000,
        'autoreset':'none; fresh environment each episode; no ignored action/reset calls counted as transitions',
        'bootstrap':'terminated masks target; 500-step timeout does not mask target; SB3 timeout correction unchanged',
        'policy':'shared task-conditioned MLP across tasks; separate actor and double critic networks; 256/256 ReLU, no task-specific heads',
        'reward_version':'v2','environment_version':'v3','wrappers':'none for real collector; PolicySpaces only for SAC constructor',
        'n_envs':1,'evaluation_terminal_rule':'native termination/truncation, no success-only stop'})
    write(ROOT/'baseline_manifest.json',{'base_directory':str(BASE),'code_hashes':{str(p):sha(p) for p,_ in sources if p.suffix=='.py'},
        'packages':{n:metadata.version(n) for n in deps},'python':sys.version,
        'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=PROJECT,text=True).strip(),
        'git_state':'legacy runtime checkout with preserved uncommitted historical assets; input hashes are authoritative',
        'verified_baseline':'fresh suite-B uniform four-task SAC, not target fine-tuning; no checkpoint used as initialization',
        'available_disk_bytes':shutil.disk_usage(ROOT).free,'expected_storage_upper_bytes':45000000000,
        'resource_preflight':'105+ GB initially available; no historical files deleted; refine from technical measurements'})
    print(json.dumps({'prepared':str(ROOT),'input_files':len(rows),'light_steps':light,'disk_free':shutil.disk_usage(ROOT).free}))

if __name__=='__main__': main()
