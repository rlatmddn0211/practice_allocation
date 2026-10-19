"""Final provenance, record completeness and local report-link validation."""
import re
import shutil
import traceback
from pathlib import Path
from common import Run,HERE,ROOT,save,sha,table

def main():
    run=Run('delivery')
    try:
        dirs={'measurement':'20261014T062246Z_measure_10dac0ac','analysis':'20261014T062648Z_analysis_4a05b167',
              'verify_measurements':'20261014T062957Z_verify_measurements_61c9843d','verify_analysis':'20261014T062957Z_verify_analysis_d5cee918'}
        summaries={}
        for role,name in dirs.items():
            d=HERE/'results'/name;s=run.read(d/'summary.json');summaries[role]=s
            run.check('completed '+role,s['status']=='completed' and s['checks_failed']==0)
            hashes=run.read(d/'source_hashes.json')
            for filename,digest in hashes.items():run.hashed(d/'sources'/filename,digest)
            run.check('no new environment '+role,s['new_environment_steps']==0 and s['new_learner_updates']==0)
        run.check('main sizes',summaries['measurement']['snapshots']==192 and summaries['measurement']['transitions_measured']==1572864)
        run.check('raw measurements independently verified',summaries['verify_measurements']['raw_transitions']==1572864)
        run.check('all selections verified',summaries['verify_analysis']['selections_verified']==648)
        run.check('primary result',summaries['analysis']['primary']['vs_base_scale_pp']==0 and not summaries['analysis']['operational_screen_pass'])
        for role,files in [('measurement',['measure.py','common.py','protocol.json']),('analysis',['analyze.py','common.py','protocol.json']),
                           ('verify_measurements',['verify_measurements.py','common.py']),('verify_analysis',['verify_analysis.py','common.py'])]:
            for name in files:
                run.check('delivered code matches executed '+role+name,sha(HERE/name)==sha(HERE/'results'/dirs[role]/'sources'/name))
        docs=[HERE/'README.md',HERE/'report_ko.md',HERE/'factor_status_ko.md',ROOT/'README.md']
        links=0
        for doc in docs:
            body=doc.read_text(encoding='utf-8-sig');run.hashed(doc)
            dest=run.out/'documents'/('root_README.md' if doc==ROOT/'README.md' else doc.name)
            dest.parent.mkdir(exist_ok=True);shutil.copy2(doc,dest)
            for target in re.findall(r'\]\(([^)]+)\)',body):
                if target.startswith(('http:','https:')):continue
                path=target.split('#')[0]
                if not path:continue
                run.check('document link '+str(doc.name)+' '+target,(doc.parent/path).exists());links+=1
        report=(HERE/'report_ko.md').read_text(encoding='utf-8')
        for phrase in ['0.00%p','6.361','6.389','36건','보류','부분','500-step','float32','40k']:
            run.check('report retains key scope '+phrase,phrase in report)
        # All attempts remain, including both failed numerical checks.
        attempts=[]
        for path in sorted((HERE/'results').glob('*/summary.json')):
            s=run.read(path)
            attempts.append({'directory':path.parent.name,'status':s['status'],'wall_seconds':s['wall_seconds'],'cpu_seconds':s['cpu_seconds'],
                             'checks_failed':s.get('checks_failed',0),'gpu_forward_seconds':s.get('gpu_forward_seconds',0),
                             'new_environment_steps':s['new_environment_steps'],'new_learner_updates':s['new_learner_updates']})
        run.check('two failed numerical verifications preserved',sum(a['status']=='failed' for a in attempts)==2)
        table(run.out/'attempt_costs.csv',attempts)
        run.finish({'status':'completed','local_links_checked':links,'scientific_runs':dirs,'attempts':len(attempts),
                    'failed_attempts_preserved':2,'program_wall_seconds_sum_including_parallel_overlap':sum(a['wall_seconds'] for a in attempts),
                    'program_cpu_seconds_sum':sum(a['cpu_seconds'] for a in attempts),'forward_gpu_seconds_sum':sum(a['gpu_forward_seconds'] for a in attempts),
                    'scope':'F05 critic diagnostic screen completed; other F05 subquestions remain untested'})
    except Exception:
        run.finish({'status':'failed','traceback':traceback.format_exc()});raise

if __name__=='__main__':main()
