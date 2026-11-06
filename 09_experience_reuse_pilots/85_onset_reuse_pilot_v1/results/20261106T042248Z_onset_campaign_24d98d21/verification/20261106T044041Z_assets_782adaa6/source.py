"""Supplemental immutable dependency/asset and analysis syntax checks, no runtime calls."""
from __future__ import annotations
import sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from common import *
guard_file_only()
import argparse
import numpy as np
import pandas as pd

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--campaign',type=Path,required=True);args=ap.parse_args();campaign=args.campaign.resolve()
    out=campaign/'verification'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_assets_'+uuid.uuid4().hex[:8]);out.mkdir(parents=True,exist_ok=False)
    shutil.copy2(__file__,out/'source.py');inputs=Inputs();started=time.perf_counter();checks=[]
    def ck(name,v,scope=''):
        checks.append(dict(check=name,passed=bool(v),scope=scope))
        if not v:raise RuntimeError(name+': '+scope)
    try:
        baseline=inputs.json(CAMPAIGN/'baseline_manifest.json','all pinned installed source paths')
        receipt=inputs.json(CAMPAIGN/'input_receipt.json','original fixed source/XML/mesh reference hashes')
        checked=set()
        for row in receipt['files']:
            path=Path(row['path']);inputs.ref(path,'original input receipt full reference audit',expected=row['sha256']);checked.add(str(path.resolve()))
        for path,digest in baseline['code_hashes'].items():
            inputs.ref(path,'all pinned baseline implementation and installed package source hashes',expected=digest);checked.add(str(Path(path).resolve()))
        config=load(campaign/'campaign_config.json');prep=Path(config['preparation'])
        positive=inputs.parquet(prep/'source_success_episodes.parquet','source success archive original normalization audit')
        for row in positive.itertuples(index=False):
            z=inputs.npz(row.trajectory_ref,'original stored executed versus pre-transform action')
            scaled=(2*((z['action_pre_transform']+np.float32(1))/np.float32(2))-np.float32(1)).astype(np.float32)
            ck('archive executed action equals original buffer normalized action',np.array_equal(scaled,z['action_executed']),row.permanent_episode_id)
        for path in sorted(Path(__file__).parent.glob('*.py')):
            compile(path.read_text(encoding='utf-8'),str(path),'exec');inputs.ref(path,'syntax-checked file-only analysis/report code')
            ck('analysis/report source parses',True,path.name)
        from analysis_contract import analysis_checks
        checks.extend(analysis_checks())
        # Explicit missing-value macro and join-risk fixtures, independent of outcomes.
        frame=pd.DataFrame({'x':[.1,np.nan,.3]})
        ck('macro summary must not skip missing task',np.isnan(frame.x.to_numpy(dtype=float).mean()))
        initial=pd.DataFrame({'parent':['R01'],'task':['DO'],'case':['DO_E00'],'initial_label':[0]})
        final=pd.DataFrame({'parent':['R01'],'task':['DO'],'case':['DO_E00'],'final_label':[1]})
        joined=final.merge(initial,on=['parent','task','case'],validate='many_to_one')
        ck('label-changing case retained by identity join',len(joined)==1 and joined.initial_label.iloc[0]==0 and joined.final_label.iloc[0]==1)
        save(out/'FINAL_STATUS.json',dict(status='passed',original_reference_files=len(checked),success_archive_episodes=len(positive),
            checks=len(checks),new_execution=ZERO_EXECUTION,source_hashes_unchanged=True))
        print(json.dumps(dict(output=str(out),files=len(checked),checks=len(checks),status='passed')),flush=True)
    except BaseException as ex:
        save(out/'FAILED.json',dict(error=repr(ex),new_execution=ZERO_EXECUTION));raise
    finally:
        inputs.flush(out);pd.DataFrame(checks).to_csv(out/'verification_checks.csv',index=False)
        save(out/'costs.json',dict(wall_seconds=time.perf_counter()-started,tracked_read_bytes=inputs.bytes_read,new_execution=ZERO_EXECUTION))

if __name__=='__main__':main()
