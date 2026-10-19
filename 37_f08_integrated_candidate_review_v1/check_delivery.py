"""Record document links, final artifact hashes, and preserved source references."""
import hashlib
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
    out = HERE/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_delivery_'+uuid.uuid4().hex[:8])
    out.mkdir(parents=True)
    shutil.copy2(Path(__file__), out/'check_delivery.py')
    checks, hashes = [], {}
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    for path in [ROOT/'README.md', *HERE.glob('*.md'), *HERE.glob('*.py'), HERE/'protocol.json']:
        hashes[path.relative_to(ROOT).as_posix()] = digest(path)
        if path.suffix != '.md':
            continue
        txt = path.read_text(encoding='utf-8-sig')
        for label, target in re.findall(r'\[([^\]]+)\]\(([^)]+)\)', txt):
            if '://' in target or target.startswith('#'):
                continue
            checks.append({'kind': 'local_link', 'file': str(path.relative_to(ROOT)), 'target': target,
                           'passed': (path.parent/target.split('#')[0]).resolve().exists()})
    ad = HERE/'results/20261019T024708Z_review_cef06973'
    iv = json.loads((ad/'input_hashes.json').read_text())
    old = (ad/'inputs'/(iv['README.md']+'.md')).read_text(encoding='utf-8-sig')
    current = (ROOT/'README.md').read_text(encoding='utf-8-sig')
    get_table = lambda s: s[s.index('| '):s.index('\n\n', s.index('| '))]
    checks.append({'kind': 'original_three_factor_table', 'passed': get_table(old) == get_table(current)})
    for folder in ['20261019T024708Z_review_cef06973', '20261019T024727Z_verify_8ec46ef7', '20261019T024807Z_figure_e8001806']:
        for p in (HERE/'results'/folder).iterdir():
            if p.is_file() and p.suffix in ['.csv', '.json', '.png', '.svg']:
                hashes[p.relative_to(ROOT).as_posix()] = digest(p)
    receipt = {'status': 'completed' if all(x['passed'] for x in checks) else 'failed',
               'checks': checks, 'artifact_hashes': hashes,
               'python': sys.version, 'dependencies': 'standard library only',
               'final_png_visual_inspection': 'Performed via view_image: six panels, common scale, observed repeats, parent references, legend and footer; overlap fixed in second immutable output.',
               'svg_browser_inspection': 'not performed; same Matplotlib data export',
               'new_environment_steps': 0, 'new_learner_updates': 0,
               'wall_seconds': time.perf_counter()-start, 'cpu_seconds': time.process_time()-cpu}
    with (out/'summary.json').open('x', encoding='utf-8') as f:
        json.dump(receipt, f, indent=2, ensure_ascii=False)
        f.write('\n')
    print(json.dumps({'output': str(out), 'status': receipt['status'], 'links': len(checks)-1, 'artifacts_hashed': len(hashes)}))
    if receipt['status'] != 'completed':
        raise RuntimeError('Delivery checks failed; receipt retained')


if __name__ == '__main__':
    main()
