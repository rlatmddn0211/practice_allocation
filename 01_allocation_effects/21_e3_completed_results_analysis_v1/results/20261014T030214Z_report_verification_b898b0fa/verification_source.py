"""Check the delivered E3 report against its immutable analysis and figures."""
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
ANALYSIS = HERE / 'results/20261014T024817Z_ca372238'
FIGURES = HERE / 'results/20261014T025205Z_figures_e78210f9'
# These rendered PNGs were actually opened with view_image and visually reviewed.
# Hash binding prevents that review from silently applying to another rendering.
VISUAL_REVIEW = {
    'allocation_effects.png': 'e1dc12beffdc211f2db35afa5a7ad8ed5d7c1f94456b01c8a2d7e373da921c4d',
    'task_success.png': 'c655431adbcec1726c8c45b02bb529acd5ac4cf393741e9437b2238e579d364e',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    output = HERE / 'results' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_report_verification_') + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    shutil.copy2(__file__, output / 'verification_source.py')
    checks, inputs = [], {}

    def check(name, passed):
        checks.append({'name': name, 'passed': bool(passed)})
        if not passed:
            raise AssertionError(name)

    def read(path):
        inputs[str(path)] = sha(path)
        return path.read_text(encoding='utf-8')

    try:
        data = json.loads(read(ANALYSIS / 'analysis.json'))
        audit = json.loads(read(ANALYSIS / 'checks.json'))
        check('full_audit_passed', data['status'] == 'verified' and len(audit) == data['checks_passed'] == 15226 and all(r['passed'] for r in audit))
        read(ANALYSIS / 'analysis_source.py')
        check('executed_analysis_source', sha(ANALYSIS / 'analysis_source.py') == data['analysis_source_sha256'] == sha(HERE / 'analyze.py'))
        check('seed_hierarchy', data['original_seeds'] == [11, 12, 13] and data['continuation_labels'] == [2301, 2302, 2303])
        check('completed_design', data['completed_jobs'] == 459 and data['branches'] == 90 and data['branch_evaluations'] == 180)
        check('episodes_and_checkpoints', data['recomputed_evaluation_episodes'] == 81600 and data['full_checkpoints_verified'] == 246)
        check('cost_totals', data['costs']['completed_training_steps'] == 4800000 and data['costs']['completed_environment_steps'] - 4800000 == 29601294)
        check('no_new_RL', data['new_training_steps'] == data['new_evaluation_episodes'] == 0)
        docs = {name: read(HERE / name) for name in ['README.md', 'report_ko.md']}
        for name, body in docs.items():
            for destination in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)', body):
                if '://' not in destination and not destination.startswith('#'):
                    check('local_link:' + name + ':' + destination, (HERE / unquote(destination.split('#')[0])).exists())
        report = docs['report_ko.md'].replace('**', '')
        allocation_names = {'U': 'Uniform', 'F_DO': 'DrawerOpen 집중', 'F_DC': 'DrawerClose 집중', 'F_PP': 'PickPlace 집중', 'F_PU': 'Push 집중', 'F_BP': 'ButtonPress 집중'}

        def signed(value):
            return '0.00%p' if abs(value) < 1e-9 else f'{value:+.2f}%p'.replace('-', '−')

        for suite in ['B', 'C']:
            section = report.split('## ' + suite + '에서는', 1)[1].split('\n## ', 1)[0]
            baseline = statistics.mean(r['macro_pct'] for r in data['baseline_by_seed'] if r['suite'] == suite)
            check('baseline:' + suite, f'{baseline:.2f}%' in section)
            for row in data['allocation_summary']:
                if row['suite'] == suite and row['horizon'] == 40000:
                    line = f"| {allocation_names[row['allocation']]} | {row['macro_pct']:.2f}% | {signed(row['macro_gain_pp'])} | {signed(row['macro_vs_U_pp'])} |"
                    check('allocation_row:' + suite + ':' + row['allocation'], line in section)

        rule_names = {
            'Failure': 'Failure', 'Progress': 'Progress', 'LOSO_fixed': '다른 원래 seed에서 고른 고정 배분',
            'cross_repeat_same_horizon': '다른 두 후속 반복의 40k 결과로 고른 배분',
            'cross_repeat_20k_to_40k': '다른 두 후속 반복의 20k 결과로 고른 배분',
        }
        rules = {(r['suite'], r['rule']): r for r in data['rules'] if r['horizon'] == 40000}
        for key, label in rule_names.items():
            line = f"| {label} | {signed(rules['B', key]['macro_vs_U_pp'])} | {signed(rules['C', key]['macro_vs_U_pp'])} |"
            check('rule_row:' + key, line in report)
        final = {(r['suite'], r['allocation']): r for r in data['allocation_summary'] if r['horizon'] == 40000}
        check('B_BP_all_original_seeds_positive', final['B', 'F_BP']['positive_original_seeds'] == 3 and final['B', 'F_BP']['positive_continuations'] == 8)
        check('C_all_pooled_gains_negative', all(r['macro_gain_pp'] < 0 for (suite, _), r in final.items() if suite == 'C'))
        seed_rows = list(csv.DictReader(read(ANALYSIS / 'original_seed_effects.csv').splitlines()))
        c13 = [r for r in seed_rows if r['suite'] == 'C' and int(r['original_seed']) == 13 and int(r['horizon']) == 40000]
        check('C13_best_still_loses_10pp', abs(max(float(r['macro_gain_pp']) for r in c13) + 10) < 1e-9)
        check('horizon_winners_4_of_6', len(data['horizon_contexts']) == 6 and sum(r['same_winner'] for r in data['horizon_contexts']) == 4)
        manifest = json.loads(read(FIGURES / 'figure_manifest.json'))
        read(FIGURES / 'plot_source.py')
        check('figure_input_hash', manifest['input_sha256'] == sha(ANALYSIS / 'analysis.json'))
        check('figure_source_hash', manifest['source_sha256'] == sha(FIGURES / 'plot_source.py') == sha(HERE / 'plot_results.py'))
        for figure in manifest['figures']:
            path = FIGURES / figure['name']
            inputs[str(path)] = sha(path)
            check('figure_bytes:' + path.name, inputs[str(path)] == figure['sha256'] and path.stat().st_size == figure['bytes'])
        for name, digest in VISUAL_REVIEW.items():
            check('reviewed_render:' + name, sha(FIGURES / name) == digest)
        receipt = {
            'status': 'verified', 'created_at': datetime.now(timezone.utc).isoformat(),
            'checks': checks, 'inputs': inputs, 'source_sha256': sha(Path(__file__)),
            'python': platform.python_version(), 'dependencies': 'Python standard library only',
            'visual_review': {'status': 'passed', 'reviewed_images': VISUAL_REVIEW,
                              'findings': 'Both rendered PNGs inspected: readable labels, visible legend and color scale, no cropped data or text. Means are explicitly distinguished from confidence intervals.',
                              'recording': 'This sidecar resolves the generation manifest pending status without overwriting it.'},
            'training_steps': 0, 'evaluation_episodes': 0,
            'inspection_note': 'An exploratory schema read looked for nonexistent rule_summary and raised KeyError; the actual key rules was used. No analysis artifact was changed.',
        }
        with (output / 'verification.json').open('x', encoding='utf-8') as f:
            json.dump(receipt, f, ensure_ascii=False, indent=2)
        print(json.dumps({'output': str(output), 'checks_passed': len(checks), 'visual_review': 'passed'}))
    except Exception:
        with (output / 'failure.json').open('x', encoding='utf-8') as f:
            json.dump({'traceback': traceback.format_exc(), 'checks': checks, 'inputs': inputs}, f, ensure_ascii=False, indent=2)
        raise


if __name__ == '__main__':
    main()
