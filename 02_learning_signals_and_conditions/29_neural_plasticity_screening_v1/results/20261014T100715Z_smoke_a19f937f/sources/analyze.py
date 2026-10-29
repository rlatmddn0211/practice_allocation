"""Held-original-seed prediction and retrospective allocation comparison."""
import argparse
import traceback
from pathlib import Path
import numpy as np
from common import Run,HERE,allocations,contexts,context_weight,prefix,save,table
from outcomes import read_outcomes,cases,macro,task_values
from features import GROUPS,build

def choose(values):
    return int(np.flatnonzero(np.asarray(values)>=np.max(values)-1e-12)[0])

def fit(rows,cols,held,method):
    tr=[r for r in rows if r['original_seed']!=held];te=[r for r in rows if r['original_seed']==held]
    x=np.array([[r[k] for k in cols] for r in tr]);xt=np.array([[r[k] for k in cols] for r in te])
    w=np.array([r['weight'] for r in tr]);w/=w.sum();y=np.array([r['target_D_remainder'] for r in tr])
    mu=w@x;sd=np.sqrt(w@((x-mu)**2));sd=np.where(sd>1e-12,sd,1.);z=(x-mu)/sd;ym=float(w@y)
    beta=np.linalg.solve(z.T@(w[:,None]*z)+np.eye(len(cols)),z.T@(w*(y-ym)))
    pred=ym+(xt-mu)/sd@beta
    return {r['id']:float(r['D20']+v) for r,v in zip(te,pred)}, {'method':method,'held_original_seed':held,'features':cols,
        'train_ids':[r['id'] for r in tr],'test_ids':[r['id'] for r in te],'mean':mu.tolist(),'scale':sd.tolist(),
        'intercept':ym,'coef':beta.tolist(),'penalty':1.}

def avg(rows,k):return float(np.average([r[k] for r in rows],weights=[r['weight'] for r in rows]))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--measurement');args=ap.parse_args();run=Run('analysis')
    try:
        p=run.read(HERE/'protocol.json');parents,ys,lengths,splits,refs=read_outcomes(run,p)
        rows,diagnostics=build(run,p,parents,ys,lengths,splits,refs,args.measurement)
        table(run.out/'features.csv',rows);predictions={};fits=[];errors=[]
        for method,cols in GROUPS.items():
            predictions[method]={}
            for held in p['original_seeds']:
                pr,ff=fit(rows,cols,held,method);predictions[method].update(pr);fits.append(ff)
            errors.append({'method':method,'O40_MAE_pp':sum(r['weight']*abs(predictions[method][r['id']]-r['O40'])*100 for r in rows)})
        save(run.out/'ridge_fits.json',fits);table(run.out/'prediction_metrics.csv',errors)
        table(run.out/'predictions.csv',[{'id':r['id'],'method':m,'predicted40':pr[r['id']],'observed_O40':r['O40']} for m,pr in predictions.items() for r in rows])
        selected=[];methods=['Uniform','Failure','Development_fixed','Greedy20']+list(GROUPS)
        for ctx,y in ys.items():
            s,n,c=ctx;dix,oix=splits[s];names=allocations(p,s)
            fixed=choose(np.mean([macro(ys[o][1],dix).mean(0) for o in ys if o[0]==s and o[2]==c and o[1]!=n],axis=0))
            failure=1+int(np.argmin(task_values(parents[ctx],dix)))
            # Reconstruct parent evaluation duration directly; previously only success was returned.
            from common import campaign,record
            cam,planned=campaign(run);br,_=record(run,cam,planned,prefix(ctx)+'_base')
            parent_rows=run.rows(br['episodes_path']);parent_eval=sum(int(e['length']) for e in parent_rows if int(e['episode_index']) in dix[p['suites'][s].index(e['task'])])
            for mode in ['same_repeat','cross_repeat']:
                for ri,rep in enumerate(p['continuations'][s]):
                    dr=[ri] if mode=='same_repeat' else [j for j in range(3) if j!=ri]
                    choice={'Uniform':0,'Failure':failure,'Development_fixed':fixed,'Greedy20':choose(macro(y[0,dr],dix).mean(0))}
                    for method,pr in predictions.items():
                        choice[method]=choose([np.mean([pr[prefix(ctx)+f'_r{p["continuations"][s][j]}_{a}_t20'] for j in dr]) for a in names])
                    val=macro(y[1,ri],oix)*100
                    for method,ai in choice.items():
                        probes=method not in ['Uniform','Failure','Development_fixed']
                        selected.append({'suite':s,'original_seed':n,'checkpoint_step':c,'continuation':rep,'mode':mode,'method':method,
                            'selected_allocation':names[ai],'allocation_index':ai,'weight':context_weight(ctx)/3,'score_pp':float(val[ai]),
                            'vs_uniform_pp':float(val[ai]-val[0]),'vs_fixed_pp':float(val[ai]-val[fixed]),
                            'absolute_gain_pp':float(val[ai]-macro(parents[ctx],oix)*100),'hindsight_regret_pp':float(val.max()-val[ai]),
                            'max_task_drop_pp':float(max(task_values(parents[ctx],oix)-task_values(y[1,ri,ai],oix))*100),
                            'probe_training_steps':len(dr)*100000 if probes else 0,
                            'total_training_steps':(120000 if mode=='same_repeat' else 240000) if probes else 40000,
                            'parent_D_eval_steps':parent_eval if method not in ['Uniform','Development_fixed','Greedy20'] else 0,
                            'probe_D_eval_steps':int(cases(lengths[ctx][0,dr],dix).sum()) if probes else 0})
        key=lambda r:tuple(r[k] for k in ['suite','original_seed','checkpoint_step','continuation','mode'])
        base={key(r):r for r in selected if r['method']==p['primary_comparator']}
        greedy={key(r):r for r in selected if r['method']=='Greedy20'}
        for r in selected:
            r['vs_base_pp']=r['score_pp']-base[key(r)]['score_pp'];r['vs_greedy_pp']=r['score_pp']-greedy[key(r)]['score_pp']
            r['changed_vs_base']=int(r['allocation_index']!=base[key(r)]['allocation_index'])
        table(run.out/'selection_rows.csv',selected)
        metrics=['score_pp','vs_uniform_pp','vs_fixed_pp','vs_base_pp','vs_greedy_pp','absolute_gain_pp','hindsight_regret_pp',
                 'max_task_drop_pp','probe_training_steps','total_training_steps','parent_D_eval_steps','probe_D_eval_steps']
        aggregates={}
        for fname,split in [('selection_summary',None),('selection_by_seed','original_seed'),('selection_by_group','group')]:
            out=[]
            for mode in ['same_repeat','cross_repeat']:
                for method in methods:
                    rr=[r for r in selected if r['mode']==mode and r['method']==method]
                    parts=[None] if split is None else p['original_seeds'] if split=='original_seed' else ['A200','A400','B200','C200']
                    for part in parts:
                        sub=rr if part is None else [r for r in rr if (r['original_seed'] if split=='original_seed' else r['suite']+str(r['checkpoint_step']//1000))==part]
                        out.append({'mode':mode,'method':method,**({split:part} if split else {}),**{k:avg(sub,k) for k in metrics},
                                    'changed_choices':sum(r['changed_vs_base'] for r in sub),'choices':len(sub)})
            table(run.out/(fname+'.csv'),out);aggregates[fname]=out
        rng=np.random.default_rng(p['bootstrap_seed']);draws=p['bootstrap_draws']
        weights={s:rng.multinomial(50,np.full(50,.02),size=(draws,4)) for s in p['suites']};intervals=[]
        for mode in ['same_repeat','cross_repeat']:
            for comp in [p['primary_comparator'],'Greedy20','Development_fixed']:
                rr=[r for r in selected if r['mode']==mode and r['method']==p['primary_model']]
                cc={key(r):r for r in selected if r['method']==comp};boot=np.zeros(draws);point=0.
                for r in rr:
                    ctx=r['suite'],r['original_seed'],r['checkpoint_step'];s=ctx[0];ri=p['continuations'][s].index(r['continuation'])
                    diff=cases(ys[ctx][1,ri,r['allocation_index']]-ys[ctx][1,ri,cc[key(r)]['allocation_index']],splits[s][1])
                    boot+=r['weight']*100*np.einsum('dti,ti->d',weights[s],diff)/200;point+=r['weight']*100*diff.mean()
                intervals.append({'mode':mode,'comparator':comp,'increment_pp':float(point),'case_only_lo_pp':float(np.quantile(boot,.025)),
                                  'case_only_hi_pp':float(np.quantile(boot,.975))})
        table(run.out/'conditional_case_intervals.csv',intervals)
        primary=next(r for r in aggregates['selection_summary'] if r['mode']=='same_repeat' and r['method']==p['primary_model'])
        seeds=[r['vs_base_pp'] for r in aggregates['selection_by_seed'] if r['mode']=='same_repeat' and r['method']==p['primary_model']]
        groups=[r['vs_base_pp'] for r in aggregates['selection_by_group'] if r['mode']=='same_repeat' and r['method']==p['primary_model']]
        run.finish({'status':'completed','factor':p['factor'],'measurement':args.measurement,'feature_rows':len(rows),'diagnostics':diagnostics,
                    'primary':primary,'original_seed_increments_pp':seeds,'group_increments_pp':groups,
                    'operational_screen_pass':primary['vs_base_pp']>=1 and sum(v>0 for v in seeds)>=2 and min(groups)>=-2,
                    'prediction_metrics':errors,'conditional_intervals':intervals,'independent_confirmation':False})
    except Exception:
        run.finish({'status':'failed','traceback':traceback.format_exc()});raise

if __name__=='__main__':main()
