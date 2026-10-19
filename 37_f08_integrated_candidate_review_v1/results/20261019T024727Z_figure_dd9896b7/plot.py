"""Standalone scientific figure: every continuation, means, and parent reference."""
import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
import shutil
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--analysis', required=True)
    args = ap.parse_args()
    ad = Path(args.analysis).resolve()
    start, cpu = time.perf_counter(), time.process_time()
    out = HERE/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_figure_'+uuid.uuid4().hex[:8])
    out.mkdir(parents=True)
    print(out, flush=True)
    shutil.copy2(Path(__file__), out/'plot.py')
    os.environ['MPLCONFIGDIR'] = str(out/'mplconfig')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    with (ad/'branch_scores.csv').open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    with (ad/'parent_scores.csv').open(encoding='utf-8-sig', newline='') as f:
        parents = {r['suite']: float(r['macro_pp']) for r in csv.DictReader(f)}
    data = {(r['suite'], r['condition'], int(r['continuation'])): float(r['macro_success_pp']) for r in rows}
    colors = ['#256A9B', '#A56E13', '#A84973']
    markers = ['o', '^', 's']
    reps = [3801, 3802, 3803]
    doses = ['dose25', 'dose4375', 'dose625', 'dose8125']
    orders = ['i_then_j', 'j_then_i', 'alternate4k', 'mixture']
    fig, axes = plt.subplots(3, 2, figsize=(12.5, 10.5), sharey=True)
    for row, suite in enumerate('ABC'):
        left, right = axes[row]
        for k, rep in enumerate(reps):
            left.plot([25, 43.75, 62.5, 81.25], [data[suite, c, rep] for c in doses],
                      color=colors[k], marker=markers[k], markersize=5, linewidth=1, alpha=.85)
            right.scatter([x+(k-1)*.13 for x in range(4)], [data[suite, c, rep] for c in orders],
                          color=colors[k], marker=markers[k], s=32, zorder=3)
        left.plot([25, 43.75, 62.5, 81.25], [sum(data[suite, c, rep] for rep in reps)/3 for c in doses],
                  color='#202020', marker='D', linewidth=2, markersize=5)
        right.scatter(range(4), [sum(data[suite, c, rep] for rep in reps)/3 for c in orders], color='#202020', marker='_', s=350, linewidths=2, zorder=4)
        pair = {'A': 'DO / DC', 'B': 'BP / DO', 'C': 'PP / BP'}[suite]
        focus = {'A': 'DrawerOpen', 'B': 'ButtonPress', 'C': 'PickPlace'}[suite]
        left.set_title(f'{suite}: dose of {focus}', loc='left', fontsize=12, pad=10)
        right.set_title(f'{suite}: order of i / j = {pair}', loc='left', fontsize=12, pad=10)
        left.set_xticks([25, 43.75, 62.5, 81.25], ['25', '43.75', '62.5', '81.25'])
        left.set_xlim(20, 86)
        left.set_xlabel('Focus task share of collected steps (%)')
        right.set_xticks(range(4), ['i then j', 'j then i', 'Alternate\nevery 4k', 'Mixture'])
        right.set_xlim(-.5, 3.5)
        for ax in (left, right):
            ax.axhline(parents[suite], color='#666666', linestyle='--', linewidth=1)
            ax.set_ylim(0, 100)
            ax.set_yticks(range(0, 101, 20))
            ax.grid(axis='y', color='#E1E1E1', linewidth=.7)
            ax.set_axisbelow(True)
            ax.spines[['top', 'right']].set_visible(False)
        left.set_ylabel('Final mean task success (%)')
    legend = [Line2D([0], [0], color=colors[k], marker=markers[k], linewidth=1, label=f'Continuation {rep}') for k, rep in enumerate(reps)]
    legend += [Line2D([0], [0], color='#202020', marker='D', linewidth=2, label='Mean of 3'), Line2D([0], [0], color='#666666', linestyle='--', label='Parent policy')]
    fig.suptitle('F08: all 72 branches after 40k additional steps', x=.07, ha='left', fontsize=16, fontweight='bold', y=.985)
    fig.legend(handles=legend, loc='upper left', bbox_to_anchor=(.064, .952), ncol=5, frameon=False, fontsize=9)
    fig.subplots_adjust(top=.87, bottom=.12, left=.075, right=.975, hspace=.48, wspace=.16)
    fig.text(.075, .06, 'One original seed (12) per composition; fixed 200k parents. Points are observed continuations, not confidence intervals.\n'
             'Order conditions collect 15k steps each on i and j, 5k on each remaining task; only timing changes.\n'
             'Outcome: same 100 cases/task within each composition. Source: F08 analysis 20261016T071742Z; v37 raw-count review.', fontsize=9, linespacing=1.5)
    fig.savefig(out/'F08_all_branches.png', dpi=170)
    fig.savefig(out/'F08_all_branches.svg')
    plt.close(fig)
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    receipt = {'status': 'completed', 'analysis': str(ad), 'source_sha256': digest(Path(__file__)),
               'input_hashes': {str(ad/f): digest(ad/f) for f in ['branch_scores.csv', 'parent_scores.csv']},
               'python': sys.version, 'matplotlib': importlib.metadata.version('matplotlib'),
               'new_environment_steps': 0, 'new_learner_updates': 0,
               'wall_seconds': time.perf_counter()-start, 'cpu_seconds': time.process_time()-cpu}
    with (out/'summary.json').open('x', encoding='utf-8') as f:
        json.dump(receipt, f, indent=2)
        f.write('\n')


if __name__ == '__main__':
    main()
