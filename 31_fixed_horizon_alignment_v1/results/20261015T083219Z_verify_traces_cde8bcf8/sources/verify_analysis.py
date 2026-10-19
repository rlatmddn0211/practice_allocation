"""Independently refit task calibrations and allocation predictions."""
import argparse
import traceback
from pathlib import Path
import numpy as np
from common import Run,HERE
from outcomes import read_outcomes,cases,macro


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--campaign',required=True);ap.add_argument('--analysis',required=True);args=ap.parse_args();run=Run('verify_analysis')
    def near(label,a,b):run.check(label,bool(np.allclose(a,b,rtol=1e-9,atol=1e-9)))
    try:
        p=run.read(HERE/'protocol.json');ad=Path(args.analysis);summary=run.read(ad/'summary.json');cam=Path(args.campaign)
        run.check('analysis completed',summary['status']=='completed')
        parent,y,lengths,splits,refs=read_outcomes(run,p)
        plan=run.read(cam/'plan.json',run.read(cam/'plan_integrity.json')['sha256']);diags={};meta={};mc={}
        for job in plan['jobs']:
            if job['stage']!='F05' or job['kind']!='measure':continue
            mark=run.read(cam/'completed'/(job['id']+'.json'));result=run.read(mark['result_ref']['path'],mark['result_ref']['sha256'])
            jid=result['original_id'];run.check('diagnosed correct historical model',result['checkpoint']==refs[jid])
            run.hashed(result['episodes_path'],result['episodes_sha256']);run.hashed(result['mc_path'],result['mc_sha256'])
            diags[jid]=run.rows(result['episodes_path']);mc[jid]=run.rows(result['mc_path']);meta[jid]=job
        run.check('192 diagnostic models',len(diags)==192)
        cal=run.read(ad/'calibrations.json');rows=run.rows(ad/'features.csv');fits=run.read(ad/'ridge_fits.json')
        independently_fitted={}
        for held in p['original_seeds']:
            independently_fitted[held]={}
            for task,fit in cal[str(held)].items():
                rr=[(jid,r) for jid,episodes in diags.items() if meta[jid]['original_seed']!=held for r in episodes if r['task']==task]
                run.check('calibration excludes held original seed',set(fit['train_ids'])=={jid for jid,_ in rr})
                x=np.array([float(r['return500']) for _,r in rr]);z=(x-x.mean())/(x.std() if x.std()>1e-12 else 1.)
                design=np.column_stack([np.ones(len(x)),z])/np.sqrt(len(x));design=np.vstack([design,[0,1]])
                target=np.r_[np.array([float(r['success']) for _,r in rr])/np.sqrt(len(x)),0]
                beta=np.linalg.lstsq(design,target,rcond=None)[0]
                near('calibration slope/intercept',[fit['intercept'],fit['slope']],beta)
                near('fold-only return mean/scale',[fit['mean'],fit['scale']],[x.mean(),x.std() if x.std()>1e-12 else 1.])
                independently_fitted[held][task]=(float(x.mean()),float(x.std() if x.std()>1e-12 else 1.),beta)
        for row in rows:
            jid=row['id'];pid=jid.split('_r')[0]+'_base';tasks=p['suites'][row['suite']];focus=None if row['allocation']=='U' else tasks.index(row['allocation'][2:])
            def roles(v):return [float(np.mean(v))]*2 if focus is None else [v[focus],float(np.mean([x for i,x in enumerate(v) if i!=focus]))]
            for name,source in [('new_p0',pid),('new_p20',jid),('near',jid)]:
                field='near_object_reached' if name=='near' else 'success'
                values=[np.mean([float(x[field]) for x in diags[source] if x['task']==t]) for t in tasks]
                near('new diagnostic success controls',[float(row[name+'_'+r]) for r in ['focus','other']],roles(values))
            task_values={'scale':[],'se':[],'error':[]}
            for task in tasks:
                mm=[r for r in mc[jid] if r['task']==task];scale=max(float(np.sqrt(np.mean([float(r['soft_return'])**2 for r in mm]))),1.)
                err=[];se=[]
                for case in [0,1]:
                    ss=[r for r in mm if int(r['episode_index'])==case];values=np.array([float(r['soft_return']) for r in ss])
                    err.append(abs(float(ss[0]['q_min'])-values.mean())/scale);se.append(values.std(ddof=1)/np.sqrt(4)/scale)
                task_values['scale'].append(np.log1p(scale));task_values['se'].append(float(np.mean(se)));task_values['error'].append(float(np.mean(err)))
            for name,values in task_values.items():near('independent MC feature',[float(row['mc_'+name+'_'+r]) for r in ['focus','other']],roles(values))
            for held in p['original_seeds']:
                returns=[];gaps=[]
                for task in tasks:
                    old=[r for r in diags[pid] if r['task']==task];new=[r for r in diags[jid] if r['task']==task]
                    mu,sd,beta=independently_fitted[held][task]
                    oldx=np.array([float(r['return500']) for r in old]);newx=np.array([float(r['return500']) for r in new])
                    returns.append(float((newx.mean()-oldx.mean())/sd))
                    predict=lambda x:np.clip(np.column_stack([np.ones(len(x)),(x-mu)/sd])@beta,0,1)
                    gaps.append(float(predict(newx).mean()-predict(oldx).mean()-np.mean([float(r['success']) for r in new])+np.mean([float(r['success']) for r in old])))
                for name,value in [('return',returns),('cal_gap',gaps)]:near('independent calibrated feature',[float(row[name+'_'+r+'_held'+str(held)]) for r in ['focus','other']],roles(value))
            s=row['suite'];n=int(row['original_seed']);cp=int(row['checkpoint_step']);rep=p['continuations'][s].index(int(row['continuation']));ai=0 if focus is None else focus+1
            near('observed O40 matches raw cases',float(row['O40']),macro(y[s,n,cp][1,rep,ai],splits[s][1]))
            near('training label matches D remainder',float(row['target_D_remainder']),macro(y[s,n,cp][1,rep,ai]-y[s,n,cp][0,rep,ai],splits[s][0]))
        pred={(r['method'],r['id']):float(r['predicted40']) for r in run.rows(ad/'predictions.csv')}
        for fit in fits:
            held=fit['held_original_seed'];cols=fit['features']
            def value(row,col):return float(row[col+'_held'+str(held)] if col in ['return_focus','return_other','cal_gap_focus','cal_gap_other'] else row[col])
            tr=[r for r in rows if int(r['original_seed'])!=held];te=[r for r in rows if int(r['original_seed'])==held]
            run.check('predictor original-seed exclusion',set(fit['train_ids'])=={r['id'] for r in tr} and set(fit['test_ids'])=={r['id'] for r in te})
            x=np.array([[value(r,c) for c in cols] for r in tr]);w=np.array([float(r['weight']) for r in tr]);w/=w.sum()
            mu=w@x;sd=np.sqrt(w@((x-mu)**2));sd[sd<=1e-12]=1.;design=np.column_stack([np.ones(len(tr)),(x-mu)/sd])
            aug=np.vstack([design*np.sqrt(w)[:,None],np.column_stack([np.zeros(len(cols)),np.eye(len(cols))])])
            target=np.r_[np.array([float(r['target_D_remainder']) for r in tr])*np.sqrt(w),np.zeros(len(cols))]
            beta=np.linalg.lstsq(aug,target,rcond=None)[0]
            for r in te:near('independent prediction',pred[fit['method'],r['id']],float(r['D20'])+np.r_[1,(np.array([value(r,c) for c in cols])-mu)/sd]@beta)
        selected=run.rows(ad/'selection_rows.csv');methods={f['method'] for f in fits};lookup={tuple(r[k] for k in ['suite','original_seed','checkpoint_step','continuation','mode','method']):r for r in selected}
        for row in selected:
            if row['method'] not in methods:continue
            s=row['suite'];n=int(row['original_seed']);cp=int(row['checkpoint_step']);rep=int(row['continuation']);names=['U']+['F_'+t for t in p['suites'][s]]
            rr=[r for r in rows if r['suite']==s and int(r['original_seed'])==n and int(r['checkpoint_step'])==cp]
            reps=[rep] if row['mode']=='same_repeat' else [v for v in p['continuations'][s] if v!=rep]
            scores=[np.mean([pred[row['method'],r['id']] for r in rr if r['allocation']==a and int(r['continuation']) in reps]) for a in names]
            ix=next(i for i,x in enumerate(scores) if x>=max(scores)-1e-12);run.check('correct argmax',row['selected_allocation']==names[ix])
            near('actual selected score',float(row['score_pp']),100*macro(y[s,n,cp][1,p['continuations'][s].index(rep),ix],splits[s][1]))
            fixedcost=40000*(1+5*len(reps)) if row['method']!='CriticBase' else 0
            mccost=16000*(1+5*len(reps)) if row['method'] in ['RolloutBase','RolloutValue'] else 0
            near('new diagnostics fully charged',[float(row['new_fixed_D_eval_steps']),float(row['new_MC_eval_steps'])],[fixedcost,mccost])
        for contrast in run.rows(ad/'planned_contrasts.csv'):
            rr=[r for r in selected if r['method']==contrast['method'] and r['mode']==contrast['mode']]
            if contrast['scope']=='original_seed':rr=[r for r in rr if r['original_seed']==contrast['part']]
            if contrast['scope']=='group':rr=[r for r in rr if r['suite']+str(int(r['checkpoint_step'])//1000)==contrast['part']]
            diff=[];w=[]
            for r in rr:
                k=tuple(r[x] for x in ['suite','original_seed','checkpoint_step','continuation','mode'])+(contrast['comparator'],)
                diff.append(float(r['score_pp'])-float(lookup[k]['score_pp']));w.append(float(r['weight']))
            near('planned contrast',float(contrast['increment_pp']),np.average(diff,weights=w))
        rng=np.random.default_rng(p['bootstrap_seed']);weights={s:rng.multinomial(50,np.full(50,.02),size=(p['bootstrap_draws'],4)) for s in p['suites']}
        for ci in run.rows(ad/'conditional_case_intervals.csv'):
            boot=np.zeros(p['bootstrap_draws'])
            for r in selected:
                if r['method']!=ci['method'] or r['mode']!=ci['mode']:continue
                k=tuple(r[x] for x in ['suite','original_seed','checkpoint_step','continuation','mode'])+(ci['comparator'],);c=lookup[k]
                s=r['suite'];ctx=s,int(r['original_seed']),int(r['checkpoint_step']);rep=p['continuations'][s].index(int(r['continuation']))
                delta=cases(y[ctx][1,rep,int(r['allocation_index'])]-y[ctx][1,rep,int(c['allocation_index'])],splits[s][1])
                boot+=float(r['weight'])*100*np.sum(weights[s]*delta[None,:,:],axis=(1,2))/200
            near('independent conditional intervals',[float(ci['case_only_lo_pp']),float(ci['case_only_hi_pp'])],np.quantile(boot,[.025,.975]))
        run.finish({'status':'completed','source':str(ad),'snapshots':192,'feature_rows':len(rows),'ridge_fits':len(fits),'predictions':len(pred),'new_diagnostic_environment_steps':0})
    except Exception:
        run.finish({'status':'failed','traceback':traceback.format_exc()});raise


if __name__=='__main__':main()
