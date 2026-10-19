"""Freeze a reviewable joint delivery; preserve every prior run including failures."""
import ast
import csv
import json
import re
import shutil
import traceback
from pathlib import Path
from common import Run,ROOT,HERE,sha,save

VERSIONS=['27_success_retention_screening_v1','28_gradient_update_screening_v1']
REQUIRED={
 '27_success_retention_screening_v1':['20261014T071242Z_analysis_1ce07d19','20261014T071432Z_verify_analysis_3c86454f'],
 '28_gradient_update_screening_v1':['20261014T070936Z_measure_b6b065f3','20261014T071540Z_analysis_d2e18cbf',
                                 '20261014T071809Z_verify_measurements_9b3c92e4','20261014T071638Z_verify_analysis_bc729b29']}

def main():
    run=Run('delivery')
    try:
        inventory=[];artifacts=[];docs=[];costs={}
        for version in VERSIONS:
            d=ROOT/version
            for path in d.glob('*.py'):
                tree=ast.parse(path.read_text(encoding='utf-8'));run.hashed(path)
                for node in ast.walk(tree):
                    if isinstance(node,ast.ImportFrom):run.check('independent import '+path.name,not (node.module or '').startswith('practice_allocation'))
                run.check('no experiment sys.path injection '+path.name,'sys.path.insert' not in path.read_text(encoding='utf-8'))
            for path in list(d.glob('*.md'))+[d/'protocol.json',d/'requirements.txt']:
                docs.append(path)
            prior=[]
            for rd in sorted((d/'results').iterdir()):
                if not rd.is_dir() or rd==run.out:continue
                hashes=run.read(rd/'source_hashes.json')
                for name,digest in hashes.items():run.hashed(rd/'sources'/name,digest)
                if (rd/'summary.json').exists():
                    summary=run.read(rd/'summary.json');entry={'version':version,'run':rd.name,'status':summary['status'],'summary':summary}
                    run.check('no new environment',summary['new_environment_steps']==0)
                    run.check('no persistent learner update',summary['new_learner_updates']==0)
                    if summary['status']=='completed':
                        checks=run.read(rd/'checks.json');run.check('completed check count',sum(bool(c['passed']) for c in checks)==summary['checks_passed'] and not any(not c['passed'] for c in checks))
                else:
                    run.check('documented incomplete serialization run',rd.name=='20261014T071639Z_verify_measurements_1ff20d0b')
                    run.check('incomplete output preserved',(rd/'checks.json').exists() and (rd/'finite_differences.json').exists())
                    run.hashed(rd/'checks.json');run.hashed(rd/'finite_differences.json')
                    entry={'version':version,'run':rd.name,'status':'failed_during_serialization','wall_seconds':None,'cpu_seconds':None,
                        'observed_file_write_span_seconds':max(0,(rd/'checks.json').stat().st_mtime-(rd/'runtime.json').stat().st_mtime),
                        'note':'File write span is a filesystem proxy, not measured process wall time. Partial JSON is preserved. See technical_failures_ko.md.'}
                inventory.append(entry);prior.append(entry)
                for path in rd.rglob('*'):
                    if path.is_file():artifacts.append({'path':str(path.relative_to(ROOT)),'bytes':path.stat().st_size,'sha256':sha(path)})
            for required in REQUIRED[version]:
                s=next(x for x in prior if x['run']==required)
                run.check('required stage completed '+required,s['status']=='completed')
            costs[version]={'known_run_wall_sum_seconds':sum(e['summary']['wall_seconds'] for e in prior if 'summary' in e),
                'known_run_cpu_sum_seconds':sum(e['summary']['cpu_seconds'] for e in prior if 'summary' in e),
                'instrumented_CUDA_elapsed_sum_seconds':sum(e.get('summary',{}).get('gpu_compute_seconds',0) for e in prior),
                'virtual_optimizer_steps':sum(e.get('summary',{}).get('virtual_optimizer_steps',0) for e in prior),
                'missing_final_time_summaries':sum('summary' not in e for e in prior),
                'note':'Run wall sums may overlap. CUDA elapsed excludes uninstrumented verification GPU work. Current delivery bookkeeping excluded.'}
        docs += [ROOT/'README.md',ROOT/'AGENTS.md',ROOT/'.gitattributes']
        for path in docs:
            run.hashed(path);dest=run.out/'documents'/path.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)
            if path.suffix=='.md' and path.parent.name in VERSIONS:
                for target in re.findall(r'\]\(([^)]+)\)',path.read_text(encoding='utf-8')):
                    if '://' in target or target.startswith('#'):continue
                    run.check('report link '+str(path.name)+':'+target,(path.parent/target.split('#')[0]).exists())
        root=(ROOT/'README.md').read_text(encoding='utf-8')
        for line in ['| 학습 반응성 | 짧게 더 연습했을 때 해당 과제가 얼마나 개선되는가 |',
                     '| 다른 능력의 변화 | 그 연습으로 다른 과제의 성능이 얼마나 좋아지거나 떨어지는가 |',
                     '| 효과의 지속성 | 연습을 이어갈수록 개선 속도가 유지되는가, 포화되거나 역전되는가 |']:
            run.check('original three-factor table preserved',line in root)
        run.check('latest ledger indexed','28_gradient_update_screening_v1/factor_status_ko.md' in root)
        for version in VERSIONS:
            ss=run.read(ROOT/version/'results'/REQUIRED[version][0 if version.startswith('27') else 1]/'summary.json')
            report=(ROOT/version/'report_ko.md').read_text(encoding='utf-8').replace('−','-')
            run.check('reported primary effect '+version,f"{ss['primary']['vs_base_pp']:+.3f}" in report)
            run.check('not promoted without screen evidence',ss['operational_screen_pass'] is False)
        # Verify reused F05 numeric table against its already-delivered analysis hash record.
        old=ROOT/'26_critic_signal_screening_v1/results/20261014T062648Z_analysis_4a05b167/input_hashes.json'
        oldhash=run.read(old);path=ROOT/'26_critic_signal_screening_v1/results/20261014T062246Z_measure_10dac0ac/task_diagnostics.csv'
        run.hashed(path,oldhash[str(path)])
        # Evaluation banks across compositions contain no identical task/initial-state pairs.
        ad=ROOT/'27_success_retention_screening_v1/results/20261014T071242Z_analysis_1ce07d19';prov=run.rows(ad/'evaluation_provenance.csv');banks={}
        for s in 'ABC':
            item=next(x for x in prov if f'_{s}_s11_c200_base' in x['id']);es=run.rows(item['episodes_path'])
            banks[s]={(e['task'],e['initial_state_hash']) for e in es}
        for a,b in [('A','B'),('A','C'),('B','C')]:run.check('no cross-suite case overlap '+a+b,not banks[a]&banks[b])
        save(run.out/'prior_run_inventory.json',inventory);save(run.out/'artifact_manifest.json',artifacts);save(run.out/'costs.json',costs)
        run.finish({'status':'completed','versions':VERSIONS,'prior_runs':len(inventory),'artifact_files':len(artifacts),
                    'artifact_bytes':sum(a['bytes'] for a in artifacts),'recorded_costs':costs,
                    'failed_or_incomplete_runs':[e['run'] for e in inventory if e['status']!='completed'],
                    'publication':'local only; no git commit or push by this delivery'})
    except Exception:
        run.finish({'status':'failed','traceback':traceback.format_exc()});raise

if __name__=='__main__':main()
