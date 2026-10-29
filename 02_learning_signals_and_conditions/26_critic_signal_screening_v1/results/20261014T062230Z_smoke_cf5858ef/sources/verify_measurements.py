"""Independent NumPy reconstruction of saved per-transition critic evidence."""
import argparse
import csv
import gzip
import traceback
from collections import defaultdict
from pathlib import Path
import numpy as np
from common import Run

def main():
    ap=argparse.ArgumentParser();ap.add_argument('measure_dir');args=ap.parse_args()
    run=Run('verify_measurements')
    try:
        source=Path(args.measure_dir)
        summary=run.read(source/'summary.json')
        run.check('measurement completed',summary['status']=='completed')
        manifests=run.read(source/'snapshot_manifest.json')
        recorded=run.rows(source/'task_diagnostics.csv')
        bykey={(r['id'],r['task'],r['panel']):r for r in recorded}
        protocol=run.read(source/'sources/protocol.json')
        total=0;max_target_difference=0.
        for i,entry in enumerate(manifests):
            path=Path(entry['raw_path']);run.hashed(path,entry['raw_sha256'])
            with gzip.open(path,'rt',encoding='utf-8',newline='') as f:
                grouped=defaultdict(list)
                for r in csv.DictReader(f):grouped[(int(r['task']),int(r['panel']))].append(r)
            run.check('eight panels '+entry['id'],len(grouped)==8)
            episodes={}
            for (ti,pi),rows in grouped.items():
                a={k:np.array([float(r[k]) for r in rows]) for k in rows[0]}
                total+=len(rows)
                run.check('1024 samples '+entry['id']+str((ti,pi)),len(rows)==1024)
                run.check('unique transitions',np.unique(a['storage_index']).size==1024)
                episodes[ti,pi]=set(((a['birth_step']-1)//500).astype(int))
                mask=1-a['done']*(1-a['timeout'])
                targets=np.array([a['reward']+a['gamma']*mask*(a['next_min_q_'+str(k)]-a['alpha']*a['next_logp_'+str(k)]) for k in range(4)])
                error=float(np.max(np.abs(targets.mean(0)-a['target'])))
                max_target_difference=max(max_target_difference,error)
                run.check('soft Bellman target '+entry['id']+str((ti,pi)),np.allclose(targets.mean(0),a['target'],atol=2e-4,rtol=2e-6),error)
                run.check('target action variation',np.allclose(targets.std(0,ddof=1),a['target_mc_sd'],atol=2e-4,rtol=2e-5))
                q0,q1,y=a['q0'],a['q1'],a['target']
                resid=np.sqrt(np.mean(np.concatenate([(q0-y)**2,(q1-y)**2])))
                gap=np.linalg.norm(q0-q1)/np.sqrt(len(rows))
                scale=max(np.linalg.norm(y)/np.sqrt(len(rows)),1e-6)
                expected={'residual_rms':resid,'gap_rms':gap,'target_rms':scale,'residual_normalized':resid/scale,
                          'gap_normalized':gap/scale,'reward_rms':np.sqrt(np.mean(a['reward']**2)),
                          'q_mean':np.mean((q0+q1)/2),'target_mean':y.mean(),'target_mc_sd_mean':a['target_mc_sd'].mean(),
                          'timeout_count':a['timeout'].sum(),'sample_count':len(rows)}
                task=protocol['suites'][entry['suite']][ti];panel='M' if pi==0 else 'A'
                old=bykey[entry['id'],task,panel]
                for name,value in expected.items():
                    run.check('recompute '+entry['id']+task+panel+name,np.isclose(float(old[name]),value,atol=1e-9,rtol=1e-9),{'stored':float(old[name]),'recomputed':float(value)})
            for ti in range(4):run.check('episode exclusion '+entry['id']+str(ti),not episodes[ti,0]&episodes[ti,1])
            if (i+1)%32==0:print('verified',i+1,flush=True)
        run.check('all samples reconciled',total==summary['transitions_measured'])
        # Meaningful terminal/timeout edge cases independent of the stored all-timeout episodes.
        done=np.array([0.,1.,1.]);timeout=np.array([0.,0.,1.])
        run.check('terminal vs timeout targets',np.allclose(2+.99*(1-done*(1-timeout))*3,[4.97,2,4.97]))
        run.finish({'status':'completed','source':str(source),'snapshots':len(manifests),'raw_transitions':total,
                    'max_float32_target_reconstruction_difference':max_target_difference,'technical_smoke_source':summary['technical_smoke']})
    except Exception:
        run.finish({'status':'failed','traceback':traceback.format_exc()});raise

if __name__=='__main__':main()
