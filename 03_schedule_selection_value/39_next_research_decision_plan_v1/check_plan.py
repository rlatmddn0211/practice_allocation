"""Record proposal arithmetic and its frozen evidence inputs; no RL execution."""
import csv
import hashlib
import io
import json
import re
import shutil
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def main():
    start, cpu = time.perf_counter(), time.process_time()
    out = HERE/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_plan_check_'+uuid.uuid4().hex[:8])
    out.mkdir(parents=True)
    print(out, flush=True)
    (out/'sources').mkdir()
    sources = [Path(__file__), HERE/'proposal.json', *HERE.glob('*.md')]
    hashes = {}
    for source in sources:
        shutil.copy2(source, out/'sources'/source.name)
        hashes[source.name] = hashlib.sha256(source.read_bytes()).hexdigest()
    p = json.loads((HERE/'proposal.json').read_text(encoding='utf-8-sig'))
    a = p['first_packet']
    n = a['new_original_seeds']
    branches = n*a['continuations_per_parent']*len(a['conditions'])
    train = n*a['pretraining_steps_per_original']+branches*a['branch_steps']
    e = a['outcome_evaluation']
    episodes = (n+branches)*e['tasks_per_policy']*e['cases_per_task']
    evaluation_bound = episodes*e['max_steps_per_episode']
    checks = {'proposal_only': p['status'] == 'proposal_only_not_executed',
              '32_branches': branches == 32, 'training_2080000': train == 2080000,
              '14400_evaluation_episodes': episodes == 14400,
              'environment_upper_bound_9280000': train+evaluation_bound == 9280000}
    inputs = {}
    for key, rel in p['evidence'].items():
        source = ROOT/rel
        payload = source.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        inputs[rel] = digest
        dest = out/'inputs'/(digest+source.suffix)
        dest.parent.mkdir(exist_ok=True)
        dest.write_bytes(payload)
        if key == 'contrast_review':
            rows = list(csv.DictReader(io.StringIO(payload.decode('utf-8-sig'))))
            r = next(r for r in rows if r['suite'] == 'B' and r['contrast'] == 'alternate_minus_mixture')
            checks['B_mean_5_8333'] = abs(float(r['mean_difference_pp'])-35/6) < 1e-9
            checks['B_three_positive_continuations'] = int(r['same_sign_repeats']) == 3
        if key == 'condition_means':
            rows = list(csv.DictReader(io.StringIO(payload.decode('utf-8-sig'))))
            means = {r['condition']: float(r['mean_macro_pp']) for r in rows if r['suite'] == 'B'}
            checks['strong_fixed_baseline_preserved'] = abs(means['dose625']-40) < 1e-9 and means['dose625'] > means['alternate4k']
    for doc in HERE.glob('*.md'):
        for link in re.findall(r'\]\(([^)]+)\)', doc.read_text(encoding='utf-8-sig')):
            if '://' not in link and not link.startswith('#'):
                checks['link '+doc.name+' '+link] = (doc.parent/link.split('#')[0]).exists()
    result = {'status': 'completed' if all(checks.values()) else 'failed', 'checks': checks,
              'source_hashes': hashes, 'input_hashes': inputs, 'python': sys.version,
              'dependencies': 'Python standard library only', 'proposed_branches': branches,
              'proposed_pretraining_steps': n*a['pretraining_steps_per_original'],
              'proposed_branch_training_steps': branches*a['branch_steps'],
              'proposed_training_steps': train, 'proposed_evaluation_episodes': episodes,
              'proposed_evaluation_step_upper_bound': evaluation_bound,
              'proposed_environment_step_upper_bound': train+evaluation_bound,
              'new_environment_steps': 0, 'new_learner_updates': 0, 'experiment_launched': False,
              'wall_seconds': time.perf_counter()-start, 'cpu_seconds': time.process_time()-cpu}
    with (out/'summary.json').open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
        f.write('\n')
    if result['status'] != 'completed':
        raise AssertionError('Plan check failed; see preserved summary')


if __name__ == '__main__':
    main()
