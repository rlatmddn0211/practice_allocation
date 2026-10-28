"""Freeze authorized baseline inputs using files only; never load policy/replay.

NumPy is used only for the prespecified SeedSequence recipes. No experiment
module, learner, environment or analysis implementation is imported.
"""
from __future__ import annotations
import copy
import csv
import hashlib
import io
import json
import math
import platform
import shutil
import sys
import time
import traceback
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
PARENTS = list(range(41011, 41016))
TASKS = ['DO', 'DC', 'PU', 'BP']
SOURCE_STATES = REPO/'52_same_state_future_replication_v1/inputs/state_manifest.json'
STATES_SHA = '63728184cc1cdf4dcccacfd7140fc3c1e66908c4bef5c7f8182b4f0a7f953607'
AUDIT63 = REPO/'63_retention_intervention_design_review_v1/results/20261027T051353Z_memory_provenance_99af630b'
DETAILS_SHA = '7a95b696819fd58d13177da0efc28a4db993e0830b8988203062386db0d61404'
ANALYSIS49 = REPO/'49_bp8k_late_value_analysis_v1/results/20261020T053017Z_B_analysis_b2d46333'
CAMPAIGN48 = REPO/'48_bp8k_checkpoint_evaluation_v1/results/20261020T050842Z_B_evaluation_5a8b5434'
CRITICAL = {
    'practice_allocation/learning.py':'e32e1f2e23490c651167af24386a3af5df005af766a33128c9bb75f719e30009',
    'practice_allocation/engine.py':'ae090b11d36b715eb7c66ce89c39c1021d1de140abe7fbb5e820eff1ed4a3f26',
    'practice_allocation/environment.py':'85afb8560da5160832e619f90608eae0b4b83aa75264376800111b295ef4e4e8',
    'practice_allocation/evaluation.py':'196b18ad4b60bca516511e71a449b12b78784a20a1699caa207975203d5cc525',
}

def sha(data): return hashlib.sha256(data).hexdigest()
def digest(path): return sha(Path(path).read_bytes())
def jbytes(value): return (json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf-8')
def seed(*parts): return int(np.random.SeedSequence(list(parts)).generate_state(1)[0])
def now(): return datetime.now(timezone.utc).isoformat()

class Preparation:
    def __init__(self):
        self.started=time.perf_counter();self.inputs={};self.checks=[];self.generated={}
        self.run=ROOT/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_input_preparation_'+uuid.uuid4().hex[:8])
        (self.run/'sources').mkdir(parents=True,exist_ok=False)
        (self.run/'input_snapshots').mkdir()
        shutil.copy2(__file__,self.run/'sources/prepare_inputs.py')
        self.source_sha=digest(__file__)
    def require(self,name,passed,detail=None):
        self.checks.append({'name':name,'passed':bool(passed),'detail':detail})
        if not passed: raise RuntimeError(name+': '+str(detail))
    def read(self,path,expected=None):
        path=Path(path).resolve();data=path.read_bytes();h=sha(data)
        if expected:self.require('input_hash:'+str(path),h==expected)
        key=str(path)
        if key in self.inputs:self.require('input_stable:'+key,self.inputs[key]['sha256']==h)
        else:
            snapshot='input_snapshots/'+h+path.suffix
            target=self.run/snapshot
            if not target.exists():target.write_bytes(data)
            self.inputs[key]={'sha256':h,'bytes':len(data),'snapshot':snapshot}
        return data
    def js(self,path,expected=None):return json.loads(self.read(path,expected).decode('utf-8-sig'))
    def rows(self,path,expected=None):return list(csv.DictReader(io.StringIO(self.read(path,expected).decode('utf-8-sig'))))
    def write(self,path,value):
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as f:f.write(jbytes(value))
        self.generated[path.relative_to(ROOT).as_posix()]=digest(path)
        return {'path':str(path.resolve()),'sha256':digest(path)}
    def table(self,path,rows,fields=None):
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('x',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f,fieldnames=fields or list(rows[0]));writer.writeheader();writer.writerows(rows)
        self.generated[path.relative_to(ROOT).as_posix()]=digest(path)
        return {'path':str(path.resolve()),'sha256':digest(path)}

def ranked_cases(bank,bank_sha,parent,label):
    def key(row):
        payload=json.dumps([bank_sha,parent,row['task'],int(row['episode_index']),label],ensure_ascii=False,separators=(',',':'))
        return hashlib.sha256(payload.encode('utf-8')).hexdigest(),int(row['episode_index'])
    return sorted(bank,key=key)

def inventory_seed_roots(p,states):
    records=[]
    keys={'old_continuation_rng_seed','proposed_new_future_root_seed','root_seed','continuation_rng_seed'}
    def walk(value,path,pointer=''):
        if isinstance(value,dict):
            for k,v in value.items():
                if k in keys and isinstance(v,int):records.append({'source':str(path),'field':pointer+'/'+k,'root_seed':v})
                elif isinstance(v,(dict,list)):walk(v,path,pointer+'/'+k)
        elif isinstance(value,list):
            for i,v in enumerate(value):walk(v,path,pointer+'/'+str(i))
    walk(states,SOURCE_STATES)
    old_jobs=REPO/'59_fresh_future_confirmation_v1/inputs/proposed_jobs.csv'
    for index,row in enumerate(p.rows(old_jobs)):
        records.append({'source':str(old_jobs),'field':f'row{index}/root_seed','root_seed':int(row['root_seed'])})
    for version in ('52_same_state_future_replication_v1','59_fresh_future_confirmation_v1'):
        for path in sorted((REPO/version/'results').glob('*/jobs/*/*/request.json')):
            walk(p.js(path),path)
    for state in states:
        records.append({'source':str(SOURCE_STATES),'field':'parent_original_learning_seed','root_seed':state['parent']})
    return {'field_policy':'Only named root-seed metadata; no outcome files or step/checkpoint numbers scanned as seeds.',
            'records':records,'unique_prior_root_seeds':sorted({r['root_seed'] for r in records})}

def historical_labels(p,state,details,audit_inputs):
    old=next(item for item in details if item['parent']==state['parent'] and item['prefix_continuation']==4201)
    p.require('historical_coverage:'+str(state['parent']),old['eligible_episodes']==200 and not old['gaps'] and not old['duplicate_episode_ends'])
    label_rows=[];source_refs=[]
    for item in old['ancestry_jobs']:
        attempt=Path(item['checkpoint']).parent
        path=attempt/'train_episodes.csv';rel=path.relative_to(REPO).as_posix()
        raw=p.rows(path,audit_inputs[rel]['sha256'])
        source_refs.append({'path':str(path),'sha256':digest(path)})
        for row in raw:
            end=int(row['step'])
            if 108001<=end<=208000:
                label_rows.append({'episode':int(row['episode']),'step':end,'end_step':end,
                    'first_birth_step':end-499,'last_birth_step':end,'task':row['task'],
                    'success':row['success']=='True','success_episode':row['success']=='True',
                    'first_success_step':None,'first_success_known':False,'length':int(row['length']),
                    'initial_state_hash':row['initial_state_hash']})
    label_rows.sort(key=lambda row:row['step'])
    p.require('historical_exact_200_rows:'+str(state['parent']),[r['step'] for r in label_rows]==list(range(108500,208001,500)))
    for row,reference in zip(label_rows,old['episode_membership']):
        p.require('historical_label_matches63:'+str(state['parent'])+':'+str(row['step']),
            row['episode']==reference['episode'] and row['task']==reference['task']
            and row['success']==reference['success_episode'] and row['initial_state_hash']==reference['initial_state_hash'])
    return {'schema_version':1,'parent':state['parent'],'prefix_continuation':4201,
        'eligible_birth_range':[108001,208000],'episode_length':500,
        'birth_to_episode':'episode=(birth_step+499)//500; end_step=500*episode',
        'success_definition':'any official success during historical stochastic training episode; not current-teacher competence',
        'first_success_time_known':False,'actual_replay_slot_join_certified':False,
        'source_episode_csvs':source_refs,'episode_rows':label_rows}

def main():
    p=Preparation();status='failed';error=None;states=[];jobs=[];baseline=[]
    try:
        p.require('venv_required',sys.prefix!=sys.base_prefix,{'prefix':sys.prefix,'base_prefix':sys.base_prefix})
        p.require('fresh_inputs_destination',not (ROOT/'inputs').exists())
        original_states=p.js(SOURCE_STATES,STATES_SHA)
        selected=[copy.deepcopy(s) for s in original_states if s['prefix_continuation']==4201]
        p.require('five_prespecified_states',[s['parent'] for s in selected]==PARENTS)
        details=p.js(AUDIT63/'state_details.json',DETAILS_SHA)
        audit_inputs=p.js(AUDIT63/'input_hashes.json')
        for name,expected in CRITICAL.items():p.read(ROOT/name,expected)
        prior=inventory_seed_roots(p,original_states)
        new_roots={}
        for parent in PARENTS:
            for future in (1,2):new_roots[parent,future]=seed(640202,64,parent,4201,future)
        p.require('ten_new_root_seeds_unique',len(set(new_roots.values()))==10)
        collision=set(new_roots.values())&set(prior['unique_prior_root_seeds'])
        p.require('new_roots_absent_from_prior_metadata',not collision,sorted(collision))
        prior['new_root_seeds']=[{'parent':parent,'prefix':4201,'future':future,'root_seed':root}
                                 for (parent,future),root in new_roots.items()]
        prior['collisions']=[];prior['duplicated_across_conditions_intentionally']=True
        p.write(ROOT/'inputs/seed_collision_audit.json',prior)
        all_membership=[]
        # Bank metadata and its hash are sufficient for selection. No evaluation outcomes read above.
        for index,state in enumerate(selected):
            parent=state['parent'];bank=p.js(state['bank']['path'],state['bank']['sha256'])
            outcome=bank['outcome'];p.require('O100_case_count:'+str(parent),len(outcome)==400)
            identities={(r['task'],int(r['episode_index'])) for r in outcome}
            p.require('O100_case_identity_grid:'+str(parent),identities=={(t,i) for t in TASKS for i in range(100)})
            e50=[];t20=[]
            for task in TASKS:
                rows=[r for r in outcome if r['task']==task]
                chosen=ranked_cases(rows,state['bank']['sha256'],parent,'E50')[:50]
                traced=ranked_cases(chosen,state['bank']['sha256'],parent,'T20')[:20]
                e50.extend(chosen);t20.extend(traced)
                ei={int(r['episode_index']) for r in chosen};ti={int(r['episode_index']) for r in traced}
                for row in rows:all_membership.append({'parent':parent,'task':task,'episode_index':int(row['episode_index']),
                    'seed':int(row['seed']),'initial_state_hash':row['initial_state_hash'],
                    'in_E50':int(row['episode_index']) in ei,'in_T20':int(row['episode_index']) in ti})
            state['selected_cases']=p.write(ROOT/f'inputs/cases_{parent}.json',{'schema_version':1,'parent':parent,
                'bank':state['bank'],'ranking_encoding':'UTF-8 compact JSON array [bank_sha256,parent,task,episode_index,label]',
                'E50':e50,'T20':t20})
            state['episode_labels']=p.write(ROOT/f'inputs/episode_labels_{parent}.json',historical_labels(p,state,details,audit_inputs))
            state['state_index']=index;state['panel_seed']=seed(640202,6401,parent)
            # Read-only ancestry from S to its original 200k parent, never an old future.
            ref=state['checkpoint'];ancestry=[]
            while True:
                cp=Path(ref['path']);manifest=p.js(cp/'checkpoint_manifest.json',ref['manifest_sha256'])
                ancestry.append({'checkpoint':ref,'absolute_step':manifest['step']})
                for name,expected in CRITICAL.items():p.require('checkpoint_source:'+str(parent)+':'+str(manifest['step'])+':'+name,manifest['source_hashes'][name]==expected)
                if manifest['step']==200000:state['parent_checkpoint']=ref;break
                p.require('valid_prefix_ancestry_step:'+str(parent),200000<manifest['step']<=208000)
                request=p.js(cp.parent/'request.json');ref=request['parent']
            state['prefix_checkpoint_ancestry']=ancestry
            states.append(state)
        p.write(ROOT/'inputs/evaluation_cases.json',all_membership)
        for parent_index,state in enumerate(states):
            for future in (1,2):
                order=('dose25','dose625') if (parent_index+future-1)%2==0 else ('dose625','dose25')
                for condition in order:
                    root=new_roots[state['parent'],future]
                    jobs.append({'id':f"B_s{state['parent']}_p4201_{condition}_N{future}",
                        'order':len(jobs)+1,'state_index':parent_index,'parent':state['parent'],
                        'prefix_continuation':4201,'condition':condition,'future':future,'future_id':future,
                        'root_seed':root,'schedule_seed':seed(root,10),'panel_seed':state['panel_seed'],
                        'training_steps':32000,'full_checkpoint_absolute_steps':[212000,216000,224000,240000]})
        p.write(ROOT/'inputs/jobs.json',jobs)
        # Only after outcome-blind case sets and jobs have been written, certify P/S reuse.
        old49_hashes=p.js(ANALYSIS49/'input_hashes.json')
        canonical=p.rows(ANALYSIS49/'outcomes_25_policies.csv')
        plan48=p.js(CAMPAIGN48/'plan.json',old49_hashes[str(CAMPAIGN48/'plan.json')])
        reuse=[]
        for state in states:
            parent=state['parent'];selected_cases=p.js(state['selected_cases']['path'],state['selected_cases']['sha256'])
            original_bank=p.js(state['bank']['path'],state['bank']['sha256'])['outcome']
            bank_map={(r['task'],int(r['episode_index'])):r for r in original_bank}
            parent_ref=next(item['outcome'] for item in plan48['baselines'] if item['original_seed']==parent and item['horizon']==0)
            s_paths=[path for path in old49_hashes if path.endswith('evaluation_episodes.csv') and f'B_s{parent}_r4201_dose625_8k_O100' in path]
            p.require('unique_source_S_evaluation:'+str(parent),len(s_paths)==1)
            source_refs={'P':parent_ref,'S':{'path':s_paths[0],'sha256':old49_hashes[s_paths[0]]}}
            state['parent_evaluation']=parent_ref;state['source8k_evaluation']=source_refs['S']
            certificates={}
            for stage,ref in source_refs.items():
                source_path=Path(ref['path']);attempt=source_path.parent
                raw=p.rows(source_path,ref['sha256'])
                request=p.js(attempt/'request.json',old49_hashes.get(str(attempt/'request.json')))
                result=p.js(attempt/'result.json',old49_hashes.get(str(attempt/'result.json')))
                checkpoint=state['parent_checkpoint'] if stage=='P' else state['checkpoint']
                requested_checkpoint=request['parent'] if stage=='P' else request['checkpoint']
                p.require('reuse_exact_checkpoint:'+str(parent)+stage,requested_checkpoint==checkpoint)
                p.require('reuse_exact_bank:'+str(parent)+stage,request['bank']==state['bank'])
                p.require('reuse_result_csv_hash:'+str(parent)+stage,result['episodes_sha256']==ref['sha256'])
                p.require('reuse_evaluation_nonmutating:'+str(parent)+stage,result['evaluation_state_unchanged'])
                for name,expected in CRITICAL.items():
                    p.require('reuse_source_hash:'+str(parent)+stage+name,request['source_hashes'][name]==expected)
                    p.read(attempt/'source_snapshot'/name,expected)
                source_map={(row['task'],int(row['episode_index'])):row for row in raw}
                p.require('reuse_complete_case_grid:'+str(parent)+stage,len(raw)==400 and set(source_map)==set(bank_map))
                canonical_map={(row['task'],int(row['episode_index'])):row for row in canonical
                    if int(row['original_seed'])==parent and row['policy']==('J0' if stage=='P' else 'J8_4201')}
                p.require('canonical_case_grid:'+str(parent)+stage,set(canonical_map)==set(bank_map))
                for key,row in source_map.items():
                    case=bank_map[key];can=canonical_map[key]
                    success=int(row['success']);length=int(row['length'])
                    p.require('reuse_physical_identity:'+str(parent)+stage+str(key),
                        row['initial_state_hash']==case['initial_state_hash'] and int(row['seed'])==int(case['seed']))
                    p.require('reuse_binary_length:'+str(parent)+stage+str(key),
                        success in (0,1) and 1<=length<=500 and (success==1 or length==500)
                        and math.isfinite(float(row['return'])))
                    p.require('canonical_matches_original:'+str(parent)+stage+str(key),
                        all(row[k]==can[k] for k in ('task','seed','initial_state_hash','success','length'))
                        and float(row['return'])==float(can['return']))
                for case in selected_cases['E50']:
                    row=source_map[case['task'],int(case['episode_index'])];success=int(row['success'])
                    baseline.append({'parent':parent,'stage':stage,'task':case['task'],
                        'episode_index':int(case['episode_index']),'case_id':int(case['episode_index']),
                        'seed':int(row['seed']),'initial_state_hash':row['initial_state_hash'],
                        'success':success,'return':float(row['return']),'length':int(row['length']),
                        'first_success_step':int(row['length']) if success else '',
                        'first_success_inferred':bool(success),'first_success_inference':'early_stop_on_first_official_success' if success else 'unsuccessful_censored_at_500',
                        'source_eval_sha256':ref['sha256']})
                certificates[stage]={'certified':True,'require_reval':False,'checkpoint':checkpoint,'evaluation':ref,
                    'source_environment_and_evaluation_byte_identity':True,'same_bank_and_physical_case_identity':True,
                    'canonical49_verified_against_original':True,'first_success_step_inferred_from_early_stop_length':True,
                    'new_full_model_or_replay_verification_performed':False}
            state['baseline_reuse']={'certified':True,'require_reval':False,'stages':certificates}
            reuse.append({'parent':parent,**state['baseline_reuse']})
        p.require('two_thousand_selected_baseline_rows',len(baseline)==2000)
        p.table(ROOT/'inputs/baseline_rows.csv',baseline)
        p.write(ROOT/'inputs/baseline_reuse_certificates.json',reuse)
        p.write(ROOT/'inputs/state_manifest.json',states)
        provenance={'created_at':now(),'scope':'outcome-blind metadata selection followed by certified historical P/S reuse',
            'source_state_manifest':{'path':str(SOURCE_STATES),'sha256':STATES_SHA},
            'source_episode_audit':{'path':str(AUDIT63/'state_details.json'),'sha256':DETAILS_SHA},
            'all_read_inputs':p.inputs,'critical_source_hashes':CRITICAL,
            'case_ranking_does_not_use_outcomes':True,'models_replays_and_collector_pickles_loaded':0,
            'current_replay_episode_join_certified':False,'source_snapshot':str(p.run/'sources/prepare_inputs.py')}
        p.write(ROOT/'inputs/provenance.json',provenance)
        protocol={
            'version':ROOT.name,'authorization_date':'2026-10-27','status':'authorized_baseline_pending_technical_certification',
            'authorization':'User authorized immediate implementation and twenty same-S baseline continuations after technical integrity checks.',
            'objective':'Describe success acquisition, loss and recovery under unchanged SAC and two collection allocations; no efficacy investment gate.',
            'suite':'B','tasks':TASKS,'parents':PARENTS,'prefix_continuation':4201,'states':5,
            'parent_absolute_step':200000,'start_absolute_step':208000,'conditions':['dose25','dose625'],
            'condition_labels':{'dose25':'UNIFORM','dose625':'BP625'},'futures':[1,2],'jobs':20,
            'training_steps_per_job':32000,'training_steps_total':640000,
            'full_checkpoint_absolute_steps':[212000,216000,224000,240000],
            'training_episode_steps':500,'collection_block_episodes':16,'collection_block_steps':8000,
            'quotas':{'dose25':[4,4,4,4],'dose625':[2,2,2,10]},
            'fork_contract':'At exhausted original sixteen-episode queue only; preserve queue contents, position16, blocks_generated1, task visits, collected counters, replay branch_start200000, optimizer/learner/entropy. Change candidate and declared future RNG streams only; do not call start_branch.',
            'seed_recipe':'numpy.SeedSequence([640202,64,parent,4201,future]).generate_state(1)[0]',
            'condition_pairing':'For each parent/future, UNIFORM and BP625 share root_seed and schedule_seed intentionally; ten roots are otherwise unique and absent from inventoried prior metadata.',
            'schedule_seed_recipe':'SeedSequence([root_seed,10]).generate_state(1)[0]',
            'reset_seed_recipe':'Existing derived_seed(root_seed,20,task,retained_task_visit) unchanged',
            'job_order':'Parents ascending; futures1,2; alternate first condition with (parent_index+future-1) parity; frozen inputs/jobs.json.',
            'evaluation':{'max_steps_per_case':500,'deterministic_actions':True,'early_stop_on_success':True,
                'P_S_final':'E50:50 cases/task (200 per policy)','intermediate':'T20:20 cases/task (80 per policy), subset of E50',
                'E50_absolute_steps':[200000,208000,240000],'T20_absolute_steps':[212000,216000,224000],
                'case_ranking':'Per task SHA256 of UTF8 compact JSON [bankSHA,parent,task,episode_index,label]; E50 first50 with label E50, then independent T20 rank inside E50 first20 with label T20.',
                'P_S_reuse':'Certified actual source outcomes only after checkpoint/bank/physical identity and source-code contract checks; otherwise require explicit re-evaluation within cap, never case-index-only matching.',
                'first_success_step':'Infer from episode length only when success=1 and exact first-success early-stop contract is certified; failures are None/censored500.'},
            'telemetry':{'window_steps':250,'policy_probe_interval_steps':1000,'panel_size':256,'panel_cases_per_task':64,
                'panel_seed_recipe':'derived_seed(640202,6401,parent)','panel_selection':'Without replacement per task from restored S replay using separate numpy default_rng; no labels/outcomes; same fixed panel for all conditions/futures of parent.',
                'historical_success_label':'Entire historical training episode any_success; first-success transition unknown; actual replay-slot join requires technical verification.'},
            'analysis':{'bootstrap_seed':640303,'independent_unit':'five original parents; futures nested and paired across conditions',
                'report':'All jobs, task and parent contributions, J and gain/loss/recovery, case uncertainty separately from future/parent variability; no effect-direction stopping or post-hoc thresholds.',
                'effect_investment_gates':None},
            'budgets':{'total_environment_cap_all_attempts':6050000,'technical_environment_cap_all_attempts':10000,
                'research_training_steps':640000,'research_new_evaluation_cap':4400000,'P_S_revaluation_cap_if_needed':1000000,
                'automatic_retry_reserve':0,'all_attempts_in_caps':True,'wall_and_compute_costs_recorded_separately':True},
            'total_environment_cap':6050000,'technical_environment_cap_all_attempts':10000,
            'evaluation_cap_total':4400000,'automatic_retry_reserve':0,'max_parallel_workers':1,
            'technical_plan':{'all_twenty_restore_and_collection_forks_environment_steps':0,
                'prespecified_parent':41011,'prespecified_future':1,
                'each_condition_logging_enabled1000_vs_disabled1000_total_steps':4000,
                'each_condition_split500_save_load500_vs_existing_enabled1000_extra_steps':2000,
                'S_known_one_case_per_task_evaluation_cap':2000,
                'N2_additional_BP_training_steps':500,'optional_known_exact_repeat_one_case_cap':500,
                'first_plan_environment_cap':9000,'cumulative_all_attempts_cap':10000,
                'isolated_entropy_probe_and_checkpoint_evaluation_fullstate_checks':True,
                'separate_outputs_costs_and_source_fixtures_for_every_attempt':True,
                'technical_states_reused_for_research':False},
            'failure_policy':'Stop for integrity failure or cap exhaustion. Preserve all attempts and full checkpoints. Zero automatic retries and no extra parents, conditions or horizons. Execute all twenty authorized jobs regardless of scientific direction.',
            'held':'Prior intervention A/B/C/D, new parents, original C and original stages2/3 remain outside this authorization.',
            'packages':states[0]['packages'],'critical_source_hashes':CRITICAL,
            'input_hashes':{rel:h for rel,h in p.generated.items() if rel.startswith('inputs/')},
        }
        p.write(ROOT/'protocol.json',protocol)
        for filename in ('README.md','evidence_record_ko.md'):
            p.read(ROOT/filename);shutil.copy2(ROOT/filename,p.run/'sources'/filename)
        shutil.copy2(ROOT/'protocol.json',p.run/'sources/protocol.json')
        p.require('preparation_source_unchanged',digest(__file__)==p.source_sha)
        for path,item in p.inputs.items():p.require('input_unchanged_at_end:'+path,digest(path)==item['sha256'])
        status='complete'
    except Exception as exc:error={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
    finally:
        summary={'status':status,'created_at':now(),'states':len(states),'jobs':len(jobs),'baseline_rows':len(baseline),
            'checks':len(p.checks),'failed_checks':sum(not c['passed'] for c in p.checks),'error':error,
            'new_environment_steps':0,'new_SAC_updates':0,'policy_or_replay_loads':0,
            'wall_seconds':time.perf_counter()-p.started,'python':sys.version,'numpy':np.__version__,
            'platform':platform.platform(),'executable':sys.executable,'source_sha256':p.source_sha,
            'run':str(p.run),'generated_hashes':p.generated}
        for name,value in (('summary.json',summary),('checks.json',p.checks),('input_hashes.json',p.inputs),('output_hashes.json',p.generated)):
            with (p.run/name).open('xb') as f:f.write(jbytes(value))
        print(json.dumps(summary,ensure_ascii=False))
    return 0 if status=='complete' else 1

if __name__=='__main__':raise SystemExit(main())
