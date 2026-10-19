"""Independent reconstruction: raw successes, features, augmented-LS fits, choices."""
import argparse
import math
import traceback
from collections import defaultdict
from pathlib import Path
import numpy as np
from common import Run,save,table

def pick(values):
    return next(i for i,v in enumerate(values) if v>=max(values)-1e-12)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('analysis_dir');args=ap.parse_args();run=Run('verify_analysis')
    try:
        src=Path(args.analysis_dir);summ=run.read(src/'summary.json');p=run.read(src/'sources/protocol.json')
        rows=run.rows(src/'features.csv');fits=run.read(src/'ridge_fits.json');preds=run.rows(src/'predictions.csv')
        choices=run.rows(src/'selection_rows.csv');splits=run.read(src/'case_splits.json')
        ms=Path(summ['source_measurements']);diag=run.rows(ms/'task_diagnostics.csv')
        measured={(r['id'],r['task'],r['panel']):r for r in diag}
        outcome={};durations={}
        for entry in run.rows(src/'evaluation_provenance.csv'):
            episodes=run.rows(entry['episodes_path']);run.check('evaluation bytes',run.inputs[entry['episodes_path']]==entry['sha256'])
            suite=entry['id'].split('_')[1];tasks=p['suites'][suite]
            bytask={t:{} for t in tasks}
            for r in episodes:bytask[r['task']][int(r['episode_index'])]=r
            outcome[entry['id']]={};durations[entry['id']]={}
            for split in ['D','O']:
                outcome[entry['id']][split]=[sum(int(bytask[t][i]['success']) for i in splits[suite][split][ti])/50 for ti,t in enumerate(tasks)]
                durations[entry['id']][split]=sum(int(bytask[t][i]['length']) for ti,t in enumerate(tasks) for i in splits[suite][split][ti])
        def close(label,a,b):run.check(label,math.isclose(float(a),float(b),rel_tol=1e-9,abs_tol=1e-10),{'stored':float(a),'reconstructed':float(b)})
        means=lambda values:sum(values)/len(values)
        features={r['id']:r for r in rows}
        for r in rows:
            jid=r['id'];pre=jid.rsplit('_r',1)[0];a=r['allocation'];s=r['suite'];tasks=p['suites'][s]
            initial=outcome[pre+'_base']['D'];current=outcome[jid.replace('_t20','_e20')]['D']
            delta=[b-a for a,b in zip(initial,current)];focus=tasks.index(a[2:]) if a!='U' else None
            def role(v):return (means(v),means(v)) if focus is None else (v[focus],means([x for i,x in enumerate(v) if i!=focus]))
            bf,bo=role(initial);df,do=role(delta)
            expected={'focus':int(focus is not None),'initial_focus':bf,'initial_other':bo,'delta_focus':df,'delta_other':do,
                      'cp400':int(int(r['checkpoint_step'])==400000),'D20':means(current),
                      'target_D_remainder':means(outcome[jid.replace('_t20','_e40')]['D'])-means(current),
                      'O40':means(outcome[jid.replace('_t20','_e40')]['O'])}
            expected['weight']=(1/18 if s=='A' else 1/9)/15
            for key,column,panel in [('residual','residual_normalized','M'),('gap','gap_normalized','M'),
                                     ('residual_audit','residual_normalized','A'),('gap_audit','gap_normalized','A'),
                                     ('residual_raw','residual_rms','M'),('gap_raw','gap_rms','M'),
                                     ('reward_scale','reward_rms','M'),('target_scale','target_rms','M')]:
                expected[key]=means([math.log1p(float(measured[jid,t,panel][column])) for t in tasks])
            for k,v in expected.items():close('feature '+jid+k,r[k],v)
        original_preds={(r['method'],r['id']):float(r['predicted40']) for r in preds};recalc={}
        for fit in fits:
            held=fit['held_original_seed'];cols=fit['features'];method=fit['method']
            training=[r for r in rows if int(r['original_seed'])!=held];test=[r for r in rows if int(r['original_seed'])==held]
            run.check('no original seed leakage '+str((method,held)),set(fit['train_ids'])=={r['id'] for r in training} and set(fit['test_ids'])=={r['id'] for r in test})
            run.check('no future feature '+method,not set(cols)&{'O40','target_D_remainder','continuation','original_seed','suite'})
            x=np.array([[float(r[c]) for c in cols] for r in training]);w=np.array([float(r['weight']) for r in training]);w/=sum(w)
            y=np.array([float(r['target_D_remainder']) for r in training]);mu=np.average(x,axis=0,weights=w)
            sd=np.sqrt(np.average((x-mu)**2,axis=0,weights=w));sd[sd<1e-12]=1
            z=np.column_stack([np.ones(len(x)),(x-mu)/sd]);penalty=np.zeros((len(cols),len(cols)+1));penalty[:,1:]=np.eye(len(cols))
            aa=np.vstack([np.sqrt(w[:,None])*z,penalty]);bb=np.concatenate([np.sqrt(w)*y,np.zeros(len(cols))])
            beta=np.linalg.lstsq(aa,bb,rcond=None)[0]
            close('ridge intercept '+str((method,held)),fit['intercept'],beta[0])
            for k in range(len(cols)):
                close('ridge coefficient '+str((method,held,k)),fit['coef'][k],beta[k+1])
                close('fold mean',fit['mean'][k],mu[k]);close('fold scale',fit['scale'][k],sd[k])
            for r in test:
                value=float(r['D20'])+float(np.dot(np.r_[1,(np.array([float(r[c]) for c in cols])-mu)/sd],beta))
                recalc[method,r['id']]=value;close('held prediction '+r['id']+method,original_preds[method,r['id']],value)
        summary_groups=defaultdict(list);switches=defaultdict(int);identity={}
        for r in choices:
            s=r['suite'];n=int(r['original_seed']);cp=int(r['checkpoint_step']);rep=int(r['continuation']);mode=r['mode'];method=r['method']
            pre=f"{'E1' if s=='A' else 'E3'}_{s}_s{n}_c{cp//1000}"
            names=['U']+['F_'+t for t in p['suites'][s]]
            diagnostic=[rep] if mode=='same_repeat' else [x for x in p['continuations'][s] if x!=rep]
            fixed_vals=[]
            for a in names:
                vals=[means(outcome[f"{'E1' if s=='A' else 'E3'}_{s}_s{other}_c{cp//1000}_r{rr}_{a}_e40"]['D']) for other in p['original_seeds'] if other!=n for rr in p['continuations'][s]]
                fixed_vals.append(means(vals))
            fixed=pick(fixed_vals)
            if method=='Uniform':expected=0
            elif method=='Failure':expected=1+int(np.argmin(outcome[pre+'_base']['D']))
            elif method=='Development_fixed':expected=fixed
            elif method=='Greedy20':expected=pick([means([means(outcome[pre+f'_r{rr}_{a}_e20']['D']) for rr in diagnostic]) for a in names])
            else:expected=pick([means([recalc[method,pre+f'_r{rr}_{a}_t20'] for rr in diagnostic]) for a in names])
            run.check('choice '+str((pre,rep,mode,method)),int(r['allocation_index'])==expected and r['selected_allocation']==names[expected])
            vals=[means(outcome[pre+f'_r{rep}_{a}_e40']['O'])*100 for a in names]
            parent=means(outcome[pre+'_base']['O'])*100
            results={'score_pp':vals[expected],'vs_uniform_pp':vals[expected]-vals[0],'vs_fixed_pp':vals[expected]-vals[fixed],
                     'absolute_gain_pp':vals[expected]-parent,'hindsight_regret_pp':max(vals)-vals[expected],
                     'max_task_drop_pp':max(a-b for a,b in zip(outcome[pre+'_base']['O'],outcome[pre+f'_r{rep}_{names[expected]}_e40']['O']))*100,
                     'weight':(1/18 if s=='A' else 1/9)/3}
            if method in ['Uniform','Failure','Development_fixed']:results.update(simulated_probe_training_steps=0,simulated_selection_eval_steps=0)
            else:results.update(simulated_probe_training_steps=100000*len(diagnostic),simulated_selection_eval_steps=sum(durations[pre+f'_r{rr}_{a}_e20']['D'] for rr in diagnostic for a in names))
            for k,v in results.items():close('choice metric '+k,r[k],v)
            results.update(suite=s,original_seed=n,checkpoint_step=cp,mode=mode,method=method,continuation=rep)
            summary_groups[mode,method].append(results)
            identity[pre,rep,mode,method]=expected
        for r in choices:
            s=r['suite'];pre=f"{'E1' if s=='A' else 'E3'}_{s}_s{r['original_seed']}_c{int(r['checkpoint_step'])//1000}"
            base=next(b for b in choices if b['suite']==s and b['original_seed']==r['original_seed'] and b['checkpoint_step']==r['checkpoint_step'] and b['continuation']==r['continuation'] and b['mode']==r['mode'] and b['method']=='Base_scale')
            close('increment vs base',r['vs_base_scale_pp'],float(r['score_pp'])-float(base['score_pp']))
            if r['method'].startswith('Base_scale_'):
                switches[r['mode'],r['method']]+=int(r['selected_allocation']!=base['selected_allocation'])
        for filename,extra in [('selection_summary.csv',None),('selection_by_seed.csv','original_seed'),('selection_by_group.csv','group')]:
            for r in run.rows(src/filename):
                rr=summary_groups[r['mode'],r['method']]
                if extra=='original_seed':rr=[x for x in rr if x['original_seed']==int(r['original_seed'])]
                if extra=='group':rr=[x for x in rr if x['suite']+str(x['checkpoint_step']//1000)==r['group']]
                for field in ['score_pp','vs_uniform_pp','vs_fixed_pp','absolute_gain_pp','hindsight_regret_pp','max_task_drop_pp','simulated_probe_training_steps','simulated_selection_eval_steps']:
                    close('aggregate '+filename+field,r[field],sum(x['weight']*x[field] for x in rr)/sum(x['weight'] for x in rr))
        changes=[{'mode':k[0],'method':k[1],'changed_choices_of36':v} for k,v in switches.items()]
        table(run.out/'choice_changes.csv',changes)
        run.finish({'status':'completed','source':str(src),'raw_evaluation_rows':len(outcome)*400,'features_verified':len(rows),
                    'ridge_fits_verified':len(fits),'predictions_verified':len(recalc),'selections_verified':len(choices),'choice_changes':changes})
    except Exception:
        run.finish({'status':'failed','traceback':traceback.format_exc()});raise

if __name__=='__main__':main()
