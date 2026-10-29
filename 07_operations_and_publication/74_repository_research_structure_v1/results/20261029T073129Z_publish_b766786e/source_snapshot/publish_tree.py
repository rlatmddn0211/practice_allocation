"""Build and fast-forward the publication tree without touching the runtime index."""
import argparse,hashlib,json,os,subprocess,sys,traceback
from pathlib import Path
import prepare

HERE=Path(__file__).resolve().parent
REMOTE='https://github.com/rlatmddn0211/practice_allocation.git'

def run(bare,*args,input=None,env=None):
    isolated=(env or os.environ).copy()
    for name in ('GIT_INDEX_FILE','GIT_DIR','GIT_WORK_TREE','GIT_OBJECT_DIRECTORY','GIT_ALTERNATE_OBJECT_DIRECTORIES'):
        isolated.pop(name,None)
    return subprocess.check_output(['git','--git-dir',str(bare),*args],input=input,env=isolated)

def ingest(bare,files,entries):
    for logical,physical in files.items():
        data=Path(physical).read_bytes()
        key=run(bare,'hash-object','-w','--stdin',input=data).decode().strip()
        if key!=prepare.oid(data):raise RuntimeError('Ingest hash mismatch')
        entries[logical]={'mode':'100644','oid':key}

def write_tree(bare,entries):
    run(bare,'read-tree','--empty')
    index=b''.join((f'{v["mode"]} blob {v["oid"]}\t{k}\0').encode('utf-8') for k,v in sorted(entries.items()))
    run(bare,'update-index','-z','--index-info',input=index)
    return run(bare,'write-tree').decode().strip()

def build(preparation):
    preparation=Path(preparation).resolve();plan=prepare.read(preparation/'tree_plan.json')
    out=prepare.unique('build');prepare.snapshot(out)
    try:
        if prepare.local_state()!=plan['local_state_before']:raise RuntimeError('Runtime worktree/index changed since preparation')
        for logical,physical in {**plan['modified_files'],**plan['new_files']}.items():
            if prepare.sha(Path(physical).read_bytes())!=plan['content_sha256'][logical]:raise RuntimeError('Prepared content changed: '+logical)
        for name,key in prepare.read(preparation/'source_hashes.json').items():
            if prepare.sha((HERE/name).read_bytes())!=key:raise RuntimeError('Tool source changed after preparation: '+name)
        bare=out/'object_store.git'
        subprocess.check_output(['git','init','--bare',str(bare)],stderr=subprocess.STDOUT)
        objects=Path(prepare.git('rev-parse','--path-format=absolute','--git-common-dir').decode().strip())/'objects'
        (bare/'objects'/'info'/'alternates').write_text(objects.as_posix()+'\n',encoding='utf-8',newline='\n')
        run(bare,'config','core.longpaths','true')
        entries=dict(plan['entries'])
        ingest(bare,plan['modified_files'],entries);ingest(bare,plan['new_files'],entries)
        tree=write_tree(bare,entries)
        prepare.save(out/'build_receipt.json',{'status':'built','preparation':str(preparation),'bare':str(bare),
            'base_commit':plan['base_commit'],'tree':tree,'files':len(entries),'new_environment_steps':0,
            'root_head_and_index_preserved':prepare.local_state()==plan['local_state_before']})
        prepare.save(out/'final_entries.json',entries)
        print(json.dumps({'build_dir':str(out),'bare':str(bare),'tree':tree,'files':len(entries)}))
        return out
    except BaseException:
        prepare.save(out/'FAILED.json',{'traceback':traceback.format_exc()});raise

def finalize(build_dir,verification_dir):
    build_dir=Path(build_dir).resolve();verification_dir=Path(verification_dir).resolve()
    receipt=prepare.read(build_dir/'build_receipt.json');bare=Path(receipt['bare']);preparation=Path(receipt['preparation'])
    verification=prepare.read(verification_dir/'verification.json')
    if not verification.get('passed'):raise RuntimeError('Independent verification did not pass')
    if verification.get('tree')!=receipt['tree']:raise RuntimeError('Verification belongs to a different tree')
    plan=prepare.read(preparation/'tree_plan.json')
    if prepare.local_state()!=plan['local_state_before']:raise RuntimeError('Local runtime files changed before finalization')
    for name,key in prepare.read(preparation/'source_hashes.json').items():
        if prepare.sha((HERE/name).read_bytes())!=key:raise RuntimeError('Tool source changed before finalization: '+name)
    out=prepare.unique('publish');prepare.snapshot(out)
    try:
        # Verification/report files are added after verification. Existing verified tree
        # entries must remain unchanged; no research code, inputs, or links change here.
        entries=prepare.read(build_dir/'final_entries.json');verified=dict(entries)
        additions={}
        for p in verification_dir.iterdir():
            if p.is_file() and p.suffix in ('.json','.csv','.md','.txt'):
                additions[prepare.TOOL+'/results/'+verification_dir.name+'/'+p.name]=str(p)
        for p in (verification_dir/'source_snapshot').iterdir():
            if p.is_file() and (p.suffix in ('.py','.json','.md') or p.name=='.gitignore'):
                additions[prepare.TOOL+'/results/'+verification_dir.name+'/source_snapshot/'+p.name]=str(p)
        for name in ('tree_plan.json','path_manifest.json','document_link_changes.json','local_state_before.json','summary.json','COMPLETE.json'):
            p=verification_dir/'input_snapshot'/name
            if p.is_file():additions[prepare.TOOL+'/results/'+verification_dir.name+'/input_snapshot/'+name]=str(p)
        summary=prepare.read(preparation/'summary.json')
        report='\n'.join([
            '# GitHub 연구 폴더 정리 결과','',
            '기존 게시된 번호 폴더66개를 연구 질문별 큰 폴더8개로 정리했다. 번호와 버전명은 하위 폴더에서 유지한다.',
            '새 학습·환경 평가는0이며 로컬 체크포인트·replay·venv·미게시 실험을 옮기거나 추가 공개하지 않았다.','',
            '| 큰 폴더 | 기존 버전 수 |','|---|---:|',
            *[f'| {g["title"]} (`{g["directory"]}`) | {len(g["numbers"])} |' for g in prepare.read(preparation/'path_manifest.json')['groups']],
            '',f'원래 게시 파일{summary["published_original_files"]:,}개를 전부 경로 대응표에 기록했다. '
            f'문서의 이동 관련 링크{summary["link_audit"]["corrected_targets"]}곳을 보정했다. '
            '학습 코드·원자료·JSON·미디어의 blob은 유지하고, 수정 전 문서도 원문 blob으로 보존한다.',
            '루트 README에는 연구 질문별 지도와 기존 C/D 설명·비교 영상8개를 유지했다. 각 큰 폴더에는 해당 기록 목록을 추가했다.','',
            '기존부터 없던 문서 링크는 document_link_changes.json에 별도 표시한다. 이번 정리로 해결했다고 주장하지 않는다.',
            '동결된 대화형 보고서의 JSON 안에 남아 있는 과거main 출처 링크는 보존했다. 도구README에서 해당 여섯 대상의 새 게시 경로를 안내한다.',
            '검증은 파일·경로·Git blob·문서 링크에 대한 것이다. 학습 또는 환경 실행 재현 검증은 하지 않았다.','',
            f'기준 커밋: `{receipt["base_commit"]}`',
            f'검증 대상 tree: `{receipt["tree"]}`',
            f'검증 기록: `results/{verification_dir.name}/verification.json`',
            f'경로 대응표: `results/{preparation.name}/path_manifest.json`','',
            '로컬의 원래 checkout은 실행 자산의 절대 경로를 위해 평면 구조로 유지한다. 원격 게시 구조와 의도적으로 다르므로 '
            '이 checkout에서 일반 pull/merge로 덮어쓰지 않는다. 다음 게시 작업은 최신 원격main을 기준으로 해야 한다.',
            '정리된 clone에서 기존 평면 구조가 필요하면 restore_legacy_layout.py를 새 빈 경로에 실행한다. '
            '이 도구는 공개 파일과 원문만 복원하며 미게시 런타임·가상환경·환경 재현까지 보장하지 않는다.',''])
        (out/'report_ko.md').write_text(report,encoding='utf-8',newline='\n')
        additions[prepare.TOOL+'/results/'+out.name+'/report_ko.md']=str(out/'report_ko.md')
        for p in (out/'source_snapshot').iterdir():additions[prepare.TOOL+'/results/'+out.name+'/source_snapshot/'+p.name]=str(p)
        additions[prepare.TOOL+'/results/'+out.name+'/source_hashes.json']=str(out/'source_hashes.json')
        if set(additions)&set(entries):raise RuntimeError('Verification/report path collision')
        ingest(bare,additions,entries)
        if any(entries[k]!=v for k,v in verified.items()):raise RuntimeError('Verified entry was modified')
        final_tree=write_tree(bare,entries)
        env=os.environ.copy()
        for key,config in [('NAME','user.name'),('EMAIL','user.email')]:
            value=prepare.git('config','--get',config).decode().strip()
            env['GIT_AUTHOR_'+key]=value;env['GIT_COMMITTER_'+key]=value
        commit=run(bare,'commit-tree',final_tree,'-p',receipt['base_commit'],'-m',
            'Organize published research records by question and preserve original paths',env=env).decode().strip()
        result={'status':'ready_to_push','base_commit':receipt['base_commit'],'verified_tree':receipt['tree'],
            'final_tree':final_tree,'commit':commit,'bare':str(bare),'verification_dir':str(verification_dir),
            'preparation':str(preparation),'verified_entries_unchanged':True,'additional_record_files':len(additions),
            'root_head_and_index_preserved':True,'new_environment_steps':0,'remote':REMOTE}
        prepare.save(out/'publication_commit.json',result)
        print(json.dumps({'publication_dir':str(out),'commit':commit,'final_tree':final_tree}))
        return out
    except BaseException:
        prepare.save(out/'FAILED.json',{'traceback':traceback.format_exc()});raise

def push(publication):
    publication=Path(publication).resolve();receipt=prepare.read(publication/'publication_commit.json')
    plan=prepare.read(Path(receipt['preparation'])/'tree_plan.json')
    if prepare.local_state()!=plan['local_state_before']:raise RuntimeError('Local runtime changed before push')
    remote_head=prepare.git('ls-remote',REMOTE,'refs/heads/main').decode().split()[0]
    if remote_head!=receipt['base_commit']:raise RuntimeError('Remote advanced; rebuild from latest main, never force')
    run(Path(receipt['bare']),'push',REMOTE,receipt['commit']+':refs/heads/main')
    actual=prepare.git('ls-remote',REMOTE,'refs/heads/main').decode().split()[0]
    if actual!=receipt['commit']:raise RuntimeError('Remote verification failed')
    prepare.save(publication/'PUSH_COMPLETE.json',{'commit':actual,'remote':REMOTE,'fast_forward':True,
        'local_state_preserved':prepare.local_state()==plan['local_state_before'],'new_environment_steps':0})
    print(json.dumps({'status':'pushed','commit':actual,'remote_verified':True}))

if __name__=='__main__':
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    b=sub.add_parser('build');b.add_argument('--preparation',required=True)
    f=sub.add_parser('finalize');f.add_argument('--build',required=True);f.add_argument('--verification',required=True)
    u=sub.add_parser('push');u.add_argument('--publication',required=True)
    a=p.parse_args()
    if a.command=='build':build(a.preparation)
    elif a.command=='finalize':finalize(a.build,a.verification)
    else:push(a.publication)
