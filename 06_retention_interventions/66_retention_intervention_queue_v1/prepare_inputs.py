"""One-time preparation, no environment execution and no outcome selection."""
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/'64_gain_loss_recovery_baseline_v1'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ref(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def seed(*x):return int(np.random.SeedSequence(x).generate_state(1)[0])

def main():
    if (ROOT/'protocol.json').exists():raise RuntimeError('Prepared protocol cannot be overwritten')
    states=read(ROOT/'inputs/state_manifest.json')
    for s in states:
        for k in ('selected_cases','episode_labels'):
            s[k]=ref(ROOT/'inputs'/Path(s[k]['path']).name)
    save(ROOT/'inputs/state_manifest.json',states)
    oldjobs=read(OLD/'inputs/jobs.json');oldjobs=oldjobs.get('jobs',[]) if isinstance(oldjobs,dict) else oldjobs
    prior=set(j['root_seed'] for j in oldjobs)
    prior.update(r['root_seed'] for r in read(OLD/'inputs/seed_collision_audit.json').get('records',[]))
    # Include every declared numerical seed in historical JSON metadata (not outcomes).
    def collect(x,key=''):
        if isinstance(x,dict):
            for k,v in x.items():collect(v,k)
        elif isinstance(x,list):
            for v in x:collect(v,key)
        elif isinstance(x,int) and 'seed' in key.lower():prior.add(x)
    for folder in ('51_same_state_future_investment_protocol_v1','52_same_state_future_replication_v1',
                   '57_acquisition_state_dependence_confirmation_plan_v1','58_confirmation_prediction_preflight_v1',
                   '59_fresh_future_confirmation_v1'):
        for path in (ROOT.parent/folder/'inputs').glob('*.json'):collect(read(path))
    jobs=[];roots=[]
    for index,state in enumerate(states):
        parent=state['parent']
        for future in (1,2):
            root=seed(660202,66,parent,4201,future);schedule=seed(root,10)
            if root in prior:raise RuntimeError('Historical future-seed collision')
            roots.append(root)
            arms=list('ABCD');shift=(index+future-1)%4;arms=arms[shift:]+arms[:shift]
            for arm in arms:
                jobs.append({'id':f'B_s{parent}_p4201_{arm}_N{future}','state_index':index,
                    'parent':parent,'prefix_continuation':4201,'condition':'dose625','arm':arm,
                    'future':future,'root_seed':root,'schedule_seed':schedule})
    assert len(set(roots))==10
    save(ROOT/'inputs/jobs.json',jobs)
    save(ROOT/'inputs/seed_collision_audit.json',{'inventoried_seed_count':len(prior),
        'new_roots':roots,'intersection':sorted(set(roots)&prior),
        'pairing':'Same parent/future intentionally shares four arms; environment trajectories need not match.'})
    cam=Path(read(OLD/'ACTIVE_CAMPAIGN.json')['campaign'])
    plan=read(cam/'plan.json')
    save(ROOT/'inputs/upstream_campaign.json',{'schema_version':1,'campaign':str(cam),
        'plan_integrity':ref(cam/'plan_integrity.json'),'plan':ref(cam/'plan.json'),
        'source_hashes':plan['source_hashes'],'expected_jobs':20})
    p=read(OLD/'protocol.json')
    p.update(version=ROOT.name,status='authorized_intervention_pending_upstream_and_technical_gate',
        authorization='User explicitly approved forty BP625 A/B/C/D paths and automatic sequential execution on 2026-10-27; cap10.10M including20k technical.',
        objective='Development intervention: reduce loss while retaining acquisition and recovery. No efficacy is assumed.',
        conditions=['dose625'],arms=list('ABCD'),jobs=40,training_steps_total=1280000,
        arm_labels={'A':'unchanged SAC','B':'actor learning rate half','C':'general-memory S-policy preservation','D':'success-episode-memory S-policy preservation'},
        total_environment_cap=10100000,technical_environment_cap_all_attempts=20000,
        evaluation_cap_total=8800000,
        budgets={'total_environment_cap_all_attempts':10100000,'technical_environment_cap_all_attempts':20000,
                 'research_training_steps':1280000,'research_new_evaluation_cap':8800000,
                 'automatic_retry_reserve':0,'all_attempts_in_caps':True},
        retention={'age_bins':4,'episodes_per_stratum':4,'observations_per_episode':32,
                   'batch_size':256,'kl_coefficient':1.0,'actor_lr_multiplier':0.5,
                   'zero_success_fallback':'shared_general','memory_sampling':'with_replacement',
                   'telemetry_window_steps':250,'kl_direction':'teacher_to_student','same_actor_step':True,
                   'teacher':'fixed S actor; historical success is not proof of current-teacher competence',
                   'direction':'KL(teacher Gaussian || current Gaussian), action dimensions summed, observations averaged; tanh is shared bijection',
                   'optimizer':'Same single actor optimizer step; add KL gradient before that step. Critic, alpha and RL replay unchanged.',
                   'memory':'Within task and fixed 25k birth-age stratum choose min(4,successful episodes) distinct episodes; C same count from all episodes;32 unique observations/episode. If no successful episode, C and D share same general fallback min(4,all episodes). No replacement.',
                   'memory_seed_recipe':'derived_seed(660202,6601,parent)',
                   'regularizer_rng_recipe':'derived_seed(root_seed,6602); private RNG shared C/D; no global draws'},
        seed_recipe='SeedSequence([660202,66,parent,4201,future]).generate_state(1)[0]',
        job_order='Parents ascending, future1/2, rotate arms by(parent_index+future-1)%4; frozen jobs.json',
        held='New parents, MT10/CW, primitive preservation, original C and original stages2/3 remain held.',
        technical_plan={'cap':20000,'research_restores_original_S_again':True,
                        'gates':'exact original restores; zero-lambda equivalence; B/C/D logging and full resume; same C/D task-age support; isolated evaluation and memory RNG; all arms numerically finite'},
        failure_policy='Integrity failure/cap exhaustion stops; no retries, no seed replacement, no new arms. All40 run regardless of direction.',
        analysis={'bootstrap_seed':660303,'independent_unit':'5 parents;2 nested paired futures;4 equal tasks',
                  'primary_contrast':'D minus C','other_contrasts':['B-A','C-A','D-A'],
                  'metrics':'J,G,L,R,STOP;R subset of G;J-JS=G-L; parent/task/future and LOPO',
                  'effect_investment_gates':None})
    p['condition_labels']={'dose625':'BP625'}
    p['input_hashes']={f'inputs/{f.name}':sha(f) for f in sorted((ROOT/'inputs').iterdir()) if f.suffix in ('.json','.csv')}
    save(ROOT/'protocol.json',p)
    save(ROOT/'VERSION.json',{'version':ROOT.name,'date':'2026-10-27','independent_copy_of':OLD.name})
    print(json.dumps({'jobs':len(jobs),'new_environment_steps':0,'upstream':str(cam)}))
if __name__=='__main__':main()
