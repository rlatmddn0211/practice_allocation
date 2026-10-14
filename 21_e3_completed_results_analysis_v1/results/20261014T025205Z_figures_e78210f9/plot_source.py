"""Standalone research figures from the verified E3 analysis."""
import argparse
import hashlib
import json
import os
import shutil
import statistics as st
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--analysis', type=Path, required=True)
args = parser.parse_args()
out = HERE/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_figures_')+uuid.uuid4().hex[:8])
out.mkdir(parents=True, exist_ok=False)
shutil.copy2(__file__, out/'plot_source.py')
os.environ['MPLCONFIGDIR'] = str(out/'matplotlib_cache')

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    source = args.analysis.resolve()
    data = json.loads(source.read_text(encoding='utf-8'))
    assert data['status'] == 'verified'
    plt.rcParams.update({'font.family':'DejaVu Sans', 'font.size':11, 'axes.spines.top':False,
                         'axes.spines.right':False, 'svg.hashsalt':'E3_completed_results_v1'})
    seeds = data['original_seeds']
    colors = ['#0072B2', '#D55E00', '#009E73']
    final = {(r['suite'],r['allocation']):r for r in data['allocation_summary'] if r['horizon']==40000}
    tasks = data['task_compositions']
    fig, axes = plt.subplots(1,2,figsize=(11.6,4.8),sharey=True)
    for ax,suite in zip(axes,['B','C']):
        labels=tasks[suite]
        ax.axhline(0,color='#555555',lw=1)
        for i,t in enumerate(labels):
            r=final[suite,'F_'+t]
            ax.plot([i-.30,i+.30],[r['macro_vs_U_pp']]*2,color='#222222',lw=2.3,label='Mean of original seeds' if i==0 else None)
            for j,s in enumerate(seeds):
                ax.scatter(i+(j-1)*.15,r[f'seed_{s}_pp'],color=colors[j],s=48,zorder=3,label=f'Original seed {s}' if i==0 else None)
        ax.set_xticks(range(4),[f'{t} focus' for t in labels])
        ax.set_title(f'Composition {suite} | +40k training',loc='left',fontweight='bold')
        ax.set_ylim(-9,11)
        ax.grid(axis='y',alpha=.18)
    axes[0].set_ylabel('Macro success difference from Uniform (pp)')
    handles,labels=axes[0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='lower center',ncol=4,frameon=False,bbox_to_anchor=(.5,.01))
    fig.suptitle('Allocation effects depend on composition and original state',x=.065,ha='left',fontsize=15)
    fig.text(.065,.13,'Each colored dot averages 3 continuation seeds. Bars are means, not confidence intervals.',fontsize=10,color='#555555')
    fig.subplots_adjust(bottom=.27,top=.83,wspace=.14,left=.075,right=.98)
    for ext in ['png','svg']:fig.savefig(out/f'allocation_effects.{ext}',dpi=220)
    plt.close(fig)

    fig,axes=plt.subplots(1,2,figsize=(11.6,5.8))
    for ax,suite in zip(axes,['B','C']):
        names=['U']+['F_'+t for t in tasks[suite]]
        base=[st.mean(r[t+'_pct'] for r in data['baseline_by_seed'] if r['suite']==suite) for t in tasks[suite]]
        matrix=[base]+[[final[suite,a][t+'_pct'] for t in tasks[suite]] for a in names]
        plot=ax.imshow(matrix,vmin=0,vmax=100,cmap='viridis',aspect='auto')
        for y,row in enumerate(matrix):
            for x,v in enumerate(row):ax.text(x,y,f'{v:.1f}',ha='center',va='center',color='black' if v>57 else 'white',fontsize=11)
        ax.set_xticks(range(4),tasks[suite])
        ax.set_yticks(range(6),['Starting policy','Uniform']+[t+' focus' for t in tasks[suite]])
        ax.set_title(f'Composition {suite}',loc='left',fontweight='bold')
        ax.tick_params(length=0)
        for spine in ax.spines.values():spine.set_visible(False)
    fig.suptitle('Per-task success before and after +40k training',x=.09,ha='left',fontsize=15)
    fig.subplots_adjust(bottom=.16,top=.86,wspace=.53,left=.12,right=.88)
    bar=fig.add_axes([.91,.25,.02,.5]);fig.colorbar(plot,cax=bar,label='Success (%)')
    fig.text(.12,.075,'DO: DrawerOpen | DC: DrawerClose | PP: PickPlace | PU: Push | BP: ButtonPress',fontsize=10)
    for ext in ['png','svg']:fig.savefig(out/f'task_success.{ext}',dpi=220)
    plt.close(fig)
    figures=[{'name':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.glob('*')) if p.suffix in ['.png','.svg']]
    receipt={'status':'generated','input':str(source),'input_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
             'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'matplotlib':matplotlib.__version__,
             'figures':figures,'training_steps':0,'evaluation_episodes':0,'visual_review':'pending'}
    with (out/'figure_manifest.json').open('x',encoding='utf-8') as f:json.dump(receipt,f,indent=2)
    print(json.dumps({'output':str(out),'figures':figures},indent=2))
except Exception:
    with (out/'failure.json').open('x',encoding='utf-8') as f:json.dump({'traceback':traceback.format_exc()},f)
    raise
