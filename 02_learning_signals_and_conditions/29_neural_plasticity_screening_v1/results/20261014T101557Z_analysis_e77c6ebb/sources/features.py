"""Predeclared F06 features and controls; no future information in inputs."""
from pathlib import Path
from collections import defaultdict
import numpy as np
from scipy.stats import spearmanr
from common import ROOT,allocations,contexts,context_weight,prefix,table
from outcomes import macro,task_values
from performance_controls import PROFILE,marginal_features

CRITIC=PROFILE+['reward_scale','target_scale','residual','gap']
COVERAGE=CRITIC+['state_spread','state_rank']
STEP=COVERAGE+['actor_step1','critic_step1']
AUDIT_STEP=COVERAGE+['actor_step1_audit','critic_step1_audit']
GROUPS={'CriticBase':CRITIC,'CoverageBase':COVERAGE,
    'CoverageBase_static':COVERAGE+['dormant','erank'],
    'CoverageBase_static_zero':COVERAGE+['dormant_zero','erank'],
    'CoverageBase_static_tenth':COVERAGE+['dormant_tenth','erank'],
    'CoverageBase_static_audit':COVERAGE+['dormant_audit','erank_audit'],
    'CoverageBase_total20':COVERAGE+['actor_total20','critic_total20'],
    'StepBase':STEP,'StepBase_F06':STEP+['actor_later','critic_later'],
    'StepBase_audit':AUDIT_STEP,'StepBase_audit_F06':AUDIT_STEP+['actor_later_audit','critic_later_audit']}

def safe_rho(a,b):
    return float(spearmanr(a,b).statistic) if np.ptp(a)>0 and np.ptp(b)>0 else None

def snapshot_features(static,states,losses,tasks):
    result={}
    for name,col,panel in [('dormant','dormant_primary','M'),('dormant_zero','dormant_zero','M'),
                           ('dormant_tenth','dormant_tenth','M'),('erank','normalized_rank','M'),
                           ('dormant_audit','dormant_primary','A'),('erank_audit','normalized_rank','A')]:
        rr=[r for r in static if r['panel']==panel]
        actor=np.mean([float(r[col]) for r in rr if r['module']=='actor'])
        critic=np.mean([float(r[col]) for r in rr if r['module']!='actor'])
        result[name]=float((actor+critic)/2)
    result['state_spread']=float(np.mean([np.log1p(float(r['spread'])) for r in states if r['panel']=='M']))
    result['state_rank']=float(np.mean([float(r['normalized_rank']) for r in states if r['panel']=='M']))
    dd={(r['module'],r['train_panel'],r['eval_panel'],int(r['step']),r['task']):r for r in losses}
    for module in ['actor','critic']:
        for tr,ev,suffix in [('M','A',''),('A','M','_audit'),('M','M','_train'),('A','A','_audit_train')]:
            values=[]
            for task in tasks:
                zero,one,end=[dd[module,tr,ev,step,task] for step in [0,1,20]]
                scale=max(float(zero['loss_rms']),1e-6);z,o,e=[float(v['loss']) for v in [zero,one,end]]
                values.append([(z-o)/scale,(o-e)/scale,(z-e)/scale])
            for i,name in enumerate(['step1','later','total20']):result[module+'_'+name+suffix]=float(np.mean([v[i] for v in values]))
    return result

def build(run,p,parents,ys,lengths,splits,refs,measurement=None):
    if not measurement:raise ValueError('Full measurement directory required')
    md=Path(measurement);ms=run.read(md/'summary.json')
    run.check('complete full measurement',ms['status']=='completed' and not ms['technical_smoke'] and ms['snapshots']==192 and ms['clone_optimizer_steps']==15360)
    run.check('same protocol',run.read(md/'sources/protocol.json')==p)
    manifest=run.read(md/'snapshot_manifest.json')
    for item in manifest:
        run.check('measured checkpoint is evaluated checkpoint '+item['id'],item['checkpoint']==refs[item['id']]);run.hashed(item['raw_path'],item['raw_sha256'])
    sc=defaultdict(list);states=defaultdict(list);loss=defaultdict(list)
    for r in run.rows(md/'static_diagnostics.csv'):sc[r['id']].append(r)
    for r in run.rows(md/'state_controls.csv'):states[r['id']].append(r)
    for r in run.rows(md/'clone_losses.csv'):loss[r['id']].append(r)
    fdir=ROOT/p['f05_measurements'];fh=run.read(ROOT/p['f05_integrity_record']);normalized={Path(k).resolve():v for k,v in fh.items()}
    run.hashed(fdir/'task_diagnostics.csv',normalized[(fdir/'task_diagnostics.csv').resolve()])
    f05={(r['id'],r['task']):r for r in run.rows(fdir/'task_diagnostics.csv') if r['panel']=='M'}
    for item in run.read(fdir/'snapshot_manifest.json'):run.check('F05 control same checkpoint '+item['id'],item['checkpoint']==refs[item['id']])
    all_features=[];byid={}
    for item in manifest:
        jid=item['id'];value=snapshot_features(sc[jid],states[jid],loss[jid],p['suites'][item['suite']]);byid[jid]=value
        all_features.append({k:item[k] for k in ['id','suite','original_seed','checkpoint_step','horizon','continuation','allocation']}|value)
    table(run.out/'all_snapshot_features.csv',all_features)
    rows=[]
    for ctx in contexts(p):
        s,n,c=ctx;dix,oix=splits[s];base=task_values(parents[ctx],dix)
        for ri,rep in enumerate(p['continuations'][s]):
            for ai,alloc in enumerate(allocations(p,s)):
                jid=prefix(ctx)+f'_r{rep}_{alloc}_t20';cur=task_values(ys[ctx][0,ri,ai],dix)
                r={'id':jid,'suite':s,'original_seed':n,'checkpoint_step':c,'continuation':rep,'allocation':alloc,'weight':context_weight(ctx)/15,
                   **marginal_features(base,cur,ai,c),**byid[jid],'D20':float(cur.mean()),
                   'target_D_remainder':float(macro(ys[ctx][1,ri,ai],dix)-cur.mean()),'O40':float(macro(ys[ctx][1,ri,ai],oix))}
                for key,col in [('reward_scale','reward_rms'),('target_scale','target_rms'),('residual','residual_normalized'),('gap','gap_normalized')]:
                    r[key]=float(np.mean([np.log1p(float(f05[jid,t][col])) for t in p['suites'][s]]))
                rows.append(r)
    run.check('180 predictive rows',len(rows)==180)
    static_summary=[]
    for module in ['actor','critic0','critic1']:
        for horizon in [0,20000]:
            rr=[r for v in sc.values() for r in v if r['module']==module and int(r['horizon'])==horizon and r['panel']=='M']
            static_summary.append({'module':module,'horizon':horizon,'task_rows':len(rr),
                'mean_dormant_fraction':float(np.mean([float(r['dormant_primary']) for r in rr])),
                'mean_normalized_rank':float(np.mean([float(r['normalized_rank']) for r in rr])),
                'min_dormant_fraction':min(float(r['dormant_primary']) for r in rr),
                'max_dormant_fraction':max(float(r['dormant_primary']) for r in rr),
                'all_zero_layers':sum(r['all_zero']=='True' for r in rr)})
    dynamic_summary=[]
    for module in ['actor','critic']:
        value=lambda k:[r[module+'_'+k] for r in rows]
        dynamic_summary.append({'module':module,'branches':len(rows),
            'mean_train_total20':float(np.mean(value('total20_train'))),'mean_other_total20':float(np.mean(value('total20'))),
            'mean_other_step1':float(np.mean(value('step1'))),'mean_other_later':float(np.mean(value('later'))),
            'other_total20_positive_branches':sum(v>0 for v in value('total20')),
            'train_improves_other_worsens_branches':sum(a>0 and b<0 for a,b in zip(value('total20_train'),value('total20'))),
            'later_panel_spearman':safe_rho(value('later'),value('later_audit')),
            'later_panel_sign_agreement_pct':float(np.mean(np.sign(value('later'))==np.sign(value('later_audit')))*100)})
    stability=[]
    for field,audit in [('dormant','dormant_audit'),('erank','erank_audit')]:
        aa=[r[field] for r in rows];bb=[r[audit] for r in rows]
        stability.append({'feature':field,'panel_spearman':safe_rho(aa,bb),'median_abs_difference':float(np.median(np.abs(np.array(aa)-bb)))})
    table(run.out/'static_summary.csv',static_summary);table(run.out/'dynamic_summary.csv',dynamic_summary);table(run.out/'static_panel_stability.csv',stability)
    return rows,{'static_summary':static_summary,'dynamic_summary':dynamic_summary,'static_panel_stability':stability,
                 'scope':'Descriptive averages here are unweighted task/branch means; selection uses A/B/C-balanced weights.',
                 'measurement_costs':ms}
