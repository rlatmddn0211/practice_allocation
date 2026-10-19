"""F05 retrospective held-original-seed prediction and allocation selection."""
from __future__ import annotations
import argparse
import hashlib
import itertools
import json
import traceback
from collections import defaultdict
from pathlib import Path
import numpy as np
from scipy.stats import spearmanr
from common import Run,HERE,allocations,campaign,contexts,context_weight,prefix,record,save,table

BASE=['focus','initial_focus','initial_other','delta_focus','delta_other','cp400']
SCALE=['reward_scale','target_scale']
GROUPS={'Base':BASE,'Base_scale':BASE+SCALE,
        'Base_scale_F05':BASE+SCALE+['residual','gap'],
        'Base_scale_F05_audit_panel':BASE+SCALE+['residual_audit','gap_audit'],
        'Base_scale_raw_F05':BASE+SCALE+['residual_raw','gap_raw']}

def choose(values):
    return int(np.flatnonzero(np.asarray(values)>=np.max(values)-1e-12)[0])

def read_outcomes(run,p):
    cam,planned=campaign(run);bankmaps={};splits={};rows=[]
    for s,tasks in p['suites'].items():
        stage='E1' if s=='A' else 'E3'
        rec,_=record(run,cam,planned,stage+'_'+s+'_bank')
        bank=run.read(rec['bank']['path'],rec['bank']['sha256'])
        entries={(e['task'],e['episode_index']):e for e in bank['outcome']}
        bankmaps[s]=entries
        d=[];o=[]
        for task in tasks:
            ix=sorted(range(100),key=lambda i:hashlib.sha256(('F07-v1|'+s+'|'+task+'|'+entries[task,i]['initial_state_hash']).encode()).hexdigest())
            d.append(ix[:50]);o.append(ix[50:])
        splits[s]=np.array(d),np.array(o)
    def read_eval(ctx,jid):
        s,seed,cp=ctx;rec,path=record(run,cam,planned,jid)
        request=run.read(path.parent/'request.json')
        run.check('frozen evaluation '+jid,rec['kind']=='evaluate' and rec['evaluation_state_unchanged'] and request['bank_kind']=='outcome' and not request['technical_smoke'])
        episodes=run.rows(rec['episodes_path']);run.check('episode hash '+jid,run.inputs[rec['episodes_path']]==rec['episodes_sha256'])
        y=np.full((4,100),np.nan);length=np.zeros((4,100),int)
        for e in episodes:
            t=p['suites'][s].index(e['task']);i=int(e['episode_index']);bc=bankmaps[s][e['task'],i]
            if not (np.isnan(y[t,i]) and e['initial_state_hash']==bc['initial_state_hash'] and int(e['seed'])==bc['seed']):
                raise AssertionError('case mismatch '+jid)
            y[t,i]=int(e['success']);length[t,i]=int(e['length'])
        run.check('400 binary rows '+jid,len(episodes)==400 and np.isin(y,[0,1]).all())
        run.check('macro matches '+jid,abs(y.mean()-rec['evaluation']['macro_success'])<1e-12)
        run.check('cost matches '+jid,int(length.sum())==rec['evaluation']['environment_steps'])
        for ti,task in enumerate(p['suites'][s]):run.check('task counts '+jid+task,int(y[ti].sum())==rec['evaluation']['success_counts'][task])
        rows.append({'id':jid,'episodes_path':rec['episodes_path'],'sha256':rec['episodes_sha256'],'macro_success':float(y.mean())})
        return y,length,request['parent']
    parents={};ys={};lens={};checkpoint_refs={}
    for ctx in contexts(p):
        s,n,c=ctx;pre=prefix(ctx)
        parents[ctx],_,checkpoint_refs[pre+'_base']=read_eval(ctx,pre+'_base')
        ys[ctx]=np.zeros((2,3,5,4,100));lens[ctx]=np.zeros_like(ys[ctx],dtype=int)
        for hi,h in enumerate([20,40]):
            for ri,rep in enumerate(p['continuations'][s]):
                for ai,a in enumerate(allocations(p,s)):
                    yy,ll,ref=read_eval(ctx,pre+f'_r{rep}_{a}_e{h}')
                    ys[ctx][hi,ri,ai]=yy;lens[ctx][hi,ri,ai]=ll
                    if h==20:checkpoint_refs[pre+f'_r{rep}_{a}_t20']=ref
        print('outcomes',ctx,flush=True)
    table(run.out/'evaluation_provenance.csv',rows)
    save(run.out/'case_splits.json',{s:{'D':d.tolist(),'O':o.tolist()} for s,(d,o) in splits.items()})
    run.check('148800 raw rows',len(rows)*400==148800)
    return parents,ys,lens,splits,checkpoint_refs

def cases(y,ix):
    return np.take_along_axis(y,np.broadcast_to(ix,y.shape[:-1]+(ix.shape[-1],)),axis=-1)

def macro(y,ix):
    return cases(y,ix).mean(axis=(-1,-2))

def task_values(y,ix):
    return cases(y,ix).mean(-1)

def fit_predict(run,rows,features,held,method):
    train=[r for r in rows if r['original_seed']!=held];test=[r for r in rows if r['original_seed']==held]
    x=np.array([[r[k] for k in features] for r in train]);xt=np.array([[r[k] for k in features] for r in test])
    w=np.array([r['weight'] for r in train]);w/=w.sum()
    y=np.array([r['target_D_remainder'] for r in train])
    mu=w@x;sd=np.sqrt(w@((x-mu)**2));sd=np.where(sd>1e-12,sd,1.)
    z=(x-mu)/sd;zt=(xt-mu)/sd;ym=float(w@y)
    coef=np.linalg.solve(z.T@(w[:,None]*z)+np.eye(len(features)),z.T@(w*(y-ym)))
    pred=ym+zt@coef
    run.check('original seed excluded '+str((method,held)),all(r['original_seed']!=held for r in train))
    artifact={'method':method,'held_original_seed':held,'features':features,'train_ids':[r['id'] for r in train],
              'test_ids':[r['id'] for r in test],'mean':mu.tolist(),'scale':sd.tolist(),'intercept':ym,'coef':coef.tolist(),'penalty':1.}
    return {r['id']:float(r['D20']+v) for r,v in zip(test,pred)},artifact

def average(rows,field):
    return float(np.average([r[field] for r in rows],weights=[r['weight'] for r in rows]))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('measure_dir');args=ap.parse_args();run=Run('analysis')
    try:
        p=run.read(HERE/'protocol.json');md=Path(args.measure_dir)
        ms=run.read(md/'summary.json');mp=run.read(md/'sources/protocol.json')
        run.check('full scientific measurement',ms['status']=='completed' and not ms['technical_smoke'] and ms['snapshots']==192)
        run.check('same measurement protocol',mp==p)
        diag=run.rows(md/'task_diagnostics.csv');manifest=run.read(md/'snapshot_manifest.json')
        parents,ys,lengths,splits,refs=read_outcomes(run,p)
        for item in manifest:run.check('measured evaluated checkpoint '+item['id'],item['checkpoint']==refs[item['id']])
        dd=defaultdict(dict)
        for r in diag:dd[r['id']][r['task'],r['panel']]=r
        features=[];stability=[];task_associations=[]
        for jid,d in dd.items():
            for ti,task in enumerate(p['suites'][next(iter(d.values()))['suite']]):
                m,a=d[task,'M'],d[task,'A']
                for name in ['residual_normalized','gap_normalized']:
                    mv,av=float(m[name]),float(a[name])
                    stability.append({'id':jid,'suite':m['suite'],'original_seed':int(m['original_seed']),
                                      'horizon':int(m['horizon']),'task':task,'metric':name,'M':mv,'A':av,
                                      'symmetric_relative_difference_pct':200*abs(mv-av)/max(abs(mv)+abs(av),1e-12)})
        for ctx,y in ys.items():
            s,n,c=ctx;dix,oix=splits[s];base=task_values(parents[ctx],dix)
            for ri,rep in enumerate(p['continuations'][s]):
                for ai,alloc in enumerate(allocations(p,s)):
                    jid=prefix(ctx)+f'_r{rep}_{alloc}_t20'
                    d20=task_values(y[0,ri,ai],dix);delta=d20-base
                    focus=ai-1 if ai else None
                    def role(v):return (float(v.mean()),float(v.mean())) if focus is None else (float(v[focus]),float(np.delete(v,focus).mean()))
                    bf,bo=role(base);df,do=role(delta)
                    row={'id':jid,'suite':s,'original_seed':n,'checkpoint_step':c,'continuation':rep,'allocation':alloc,
                         'weight':context_weight(ctx)/15,'focus':int(ai>0),'initial_focus':bf,'initial_other':bo,
                         'delta_focus':df,'delta_other':do,'cp400':int(c==400000),'D20':float(d20.mean()),
                         'target_D_remainder':float(macro(y[1,ri,ai],dix)-d20.mean()),'O40':float(macro(y[1,ri,ai],oix))}
                    for key,col,panel in [('residual','residual_normalized','M'),('gap','gap_normalized','M'),
                                         ('residual_audit','residual_normalized','A'),('gap_audit','gap_normalized','A'),
                                         ('residual_raw','residual_rms','M'),('gap_raw','gap_rms','M'),
                                         ('reward_scale','reward_rms','M'),('target_scale','target_rms','M')]:
                        row[key]=float(np.mean([np.log1p(float(dd[jid][task,panel][col])) for task in p['suites'][s]]))
                    features.append(row)
                    for ti,task in enumerate(p['suites'][s]):
                        task_associations.append({'id':jid,'suite':s,'original_seed':n,'checkpoint_step':c,'task':task,
                            'D20':float(d20[ti]),'initial_D':float(base[ti]),'short_gain_D':float(delta[ti]),
                            'future_gain_O_pp':float(100*(task_values(y[1,ri,ai],oix)[ti]-task_values(y[0,ri,ai],oix)[ti])),
                            'residual_normalized':float(dd[jid][task,'M']['residual_normalized']),
                            'gap_normalized':float(dd[jid][task,'M']['gap_normalized'])})
        run.check('180 branch feature rows',len(features)==180)
        table(run.out/'features.csv',features);table(run.out/'panel_stability.csv',stability)
        table(run.out/'task_diagnostic_future_pairs.csv',task_associations)
        stability_summary=[]
        for metric in ['residual_normalized','gap_normalized']:
            for h in [0,20000]:
                rr=[r for r in stability if r['metric']==metric and r['horizon']==h]
                corr=float(spearmanr([r['M'] for r in rr],[r['A'] for r in rr]).statistic)
                stability_summary.append({'metric':metric,'horizon':h,'pairs':len(rr),'spearman':corr,
                    'median_symmetric_relative_difference_pct':float(np.median([r['symmetric_relative_difference_pct'] for r in rr])),
                    'p90_symmetric_relative_difference_pct':float(np.quantile([r['symmetric_relative_difference_pct'] for r in rr],.9))})
        # Descriptive associations, NOT feature selection or significance tests.
        associations=[]
        for metric in ['residual_normalized','gap_normalized']:
            for group in ['A200','A400','B200','C200']:
                rr=[r for r in task_associations if r['suite']+str(r['checkpoint_step']//1000)==group]
                associations.append({'group':group,'metric':metric,'rows':len(rr),
                     'spearman_with_future_task_gain':float(spearmanr([r[metric] for r in rr],[r['future_gain_O_pp'] for r in rr]).statistic),
                     'scope':'descriptive confounded association; dependent task rows, no p-value or causal claim'})
        table(run.out/'diagnostic_associations.csv',associations)
        predictions={};fits=[]
        for method,cols in GROUPS.items():
            predictions[method]={}
            for held in p['original_seeds']:
                pred,fit=fit_predict(run,features,cols,held,method);predictions[method].update(pred);fits.append(fit)
        save(run.out/'ridge_fits.json',fits)
        table(run.out/'predictions.csv',[{'id':r['id'],'method':m,'predicted40':pr[r['id']],
                'observed_O40':r['O40'],'absolute_error_pp':abs(pr[r['id']]-r['O40'])*100} for m,pr in predictions.items() for r in features])
        selected=[];fixed_records=[];pred_metrics=[]
        for method,pr in predictions.items():
            pred_metrics.append({'method':method,'held_original_seed_O40_MAE_pp':float(sum(r['weight']*abs(pr[r['id']]-r['O40'])*100 for r in features))})
        for ctx,y in ys.items():
            s,n,c=ctx;dix,oix=splits[s];names=allocations(p,s);baseO=macro(parents[ctx],oix)
            fixed_values=np.mean([macro(ys[other][1],dix).mean(0) for other in ys if other[0]==s and other[2]==c and other[1]!=n],axis=0)
            fixed=choose(fixed_values);fixed_records.append({'suite':s,'original_seed':n,'checkpoint_step':c,'allocation':names[fixed],'D40_values':fixed_values.tolist()})
            failure=1+int(np.argmin(task_values(parents[ctx],dix)))
            for mode in ['same_repeat','cross_repeat']:
                for ri,rep in enumerate(p['continuations'][s]):
                    diagnostic_repeats=[ri] if mode=='same_repeat' else [j for j in range(3) if j!=ri]
                    d20=macro(y[0,diagnostic_repeats],dix).mean(0)
                    choices={'Uniform':0,'Failure':failure,'Development_fixed':fixed,'Greedy20':choose(d20)}
                    prediction_scores={}
                    for method,pr in predictions.items():
                        values=[np.mean([pr[prefix(ctx)+f'_r{p["continuations"][s][j]}_{a}_t20'] for j in diagnostic_repeats]) for a in names]
                        choices[method]=choose(values);prediction_scores[method]=values
                    outcome=macro(y[1,ri],oix);best=float(outcome.max())
                    for method,ai in choices.items():
                        cost_eval=int(cases(lengths[ctx][0,diagnostic_repeats],dix).sum()) if method not in ['Uniform','Failure','Development_fixed'] else 0
                        selected.append({'suite':s,'original_seed':n,'checkpoint_step':c,'continuation':rep,'mode':mode,'method':method,
                             'selected_allocation':names[ai],'allocation_index':ai,'weight':context_weight(ctx)/3,
                             'score_pp':float(outcome[ai]*100),'vs_uniform_pp':float((outcome[ai]-outcome[0])*100),
                             'vs_fixed_pp':float((outcome[ai]-outcome[fixed])*100),
                             'absolute_gain_pp':float((outcome[ai]-baseO)*100),'hindsight_regret_pp':float((best-outcome[ai])*100),
                             'max_task_drop_pp':float(np.max(task_values(parents[ctx],oix)-task_values(y[1,ri,ai],oix))*100),
                             'simulated_probe_training_steps':len(diagnostic_repeats)*100000 if cost_eval else 0,
                             'simulated_selection_eval_steps':cost_eval})
        key=lambda r:tuple(r[k] for k in ['suite','original_seed','checkpoint_step','continuation','mode'])
        baseline={key(r):r for r in selected if r['method']=='Base_scale'}
        for r in selected:r['vs_base_scale_pp']=r['score_pp']-baseline[key(r)]['score_pp']
        table(run.out/'selection_rows.csv',selected);save(run.out/'development_fixed.json',fixed_records)
        summaryrows=[];group_rows=[];seed_rows=[]
        metrics=['score_pp','vs_uniform_pp','vs_fixed_pp','vs_base_scale_pp','absolute_gain_pp','hindsight_regret_pp','max_task_drop_pp','simulated_probe_training_steps','simulated_selection_eval_steps']
        for mode in ['same_repeat','cross_repeat']:
            for method in ['Uniform','Failure','Development_fixed','Greedy20']+list(GROUPS):
                rr=[r for r in selected if r['mode']==mode and r['method']==method]
                summaryrows.append({'mode':mode,'method':method,**{k:average(rr,k) for k in metrics}})
                for n in p['original_seeds']:
                    rrr=[r for r in rr if r['original_seed']==n]
                    seed_rows.append({'mode':mode,'method':method,'original_seed':n,**{k:average(rrr,k) for k in metrics}})
                for group in ['A200','A400','B200','C200']:
                    rrr=[r for r in rr if r['suite']+str(r['checkpoint_step']//1000)==group]
                    group_rows.append({'mode':mode,'method':method,'group':group,**{k:average(rrr,k) for k in metrics}})
        table(run.out/'selection_summary.csv',summaryrows);table(run.out/'selection_by_seed.csv',seed_rows)
        table(run.out/'selection_by_group.csv',group_rows);table(run.out/'prediction_metrics.csv',pred_metrics)
        table(run.out/'panel_stability_summary.csv',stability_summary)
        # Conditional uncertainty only in the final O-case scoring, choices fixed.
        rng=np.random.default_rng(p['bootstrap_seed']);draws=p['bootstrap_draws']
        weights={s:rng.multinomial(50,np.full(50,.02),size=(draws,4)) for s in p['suites']}
        intervals=[]
        for mode in ['same_repeat','cross_repeat']:
            for comparator in ['Base_scale','Development_fixed','Greedy20']:
                rr=[r for r in selected if r['mode']==mode and r['method']=='Base_scale_F05']
                cc={key(r):r for r in selected if r['mode']==mode and r['method']==comparator}
                boot=np.zeros(draws);point=0.
                for r in rr:
                    ctx=r['suite'],r['original_seed'],r['checkpoint_step'];s=ctx[0]
                    ri=p['continuations'][s].index(r['continuation']);ci=cc[key(r)]['allocation_index']
                    diff=np.take_along_axis(ys[ctx][1,ri,r['allocation_index']]-ys[ctx][1,ri,ci],splits[s][1],axis=-1)
                    boot+=r['weight']*100*np.einsum('dti,ti->d',weights[s],diff)/200
                    point+=r['weight']*100*float(diff.mean())
                intervals.append({'mode':mode,'comparator':comparator,'increment_pp':point,
                                  'case_only_lo_pp':float(np.quantile(boot,.025)),'case_only_hi_pp':float(np.quantile(boot,.975)),
                                  'scope':'fixed learned policies, fits, diagnostic cases and selections; jointly resampled O cases only'})
        table(run.out/'conditional_case_intervals.csv',intervals)
        prim=next(r for r in summaryrows if r['mode']=='same_repeat' and r['method']=='Base_scale_F05')
        seeds=[r['vs_base_scale_pp'] for r in seed_rows if r['mode']=='same_repeat' and r['method']=='Base_scale_F05']
        groups=[r['vs_base_scale_pp'] for r in group_rows if r['mode']=='same_repeat' and r['method']=='Base_scale_F05']
        passing=prim['vs_base_scale_pp']>=1 and sum(v>0 for v in seeds)>=2 and min(groups)>=-2
        run.finish({'status':'completed','source_measurements':str(md),'feature_rows':len(features),'original_seed_blocks':p['original_seeds'],
                    'primary':prim,'primary_original_seed_increments_pp':seeds,'primary_group_increments_pp':groups,
                    'operational_screen_pass':passing,'screen_is_not_independent_confirmation':True,
                    'panel_stability':stability_summary,'prediction_metrics':pred_metrics,'conditional_intervals':intervals,
                    'F05_scope_remaining':['matched-length return/success calibration','true soft-value calibration','4k diagnostics','new original-seed confirmation','cost-inclusive online allocation']})
    except Exception:
        run.finish({'status':'failed','traceback':traceback.format_exc()});raise

if __name__=='__main__':main()
