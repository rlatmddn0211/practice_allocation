"""Real CUDA verification of suite binding, lossless resume, SAC, and allocation."""
from __future__ import annotations

import argparse
import csv
import io
import json
import lzma
import os
import pickle
import time
import traceback
import unittest
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--suite', choices=['A','B','C'], default='A')
    args=parser.parse_args()
    os.environ['PRACTICE_SUITE']=args.suite
    from practice_allocation.core import (ROOT,TASKS,ALLOCATIONS,Config,configure_runtime,capture_rng,
        restore_rng,fingerprint,write_json,source_hashes,runtime_manifest)
    from practice_allocation.environment import CostCounter, TaskEpisode
    from practice_allocation.engine import Engine
    from practice_allocation.evaluation import build_banks,evaluate_model
    from practice_allocation.learning import learning_state,attach_logger
    from practice_allocation.study_io import (AuditEngine,IntegrityError,source_snapshot,save_portable,
                                               load_portable,freeze_rules)
    import numpy as np
    from stable_baselines3 import SAC
    output=ROOT/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_verification_'+args.suite+'_'+uuid.uuid4().hex[:6])
    output.mkdir(parents=True,exist_ok=False)
    source_snapshot(output)
    config=replace(Config.load(ROOT/'configs/learner.json'),diagnostic_bank_episodes_per_task=2,
                   outcome_bank_episodes_per_task=2,bank_seed=95901)
    costs=CostCounter()
    checks=[]
    started=time.perf_counter()
    engine=None
    def check(name,condition,**details):
        record={'name':name,'passed':bool(condition),**details}
        checks.append(record)
        write_json(output/'checks'/f'{len(checks):02}_{name}.json',record)
        print(('PASS ' if condition else 'FAIL ')+name,flush=True)
        if not condition:
            raise AssertionError(name)
    success=False
    try:
        configure_runtime(config)
        write_json(output/'runtime.json',runtime_manifest(config,'technical_verification'))
        suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'))
        log=io.StringIO()
        unit=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
        (output/'unit_tests.txt').write_text(log.getvalue(),encoding='utf-8')
        check('unit_contracts',unit.wasSuccessful(),tests=unit.testsRun)
        rng=fingerprint(capture_rng())
        for task in range(4):
            with TaskEpisode(task,7850+task,costs) as first, TaskEpisode(task,7850+task,costs) as second:
                check('reset_'+TASKS[task],first.initial_state_hash==second.initial_state_hash and np.array_equal(first.observation[-4:],np.eye(4)[task]))
                actions=np.random.default_rng(task).uniform(-1,1,(8,4)).astype(np.float32)
                for action in actions:
                    assert fingerprint(first.step(action))==fingerprint(second.step(action))
        check('environment_rng_isolation',fingerprint(capture_rng())==rng)
        banks=build_banks(config,costs)
        write_json(output/'evaluation_banks.json',banks)
        engine=AuditEngine(config,costs)
        engine.audit_path=output/'training_reset_audit.csv'
        engine.forbidden=({r['initial_state_hash'] for rows in banks.values() for r in rows},
                          {r['task_parameter_hash'] for rows in banks.values() for r in rows},
                          {r['seed'] for rows in banks.values() for r in rows})
        learned=fingerprint(learning_state(engine.model))
        engine.train_steps(4000,'uniform',output/'metrics.csv',trace=True,episodes_path=output/'episodes.csv')
        check('shared_sac_updated',fingerprint(learning_state(engine.model))!=learned and engine.model._n_updates==3000 and engine.collected_steps.tolist()==[1000]*4)
        reference=save_portable(engine,output/'checkpoint')
        try:
            save_portable(engine,output/'checkpoint')
        except FileExistsError:
            check('checkpoint_overwrite_refused',True)
        else:
            check('checkpoint_overwrite_refused',False)
        before=engine.fingerprints()
        first=evaluate_model(engine.model,banks['diagnostic'],costs,output/'eval.csv','repeat1')
        second=evaluate_model(engine.model,banks['diagnostic'],costs,output/'eval.csv','repeat2')
        check('evaluation_reproducible_and_isolated',engine.fingerprints()==before and first['results_hash']==second['results_hash'])
        uninterrupted=engine.train_steps(1000,'uninterrupted',output/'metrics.csv',trace=True)
        final=engine.fingerprints()
        restored=load_portable(reference,config,costs,Engine)
        resumed=restored.train_steps(1000,'restored_original_engine',output/'metrics.csv',trace=True)
        check('compressed_resume_and_audit_observer_bitwise_equal',resumed['trace_sha256']==uninterrupted['trace_sha256'] and restored.fingerprints()==final)
        restored.close()
        instrumented=load_portable(reference,config,costs)
        rng=capture_rng()
        instrumented.model.train(gradient_steps=1,batch_size=config.batch_size)
        costs.train_iterations+=1
        expected=fingerprint(learning_state(instrumented.model))
        expected_rng=fingerprint(capture_rng())
        expected_indices=instrumented.model.replay_buffer.last_indices.copy()
        stock=SAC.load(Path(reference['path'])/'model.zip',device=config.device)
        with lzma.open(Path(reference['path'])/'replay.pkl.xz','rb') as stream:
            stock.replay_buffer=pickle.load(stream)
        attach_logger(stock)
        restore_rng(rng)
        stock.train(gradient_steps=1,batch_size=config.batch_size)
        costs.train_iterations+=1
        check('stock_sac_exact_update',fingerprint(learning_state(stock))==expected and fingerprint(capture_rng())==expected_rng and np.array_equal(stock.replay_buffer.last_indices,expected_indices))
        for candidate in ALLOCATIONS:
            branch=load_portable(reference,config,costs)
            old_learning=fingerprint(learning_state(branch.model))
            old_replay=fingerprint({k:v for k,v in branch.model.replay_buffer.state_for_hash().items() if k!='branch_start_step'})
            branch.start_branch(candidate,8121)
            check('branch_start_'+candidate,fingerprint(learning_state(branch.model))==old_learning and fingerprint({k:v for k,v in branch.model.replay_buffer.state_for_hash().items() if k!='branch_start_step'})==old_replay)
            branch.close()
        branch=load_portable(reference,config,costs,AuditEngine)
        candidate='DC_plus_WO_minus' if 'DC_plus_WO_minus' in ALLOCATIONS else 'F_'+TASKS[1]
        branch.start_branch(candidate,8121)
        old=branch.collected_steps.copy()
        run=branch.train_steps(4000,'branch',output/'metrics.csv',episodes_path=output/'branch_episodes.csv')
        counts=(branch.collected_steps-old).tolist()
        check('real_branch_quota_and_no_warmup',counts==(500*np.array(ALLOCATIONS[candidate])).tolist() and run['updates']==4000,counts=counts,candidate=candidate)
        saved=save_portable(branch,output/'branch_checkpoint')
        wrong=dict(saved,manifest_sha256='0'*64)
        try:
            load_portable(wrong,config,costs)
        except IntegrityError:
            check('corrupt_input_reference_refused',True)
        else:
            check('corrupt_input_reference_refused',False)
        branch.close()
        rates={'success_by_task':{t:.5 for t in TASKS}}
        rules=freeze_rules(rates,rates,100000)
        check('failure_progress_ties_use_uniform',rules['Failure']=='U' and rules['Progress']=='U')
        success=True
    except BaseException:
        (output/'failure.txt').write_text(traceback.format_exc(),encoding='utf-8')
        traceback.print_exc()
    finally:
        if engine:
            engine.close()
        write_json(output/'verification.json',{'passed':success,'suite':args.suite,'checks':checks,'source_hashes':source_hashes(),
                   'costs':costs.snapshot(),'seconds':time.perf_counter()-started,'scope':'technical verification; no scientific effects'})
    print(json.dumps({'passed':success,'output':str(output)}),flush=True)
    return 0 if success else 1


if __name__=='__main__':
    raise SystemExit(main())
