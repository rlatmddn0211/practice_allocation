"""Independent copy of frozen raw-evaluation reader; no experiment imports."""
import hashlib
import numpy as np
from common import campaign,record,contexts,prefix,allocations,save,table

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

