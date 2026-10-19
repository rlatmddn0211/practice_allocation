"""Paired-case features; no outcome beyond20k enters predictors."""
import numpy as np
from common import allocations, contexts, context_weight, prefix, table
from outcomes import cases, macro, task_values

ROLE=['focus','initial_focus','initial_other','delta_focus','delta_other','cp400']
PROFILE=['focus','cp400']+[f'{field}_{i}' for field in ['p0','delta','decline'] for i in range(4)]
GROUPS={'Role':ROLE,'Profile':PROFILE,'Profile_F01':PROFILE+['excess_focus','excess_other'],
        'Profile_F01_Dhalf1':PROFILE+['excess_half1_focus','excess_half1_other'],
        'Profile_F01_Dhalf2':PROFILE+['excess_half2_focus','excess_half2_other']}

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
    rows=[];pairs=[]
    for ctx in contexts(p):
        s,n,c=ctx;dix,oix=splits[s];initial=cases(parents[ctx],dix);base=initial.mean(-1)
        for ri,rep in enumerate(p['continuations'][s]):
            for ai,alloc in enumerate(allocations(p,s)):
                jid=prefix(ctx)+f'_r{rep}_{alloc}_t20';now=cases(ys[ctx][0,ri,ai],dix);cur=now.mean(-1)
                lost=((initial==1)&(now==0)).sum(-1);gained=((initial==0)&(now==1)).sum(-1)
                excess=np.minimum(lost,gained)/50;capacity=np.minimum.reduce([base,cur,1-base,1-cur])
                run.check('turnover identity '+jid,np.allclose(cur-base,(gained-lost)/50) and np.all(excess<=capacity+1e-12))
                r={'id':jid,'suite':s,'original_seed':n,'checkpoint_step':c,'continuation':rep,'allocation':alloc,
                   'weight':context_weight(ctx)/15,**marginal_features(base,cur,ai,c),'D20':float(cur.mean()),
                   'target_D_remainder':float(macro(ys[ctx][1,ri,ai],dix)-cur.mean()),'O40':float(macro(ys[ctx][1,ri,ai],oix))}
                r['excess_focus'],r['excess_other']=role(excess,ai)
                for hi,sl in enumerate([slice(0,25),slice(25,50)],1):
                    ex=np.minimum(((initial[:,sl]==1)&(now[:,sl]==0)).mean(-1),((initial[:,sl]==0)&(now[:,sl]==1)).mean(-1))
                    r[f'excess_half{hi}_focus'],r[f'excess_half{hi}_other']=role(ex,ai)
                rows.append(r)
                for ti,task in enumerate(p['suites'][s]):
                    pairs.append({'id':jid,'suite':s,'original_seed':n,'checkpoint_step':c,'continuation':rep,'allocation':alloc,'task':task,
                        'initial_success_count':int(initial[ti].sum()),'current_success_count':int(now[ti].sum()),
                        'lost_count':int(lost[ti]),'gained_count':int(gained[ti]),'retained_count':int(((initial[ti]==1)&(now[ti]==1)).sum()),
                        'excess_turnover':float(excess[ti]),'excess_capacity':float(capacity[ti]),
                        'conditional_loss_rate':float(lost[ti]/initial[ti].sum()) if initial[ti].sum() else None,
                        'future_gain_O_pp':float(100*(task_values(ys[ctx][1,ri,ai],oix)[ti]-task_values(ys[ctx][0,ri,ai],oix)[ti]))})
    table(run.out/'paired_task_cases.csv',pairs)
    run.check('branch/task rows',len(rows)==180 and len(pairs)==720)
    identifiable=sum(r['excess_capacity']>1e-12 for r in pairs)
    observed=sum(r['excess_turnover']>1e-12 for r in pairs)
    groups=[]
    for group in ['A200','A400','B200','C200']:
        rr=[r for r in pairs if r['suite']+str(r['checkpoint_step']//1000)==group]
        groups.append({'group':group,'task_branch_rows':len(rr),'identifiable_rows':sum(r['excess_capacity']>1e-12 for r in rr),
                       'observed_excess_rows':sum(r['excess_turnover']>1e-12 for r in rr),'mean_excess_pp':float(np.mean([r['excess_turnover'] for r in rr])*100)})
    table(run.out/'turnover_by_group.csv',groups)
    return rows,{'task_branch_rows':720,'identifiable_rows':identifiable,'observed_excess_rows':observed,
                 'zero_initial_success_missing_conditional_loss':sum(r['conditional_loss_rate'] is None for r in pairs),'groups':groups}
