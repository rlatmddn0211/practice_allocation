"""Publish verified artifacts to the configured repository without logging credentials."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import http.client
import json
import mimetypes
import os
from pathlib import Path
import shutil
import subprocess
from urllib.parse import quote, urlencode, urlsplit
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CONFIG = json.loads((HERE / 'publication.json').read_text(encoding='utf-8'))
REPO_PATH = '/repos/' + CONFIG['repository']


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def credentials():
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='Never')
    result = subprocess.run(
        ['git', '-c', 'credential.interactive=false', 'credential', 'fill'],
        input=f'protocol=https\nhost=github.com\npath={CONFIG["repository"]}.git\n\n',
        text=True, capture_output=True, cwd=ROOT, env=env,
    )
    if result.returncode:
        raise RuntimeError('Stored GitHub credential could not be obtained; credential output was suppressed')
    fields = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    if not fields.get('password'):
        raise RuntimeError('Git credential helper did not return a GitHub credential')
    return fields['password']


class GitHub:
    def __init__(self, token):
        self.token = token

    def headers(self):
        return {'Authorization': 'Bearer ' + self.token, 'Accept': 'application/vnd.github+json',
                'X-GitHub-Api-Version': '2026-03-10', 'User-Agent': 'practice-allocation-results-archive-v1'}

    def request(self, method, path, data=None):
        if not path.startswith(REPO_PATH):
            raise RuntimeError('API request is outside the configured repository')
        conn = http.client.HTTPSConnection('api.github.com', timeout=60)
        try:
            headers = self.headers()
            body = None if data is None else json.dumps(data, ensure_ascii=False).encode('utf-8')
            if body is not None:
                headers['Content-Type'] = 'application/json'
            conn.request(method, path, body=body, headers=headers)
            response = conn.getresponse()
            raw = response.read()
            if response.status >= 400:
                raise RuntimeError(f'GitHub API {method} returned HTTP {response.status} for {path.split("?")[0]}')
            return json.loads(raw) if raw else None
        finally:
            conn.close()

    def upload(self, upload_url, path, emit):
        parsed = urlsplit(upload_url.split('{', 1)[0])
        if parsed.scheme != 'https' or parsed.hostname != 'uploads.github.com' or not parsed.path.startswith(REPO_PATH + '/releases/'):
            raise RuntimeError('Unexpected release upload endpoint')
        conn = http.client.HTTPSConnection(parsed.hostname, timeout=60)
        try:
            target = parsed.path + '?' + urlencode({'name': path.name})
            conn.putrequest('POST', target)
            headers = self.headers()
            headers.update({'Content-Type': mimetypes.guess_type(path.name)[0] or 'application/octet-stream', 'Content-Length': str(path.stat().st_size)})
            for key, value in headers.items():
                conn.putheader(key, value)
            conn.endheaders()
            sent = 0
            with path.open('rb') as stream:
                while chunk := stream.read(1024 * 1024):
                    conn.send(chunk)
                    sent += len(chunk)
                    if sent % (32 * 1024 * 1024) == 0:
                        emit('upload_progress', asset=path.name, sent_bytes=sent, total_bytes=path.stat().st_size)
            response = conn.getresponse()
            body = response.read()
            if response.status != 201:
                raise RuntimeError(f'GitHub asset upload returned HTTP {response.status}: {path.name}')
            return json.loads(body)
        finally:
            conn.close()


def matched(asset, local):
    return asset['state'] == 'uploaded' and asset['size'] == local['bytes'] and asset.get('digest') == 'sha256:' + local['sha256']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['inspect', 'publish'])
    parser.add_argument('--archive-run', type=Path)
    parser.add_argument('--target-commit')
    args = parser.parse_args()
    api = GitHub(credentials())
    if args.command == 'inspect':
        repo = api.request('GET', REPO_PATH)
        releases = api.request('GET', REPO_PATH + '/releases?per_page=100')
        print(json.dumps({'repository': repo['full_name'], 'visibility': repo['visibility'],
                          'can_push': repo.get('permissions', {}).get('push'),
                          'releases': [{'id': r['id'], 'tag': r['tag_name'], 'draft': r['draft']} for r in releases]}, indent=2))
        return
    if args.archive_run is None or not args.target_commit:
        parser.error('publish requires --archive-run and --target-commit')
    archive_run = args.archive_run.resolve()
    archive_run.relative_to(HERE / 'results')
    manifest = json.loads((archive_run / 'archive_manifest.json').read_text(encoding='utf-8'))
    assert manifest['status'] == 'verified' and manifest['repository'] == CONFIG['repository']
    assert manifest['release_tag'] == CONFIG['tag']
    expected = []
    for line in (archive_run / 'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
        digest, name = line.split('  ', 1)
        if Path(name).name != name:
            raise RuntimeError('Invalid asset filename')
        path = archive_run / name
        if sha256(path) != digest:
            raise RuntimeError(f'Local asset hash mismatch: {name}')
        expected.append({'name': name, 'bytes': path.stat().st_size, 'sha256': digest})
    checksums = archive_run / 'SHA256SUMS.txt'
    expected.append({'name': checksums.name, 'bytes': checksums.stat().st_size, 'sha256': sha256(checksums)})
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output = HERE / 'results' / f'{stamp}_github_publication_{uuid.uuid4().hex[:8]}'
    output.mkdir(parents=True, exist_ok=False)
    snapshot = output / 'source_snapshot'
    snapshot.mkdir()
    for path in [Path(__file__), HERE / 'publication.json']:
        shutil.copy2(path, snapshot / path.name)

    def emit(event, **details):
        row = {'at': datetime.now(timezone.utc).isoformat(), 'event': event, **details}
        with (output / 'events.jsonl').open('a', encoding='utf-8', newline='\n') as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
        print(json.dumps(row, ensure_ascii=False), flush=True)

    def save(name, value):
        with (output / name).open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')

    try:
        save('run_started.json', {'archive_run': str(archive_run), 'target_commit': args.target_commit,
                                 'uploader_sha256': sha256(Path(__file__)), 'configuration_sha256': sha256(HERE / 'publication.json'),
                                 'configuration': CONFIG, 'assets': expected, 'training_steps': 0, 'evaluation_episodes': 0})
        remote = api.request('GET', REPO_PATH + '/git/ref/heads/main')
        if remote['object']['sha'] != args.target_commit:
            raise RuntimeError('Target commit must match current remote main; no remote code changes are made by this tool')
        notes = (HERE / 'release_notes.md').read_text(encoding='utf-8')
        releases = api.request('GET', REPO_PATH + '/releases?per_page=100')
        matches = [r for r in releases if r['tag_name'] == CONFIG['tag']]
        if len(matches) > 1:
            raise RuntimeError('Ambiguous existing release')
        if matches:
            release = matches[0]
            if release['target_commitish'] != args.target_commit or release['name'] != CONFIG['title'] or release['body'] != notes:
                raise RuntimeError('Existing release does not match this publication; it will not be overwritten')
        else:
            release = api.request('POST', REPO_PATH + '/releases', {
                'tag_name': CONFIG['tag'], 'target_commitish': args.target_commit,
                'name': CONFIG['title'], 'body': notes, 'draft': True, 'prerelease': False,
                'generate_release_notes': False,
            })
        emit('release_ready', release_id=release['id'], draft=release['draft'])
        assets_path = REPO_PATH + f'/releases/{release["id"]}/assets?per_page=100'
        existing = {a['name']: a for a in api.request('GET', assets_path)}
        if set(existing) - {a['name'] for a in expected}:
            raise RuntimeError('Existing release contains unexpected assets; no changes were made to them')
        for item in expected:
            if item['name'] in existing:
                asset = existing[item['name']]
                if not matched(asset, item):
                    raise RuntimeError(f'Existing asset differs: {item["name"]}; it will not be overwritten')
            else:
                if not release['draft']:
                    raise RuntimeError('Published release is incomplete; this tool only adds assets to its draft')
                emit('upload_started', asset=item['name'], bytes=item['bytes'])
                asset = api.upload(release['upload_url'], archive_run / item['name'], emit)
                if not matched(asset, item):
                    raise RuntimeError(f'Server SHA-256 verification failed: {item["name"]}')
            emit('asset_verified', name=item['name'], asset_id=asset['id'], digest=asset['digest'], bytes=asset['size'])
        verified = api.request('GET', assets_path)
        lookup = {a['name']: a for a in verified}
        if set(lookup) != {a['name'] for a in expected} or not all(matched(lookup[a['name']], a) for a in expected):
            raise RuntimeError('Final draft asset verification failed')
        if release['draft']:
            release = api.request('PATCH', REPO_PATH + f'/releases/{release["id"]}', {'draft': False, 'make_latest': 'true'})
        public = api.request('GET', REPO_PATH + '/releases/tags/' + quote(CONFIG['tag'], safe=''))
        if public['draft'] or public['id'] != release['id']:
            raise RuntimeError('Published release verification failed')
        save('publication_receipt.json', {
            'status': 'published_and_verified', 'completed_at': datetime.now(timezone.utc).isoformat(),
            'url': public['html_url'], 'release_id': public['id'], 'tag': public['tag_name'],
            'target_commit': args.target_commit, 'experiment_source_commit': manifest['source_commit'],
            'archive_manifest_sha256': sha256(archive_run / 'archive_manifest.json'),
            'all_asset_sha256_verified_with_github': True, 'asset_count': len(expected),
            'total_asset_bytes': sum(a['bytes'] for a in expected),
            'assets': [{k: a[k] for k in ['id', 'name', 'size', 'digest', 'browser_download_url']} for a in verified],
        })
        emit('published', url=public['html_url'], assets=len(expected), receipt=str(output / 'publication_receipt.json'))
    except Exception as error:
        save('failure.json', {'type': type(error).__name__, 'message': str(error)})
        raise


if __name__ == '__main__':
    main()
