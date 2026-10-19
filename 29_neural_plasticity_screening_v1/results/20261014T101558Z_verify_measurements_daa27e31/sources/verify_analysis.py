"""Independent raw-case reconstruction, augmented least squares and all choices."""
import argparse
import hashlib
import math
import traceback
from collections import defaultdict
from pathlib import Path
import numpy as np
from common import Run,ROOT,save,table

def derive_diagnostics(raw):
    result={};bylayer={}
    for row in raw['static']:
        activation=row['neuron_mean_abs'];average=sum(activation)/len(activation)
        ratios=[v/average if average else 0 for v in activation];power=row['power'];total=sum(power)
        entropy=-sum((v/total)*math.log(v/total) for v in power if v>0) if total else None
        bylayer[row['task'],row['panel'],row['module']]={'dormant':sum(v<=.01 for v in ratios)/len(ratios),
            'dormant_zero':sum(v<=0 for v in ratios)/len(ratios),'dormant_tenth':sum(v<=.1 for v in ratios)/len(ratios),
            'erank':math.exp(entropy)/min(row['rows'],row['width']) if total else 0}
    for key,panel,field in [('dormant','M','dormant'),('dormant_zero','M','dormant_zero'),('dormant_tenth','M','dormant_tenth'),
                            ('erank','M','erank'),('dormant_audit','A','dormant'),('erank_audit','A','erank')]:
        result[key]=sum((.125 if module=='actor' else .0625)*values[field] for (task,pi,module),values in bylayer.items() if pi==panel)
    states=[r for r in raw['states'] if r['panel']=='M'];result['state_spread']=sum(math.log1p(math.sqrt(sum(r['power'])/r['rows'])) for r in states)/4
    ranks=[]
    for r in states:
        total=sum(r['power']);entropy=-sum(v/total*math.log(v/total) for v in r['power'] if v>0) if total else None
        ranks.append(math.exp(entropy)/min(r['rows'],r['width']) if total else 0)
    result['state_rank']=sum(ranks)/4
    losses={(r['module'],r['train_panel'],r['eval_panel'],r['step'],r['task']):r for r in raw['losses']}
    tasks=sorted({r['task'] for r in raw['losses']})
    for module in ['actor','critic']:
        for tr,ev,suffix in [('M','A',''),('A','M','_audit'),('M','M','_train'),('A','A','_audit_train')]:
            for name,a,b in [('step1',0,1),('later',1,20),('total20',0,20)]:
                result[module+'_'+name+suffix]=sum((losses[module,tr,ev,a,t]['loss']-losses[module,tr,ev,b,t]['loss'])/max(losses[module,tr,ev,0,t]['loss_rms'],1e-6) for t in tasks)/4
    return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('analysis_dir');args=ap.parse_args();run=Run('verify_analysis')
    try:
        src=Path(args.analysis_dir);summ=run.read(src/'summary.json');p=run.read(src/'sources/protocol.json')
        rows=run.rows(src/'features.csv');fits=run.read(src/'ridge_fits.json');pred=run.rows(src/'predictions.csv')
        selected=run.rows(src/'selection_rows.csv');splits=run.read(src/'case_splits.json');raw={};outcome={};duration={}
        def close(label,a,b):run.check(label,math.isclose(float(a),float(b),rel_tol=1e-8,abs_tol=1e-10),{'a':float(a),'b':float(b)})
        def mean(v):return sum(v)/len(v)
        def pick(v):return next(i for i,x in enumerate(v) if x>=max(v)-1e-12)
        for entry in run.rows(src/'evaluation_provenance.csv'):
            es=run.rows(entry['episodes_path']);run.check('raw hash',run.inputs[entry['episodes_path']]==entry['sha256'])
            jid=entry['id'];s=jid.split('_')[1];raw[jid]={(e['task'],int(e['episode_index'])):e for e in es}
            for ti,t in enumerate(p['suites'][s]):
                order=sorted(range(100),key=lambda i:hashlib.sha256(f"F07-v1|{s}|{t}|{raw[jid][t,i]['initial_state_hash']}".encode()).hexdigest())
                run.check('case split independently hashed',order==splits[s]['D'][ti]+splits[s]['O'][ti])
            outcome[jid]={};duration[jid]={}
            for bank in ['D','O']:
                outcome[jid][bank]=[mean([int(raw[jid][t,i]['success']) for i in splits[s][bank][ti]]) for ti,t in enumerate(p['suites'][s])]
                duration[jid][bank]=sum(int(raw[jid][t,i]['length']) for ti,t in enumerate(p['suites'][s]) for i in splits[s][bank][ti])
        md=Path(summ['measurement']);derived={}
        for item in run.read(md/'snapshot_manifest.json'):
            rec=run.read(item['raw_path'],item['raw_sha256']);derived[item['id']]=derive_diagnostics(rec)
        f05={(r['id'],r['task']):r for r in run.rows(ROOT/p['f05_measurements']/'task_diagnostics.csv') if r['panel']=='M'}
        for row in run.rows(src/'all_snapshot_features.csv'):
            for name,value in derived[row['id']].items():close('all192 derived snapshot features '+name,row[name],value)
        for r in rows:
            jid=r['id'];pre=jid.rsplit('_r',1)[0];s=r['suite'];tasks=p['suites'][s];a=r['allocation'];fi=tasks.index(a[2:]) if a!='U' else None
            initial=outcome[pre+'_base']['D'];cur=outcome[jid.replace('_t20','_e20')]['D'];delta=[b-a for a,b in zip(initial,cur)]
            def role(v):return (mean(v),mean(v)) if fi is None else (v[fi],mean([x for i,x in enumerate(v) if i!=fi]))
            bf,bo=role(initial);df,do=role(delta)
            expected={'focus':int(fi is not None),'cp400':int(int(r['checkpoint_step'])==400000),'initial_focus':bf,'initial_other':bo,
                'delta_focus':df,'delta_other':do,'D20':mean(cur),'target_D_remainder':mean(outcome[jid.replace('_t20','_e40')]['D'])-mean(cur),
                'O40':mean(outcome[jid.replace('_t20','_e40')]['O']),'weight':(1/18 if s=='A' else 1/9)/15}
            order=sorted(range(4),key=lambda i:(initial[i],cur[i],i))
            if fi is not None:order.remove(fi);order.insert(0,fi)
            for k,ti in enumerate(order):expected.update({f'p0_{k}':initial[ti],f'delta_{k}':delta[ti],f'decline_{k}':max(-delta[ti],0)})
            expected.update(derived[jid])
            for k,col in [('reward_scale','reward_rms'),('target_scale','target_rms'),('residual','residual_normalized'),('gap','gap_normalized')]:
                expected[k]=mean([math.log1p(float(f05[jid,t][col])) for t in tasks])
            for k,v in expected.items():close('raw reconstructed feature '+jid+k,r[k],v)
        observed={(r['method'],r['id']):float(r['predicted40']) for r in pred};computed={}
        for fit in fits:
            held=fit['held_original_seed'];cols=fit['features'];method=fit['method']
            tr=[r for r in rows if int(r['original_seed'])!=held];te=[r for r in rows if int(r['original_seed'])==held]
            run.check('all histories of held original seed excluded',set(fit['train_ids'])=={r['id'] for r in tr} and set(fit['test_ids'])=={r['id'] for r in te})
            run.check('no outcome/identity predictor',not set(cols)&{'O40','target_D_remainder','original_seed','continuation','suite','id'})
            x=np.array([[float(r[k]) for k in cols] for r in tr]);w=np.array([float(r['weight']) for r in tr]);w/=w.sum();y=np.array([float(r['target_D_remainder']) for r in tr])
            mu=np.average(x,axis=0,weights=w);sd=np.sqrt(np.average((x-mu)**2,axis=0,weights=w));sd[sd<=1e-12]=1
            z=np.column_stack([np.ones(len(x)),(x-mu)/sd]);penalty=np.column_stack([np.zeros(len(cols)),np.eye(len(cols))])
            design=np.vstack([np.sqrt(w[:,None])*z,penalty]);target=np.r_[np.sqrt(w)*y,np.zeros(len(cols))]
            beta=np.linalg.lstsq(design,target,rcond=None)[0]
            close('independent LS intercept',fit['intercept'],beta[0])
            for j in range(len(cols)):
                close('independent LS coefficient',fit['coef'][j],beta[j+1]);close('fold mean',fit['mean'][j],mu[j]);close('fold scale',fit['scale'][j],sd[j])
            for r in te:
                val=float(r['D20'])+float(np.r_[1,(np.array([float(r[c]) for c in cols])-mu)/sd]@beta)
                close('held seed prediction',observed[method,r['id']],val);computed[method,r['id']]=val
        identity=lambda r:tuple(r[k] for k in ['suite','original_seed','checkpoint_step','continuation','mode'])
        base={identity(r):r for r in selected if r['method']==p['primary_comparator']};greedy={identity(r):r for r in selected if r['method']=='Greedy20'}
        for r in selected:
            s=r['suite'];n=int(r['original_seed']);cp=int(r['checkpoint_step']);rep=int(r['continuation']);method=r['method'];mode=r['mode']
            pre=f"{'E1' if s=='A' else 'E3'}_{s}_s{n}_c{cp//1000}";names=['U']+['F_'+t for t in p['suites'][s]]
            dr=[rep] if mode=='same_repeat' else [v for v in p['continuations'][s] if v!=rep]
            fixedvals=[mean([mean(outcome[f"{'E1' if s=='A' else 'E3'}_{s}_s{other}_c{cp//1000}_r{rr}_{a}_e40"]['D']) for other in p['original_seeds'] if other!=n for rr in p['continuations'][s]]) for a in names]
            fixed=pick(fixedvals)
            if method=='Uniform':ai=0
            elif method=='Failure':ai=1+int(np.argmin(outcome[pre+'_base']['D']))
            elif method=='Development_fixed':ai=fixed
            elif method=='Greedy20':ai=pick([mean([mean(outcome[pre+f'_r{rr}_{a}_e20']['D']) for rr in dr]) for a in names])
            else:ai=pick([mean([computed[method,pre+f'_r{rr}_{a}_t20'] for rr in dr]) for a in names])
            run.check('selected allocation',int(r['allocation_index'])==ai and r['selected_allocation']==names[ai])
            values=[mean(outcome[pre+f'_r{rep}_{a}_e40']['O'])*100 for a in names];probe=method not in ['Uniform','Failure','Development_fixed']
            checks={'score_pp':values[ai],'vs_uniform_pp':values[ai]-values[0],'vs_fixed_pp':values[ai]-values[fixed],
                'vs_base_pp':values[ai]-float(base[identity(r)]['score_pp']),'vs_greedy_pp':values[ai]-float(greedy[identity(r)]['score_pp']),
                'absolute_gain_pp':values[ai]-mean(outcome[pre+'_base']['O'])*100,'hindsight_regret_pp':max(values)-values[ai],
                'max_task_drop_pp':max(x-y for x,y in zip(outcome[pre+'_base']['O'],outcome[pre+f'_r{rep}_{names[ai]}_e40']['O']))*100,
                'probe_training_steps':len(dr)*100000 if probe else 0,'total_training_steps':(120000 if mode=='same_repeat' else 240000) if probe else 40000,
                'parent_D_eval_steps':duration[pre+'_base']['D'] if method not in ['Uniform','Development_fixed','Greedy20'] else 0,
                'probe_D_eval_steps':sum(duration[pre+f'_r{rr}_{a}_e20']['D'] for rr in dr for a in names) if probe else 0,
                'weight':(1/18 if s=='A' else 1/9)/3,'changed_vs_base':int(r['allocation_index']!=base[identity(r)]['allocation_index'])}
            for k,v in checks.items():close('selection metric '+k,r[k],v)
        for filename,group in [('selection_summary.csv',None),('selection_by_seed.csv','original_seed'),('selection_by_group.csv','group')]:
            for r in run.rows(src/filename):
                sub=[v for v in selected if v['method']==r['method'] and v['mode']==r['mode']]
                if group=='original_seed':sub=[v for v in sub if v['original_seed']==r['original_seed']]
                if group=='group':sub=[v for v in sub if v['suite']+str(int(v['checkpoint_step'])//1000)==r['group']]
                for k in r:
                    if k in ['mode','method','original_seed','group']:continue
                    val=len(sub) if k=='choices' else sum(int(v['changed_vs_base']) for v in sub) if k=='changed_choices' else sum(float(v['weight'])*float(v[k]) for v in sub)/sum(float(v['weight']) for v in sub)
                    close('aggregate '+filename+k,r[k],val)
        for r in run.rows(src/'prediction_metrics.csv'):
            val=sum(float(x['weight'])*abs(computed[r['method'],x['id']]-float(x['O40']))*100 for x in rows)
            close('MAE',r['O40_MAE_pp'],val)
        for r in run.rows(src/'planned_contrasts.csv'):
            comparison={identity(x):x for x in selected if x['method']==r['comparator']}
            rr=[x for x in selected if x['mode']==r['mode'] and x['method']==r['method']]
            if r['scope']=='original_seed':rr=[x for x in rr if x['original_seed']==r['part']]
            if r['scope']=='group':rr=[x for x in rr if x['suite']+str(int(x['checkpoint_step'])//1000)==r['part']]
            effect=sum(float(x['weight'])*(float(x['score_pp'])-float(comparison[identity(x)]['score_pp'])) for x in rr)/sum(float(x['weight']) for x in rr)
            close('planned contrast increment',r['increment_pp'],effect)
            close('planned contrast choices',r['changed_choices'],sum(x['allocation_index']!=comparison[identity(x)]['allocation_index'] for x in rr))
        # Reconstruct conditional O-case intervals using raw episode records.
        rng=np.random.default_rng(p['bootstrap_seed']);draws=p['bootstrap_draws']
        counts={s:rng.multinomial(50,[.02]*50,size=(draws,4)) for s in p['suites']}
        for ci in run.rows(src/'conditional_case_intervals.csv'):
            rr=[r for r in selected if r['mode']==ci['mode'] and r['method']==ci['method']]
            cc={identity(r):r for r in selected if r['method']==ci['comparator']};boot=np.zeros(draws);point=0.
            for r in rr:
                s=r['suite'];pre=f"{'E1' if s=='A' else 'E3'}_{s}_s{r['original_seed']}_c{int(r['checkpoint_step'])//1000}_r{r['continuation']}_"
                a=raw[pre+r['selected_allocation']+'_e40'];b=raw[pre+cc[identity(r)]['selected_allocation']+'_e40']
                for ti,t in enumerate(p['suites'][s]):
                    difference=np.array([int(a[t,i]['success'])-int(b[t,i]['success']) for i in splits[s]['O'][ti]])
                    boot+=float(r['weight'])*25*(counts[s][:,ti]@difference)/50
                    point+=float(r['weight'])*25*difference.mean()
            close('conditional interval point',ci['increment_pp'],point)
            close('conditional interval lower',ci['case_only_lo_pp'],np.quantile(boot,.025))
            close('conditional interval upper',ci['case_only_hi_pp'],np.quantile(boot,.975))
        run.finish({'status':'completed','factor':p['factor'],'source':str(src),'raw_episode_rows':len(raw)*400,'feature_rows':len(rows),
                    'ridge_fits':len(fits),'predictions':len(computed),'selected_rows':len(selected),'independent_solver':'augmented least squares'})
    except Exception:
        run.finish({'status':'failed','traceback':traceback.format_exc()});raise

if __name__=='__main__':main()
