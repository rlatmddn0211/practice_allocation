"""Audit the exact Git index bytes before the authorized README/media push."""
import argparse,hashlib,json,subprocess,uuid,shutil
from pathlib import Path
from datetime import datetime,timezone
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
def git(*a):return subprocess.check_output(['git',*a],cwd=ROOT)
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('verification');a=ap.parse_args()
    out=HERE/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_stage_'+uuid.uuid4().hex[:8]);out.mkdir(parents=True)
    shutil.copy2(__file__,out/'executed_verify_stage.py')
    (out/'source_hashes.json').write_text(json.dumps({'verify_stage.py':sha(Path(__file__).read_bytes())}),encoding='utf-8')
    try:
        v=json.loads((Path(a.verification)/'summary.json').read_text(encoding='utf-8'))
        expected=Path(v['published_readme']['path']).read_bytes()
        assert git('show',':README.md')==expected,'README index does not match checked published version'
        names=[p.decode() for p in git('diff','--cached','--name-only','-z').split(b'\0') if p]
        assert all(p in ('README.md','.gitattributes') or p.startswith(HERE.name+'/') for p in names),'Unrelated local work staged'
        assets=[]
        for name in names:
            if name=='README.md':continue
            raw=(ROOT/name).read_bytes();staged=git('show',':'+name)
            if name=='.gitattributes':raw=raw.replace(b'\r\n',b'\n')
            assert raw==staged,'Staged bytes differ: '+name
            if name.endswith(('.mp4','.gif')):assets.append(name)
        assert sum(p.endswith('.mp4') for p in assets)==8 and sum(p.endswith('.gif') for p in assets)==8
        assert sha((ROOT/'README.md').read_bytes())==v['working_readme_preserved_with_requested_changes']['sha256']
        assert sha((ROOT/'AGENTS.md').read_bytes())==v['working_agents_unchanged']['sha256']
        summary={'status':'passed','staged_files':len(names),'media_files':len(assets),'published_readme_sha256':sha(expected),
                 'unrelated_work_preserved':True,'new_environment_steps':0}
        (out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
        (out/'COMPLETE.json').write_text(json.dumps({'summary_sha256':sha((out/'summary.json').read_bytes())}),encoding='utf-8')
        print(json.dumps({'output_dir':str(out),**summary}))
    except BaseException:
        import traceback
        (out/'FAILED.json').write_text(json.dumps({'traceback':traceback.format_exc(),'new_environment_steps':0}),encoding='utf-8');raise
if __name__=='__main__':main()
