"""Independent integer arithmetic from raw saved episode outcomes, zero steps."""
import argparse
from collections import defaultdict
from pathlib import Path
import json
import pandas as pd

def verify(campaign,analysis):
    checks=[];labels={};counts=defaultdict(lambda:[0,0])
    for p in (Path(campaign)/'runs').glob('*/evaluation_episodes/part_*.parquet'):
        for row in pd.read_parquet(p).to_dict('records'):
            key=(row['run_id'],row['task_id'],int(row['checkpoint_id']),row['initial_case_id'],row['physical_case_id'])
            if key in labels:raise RuntimeError('Raw outcome key duplicated')
            labels[key]=int(row['success_any']);group=key[:3];counts[group][0]+=int(row['success_any']);counts[group][1]+=1
    metric=Path(analysis)/'cell_metrics.csv'
    if metric.exists():
        for row in pd.read_csv(metric).to_dict('records'):
            n,d=counts[(row['run_id'],row['task_id'],int(row['checkpoint_id']))]
            if d!=row['completed_episodes'] or abs(n/d-row['success_any_rate'])>1e-12:raise RuntimeError('Aggregate arithmetic mismatch')
            checks.append('aggregate')
    pair=Path(analysis)/'paired_case_transitions.csv'
    if pair.exists():
        for r in pd.read_csv(pair).to_dict('records'):
            a,b=int(r['checkpoint_from']),int(r['checkpoint_to']);events=[0,0,0,0]
            for key,x in labels.items():
                if key[:3]!=(r['run_id'],r['task_id'],a):continue
                other=(key[0],key[1],b,key[3],key[4])
                if other in labels:events[[(1,1),(1,0),(0,1),(0,0)].index((x,labels[other]))]+=1
            expected=[int(r[n]) for n in ('retained_11','observed_loss_10','observed_gain_01','failed_00')]
            if events!=expected or sum(events)!=int(r['valid_pairs']):raise RuntimeError('Paired transition arithmetic mismatch')
            checks.append('paired')
    result={'status':'passed','raw_evaluation_outcomes':len(labels),'integer_checks':len(checks),'new_environment_steps':0,
        'independence':'separate code path and integer accumulation; not independent scientific evidence'}
    (Path(analysis)/'independent_verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--campaign',required=True);p.add_argument('--analysis',required=True);a=p.parse_args();verify(a.campaign,a.analysis)
