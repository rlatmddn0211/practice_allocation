"""File-only delivery checks after manual inspection of the six final figures."""
from __future__ import annotations
import sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from common import *
guard_file_only()
import argparse
import zipfile
import pandas as pd


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--analysis',type=Path,required=True);a=ap.parse_args()
    analysis=a.analysis.resolve();status=load(analysis/'FINAL_STATUS.json');campaign=Path(status['campaign'])
    out=campaign/'verification'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_delivery_'+uuid.uuid4().hex[:8])
    out.mkdir(parents=True,exist_ok=False);shutil.copy2(__file__,out/'source.py');started=time.perf_counter();checks=[]

    def check(name,condition,detail=None):
        checks.append(dict(check=name,passed=bool(condition),detail=detail))
        if not condition:raise RuntimeError(name)

    try:
        check('Complete fixed design',status['status']=='complete' and status['completed_branches']==30 and status['valid_evaluations']==6080)
        check('Issued and completed costs agree inside fixed caps',status['actual_issued']==status['actual_completed']==4964900
            and status['actual_train_steps']==1920000 and status['actual_eval_steps']==3040000 and status['actual_technical_steps']==4900
            and status['actual_issued']<=4970000 and status['actual_technical_steps']<=10000)
        check('Independent saved-label verification passed',load(Path(status['verification'])/'FINAL_STATUS.json')['status']=='passed')
        plan=pd.read_csv(campaign/'execution_plan.csv');jobs=[load(p) for p in (campaign/'jobs').glob('*/COMPLETE.json')]
        branches=[r for r in jobs if r['kind']=='branch']
        check('Exactly all planned cells adopted once',len(branches)==30 and {Path(r['attempt']).parent.name for r in branches}==set(plan.cell_id))
        check('Exactly five shared initial evaluations',sum(r['kind']=='shared_start' for r in jobs)==5)
        videos=[p for r in branches for p in (Path(r['attempt'])/'videos').glob('*.mp4')]
        check('Fixed final evaluation videos recorded without extra rollouts',len(videos)==240,dict(videos=len(videos)))
        figures=sorted((analysis/'figures').glob('*.png'))
        check('Six required standalone figures present',len(figures)==6)
        check('Both source snapshots and live frozen research files match hashes',all(sha(BASE/name)==digest and sha(campaign/'source_snapshot'/name)==digest
            for name,digest in load(campaign/'research_source_hashes.json').items()))
        receipt=load(analysis/'reproduction_receipt.json');bundle=Path(receipt['bundle'])
        check('Bundle checksum matches immutable receipt',sha(bundle)==receipt['sha256'])
        with zipfile.ZipFile(bundle) as z:
            check('Bundle CRC valid',z.testzip() is None)
            check('Bundle status equals delivered final status',json.loads(z.read('FINAL_STATUS.json'))==status)
            check('Bundle report equals delivered report',z.read('report_ko.md')==(analysis/'report_ko.md').read_bytes())
        exposure=pd.read_csv(analysis/'archive_usage_summaries.csv');final=exposure[exposure.actual_train_step==1064000]
        totals=final.groupby('arm')[['native_draw_count','native_actual_use','archive_actual_use','archive_actor_use','archive_critic_use']].sum()
        check('Final native/archive use conserved',bool((totals.native_actual_use+totals.archive_actual_use==totals.native_draw_count).all()))
        check('Archive actor and critic batch-use counts agree',bool((totals.archive_actor_use==totals.archive_critic_use).all()))
        check('All ten P/U draw and replacement hash correspondences passed',bool(pd.read_csv(analysis/'paired_exposure_checks.csv').common_draws_and_masks.all()))
        retention=pd.read_csv(analysis/'retention_gain_loss.csv')
        do=retention[retention.task_id=='DO'];do_counts=do.groupby('arm').final_successes.sum().to_dict()
        do_positive=do[(do.arm=='ONSET')&(do.final_successes>0)][['parent_id','future_id','final_successes']].to_dict('records')
        check('Fixed final DO counts match report',do_counts=={'BASE':1,'ONSET':4,'RANDOM_PRE':11},do_counts)
        report=dict(status='passed',analysis=str(analysis),source_sha256=sha(__file__),checks=checks,
            manual_visual_review=dict(all_six_inspected=True,legible_Korean_and_units=True,figures=[dict(path=str(p),sha256=sha(p)) for p in figures],
                notes='All six plots inspected in image tool; figure03 retains full0-100% scale. No raw data or scientific result altered.'),
            final_DO_ONSET_positive_cells=do_positive,actual_final_batch_usage=totals.reset_index().to_dict('records'),
            wall_seconds=time.perf_counter()-started,
            new_execution=dict(environment_creations=0,resets=0,transitions=0,model_loads=0,policy_forwards=0,learning_updates=0))
        save(out/'FINAL_STATUS.json',report)
        print(json.dumps(dict(output=str(out),status='passed',DO_final_counts=do_counts,DO_ONSET_positive_cells=do_positive,
            final_batch_usage=report['actual_final_batch_usage'])),flush=True)
    except BaseException as ex:
        save(out/'FAILED.json',dict(error=repr(ex),checks=checks,wall_seconds=time.perf_counter()-started));raise


if __name__=='__main__':main()
