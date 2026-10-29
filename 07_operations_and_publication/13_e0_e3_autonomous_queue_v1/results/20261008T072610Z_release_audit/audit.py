"""Final static contract and future reset-seed collision audit; no training."""
import hashlib
import json
import sys
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
QUEUE=HERE.parents[1]
sys.path.insert(0,str(QUEUE))
from campaign import REPO,STAGES,make_plan,sha,write
plan=make_plan()
sources={}
for stage,directory in STAGES.items():
    sources[stage]={}
    for filename in ['learning.py','engine.py','environment.py','evaluation.py']:
        original=REPO/'06_p0_branch_replication_v1/practice_allocation'/filename
        current=REPO/directory/'practice_allocation'/filename
        assert sha(original)==sha(current)
        sources[stage][filename]=sha(current)
def derive(seed,domain,*indices):
    return int(np.random.SeedSequence([seed,domain,*indices]).generate_state(1)[0])
train=set()
for seed in [901,11,12,13]:
    for task in range(4):
        train.update(derive(seed,20,task,visit) for visit in range(200))
for seed in range(1901,1906):
    for task in range(4):
        train.update(derive(seed,20,task,visit) for visit in range(50))
streams={}
for job in plan['jobs']:
    if job.get('start_branch'):
        context=(job['stage'],job['suite'],job['original_seed'],job['checkpoint_step'],job['continuation_label'])
        streams.setdefault(context,set()).add(job['continuation_rng_seed'])
assert all(len(values)==1 for values in streams.values())
assert len({next(iter(values)) for values in streams.values()})==len(streams)
for context,values in streams.items():
    seed=next(iter(values))
    visits=[20,30,30,20] if context[0]=='E2' else [50]*4
    for task,count in enumerate(visits):
        train.update(derive(seed,20,task,visit) for visit in range(count))
bank=set()
for root in [95001,95101,95201,95301,95302]:
    for domain in [100,200]:
        for task in range(4):
            for index in range(100):
                value=derive(root,domain,task,index)
                assert value not in bank
                bank.add(value)
assert not train & bank
checkpoint_count=sum(j['kind'] in ('init','train') for j in plan['jobs'])
write(HERE/'audit.json',{'passed':True,'source_sha256':sha(Path(__file__)),'learner_core_identical_to_06':sources,
     'counts':plan['counts'],'jobs':len(plan['jobs']),'checkpoints':checkpoint_count,
     'unique_continuation_contexts':len(streams),'unique_reserved_training_reset_seeds':len(train),
     'new_bank_seeds':len(bank),'train_bank_seed_intersection':0,'bank_seed_duplicates':0,
     'estimated_checkpoint_bytes_at_p0_compression':checkpoint_count*(3499534+4609400+14000),
     'scope':'Static contract and numerical seed audit. Physical hashes are also checked at runtime.'})
print(json.dumps({'passed':True,'checkpoints':checkpoint_count,'unique_continuation_contexts':len(streams),'seed_overlap':0}))
