"""Read-only size inventory for the explicitly requested 81/82 publication."""
from pathlib import Path
import collections
import json
import shutil

ROOT = Path(__file__).resolve().parent.parent
totals = collections.defaultdict(lambda: [0, 0])
subdirectories = collections.defaultdict(lambda: [0, 0])
largest = []
for name in ('81_basic_sac_observation_campaign_v1', '82_basic_observation_exploratory_report_v1'):
    for p in (ROOT / name).rglob('*'):
        if not p.is_file():
            continue
        size = p.stat().st_size
        key = (name, p.suffix.lower())
        totals[key][0] += 1
        totals[key][1] += size
        parts = p.relative_to(ROOT).parts
        section = '/'.join(parts[:6]) if len(parts) > 5 and parts[3] == 'runs' else '/'.join(parts[:4])
        subdirectories[section][0] += 1
        subdirectories[section][1] += size
        largest.append((size, p.relative_to(ROOT).as_posix()))
print(json.dumps({
    'free_bytes': shutil.disk_usage(ROOT).free,
    'totals': [dict(directory=k[0], extension=k[1], files=v[0], bytes=v[1])
               for k, v in sorted(totals.items())],
    'largest': [dict(bytes=n, path=p) for n, p in sorted(largest, reverse=True)[:12]],
    'sections': [dict(path=k, files=v[0], bytes=v[1]) for k, v in sorted(subdirectories.items())
                 if v[1] > 1000000],
}, ensure_ascii=False))
