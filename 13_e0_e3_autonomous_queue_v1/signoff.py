"""Require matching final CUDA, queue recovery and known-answer analysis evidence."""
import argparse
from pathlib import Path
from campaign import ROOT,REPO,STAGES,write,read,sha,stage_hashes,now

parser=argparse.ArgumentParser()
parser.add_argument('--cuda',type=Path,required=True)
parser.add_argument('--queue',type=Path,required=True)
parser.add_argument('--analysis',type=Path,required=True)
args=parser.parse_args()
sources={stage:stage_hashes(REPO/name) for stage,name in STAGES.items()}
for stage,suite in [('E0','A'),('E1','A'),('E2','A'),('E3','B'),('E3','C')]:
    assert read(args.cuda/f'{stage}_{suite}_source_hashes.json')==sources[stage]
assert read(args.queue/'plan.json')['sources']==sources
assert read(args.analysis/'source_hashes.json')==sources
assert read(args.queue/'plan.json')['controller_sources']=={p.name:sha(p) for pattern in ('*.py','*.ps1','requirements.txt') for p in ROOT.glob(pattern)}
evidence=[]
for directory in [args.cuda,args.queue,args.analysis]:
    path=directory/'verification.json'
    assert read(path)['passed'] is True
    evidence.append({'path':str(path.resolve()),'sha256':sha(path)})
write(ROOT/'VALIDATION.json',{'passed':True,'created_at':now(),'sources':sources,'evidence':evidence,
      'scope':'CUDA exact resume and unchanged SAC, all A/B/C bindings, E1-to-E2 import, queue crash/retry, known-answer summaries',
      'scientific_effect_established':False})
print('Final implementation signoff passed.')
