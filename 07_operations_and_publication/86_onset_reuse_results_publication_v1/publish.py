"""Publish85 by extending current remote main in an isolated object store."""
from __future__ import annotations
import argparse
import csv
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import traceback
import uuid
from inventory import ROOT,HERE,VERSION,GROUP,PUBLIC,CAMPAIGN,ANALYSIS,PREP,selections
from verify_public import verify

REMOTE='https://github.com/rlatmddn0211/practice_allocation.git'
TOOL='86_onset_reuse_results_publication_v1'
PUBLIC_TOOL='07_operations_and_publication/'+TOOL
OLD_STORE=ROOT/'83_basic_observation_results_publication_v1/results/20261105T024924Z_publication_4f3ebc79/object_store.git'
LAYOUT=ROOT/'74_repository_research_structure_v1/results/20261029T073005Z_prepare_4b1e5fac/path_manifest.json'


def utc():return datetime.now(timezone.utc).isoformat()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def save(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def command(args,data=None,env=None):
    r=subprocess.run(args,input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=ROOT,env=env)
    if r.returncode:raise RuntimeError(repr(args)+'\n'+r.stderr.decode('utf-8','replace'))
    return r.stdout
def git(bare,*args,data=None,env=None):
    clean=(env or os.environ).copy()
    for k in ('GIT_INDEX_FILE','GIT_DIR','GIT_WORK_TREE','GIT_OBJECT_DIRECTORY','GIT_ALTERNATE_OBJECT_DIRECTORIES'):clean.pop(k,None)
    return command(['git','-c','core.longpaths=true','--git-dir='+str(bare),*args],data=data,env=clean)
def runtime_state():
    gd=Path(command(['git','rev-parse','--path-format=absolute','--git-common-dir']).decode().strip())
    return dict(head=command(['git','rev-parse','HEAD']).decode().strip(),index_sha256=sha(gd/'index'),
        root_readme_sha256=sha(ROOT/'README.md'),root_agents_sha256=sha(ROOT/'AGENTS.md'))
def entries(bare,ref):
    result={}
    for r in git(bare,'ls-tree','-rz',ref).split(b'\0'):
        if not r:continue
        header,path=r.split(b'\t',1);mode,kind,oid=header.decode().split()
        if kind!='blob':raise RuntimeError('Unexpected existing tree entry')
        result[path.decode('utf-8')]=(mode,oid)
    return result


def prepare(base_commit):
    if not re.fullmatch('[0-9a-f]{40}',base_commit):raise ValueError('Exact independently read remote SHA required')
    out=HERE/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_publication_'+uuid.uuid4().hex[:8])
    out.mkdir(parents=True,exist_ok=False);snap=out/'source_snapshot';snap.mkdir()
    for p in HERE.iterdir():
        if p.is_file() and p.suffix in {'.py','.md'}:shutil.copy2(p,snap/p.name)
    save(out/'source_hashes.json',{p.name:sha(p) for p in snap.iterdir()})
    print(json.dumps(dict(stage='preparing',output=str(out))),flush=True)
    try:
        before=runtime_state();save(out/'runtime_before.json',before)
        latest=read(ROOT/VERSION/'LATEST.json');status=read(ANALYSIS/'FINAL_STATUS.json')
        if latest['status']!='complete' or status['status']!='complete':raise RuntimeError('Exact completed85 input required')
        check=read(Path(status['verification'])/'FINAL_STATUS.json')
        if check['status']!='passed':raise RuntimeError('Original independent result verification missing')
        receipt=read(ANALYSIS/'reproduction_receipt.json')
        if sha(receipt['bundle'])!=receipt['sha256']:raise RuntimeError('Original reproduction bundle differs')
        bare=out/'object_store.git';command(['git','init','--bare',str(bare)])
        (bare/'objects/info/alternates').write_text((OLD_STORE/'objects').as_posix()+'\n',encoding='utf-8',newline='\n')
        git(bare,'cat-file','-e',base_commit+'^{commit}');old=entries(bare,base_commit)
        layout=read(LAYOUT)
        if len(layout['groups'])!=8:raise RuntimeError('Unexpected historical74 path manifest')
        stage_plain=(out/'stage').resolve();stage=Path('\\\\?\\'+str(stage_plain)) if os.name=='nt' else stage_plain;stage.mkdir()
        selected,media,source_map=selections();copied=[]
        for row in selected:
            target=row['public_path']
            if target in old:raise RuntimeError('Existing published file must be preserved: '+target)
            dest=stage/target;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(row['source'],dest)
            h=sha(row['source'])
            if sha(dest)!=h:raise RuntimeError('Publication copy differs '+target)
            copied.append(dict(row,sha256=h))
        print(json.dumps(dict(stage='copied',files=len(copied),bytes=sum(r['bytes'] for r in copied))),flush=True)
        pub_record=PUBLIC_TOOL+'/results/'+out.name
        def document(path,text):
            p=stage/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8',newline='\n')
        def record(name,value):save(out/name,value);save(stage/pub_record/name,value)
        document(PUBLIC+'/PUBLICATION_FILE_MAP.jsonl',''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in copied))
        document(PUBLIC+'/SOURCE_EPISODE_MAP.jsonl',''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in source_map))
        with (stage/PUBLIC/'MEDIA_INDEX.csv').open('w',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(media[0]));w.writeheader();w.writerows(media)
        published_sources={r['source'] for r in copied};omitted=[]
        for line in (ANALYSIS/'large_artifact_references.jsonl').read_text(encoding='utf-8').splitlines():
            r=json.loads(line)
            if r['path'] not in published_sources:omitted.append(dict(local_path=r['path'],bytes=r['bytes'],sha256=r['sha256'],
                availability='local_only_not_uploaded',hash_source='completed85 immutable large artifact catalog'))
        document(PUBLIC+'/LOCAL_ONLY_ARTIFACTS.jsonl',''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in omitted))
        for p in HERE.iterdir():
            if p.is_file() and p.suffix in {'.py','.md'}:
                dst=stage/PUBLIC_TOOL/p.name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst)
        for p in snap.iterdir():
            dst=stage/pub_record/'source_snapshot'/p.name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst)
        record('path_manifest_extension.json',dict(base_commit=base_commit,historical74_manifest_sha256=sha(LAYOUT),
            historical_mapping_unchanged=True,additions={VERSION:PUBLIC,TOOL:PUBLIC_TOOL},new_topic=GROUP,
            prior83_publication_commit='68f536f7ca20579af5904801e2d47744983b4c95'))
        report=GROUP+'/'+Path(latest['report']).relative_to(ROOT).as_posix()
        analysis_rel=report.rsplit('/',1)[0]
        rel_a='results/'+CAMPAIGN.name+'/analysis/'+ANALYSIS.name
        public_doc=f'''# 85번 GitHub 공개 범위와 재현 안내

[원문 결과 보고서]({rel_a}/report_ko.md) · [핵심 그림]({rel_a}/figures/03_do_learning_curves.png) · [부모·미래별 대응표]({rel_a}/paired_effects_by_parent_future.csv) · [원 재현 ZIP]({rel_a}/reproduction_bundle.zip)

85는 원81의 다섯 실제1M full 학습기를 복원해 두 미래×세 조건을64k씩 계속한 새 파일럿이다. BASE/RANDOM_PRE/ONSET의 기존 네 과제 SAC를 비교했다. 81/82/84는 같은 원 관측 캠페인의 기록·사후분석이다. 이번 게시가84나 다른 미게시 실험을 추가 공개한 것은 아니다.

| 조건 | DO 정규화 AUC | 최종 DO 성공 |
|---|---:|---:|
| BASE |0.547%|1/160|
| RANDOM_PRE |3.125%|11/160|
| ONSET |1.875%|4/160|

ONSET−RANDOM_PRE는−1.250%p, 고정 저장소·개발 패널의 부모 bootstrap 분위 범위[-1.875,−0.547]이다. 부모 평균4개는 음수,1개는0이다. ONSET−BASE는+1.328%p[-0.469,+3.828]이고, 최종 ONSET 성공4건은 모두R04/F01이다. 명목 후속 신호 기준을 충족하지 않아 현재 onset 처치의 확대는 보류했다. BP 이득과 Push 손해도 원 보고서에 함께 제시했다. 일반적인 우위나 재사용 가능한 기초동작을 입증한 결과가 아니다.

초기 물리 X와 reset 반환 관측의 이전 X를 혼동한 측정 오류를 고쳤다. 원1M 정책/사례 +0의 DO5mm 진행은 raw 기준63/80에서 물리 x0 기준14/80으로 정정된다. 공식 성공0/80과 원 관측·옛 보고서는 그대로다. detector 문턱·창·SAC 입력을 바꾸지 않았고 branch 결과를 보기 전에 매핑을 수정했다.

## 공개한 자료

- 원문 보고서, 표·그림6개,6,080개 평가 라벨/에피소드 지표, 모든 부모·미래·조건의 결과와 고정 bootstrap draw.
- 실제 코드와 source snapshot, 설정·seed·원본 hash, 준비 실패/정정·기술 및 독립 검산·비용 원장.
- 결과와 무관하게 사전 고정한 최종 영상240개, 같은240에피소드의 NPZ·sidecar·frame/step 대응. [영상 목록](MEDIA_INDEX.csv).
- 초기 좌표 정정 검산을 위한 공통 +0 DO80개 원 수치 궤적.
- 적격25개와 제외6개를 포함한 원 DO 성공31개 원 수치 에피소드, 선정창과 cache. [원 경로↔공개 경로](SOURCE_EPISODE_MAP.jsonl).

원 보고서·코드·표·영상·NPZ·원 ZIP의 bytes는 유지했다. Windows 절대 경로는 출처이며 공개 다운로드 URL이 아니다. [공개 파일 경로·크기·SHA256](PUBLICATION_FILE_MAP.jsonl)이 원 경로를 연결한다. 이 게시 과정의 새 환경·정책·학습 실행은0이다.

## 로컬 보관 자료와 한계

모델/optimizer/replay checkpoint 본체, 전체 훈련 전이, 나머지 평가 원 전이, 상세 update/native replay 기록과 환경 snapshot 본체는 로컬 보관이다. [명시적 미게시 목록](LOCAL_ONLY_ARTIFACTS.jsonl)과 원본[해시 목록]({rel_a}/large_artifact_references.jsonl)을 따른다. 이 로컬 경로를 누구나 다운로드할 수 있다고 해석하지 않는다. 다섯 원1M full 상태도 준비 state_manifest에 hash가 있으나 본체는 GitHub에 없다.

공개 자료만으로 전체 평가 라벨의 AUC·대응 효과·저장 bootstrap,31개 source의 detector·window/cache와 공개320개 평가 원 궤적을 파일만으로 검산할 수 있다. 전체 SAC 학습 재개 및 원 분석 전체를 그대로 재실행하려면 로컬 대형 자료와 고정 runtime이 필요하다. 공개 소스를 원 flat 경로로 복구할 때는74/83/86 path manifest를 함께 사용한다. 원 코드의 절대/상대 경로를 임의로 새 경로와 같다고 가정하지 않는다.

저장소 루트에서 Python과 NumPy/pandas/Parquet 엔진을 사용해 다음 파일 전용 검산을 실행한다.

```text
python 07_operations_and_publication/86_onset_reuse_results_publication_v1/verify_public.py --repository .
```

새 환경 생성/reset/step, 모델 역직렬화/forward, 학습 및 새 bootstrap draw를 수행하지 않는다. 신규 본실험 비용은4,964,900전이(학습1.92M,평가3.04M,기술4,900)로4.97M 상한 이내다. 원81비용6,604,850은 별도로 보존한다.
'''
        document(PUBLIC+'/PUBLICATION_README_ko.md',public_doc)
        document(GROUP+'/README.md',f'''# 경험 구간 재사용 파일럿

같은 성공 에피소드에서 어떤 구간을 SAC에 재사용할 때 추가 학습에 도움이 되는가?

- [85번 결과·공개 자료 안내]({VERSION}/PUBLICATION_README_ko.md)
- [원문 한국어 보고서]({VERSION}/{rel_a}/report_ko.md)
- [관련 원81·82 관측](../08_basic_learning_observations/README.md)

85는 ONSET/RANDOM_PRE/BASE30분기를 모두 완료했다. DO AUC의 ONSET−RANDOM_PRE는−1.250%p, ONSET−BASE는+1.328%p다. 명목 후속 신호 기준은 미충족이며, 고정 저장소/기존16사례 패널의 파일럿이다. 추가 학습에서의 보편적인 경험 선택법이나 기초동작을 찾았다고 주장하지 않는다.

![DO 부모별 학습 곡선]({VERSION}/{rel_a}/figures/03_do_learning_curves.png)
''')
        main=git(bare,'show',base_commit+':README.md').decode('utf-8');marker='## 연구 질문별로 보기'
        if marker not in main:raise RuntimeError('Remote root navigation anchor differs')
        intro=f'''## 2026-11-06 게시: 성공 이전 진행 시작 구간 재사용

[85번 보고서·표·그림·원자료 공개 안내]({PUBLIC}/PUBLICATION_README_ko.md): 원81의 다섯1M 부모에서 BASE/RANDOM_PRE/ONSET30분기와6,080에피소드 평가를 완료했다. DO AUC의 ONSET−RANDOM_PRE는−1.250%p, ONSET−BASE는+1.328%p다. 현재 onset 선택의 확대 기준은 충족하지 못했다. BP 이득·Push 손해와 초기 좌표에 따른 DO 진행63/80→14/80 정정을 함께 남긴다. 원문 보고서·재현 자료·사전 고정 영상240개를 공개한다.

'''
        main=main.replace(marker,intro+marker,1)
        anchor='\n실행·공개 폴더에는'
        if anchor not in main:raise RuntimeError('Remote topic table anchor differs')
        main=main.replace(anchor,f'| [경험 구간 재사용]({GROUP}/) | 성공 경험의 어느 구간을 재사용하면 추가 SAC 학습에 유용한가? | 1 |\n'+anchor,1)
        document('README.md',main)
        ops=git(bare,'show',base_commit+':07_operations_and_publication/README.md').decode('utf-8')
        document('07_operations_and_publication/README.md',ops+f'\n## 2026-11-06 추가 게시\n\n- [86 — onset 재사용 파일럿85 결과 게시]({TOOL}/README.md)\n')
        agents=git(bare,'show',base_commit+':AGENTS.md').decode('utf-8')
        document('AGENTS.md',agents+'\n- On2026-11-06 the user authorized publication of completed85 only. Independent86 adds30 fixed BASE/RANDOM_PRE/ONSET continuations from original81 five1M parents, reports/labels/figures/code/receipts,240 fixed videos with numeric traces,80 shared-start DO traces and31 original successful DO source episodes. Large model/replay/full raw payloads stay local with explicit hashes/availability. DO AUC P-U=-1.250pp, P-B=+1.328pp; nominal progression not met, no automatic onset expansion. Preserve the physical-x0 correction of raw DO5mm-progress63/80 to14/80, with original official success0/80 unchanged. Group09 contains85; group07 contains86. Existing published blobs, local runtime HEAD/index and original results are preserved. No environment/model/learning/new-bootstrap execution or publication of84/other unrelated local experiments.\n')
        verification=verify(stage);record('verification.json',verification)
        record('selection_summary.json',dict(copied_files=len(copied),copied_bytes=sum(r['bytes'] for r in copied),videos=240,
            numeric_evaluation_episodes=320,successful_source_episodes=31,local_only_catalogued_files=len(omitted),
            local_only_catalogued_bytes=sum(r['bytes'] for r in omitted),publication_excludes_other_unpublished_experiments=True))
        record('runtime_before.json',before);record('source_hashes.json',read(out/'source_hashes.json'))
        allowed={'README.md','AGENTS.md','07_operations_and_publication/README.md'}
        staged=sorted(p for p in stage.rglob('*') if p.is_file())
        for p in staged:
            if p.stat().st_size>=50*1024**2:raise RuntimeError('Unexpected large published file '+str(p))
            if p.suffix in {'.py','.md','.json','.jsonl','.csv','.txt','.log'}:
                if re.search(r'(?:ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|sk-proj-[A-Za-z0-9_-]{30,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----)',p.read_text(encoding='utf-8-sig')):
                    raise RuntimeError('Credential-like content; blocked publication '+str(p))
        for name in ['README.md',GROUP+'/README.md',PUBLIC+'/PUBLICATION_README_ko.md',report]:
            path=stage/name
            for target in re.findall(r'\]\(([^)]+)\)',path.read_text(encoding='utf-8')):
                if re.match(r'^(https?://|mailto:|#|[A-Za-z]:)',target):continue
                resolved=(path.parent/target.split('#')[0].strip('<>')).resolve();rel=resolved.relative_to(stage.resolve()).as_posix()
                if not (resolved.exists() or rel in old or any(k.startswith(rel.rstrip('/')+'/') for k in old)):
                    raise RuntimeError('Missing public navigation '+name+': '+target)
        paths=''.join((p.as_posix().removeprefix('//?/') if os.name=='nt' else p.as_posix())+'\n' for p in staged).encode('utf-8')
        keys=git(bare,'hash-object','-w','--stdin-paths',data=paths).decode().splitlines()
        if len(keys)!=len(staged):raise RuntimeError('Git blob count mismatch')
        tree_entries=dict(old)
        for p,oid in zip(staged,keys):tree_entries[p.relative_to(stage).as_posix()]=('100644',oid)
        if not all(tree_entries[k]==v for k,v in old.items() if k not in allowed):raise RuntimeError('Historical blob changed')
        git(bare,'read-tree','--empty')
        data=b''.join((mode+' blob '+oid+'\t'+path+'\0').encode('utf-8') for path,(mode,oid) in sorted(tree_entries.items()))
        git(bare,'update-index','-z','--index-info',data=data);tree=git(bare,'write-tree').decode().strip()
        if entries(bare,tree)!=tree_entries or runtime_state()!=before:raise RuntimeError('Git tree/runtime preservation failed')
        env=os.environ.copy()
        for field,key in [('NAME','user.name'),('EMAIL','user.email')]:
            value=command(['git','config','--get',key]).decode().strip();env['GIT_AUTHOR_'+field]=value;env['GIT_COMMITTER_'+field]=value
        commit=git(bare,'commit-tree',tree,'-p',base_commit,'-m','Publish onset replay pilot85 results and reproducibility artifacts',env=env).decode().strip()
        plan=dict(status='ready_to_push',base_commit=base_commit,commit=commit,tree=tree,bare=str(bare),stage=str(stage),remote=REMOTE,
            files_added=len(set(tree_entries)-set(old)),files_modified=sorted(allowed),existing_other_blobs_preserved=True,
            runtime_before=before,source_hashes=read(out/'source_hashes.json'),report=report,overview=PUBLIC+'/PUBLICATION_README_ko.md',
            bundle=analysis_rel+'/reproduction_bundle.zip',verification=verification,new_environment_steps=0,new_policy_forwards=0)
        save(out/'publication_plan.json',plan);save(HERE/'LATEST.json',dict(publication=str(out),status='ready_to_push'))
        print(json.dumps(dict(status='ready_to_push',publication=str(out),commit=commit,files_added=plan['files_added'],copied_bytes=sum(r['bytes'] for r in copied))),flush=True)
    except BaseException:
        save(out/'FAILED.json',dict(at=utc(),traceback=traceback.format_exc()));raise


def record_push(publication,observed):
    out=Path(publication).resolve();plan=read(out/'publication_plan.json')
    if (out/'PUSH_COMPLETE.json').exists():raise RuntimeError('Already recorded published commit')
    if observed!=plan['commit'] or runtime_state()!=plan['runtime_before']:raise RuntimeError('Remote or local state differs')
    for name,h in plan['source_hashes'].items():
        if sha(HERE/name)!=h:raise RuntimeError('Publication source changed '+name)
    receipt=dict(status='published',at=utc(),commit=observed,base_commit=plan['base_commit'],remote=REMOTE,
        fast_forward=True,remote_verified=True,local_runtime_head_index_and_original_results_preserved=True,
        report=plan['report'],overview=plan['overview'],bundle=plan['bundle'],files_added=plan['files_added'],
        new_environment_steps=0,new_policy_forwards=0,new_learning_updates=0,new_bootstrap_draws=0)
    save(out/'PUSH_COMPLETE.json',receipt);save(HERE/'LATEST.json',dict(publication=str(out),**receipt))
    print(json.dumps(receipt,ensure_ascii=False),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('--base-commit',required=True)
    p=sub.add_parser('record-push');p.add_argument('--publication',type=Path,required=True);p.add_argument('--observed-commit',required=True)
    a=ap.parse_args()
    if a.command=='prepare':prepare(a.base_commit)
    else:record_push(a.publication,a.observed_commit)
