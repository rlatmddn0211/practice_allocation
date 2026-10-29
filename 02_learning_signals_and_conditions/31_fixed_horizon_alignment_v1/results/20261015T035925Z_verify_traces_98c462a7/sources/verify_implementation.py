"""Real-model diagnostic smoke, early-stop equivalence and formula verification."""
import argparse
import json
import os
import time
import traceback
import uuid
from datetime import datetime,timezone
from pathlib import Path


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--suite',required=True);ap.add_argument('--parent',required=True);args=ap.parse_args()
    os.environ['PRACTICE_SUITE']=args.suite;os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
    import csv
    import numpy as np
    from dataclasses import replace
    from practice_allocation.core import ROOT,Config,configure_runtime,write_json,runtime_manifest,derived_seed,TASKS
    from practice_allocation.environment import TaskEpisode,CostCounter
    from practice_allocation.evaluation import evaluate_model
    from practice_allocation.study_io import source_snapshot,load_portable
    from diagnostics import measure
    from verify_traces import verify_record
    from common import sha
    out=ROOT/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_verify_implementation_')+args.suite+'_'+uuid.uuid4().hex[:8]);out.mkdir(parents=True)
    source_snapshot(out);print(str(out),flush=True);checks=[];costs=CostCounter();started=time.perf_counter();cpu=time.process_time();engine=None
    def check(name,value,*_):
        checks.append({'name':name,'passed':bool(value)})
        if not value:raise AssertionError(name)
    try:
        config=replace(Config.load(ROOT/'configs/learner.json'),seed=12);configure_runtime(config)
        write_json(out/'runtime.json',runtime_manifest(config,'F05 technical verification'))
        ref=json.loads(Path(args.parent).read_text());write_json(out/'input_reference.json',ref);engine=load_portable(ref,config,costs)
        before=engine.fingerprints();bank=[]
        for task in range(4):
            seed=derived_seed(315099,ord(args.suite),task,0)
            with TaskEpisode(task,seed,costs) as ep:bank.append({'task':TASKS[task],'task_index':task,'episode_index':0,'seed':seed,'initial_state_hash':ep.initial_state_hash,'bank':'technical'})
        protocol=json.loads((ROOT/'protocol.json').read_text());result=measure(engine.model,bank,costs,out/'diagnostics',protocol,technical=True)
        check('full original state/RNG unchanged',engine.fingerprints()==before);result['learner_unchanged']=True;result['technical_smoke']=True
        write_json(out/'result.json',result)
        verify_record(result,check,lambda path,digest:check('trace hash',sha(path)==digest))
        evaluate_model(engine.model,bank,costs,out/'early_stop.csv','independent_reference',context='technical')
        with (out/'early_stop.csv').open(encoding='utf-8') as f:early=list(csv.DictReader(f))
        with Path(result['episodes_path']).open(encoding='utf-8') as f:fixed=list(csv.DictReader(f))
        return_errors=[]
        for a,b in zip(early,fixed):
            check('official success equals first-success evaluation',a['task']==b['task'] and a['success']==b['success'])
            error=abs(float(a['return'])-float(b['return_to_first_success']));return_errors.append(error)
            # Independent sequential and vectorized sums differ by roundoff only.
            check('return prefix equals original evaluator within1e-10',error<=1e-10)
            check('first success time agrees',int(a['length'])==(int(b['first_success_step']) if b['first_success_step'] else 500))
        check('reference evaluation preserves full state',engine.fingerprints()==before)
        summary={'status':'completed','suite':args.suite,'scientific_evidence':False,'maximum_return_sum_roundoff':max(return_errors)}
    except BaseException:
        summary={'status':'failed','suite':args.suite,'traceback':traceback.format_exc(),'scientific_evidence':False};traceback.print_exc()
    finally:
        if engine:engine.close()
        write_json(out/'checks.json',checks);summary.update(costs=costs.snapshot(),wall_seconds=time.perf_counter()-started,cpu_seconds=time.process_time()-cpu,
             checks_passed=sum(c['passed'] for c in checks),checks_failed=sum(not c['passed'] for c in checks));write_json(out/'summary.json',summary);print(json.dumps(summary,indent=2),flush=True)
    return 0 if summary['status']=='completed' else 1


if __name__=='__main__':raise SystemExit(main())
