"""Validate research-document links, requested table and immutable evidence."""
import csv
import hashlib
import json
import platform
import re
import shutil
import statistics
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EVIDENCE = HERE / 'results/20261014T040516Z_replay_b4e477d0'
TABLE = '''| 후보 요인 | 측정하려는 것 |
|---|---|
| 학습 반응성 | 짧게 더 연습했을 때 해당 과제가 얼마나 개선되는가 |
| 다른 능력의 변화 | 그 연습으로 다른 과제의 성능이 얼마나 좋아지거나 떨어지는가 |
| 효과의 지속성 | 연습을 이어갈수록 개선 속도가 유지되는가, 포화되거나 역전되는가 |'''


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    output = HERE / 'results' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_publication_') + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    shutil.copy2(__file__, output / 'verification_source.py')
    checks, hashes = [], {}

    def check(name, passed):
        checks.append({'name': name, 'passed': bool(passed)})
        if not passed:
            raise AssertionError(name)

    def read(path):
        hashes[str(path)] = sha(path)
        return path.read_text(encoding='utf-8')

    try:
        docs = [ROOT / 'README.md', *HERE.glob('*.md')]
        for path in docs:
            body = read(path)
            if path.name in ['research_development_ko.md'] or path == ROOT / 'README.md':
                check('requested_table:' + str(path), TABLE in body)
            for destination in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)', body):
                if '://' not in destination and not destination.startswith('#'):
                    check('link:' + destination, (path.parent / unquote(destination.split('#')[0])).exists())
        sources = json.loads(read(HERE / 'sources.json'))
        check('primary_source_registry', len(sources['papers']) == 9 and all(p['url'].startswith('https://') and p['supports'] and p['boundary'] for p in sources['papers']))
        evidence = json.loads(read(EVIDENCE / 'analysis.json'))
        audit = json.loads(read(EVIDENCE / 'checks.json'))
        check('exposure_audit', evidence['status'] == 'verified' and evidence['checks_passed'] == len(audit) == 1290 and all(r['passed'] for r in audit))
        check('executed_exposure_source', evidence['source_sha256'] == sha(EVIDENCE / 'audit_source.py') == sha(HERE / 'audit_replay_exposure.py'))
        rows = list(csv.DictReader(read(EVIDENCE / 'replay_exposure.csv').splitlines()))
        check('180_intervals', len(rows) == 180)
        report = (HERE / 'candidate_factors_ko.md').read_text(encoding='utf-8')
        for summary in evidence['summary']:
            subset = [r for r in rows if int(r['interval_end']) == summary['interval_end'] and r['allocation'] != 'U']
            check('focus_count:' + str(summary['interval_end']), len(subset) == 72)
            for key, field in [('mean_sampled_pct', 'focus_sampled_pct'), ('mean_cumulative_sampled_pct', 'cumulative_focus_sampled_pct')]:
                value = statistics.mean(float(r[field]) for r in subset)
                check(key + ':' + str(summary['interval_end']), abs(value - summary[key]) < 1e-10 and f'{value:.2f}%' in report)
        previous = ROOT / '21_e3_completed_results_analysis_v1/results/20261014T030214Z_report_verification_b898b0fa/verification.json'
        review = json.loads(read(previous))
        check('previous_report_verified', review['status'] == 'verified')
        for path, digest in review['inputs'].items():
            check('frozen_E3_report:' + path, sha(Path(path)) == digest)
        check('no_new_training_or_evaluation', evidence['new_training_steps'] == evidence['new_evaluation_episodes'] == sources['new_RL_training_steps'] == sources['new_environment_evaluation_episodes'] == 0)
        receipt = {'status': 'verified', 'created_at': datetime.now(timezone.utc).isoformat(), 'checks': checks,
                   'inputs': hashes, 'source_sha256': sha(Path(__file__)), 'python': platform.python_version(),
                   'dependencies': 'Python standard library only', 'new_training_steps': 0, 'new_evaluation_episodes': 0,
                   'scope': 'Links, exact requested table, numeric evidence and frozen E3 report. Literature interpretation was reviewed separately; mechanical checks do not prove hypotheses.'}
        with (output / 'verification.json').open('x', encoding='utf-8') as f:
            json.dump(receipt, f, ensure_ascii=False, indent=2)
        print(json.dumps({'output': str(output), 'checks_passed': len(checks)}))
    except Exception:
        with (output / 'failure.json').open('x', encoding='utf-8') as f:
            json.dump({'traceback': traceback.format_exc(), 'checks': checks, 'inputs': hashes}, f, ensure_ascii=False, indent=2)
        raise


if __name__ == '__main__':
    main()
