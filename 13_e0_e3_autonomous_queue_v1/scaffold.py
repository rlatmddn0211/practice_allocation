"""One-time construction of independent implementations; never run after delivery."""
import json
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
STAGES = {
    'E0': '09_fresh_evaluation_audit_v1',
    'E1': '10_independent_seed_checkpoint_study_v1',
    'E2': '11_fixed_target_donor_swap_v1',
    'E3': '12_task_composition_study_v1',
}
SUITES = {
    'A': {'labels': ['DO', 'DC', 'WO', 'WC'], 'envs': ['drawer-open-v3', 'drawer-close-v3', 'window-open-v3', 'window-close-v3']},
    'B': {'labels': ['DO', 'DC', 'PU', 'BP'], 'envs': ['drawer-open-v3', 'drawer-close-v3', 'push-v3', 'button-press-v3']},
    'C': {'labels': ['DO', 'PP', 'PU', 'BP'], 'envs': ['drawer-open-v3', 'pick-place-v3', 'push-v3', 'button-press-v3']},
}
source = REPO / '06_p0_branch_replication_v1'
for stage, name in STAGES.items():
    dest = REPO / name
    dest.mkdir(exist_ok=False)
    (dest / 'practice_allocation').mkdir()
    (dest / 'configs').mkdir()
    (dest / 'tests').mkdir()
    for filename in ['__init__.py', 'core.py', 'environment.py', 'learning.py', 'engine.py', 'evaluation.py']:
        shutil.copy2(source / 'practice_allocation' / filename, dest / 'practice_allocation' / filename)
    shutil.copy2(source / 'requirements.txt', dest / 'requirements.txt')
    shutil.copy2(source / 'tests/test_contracts.py', dest / 'tests/test_contracts.py')
    core_path = dest / 'practice_allocation/core.py'
    core = core_path.read_text(encoding='utf-8')
    start, end = core.index('TASKS = '), core.index('PINNED = ')
    binding = '''SUITES = json.loads((ROOT / "configs/suites.json").read_text(encoding="utf-8"))
SUITE = os.environ.get("PRACTICE_SUITE", "A")
if SUITE not in SUITES:
    raise ValueError(f"Unknown suite: {SUITE}")
TASKS = tuple(SUITES[SUITE]["labels"])
ENV_NAMES = tuple(SUITES[SUITE]["envs"])
ALLOCATIONS = {"U": (2, 2, 2, 2)}
ALLOCATIONS.update({f"F_{label}": tuple(5 if i == j else 1 for i in range(4)) for j, label in enumerate(TASKS)})
if SUITE == "A":
    ALLOCATIONS.update({"DC_plus_WO_minus": (2, 3, 1, 2), "DC_minus_WO_plus": (2, 1, 3, 2)})
'''
    core_path.write_text(core[:start] + binding + core[end:], encoding='utf-8', newline='\n')
    config = json.loads((source / 'configs/learner.json').read_text(encoding='utf-8'))
    config.update(version=name, diagnostic_bank_episodes_per_task=100, outcome_bank_episodes_per_task=100, bank_seed=95001)
    (dest / 'configs/learner.json').write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    (dest / 'configs/suites.json').write_text(json.dumps(SUITES, indent=2) + '\n', encoding='utf-8')
    (dest / 'VERSION.json').write_text(json.dumps({'version': name, 'stage': stage, 'base': source.name, 'authorized': '2026-10-08', 'self_contained': True}, indent=2) + '\n', encoding='utf-8')
print(json.dumps(STAGES))
