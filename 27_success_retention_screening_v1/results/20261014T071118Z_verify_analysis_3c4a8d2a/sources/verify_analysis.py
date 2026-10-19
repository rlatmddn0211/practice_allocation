"""Independent raw-case reconstruction, augmented least squares and all choices."""
import argparse
import hashlib
import math
import traceback
from collections import defaultdict
from pathlib import Path
import numpy as np
from common import Run,ROOT,save,table

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
        if p['factor']=='F04':
            md=Path(summ['measurement']);bb=run.rows(md/'batch_diagnostics.csv');diag=defaultdict(list)
            for b in bb:diag[b['id'],b['module'],b['source_panel']].append(b)
            f05={(r['id'],r['task']):r for r in run.rows(ROOT/p['f05_measurements']/'task_diagnostics.csv') if r['panel']=='M'}
        paircheck={}
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
            if p['factor']=='F01':
                for name,lo,hi in [('excess',0,50),('excess_half1',0,25),('excess_half2',25,50)]:
                    values=[]
                    for ti,t in enumerate(tasks):
                        contingency=np.zeros((2,2),int)
                        for i in splits[s]['D'][ti][lo:hi]:
                            ea=raw[pre+'_base'][t,i];eb=raw[jid.replace('_t20','_e20')][t,i]
                            run.check('paired initial state',ea['initial_state_hash']==eb['initial_state_hash'] and ea['seed']==eb['seed'])
                            contingency[int(ea['success']),int(eb['success'])]+=1
                        values.append(min(contingency[1,0],contingency[0,1])/(hi-lo))
                        if name=='excess':paircheck[jid,t]=contingency
                    expected[name+'_focus'],expected[name+'_other']=role(values)
            else:
                for module in ['actor','critic']:
                    for suffix,col,panel in [('cosine','raw_cosine','M'),('raw','weighted_alignment','M'),('adam','adam_relative','M'),
                                             ('audit','adam_relative','A'),('uniform','uniform_adam_relative','M')]:
                        expected[module+'_'+suffix]=mean([float(b[col]) for b in diag[jid,module,panel]])
                for k,col in [('reward_scale','reward_rms'),('target_scale','target_rms'),('residual','residual_normalized'),('gap','gap_normalized')]:
                    expected[k]=mean([math.log1p(float(f05[jid,t][col])) for t in tasks])
            for k,v in expected.items():close('raw reconstructed feature '+jid+k,r[k],v)
        if p['factor']=='F01':
            for r in run.rows(src/'paired_task_cases.csv'):
                ct=paircheck[r['id'],r['task']];n0=int(ct[1].sum());n1=int(ct[:,1].sum())
                for k,v in {'initial_success_count':n0,'current_success_count':n1,'lost_count':ct[1,0],'gained_count':ct[0,1],
                            'retained_count':ct[1,1],'excess_turnover':min(ct[1,0],ct[0,1])/50,
                            'excess_capacity':min(n0,n1,50-n0,50-n1)/50}.items():close('paired count '+k,r[k],v)
                if n0:close('conditional loss',r['conditional_loss_rate'],ct[1,0]/n0)
                else:run.check('undefined conditional loss remains missing',r['conditional_loss_rate']=='')
            # A control showing why equal marginal performance does not determine turnover.
            stable=np.array([[25,0],[0,25]]);flip=np.array([[15,10],[10,15]])
            run.check('equal margins distinct turnover',np.array_equal(stable.sum(0),flip.sum(0)) and np.array_equal(stable.sum(1),flip.sum(1)) and min(stable[1,0],stable[0,1])!=min(flip[1,0],flip[0,1]))
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
                'parent_D_eval_steps':duration[pre+'_base']['D'] if method not in ['Uniform','Development_fixed'] else 0,
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
        run.finish({'status':'completed','factor':p['factor'],'source':str(src),'raw_episode_rows':len(raw)*400,'feature_rows':len(rows),
                    'ridge_fits':len(fits),'predictions':len(computed),'selected_rows':len(selected),'independent_solver':'augmented least squares'})
    except Exception:
        run.finish({'status':'failed','traceback':traceback.format_exc()});raise

if __name__=='__main__':main()
