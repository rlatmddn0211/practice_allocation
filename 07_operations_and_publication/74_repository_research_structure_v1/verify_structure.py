"""Independent read-only audit of an organized Git tree and all recovery routes.

No prepare/restore implementation is imported, no checkout is materialized,
and no Git write, environment evaluation, or training command is executed.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import subprocess
import sys
import time
import traceback
from urllib.parse import unquote, urlsplit
import uuid


HERE = Path(__file__).resolve().parent
REPOSITORY = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], cwd=HERE).decode().strip()).resolve()
UNPUBLISHED = {61, 62, 63, 65, 69, 71, 72}
PILOT = 'LOCAL_PRACTICE_ALLOCATION_PILOT_DESIGN_20261007.md'
ROOT_EDIT_EXCEPTIONS = {'README.md', 'AGENTS.md', '.gitignore', '.gitattributes'}
REPO_URL = '/rlatmddn0211/practice_allocation/'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def blob_oid(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')


class Checks:
    def __init__(self):
        self.passed = 0
        self.categories = Counter()
        self.failed = []

    def need(self, value, label, detail=None):
        if not value:
            failure = {'check': label, 'detail': detail}
            self.failed.append(failure)
            raise AssertionError(label + (': ' + str(detail) if detail is not None else ''))
        self.passed += 1
        self.categories[label] += 1


class Git:
    def __init__(self, bare=None):
        self.prefix = ['git', '--git-dir=' + str(Path(bare).resolve())] if bare else ['git', '-C', str(REPOSITORY)]

    def call(self, *args, payload=None):
        return subprocess.check_output(self.prefix + list(args), input=payload)

    def tree(self, ref):
        result = {}
        for entry in self.call('ls-tree', '-r', '-z', ref).split(b'\0'):
            if not entry:
                continue
            metadata, path = entry.split(b'\t', 1)
            mode, kind, oid = metadata.decode('ascii').split()
            if kind != 'blob':
                raise ValueError('Unexpected submodule/non-blob entry: ' + path.decode('utf-8'))
            name = path.decode('utf-8')
            if name in result:
                raise ValueError('Duplicate tree path: ' + name)
            result[name] = {'mode': mode, 'oid': oid}
        return result

    def blobs(self, keys):
        keys = list(dict.fromkeys(keys))
        if not keys:
            return {}
        raw = self.call('cat-file', '--batch', payload=('\n'.join(keys) + '\n').encode('ascii'))
        cursor, result = 0, {}
        for expected in keys:
            end = raw.index(b'\n', cursor)
            fields = raw[cursor:end].decode('ascii').split()
            if len(fields) != 3 or fields[1] != 'blob':
                raise ValueError('Required blob is missing: ' + expected)
            actual, _, size = fields
            size = int(size)
            cursor = end + 1
            data = raw[cursor:cursor + size]
            cursor += size + 1
            if actual != expected or blob_oid(data) != expected:
                raise ValueError('Content does not hash to its Git blob identity: ' + expected)
            result[expected] = data
        return result

    def check_blob_existence(self, keys):
        keys = list(dict.fromkeys(keys))
        raw = self.call('cat-file', '--batch-check', payload=('\n'.join(keys) + '\n').encode('ascii'))
        lines = raw.decode('ascii').splitlines()
        if len(lines) != len(keys):
            raise ValueError('Incomplete object existence report.')
        for key, line in zip(keys, lines):
            fields = line.split()
            if len(fields) != 3 or fields[0] != key or fields[1] != 'blob' or not fields[2].isdigit():
                raise ValueError('Missing or non-blob object: ' + key)
        return len(keys)


def local_state():
    git = Git()
    return {'head': git.call('rev-parse', 'HEAD').decode('ascii').strip(),
            'index_sha256': hashlib.sha256(git.call('ls-files', '--stage', '-z')).hexdigest(),
            'README_sha256': sha(REPOSITORY / 'README.md'), 'AGENTS_sha256': sha(REPOSITORY / 'AGENTS.md')}


def dirs(paths):
    result = {'', '.'}
    for path in paths:
        parent = posixpath.dirname(path)
        while parent:
            result.add(parent)
            parent = posixpath.dirname(parent)
    return result


def mapped(path, mapping):
    first, slash, remainder = path.partition('/')
    return mapping.get(first, first) + (slash + remainder if slash else '')


def safe_relative(path):
    return bool(path) and not path.startswith('/') and '\\' not in path and '..' not in PurePosixPath(path).parts


def destinations(data):
    """Tokenize URL spans independently, including nested image-click links.

    A small state machine handles fenced/inline code and balanced parentheses;
    its implementation is independent of prepare.py's substitutions.
    """
    text = data.decode('utf-8')
    result, offset, fence_character, fence_length = [], 0, None, 0
    for line_number, line in enumerate(text.splitlines(keepends=True), 1):
        fence = re.match(r'^ {0,3}([`~])\1{2,}', line)
        if fence:
            run = fence.group(0).lstrip(' ')
            character = run[0]
            if fence_character is None:
                fence_character, fence_length = character, len(run)
            elif character == fence_character and len(run) >= fence_length and not line[fence.end():].strip():
                fence_character, fence_length = None, 0
            offset += len(line)
            continue
        if fence_character is not None:
            offset += len(line)
            continue
        allowed = [True] * len(line)
        position = 0
        while position < len(line):
            if line[position] != '`':
                position += 1
                continue
            end = position
            while end < len(line) and line[end] == '`':
                end += 1
            run = line[position:end]
            closing = line.find(run, end)
            if closing < 0:
                position = end
                continue
            for index in range(position, closing + len(run)):
                allowed[index] = False
            position = closing + len(run)

        spans = set()
        # Every ]( is inspected, so outer MP4 targets survive nested GIF syntax.
        for match in re.finditer(r'\]\(', line):
            if not allowed[match.start()]:
                continue
            start = match.end()
            while start < len(line) and line[start].isspace():
                start += 1
            if start >= len(line):
                continue
            if line[start] == '<':
                start += 1
                end = line.find('>', start)
                if end < 0:
                    continue
            else:
                end, depth = start, 0
                while end < len(line):
                    char = line[end]
                    if char == '\\' and end + 1 < len(line):
                        end += 2
                        continue
                    if char == '(':
                        depth += 1
                    elif char == ')':
                        if depth == 0:
                            break
                        depth -= 1
                    elif char.isspace() and depth == 0:
                        break
                    end += 1
            if start < end and all(allowed[start:end]):
                spans.add((start, end))
        for pattern in (r'\b(?:href|src|poster)\s*=\s*([\"\x27])([^\"\x27]+)\1',
                        r'^ {0,3}\[[^\]\n]+\]:\s*(?:<([^>]+)>|(\S+))'):
            for match in re.finditer(pattern, line, re.I):
                group = 2 if match.lastindex == 2 and pattern.startswith(r'\b') else (1 if match.group(1) is not None else 2)
                start, end = match.span(group)
                if start < end and all(allowed[start:end]):
                    spans.add((start, end))
        for start, end in sorted(spans):
            result.append({'start': offset + start, 'end': offset + end,
                           'url': line[start:end], 'line': line_number})
        offset += len(line)
    result.sort(key=lambda item: item['start'])
    for left, right in zip(result, result[1:]):
        if left['end'] > right['start']:
            raise ValueError('Overlapping Markdown URL spans.')
    return text, result


def non_url_segments(text, tokens):
    segments, start = [], 0
    for item in tokens:
        segments.append(text[start:item['start']])
        start = item['end']
    segments.append(text[start:])
    return segments


def link_kind(url, source):
    parsed = urlsplit(url)
    if parsed.netloc.lower() in ('github.com', 'www.github.com') and parsed.path.startswith(REPO_URL):
        remainder = parsed.path[len(REPO_URL):]
        match = re.match(r'(blob|tree)/main/(.*)', remainder)
        if match:
            return 'same_repo_main', posixpath.normpath(unquote(match.group(2))), parsed
    if parsed.scheme or parsed.netloc or not parsed.path or parsed.path.startswith('/'):
        return 'unchanged_external_or_anchor', None, parsed
    return 'relative', posixpath.normpath(posixpath.join(posixpath.dirname(source), unquote(parsed.path).replace('\\', '/'))), parsed


def verify_document(old_data, new_data, old_path, new_path, mapping, old_valid, new_valid, checks, statistics, missing):
    old_text, old_tokens = destinations(old_data)
    new_text, new_tokens = destinations(new_data)
    checks.need(non_url_segments(old_text, old_tokens) == non_url_segments(new_text, new_tokens),
                'Existing Markdown changed only URL destinations', old_path)
    checks.need(len(old_tokens) == len(new_tokens), 'Existing document link count retained', old_path)
    for old, new in zip(old_tokens, new_tokens):
        kind, old_target, old_uri = link_kind(old['url'], old_path)
        if kind == 'unchanged_external_or_anchor':
            checks.need(old['url'] == new['url'], 'External/fixed-commit/anchor URL unchanged', old_path)
            statistics['unchanged_external_fixed_or_anchor'] += 1
            continue
        if old_target not in old_valid:
            checks.need(old['url'] == new['url'], 'Pre-existing missing destination preserved', old_path)
            missing.append({'document': old_path, 'line': old['line'], 'target': old['url'], 'resolved_old': old_target})
            statistics['preexisting_missing'] += 1
            continue
        expected = mapped(old_target, mapping)
        new_kind, new_target, new_uri = link_kind(new['url'], new_path)
        checks.need(new_kind == kind and new_target == expected, 'Originally valid URL resolves to mapped target',
                    {'document': old_path, 'old': old['url'], 'new': new['url'], 'expected': expected})
        checks.need(expected in new_valid, 'Mapped link target exists in candidate Git tree', expected)
        checks.need(old_uri.query == new_uri.query and old_uri.fragment == new_uri.fragment,
                    'Link query and fragment preserved', old_path)
        statistics['originally_valid'] += 1
        statistics['corrected_destinations' if old['url'] != new['url'] else 'valid_destinations_unchanged'] += 1


def new_document_links(data, path, candidate_valid, checks, missing):
    _, tokens = destinations(data)
    for token in tokens:
        kind, target, _ = link_kind(token['url'], path)
        if kind in ('relative', 'same_repo_main'):
            if target not in candidate_valid:
                missing.append({'document': path, 'line': token['line'], 'url': token['url'], 'resolved': target})
            checks.need(target in candidate_valid, 'New navigation link has a candidate target',
                        {'document': path, 'url': token['url'], 'resolved': target})


def parser_contract_checks(checks):
    fixtures = (
        (b'[![sample](73/media/a.gif)](73/media/a.mp4)', ['73/media/a.gif', '73/media/a.mp4']),
        (b'````text\n```python\n[hidden](no.md)\n```\n````\n[visible](../README.md)', ['../README.md']),
        (b'`[hidden](no.md)` [visible](a%20b%23c.md?q=1#part)', ['a%20b%23c.md?q=1#part']),
        (b'[balanced](folder/a(b).md#part)', ['folder/a(b).md#part']),
        (b'[space](<with space.md>)\n[r]: <other%20space.md>', ['with space.md', 'other%20space.md']),
        (b'<img src="a.svg"><a href=\'b.md\' poster="c.jpg">', ['a.svg', 'b.md', 'c.jpg']),
    )
    for raw, expected in fixtures:
        checks.need([item['url'] for item in destinations(raw)[1]] == expected,
                    'Independent Markdown parser hand-calculated fixture', expected)
    mapping = {'01_x': 'group/01_x', '02_y': 'other/02_y'}
    old_valid = {'.', '02_y/data name#x.csv', '02_y/n.md'}
    new_valid = {'.', 'other/02_y/data name#x.csv', 'other/02_y/n.md'}
    old = (b'[local](../02_y/data%20name%23x.csv?q=1#part) [root](../) '
           b'[main](https://github.com/rlatmddn0211/practice_allocation/blob/main/02_y/n.md) '
           b'[fixed](https://github.com/rlatmddn0211/practice_allocation/blob/abcdef0/02_y/n.md)')
    new = (b'[local](../../other/02_y/data%20name%23x.csv?q=1#part) [root](../../) '
           b'[main](https://github.com/rlatmddn0211/practice_allocation/blob/main/other/02_y/n.md) '
           b'[fixed](https://github.com/rlatmddn0211/practice_allocation/blob/abcdef0/02_y/n.md)')
    verify_document(old, new, '01_x/README.md', 'group/01_x/README.md', mapping, old_valid,
                    new_valid, checks, Counter(), [])


def _audit(preparation, bare, tree, out, checks):
    plan = read(preparation / 'tree_plan.json')
    manifest = read(preparation / 'path_manifest.json')
    changes = read(preparation / 'document_link_changes.json')
    parser_contract_checks(checks)
    before = local_state()
    checks.need(before == plan['local_state_before'], 'Original local HEAD/index/README/AGENTS equal preparation baseline')
    checks.need(read(preparation / 'local_state_before.json') == before, 'Independent preparation local-state receipt agrees')
    local, remote = Git(), Git(bare)
    checks.need(remote.call('cat-file', '-t', tree).strip() == b'tree', 'Candidate object is a Git tree')
    original = local.tree(plan['base_commit'])
    candidate = remote.tree(tree)
    checks.need(plan['base_commit'] == manifest['base_commit'], 'Plan and recovery manifest share base commit')
    checks.need(len(original) == manifest['original_files'] == len(manifest['files']) == 31290, 'Exactly 31,290 published original files')
    file_rows = {row['old_path']: row for row in manifest['files']}
    checks.need(len(file_rows) == len(manifest['files']) and set(file_rows) == set(original), 'Recovery manifest covers original paths exactly once')
    mapping = manifest['folder_mapping']
    original_folders = {path.split('/')[0] for path in original if re.match(r'^\d{2}_', path)}
    groups = manifest['groups']
    group_names = {group['directory'] for group in groups}
    checks.need(len(original_folders) == manifest['original_version_folders'] == len(mapping) == 66, 'Exactly 66 original version folders')
    checks.need(len(group_names) == len(groups) == 8, 'Exactly eight distinct research groups')
    checks.need(set(mapping) == original_folders, 'Every old version folder has one mapping')
    assigned = [n for group in groups for n in group['numbers']]
    checks.need(len(assigned) == len(set(assigned)) == 66 and set(assigned) == {int(name[:2]) for name in original_folders}, 'Group number assignment is a bijection')
    for old_name, new_name in mapping.items():
        number = int(old_name[:2])
        group = next(group['directory'] for group in groups if number in group['numbers'])
        checks.need(new_name == group + '/' + old_name, 'Original version identifier retained under correct group', old_name)
        occurrences = {path.split('/')[0] for path in candidate if len(path.split('/')) >= 2 and path.split('/')[1] == old_name}
        checks.need(occurrences == {group}, 'Each original version appears under one top-level group', old_name)
    for path in candidate:
        checks.need(safe_relative(path), 'Candidate path is safe and relative', path)
        checks.need(not any(re.match(r'^\d{2}_', part) and int(part[:2]) in UNPUBLISHED for part in PurePosixPath(path).parts),
                    'Unpublished numbered versions excluded', path)
    checks.need({path.split('/')[0] for path in candidate if '/' in path} == group_names, 'Candidate has exactly the eight expected top-level directories')

    # Reconstruct the publisher's explicit file allowlist using independent blob hashing.
    expected = {path: dict(entry) for path, entry in plan['entries'].items()}
    expected_content_keys = set(plan['modified_files']) | set(plan['new_files'])
    checks.need(set(plan['content_sha256']) == expected_content_keys,
                'Content SHA256 allowlist covers exactly every modified and new file')
    for path, source in plan['modified_files'].items():
        checks.need(path in expected and Path(source).resolve().is_relative_to(preparation), 'Modification comes from the pinned preparation output', path)
        checks.need(sha(source) == plan['content_sha256'][path], 'Modified file matches independent preparation SHA256 ledger', path)
        expected[path] = {'mode': expected[path]['mode'], 'oid': blob_oid(Path(source).read_bytes())}
    for path, source in plan['new_files'].items():
        checks.need(path not in expected, 'New generated file does not overwrite an original/archive path', path)
        checks.need(Path(source).resolve().is_relative_to(preparation), 'New file comes from immutable preparation snapshots', path)
        checks.need(sha(source) == plan['content_sha256'][path], 'New file matches independent preparation SHA256 ledger', path)
        expected[path] = {'mode': '100644', 'oid': blob_oid(Path(source).read_bytes())}
    checks.need(set(candidate) == set(expected), 'Candidate file set equals tree_plan allowlist',
                {'missing': sorted(set(expected) - set(candidate))[:20], 'extra': sorted(set(candidate) - set(expected))[:20]})
    for path in expected:
        checks.need(candidate[path] == expected[path], 'Planned candidate blob and mode exact', path)

    restored_routes, modified_originals, unchanged_originals = [], [], 0
    categories = Counter()
    original_mapped_paths = set()
    for old_path, item in original.items():
        row = file_rows[old_path]
        new_path = mapped(old_path, mapping)
        original_mapped_paths.add(new_path)
        checks.need(row['mode'] == item['mode'] and row['old_oid'] == item['oid'] and row['new_path'] == new_path,
                    'Manifest old identity and destination independently match Git', old_path)
        checks.need(candidate[new_path]['mode'] == item['mode'], 'Original file mode retained', old_path)
        if candidate[new_path]['oid'] != item['oid']:
            checks.need(old_path.endswith('.md') or old_path in ROOT_EDIT_EXCEPTIONS, 'Only Markdown/root navigation metadata may change', old_path)
            checks.need(bool(row.get('original_archive')), 'Every modified original has an exact recovery archive', old_path)
            modified_originals.append(old_path)
        else:
            unchanged_originals += 1
        route = row.get('original_archive') or new_path
        checks.need(route in candidate and candidate[route]['oid'] == item['oid'], 'Original bytes recoverable through exact Git blob route', old_path)
        checks.need(candidate[route]['mode'] == item['mode'], 'Recovery route retains original Git mode', old_path)
        restored_routes.append({'old_path': old_path, 'route': route, 'mode': item['mode'], 'blob': item['oid']})
        categories['markdown' if old_path.endswith('.md') else 'root_metadata' if old_path in ROOT_EDIT_EXCEPTIONS else 'non_document_code_data_media'] += 1
    checks.need(len({row['new_path'] for row in manifest['files']}) == 31290, 'No original destination collision')
    checks.need(candidate[PILOT] == original[PILOT], 'Root pilot design byte/mode identical')
    unique_restore_objects = remote.check_blob_existence(row['blob'] for row in restored_routes)
    checks.need(unique_restore_objects > 0, 'Every restoration-route blob exists without materializing a checkout')

    old_md = {path: item for path, item in original.items() if path.endswith('.md')}
    old_blobs = local.blobs(item['oid'] for item in old_md.values())
    new_md = {path: item for path, item in candidate.items() if path.endswith('.md')}
    new_blobs = remote.blobs(item['oid'] for item in new_md.values())
    old_valid, candidate_valid = set(original) | dirs(original), set(candidate) | dirs(candidate)
    statistics, missing, new_missing = Counter(), [], []
    # Scientific/report text must remain exact except the path tokens themselves.
    for old_path, item in old_md.items():
        if old_path in ('README.md', 'AGENTS.md', PILOT):
            continue
        new_path = mapped(old_path, mapping)
        verify_document(old_blobs[item['oid']], new_blobs[candidate[new_path]['oid']], old_path, new_path,
                        mapping, old_valid, candidate_valid, checks, statistics, missing)
    old_root, new_root = old_blobs[original['README.md']['oid']], new_blobs[candidate['README.md']['oid']]
    video_pattern = rb'<!-- retention-video-publication:start -->[\s\S]*?<!-- retention-video-publication:end -->'
    old_video, new_video = re.search(video_pattern, old_root), re.search(video_pattern, new_root)
    checks.need(old_video is not None and new_video is not None, 'Original C/D video section retained')
    verify_document(old_video.group(0), new_video.group(0), 'README.md', 'README.md', mapping, old_valid,
                    candidate_valid, checks, statistics, missing)
    _, root_tokens = destinations(new_root)
    media = []
    for token in root_tokens:
        kind, target, _ = link_kind(token['url'], 'README.md')
        if kind == 'relative' and target.endswith(('.gif', '.mp4')):
            checks.need(target in candidate, 'Root C/D media blob exists', target)
            checks.need(target.startswith(mapping['73_retention_readme_video_publication_v1'] + '/'), 'Root media points into the relocated version73', target)
            media.append(target)
    checks.need(len({path for path in media if path.endswith('.gif')}) == 8, 'Eight unique C/D GIF assets linked from root')
    checks.need(len({path for path in media if path.endswith('.mp4')}) == 8, 'Eight unique C/D MP4 assets linked from root')
    new_agents = new_blobs[candidate['AGENTS.md']['oid']]
    checks.need(new_agents.startswith(old_blobs[original['AGENTS.md']['oid']]), 'Historical AGENTS instructions retained as exact prefix')
    for path, item in new_md.items():
        if path not in original_mapped_paths or path == 'README.md':
            new_document_links(new_blobs[item['oid']], path, candidate_valid, checks, new_missing)
    required_docs = {name + '/README.md' for name in group_names} | {'00_research_overview/RESEARCH_TRAJECTORY.md'}
    checks.need(required_docs <= set(candidate), 'Every group index and research trajectory is present')
    for change in changes['changes']:
        row = file_rows[change['old_path']]
        checks.need(change['old_oid'] == original[change['old_path']]['oid'] and change['new_oid'] == candidate[row['new_path']]['oid'],
                    'Document-change receipt matches independently read blobs', change['old_path'])
        checks.need(change['original_archive'] == row.get('original_archive'), 'Document recovery route matches manifest', change['old_path'])
    after = local_state()
    checks.need(after == before == plan['local_state_before'], 'Local HEAD/index/README/AGENTS unchanged after independent verification')
    write(out / 'original_recovery_routes.json', {'base_commit': plan['base_commit'], 'files': restored_routes,
          'unique_blob_objects': unique_restore_objects, 'actual_checkout_or_large_copy_performed': False})
    write(out / 'existing_missing_links.json', {'count': len(missing), 'links': missing,
          'scope': 'Original non-root Markdown plus preserved video block; old root index/pilot/AGENTS are separately accounted for below',
          'root_pilot_preexisting_missing': [{'target': token['url'], 'resolved': target}
              for token in destinations(old_blobs[original[PILOT]['oid']])[1]
              for kind, target, _ in [link_kind(token['url'], PILOT)] if kind == 'relative' and target not in old_valid]})
    write(out / 'new_navigation_links.json', {'missing': new_missing, 'root_media_targets': media,
          'group_indexes': sorted(required_docs), 'link_statistics': dict(statistics)})
    return {'passed': True, 'tree': tree, 'base_commit': plan['base_commit'], 'bare': str(Path(bare).resolve()),
            'original_files': 31290, 'candidate_files': len(candidate), 'original_version_folders': 66, 'groups': 8,
            'unchanged_original_files': unchanged_originals, 'modified_original_files': len(modified_originals),
            'modified_original_paths': modified_originals, 'original_file_categories': dict(categories),
            'all_original_recovery_routes_verified': True, 'recovery_files': len(restored_routes),
            'original_blob_objects_verified_present': unique_restore_objects,
            'code_data_media_original_blobs_and_modes_unchanged': True,
            'originally_valid_links_verified': statistics['originally_valid'], 'link_statistics': dict(statistics),
            'preexisting_missing_links_separately_recorded': len(missing), 'new_navigation_missing_links': len(new_missing),
            'root_gif_assets': 8, 'root_mp4_assets': 8, 'unpublished_versions_excluded': sorted(UNPUBLISHED),
            'local_state_before': before, 'local_state_after': after,
            'new_environment_steps': 0, 'SAC_updates': 0, 'policy_evaluations': 0, 'git_write_commands': 0,
            'large_checkout_or_restore_copy_performed': False, 'scientific_effect_test': False}


def run(preparation, bare, tree, output_parent=None):
    started = time.perf_counter()
    preparation = Path(preparation).resolve()
    parent = Path(output_parent).resolve() if output_parent else HERE / 'results'
    parent.mkdir(parents=True, exist_ok=True)
    out = parent / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_verify_structure_' + uuid.uuid4().hex[:8])
    out.mkdir()
    checks, inputs, source_hashes = Checks(), [], {}
    try:
        snapshots = out / 'source_snapshot'
        snapshots.mkdir()
        for source in HERE.iterdir():
            if source.is_file() and (source.suffix in ('.py', '.md', '.json') or source.name == '.gitignore'):
                shutil.copy2(source, snapshots / source.name)
                source_hashes[source.name] = sha(source)
        write(out / 'source_hashes.json', source_hashes)
        target = out / 'input_snapshot'
        target.mkdir()
        for name in ('tree_plan.json', 'path_manifest.json', 'document_link_changes.json', 'local_state_before.json', 'summary.json', 'COMPLETE.json'):
            source = preparation / name
            digest = sha(source)
            shutil.copy2(source, target / name)
            inputs.append({'path': str(source), 'sha256': digest, 'snapshot': str((target / name).relative_to(out))})
        write(out / 'request.json', {'preparation': str(preparation), 'bare': str(Path(bare).resolve()), 'tree': tree,
              'argv': sys.argv, 'read_only_git_commands': ['rev-parse', 'ls-files', 'ls-tree', 'cat-file', '--version'],
              'new_environment_steps': 0, 'git_write_commands': 0})
        result = _audit(preparation, bare, tree, out, checks)
        checks.need(all(sha(item['path']) == item['sha256'] for item in inputs), 'Preparation inputs unchanged during verification')
        checks.need(all(sha(HERE / name) == digest for name, digest in source_hashes.items()), 'Verifier/tool sources unchanged during verification')
        result.update({'checks_passed': checks.passed, 'wall_seconds': time.perf_counter() - started,
                       'python': sys.version, 'git_version': Git().call('--version').decode().strip()})
        write(out / 'verification.json', result)
        write(out / 'summary.json', result)
        write(out / 'input_receipt.json', inputs)
        write(out / 'checks.json', {'passed': checks.passed, 'categories': dict(checks.categories), 'failed': checks.failed})
        write(out / 'COMPLETE.json', {'passed': True, 'tree': tree, 'verification_sha256': sha(out / 'verification.json'), 'checks_passed': checks.passed})
        return out
    except BaseException as exc:
        write(out / 'input_receipt.json', inputs)
        write(out / 'checks.json', {'passed': checks.passed, 'categories': dict(checks.categories), 'failed': checks.failed})
        write(out / 'verification.json', {'passed': False, 'tree': tree, 'type': type(exc).__name__, 'message': str(exc),
              'traceback': traceback.format_exc(), 'checks_passed': checks.passed, 'new_environment_steps': 0, 'git_write_commands': 0})
        write(out / 'FAILED.json', {'passed': False, 'tree': tree, 'type': type(exc).__name__, 'message': str(exc),
              'traceback': traceback.format_exc(), 'checks_passed': checks.passed, 'new_environment_steps': 0})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preparation', required=True)
    parser.add_argument('--bare', required=True)
    parser.add_argument('--tree', required=True)
    parser.add_argument('--output-parent')
    args = parser.parse_args()
    output = run(args.preparation, args.bare, args.tree, args.output_parent)
    print(json.dumps({'verification_dir': str(output), 'checks_passed': read(output / 'verification.json')['checks_passed'],
                      'passed': True, 'tree': args.tree}), flush=True)
