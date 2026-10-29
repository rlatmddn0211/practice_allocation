"""Prepare a research-question layout from published Git blobs, never runtime files."""
import argparse,csv,hashlib,json,os,posixpath,re,shutil,subprocess,traceback,uuid
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import quote,unquote,urlsplit,urlunsplit

HERE=Path(__file__).resolve().parent
ROOT=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=HERE).decode().strip()).resolve()
TOOL='07_operations_and_publication/'+HERE.name

def git(*args,input=None):return subprocess.check_output(['git',*args],cwd=ROOT,input=input)
def sha(data):return hashlib.sha256(data).hexdigest()
def oid(data):return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False)
def unique(label):
    p=HERE/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+label+'_'+uuid.uuid4().hex[:8]);p.mkdir(parents=True,exist_ok=False);return p
def snapshot(out):
    hashes={}
    for p in HERE.iterdir():
        if p.is_file() and (p.suffix in ('.py','.md','.json') or p.name=='.gitignore'):
            target=out/'source_snapshot'/p.name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target);hashes[p.name]=sha(p.read_bytes())
    save(out/'source_hashes.json',hashes)
def tree(base):
    entries={}
    for part in git('ls-tree','-r','-z',base).split(b'\0'):
        if not part:continue
        meta,name=part.split(b'\t',1);mode,kind,key=meta.decode().split()
        if kind!='blob':raise RuntimeError('Unsupported non-blob tree entry '+name.decode())
        entries[name.decode()]={'mode':mode,'oid':key}
    return entries
def blobs(keys):
    keys=list(dict.fromkeys(keys));raw=git('cat-file','--batch',input=('\n'.join(keys)+'\n').encode());out={};cursor=0
    for key in keys:
        end=raw.index(b'\n',cursor);header=raw[cursor:end].decode().split();size=int(header[2]);cursor=end+1
        value=raw[cursor:cursor+size];cursor+=size+1
        if oid(value)!=key:raise RuntimeError('Git blob identity failure')
        out[key]=value
    return out
def local_state():
    return {'head':git('rev-parse','HEAD').decode().strip(),'index_sha256':sha(git('ls-files','--stage','-z')),
        'README_sha256':sha((ROOT/'README.md').read_bytes()),'AGENTS_sha256':sha((ROOT/'AGENTS.md').read_bytes())}
def directories(paths):
    out={'.'}
    for p in paths:
        while '/' in p:p=p.rsplit('/',1)[0];out.add(p)
    return out
def map_path(path,mapping):
    first,sep,rest=path.partition('/');return mapping.get(first,first)+(sep+rest if sep else '')

# Every destination is parsed independently, including outer MP4 targets of linked GIFs.
INLINE=re.compile(r'(?P<prefix>\]\()(?P<url><[^>\n]+>|[^\s)]+)(?P<tail>[^)\n]*\))')
REF=re.compile(r'(?m)^(?P<prefix>\s{0,3}\[[^\]\n]+\]:\s*)(?P<url><[^>\n]+>|\S+)')
HTML=re.compile(r'(?P<prefix>\b(?:href|src|poster)\s*=\s*[\"\x27])(?P<url>[^\"\x27]+)(?P<tail>[\"\x27])')

def rewrite_markdown(raw,old_path,new_path,mapping,valid_paths,audit):
    bom=raw.startswith(b'\xef\xbb\xbf');text=raw.decode('utf-8-sig');edits=[];fenced=False;fence_char='';fence_length=0
    def replace_target(match):
        target=match.group('url');angle=target.startswith('<') and target.endswith('>');url=target[1:-1] if angle else target
        u=urlsplit(url)
        published=re.match(r'^/(rlatmddn0211/practice_allocation/(?:tree|blob|raw)/main/)(.*)$',u.path) if u.netloc=='github.com' else None
        if published:
            old_target=posixpath.normpath(unquote(published.group(2)))
        else:
            if u.scheme or u.netloc or not u.path or u.path.startswith('/'):return match.group(0)
            old_target=posixpath.normpath(posixpath.join(posixpath.dirname(old_path),unquote(u.path).replace('\\','/')))
        if old_target not in valid_paths:
            audit['preexisting_missing']+=1
            if len(audit['missing_examples'])<30:audit['missing_examples'].append({'document':old_path,'target':url})
            return match.group(0)
        audit['originally_valid']+=1
        new_target=map_path(old_target,mapping)
        rel=('/'+published.group(1)+new_target) if published else posixpath.relpath(new_target,posixpath.dirname(new_path) or '.')
        if u.path.endswith('/') and not rel.endswith('/'):rel+='/'
        rewritten=urlunsplit((u.scheme if published else '',u.netloc if published else '',quote(rel,safe='/'),u.query,u.fragment))
        # Keep already-correct same-version spellings and percent encodings.
        old_after_move=old_target if published else posixpath.normpath(posixpath.join(posixpath.dirname(new_path),unquote(u.path).replace('\\','/')))
        if old_after_move==new_target:
            audit['valid_unchanged']+=1;return match.group(0)
        edits.append({'old_target':url,'new_target':rewritten,'resolved_old':old_target,'resolved_new':new_target})
        audit['corrected_targets']+=1
        if map_path(old_target,mapping)!=new_target:raise RuntimeError('Link target mapping error')
        replacement='<'+rewritten+'>' if angle else rewritten
        return match.group(0)[:match.start('url')-match.start()]+replacement+match.group(0)[match.end('url')-match.start():]
    lines=[]
    for line in text.splitlines(keepends=True):
        fence=re.match(r'^\s{0,3}(`{3,}|~{3,})',line)
        if fence:
            if not fenced:fenced=True;fence_char=fence.group(1)[0];fence_length=len(fence.group(1))
            elif fence.group(1)[0]==fence_char and len(fence.group(1))>=fence_length and not line[fence.end():].strip():fenced=False
            lines.append(line);continue
        if fenced:lines.append(line);continue
        # Inline code examples are kept as recorded text.
        parts=re.split(r'(`+[^`]*`+)',line)
        for i in range(0,len(parts),2):
            value=INLINE.sub(replace_target,parts[i]);value=REF.sub(replace_target,value);value=HTML.sub(replace_target,value);parts[i]=value
        lines.append(''.join(parts))
    result=('\ufeff' if bom else '')+''.join(lines)
    return result.encode('utf-8'),edits

def role(name):
    if any(x in name for x in ('publication','archive')):return '공개·보존'
    if any(x in name for x in ('protocol','plan','design')):return '설계·명세'
    if any(x in name for x in ('analysis','results','review','report','grounding')):return '분석·해석'
    if any(x in name for x in ('audit','validation','verification')):return '검증·감사'
    if 'register' in name:return '근거 원장'
    return '실행·구현'

def prepare(base_ref='origin/main'):
    out=unique('prepare');snapshot(out)
    try:
        base=git('rev-parse',base_ref).decode().strip();entries=tree(base);layout=read(HERE/'layout.json')
        roots=sorted({p.split('/')[0] for p in entries if re.match(r'^\d{2}_',p)})
        bynum={int(r[:2]):r for r in roots}
        assigned=[n for g in layout['groups'] for n in g['numbers']]
        if len(assigned)!=len(set(assigned)) or set(assigned)!=set(bynum):raise RuntimeError('Published versions must map exactly once')
        mapping={bynum[n]:g['directory']+'/'+bynum[n] for g in layout['groups'] for n in g['numbers']}
        valid=set(entries)|directories(entries);contents=blobs(e['oid'] for p,e in entries.items() if p.endswith('.md') or p in ('.gitattributes','.gitignore'))
        local_before=local_state();changed={};archives={};file_rows=[];doc_changes=[]
        audit={'originally_valid':0,'valid_unchanged':0,'corrected_targets':0,'preexisting_missing':0,'missing_examples':[]}
        def changed_file(old,new_path,data,reason):
            original=contents[entries[old]['oid']]
            if data==original:return None
            # Keep staging paths short even for deeply nested historical reports.
            dest=out/'modified'/(sha(new_path.encode())+'.bin');dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
            changed[new_path]=str(dest)
            archive=f'{TOOL}/results/{out.name}/original_files/{entries[old]["oid"]}.bin'
            archives[archive]={'mode':entries[old]['mode'],'oid':entries[old]['oid']}
            return archive
        for path,entry in entries.items():
            new=map_path(path,mapping);archive=None
            if path.endswith('.md') and path not in ('README.md','AGENTS.md','LOCAL_PRACTICE_ALLOCATION_PILOT_DESIGN_20261007.md'):
                updated,edits=rewrite_markdown(contents[entry['oid']],path,new,mapping,valid,audit)
                archive=changed_file(path,new,updated,'Markdown link paths only')
                if archive:doc_changes.append({'old_path':path,'new_path':new,'old_oid':entry['oid'],'new_oid':oid(updated),
                    'old_sha256':sha(contents[entry['oid']]),'new_sha256':sha(updated),'original_archive':archive,'edits':edits})
            file_rows.append({'old_path':path,'new_path':new,'mode':entry['mode'],'old_oid':entry['oid'],**({'original_archive':archive} if archive else {})})
        root_readme=contents[entries['README.md']['oid']].decode('utf-8')
        marker=re.search(r'<!-- retention-video-publication:start -->[\s\S]*?<!-- retention-video-publication:end -->',root_readme)
        if not marker:raise RuntimeError('Published C/D video block missing')
        video,_=rewrite_markdown(marker.group(0).encode(),'README.md','README.md',mapping,valid,audit)
        new_files={}
        def generated(logical,text):
            p=out/'generated'/logical;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8',newline='\n');new_files[logical]=str(p)
        for group in layout['groups']:
            lines=['# '+group['title'],'',group['question'],'',group['note'],'',
                '[전체 연구 지도](../README.md) · [질문이 바뀐 과정](../00_research_overview/RESEARCH_TRAJECTORY.md)','',
                '| 번호 | 기록 | 역할 |','|---:|---|---|']
            for n in group['numbers']:
                name=bynum[n];lines.append(f'| {n:02d} | [{name}]({name}/) | {role(name)} |')
            if group['directory']=='07_operations_and_publication':lines.append(f'| 74 | [{HERE.name}]({HERE.name}/) | 이번 폴더 정리·경로 대응·원문 복원 도구 |')
            lines+=['','번호는 생성 순서이며 과학적 확증 수준을 뜻하지 않는다. 설계·실행·분석·검산·공개 기록을 구분해서 읽는다.',
                '이동으로 바뀌는 문서 링크만 보정했고 학습 코드·수치 원자료·JSON 출처는 수정하지 않았다.',
                f'정리 전 문서는 [고정 커밋 {base[:7]}](https://github.com/rlatmddn0211/practice_allocation/tree/{base})와 '
                '[경로/원문 복원 기록](../07_operations_and_publication/74_repository_research_structure_v1/README.md)을 따른다.','']
            generated(group['directory']+'/README.md','\n'.join(lines))
        trajectory=['# 연구 질문을 구체화한 과정','',
            '기록을 주제별로 묶되, 이전 실험의 음성·불확실한 결과를 새 질문의 성공으로 바꾸지 않는다.', '',
            '| 순서 | 당시 질문 | 수행한 접근 | 다음 질문으로 이어진 이유 |', '|---:|---|---|---|',
            '| 1 | 어느 과제에 연습을 더 주면 좋은가? | 최초 배분 비교와 후속 반복 | 한 출발점의 큰 차이를 독립 부모에 일반화할 수 있는지 확인할 필요 |',
            '| 2 | 배분 효과가 재현되고 특별한 전이가 있는가? | 새 부모·donor 대조·과제 구성 확장 | 효과가 출발 조건과 과제에 민감해 강한 고정 기준과 진단 필요 |',
            '| 3 | 무엇을 보면 좋은 배분을 고를 수 있는가? | critic·gradient/update·가소성·실제 노출·수집 강도/순서 | 측정한 신호가 안정적인 추가 선택 가치로 이어지는지 별도 확인 |',
            '| 4 | 부모별 일정 선택이 강한 고정보다 좋은가? | 다섯 새 부모·30분기의 1단계 | 다른 후속 반복으로 이전 가능한 선택 이득의 투자 기준 미통과 |',
            '| 5 | 추가 학습을 계속할 가치가 있는가? | 같은 사례의 획득·상실,8k 평가,같은 상태의 미래 반복 | 후기 상실과 회복이 공존하며 결과 차이와 사전 선택 가능성이 다름 |',
            '| 6 | 어떤 사례를 획득하는지가 상태와 연결되는가? | 동일/교차 상태 중첩,설명 비교,새 F3/F4 | 관측된 사례 구조와 새 미래의 확인을 분리해 연구 질문을 좁힘 |',
            '| 7 | 무엇을 보호해야 획득·회복과 보존을 함께 개선할 수 있는가? | 기준선,기본/LR감소/일반보호/성공우선보호,양방향 영상 | 보호 대상 선택의 신호는 있으나 과제·부모별 차이와 기능적 설명은 별도 확인 대상 |','',
            '각 단계의 대표 원문과 설계·실행·분석 범위는 해당 그룹 목차를 따른다. 이번 재분류는 이미 게시된66개 버전만 대상으로 하며, 미게시 로컬 연구 기록을 자동 공개하지 않는다.', '',
            f'[정리 전 최상위 README 원문](https://github.com/rlatmddn0211/practice_allocation/blob/{base}/README.md)','']
        generated('00_research_overview/RESEARCH_TRAJECTORY.md','\n'.join(trajectory))
        main=['# Robot practice allocation','',
            '추가 학습에서 무엇을 어떻게 보호해야 기존 성공의 상실을 줄이면서, 다른 사례의 성공 획득과 이전 성공의 회복을 유지할 수 있는지 연구합니다.','',
            '## 연구 질문별로 보기','',
            '기존 실험 번호와 버전명은 그대로 유지하고 관련 질문을8개 큰 폴더로 묶었습니다. '
            '[연구 질문의 변화 과정](00_research_overview/RESEARCH_TRAJECTORY.md)을 먼저 보면 각 묶음이 이어진 이유를 볼 수 있습니다.','',
            '| 큰 폴더 | 핵심 질문 | 기존 버전 수 |','|---|---|---:|']
        for g in layout['groups']:main.append(f'| [{g["title"]}]({g["directory"]}/) | {g["question"]} | {len(g["numbers"])} |')
        main+=['','실행·공개 폴더에는 이번 정리 도구74를 추가했습니다. 번호 순서는 실험의 성패나 확증 수준을 뜻하지 않습니다.','',
            '## 먼저 볼 자료','',
            '- [현재 보존 개입 결과](06_retention_interventions/68_retention_intervention_result_review_v1/results/20261028T072607Z_review_323af171/report_ko.md)',
            '- [보존 개입·사례 영상 목차](06_retention_interventions/README.md)',
            '- [연구 개요와 문헌](00_research_overview/README.md)',
            '- [루트 파일럿 설계 원문](LOCAL_PRACTICE_ALLOCATION_PILOT_DESIGN_20261007.md)','',
            video.decode('utf-8'),'',
            '## 기록 보존과 실행 경로','',
            '학습 코드·원자료·JSON의 원래 출처 경로는 그대로입니다. 문서 링크만 게시용 경로로 보정했고 수정 전 원문을 함께 보관했습니다. '
            '이동된 폴더에서 기존 실행 코드를 그대로 다시 학습시키기 전에 [원래 구조 복원 도구와 주의사항](07_operations_and_publication/74_repository_research_structure_v1/README.md)을 확인하세요. '
            '이번 정리는 새 학습이나 평가가 아닙니다.','']
        data='\n'.join(main).encode();archive=changed_file('README.md','README.md',data,'root navigation rewritten; original preserved')
        next(r for r in file_rows if r['old_path']=='README.md')['original_archive']=archive
        # Root pilot stays byte-identical. Root metadata receives path/rules updates only.
        for name in ('.gitattributes','.gitignore'):
            raw=contents[entries[name]['oid']];text=raw.decode('utf-8')
            for old,new in sorted(mapping.items(),key=lambda x:-len(x[0])):text=text.replace(old+'/',new+'/')
            if name=='.gitattributes':text+='\n# Organization records preserve bytes.\n'+TOOL+'/** -text whitespace=cr-at-eol\n'
            archive=changed_file(name,name,text.encode(),'root path patterns updated')
            if archive:next(r for r in file_rows if r['old_path']==name)['original_archive']=archive
        agents=contents[entries['AGENTS.md']['oid']]
        note=('\n\n# Published repository layout (2026-10-29)\n\n'
            'The user requested organization by research question. Numbered versions now live under eight topic groups. '
            'Historical version names in rules are identifiers; consult74 path_manifest.json for their current paths. '
            'Training/evaluation code and data blobs are preserved. Markdown link adjustments are publication derivatives; '
            'their original blobs are retained in74 original_files and the fixed pre-organization commit. '
            'Use restore_legacy_layout.py into a new empty directory before running source that expects flat sibling paths. '
            'Do not rewrite absolute provenance paths or silently change numerical protocols. '
            'Local original runtime checkouts may intentionally retain the flat tree; do not pull the reorganized tree '
            'over checkpoint/venv assets. Future publishing must start from the current remote main, not such a legacy HEAD.\n')
        archive=changed_file('AGENTS.md','AGENTS.md',agents+note.encode(),'publication navigation/execution rules appended')
        next(r for r in file_rows if r['old_path']=='AGENTS.md')['original_archive']=archive
        # Every original file, including edited documentation, has an exact-byte recovery route.
        save(out/'path_manifest.json',{'base_commit':base,'original_files':len(file_rows),'original_version_folders':len(roots),
            'groups':layout['groups'],'folder_mapping':mapping,'files':file_rows,'scope':'published tracked files only'})
        save(out/'document_link_changes.json',{'changes':doc_changes,'audit':audit,'originals_stored_as_git_blobs':True,
            'edited_documents_are_publication_derivatives':True})
        with (out/'folder_mapping.csv').open('x',encoding='utf-8',newline='') as f:
            w=csv.writer(f);w.writerow(['old_folder','new_folder']);w.writerows(sorted(mapping.items()))
        save(out/'local_state_before.json',local_before)
        original_entries={r['new_path']:{'mode':r['mode'],'oid':r['old_oid']} for r in file_rows}
        original_entries.update(archives)
        if len({r['new_path'] for r in file_rows})!=len(file_rows):raise RuntimeError('Destination path collision')
        summary={'status':'prepared','base_commit':base,'published_original_files':len(file_rows),'version_folders':len(roots),
            'groups':8,'link_edited_documents':len(doc_changes),'link_audit':audit,'original_archives':len(archives),
            'new_environment_steps':0,'local_runtime_files_moved':0,'scope':'published files reorganized; unpublished61/62/63/65/69/71/72 excluded'}
        save(out/'summary.json',summary)
        save(out/'COMPLETE.json',{'summary_sha256':sha((out/'summary.json').read_bytes())})
        # Explicit allowlist; never include a temporary bare object store or runtime assets.
        for p in HERE.iterdir():
            if p.is_file() and (p.suffix in ('.py','.md','.json') or p.name=='.gitignore'):new_files[TOOL+'/'+p.name]=str(out/'source_snapshot'/p.name)
        for p in out.iterdir():
            if p.is_file():new_files[TOOL+'/results/'+out.name+'/'+p.name]=str(p)
        for p in (out/'source_snapshot').iterdir():new_files[TOOL+'/results/'+out.name+'/source_snapshot/'+p.name]=str(p)
        save(out/'tree_plan.json',{'base_commit':base,'entries':original_entries,'modified_files':changed,'new_files':new_files,
            'content_sha256':{logical:sha(Path(physical).read_bytes()) for logical,physical in {**changed,**new_files}.items()},
            'local_state_before':local_before,'path_manifest':str(out/'path_manifest.json')})
        print(json.dumps({'preparation_dir':str(out),'folders':len(roots),'files':len(file_rows),'edited_markdown':len(doc_changes),'links_corrected':audit['corrected_targets']}))
        return out
    except BaseException:
        save(out/'FAILED.json',{'traceback':traceback.format_exc(),'new_environment_steps':0});raise

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--base',default='origin/main');args=parser.parse_args()
    prepare(args.base)
