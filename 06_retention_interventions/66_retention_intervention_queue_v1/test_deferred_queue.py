"""Small, file-only queue fixtures; no learner, environment or subprocess runs."""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import deferred_queue as dq

def put(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if isinstance(value,bytes):path.write_bytes(value)
    else:path.write_text(json.dumps(value),encoding='utf-8')
    return path
def ref(path):return {'path':str(path.resolve()),'sha256':dq.sha(path)}

class Fixture:
    def __init__(self,base):
        self.version=Path(base)/'64_fixture';self.cam=self.version/'results/pinned_campaign'
        self.cam.mkdir(parents=True)
        source={}
        for name in ('worker.py','analyze_baseline.py','verify_baseline.py'):
            body=b'# inert fixture, never executed\n'
            if name=='analyze_baseline.py':body+=b'evaluated = sum(row["length"] for row in worker_rows)\n'
            source[name]=dq.sha(put(self.version/name,body))
        states=[]
        for i in range(5):
            cp=self.version/'original_states'/str(i)
            manifest={'step':208000,'state_fingerprints':{'learning':'L','replay':'R','collector':'C','rng':'G'}}
            path=put(cp/'checkpoint_manifest.json',manifest)
            states.append({'parent':41011+i,'checkpoint':{'path':str(cp),'manifest_sha256':dq.sha(path)}})
        jobs=[];completed=[]
        for index in range(20):
            state_index=index//4;condition=('dose25','dose625')[index%2]
            job={'id':'job_'+str(index),'state_index':state_index,'parent':41011+state_index,
                 'future':index%4//2+1,'root_seed':100+index//2,'condition':condition}
            jobs.append(job);attempt=self.cam/'jobs'/job['id']/'one_attempt'
            checkpoints=[]
            for end in (212000,216000,224000,240000):
                cp=attempt/'checkpoints'/str(end);files={}
                for name in ('model.zip','replay.pkl.xz','collector_and_rng.pkl'):
                    files[name]=dq.sha(put(cp/name,b'inert bytes, never loaded'))
                m=put(cp/'checkpoint_manifest.json',{'step':end,'updates':end-1000,
                    'source_hashes':source,'files':files})
                checkpoints.append({'path':str(cp),'manifest_sha256':dq.sha(m),'absolute_step':end})
            ep=put(attempt/'evaluation_episodes.csv',b'fixture CSV; semantic verification represented by inert verifier marker\n')
            result={'id':job['id'],'job':job,'state':states[state_index],'status':'completed',
                    'training_steps':32000,'evaluation_steps':1000,'checkpoints':checkpoints,'episodes':ref(ep)}
            r=put(attempt/'result.json',result)
            c=put(attempt/'costs.json',{'status':'completed','training_steps':32000,'evaluation_steps':1000,
                'costs':{'train_iterations':32000,'evaluation_episodes':440,'environment_steps':33000}})
            completed.append({'id':job['id'],'result':ref(r),'costs':ref(c)})
            put(self.cam/'completed'/(job['id']+'.json'),ref(r))
            put(attempt/'request.json',{'job':job,'source_hashes':source,'output':str(attempt)})
            put(attempt/'runtime.json',{'source_hashes':source,'job':job})
            put(attempt/'research_start_integrity.json',{'restored_original_S_again':True,
                'environment_steps_before_fork':0,'full_fingerprints':{'learning':'L','replay':'R','collector':'C','rng':'G'}})
            put(attempt/'fork_integrity.json',{'before':{'learning':'L','replay':'R'},'after':{'learning':'L','replay':'R'},
                'preserved_visits_and_queue':True,'root_seed':job['root_seed'],'condition':condition})
        self.plan={'jobs':jobs,'states':states,'source_hashes':source,'technical_steps':8555,'new_P_S_evaluation_steps':0}
        plan_path=put(self.cam/'plan.json',self.plan);integrity=put(self.cam/'plan_integrity.json',ref(plan_path))
        self.config={'schema_version':1,'campaign':str(self.cam),'plan':ref(plan_path),
                     'plan_integrity':ref(integrity),'source_hashes':source,'expected_jobs':20}
        self.status={'status':'completed','completed':20,'failed':0,'total':20,'error':None,
                     'training_steps':640000,'evaluation_steps':20000,'actual_environment_steps':668555,
                     'unaccounted_attempt_reserved_upper_bound':0}
        put(self.cam/'STATUS.json',self.status)
        put(self.cam/'completion_summary.json',{'status':'completed','planned_jobs':20,'failed':[],
            'completed':completed,'training_steps':640000,'evaluation_steps':20000,'total_environment_steps':668555})
        self.analysis=self.version/'results/exact_analysis'
        summary=put(self.analysis/'summary.json',{'execution_status':'completed_file_only_analysis','completed_jobs':20,
            'planned_jobs':20,'campaign':str(self.cam),'analysis_new_environment_steps':0,'analysis_SAC_updates':0,
            'future_execution_authorized_by_analysis':False})
        put(self.analysis/'checks.json',{'passed':10,'failed':[]})
        assets=put(self.analysis/'input_assets.json',[])
        put(self.analysis/'COMPLETE.json',{'status':'completed','summary_sha256':dq.sha(summary)})
        put(self.cam/'analysis_result.json',{'analysis':str(self.analysis),'summary':ref(summary)})
        self.verify=self.version/'results/exact_verification'
        vs=put(self.verify/'summary.json',{'status':'passed','full_campaign':True,'self_test_only':False,
            'new_environment_steps':0,'SAC_updates':0})
        put(self.verify/'COMPLETE.json',{'status':'completed','summary_sha256':dq.sha(vs)})
        put(self.verify/'verified_inputs.json',{'analysis':str(self.analysis),'summary_sha256':dq.sha(summary),
            'asset_receipt_sha256':dq.sha(assets)})
        put(self.verify/'source_hashes.json',{name:source[name] for name in ('analyze_baseline.py','verify_baseline.py')})
        put(self.cam/'verify_stdout.log',(json.dumps({'verification_dir':str(self.verify)})+'\n').encode())

class QueueContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.fixture=Fixture(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def test_complete_exact_chain(self):
        with patch('subprocess.Popen',side_effect=AssertionError('Subprocess forbidden in fixture test')):
            result=dq.validate_predecessor(self.fixture.config)
        self.assertEqual(result['status'],'passed');self.assertEqual(result['completed_jobs'],20)
        self.assertGreater(len(result['artifact_hashes']),200)
    def test_running_does_not_trigger_even_with_completion_artifacts(self):
        put(self.fixture.cam/'STATUS.json',{**self.fixture.status,'status':'running'})
        with self.assertRaises(dq.Pending):dq.validate_predecessor(self.fixture.config)
    def test_numerical_failure_terminal_does_not_trigger(self):
        put(self.fixture.cam/'STATUS.json',{**self.fixture.status,'status':'completed_with_numerical_failures','failed':1})
        with self.assertRaises(dq.Rejected):dq.validate_predecessor(self.fixture.config)
    def test_altered_result_hash_rejected(self):
        path=self.fixture.cam/'jobs/job_0/one_attempt/result.json'
        put(path,{**dq.load(path),'training_steps':1})
        with self.assertRaises(dq.Rejected):dq.validate_predecessor(self.fixture.config)
    def test_partial_verification_cannot_masquerade_as_complete(self):
        path=self.fixture.verify/'summary.json';put(path,{**dq.load(path),'full_campaign':False})
        put(self.fixture.verify/'COMPLETE.json',{'status':'completed','summary_sha256':dq.sha(path)})
        with self.assertRaises(dq.Rejected):dq.validate_predecessor(self.fixture.config)
    def test_self_test_verification_rejected(self):
        path=self.fixture.verify/'summary.json';put(path,{**dq.load(path),'self_test_only':True})
        put(self.fixture.verify/'COMPLETE.json',{'status':'completed','summary_sha256':dq.sha(path)})
        with self.assertRaises(dq.Rejected):dq.validate_predecessor(self.fixture.config)
    def test_changed_checkpoint_bytes_rejected(self):
        put(self.fixture.cam/'jobs/job_0/one_attempt/checkpoints/212000/replay.pkl.xz',b'tampered inert bytes')
        with self.assertRaises(dq.Rejected):dq.validate_predecessor(self.fixture.config)
    def test_duplicate_dispatch_is_never_retried(self):
        path=Path(self.temp.name)/'claim.json';dq.claim_dispatch(path,{'first':True})
        with self.assertRaises(dq.Rejected):dq.claim_dispatch(path,{'second':True})
        self.assertTrue(dq.load(path)['first'])
    def test_exact_stdout_path_rejects_two_runs(self):
        path=Path(self.temp.name)/'stdout.log'
        put(path,(json.dumps({'run':str(Path(self.temp.name)/'a')})+'\n'+json.dumps({'run':str(Path(self.temp.name)/'b')})).encode())
        with self.assertRaises(dq.Rejected):dq.exact_stdout_path(path,'run',self.temp.name)
    def test_source_pin_detects_late_additions(self):
        root=Path(self.temp.name)/'downstream';put(root/'protocol.json',{'jobs':40})
        pin=dq.source_hashes(root);put(root/'late_source.py',b'# extra source')
        with self.assertRaises(dq.Rejected):dq.check_source_pin(root,pin)
    def test_stop_prevents_next_stage_without_touching_upstream(self):
        queue=dq.DeferredQueue.__new__(dq.DeferredQueue)
        queue.root=Path(self.temp.name)/'downstream';queue.run=queue.root/'results/new_queue'
        queue.run.mkdir(parents=True);put(queue.root/'STOP',b'cancel')
        with self.assertRaises(dq.Cancelled):queue.check_before_stage()
    def test_no_heavy_dependencies_imported_by_queue(self):
        self.assertNotIn('torch',dq.__dict__);self.assertNotIn('numpy',dq.__dict__)
    def test_child_technical_marker_requires_success_and_frozen_source(self):
        root=Path(self.temp.name)/'child_technical';pin={'worker.py':'fixed'}
        summary=put(root/'summary.json',{'status':'passed','failed_checks':[],
            'source_hashes':pin,'total_technical_environment_steps_all_attempts':100})
        put(root/'VERIFIED.json',{'summary':ref(summary),'source_hashes':pin})
        self.assertEqual(dq.validate_technical_marker(root,pin)[1]['status'],'passed')
        put(root/'VERIFIED.json',{'summary':ref(summary),'source_hashes':{'worker.py':'changed'}})
        with self.assertRaises(dq.Rejected):dq.validate_technical_marker(root,pin)
    def test_only_exact_known_analysis_failure_can_use_pinned_file_only_repair(self):
        fix=Path(self.temp.name)/'67_fixture'
        put(fix/'analyze_baseline.py',b'# inert corrected analysis fixture\n')
        put(fix/'verify_baseline.py',b'# inert independent verification fixture\n')
        repair={'root':str(fix),'source_hashes':dq.source_hashes(fix),
                'known_source_line':'        evaluated = sum(row["length"] for row in worker_rows)',
                'known_error_message':"unsupported operand type(s) for +: 'int' and 'str'"}
        config={**self.fixture.config,'analysis_repair':repair}
        original_status={**self.fixture.status,'status':'research_completed_analysis_failed'}
        put(self.fixture.cam/'STATUS.json',original_status)
        (self.fixture.cam/'analysis_result.json').unlink()
        stderr='Traceback (most recent call last):\n  File "'+str(self.fixture.version/'analyze_baseline.py')+'", line 2\n'
        stderr+='    evaluated = sum(row["length"] for row in worker_rows)\n'
        stderr+="TypeError: unsupported operand type(s) for +: 'int' and 'str'\n"
        put(self.fixture.cam/'analysis_stderr.log',stderr.encode())
        waiting=dq.validate_predecessor(config,allow_known_repair=True)
        self.assertTrue(waiting['requires_analysis_repair'])
        with self.assertRaises(dq.Rejected):dq.validate_predecessor(config)
        analysis=fix/'results/fixed_analysis';verification=fix/'results/fixed_verification'
        shutil.copytree(self.fixture.analysis,analysis);shutil.copytree(self.fixture.verify,verification)
        put(verification/'source_hashes.json',repair['source_hashes'])
        put(verification/'verified_inputs.json',{'analysis':str(analysis),
            'summary_sha256':dq.sha(analysis/'summary.json'),'asset_receipt_sha256':dq.sha(analysis/'input_assets.json')})
        certificate={'analysis':str(analysis),'summary':ref(analysis/'summary.json'),
            'verification':str(verification),'repair_source_hashes':repair['source_hashes']}
        result=dq.validate_predecessor(config,analysis_override=certificate)
        self.assertEqual(result['status'],'passed')
        self.assertEqual(result['analysis_origin'],'separate_pinned_file_only_repair')
        self.assertEqual(dq.load(self.fixture.cam/'STATUS.json'),original_status)
        put(self.fixture.cam/'analysis_stderr.log',stderr.replace("'int' and 'str'","'float' and 'str'").encode())
        with self.assertRaises(dq.Rejected):dq.validate_predecessor(config,allow_known_repair=True)

if __name__=='__main__':unittest.main(verbosity=2)
