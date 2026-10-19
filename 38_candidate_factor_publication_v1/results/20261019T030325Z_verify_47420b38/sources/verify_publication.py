"""Check publication bytes, live document links, and headline evidence before push."""
import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import traceback
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def save(path, value):
    with path.open('x', encoding='utf-8') as f:
        json.dump(value, f, indent=2, ensure_ascii=False)
        f.write('\n')


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, check=True, capture_output=True).stdout


def main():
    start, cpu = time.perf_counter(), time.process_time()
    out = HERE/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_verify_'+uuid.uuid4().hex[:8])
    out.mkdir(parents=True)
    print(out, flush=True)
    (out/'sources').mkdir()
    source_hashes = {}
    for p in [*HERE.glob('*.py'), HERE/'protocol.json']:
        shutil.copy2(p, out/'sources'/p.name)
        source_hashes[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    save(out/'source_hashes.json', source_hashes)
    save(out/'runtime.json', {'python': sys.version, 'argv': sys.argv,
        'dependencies': 'Python standard library and Git', 'git_version': git('--version').decode().strip()})
    checks, inputs, summary = [], {}, {'status': 'failed'}

    def check(label, value):
        checks.append({'check': label, 'passed': bool(value)})
        if not value:
            raise AssertionError(label)

    def pin(p):
        data = p.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        inputs[p.relative_to(ROOT).as_posix()] = digest
        snapshot = out/'inputs'/(digest+p.suffix)
        if not snapshot.exists():
            snapshot.parent.mkdir(exist_ok=True)
            with snapshot.open('xb') as f:
                f.write(data)
        return data.decode('utf-8-sig')

    def rows(p):
        return list(csv.DictReader(pin(p).splitlines()))

    try:
        config = json.loads(pin(HERE/'protocol.json'))
        check('authorized remote', git('remote', 'get-url', 'origin').decode().strip() == config['authorized_remote'])
        check('main branch', git('branch', '--show-current').decode().strip() == config['branch'])
        current = git('rev-parse', 'HEAD').decode().strip()
        remote = git('rev-parse', 'origin/main').decode().strip()
        check('fetched origin baseline matches local', current == remote)
        stage = {}
        for line in git('ls-files', '--stage', '-z').split(b'\0'):
            if not line:
                continue
            meta, rel = line.split(b'\t', 1)
            mode, blob, level = meta.decode().split()
            check('no unmerged index', level == '0')
            stage[rel.decode('utf-8')] = blob
        object_format = git('rev-parse', '--show-object-format').decode().strip()
        manifest, group = [], defaultdict(lambda: [0, 0])
        for rel, blob in sorted(stage.items()):
            top = rel.split('/')[0]
            if not re.match(r'^(2[3-9]|3[0-8])_', top):
                continue
            payload = (ROOT/rel).read_bytes()
            h = hashlib.new(object_format)
            h.update(b'blob '+str(len(payload)).encode()+b'\0')
            h.update(payload)
            check('staged bytes match immutable evidence '+rel, h.hexdigest() == blob)
            manifest.append({'path': rel, 'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest(), 'git_blob': blob})
            group[top][0] += 1
            group[top][1] += len(payload)
        check('all sixteen version directories staged', len(group) == 16)
        with (out/'staged_evidence_manifest.csv').open('x', encoding='utf-8', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(manifest[0]))
            w.writeheader()
            w.writerows(manifest)

        documents = [ROOT/'README.md', *HERE.glob('*.md'), * (ROOT/'37_f08_integrated_candidate_review_v1').glob('*.md')]
        link_count = 0
        for doc in documents:
            body = pin(doc)
            for label, link in re.findall(r'\[([^\]]+)\]\(([^)]+)\)', body):
                if '://' in link or link.startswith('#'):
                    continue
                target = (doc.parent/link.split('#')[0]).resolve()
                check('linked artifact exists '+link, target.exists())
                rel = target.relative_to(ROOT).as_posix()
                check('linked artifact is included in Git '+link, rel in stage)
                link_count += 1
        guide = pin(HERE/'candidate_guide_ko.md')
        heads = re.findall(r'^## ([\u2460-\u2467]) ', guide, re.M)
        check('eight distinct candidate sections', len(heads) == len(set(heads)) == 8)
        for word in ['\uae30\uc5ec\ud558\ub824\ub294 \uac83.', '\uac80\uc99d\ud55c \uac83\uacfc \uacb0\uacfc.', '\ud574\uacb0\uc744 \uc704\ud574 \ud655\uc778\ud560 \uac83.', '\ub0a8\uae38 \uc870\uac74.']:
            check('each candidate has required explanation '+word, guide.count('**'+word+'**') == 8)
        comparison = rows(ROOT/config['scientific_evidence']['comparisons'])
        facts = []
        for factor in ['F01', 'F02', 'F03', 'F04', 'F05_alignment', 'F06']:
            row = next(r for r in comparison if r['factor'] == factor and r['role'] == 'primary' and r['mode'] == 'same_repeat')
            value = float(row['increment_pp'])
            token = ('\u2212' if value < 0 else '+' if value > 0 else '')+f'{abs(value):.3f}%p'
            check('primary result appears accurately '+factor, token in guide)
            facts.append({'factor': factor, 'value_pp': value, 'baseline': row['comparator'], 'mode': row['mode']})
        f07 = rows(ROOT/config['scientific_evidence']['F07'])
        r = next(r for r in f07 if r['method'] == 'Reliability_Development_fixed' and r['cases_per_task'] == '2')
        check('correct F07 time direction', r['mode'] == 'cross_repeat_20_to_40')
        check('F07 primary rounded value', f"+{float(r['vs_development_fixed_pp']):.3f}%p" in guide)
        f08 = rows(ROOT/config['scientific_evidence']['F08'])
        for suite in 'ABC':
            row = next(r for r in f08 if r['suite'] == suite and r['contrast'] == 'alternate_minus_mixture')
            val = float(row['mean_difference_pp'])
            token = ('\u2212' if val < 0 else '+')+f'{abs(val):.3f}%p'
            check('F08 result '+suite, token in guide)
        pin(ROOT/config['scientific_evidence']['latest_register'])
        summary.update({'status': 'completed', 'base_commit': current, 'fetched_origin_main': remote,
            'staged_evidence_files': len(manifest), 'staged_evidence_bytes': sum(r['bytes'] for r in manifest),
            'largest_file_bytes': max(r['bytes'] for r in manifest), 'groups': dict(group),
            'publication_links_checked': link_count, 'headline_facts': facts,
            'scientific_recomputation': 'Reused v36/v37; publication audit is not a fresh scientific replication',
            'new_environment_steps': 0, 'new_learner_updates': 0, 'remote_push_verified': False})
    except Exception:
        summary['traceback'] = traceback.format_exc()
        raise
    finally:
        summary.update({'wall_seconds': time.perf_counter()-start, 'cpu_seconds': time.process_time()-cpu,
            'checks_passed': sum(c['passed'] for c in checks), 'checks_failed': sum(not c['passed'] for c in checks)})
        save(out/'input_hashes.json', inputs)
        save(out/'checks.json', checks)
        save(out/'summary.json', summary)


if __name__ == '__main__':
    main()
