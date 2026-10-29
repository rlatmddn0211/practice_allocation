"""Prepare and verify the requested result publication, never run experiments."""
import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
import traceback
import uuid
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
NAMES={n:next(p for p in ROOT.iterdir() if p.is_dir() and p.name.startswith(str(n)+'_')) for n in (64,66,67,68)}
C64=NAMES[64]/'results/20261027T064706Z_baseline_1d8fb9bf'
C66=NAMES[66]/'results/20261027T130711Z_retention_1312ce94'
A66=NAMES[66]/'results/20261028T014720Z_analysis_0918111d'
V66=NAMES[66]/'results/20261028T014738Z_verify_f207b31f'
A67=NAMES[67]/'results/20261027T125938Z_analysis_9467d7b9'
V67=NAMES[67]/'results/20261027T130008Z_verify_e37dfa31'
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save(p,x):
    with Path(p).open('x',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rel(p):return Path(p).resolve().relative_to(ROOT).as_posix()
def files(directory):
    for p in Path(directory).rglob('*'):
        if not p.is_file():continue
        if any(x in p.parts for x in ('source_snapshot','__pycache__','.venv','sources')):continue
        if p.suffix in ('.py','.md','.json','.csv','.txt','.ps1') and p.name not in ('ACTIVE_CAMPAIGN.json','ACTIVE_QUEUE.json','STATUS.json'):
            yield p
def main():
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=('prepare','verify'));ap.add_argument('--preparation');a=ap.parse_args()
    out=HERE/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+a.mode+'_'+uuid.uuid4().hex[:8])
    (out/'sources').mkdir(parents=True)
    for name in ('publish.py','README.md'):shutil.copy2(HERE/name,out/'sources'/name)
    save(out/'source_hashes.json',{name:sha(HERE/name) for name in ('publish.py','README.md')})
    checks=[]
    def check(name,ok):
        checks.append({'name':name,'passed':bool(ok)})
        if not ok:raise AssertionError(name)
    try:
        check('origin',git('remote','get-url','origin').decode().strip()=='https://github.com/rlatmddn0211/practice_allocation.git')
        check('main',git('branch','--show-current').decode().strip()=='main')
        for n,cam in ((64,C64),(66,C66)):
            plan=read(cam/'plan.json')
            for name,h in plan['source_hashes'].items():check(str(n)+' executed source '+name,sha(NAMES[n]/name)==h)
            completion=read(cam/'completion_summary.json')
            check(str(n)+' completed',completion['status']=='completed' and len(completion['completed'])==(20 if n==64 else40) and not completion['failed'])
            for entry in completion['completed']:
                for key in ('result','costs'):
                    ref=entry[key];check(entry['id']+' '+key,sha(ref['path'])==ref['sha256'])
                result=read(entry['result']['path']);check(entry['id']+' episodes',sha(result['episodes']['path'])==result['episodes']['sha256'])
        for analysis,verify in ((A66,V66),(A67,V67)):
            s=read(analysis/'summary.json');v=read(verify/'summary.json')
            check(str(analysis)+' analysis hash',sha(analysis/'summary.json')==read(analysis/'COMPLETE.json')['summary_sha256'])
            check(str(verify)+' verification',v['status']=='passed' and v['full_campaign'] and not v['self_test_only'])
        if a.mode=='prepare':
            check('clean existing index',not git('diff','--cached','--name-only').strip())
            check('fetched remote synchronized',git('rev-parse','HEAD')==git('rev-parse','origin/main'))
            selected=set()
            for n,cam in ((64,C64),(66,C66)):
                for name in read(cam/'plan.json')['source_hashes']:selected.add(rel(NAMES[n]/name))
                selected.update(rel(p) for p in files(cam))
            for n in (67,68):
                selected.update(rel(p) for p in NAMES[n].iterdir() if p.is_file() and p.suffix in ('.py','.md','.json','.txt'))
                if n==67:selected.update(rel(p) for p in files(NAMES[n]/'inputs'))
            for directory in (A66,V66,A67,V67,NAMES[68]/'results',
                NAMES[64]/'results/20261027T064040Z_technical_a47c3a21',
                NAMES[64]/'results/20261027T064640Z_technical_repair_900a1b32',
                NAMES[64]/'results/20261027T125927Z_analysis_66bfae10',
                NAMES[66]/'results/20261027T130041Z_technical_1175c85d',
                NAMES[66]/'results/20261027T112624Z_launch_016af200',
                NAMES[66]/'results/20261027T112625Z_deferred_1357e818'):
                selected.update(rel(p) for p in files(directory))
            selected.add(rel(C64/'analysis_stderr.log'))
            arrays=[]
            for directory in (A66,A67):
                for name in ('bootstrap_draws.npz','case_resample_counts.npz'):
                    arrays.append(rel(directory/name));selected.add(rel(directory/name))
            selected.update((rel(HERE/'README.md'),rel(HERE/'publish.py'),'.gitattributes'))
            groups=defaultdict(lambda:{'files':0,'bytes':0});manifest=[]
            for name in sorted(selected):
                path=ROOT/name;check('file below50MiB '+name,path.stat().st_size<50*1024**2)
                check('no excluded scope '+name,not re.match(r'^(61_|62_|63_|65_|69_|52_|59_)',name))
                manifest.append({'path':name,'bytes':path.stat().st_size,'sha256':sha(path)})
                group=groups[name.split('/')[0]];group['files']+=1;group['bytes']+=path.stat().st_size
            readme=git('show','HEAD:README.md').decode('utf-8')
            header='''2026-10-28 공개: [68번 보존 개입 결과와 해석](68_retention_intervention_result_review_v1/results/20261028T072607Z_review_323af171/report_ko.md).
기준선20분기와보존비교40분기를모두완료했고,원자료CSV·동결명세·실제seed·비용·독립검산·재표집결과를함께게시했습니다.
성공경험우선보존D−일반경험보존C는+2.55%p(조건부사례95%구간[+1.499,+3.650])이고,
기본SAC대비D는+1.10%p([−0.25,+2.45])로총성능우위는미확정입니다.
BP와일부부모에집중된효과,신규획득·상실·회복의손익과한계를[근거원장](68_retention_intervention_result_review_v1/results/20261028T072607Z_review_323af171/evidence_record.json)에기록했습니다.
정확한게시범위와로컬보관항목은[70번게시기록](70_retention_results_github_publication_v1/README.md)을따릅니다.
아래기존59번등의진행상태서술은앞선공개시점의역사적기록입니다.

'''
            readme=readme.replace('\n\n','\n\n'+header,1)
            (out/'published_README.md').write_text(readme,encoding='utf-8',newline='\n')
            agents=git('show','HEAD:AGENTS.md').decode('utf-8');working=(ROOT/'AGENTS.md').read_text(encoding='utf-8')
            start=working.index('- On 2026-10-27 the user explicitly authorized the final twenty-branch baseline')
            end=working.index('- On2026-10-28 the user',start)
            (out/'published_AGENTS.md').write_text(agents.rstrip()+'\n\n'+working[start:end].rstrip()+'\n',encoding='utf-8',newline='\n')
            roots={'README.md':{'path':str(out/'published_README.md'),'sha256':sha(out/'published_README.md')},
                   'AGENTS.md':{'path':str(out/'published_AGENTS.md'),'sha256':sha(out/'published_AGENTS.md')}}
            save(out/'root_index_content.json',roots)
            scope={'base_commit':git('rev-parse','HEAD').decode().strip(),'selected_files':sorted(selected),
                'explicit_ignored_arrays':arrays,'groups':dict(groups),'files':len(selected),
                'bytes':sum(x['bytes'] for x in manifest),'root_index_content':roots,
                'working_root_files_preserved':{'README.md':sha(ROOT/'README.md'),'AGENTS.md':sha(ROOT/'AGENTS.md')},
                'scope':'68 review and direct64/66/67 evidence;69 not included',
                'full_checkpoint_backup':False,'new_environment_steps':0}
            save(out/'publication_scope.json',scope)
            with (out/'manifest.csv').open('x',encoding='utf-8',newline='') as f:
                w=csv.DictWriter(f,fieldnames=('path','bytes','sha256'));w.writeheader();w.writerows(manifest)
            ordinary=[s for s in sorted(selected) if s not in arrays]
            (out/'staging_paths.nul').write_bytes(b'\0'.join(x.encode() for x in ordinary)+b'\0')
            (out/'array_paths.nul').write_bytes(b'\0'.join(x.encode() for x in arrays)+b'\0')
        else:
            prep=Path(a.preparation).resolve();scope=read(prep/'publication_scope.json')
            check('unchanged base',git('rev-parse','HEAD').decode().strip()==scope['base_commit'])
            with (prep/'manifest.csv').open(encoding='utf-8',newline='') as f:manifest=list(csv.DictReader(f))
            allowed=set(scope['selected_files'])|set(scope['root_index_content'])
            changed={p.decode() for p in git('diff','--cached','--name-only','-z').split(b'\0') if p}
            check('all selected staged',allowed.issubset(changed))
            check('no unrelated changes staged',all(p in allowed or p.startswith(HERE.name+'/') for p in changed))
            for row in manifest:
                name=row['path'];data=git('show',':'+name)
                expected=(ROOT/name).read_bytes()
                if name=='.gitattributes':expected=expected.replace(b'\r\n',b'\n')
                check('staged bytes '+name,data==expected)
                check('original file unchanged '+name,sha(ROOT/name)==row['sha256'])
            for name,ref in scope['root_index_content'].items():
                check('root index scoped '+name,git('show',':'+name)==Path(ref['path']).read_bytes())
                check('local root preserved '+name,sha(ROOT/name)==scope['working_root_files_preserved'][name])
            patterns=[rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',rb'ghp_[A-Za-z0-9]{36}',rb'github_pat_[A-Za-z0-9_]{70,}',rb'AKIA[0-9A-Z]{16}',rb'sk-proj-[A-Za-z0-9_-]{40,}']
            for name in changed:
                data=git('show',':'+name)
                check('no credential material '+name,not any(re.search(p,data) for p in patterns))
            save(out/'verified_scope.json',{'preparation':str(prep),'staged_files':len(changed),
                'base_commit':scope['base_commit'],'scope':'68 and direct supporting records only'})
        save(out/'summary.json',{'status':'passed','checks':len(checks),'new_environment_steps':0,
            'git':git('--version').decode().strip(),'python':sys.version})
        save(out/'COMPLETE.json',{'summary_sha256':sha(out/'summary.json')})
    except BaseException:
        save(out/'FAILED.json',{'traceback':traceback.format_exc(),'checks':checks,'new_environment_steps':0});raise
    print(json.dumps({'output_dir':str(out),'checks':len(checks),'mode':a.mode},ensure_ascii=False))
if __name__=='__main__':main()
