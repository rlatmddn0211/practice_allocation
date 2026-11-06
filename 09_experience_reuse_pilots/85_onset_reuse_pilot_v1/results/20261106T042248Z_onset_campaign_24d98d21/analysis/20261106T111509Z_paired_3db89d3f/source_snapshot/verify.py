"""Independent scalar raw-label, AUC, pairing and parent-summary verification."""
from __future__ import annotations
import sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from common import *
guard_file_only()
import argparse
import math
import numpy as np
import pandas as pd
from provenance import PilotInputs

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--analysis',type=Path,required=True);a=ap.parse_args();analysis=a.analysis.resolve()
    out=analysis/'verification'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]);out.mkdir(parents=True,exist_ok=False)
    shutil.copy2(__file__,out/'verification_source.py');inputs=PilotInputs(Path(load(analysis/'FINAL_STATUS.json')['campaign']));started=time.perf_counter();checks=[]
    def ck(name,v,scope='',detail=''):
        checks.append(dict(check=name,passed=bool(v),scope=scope,detail=str(detail)))
        if not v:raise AssertionError(name+': '+scope+' '+str(detail))
    try:
        episodes=inputs.parquet(analysis/'evaluation_outcomes.parquet','analysis outcomes to independently remeasure from raw labels')
        label_lookup={};raw_total=0
        for r in episodes.itertuples(index=False):
            path=Path(r.trajectory_ref);inputs.ref(path,'independent raw success/reward input')
            with np.load(path,allow_pickle=False) as z:
                b=[int(v) for v in z['success_step']];reward=[float(v) for v in z['reward']]
            ck('raw success OR agrees with canonical outcome',int(any(b))==r.success_any,r.parent_id+'/'+r.episode_id)
            ck('raw episode return agrees',abs(math.fsum(reward)-r.recomputed_return)<=1e-8,r.parent_id+'/'+r.episode_id)
            future='SHARED' if r.relative_train_step==0 else r.future_id
            arm='SHARED_START' if r.relative_train_step==0 else r.arm
            key=(r.parent_id,future,arm,r.task_id,int(r.relative_train_step),r.initial_case_id)
            ck('unique raw episode identity',key not in label_lookup,str(key));label_lookup[key]=int(any(b));raw_total+=len(b)
        cells=pd.read_csv(analysis/'cell_metrics.csv');inputs.ref(analysis/'cell_metrics.csv','independent AUC comparison')
        independent={}
        for r in cells.itertuples(index=False):
            rates=[]
            for t in [0,16000,32000,64000]:
                f='SHARED' if t==0 else r.future_id;arm='SHARED_START' if t==0 else r.arm
                labels=[label_lookup[(r.parent_id,f,arm,r.task_id,t,f'{r.task_id}_E{i:02d}')] for i in range(16)]
                rate=sum(labels)/16;rates.append(rate)
                ck('fixed sixteen-case success rate',rate==getattr(r,f'J_{t}'),r.cell_id+'/'+r.task_id+'/'+str(t))
            area=(16000*(rates[0]+rates[1])/2+16000*(rates[1]+rates[2])/2+32000*(rates[2]+rates[3])/2)/64000
            ck('independent trapezoidal normalized AUC',abs(area-r.auc)<1e-12,r.cell_id+'/'+r.task_id)
            independent[(r.parent_id,r.future_id,r.arm,r.task_id)]=(area,rates[-1])
        effects=pd.read_csv(analysis/'paired_effects_by_parent_future.csv')
        for r in effects.itertuples(index=False):
            tasks=['DO','DC','PU','BP'] if r.scope=='MACRO4' else ['DC','PU','BP'] if r.scope=='OTHER3' else [r.scope]
            actual=[]
            for metric in (0,1):actual.append(sum(independent[(r.parent_id,r.future_id,r.method,t)][metric]-independent[(r.parent_id,r.future_id,r.reference,t)][metric] for t in tasks)/len(tasks))
            ck('paired effects from raw labels',abs(actual[0]-r.delta_auc)<1e-12 and abs(actual[1]-r.delta_final)<1e-12,r.parent_id+'/'+r.future_id+'/'+r.contrast+'/'+r.scope)
        parent=pd.read_csv(analysis/'parent_effects.csv')
        for r in parent.itertuples(index=False):
            f=effects[(effects.parent_id==r.parent_id)&(effects.contrast==r.contrast)&(effects.scope==r.scope)]
            ck('exact two-future equal weighting',len(f)==2 and abs(sum(f.delta_auc)/2-r.delta_auc)<1e-12,r.parent_id+'/'+r.contrast+'/'+r.scope)
        summaries=load(analysis/'bootstrap_summary.json')
        with np.load(analysis/'bootstrap_draws.npz',allow_pickle=False) as z:indices=z['parent_indices'];draw_values=z['contrasts']
        expected=np.random.Generator(np.random.PCG64(54001)).integers(0,5,size=(20000,5))
        ck('same prespecified parent bootstrap indices',np.array_equal(indices,expected))
        for j,s in enumerate(summaries['summary']):
            values=[]
            for rid in ['R01','R02','R03','R04','R05']:
                r=parent[(parent.parent_id==rid)&(parent.contrast==s['contrast'])&(parent.scope==s['scope'])].iloc[0]
                values.append(float(r[s['metric']]))
            direct=np.array([sum(values[int(i)] for i in draw)/5 for draw in indices])
            ck('bootstrap draw means share entire parent vectors',np.allclose(direct,draw_values[:,j],atol=1e-12,rtol=0),str(j))
            interval=np.quantile(direct,[.025,.975],method='linear')
            ck('reported estimate and percentile limits',abs(sum(values)/5-s['estimate'])<1e-12 and np.allclose(interval,[s['lower'],s['upper']],atol=1e-12,rtol=0),str(j))
        ck('full completed raw evaluation count',len(episodes)==6080 and raw_total==3040000)
        save(out/'FINAL_STATUS.json',dict(status='passed',checks=len(checks),raw_episodes=len(episodes),raw_transitions_read=raw_total,new_execution=ZERO_EXECUTION))
        print(json.dumps(dict(output=str(out),status='passed',checks=len(checks))),flush=True)
    except BaseException as ex:
        save(out/'FAILED.json',dict(error=repr(ex),new_execution=ZERO_EXECUTION));raise
    finally:
        inputs.flush(out);pd.DataFrame(checks).to_csv(out/'verification_checks.csv',index=False)
        save(out/'costs.json',dict(wall_seconds=time.perf_counter()-started,new_execution=ZERO_EXECUTION))
    save(analysis/'LATEST_VERIFICATION.json',dict(output=str(out)),replace=True)

if __name__=='__main__':main()
