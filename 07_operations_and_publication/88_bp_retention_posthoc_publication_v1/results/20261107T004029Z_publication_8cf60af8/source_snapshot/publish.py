"""Publish completed87 on current remote main without touching the runtime checkout."""
from __future__ import annotations
import argparse,re,shutil,time,traceback,uuid
from common import *
from verify_public import verify


def prepare(base):
    if not re.fullmatch('[0-9a-f]{40}',base):raise ValueError('Exact current remote main hash required')
    out=HERE/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_publication_'+uuid.uuid4().hex[:8])
    out.mkdir(parents=True,exist_ok=False);started=time.perf_counter()
    try:
        before=runtime_state();save(out/'runtime_before.json',before)
        snapshot=out/'source_snapshot';snapshot.mkdir()
        for p in HERE.iterdir():
            if p.is_file() and p.suffix in {'.py','.md'}:shutil.copy2(p,snapshot/p.name)
        hashes={p.name:sha(p) for p in snapshot.iterdir()};save(out/'source_hashes.json',hashes)
        latest=read(ROOT/VERSION/'LATEST.json');delivery=Path(latest['output']);core=Path(latest['core_analysis'])
        status=read(delivery/'FINAL_STATUS.json');receipt=read(delivery/'reproduction_receipt.json')
        if latest['status']!='complete' or status['status']!='complete':raise RuntimeError('Only completed87 is eligible')
        if sha(delivery/'reproduction_bundle.zip')!=receipt['sha256']:raise RuntimeError('87 bundle differs')
        for line in (delivery/'artifact_manifest.jsonl').read_text(encoding='utf-8').splitlines():
            r=json.loads(line)
            if sha(delivery/r['path'])!=r['sha256']:raise RuntimeError('Immutable87 artifact differs '+r['path'])
        if read(Path(status['verification'])/'FINAL_STATUS.json')['status']!='passed':raise RuntimeError('Independent87 verification missing')
        if read(Path(status['file_delivery_review'])/'FINAL_STATUS.json')['status']!='passed':raise RuntimeError('87 delivery audit missing')
        bare=out/'object_store.git';command(['git','init','--bare',str(bare)])
        (bare/'objects/info/alternates').write_text((OLD_STORE/'objects').as_posix()+'\n',encoding='utf-8',newline='\n')
        git(bare,'cat-file','-e',base+'^{commit}');old=entries(bare,base)
        stage_plain=(out/'stage').resolve();stage=Path('\\\\?\\'+str(stage_plain)) if os.name=='nt' else stage_plain;stage.mkdir()
        copied={}
        def add(p,role):
            p=Path(p)
            if not p.is_file() or any(x in p.parts for x in ['__pycache__','.mplconfig']):return
            target=PUBLIC+'/'+p.relative_to(ROOT/VERSION).as_posix()
            if target in old:raise RuntimeError('87 already published: '+target)
            if target in copied:return
            dst=stage/target;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst)
            digest=sha(p)
            if sha(dst)!=digest:raise RuntimeError('Copy differs '+target)
            copied[target]=dict(source=str(p),public_path=target,bytes=p.stat().st_size,sha256=digest,role=role)
        def folder(p,role):
            for f in Path(p).rglob('*'):add(f,role)
        for p in (ROOT/VERSION).iterdir():
            if p.is_file() and p.suffix in {'.py','.json','.md'}:add(p,'frozen87 source, specification or status pointer')
        folder(delivery,'immutable adopted87 report/tables/9figures/bundle/provenance/verification')
        folder(core,'adopted87 core extraction and independent verification; Git deduplicates identical tables')
        # Keep earlier attempts identifiable without publishing duplicate presentation output.
        for parent in [ROOT/VERSION/'results',ROOT/VERSION/'delivery']:
            for attempt in parent.iterdir():
                if attempt.is_file() and attempt.name.startswith('visual_review_'):add(attempt,'actual visual-content review receipt')
                elif attempt.is_dir() and attempt not in {core,delivery}:
                    for name in ['FAILED.json','FINAL_STATUS.json','analysis_costs.json','source_hashes.json']:
                        if (attempt/name).is_file():add(attempt/name,'preserved earlier file-only attempt receipt')
                    if (attempt/'source_snapshot').is_dir():folder(attempt/'source_snapshot','actual source of preserved earlier attempt')
        public_record=PUBLIC_TOOL+'/results/'+out.name
        def document(path,text):
            p=stage/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8',newline='\n')
        def record(name,value):save(out/name,value);save(stage/public_record/name,value)
        for p in snapshot.iterdir():
            target=stage/PUBLIC_TOOL/p.name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
            target=stage/public_record/'source_snapshot'/p.name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
        document(PUBLIC+'/PUBLICATION_FILE_MAP.jsonl',''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in copied.values()))
        old_source_map={r['original_path']:r['public_path'] for r in map(json.loads,git(bare,'show',base+':'+V85+'/SOURCE_EPISODE_MAP.jsonl').decode('utf-8').splitlines())}
        availability=[]
        for line in (core/'input_manifest.jsonl').read_text(encoding='utf-8').splitlines():
            r=json.loads(line);p=Path(r['path']);public=None
            if r['path'] in old_source_map:public=old_source_map[r['path']]
            elif p.is_relative_to(ROOT):
                rel=p.relative_to(ROOT).as_posix()
                if rel.startswith('85_onset_reuse_pilot_v1/'):public='09_experience_reuse_pilots/'+rel
                elif rel.startswith('81_basic_sac_observation_campaign_v1/'):public='08_basic_learning_observations/'+rel
                elif rel.startswith(VERSION+'/'):public='09_experience_reuse_pilots/'+rel
            if public not in old and public not in copied:public=None
            availability.append(dict(**r,public_path=public,availability='published_existing_or_new' if public else 'local_only_hash_reference'))
        document(PUBLIC+'/PUBLIC_INPUT_AVAILABILITY.jsonl',''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in availability))
        bp=[r for r in availability if 'BP actual numeric trajectory' in r['roles']]
        public_bp=sum(r['public_path'] is not None for r in bp)
        record('path_manifest_extension.json',dict(base_commit=base,prior_publication86=str(OLD_STORE.parent),
            historical_paths_unchanged=True,additions={VERSION:PUBLIC,TOOL:PUBLIC_TOOL}))
        rel=delivery.relative_to(ROOT/VERSION).as_posix();report=PUBLIC+'/'+rel+'/report_ko.md';bundle=PUBLIC+'/'+rel+'/reproduction_bundle.zip'
        document(PUBLIC+'/PUBLICATION_README_ko.md',f'''# 87번 사후분석 — GitHub 공개 안내

[원문 한국어 보고서]({rel}/report_ko.md) · [그림 9개와 표]({rel}/) · [재현 ZIP]({rel}/reproduction_bundle.zip) · [BP 부모·미래별 표]({rel}/tables/bp_ten_matched_runs_summary.csv)

87은 [85번 파일럿](../85_onset_reuse_pilot_v1/PUBLICATION_README_ko.md)의 **같은 기록에 대한 사후분석**이다. 독립 실험을 추가하지 않았다. 2026-11-07 사용자의 게시 지시에 따라88에서 공개했다. 원 보고서·README·FINAL_STATUS의 ‘이번 분석에서는 게시하지 않았다’는 문장은2026-11-06 분석 완료 당시 기록이며, 그 원문과 hash를 보존했다. 현재 게시 상태는 이 안내와88 게시 영수증을 따른다.

| BP 지표 | ONSET−RANDOM_PRE | ONSET−BASE |
| --- | ---: | ---: |
| 정규화 AUC 차이 | +7.578%p | +12.031%p |
| 양수 부모 | 3/5 | 4/5 |
| 양수 부모×미래 | 6/10 | 9/10 |
| 최종 성공 순차 | +11/160 | +40/160 |

P-U AUC는 각 부모 안 두 미래에서 방향이 같지만 R03/R04에서는 둘 다 불리했다. R05를 빼도 P-U+2.930%p,P-B+6.152%p다. P-U 최종+11은 초기 성공 유지+8과 초기 실패 최종 성공+3이다. P의 초기 실패12이력은11개가16k,1개가32k에 처음 성공했다. P/U 실제 사용은 각10,227,844회로 episode-offset별로도 정확히 같지만 내용은 달랐다.

자료 특성의 서열은 약한 사후 후보이고, 부모 상태와 중첩 LOO 자료 구성을 분리하지 못했다. 기존16개 개발 물리 사례,독립 부모5개,부모 안 미래2개다. 새로운 보존 방법·공유 기초동작·인과적 자료 기여를 입증한 결과가 아니다. 원85 DO 주지표의 보류 판단과 불리한 Push 결과를 유지한다.

## 공개 범위와 원본 보존

- 원 보고서·그림9개(PNG/SVG)·표·설정·분석/독립검산 코드·source snapshot·비용·근거 기록·원 재현 ZIP을 byte 그대로 공개했다.
- BP160개 대응 이력×3arm,1,520에피소드의 파생 물리 지표,고정DO25에피소드/50창,실제사용과90개 시간 일치 연결행을 공개했다.
- 원87 경로↔공개 경로와SHA256: [PUBLICATION_FILE_MAP.jsonl](PUBLICATION_FILE_MAP.jsonl). 원 입력의 공개 여부: [PUBLIC_INPUT_AVAILABILITY.jsonl](PUBLIC_INPUT_AVAILABILITY.jsonl).
- 대형 raw/model/replay를 새로 복제하지 않았다. BP 원시1,520개 중 기존 공개 경로가 확인된 것은 {public_bp}개다. 전체 BP raw에 대한 검산은 로컬87에서 수행했으며,공개된 파생표가 전체 raw의 다운로드 가능성을 뜻하지 않는다. 원DO25개는 기존85의31개 source subset에 포함되어 다시 올리지 않았다.
- Windows 절대 경로는 당시 출처다. 공개 자료만으로 원 SAC 학습 재개나 로컬87 전체 raw 분석을 그대로 실행할 수 있다고 주장하지 않는다.

## 공개 파일만으로 가능한 검산

저장소 전체를 확보한 뒤 Python과NumPy/pandas/Parquet 엔진으로 다음을 실행한다.

```text
python {PUBLIC_TOOL}/verify_public.py --repository .
```

원85 공개 라벨에서480개 BP이력·30개대비·사건을 다시 계산하고,이미 공개한25개DO원수치에서창·개방/닫힘을 검산한다. 원85의실제사용count에서각시점노출량과가중내용·90개시간연결을 확인하고원ZIP해시를대조한다. 새 환경 생성/reset/step/복원,모델 로드/forward,학습 및 새bootstrap draw는0이다. 전체 BP raw1520개를 공개 검산했다고 표현하지 않는다.

원래 로컬 재분석 방법과 자산 요구는 [{rel}/REPRODUCE.md]({rel}/REPRODUCE.md)에 보존했다. 이번 게시의 Git 트리는 현재 원격main 위에 추가하며 기존runtime checkout의HEAD/index와원본실험은유지한다.
''')
        root_text=git(bare,'show',base+':README.md').decode('utf-8');anchor='## 연구 질문별로 보기'
        if anchor not in root_text:raise RuntimeError('Remote navigation anchor differs')
        intro=f'''## 2026-11-07 게시: BP 보존과 DO 경험 내용의 사후분석

[87번 보고서·표·그림9개·재현 자료]({PUBLIC}/PUBLICATION_README_ko.md): 같은85 기록에서 BP160개 대응 이력과 실제 경험 사용을 분해했다. BP AUC의 ONSET−RANDOM_PRE는+7.578%p이며 부모3/5개에서 양수,2개에서 음수였다. 실제자료사용량은두재사용조건에서같았지만내용은달랐다. 출발학습기와자료구성의얽힘은남으며,독립확인이나공유기초동작발견으로해석하지않는다. 원85의DO보류판정은유지한다.

'''
        root_text=root_text.replace(anchor,intro+anchor,1)
        for group in ['09_experience_reuse_pilots','07_operations_and_publication']:
            previous={p.split('/')[1] for p in old if p.startswith(group+'/') and len(p.split('/'))>=3}
            pattern=r'(?m)^(\|[^\n]*\]\('+re.escape(group)+r'/\)[^\n]*\|)\s*\d+\s*\|$'
            root_text,n=re.subn(pattern,lambda m:m.group(1)+' '+str(len(previous)+1)+' |',root_text)
            if n!=1:raise RuntimeError('Topic row differs '+group)
        document('README.md',root_text)
        group='09_experience_reuse_pilots/README.md';text=git(bare,'show',base+':'+group).decode('utf-8')
        document(group,text+f'\n## 85번의 같은 기록에 대한87번 사후분석\n\n- [87 공개 범위·핵심 결과]({VERSION}/PUBLICATION_README_ko.md)\n- [한국어 보고서]({VERSION}/{rel}/report_ko.md)\n- [재현 ZIP]({VERSION}/{rel}/reproduction_bundle.zip)\n\nBP 반복성·유지/회복·DO선택내용·실제사용을연결했다. 독립실험추가가아니며P-U AUC는부모3개양수/2개음수다. 원85 DO진행기준미통과를유지한다.\n\n![BP 부모·미래 반복 범위]({VERSION}/{rel}/figures/01_BP_repetition.png)\n')
        ops='07_operations_and_publication/README.md';document(ops,git(bare,'show',base+':'+ops).decode('utf-8')+f'\n## 2026-11-07 추가 게시\n\n- [88 — BP 보존 사후분석87 결과 게시]({TOOL}/README.md)\n')
        agents=git(bare,'show',base+':AGENTS.md').decode('utf-8')
        document('AGENTS.md',agents+'\n- On2026-11-07 the user authorized publication of completed87 only. Independent88 publishes its original report/tables/9figures/code/receipts/ZIP under09_experience_reuse_pilots, preserving exact bytes and all historical non-navigation blobs.87 is posthoc analysis of the same85 data, not independent confirmation. BP P-U AUC+7.578pp has3 positive/2 adverse parent means;P-B+12.031pp. ActualP/U usage matches but content differs;learner/LOO confounding remains. Preserve85 DO progression hold and task tradeoffs. Large raw/model assets remain local or already published as explicitly mapped;do not claim all BP raw downloadable. Publication88 uses isolated Git objects and preserves runtime HEAD/index. No new environment/model/learning/bootstrap execution or followup experiment is authorized.\n')
        verification=verify(stage,delivery.name,bare,base);record('public_verification.json',verification)
        record('source_hashes.json',hashes);record('runtime_before.json',before)
        record('selection_summary.json',dict(files=len(copied),bytes=sum(r['bytes'] for r in copied.values()),
            original_BP_raw_episodes=1520,previously_public_BP_raw_episodes=public_bp,new_raw_model_payloads=0,
            all_other_local_experiments_excluded=True,report_original_bytes_preserved=True,new_execution=ZERO))
        allowed={'README.md','AGENTS.md',group,ops}
        staged=sorted(p for p in stage.rglob('*') if p.is_file())
        for p in staged:
            if p.stat().st_size>20*1024**2:raise RuntimeError('Unexpected large publication file '+str(p))
            if p.suffix in {'.py','.md','.json','.jsonl','.csv','.txt','.log'} and re.search(
                r'(?:ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|sk-proj-[A-Za-z0-9_-]{30,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----)',p.read_text(encoding='utf-8-sig')):
                raise RuntimeError('Credential-like content; blocked '+str(p))
        for name in ['README.md',group,ops,PUBLIC+'/PUBLICATION_README_ko.md',report]:
            p=stage/name
            for target in re.findall(r'\]\(([^)]+)\)',p.read_text(encoding='utf-8')):
                if re.match(r'^(https?://|mailto:|#|[A-Za-z]:)',target):continue
                resolved=(p.parent/target.split('#')[0].strip('<>')).resolve();relpath=resolved.relative_to(stage.resolve()).as_posix()
                if not (resolved.exists() or relpath in old or any(x.startswith(relpath.rstrip('/')+'/') for x in old)):
                    raise RuntimeError('Broken navigation '+name+': '+target)
        paths=''.join(p.as_posix().removeprefix('//?/')+'\n' for p in staged).encode('utf-8')
        oids=git(bare,'hash-object','-w','--stdin-paths',data=paths).decode().splitlines()
        if len(oids)!=len(staged):raise RuntimeError('Git hash count mismatch')
        tree_entries=dict(old)
        for p,oid in zip(staged,oids):tree_entries[p.relative_to(stage).as_posix()]=('100644',oid)
        if any(tree_entries[k]!=v for k,v in old.items() if k not in allowed):raise RuntimeError('Historical data changed')
        git(bare,'read-tree','--empty')
        git(bare,'update-index','-z','--index-info',data=b''.join((mode+' blob '+oid+'\t'+path+'\0').encode('utf-8') for path,(mode,oid) in sorted(tree_entries.items())))
        tree=git(bare,'write-tree').decode().strip()
        if entries(bare,tree)!=tree_entries or runtime_state()!=before:raise RuntimeError('Git/runtime preservation failed')
        env=os.environ.copy()
        for field,key in [('NAME','user.name'),('EMAIL','user.email')]:
            value=command(['git','config','--get',key]).decode().strip();env['GIT_AUTHOR_'+field]=value;env['GIT_COMMITTER_'+field]=value
        commit=git(bare,'commit-tree',tree,'-p',base,'-m','Publish BP retention and archive-content posthoc analysis87',env=env).decode().strip()
        plan=dict(status='ready_to_push',base_commit=base,commit=commit,tree=tree,bare=str(bare),stage=str(stage),remote=REMOTE,
            files_added=len(set(tree_entries)-set(old)),files_modified=sorted(allowed),historical_other_blobs_preserved=True,
            runtime_before=before,source_hashes=hashes,report=report,bundle=bundle,overview=PUBLIC+'/PUBLICATION_README_ko.md',
            copied_files=list(copied.values()),preparation_wall_seconds=time.perf_counter()-started,new_execution=ZERO)
        save(out/'publication_plan.json',plan);save(HERE/'LATEST.json',dict(status='ready_to_push',publication=str(out)))
        print(json.dumps(dict(status='ready_to_push',publication=str(out),commit=commit,files_added=plan['files_added'],bytes=sum(r['bytes'] for r in copied.values())),ensure_ascii=False),flush=True)
    except BaseException:
        save(out/'FAILED.json',dict(at=utc(),traceback=traceback.format_exc(),elapsed_seconds=time.perf_counter()-started,new_execution=ZERO));raise


def record_push(publication,observed):
    out=Path(publication).resolve();plan=read(out/'publication_plan.json')
    if (out/'PUSH_COMPLETE.json').exists():raise RuntimeError('Publication already recorded')
    if observed!=plan['commit'] or runtime_state()!=plan['runtime_before']:raise RuntimeError('Remote/runtime verification differs')
    for name,digest in plan['source_hashes'].items():
        if sha(HERE/name)!=digest:raise RuntimeError('Publication source changed')
    for r in plan['copied_files']:
        if sha(r['source'])!=r['sha256']:raise RuntimeError('Original87 input changed during publication')
    receipt={k:plan[k] for k in ['base_commit','commit','remote','files_added','files_modified','report','overview','bundle','new_execution']}
    receipt.update(status='published',at=utc(),remote_main_verified=True,fast_forward=True,original87_bytes_preserved=True,
        runtime_HEAD_index_and_existing_root_changes_preserved=True,other_historical_data_blobs_preserved=True)
    save(out/'PUSH_COMPLETE.json',receipt);save(HERE/'LATEST.json',dict(publication=str(out),**receipt))
    print(json.dumps(receipt,ensure_ascii=False,indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('--base-commit',required=True)
    p=sub.add_parser('record-push');p.add_argument('--publication',required=True);p.add_argument('--observed-commit',required=True)
    a=ap.parse_args()
    if a.command=='prepare':prepare(a.base_commit)
    else:record_push(a.publication,a.observed_commit)
