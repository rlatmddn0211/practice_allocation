"""Add completed 81/82 results to current remote main in an isolated Git store."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import traceback
import uuid
from datetime import datetime, timezone
from verify_results import verify as verify_results

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REMOTE = 'https://github.com/rlatmddn0211/practice_allocation.git'
GROUP = '08_basic_learning_observations'
V81 = '81_basic_sac_observation_campaign_v1'
V82 = '82_basic_observation_exploratory_report_v1'
TOOL = '83_basic_observation_results_publication_v1'
PUBLIC_TOOL = '07_operations_and_publication/' + TOOL
CAMPAIGN = '20261102T085036Z_observation_8e858967'
A81 = '20261103T000632Z_f77754'
A82 = '20261103T000931Z_1c0dc354'
C81 = ROOT / V81 / 'results' / CAMPAIGN
C82 = ROOT / V82 / 'results' / A82
OLD_STORE = ROOT / '74_repository_research_structure_v1/results/20261029T073015Z_build_a6ebdafd/object_store.git'
LAYOUT = ROOT / '74_repository_research_structure_v1/results/20261029T073005Z_prepare_4b1e5fac/path_manifest.json'


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def command(args, *, data=None, env=None):
    result = subprocess.run(args, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            cwd=ROOT, env=env, check=False)
    if result.returncode:
        raise RuntimeError('Command failed: ' + repr(args) + '\n' + result.stderr.decode('utf-8', 'replace'))
    return result.stdout


def git(bare, *args, data=None, env=None):
    clean = (env or os.environ).copy()
    for name in ('GIT_INDEX_FILE', 'GIT_DIR', 'GIT_WORK_TREE', 'GIT_OBJECT_DIRECTORY',
                 'GIT_ALTERNATE_OBJECT_DIRECTORIES'):
        clean.pop(name, None)
    return command(['git', '--git-dir=' + str(bare), *args], data=data, env=clean)


def runtime_state():
    common = Path(command(['git', 'rev-parse', '--path-format=absolute', '--git-common-dir']).decode().strip())
    return dict(head=command(['git', 'rev-parse', 'HEAD']).decode().strip(),
                index_sha256=file_sha(common / 'index'),
                root_readme_sha256=file_sha(ROOT / 'README.md'),
                root_agents_sha256=file_sha(ROOT / 'AGENTS.md'))


def remote_head():
    return command(['git', 'ls-remote', REMOTE, 'refs/heads/main']).decode().split()[0]


def entries(bare, ref):
    result = {}
    for record in git(bare, 'ls-tree', '-rz', ref).split(b'\0'):
        if record:
            header, name = record.split(b'\t', 1)
            mode, kind, oid = header.decode().split()
            if kind != 'blob':
                raise RuntimeError('Unexpected tree entry ' + name.decode())
            result[name.decode('utf-8')] = (mode, oid)
    return result


def public_path(source):
    rel = source.relative_to(ROOT).as_posix()
    if rel.startswith((V81 + '/', V82 + '/')):
        return GROUP + '/' + rel
    raise ValueError(rel)


def is_selected(p):
    rel = p.relative_to(ROOT).parts
    if '__pycache__' in rel or p.suffix in ('.pyc', '.pyo'):
        return False
    if rel[0] == V82:
        if 'results' in rel:
            return len(rel) > 2 and rel[2] == A82
        return p.suffix in ('.py', '.md') or p.name in ('LATEST.json', 'DELIVERY.json', 'ACTIVE_INPUT.json')
    if len(rel) == 2 or rel[1] == 'practice_allocation':
        return p.suffix in ('.py', '.json', '.md')
    if rel[1] == 'verification':
        return p.suffix in ('.py', '.json', '.md', '.csv', '.log', '.txt', '.png')
    if len(rel) < 4 or rel[1:3] != ('results', CAMPAIGN):
        return False
    inside = rel[3:]
    if inside[0] == 'runs':
        if len(inside) == 3:
            return p.suffix in ('.json', '.jsonl', '.log', '.md')
        section = inside[2]
        if section == 'evaluation_transitions':
            return (p.parents[1] / 'videos' / (p.stem + '.mp4')).is_file()
        if section in ('training_transitions', 'replay_usage', 'update_scalars', 'update_summaries',
                       'environment_snapshots'):
            return False
        if section == 'checkpoints':
            return p.suffix == '.json'
        return section in ('costs', 'episodes', 'evaluation_episodes', 'evaluation_receipts',
                           'schema', 'source_snapshot', 'videos')
    if inside[0] == 'verification':
        return p.suffix in ('.py', '.json', '.md', '.csv', '.log', '.txt', '.png')
    return True


def fresh_output():
    name = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_publication_' + uuid.uuid4().hex[:8]
    out = HERE / 'results' / name
    out.mkdir(parents=True, exist_ok=False)
    snap = out / 'source_snapshot'
    snap.mkdir()
    for p in HERE.iterdir():
        if p.is_file() and p.suffix in ('.py', '.md'):
            shutil.copy2(p, snap / p.name)
    save(out / 'source_hashes.json', {p.name: file_sha(p) for p in snap.iterdir()})
    return out


def prepare(base_commit=None):
    out = fresh_output()
    print(json.dumps(dict(stage='preparing', output=str(out))), flush=True)
    try:
        before = runtime_state()
        # An explicit SHA permits offline construction after an independently approved
        # native Git network read. The eventual push still has to fast-forward.
        base = base_commit or remote_head()
        assert re.fullmatch('[0-9a-f]{40}', base)
        save(out / 'runtime_state_before.json', before)
        save(out / 'independent_result_verification.json', verify_results(ROOT))
        final = read(C81 / 'FINAL_STATUS.json')
        latest82 = read(ROOT / V82 / 'LATEST.json')
        for item in (final['report'], final['bundle'], latest82['report'], latest82['bundle']):
            assert file_sha(item['path']) == item['sha256']
        bare = out / 'object_store.git'
        command(['git', 'init', '--bare', str(bare)])
        (bare / 'objects/info/alternates').write_text((OLD_STORE / 'objects').as_posix() + '\n', encoding='utf-8', newline='\n')
        git(bare, 'config', 'core.longpaths', 'true')
        git(bare, 'cat-file', '-e', base + '^{commit}')
        old = entries(bare, base)
        # Consume and preserve the actual historical mapping, rather than assuming flat paths.
        old_layout = read(LAYOUT)
        assert len(old_layout['groups']) == 8
        stage_plain = (out / 'stage').resolve()
        stage = Path('\\\\?\\' + str(stage_plain)) if os.name == 'nt' else stage_plain
        stage.mkdir()
        copies = []
        source_paths = [p for name in (V81, V82) for p in (ROOT / name).rglob('*') if p.is_file()]
        selected = [p for p in source_paths if is_selected(p)]
        assert len([p for p in selected if p.suffix == '.mp4']) == 400
        assert len([p for p in selected if p.suffix == '.npz' and 'evaluation_transitions' in p.parts]) == 400
        assert sum(p.stat().st_size for p in selected) < 512 * 1024 * 1024
        for p in selected:
            target = public_path(p)
            if target in old:
                raise RuntimeError('Existing published path: ' + target)
            dst = stage / target
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst)
            key = file_sha(p)
            assert file_sha(dst) == key
            copies.append(dict(original_path=str(p), public_path=target, bytes=p.stat().st_size, sha256=key))
        print(json.dumps(dict(stage='copied', files=len(copies), bytes=sum(x['bytes'] for x in copies))), flush=True)
        pub_record = PUBLIC_TOOL + '/results/' + out.name

        def document(logical, content):
            target = stage / logical
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding='utf-8', newline='\n')

        def record(name, value):
            save(stage / pub_record / name, value)
            save(out / name, value)

        for p in HERE.iterdir():
            if p.is_file() and p.suffix in ('.py', '.md'):
                dest = stage / PUBLIC_TOOL / p.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dest)
        for p in (out / 'source_snapshot').iterdir():
            dest = stage / pub_record / 'source_snapshot' / p.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest)
        for name in ('source_hashes.json', 'runtime_state_before.json', 'independent_result_verification.json'):
            shutil.copy2(out / name, stage / pub_record / name)
        receipt = stage / pub_record / 'published_input_receipt.jsonl'
        receipt.write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in copies), encoding='utf-8')
        reference_hashes = {}
        for line in (C81 / 'analysis' / A81 / 'artifact_hashes.jsonl').read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            reference_hashes[str(Path(row['path']).resolve())] = row
        selected_set = set(selected)
        omitted = []
        for p in source_paths:
            if p in selected_set or '__pycache__' in p.parts:
                continue
            prior = reference_hashes.get(str(p.resolve()), {})
            omitted.append(dict(local_path=str(p), bytes=p.stat().st_size, sha256=prior.get('sha256'),
                                hash_source='81 archived artifact manifest' if prior else 'not recorded here',
                                availability='local_only_not_uploaded',
                                reason='large raw/checkpoint/replay/update/snapshot data or non-main fixture/watcher'))
        omitted_path = stage / pub_record / 'local_only_artifacts.jsonl'
        omitted_path.write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in omitted), encoding='utf-8')
        media = []
        for p in selected:
            if p.suffix == '.mp4':
                checkpoint, task, case = p.stem.split('_')
                media.append(dict(run_id=p.parents[1].name, task_id=task, checkpoint_id=int(checkpoint),
                                  initial_case_id=task + '_' + case, video=public_path(p),
                                  numeric_trajectory=public_path(p.parents[1] / 'evaluation_transitions' / (p.stem + '.npz')),
                                  selection='pre-outcome fixed first two cases per task'))
        with (stage / pub_record / 'media_index.csv').open('w', encoding='utf-8', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(media[0]))
            w.writeheader()
            w.writerows(sorted(media, key=lambda x: (x['run_id'], x['task_id'], x['checkpoint_id'], x['initial_case_id'])))
        report81 = V81 + '/results/' + CAMPAIGN + '/analysis/' + A81 + '/report_ko.md'
        report82 = V82 + '/results/' + A82 + '/report_ko.md'
        overview = '\n'.join([
            '# 기본 학습의 행동·경험 관측', '',
            '81번은 DO/DC/Push/BP 기본 SAC의 다섯 독립 초기학습을 실행당 총 1M 전이까지 기록한 관측 캠페인이다. '
            '82번은 같은 자료의 탐색 분석이며 별도의 독립 실험이 아니다.', '',
            '- [81 실험 보고서](' + report81 + ')',
            '- [82 탐색 분석 보고서](' + report82 + ')',
            '- [공개 자료 범위·재현 안내](../' + pub_record + '/report_ko.md)',
            '- [영상 400개와 대응 수치 궤적 목록](../' + pub_record + '/media_index.csv)', '',
            '| 과제 | 최종 success_any | 5개 실행 범위 | 최종 시점 success_final |',
            '|---|---:|---:|---:|',
            '| DrawerClose | 100% | 100% | 97.5% |',
            '| ButtonPress | 92.5% | 87.5–100% | 73.75% |',
            '| DrawerOpen | 0% | 0% | 0% |',
            '| Push | 1.25% | 0–6.25% | 0% |', '',
            '과제당 고정된 16개 물리 초기조건을 모든 실행·시점에서 공유한다. 표의 평균은 5개 실행의 평균이며 '
            '표준 Meta-World 전체 goal 평가가 아니다. 신뢰구간은 계산하지 않았다.', '',
            'BP의 80개 실행×사례 이력 중 45개에서 후속 평가의 실패, 41개에서 이후 관측된 회복이 있었다. '
            '이 수는 80개의 독립 초기조건 또는 영구적 능력 상실 건수가 아니다. '
            '한 에피소드 안의 성공 상태 이탈과 학습 시점 사이의 성공 상실을 구분한다.', '',
            '학습 5M, 정기 평가 1.6M, 기술 검사 4,850으로 총 6,604,850 전이를 사용했다. '
            '추가 진단은 0이며 6.71M 상한 이내다. 유용한 기초동작·원인·경험 선택 방법을 확인한 결과는 아니다.', '',
            '![과제·실행별 학습 곡선](' + V81 + '/results/' + CAMPAIGN + '/analysis/' + A81 + '/figures/learning_curves.png)', '',
            '원본 보고서·분석 코드·표·그림·재현 ZIP은 원문 bytes를 유지했다. 전체 훈련 전이·모델·replay·상세 '
            '업데이트 로그와 중간 환경 snapshot은 로컬 보관이며 이 GitHub 게시본에 포함되지 않는다. '
            '누락 범위와 해시 출처는 공개 자료 범위 문서를 따른다.', ''])
        document(GROUP + '/README.md', overview)
        # Preserve remote README content, adding a dated entry rather than replacing it with the runtime copy.
        main = git(bare, 'show', base + ':README.md').decode('utf-8')
        marker = '## 연구 질문별로 보기'
        assert marker in main
        addition = ('## 2026-11-05 게시: 기본 학습 관측 결과\n\n'
                    '[81·82번 결과와 공개 자료 안내](' + GROUP + '/README.md): '
                    '다섯 독립 초기학습, 총 5M 학습 전이와 3,200회 평가를 완료했다. '
                    'DC 100%, BP 92.5%, DO 0%, Push 1.25%는 과제당 공통 16사례의 최종 평균이다. '
                    '수치 궤적·사례 이력·그림·사전 선정 영상 400개와 비용을 함께 공개한다. '
                    '유용한 기초동작이나 학습 개선 방법은 아직 확인하지 못했다.\n\n')
        main = main.replace(marker, addition + marker, 1)
        main = main.replace('관련 질문을8개 큰 폴더로 묶었습니다.', '관련 질문을 주제별 큰 폴더로 묶었습니다.')
        newrow = '| [기본 학습 관측](' + GROUP + '/) | 행동·경험·정책 변화에서 어떤 반복 현상이 관찰되는가? | 2 |\n'
        anchor = '\n실행·공개 폴더에는'
        assert anchor in main
        main = main.replace(anchor, newrow + anchor, 1)
        main = main.replace('[현재 보존 개입 결과]', '[이전 보존 개입 결과]')
        document('README.md', main)
        ops = git(bare, 'show', base + ':07_operations_and_publication/README.md').decode('utf-8')
        ops += '\n## 2026-11-05 추가 게시\n\n- [83 — 기본 관측 81·82 결과 게시](' + TOOL + '/README.md)\n'
        document('07_operations_and_publication/README.md', ops)
        agents = git(bare, 'show', base + ':AGENTS.md').decode('utf-8')
        agents += ('\n- On 2026-11-05 the user explicitly requested publication of completed 81/82 results. '
                   'Independent 83 adds their unchanged reports, code, labels, figures, 400 outcome-blind videos '
                   'and matching numeric trajectories under 08_basic_learning_observations. 82 is the same '
                   '81 data, not an independent experiment. Preserve local runtime paths/HEAD/index and all '
                   'historical sources. Large training/checkpoint/replay/update/snapshot data stay local '
                   'with explicit availability records. No new environment steps or policy execution.\n')
        document('AGENTS.md', agents)
        record('path_manifest_extension.json', dict(base_commit=base,
            historical_mapping_path=str(LAYOUT), historical_mapping_sha256=file_sha(LAYOUT),
            additions={V81: GROUP + '/' + V81, V82: GROUP + '/' + V82, TOOL: PUBLIC_TOOL},
            unchanged_historical_mapping=True))
        verification = verify_results(stage)
        verification['original_report_and_bundle_sha256_passed'] = True
        verification['video_count'] = 400
        verification['matching_numeric_trajectory_count'] = 400
        record('verification.json', verification)
        doc = '\n'.join([
            '# 81·82번 GitHub 공개 범위와 검증', '',
            '게시 요청일: 2026-11-05. 학습·평가 완료일: 2026-11-03. 새 환경 전이·정책 forward는 0이다.', '',
            '81의 다섯 실행과 3,200개 평가 및 82의 파일 분석을 게시한다. '
            '모든 과제·실행·시점과 불리하거나 변화가 없는 결과를 포함한다. '
            '75–80 등 다른 미게시 실험을 이 요청에 묶어 새로 공개하지 않는다.', '',
            '## 게시한 자료', '',
            '- 원문 한국어 보고서 2개, 집계 CSV/Parquet, 원 평가 라벨 3,200행, 학습 곡선·사례 이력 그림.',
            '- 실제 실행 코드와 source snapshot, 고정 설정·seed·물리 평가 사례·schema, 기술·산술 검증 영수증.',
            '- 사전 선정한 영상 400개, 동일 400에피소드의 원본 수치 NPZ와 sidecar, 영상별 frame/step 대응.',
            '- 실행 완료·비용 기록과 original reproduction_bundle.zip 두 개.', '',
            '## 로컬 보관 자료와 재현 범위', '',
            '전체 훈련 전이, 나머지 평가 수치 궤적, model/optimizer/replay checkpoint 본체, '
            '상세 업데이트·replay 사용 원장과 환경 snapshot 본체는 GitHub에 업로드하지 않았다. '
            'local_only_artifacts.jsonl의 availability와 해시 출처를 확인한다. '
            '이 파일의 로컬 절대 경로는 공개 다운로드 URL이 아니다. '
            '원문 artifact_hashes.jsonl은 원 분석 시점의 해시 기록이며 모든 보관 파일을 이번에 재검증했다는 뜻은 아니다.', '',
            '이 공개본으로 원 평가 라벨·집계·사례 이력·공개 영상의 수치 궤적을 검산할 수 있다. '
            '전체 학습의 재개 또는 원 분석 전체의 재실행에는 비공개 대형 원본과 원 runtime이 추가로 필요하다. '
            '기존 Windows 절대 경로는 출처 기록으로 보존했으며 path_manifest_extension.json에서 게시 경로를 연결한다.', '',
            '공개본 라벨 검산: 저장소 루트에서 Python으로 '
            '07_operations_and_publication/83_basic_observation_results_publication_v1/verify_results.py '
            '--repository . 를 실행한다. pandas와 Parquet 엔진이 필요하고 환경·모델을 실행하지 않는다.', '',
            '## 검증', '',
            '원문 보고서·ZIP 해시, 200개 평가 셀·3,200개 라벨·320개 사례 이력과 64개 고유 물리 사례, '
            '모든 기존 게시 파일의 Git blob 보존, 새 공개 파일의 원본 SHA256, 영상·수치 대응 및 상대 링크를 검증한다. '
            '이 검증은 게시 무결성 검증이며 새 과학적 실험이 아니다.', '',
            '최종 성공률: DC 100%, BP 92.5%, DO 0%, Push 1.25%. '
            '과제당 고정 16사례·5개 학습 실행에 조건화한 탐색 통계이며 신뢰구간을 산출하지 않았다. '
            '기초동작·학습 개선·인과 원리를 확인했다는 결론을 추가하지 않는다.', '',
            '기준 원격 커밋: ' + base, '',
            '[결과 목차](../../../' + GROUP + '/README.md)', ''])
        # The report is nested results/<id>, therefore four levels back to repository root.
        doc = doc.replace('../../../' + GROUP, '../../../../' + GROUP)
        document(pub_record + '/report_ko.md', doc)
        save(out / 'selection_summary.json', dict(copied_files=len(copies), copied_bytes=sum(x['bytes'] for x in copies),
             local_only_files=len(omitted), local_only_bytes=sum(x['bytes'] for x in omitted),
             videos=400, numeric_trajectories=400, new_environment_steps=0))
        shutil.copy2(out / 'selection_summary.json', stage / pub_record / 'selection_summary.json')
        validate(stage, bare, old, copies)
        # Single Git process hashes all new content without shell interpolation or filters.
        staged = sorted(p for p in stage.rglob('*') if p.is_file())
        paths = ''.join((p.as_posix().removeprefix('//?/') if os.name == 'nt' else p.as_posix())
                        + '\n' for p in staged).encode('utf-8')
        keys = git(bare, 'hash-object', '-w', '--stdin-paths', data=paths).decode().splitlines()
        assert len(keys) == len(staged)
        tree_entries = dict(old)
        for p, oid in zip(staged, keys):
            tree_entries[p.relative_to(stage).as_posix()] = ('100644', oid)
        allowed = {'README.md', 'AGENTS.md', '07_operations_and_publication/README.md'}
        assert all(tree_entries[k] == v for k, v in old.items() if k not in allowed)
        git(bare, 'read-tree', '--empty')
        index = b''.join((mode + ' blob ' + oid + '\t' + path + '\0').encode('utf-8')
                         for path, (mode, oid) in sorted(tree_entries.items()))
        git(bare, 'update-index', '-z', '--index-info', data=index)
        tree = git(bare, 'write-tree').decode().strip()
        actual = entries(bare, tree)
        assert actual == tree_entries
        assert runtime_state() == before
        env = os.environ.copy()
        for suffix, config in (('NAME', 'user.name'), ('EMAIL', 'user.email')):
            value = command(['git', 'config', '--get', config]).decode().strip()
            env['GIT_AUTHOR_' + suffix] = value
            env['GIT_COMMITTER_' + suffix] = value
        commit = git(bare, 'commit-tree', tree, '-p', base, '-m',
                     'Publish completed basic SAC observation results and exploratory analysis', env=env).decode().strip()
        plan = dict(status='ready_to_push', created_at=utc(), base_commit=base, commit=commit, tree=tree,
                    bare=str(bare), stage=str(stage), remote=REMOTE, files_added=len(set(actual) - set(old)),
                    files_modified=sorted(allowed), existing_other_blobs_preserved=True,
                    runtime_state_before=before, new_environment_steps=0, new_policy_forwards=0,
                    report81=GROUP + '/' + report81, report82=GROUP + '/' + report82,
                    source_hashes=read(out / 'source_hashes.json'))
        save(out / 'publication_plan.json', plan)
        save(HERE / 'LATEST.json', dict(publication=str(out), status='ready_to_push'))
        print(json.dumps(dict(status='ready_to_push', publication=str(out), commit=commit,
                              added=plan['files_added'], copied_bytes=sum(x['bytes'] for x in copies))), flush=True)
    except BaseException:
        save(out / 'FAILED.json', dict(time=utc(), traceback=traceback.format_exc()))
        raise


def validate(stage, bare, old, copies):
    historical_readme_links = set(re.findall(r'\]\(([^)]+)\)',
        git(bare, 'show', old['README.md'][1]).decode('utf-8')))
    for row in copies:
        assert file_sha(stage / row['public_path']) == row['sha256']
        assert file_sha(row['original_path']) == row['sha256']
    for p in stage.rglob('*'):
        if not p.is_file():
            continue
        assert p.stat().st_size < 50 * 1024 * 1024, str(p)
        if p.suffix in ('.py', '.md', '.json', '.jsonl', '.csv', '.txt', '.log'):
            text = p.read_text(encoding='utf-8-sig')
            assert not re.search(r'(?:ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|sk-proj-[A-Za-z0-9_-]{30,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----)', text), str(p)
        if p.suffix == '.md':
            for target in re.findall(r'\]\(([^)]+)\)', p.read_text(encoding='utf-8')):
                if p.relative_to(stage).as_posix() == 'README.md' and target in historical_readme_links:
                    continue
                if re.match(r'^(?:https?://|mailto:|#|[A-Za-z]:)', target):
                    continue
                clean = target.split('#')[0].strip('<>')
                # Frozen original documents may contain historical missing links; new navigation may not.
                if p.name not in ('PUBLICATION_README_ko.md',) and p.relative_to(stage).as_posix() not in (
                        GROUP + '/README.md', 'README.md') and not str(p).endswith('report_ko.md'):
                    continue
                resolved = (p.parent / clean).resolve()
                try:
                    rel = resolved.relative_to(stage.resolve()).as_posix()
                except ValueError:
                    raise RuntimeError('Relative link leaves repository: ' + target)
                if resolved.exists() or rel in old or any(k.startswith(rel.rstrip('/') + '/') for k in old):
                    continue
                # Original 81/82 reports contain figure links only; they must resolve.
                raise RuntimeError('Missing link ' + str(p) + ': ' + target)


def push(publication):
    out = Path(publication).resolve()
    plan = read(out / 'publication_plan.json')
    if (out / 'PUSH_COMPLETE.json').exists():
        raise RuntimeError('Already published; no duplicate push')
    assert runtime_state() == plan['runtime_state_before']
    for name, key in plan['source_hashes'].items():
        assert file_sha(HERE / name) == key, 'Publication source changed: ' + name
    assert remote_head() == plan['base_commit'], 'Remote advanced; prepare a new publication, never force'
    bare = Path(plan['bare'])
    assert git(bare, 'rev-parse', plan['commit'] + '^{tree}').decode().strip() == plan['tree']
    git(bare, 'push', REMOTE, plan['commit'] + ':refs/heads/main')
    actual = remote_head()
    assert actual == plan['commit']
    assert runtime_state() == plan['runtime_state_before']
    receipt = dict(status='published', completed_at=utc(), commit=actual, remote=REMOTE,
                   fast_forward=True, remote_verified=True, runtime_head_index_readme_agents_preserved=True,
                   new_environment_steps=0, report81=plan['report81'], report82=plan['report82'])
    save(out / 'PUSH_COMPLETE.json', receipt)
    save(HERE / 'LATEST.json', dict(publication=str(out), **receipt))
    print(json.dumps(receipt, ensure_ascii=False), flush=True)


def record_external_push(publication, observed_remote_commit):
    """Save a receipt after separate approved native Git push and ls-remote calls."""
    out = Path(publication).resolve()
    plan = read(out / 'publication_plan.json')
    assert observed_remote_commit == plan['commit']
    assert runtime_state() == plan['runtime_state_before']
    for name, key in plan['source_hashes'].items():
        assert file_sha(HERE / name) == key
    parents = git(Path(plan['bare']), 'rev-list', '--parents', '-n', '1', plan['commit']).decode().split()
    assert parents == [plan['commit'], plan['base_commit']]
    receipt = dict(status='published', completed_at=utc(), commit=observed_remote_commit, remote=REMOTE,
                   fast_forward=True, remote_verified=True,
                   remote_verification='separate native git ls-remote; observed SHA supplied explicitly',
                   runtime_head_index_readme_agents_preserved=True, new_environment_steps=0,
                   report81=plan['report81'], report82=plan['report82'])
    save(out / 'PUSH_COMPLETE.json', receipt)
    save(HERE / 'LATEST.json', dict(publication=str(out), **receipt))
    print(json.dumps(receipt, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('--base-commit')
    p = sub.add_parser('push')
    p.add_argument('--publication', type=Path, required=True)
    record_parser = sub.add_parser('record-push')
    record_parser.add_argument('--publication', type=Path, required=True)
    record_parser.add_argument('--remote-commit', required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare(args.base_commit)
    elif args.command == 'push':
        push(args.publication)
    else:
        record_external_push(args.publication, args.remote_commit)
