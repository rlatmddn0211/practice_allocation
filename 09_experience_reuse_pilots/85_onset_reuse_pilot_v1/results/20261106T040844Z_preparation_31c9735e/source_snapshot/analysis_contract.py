"""Pure-array planned AUC/parent/bootstrap calculations, not synthetic evidence."""
from __future__ import annotations
import numpy as np

AUC_WEIGHTS=np.array([.125,.25,.375,.25],dtype=np.float64)

def fixed_panel_auc(labels):
    """[four observation times,16 cases]; any missing label makes AUC unknown.

    Bounds retain all 16 planned cases. A failed/missing evaluation is never an
    observed failure; numeric bounds are explicitly separate from the estimate.
    """
    a=np.asarray(labels,dtype=float)
    if a.shape!=(4,16):raise ValueError(a.shape)
    known=np.isfinite(a)
    if not np.isin(a[known],[0,1]).all():raise ValueError('nonbinary label')
    lo=np.where(known,a,0).mean(axis=1);hi=np.where(known,a,1).mean(axis=1)
    return dict(complete=bool(known.all()),auc=float(AUC_WEIGHTS@a.mean(axis=1)) if known.all() else None,
        auc_lower_bound=float(AUC_WEIGHTS@lo),auc_upper_bound=float(AUC_WEIGHTS@hi),
        planned_cases=16,valid_case_counts=known.sum(axis=1).tolist())

def parent_future_effects(aucs):
    """Array [5 parents,2 futures,3 arms]; arm order BASE,RANDOM_PRE,ONSET."""
    a=np.asarray(aucs,dtype=float)
    if a.shape!=(5,2,3):raise ValueError(a.shape)
    effects=np.stack((a[:,:,2]-a[:,:,1],a[:,:,2]-a[:,:,0],a[:,:,1]-a[:,:,0]),axis=-1)
    # Do not renormalize over whatever cells happen to be present.
    parent=effects.mean(axis=1)
    return effects,parent,parent.mean(axis=0)

def paired_parent_bootstrap(parent_effects):
    a=np.asarray(parent_effects,dtype=float)
    if a.shape[0]!=5 or not np.isfinite(a).all():raise ValueError('five complete parents required')
    draws=np.random.Generator(np.random.PCG64(54001)).integers(0,5,size=(20000,5))
    estimates=a[draws].mean(axis=1)
    return draws,np.quantile(estimates,[.025,.975],axis=0,method='linear')

def analysis_checks():
    rows=[]
    def ck(name,v):
        rows.append(dict(check=name,passed=bool(v),scope='synthetic analysis; not scientific effect'))
        if not v:raise AssertionError(name)
    a=np.zeros((4,16));a[1:]=1
    ck('AUC time weighting',fixed_panel_auc(a)['auc']==.875)
    a[1,0]=np.nan;r=fixed_panel_auc(a)
    ck('missing case gives no point AUC and retains 16-case bounds',not r['complete'] and r['auc'] is None and r['auc_upper_bound']-r['auc_lower_bound']==.25/16)
    f,p,mean=parent_future_effects(np.ones((5,2,3))*.25)
    ck('identical arms have zero differences',not f.any() and not p.any() and not mean.any())
    a=np.ones((5,2,3));a[0,0,2]=np.nan
    ck('missing branch not silently dropped',np.isnan(parent_future_effects(a)[2][:2]).all())
    x=np.array([0,1,0,1,1,0,1]);gain=int(((x[:-1]==0)&(x[1:]==1)).sum());loss=int(((x[:-1]==1)&(x[1:]==0)).sum())
    ck('gain loss telescoping identity',gain==3 and loss==2 and gain-loss==x[-1]-x[0])
    return rows
