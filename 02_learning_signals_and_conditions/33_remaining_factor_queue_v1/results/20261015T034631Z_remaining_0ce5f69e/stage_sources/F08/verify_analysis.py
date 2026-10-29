"""Audit all real training paths and independently recompute paired contrasts."""
import argparse
import traceback
from pathlib import Path
import numpy as np
from common import Run,HERE


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--campaign',required=True);ap.add_argument('--analysis',required=True);args=ap.parse_args();run=Run('verify_analysis')
    def near(name,a,b):run.check(name,bool(np.allclose(a,b,atol=1e-10,rtol=1e-10)))
    try:
        p=run.read(HERE/'protocol.json');cam=Path(args.campaign);ad=Path(args.analysis);plan=run.read(cam/'plan.json',run.read(cam/'plan_integrity.json')['sha256'])
        run.check('completed analysis',run.read(ad/'summary.json')['status']=='completed')
        paths={};results={};train={};yy={};parents={};bankcases={};count=0
        for job in plan['jobs']:
            if job['stage']!='F08' or job['kind'] not in ['train','evaluate']:continue
            mark=run.read(cam/'completed'/(job['id']+'.json'));result=run.read(mark['result_ref']['path'],mark['result_ref']['sha256']);results[job['id']]=result
            attempt=Path(mark['result_ref']['path']).parent;q=run.read(attempt/'request.json');cost=run.read(attempt/'costs.json')
            if job['kind']=='train':
                run.check('exact iteration and transition budget',cost['costs']['train_iterations']==cost['costs']['environment_steps']==20000)
                ref=result['checkpoint'];checkpoint=Path(ref['path']);cm=run.read(checkpoint/'checkpoint_manifest.json',ref['manifest_sha256'])
                for name,digest in cm['files'].items():run.hashed(checkpoint/name,digest)
                run.check('right saved horizon',cm['step']==200000+job['horizon'])
                run.check('branch RNG reset only at start',bool(q['start_branch'])==(job['horizon']==20000))
                episodes=run.rows(attempt/'train_episodes.csv');run.check('40 complete training episodes',len(episodes)==40 and all(int(e['length'])==500 for e in episodes))
                identity=(job['suite'],job['condition'],job['continuation']);train.setdefault(identity,{})[job['horizon']]=(q,result,episodes);count+=20000
            elif job['bank_kind']=='outcome':
                bank=run.read(q['bank']['path'],q['bank']['sha256']);entries={(r['task'],r['episode_index']):r for r in bank['outcome']}
                run.hashed(result['episodes_path'],result['episodes_sha256']);rows=run.rows(result['episodes_path']);a=np.full((4,100),np.nan)
                for r in rows:
                    key=(r['task'],int(r['episode_index']));b=entries[key]
                    run.check('same recorded physical outcome case',r['initial_state_hash']==b['initial_state_hash'] and int(r['seed'])==b['seed'])
                    ti=p['suites'][job['suite']].index(r['task']);ix=key[1];run.check('case unique',np.isnan(a[ti,ix]));a[ti,ix]=int(r['success'])
                run.check('all400 binary outcomes',np.isin(a,[0,1]).all() and len(rows)==400)
                near('evaluation step cost',sum(int(r['length']) for r in rows),cost['costs']['environment_steps'])
                if job.get('condition'):yy[job['suite'],job['condition'],job['continuation']]=a
                else:parents[job['suite']]=a
        run.check('72 full branches',len(train)==len(yy)==72 and count==2880000)
        for (suite,condition,rep),segments in train.items():
            first,last=segments[20000],segments[40000]
            run.check('actual same-branch full checkpoint continuation',last[0]['parent']==first[1]['checkpoint'])
            episodes=first[2]+last[2];tasks=p['suites'][suite];i,j=[tasks.index(t) for t in p['pairs'][suite]]
            counts=np.bincount([tasks.index(e['task']) for e in episodes],minlength=4).tolist()
            if condition.startswith('dose'):
                f,o={'dose25':(20,20),'dose4375':(35,15),'dose625':(50,10),'dose8125':(65,5)}[condition];expected=[o]*4;expected[i]=f
            else:expected=[10]*4;expected[i]=expected[j]=30
            run.check('matched total allocation '+str((suite,condition,rep)),counts==expected)
            # Order is checked per8-episode block; endpoints reset neither optimizer nor replay.
            if not condition.startswith('dose'):
                for block in range(10):
                    c=np.bincount([tasks.index(e['task']) for e in episodes[8*block:8*(block+1)]],minlength=4).tolist();expected=[1]*4
                    if condition=='mixture':expected[i]=expected[j]=3
                    else:
                        focus=(i if block<5 else j) if condition=='i_then_j' else (j if block<5 else i) if condition=='j_then_i' else (i if block%2==0 else j)
                        expected[focus]=5
                    run.check('order block schedule',c==expected)
        independent={};rng=np.random.default_rng(p['bootstrap_seed'])
        for suite in p['suites']:
            weights=rng.multinomial(100,np.full(100,.01),size=(5000,4))
            byrepeat={}
            for rep in p['continuations']:
                a=lambda cond:yy[suite,cond,rep]
                byrepeat[rep]={'dose81_minus25':a('dose8125')-a('dose25'),
                    'dose4375_nonlinearity':a('dose4375')-(2*a('dose25')+a('dose8125'))/3,
                    'dose625_nonlinearity':a('dose625')-(a('dose25')+2*a('dose8125'))/3,
                    'forward_minus_reverse':a('i_then_j')-a('j_then_i'),
                    'forward_minus_mixture':a('i_then_j')-a('mixture'),
                    'reverse_minus_mixture':a('j_then_i')-a('mixture'),
                    'alternate_minus_mixture':a('alternate4k')-a('mixture')}
            for name in byrepeat[p['continuations'][0]]:
                means=np.mean([v[name] for v in byrepeat.values()],axis=0);boot=np.sum(weights*means[None],axis=(1,2))/4
                independent[suite,name]=(float(means.mean()*100),np.quantile(boot,[.025,.975]),[float(v[name].mean()*100) for v in byrepeat.values()])
        for r in run.rows(ad/'contrasts.csv'):
            point,ci,repeats=independent[r['suite'],r['contrast']];near('independent contrast',float(r['difference_pp']),point)
            near('independent paired case intervals',[float(r['case_only_lo_pp']),float(r['case_only_hi_pp'])],ci)
            n=sum(v>0 for v in repeats) if point>=0 else sum(v<0 for v in repeats);run.check('repeat consistency',int(r['same_sign_repeats'])==n)
        run.finish({'status':'completed','source':str(ad),'branches_verified':72,'full_checkpoints_verified':144,'training_steps_verified':count,
                    'original_seed_count':1,'independent_scientific_confirmation':False})
    except Exception:
        run.finish({'status':'failed','traceback':traceback.format_exc()});raise


if __name__=='__main__':main()
