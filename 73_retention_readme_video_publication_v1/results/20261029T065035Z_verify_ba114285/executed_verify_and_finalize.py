"""Check selected saved media, links and README-only publication scope."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import traceback
import uuid
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ref(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def save(p,x):
    with Path(p).open('x',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,indent=2)
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('preparation');a=ap.parse_args();prep=Path(a.preparation).resolve()
    out=HERE/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_verify_'+uuid.uuid4().hex[:8]);out.mkdir(parents=True)
    shutil.copy2(__file__,out/'executed_verify_and_finalize.py');save(out/'source_hashes.json',{'verify_and_finalize.py':sha(__file__)})
    checks=[]
    def check(name,ok):
        checks.append({'name':name,'passed':bool(ok)})
        if not ok:raise RuntimeError(name)
    try:
        state=read(prep/'prepublication_state.json');s=read(prep/'summary.json');cases=read(prep/'cases.json')
        check('base unchanged',git('rev-parse','HEAD').decode().strip()==state['base_commit'])
        check('local AGENTS untouched',sha(ROOT/'AGENTS.md')==state['local_agents_preserved']['sha256'])
        check('local README exact prepared content',sha(ROOT/'README.md')==s['local_readme_after']['sha256'])
        check('four paired examples',len(cases)==4 and {c['task'] for c in cases}=={'BP','DC'})
        for c in cases:
            check('opposite outcome examples',c['group'] in ('01','10'))
            for arm in ('C','D'):
                x=c[arm]
                for kind in ('published_mp4','published_preview'):
                    check('unchanged '+kind,sha(x[kind]['path'])==x[kind]['sha256'])
                check('MP4 byte identity',sha(x['published_mp4']['path'])==x['video_source']['sha256'])
                with Image.open(x['published_preview']['path']) as im:
                    check('animated GIF',im.n_frames>=2 and im.size==(320,288))
                    check('GIF below10MB',Path(x['published_preview']['path']).stat().st_size<10*1024**2)
                    if c['slug']=='bp_d_better' and arm=='D':
                        im.seek(im.n_frames//2);im.convert('RGB').save(out/'D_observation_ended_preview.png')
                for kind in ('episode','result'):
                    copied=prep/'inputs'/(c['slug']+'_'+arm+'_'+kind+'.json')
                    check('copied input identical',sha(copied)==x[kind]['sha256'])
        # Clarify wording without overwriting immutable prepared artifacts.
        replacement={'P는 200k 이전 기준':'P는 200k 사전학습 기준',
            '새 rollout이나 정책 실행을 생성하지 않았다.':'이 재시각화와 README 게시에서는 새 rollout이나 정책 실행을 생성하지 않았다.'}
        published=(prep/'published_README.md').read_text(encoding='utf-8')
        section=(prep/'readme_section.md').read_text(encoding='utf-8')
        working=(ROOT/'README.md').read_text(encoding='utf-8')
        for old,new in replacement.items():published=published.replace(old,new);section=section.replace(old,new);working=working.replace(old,new)
        (out/'published_README.md').write_text(published,encoding='utf-8',newline='\n')
        (out/'readme_section.md').write_text(section,encoding='utf-8',newline='\n')
        tracked={p.decode() for p in git('ls-files','-z').split(b'\0') if p}
        selected={p.relative_to(ROOT).as_posix() for p in HERE.rglob('*') if p.is_file() and
                  'source_snapshot' not in p.parts and '__pycache__' not in p.parts}
        for match in re.findall(r'\]\(([^)]+)\)',published):
            if match.startswith(('https://','http://','#')):continue
            path=match.split('#',1)[0]
            check('README link exists '+path,(ROOT/path).exists() or path in tracked)
            check('README link published '+path,path in tracked or path in selected)
        for n in (69,71,72):check('unpublished local index omitted '+str(n),not re.search(r'\]\('+str(n)+'_',published))
        check('8 GIF images',section.count('[![')==8)
        check('8 MP4 destinations',len(set(re.findall(r'\]\(([^)]+\.mp4)\)',section)))==8)
        check('no unsupported raw video HTML','<video' not in section)
        (ROOT/'README.md').write_text(working,encoding='utf-8',newline='\n')
        save(out/'summary.json',{'status':'passed','checks':len(checks),'preparation':ref(prep/'summary.json'),
            'published_readme':ref(out/'published_README.md'),'working_readme_preserved_with_requested_changes':ref(ROOT/'README.md'),
            'working_agents_unchanged':ref(ROOT/'AGENTS.md'),'media_bytes':s['media_bytes'],
            'new_environment_steps':0,'scope':'73 media/provenance and README only; unrelated local additions not staged'})
        save(out/'checks.json',checks);save(out/'COMPLETE.json',{'summary':ref(out/'summary.json')})
        print(json.dumps({'verification_dir':str(out),'published_readme':str(out/'published_README.md'),'checks':len(checks)}))
    except BaseException:
        save(out/'FAILED.json',{'traceback':traceback.format_exc(),'checks':checks,'new_environment_steps':0});raise

if __name__=='__main__':main()
