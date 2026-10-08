"""Archive original experiment bytes, including Git-ignored research artifacts."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import uuid
import zipfile
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EXCLUDED_DIRS = {'.venv', '__pycache__', '.pytest_cache', '.git'}


def now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT).decode('utf-8').strip()


def files_under(directory):
    files = []
    for parent, directories, names in os.walk(directory, followlinks=False):
        for name in directories:
            if (Path(parent) / name).is_symlink():
                raise RuntimeError(f'Symlink is outside this archive contract: {name}')
        directories[:] = sorted(name for name in directories if name not in EXCLUDED_DIRS)
        for name in sorted(names):
            path = Path(parent) / name
            if name == 'worker.lock' or path.suffix in {'.pyc', '.pyo'}:
                continue
            if path.is_symlink():
                raise RuntimeError(f'Symlink is outside this archive contract: {path}')
            files.append(path)
    return sorted(files)


def main():
    config = json.loads((HERE / 'publication.json').read_text(encoding='utf-8'))
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output = HERE / 'results' / f'{stamp}_complete_archive_{uuid.uuid4().hex[:8]}'
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()

    def event(kind, **details):
        row = {'at': now(), 'event': kind, **details}
        with (output / 'archive_events.jsonl').open('a', encoding='utf-8', newline='\n') as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
        print(json.dumps(row, ensure_ascii=False), flush=True)

    try:
        snapshot = output / 'source_snapshot'
        snapshot.mkdir()
        archive_sources = sorted(p for p in HERE.iterdir() if p.is_file())
        for path in archive_sources:
            shutil.copy2(path, snapshot / path.name)
        source_hashes = {p.name: sha256(p) for p in archive_sources}
        write_json(output / 'run_started.json', {
            'created_at': now(), 'source_commit': git('rev-parse', 'HEAD'),
            'source_hashes': source_hashes, 'python': sys.version,
            'platform': platform.platform(), 'dependencies': 'Python standard library only',
            'additional_training_steps': 0, 'additional_evaluation_episodes': 0,
            'configuration': config,
        })
        root_names = git('ls-files', '-z').split('\0')
        root_files = sorted(ROOT / name for name in root_names if name and len(Path(name).parts) == 1)
        groups = [('00_repository_context', root_files + archive_sources)]
        groups += [(name, files_under(ROOT / name)) for name in config['experiment_directories']]
        total_bytes = sum(p.stat().st_size for _, paths in groups for p in paths)
        if shutil.disk_usage(output).free < total_bytes + 100_000_000:
            raise RuntimeError('Not enough free disk space for a conservative archive-size bound')
        event('started', output=str(output), file_count=sum(len(p) for _, p in groups), source_bytes=total_bytes)
        archives = []
        member_count = 0
        checkpoint_count = 0
        for name, paths in groups:
            event('packing', archive=name, file_count=len(paths))
            destination = output / f'{name}.zip'
            members = []
            with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
                for path in paths:
                    relative = path.relative_to(ROOT).as_posix()
                    before = path.stat()
                    digest = hashlib.sha256()
                    size = 0
                    with path.open('rb') as source, archive.open(relative, 'w', force_zip64=True) as target:
                        while chunk := source.read(1024 * 1024):
                            target.write(chunk)
                            digest.update(chunk)
                            size += len(chunk)
                    after = path.stat()
                    if size != before.st_size or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                        raise RuntimeError(f'Source changed during archive creation: {relative}')
                    members.append({'path': relative, 'bytes': size, 'sha256': digest.hexdigest()})
                    checkpoint_count += path.name == 'model.zip'
            with zipfile.ZipFile(destination) as archive:
                if archive.namelist() != [m['path'] for m in members]:
                    raise RuntimeError(f'ZIP member list mismatch: {name}')
                for member in members:
                    with archive.open(member['path']) as stream:
                        restored = hashlib.file_digest(stream, 'sha256').hexdigest()
                    if restored != member['sha256'] or sha256(ROOT / member['path']) != member['sha256']:
                        raise RuntimeError(f'Archive or source hash mismatch: {member["path"]}')
                    member_count += 1
            record = {
                'filename': destination.name, 'bytes': destination.stat().st_size,
                'sha256': sha256(destination), 'file_count': len(members),
                'uncompressed_bytes': sum(m['bytes'] for m in members), 'members': members,
            }
            if record['bytes'] >= 2 * 1024 ** 3:
                raise RuntimeError('An archive exceeds the selected single-release-asset size bound')
            archives.append(record)
            event('archive_verified', archive=destination.name, files=len(members), bytes=record['bytes'], sha256=record['sha256'])
        manifest = {
            'created_at': now(), 'status': 'verified', 'repository': config['repository'],
            'release_tag': config['tag'], 'source_commit': git('rev-parse', 'HEAD'),
            'archive_builder_source_hashes': source_hashes,
            'included': 'All files in experiment versions 01 through 04, including ignored checkpoints, replay, source snapshots, and failed runs; tracked root files and archive-builder sources.',
            'excluded': ['virtual environments', 'Python bytecode and caches', 'Git internal files', 'worker.lock runtime locks'],
            'file_count': member_count, 'uncompressed_bytes': total_bytes,
            'compressed_archive_bytes': sum(a['bytes'] for a in archives), 'archives': archives,
        }
        write_json(output / 'archive_manifest.json', manifest)
        verification = {
            'completed_at': now(), 'status': 'passed', 'files_verified': member_count,
            'archives_verified': len(archives), 'all_archived_members_sha256_match_original': True,
            'all_source_files_unchanged_after_packaging': True,
            'archive_source_snapshot_verified': all(sha256(snapshot / p.name) == source_hashes[p.name] for p in archive_sources),
            'elapsed_seconds': time.perf_counter() - started,
            'additional_training_steps': 0, 'additional_evaluation_episodes': 0,
            'runtime_checkpoint_model_files': checkpoint_count,
        }
        if not verification['archive_source_snapshot_verified']:
            raise RuntimeError('Archive builder snapshot mismatch')
        write_json(output / 'archive_verification.json', verification)
        event('completed', **verification)
        assets = [output / a['filename'] for a in archives]
        assets += [output / name for name in ['run_started.json', 'archive_manifest.json', 'archive_verification.json', 'archive_events.jsonl']]
        with (output / 'SHA256SUMS.txt').open('x', encoding='utf-8', newline='\n') as stream:
            for path in assets:
                stream.write(f'{sha256(path)}  {path.name}\n')
        print(f'ARCHIVE_RUN={output}', flush=True)
    except Exception as error:
        write_json(output / 'failure.json', {'failed_at': now(), 'type': type(error).__name__, 'message': str(error)})
        raise


if __name__ == '__main__':
    main()
