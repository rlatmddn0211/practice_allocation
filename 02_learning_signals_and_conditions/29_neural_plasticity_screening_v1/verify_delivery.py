"""Audit this delivery's evidence, documents and immutable run snapshots."""
from __future__ import annotations
import ast
import json
import re
import shutil
import traceback
from pathlib import Path
from urllib.parse import unquote
from common import Run, HERE, ROOT, save, sha, table


def check_close(run, label, actual, expected, tolerance=1e-10):
    run.check(label, abs(float(actual)-float(expected)) <= tolerance,
              {'actual': actual, 'expected': expected})


def main():
    run = Run('verify_delivery')
    try:
        index = run.read(HERE/'result_index.json')
        protocol = run.read(HERE/'protocol.json')
        roles = ['failed_smoke', 'successful_smoke', 'smoke_verification',
                 'measurement', 'analysis', 'measurement_verification', 'analysis_verification']
        summaries, cost_rows = {}, []
        for role in roles:
            path = HERE/'results'/index[role]
            summary = run.read(path/'summary.json')
            summaries[role] = summary
            run.check('run status '+role, summary['status'] == ('failed' if role == 'failed_smoke' else 'completed'))
            checks = run.read(path/'checks.json')
            run.check('check totals '+role,
                      sum(bool(c['passed']) for c in checks) == summary['checks_passed'] and
                      sum(not c['passed'] for c in checks) == summary['checks_failed'])
            run.check('no original updates or environment steps '+role,
                      summary['new_environment_steps'] == summary['new_learner_updates'] == 0)
            runtime = run.read(path/'runtime.json')
            sources = run.read(path/'source_hashes.json')
            for name, digest in sources.items():
                run.hashed(path/'sources'/name, digest)
            run.check('invoked script was snapshotted '+role,
                      Path(runtime['argv'][0]).name in sources)
            run.check('protocol unchanged since each run '+role,
                      run.read(path/'sources/protocol.json') == protocol)
            # Recheck local input evidence. Checkpoint payload verification is in the
            # independent measurement audit; do not reread tens of GB for a doc audit.
            inputs = run.read(path/'input_hashes.json')
            for name, digest in inputs.items():
                target = Path(name).resolve()
                if target.is_relative_to(HERE):
                    run.hashed(target, digest)
            cost_rows.append({'role': role, 'run': path.name, 'status': summary['status'],
                              'wall_seconds': summary['wall_seconds'], 'cpu_seconds': summary['cpu_seconds'],
                              'clone_optimizer_steps': summary.get('clone_optimizer_steps', 0),
                              'measured_cuda_event_seconds': summary.get('gpu_compute_seconds'),
                              'new_environment_steps': summary['new_environment_steps'],
                              'new_persistent_learner_updates': summary['new_learner_updates']})
        totals = {key: sum(r[key] for r in cost_rows)
                  for key in ['wall_seconds', 'cpu_seconds', 'clone_optimizer_steps',
                              'new_environment_steps', 'new_persistent_learner_updates']}
        totals['measured_cuda_event_seconds_only'] = sum(r['measured_cuda_event_seconds'] or 0 for r in cost_rows)
        totals['all_run_gpu_time_measured'] = False
        table(run.out/'execution_costs.csv', cost_rows)
        save(run.out/'pre_delivery_cost_totals.json', totals)

        failed = summaries['failed_smoke']
        run.check('failure preserved with cause', 'AttributeError' in failed['traceback'] and
                  "module 'profile'" in failed['traceback'] and failed['clone_optimizer_steps'] == 0)
        run.check('shadowing module removed from delivered implementation', not (HERE/'profile.py').exists())
        measured = summaries['measurement']
        run.check('full measurement size', measured['snapshots'] == 192 and
                  measured['clone_optimizer_steps'] == 15360 and measured['clone_loss_rows'] == 18432)
        measured_check = summaries['measurement_verification']
        run.check('independent reference audit complete', measured_check['snapshots_verified'] == 192 and
                  len(measured_check['reference_snapshots']) == 8 and
                  all(r['max_independent_mean_loss_abs_error'] == 0 for r in measured_check['reference_snapshots']))
        run.check('prediction reference audit complete', summaries['analysis_verification']['raw_episode_rows'] == 148800 and
                  summaries['analysis_verification']['ridge_fits'] == 33 and
                  summaries['analysis_verification']['predictions'] == 1980)
        analysis = summaries['analysis']
        primary = analysis['primary']
        expected_screen = (primary['vs_base_pp'] >= 1 and
                           sum(x > 0 for x in analysis['original_seed_increments_pp']) >= 2 and
                           min(analysis['group_increments_pp']) >= -2)
        run.check('reported screen follows fixed rule', analysis['operational_screen_pass'] == expected_screen)
        run.check('independent confirmation not claimed', not analysis['independent_confirmation'])
        a = HERE/'results'/index['analysis']
        contrasts = run.rows(a/'planned_contrasts.csv')
        primary_contrast = next(r for r in contrasts if r['method'] == protocol['primary_model'] and
                               r['mode'] == 'same_repeat' and r['scope'] == 'all')
        static_contrast = next(r for r in contrasts if r['method'] == 'CoverageBase_static' and
                              r['mode'] == 'same_repeat' and r['scope'] == 'all')
        check_close(run, 'primary reported contrast', primary['vs_base_pp'], primary_contrast['increment_pp'])
        run.check('static comparison has correct baseline', static_contrast['comparator'] == 'CoverageBase')
        run.check('primary comparison has correct baseline', primary_contrast['comparator'] == 'StepBase')

        docs = list(HERE.glob('*.md')) + [ROOT/'README.md']
        texts = {path: path.read_text(encoding='utf-8-sig') for path in docs}
        formatted_primary = f"+{float(primary_contrast['increment_pp']):.3f}%p"
        formatted_static = f"+{float(static_contrast['increment_pp']):.3f}%p"
        for path in [HERE/'README.md', HERE/'report_ko.md', HERE/'factor_status_ko.md', ROOT/'README.md']:
            run.check('document main effects agree '+path.name,
                      formatted_primary in texts[path] and formatted_static in texts[path])
        report = texts[HERE/'report_ko.md']
        for r in run.rows(a/'prediction_metrics.csv'):
            if r['method'] in ['CriticBase', 'CoverageBase', 'CoverageBase_static',
                               'CoverageBase_total20', 'StepBase', 'StepBase_F06']:
                run.check('document MAE '+r['method'], f"{float(r['O40_MAE_pp']):.3f}%p" in report)
        for key in ['wall_seconds', 'cpu_seconds']:
            run.check('document total cost '+key, f"{totals[key]:,.3f}" in report)
        run.check('document total clone steps', f"{totals['clone_optimizer_steps']:,}" in report)
        for role in ['measurement_verification', 'analysis_verification']:
            run.check('document independent check totals '+role,
                      f"{summaries[role]['checks_passed']:,}" in report)
        for module in analysis['diagnostics']['dynamic_summary']:
            token = f"{module['train_improves_other_worsens_branches']}/180"
            run.check('document fitting gap count '+module['module'], token in report)
        for token in ['40k 동일 총예산', '미계측', '원래 seed', '채택 보류', '조건부', '새로운 확인 표본']:
            run.check('document limitations '+token, token in report)
        core_table = ('| 후보 요인 | 측정하려는 것 |\n|---|---|\n'
                      '| 학습 반응성 | 짧게 더 연습했을 때 해당 과제가 얼마나 개선되는가 |\n'
                      '| 다른 능력의 변화 | 그 연습으로 다른 과제의 성능이 얼마나 좋아지거나 떨어지는가 |\n'
                      '| 효과의 지속성 | 연습을 이어갈수록 개선 속도가 유지되는가, 포화되거나 역전되는가 |')
        run.check('original three-factor table preserved', core_table in texts[ROOT/'README.md'])
        run.check('root points at newest ledger',
                  '[최신 후보별 근거 기록](29_neural_plasticity_screening_v1/factor_status_ko.md)' in texts[ROOT/'README.md'])
        local_links = 0
        for path, body in texts.items():
            for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', body):
                target = target.strip('<>').split('#')[0]
                if not target or re.match(r'^[a-z]+://', target):
                    continue
                destination = (path.parent/unquote(target)).resolve()
                run.check('document local link '+path.name+' '+target, destination.exists())
                local_links += 1
        attr = (ROOT/'.gitattributes').read_text(encoding='utf-8-sig')
        run.check('recorded bytes protected in Git',
                  '29_neural_plasticity_screening_v1/** -text whitespace=cr-at-eol' in attr)
        doc_copies = {}
        for path in docs + [ROOT/'AGENTS.md', ROOT/'.gitattributes', HERE/'result_index.json']:
            target = run.out/'documents'/path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            digest = run.hashed(path)
            run.hashed(target, digest)
            doc_copies[str(path.relative_to(ROOT))] = digest
        save(run.out/'document_hashes.json', doc_copies)

        # Audit actual imports, rather than rejecting words inside comments/strings.
        code_files = list(HERE.glob('*.py'))
        imported = {}
        for path in code_files:
            tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
            names = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names.extend(a.name for a in node.names)
                elif isinstance(node, ast.ImportFrom):
                    names.append(node.module or '')
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Attribute):
                        value = node.func.value
                        if isinstance(value.value, ast.Name) and value.value.id == 'sys' and value.attr == 'path':
                            run.check('no path injection '+path.name, node.func.attr not in ['append', 'insert', 'extend'])
                    function = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ''
                    if function in ['__import__', 'import_module', 'spec_from_file_location']:
                        literal_args = [a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
                        run.check('no external-version dynamic import '+path.name,
                                  len(literal_args) == len(node.args) and
                                  not any(re.search(r'(?:^|[\\/.])\d{2}_[a-z_]+', x) for x in literal_args))
            run.check('no cross-version static imports '+path.name,
                      not any(re.search(r'(?:^|\.)\d{2}_', x) for x in names))
            imported[path.name] = sorted(set(names))
        save(run.out/'import_audit.json', imported)

        # Preserve a checksum inventory of all current implementation and prior runs.
        # The current audit directory has its own source/document records and is omitted.
        inventory = []
        for path in sorted(HERE.rglob('*')):
            if path.is_file() and not path.is_relative_to(run.out) and '__pycache__' not in path.parts:
                inventory.append({'path': str(path.relative_to(HERE)), 'size': path.stat().st_size, 'sha256': sha(path)})
        table(run.out/'artifact_manifest.csv', inventory)
        run.finish({'status': 'completed', 'factor': 'F06', 'audited_runs': len(roles),
                    'preserved_failed_runs': 1, 'prior_run_cost_totals': totals,
                    'primary_screen_pass': expected_screen, 'scientific_decision': 'defer_current_summary_features',
                    'local_document_links': local_links, 'python_files_audited': len(code_files),
                    'artifacts': len(inventory), 'artifact_bytes': sum(r['size'] for r in inventory),
                    'clone_optimizer_steps': 0,
                    'scope': 'Recorded source snapshots, local analysis inputs, documents and final artifact inventory. Original checkpoint payload integrity is covered by the completed measurement audit.'})
    except Exception:
        run.finish({'status': 'failed', 'traceback': traceback.format_exc(), 'clone_optimizer_steps': 0})
        raise


if __name__ == '__main__':
    main()
