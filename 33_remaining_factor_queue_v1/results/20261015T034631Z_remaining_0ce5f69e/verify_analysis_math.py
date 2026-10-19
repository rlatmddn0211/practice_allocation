"""Technical checks on fold exclusion, ridge fits and paired-contrast units."""
import ast
import hashlib
import importlib.util
import json
import shutil
import sys
import time
import traceback
import uuid
from datetime import datetime,timezone
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent

def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    out=HERE/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_analysis_preflight_'+uuid.uuid4().hex[:8]);out.mkdir(parents=True)
    print(str(out),flush=True);start=time.perf_counter();cpu=time.process_time();checks=[];sources={};error=None
    def check(name,ok):
        checks.append({'check':name,'passed':bool(ok)})
        if not ok:raise AssertionError(name)
    try:
        for directory in [ROOT/'31_fixed_horizon_alignment_v1',ROOT/'32_dose_order_intervention_v1',HERE]:
            for p in directory.glob('*.py'):
                name=p.relative_to(ROOT).as_posix();sources[name]=sha(p);dest=out/'source'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
                ast.parse(p.read_text(encoding='utf-8-sig'),filename=str(p))
        sys.path.insert(0,str(ROOT/'31_fixed_horizon_alignment_v1'))
        import features
        import analyze
        import verify_analysis
        rng=np.random.default_rng(331015)
        for constant in [False,True]:
            x=np.ones(37)*8 if constant else rng.normal(size=37);y=rng.integers(0,2,size=37)
            f=features.calibrated_fit(x,y);z=(x-x.mean())/(x.std() if x.std()>1e-12 else 1.)
            design=np.vstack([np.column_stack([np.ones(len(x)),z])/np.sqrt(len(x)),[0,1]])
            beta=np.linalg.lstsq(design,np.r_[y/np.sqrt(len(x)),0],rcond=None)[0]
            check('calibration independently fit '+str(constant),np.allclose(beta,[f['intercept'],f['slope']],rtol=1e-12,atol=1e-12))
        rows=[]
        for seed in [11,12,13]:
            for k in range(7):
                r={'id':f'{seed}_{k}','original_seed':seed,'weight':1/21,'D20':float(rng.random()),'target_D_remainder':float(rng.normal())}
                r.update({field+'_held'+str(held):float(rng.normal()) for field in features.FOLD_FIELDS for held in [11,12,13]});rows.append(r)
        for held in [11,12,13]:
            cols=features.FOLD_FIELDS;pred,f=analyze.fit(rows,cols,held,'fixture')
            tr=[r for r in features.prepare_fold(rows,held) if r['original_seed']!=held];te=[r for r in features.prepare_fold(rows,held) if r['original_seed']==held]
            x=np.array([[r[c] for c in cols] for r in tr]);mu=x.mean(0);sd=x.std(0);z=(x-mu)/sd
            design=np.vstack([np.column_stack([np.ones(len(x)),z])/np.sqrt(len(x)),np.column_stack([np.zeros(len(cols)),np.eye(len(cols))])])
            beta=np.linalg.lstsq(design,np.r_[[r['target_D_remainder']/np.sqrt(len(x)) for r in tr],np.zeros(len(cols))],rcond=None)[0]
            expected={r['id']:r['D20']+np.r_[1,(np.array([r[c] for c in cols])-mu)/sd]@beta for r in te}
            check('allocation ridge independently fit '+str(held),all(abs(pred[k]-v)<1e-12 for k,v in expected.items()))
            altered=[dict(r,target_D_remainder=1e8 if r['original_seed']==held else r['target_D_remainder']) for r in rows]
            check('held outcomes cannot affect fit '+str(held),analyze.fit(altered,cols,held,'fixture')[0]==pred)
            check('fold materialization preserves source '+str(held),all(not any(c in r for c in cols) for r in rows))
        check('deterministic tie breaking',analyze.choose([1,1,0])==0)
        spec=importlib.util.spec_from_file_location('dose_analysis',ROOT/'32_dose_order_intervention_v1/analyze.py');dose=importlib.util.module_from_spec(spec);spec.loader.exec_module(dose)
        spec=importlib.util.spec_from_file_location('dose_verification',ROOT/'32_dose_order_intervention_v1/verify_analysis.py');ver=importlib.util.module_from_spec(spec);spec.loader.exec_module(ver)
        check('seven preregistered contrasts',len(dose.CONTRASTS)==7)
        doses={'dose25':.25,'dose4375':.4375,'dose625':.625,'dose8125':.8125}
        for name,coeff in dose.CONTRASTS.items():
            check('constant outcome cancels '+name,abs(sum(coeff.values()))<1e-12)
            if 'nonlinearity' in name:check('linear dose has zero curvature '+name,abs(sum(v*doses[k] for k,v in coeff.items()))<1e-12)
        weights=rng.multinomial(100,np.full(100,.01),size=(23,4));delta=np.ones((4,100))*.03
        check('paired case bootstrap percentage-point unit',np.allclose(np.einsum('dti,ti->d',weights,delta)/4,3.))
    except BaseException:
        error=traceback.format_exc()
    summary={'status':'failed' if error else 'completed','scientific_evidence':False,'checks':checks,'source_hashes':sources,
             'wall_seconds':time.perf_counter()-start,'cpu_seconds':time.process_time()-cpu,'new_environment_steps':0,'train_iterations':0,
             'runtime':{'python':sys.version,'numpy':np.__version__},'error':error}
    (out/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
    if error:raise RuntimeError(error)
    pointer=HERE/'ANALYSIS_PREFLIGHT.json';tmp=pointer.with_suffix('.'+uuid.uuid4().hex[:8]+'.tmp')
    tmp.write_text(json.dumps({'path':str(out/'summary.json'),'sha256':sha(out/'summary.json')},indent=2),encoding='utf-8');tmp.replace(pointer)
    print(json.dumps({'status':summary['status'],'checks':len(checks),'scientific_evidence':False}),flush=True)

if __name__=='__main__':main()
