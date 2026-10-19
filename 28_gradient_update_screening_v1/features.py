"""Independent F04 feature construction, full marginal controls and frozen F05 diagnostics."""
from pathlib import Path
import numpy as np
from scipy.stats import spearmanr
from common import ROOT,allocations,contexts,context_weight,prefix,table
from outcomes import macro,task_values

PROFILE=['focus', 'cp400', 'p0_0', 'p0_1', 'p0_2', 'p0_3', 'delta_0', 'delta_1', 'delta_2', 'delta_3', 'decline_0', 'decline_1', 'decline_2', 'decline_3']
F05=["reward_scale","target_scale","residual","gap"]
BASE=PROFILE+F05
GROUPS={"Profile":PROFILE,"CriticBase":BASE,"CriticBase_cosine":BASE+["actor_cosine","critic_cosine"],"CriticBase_raw":BASE+["actor_raw","critic_raw"],"CriticBase_F04":BASE+["actor_adam","critic_adam"],"CriticBase_F04_audit":BASE+["actor_audit","critic_audit"],"CriticBase_F04_uniform":BASE+["actor_uniform","critic_uniform"],"Profile_F04":PROFILE+["actor_adam","critic_adam"]}

def role(values,ai):
    return (float(values.mean()),float(values.mean())) if ai==0 else (float(values[ai-1]),float(np.delete(values,ai-1).mean()))

def marginal_features(base,current,ai,cp):
    delta=current-base;bf,bo=role(base,ai);df,do=role(delta,ai)
    row={'focus':int(ai>0),'cp400':int(cp==400000),'initial_focus':bf,'initial_other':bo,'delta_focus':df,'delta_other':do}
    order=sorted(range(4),key=lambda j:(base[j],current[j],j))
    if ai:order=[ai-1]+[j for j in order if j!=ai-1]
    for i,j in enumerate(order):
        row.update({f'p0_{i}':float(base[j]),f'delta_{i}':float(delta[j]),f'decline_{i}':float(max(-delta[j],0))})
    return row

def build(run,p,parents,ys,lengths,splits,refs,measurement=None):
    if measurement is None:raise ValueError('Full measurement directory required')
    md=Path(measurement);ms=run.read(md/'summary.json');manifest=run.read(md/'snapshot_manifest.json')
    run.check('full measurement only',ms['status']=='completed' and not ms['technical_smoke'] and ms['snapshots']==192)
    run.check('same protocol',run.read(md/'sources/protocol.json')==p)
    for item in manifest:
        run.check('evaluated checkpoint identity '+item['id'],item['checkpoint']==refs[item['id']])
        run.hashed(item['raw_path'],item['raw_sha256'])
    dd={}
    for r in run.rows(md/'batch_diagnostics.csv'):dd.setdefault(r['id'],[]).append(r)
    fdir=ROOT/p['f05_measurements'];fs=run.read(fdir/'summary.json')
    run.check('full frozen F05',fs['status']=='completed' and fs['snapshots']==192 and not fs['technical_smoke'])
    for item in run.read(fdir/'snapshot_manifest.json'):run.check('F05 checkpoint same '+item['id'],item['checkpoint']==refs[item['id']])
    fdiag={(r['id'],r['task']):r for r in run.rows(fdir/'task_diagnostics.csv') if r['panel']=='M'}
    rows=[];stability=[]
    for ctx in contexts(p):
        s,n,c=ctx;dix,oix=splits[s];base=task_values(parents[ctx],dix)
        for ri,rep in enumerate(p['continuations'][s]):
            for ai,alloc in enumerate(allocations(p,s)):
                jid=prefix(ctx)+f'_r{rep}_{alloc}_t20';cur=task_values(ys[ctx][0,ri,ai],dix)
                r={'id':jid,'suite':s,'original_seed':n,'checkpoint_step':c,'continuation':rep,'allocation':alloc,'weight':context_weight(ctx)/15,
                    **marginal_features(base,cur,ai,c),'D20':float(cur.mean()),'target_D_remainder':float(macro(ys[ctx][1,ri,ai],dix)-cur.mean()),
                    'O40':float(macro(ys[ctx][1,ri,ai],oix))}
                for name in ['actor','critic']:
                    def values(col,panel):return [float(b[col]) for b in dd[jid] if b['module']==name and b['source_panel']==panel]
                    for suffix,col,panel in [('cosine','raw_cosine','M'),('raw','weighted_alignment','M'),('adam','adam_relative','M'),
                                             ('audit','adam_relative','A'),('uniform','uniform_adam_relative','M')]:
                        vv=values(col,panel);run.check('eight gradient batches '+jid+name+suffix,len(vv)==8)
                        r[name+'_'+suffix]=float(np.mean(vv))
                    mm=np.array(values('adam_relative','M'));aa=np.array(values('adam_relative','A'))
                    stability.append({'id':jid,'suite':s,'original_seed':n,'checkpoint_step':c,'module':name,
                        'M':float(mm.mean()),'A':float(aa.mean()),'M_sd':float(mm.std(ddof=1)),'A_sd':float(aa.std(ddof=1)),
                        'M_negative_batches':int((mm<0).sum()),'panel_sign_agree':int(np.sign(mm.mean())==np.sign(aa.mean())),
                        'batch_sign_mixed':int((mm<0).any() and (mm>0).any()),
                        'negative_raw_pair_fraction':float(np.mean(values('negative_pair_fraction','M'))),
                        'gradient_norm_ratio':float(np.mean(values('gradient_norm_ratio','M'))),
                        'mean_adam_cosine':float(np.mean(values('adam_cosine','M'))),
                        'mean_adam_norm':float(np.mean(values('adam_norm','M')))})
                for key,col in [('reward_scale','reward_rms'),('target_scale','target_rms'),('residual','residual_normalized'),('gap','gap_normalized')]:
                    r[key]=float(np.mean([np.log1p(float(fdiag[jid,t][col])) for t in p['suites'][s]]))
                rows.append(r)
    table(run.out/'gradient_stability.csv',stability)
    summary=[]
    for name in ['actor','critic']:
        rr=[r for r in stability if r['module']==name]
        summary.append({'module':name,'branches':len(rr),'panel_spearman':float(spearmanr([r['M'] for r in rr],[r['A'] for r in rr]).statistic),
            'panel_sign_agreement_pct':float(np.mean([r['panel_sign_agree'] for r in rr])*100),
            'mixed_batch_sign_branches':sum(r['batch_sign_mixed'] for r in rr),
            'mean_negative_raw_pair_pct':float(np.mean([r['negative_raw_pair_fraction'] for r in rr])*100),
            'median_gradient_norm_ratio':float(np.median([r['gradient_norm_ratio'] for r in rr])),
            'negative_mean_adam_descent_branches':sum(r['M']<0 for r in rr)})
    table(run.out/'gradient_stability_summary.csv',summary)
    run.check('180 feature rows',len(rows)==180)
    return rows,{'measurement':str(md),'snapshots':192,'stability':summary,'measurement_costs':ms}

