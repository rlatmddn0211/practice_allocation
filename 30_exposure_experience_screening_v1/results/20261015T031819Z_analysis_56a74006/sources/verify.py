"""Independent raw-log reconstruction and augmented least-squares audit."""
import argparse
import json
import traceback
from pathlib import Path
import numpy as np
from common import Run,HERE,ROOT,save


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--measurement',required=True);ap.add_argument('--analysis');args=ap.parse_args();run=Run('verify')
    def near(name,a,b):run.check(name,np.allclose(a,b,rtol=1e-10,atol=1e-10),{'actual':np.asarray(a).tolist(),'expected':np.asarray(b).tolist()})
    try:
        p=run.read(HERE/'protocol.json');d=Path(args.measurement);ms=run.read(d/'summary.json');run.check('complete measurement',ms['status']=='completed')
        taskrows={(r['id'],r['task']):r for r in run.rows(d/'task_features.csv')};raw={};parents={}
        for ref in run.read(d/'manifest.json'):
            obj=run.read(ref['path'],ref['sha256']);raw[ref['id']]=obj;e=obj['entry'];ctx=(e['suite'],e['original_seed'],e['checkpoint_step'])
            if e['horizon']==0:parents[ctx]=obj
            all_episodes=[]
            for src in obj['episode_sources']:all_episodes+=run.rows(src['path']);run.hashed(src['path'],src['sha256'])
            cutoff=e['checkpoint_step']+e['horizon']
            for task in p['suites'][e['suite']]:
                recent=sorted([r for r in all_episodes if r['task']==task and int(r['step'])<=cutoff],key=lambda r:int(r['step']))[-20:]
                run.check('last20 original episodes '+ref['id']+task,len(recent)==20)
                observed=obj['episodes'][task];run.check('exact episode identities '+ref['id']+task,
                    [(int(r['step']),r['initial_state_hash']) for r in recent]==[(r['step'],r['initial_state_hash']) for r in observed])
                tr=taskrows[ref['id'],task]
                near('success count '+ref['id']+task,float(tr['recent_success']),sum(r['success'] in ['True','1','1.0'] for r in recent)/20)
                near('equal-length return '+ref['id']+task,float(tr['recent_return']),sum(float(r['return']) for r in recent)/20)
                near('unique reset count '+ref['id']+task,float(tr['recent_unique']),len({r['initial_state_hash'] for r in recent}))
                for panel in ['M','A']:
                    pm=parents[ctx]['moments'][task+'_M'];cur=obj['moments'][task+'_'+panel]
                    delta=np.array(cur['mean'])-pm['mean'];scale=np.maximum(np.array(pm['variance']),.0001)
                    expected=np.log1p(np.sqrt(np.mean((delta**2+cur['variance'])/scale)))
                    near('raw coverage '+ref['id']+task+panel,float(tr['raw_displacement' if panel=='M' else 'raw_displacement_audit']),expected)
            ex=obj['exposure']
            if ex:
                before=parents[ctx]['replay_counters'];cur=obj['replay_counters'];n=cur['sampled_total']-before['sampled_total']
                near('exact sample budget '+ref['id'],n,20000*256)
                near('sample proportions '+ref['id'],ex['observed_share'],(np.array(cur['sampled'])-before['sampled'])/n)
                near('new sample fraction '+ref['id'],ex['new_fraction'],(cur['sampled_new_count']-before['sampled_new_count'])/n)
                near('expected new fraction '+ref['id'],ex['expected_new_fraction'],20001/200000)
        # Derive FIFO expectation through a weighted occupancy identity on eight
        # fixed parent/focus contexts, using independently reloaded replay buffers.
        from snapshot_io import load_snapshot
        references=[]
        for suite,cp in [('A',200000),('A',400000),('B',200000),('C',200000)]:
            candidates=[v for v in raw.values() if v['entry']['suite']==suite and v['entry']['checkpoint_step']==cp and v['entry']['horizon']==20000 and v['entry']['allocation']=='F_'+p['suites'][suite][0]]
            if not candidates:continue
            v=min(candidates,key=lambda x:(x['entry']['original_seed'],x['entry']['continuation']));e=v['entry'];parent=parents[suite,e['original_seed'],cp]
            m,b0,_=load_snapshot(run,parent['entry']['checkpoint'],'cpu');del m
            m,b1,_=load_snapshot(run,v['entry']['checkpoint'],'cpu');del m
            old=b0.observations[np.argsort(b0.birth_steps[:b0.size()]),0,-4:].argmax(1)[:20000]
            new=b1.observations[np.argsort(b1.birth_steps[:b1.size()])[-20000:],0,-4:].argmax(1)
            weight=np.arange(20000,0,-1)
            estimate=[]
            for task in range(4):estimate.append((parent['replay_counters']['task_counts'][task]+(weight@(new==task)-weight@(old==task))/20000)/100000)
            near('independent FIFO expectation '+e['id'],v['exposure']['expected_share'],estimate);references.append(e['id']);del b0,b1
        if args.analysis:
            ad=Path(args.analysis);analysis=run.read(ad/'summary.json');rows=run.rows(ad/'features.csv');byid={r['id']:r for r in rows}
            previous={r['id']:r for r in run.rows(ROOT/p['prior_features'])}
            for r in rows:
                for key in ['D20','target_D_remainder','O40','weight','residual','gap']:
                    near('unchanged baseline '+r['id']+key,float(r[key]),float(previous[r['id']][key]))
                obj=raw[r['id']];tasks=p['suites'][r['suite']];focus=None if r['allocation']=='U' else tasks.index(r['allocation'][2:])
                role=lambda v:(np.mean(v),np.mean(v)) if focus is None else (v[focus],np.mean([v[i] for i in range(4) if i!=focus]))
                for name,col,fn in [('train_return','recent_return',float),('history_age','oldest_episode_age',lambda x:np.log1p(float(x))),('experience','recent_success',float),('unique','recent_unique',float),('replay_age','mean_replay_age',float),('coverage','raw_displacement',float)]:
                    vv=[fn(taskrows[r['id'],t][col]) for t in tasks];f,o=role(vv)
                    near('derived '+r['id']+name,[float(r[name+'_focus']),float(r[name+'_other'])],[f,o])
                ex=obj['exposure'];gap=0 if focus is None else ex['collection_share'][focus]-ex['observed_share'][focus]
                near('exposure feature '+r['id'],float(r['exposure_gap']),gap)
            predictions={(r['method'],r['id']):float(r['predicted40']) for r in run.rows(ad/'predictions.csv')}
            for fit in run.read(ad/'ridge_fits.json'):
                held=fit['held_original_seed'];cols=fit['features'];tr=[r for r in rows if int(r['original_seed'])!=held];te=[r for r in rows if int(r['original_seed'])==held]
                run.check('fold IDs',set(fit['train_ids'])=={r['id'] for r in tr} and set(fit['test_ids'])=={r['id'] for r in te})
                x=np.array([[float(r[c]) for c in cols] for r in tr]);w=np.array([float(r['weight']) for r in tr]);w/=w.sum()
                mu=np.sum(x*w[:,None],axis=0);sd=np.sqrt(np.sum((x-mu)**2*w[:,None],axis=0));sd[sd<=1e-12]=1
                z=(x-mu)/sd;design=np.column_stack([np.ones(len(tr)),z]);penalty=np.column_stack([np.zeros(len(cols)),np.eye(len(cols))])
                matrix=np.vstack([design*np.sqrt(w)[:,None],penalty]);target=np.r_[np.array([float(r['target_D_remainder']) for r in tr])*np.sqrt(w),np.zeros(len(cols))]
                beta=np.linalg.lstsq(matrix,target,rcond=None)[0]
                for r in te:
                    value=float(r['D20'])+np.r_[1,(np.array([float(r[c]) for c in cols])-mu)/sd]@beta
                    near('independent prediction '+fit['method']+r['id'],predictions[fit['method'],r['id']],value)
            selected=run.rows(ad/'selection_rows.csv');lookup={tuple(r[k] for k in ['suite','original_seed','checkpoint_step','continuation','mode','method']):r for r in selected}
            for r in selected:
                if r['method'] not in {f['method'] for f in run.read(ad/'ridge_fits.json')}:continue
                s=r['suite'];tasks=p['suites'][s];alloc=['U']+['F_'+t for t in tasks];rep=int(r['continuation'])
                reps=[rep] if r['mode']=='same_repeat' else [x for x in p['continuations'][s] if x!=rep]
                ctxrows=[x for x in rows if x['suite']==s and x['original_seed']==r['original_seed'] and x['checkpoint_step']==r['checkpoint_step']]
                vals=[np.mean([predictions[r['method'],x['id']] for x in ctxrows if x['allocation']==a and int(x['continuation']) in reps]) for a in alloc]
                chosen=next(i for i,v in enumerate(vals) if v>=max(vals)-1e-12)
                run.check('independent selected allocation',r['selected_allocation']==alloc[chosen])
                actual=next(x for x in ctxrows if int(x['continuation'])==rep and x['allocation']==alloc[chosen])
                near('actual O40 selected score',float(r['score_pp']),100*float(actual['O40']))
            for contrast in run.rows(ad/'planned_contrasts.csv'):
                rr=[r for r in selected if r['method']==contrast['method'] and r['mode']==contrast['mode']]
                if contrast['scope']=='original_seed':rr=[r for r in rr if r['original_seed']==contrast['part']]
                if contrast['scope']=='group':rr=[r for r in rr if r['suite']+str(int(r['checkpoint_step'])//1000)==contrast['part']]
                diff=[];weights=[]
                for r in rr:
                    k=tuple(r[x] for x in ['suite','original_seed','checkpoint_step','continuation','mode'])+(contrast['comparator'],)
                    diff.append(float(r['score_pp'])-float(lookup[k]['score_pp']));weights.append(float(r['weight']))
                near('planned contrast',float(contrast['increment_pp']),np.average(diff,weights=weights))
        run.finish({'status':'completed','snapshots_verified':len(raw),'reference_FIFO_snapshots':references,'analysis_verified':bool(args.analysis),'scientific_confirmation':False})
    except Exception:
        run.finish({'status':'failed','traceback':traceback.format_exc()});raise


if __name__=='__main__':main()
