"""Immutable E0-E2 export, including full checkpoints and their evaluated parents."""
from __future__ import annotations

import csv
import hashlib
import json
import platform
import shutil
import subprocess
import time
import traceback
import uuid
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CONFIG = json.loads((HERE / 'publication.json').read_text(encoding='utf-8'))
STAGES = {'E0': '09_fresh_evaluation_audit_v1', 'E1': '10_independent_seed_checkpoint_study_v1', 'E2': '11_fixed_target_donor_swap_v1'}


def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def save(p, value):
    with p.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')


def main():
    start = time.perf_counter()
    run = HERE / 'results' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_archive_') + uuid.uuid4().hex[:8])
    run.mkdir(parents=True, exist_ok=False)
    snap = run / 'source_snapshot'
    snap.mkdir()
    for p in [Path(__file__), HERE/'github_release.py', HERE/'publication.json']:
        shutil.copy2(p, snap/p.name)
    hashes = {}
    checks = []

    def check(name, passed):
        checks.append({'name': name, 'passed': bool(passed)})
        if not passed:
            raise AssertionError(name)

    def read(p):
        hashes[str(p)] = sha(p)
        return json.loads(p.read_text(encoding='utf-8'))

    try:
        active = read(ROOT/'13_e0_e3_autonomous_queue_v1/ACTIVE_CAMPAIGN.json')
        campaign = Path(active['campaign'])
        runs_root = campaign.parents[2]
        plan = read(campaign/'plan.json')
        markers = sorted((campaign/'completed').glob('E[012]_*.json'))
        check('592_completed_E0_E2_jobs', len(markers) == 592)
        groups = {s: set() for s in STAGES}
        groups['E0_parent_checkpoints'] = set()
        groups['queue_provenance'] = {campaign/'plan.json', campaign/'plan_integrity.json'}
        groups['queue_provenance'].update(p for p in (campaign/'source_snapshot').rglob('*') if p.is_file())
        records = []
        episode_sources = []
        costs = []
        checkpoint_refs = {}
        expected_hashes = {}
        for marker_path in markers:
            marker = read(marker_path)
            path = Path(marker['result_ref']['path'])
            rec = read(path)
            check('result_'+rec['id'], hashes[str(path)] == marker['result_ref']['sha256'])
            records.append(rec)
            cost = read(path.parent/'costs.json')
            costs.append({'id': rec['id'], 'stage': rec['stage'], **cost})
            req = read(path.parent/'request.json')
            groups['queue_provenance'].add(marker_path)
            attempt_dir = campaign/'attempts'/rec['id']
            if attempt_dir.exists():
                groups['queue_provenance'].update(p for p in attempt_dir.rglob('*') if p.is_file())
            if rec['kind'] == 'evaluate':
                ep = Path(rec['episodes_path'])
                check('episodes_'+rec['id'], sha(ep) == rec['episodes_sha256'])
                episode_sources.append((rec, ep))
            if 'checkpoint' in rec:
                checkpoint_refs[Path(rec['checkpoint']['path'])] = rec['checkpoint']['manifest_sha256']
            if rec['stage'] == 'E0' and 'parent' in req:
                parent = Path(req['parent']['path'])
                checkpoint_refs[parent] = req['parent']['manifest_sha256']
                groups['E0_parent_checkpoints'].update(p for p in parent.rglob('*') if p.is_file())
            # Original bank definitions needed to reproduce exclusion checks.
            for bank in req.get('all_banks', []):
                b = Path(bank['path'])
                if b.is_relative_to(ROOT):
                    groups['E0_parent_checkpoints'].add(b)
                    expected_hashes[b] = bank['sha256']

        for stage, folder in STAGES.items():
            source = runs_root/folder
            groups[stage].update(p for p in source.rglob('*') if p.is_file())
        for checkpoint, expected in checkpoint_refs.items():
            manifest_path = checkpoint/'checkpoint_manifest.json'
            manifest = read(manifest_path)
            check('checkpoint_manifest_'+str(checkpoint), sha(manifest_path) == expected)
            for name, wanted in manifest['files'].items():
                expected_hashes[checkpoint/name] = wanted

        def member(p):
            if p.is_relative_to(runs_root):
                return 'runs/'+p.relative_to(runs_root).as_posix()
            if p.is_relative_to(ROOT):
                return 'workspace/'+p.relative_to(ROOT).as_posix()
            raise ValueError('Unexpected export source outside approved roots')

        excluded = []
        inventory = []
        assets = []
        for group, paths in groups.items():
            accepted = []
            for p in sorted(paths):
                if any(x in p.parts for x in ['__pycache__', '.git', '.venv', 'node_modules']) or p.name.endswith('.lock'):
                    excluded.append(str(p))
                else:
                    accepted.append(p)
            target = run/(group+'.zip')
            print(json.dumps({'event': 'archive_start', 'group': group, 'files': len(accepted)}), flush=True)
            local = []
            with zipfile.ZipFile(target, 'x', allowZip64=True) as z:
                for p in accepted:
                    h = sha(p)
                    if p in expected_hashes:
                        check('checkpoint_member_'+str(p), h == expected_hashes[p])
                    compression = zipfile.ZIP_STORED if p.suffix in ['.zip', '.xz', '.npz'] else zipfile.ZIP_DEFLATED
                    name = member(p)
                    z.write(p, name, compress_type=compression, compresslevel=1)
                    local.append({'asset': target.name, 'path': name, 'original_path': str(p), 'bytes': p.stat().st_size, 'sha256': h})
            with zipfile.ZipFile(target) as z:
                check('unique_members_'+group, len(set(z.namelist())) == len(local))
                for row in local:
                    with z.open(row['path']) as f:
                        actual = hashlib.file_digest(f, 'sha256').hexdigest()
                    check('zip_member_'+row['path'], actual == row['sha256'])
            check('github_asset_under_2GiB_'+group, target.stat().st_size < 2**31)
            inventory.extend(local)
            assets.append({'name': target.name, 'bytes': target.stat().st_size, 'sha256': sha(target), 'files': len(local)})
            print(json.dumps({'event': 'archive_verified', **assets[-1]}), flush=True)
        check('all_checkpoint_files_exported', set(expected_hashes) <= {Path(r['original_path']) for r in inventory})

        portable = run/'portable_data'
        portable.mkdir()
        save(portable/'completed_results.json', records)
        save(portable/'completed_job_costs.json', costs)
        episode_count = 0
        with (portable/'evaluation_episodes.csv').open('x', encoding='utf-8', newline='') as dest:
            writer = None
            for rec, source in episode_sources:
                with source.open(encoding='utf-8', newline='') as f:
                    reader = csv.DictReader(f)
                    prefix = {'job_id': rec['id'], 'stage': rec['stage'], 'original_seed': rec['original_seed'],
                              'role': rec['role'], 'checkpoint_step': rec.get('checkpoint_step'),
                              'continuation_label': rec.get('continuation_label'), 'allocation': rec.get('allocation'),
                              'horizon': rec.get('horizon')}
                    fields = list(prefix) + list(reader.fieldnames)
                    if writer is None:
                        writer = csv.DictWriter(dest, fieldnames=fields)
                        writer.writeheader()
                    check('episode_schema_'+rec['id'], fields == writer.fieldnames)
                    count = 0
                    successes = Counter()
                    steps = 0
                    for row in reader:
                        writer.writerow({**prefix, **row})
                        count += 1
                        successes[row['task']] += int(row['success'])
                        steps += int(row['length'])
                    check('episode_count_'+rec['id'], count == rec['evaluation']['episodes'])
                    check('success_counts_'+rec['id'], dict(successes) == rec['evaluation']['success_counts'])
                    check('evaluation_cost_'+rec['id'], steps == rec['evaluation']['environment_steps'])
                    episode_count += count
        check('112800_exported_evaluation_episodes', episode_count == 112800)
        source_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        manifest = {'status': 'verified', 'repository': CONFIG['repository'], 'release_tag': CONFIG['tag'],
                    'source_commit': source_commit, 'created_at': datetime.now(timezone.utc).isoformat(),
                    'scope': 'All files in D-drive E0-E2 stage directories including failed attempts; scoped queue provenance; the 26 original full checkpoints evaluated by E0 and referenced original banks.',
                    'not_included': ['E3 results and live queue status/locks', 'venvs and Python caches', 'Unreferenced earlier checkpoints already covered by prior release or earlier local runs'],
                    'immutable_original_records': True, 'path_mapping': {'workspace/': str(ROOT), 'runs/': str(runs_root)},
                    'completed_jobs': len(records), 'evaluation_episodes': episode_count, 'referenced_full_checkpoints': len(checkpoint_refs),
                    'files': inventory, 'assets': assets, 'excluded_paths': excluded,
                    'portable_data': [{'name': p.relative_to(run).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)} for p in sorted(portable.iterdir())],
                    'checks_passed': len(checks), 'new_training_steps': 0, 'new_evaluation_episodes': 0,
                    'archive_wall_seconds': time.perf_counter()-start, 'python': platform.python_version(),
                    'dependencies': 'Python standard library only', 'source_sha256': sha(Path(__file__))}
        save(run/'archive_manifest.json', manifest)
        save(run/'input_hashes.json', hashes)
        save(run/'verification.json', {'status': 'passed', 'checks': checks})
        with (run/'SHA256SUMS.txt').open('x', encoding='utf-8', newline='\n') as f:
            for a in assets:
                f.write(a['sha256']+'  '+a['name']+'\n')
            f.write(sha(run/'archive_manifest.json')+'  archive_manifest.json\n')
        print(json.dumps({'status': 'verified', 'run': str(run), 'assets': assets, 'files': len(inventory),
                          'full_checkpoints': len(checkpoint_refs), 'checks_passed': len(checks)}, indent=2))
    except Exception:
        save(run/'failure.json', {'traceback': traceback.format_exc(), 'checks': checks})
        raise


if __name__ == '__main__':
    main()
