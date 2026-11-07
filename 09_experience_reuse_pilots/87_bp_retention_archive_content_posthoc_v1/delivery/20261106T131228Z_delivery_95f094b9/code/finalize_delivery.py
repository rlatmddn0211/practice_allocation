"""File-only delivery integrity, cost accounting and small reproduction bundle."""
from __future__ import annotations
import argparse
import re
import shutil
import time
import zipfile
from common import *

guard()
import numpy as np
import pandas as pd


def run(delivery,visual_review):
    import psutil
    start=time.perf_counter();delivery=Path(delivery).resolve();visual_review=Path(visual_review).resolve()
    if not delivery.is_relative_to((HERE/'delivery').resolve()):raise ValueError('Only this87 delivery can be finalized')
    status=load(delivery/'FINAL_STATUS.json')
    if status['status']=='complete':raise RuntimeError('Already delivered; preserve existing artifact')
    out=delivery/'verification'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_file_delivery_'+uuid.uuid4().hex[:8])
    out.mkdir(parents=True,exist_ok=False);shutil.copy2(Path(__file__),out/'source.py')
    inputs=Inputs();checks=Checks()
    try:
        save(out/'pre_review_status.json',status)
        review=inputs.json(visual_review,'actual visual review of PNG content')
        checks.add('visual review covers all9 figures',review['status']=='passed' and len(review['figures'])==9)
        for row in review['figures']:
            p=delivery/'figures'/row['filename']
            inputs.ref(p,'final scientific figure; matches actually viewed PNG',row['sha256'])
        shutil.copy2(visual_review,out/'visual_review.json')
        report=inputs.text(delivery/'report_ko.md','final Korean report')
        checks.add('report template fully resolved','@@' not in report)
        refs=re.findall(r'!\[[^\]]*\]\(([^)]+)\)',report)
        checks.add('report9 scientific figure links resolve',len(refs)==9 and all((delivery/p).is_file() for p in refs))
        sources=inputs.json(delivery/'source_hashes.json','exact producer code hashes')
        for name,value in sources.items():inputs.ref(delivery/name,'unchanged producer snapshot',value)
        core=Path(status['core_analysis']);ver=inputs.json(Path(status['verification'])/'FINAL_STATUS.json','passed independent verification')
        checks.add('all four requested stages complete',len(status['stages'])==4 and all(r['status']=='complete' for r in status['stages'].values()))
        checks.add('independent original-label/count/joint verification passed',ver['status']=='passed')
        # Table delivery must be lossless; additions and presentation tables are separately named.
        for p in core.iterdir():
            if p.is_file() and p.suffix in {'.csv','.parquet'}:
                checks.add('core table bytes preserved '+p.name,sha(p)==sha(delivery/'tables'/p.name))
        h=inputs.parquet(delivery/'tables/bp_160_paired_histories.parquet','all paired histories')
        r=inputs.csv(delivery/'tables/bp_fixed_initial_risk_summary.csv','risk decomposition')
        checks.add('160 paired histories retained',len(h)==160)
        expected={'BASE':(87,14,47,4),'RANDOM_PRE':(105,20,23,9),'ONSET':(113,20,15,12)}
        for a,counts in expected.items():
            q=r[r.arm==a].iloc[0]
            checks.add('risk table exact '+a,tuple(q[['all_four_success','loss_then_final_recovery','final_loss','initial_failure_final_success']].astype(int))==counts)
        w=inputs.parquet(delivery/'tables/do_window_content.parquet','all fixed DO windows')
        checks.add('25 original episodes and50 windows retained',len(w)==50 and w.source_episode_id.nunique()==25 and (w.transitions==32).all())
        e=inputs.csv(delivery/'tables/actual_interval_exposure_features.csv','actual interval exposure summary')
        checks.add('actual use each arm10227844',all(int(e[e.arm==a].actual_uses.sum())==10227844 for a in ['ONSET','RANDOM_PRE']))
        q=inputs.parquet(delivery/'tables/exposure_BP_effect_linkage.parquet','time-respecting three-contrast linkage')
        checks.add('90 time-respecting links delivered',len(q)==90 and (q.interval_end==q.exposure_latest_allowed_train_step).all())
        f=inputs.csv(delivery/'tables/BP_final_all_case_physical_summary.csv','all final physical summaries')
        checks.add('final BP all-case success and end labels preserved',
            f.set_index('arm').success_any_count.to_dict()=={'BASE':105,'ONSET':145,'RANDOM_PRE':134} and
            f.set_index('arm').episode_end_success_count.to_dict()=={'BASE':92,'ONSET':123,'RANDOM_PRE':112})
        triad=inputs.csv(delivery/'tables/BP_selected_recovery_physical_summary.csv','selected raw-path recovery summary')
        checks.add('selected recovery raw summaries have6 observations',len(triad)==6 and set(triad.relative_train_step)=={16000,32000,64000})
        checks.add('runtime/model modules absent',not FORBIDDEN&set(sys.modules))
        checks.add('all new execution counts zero',all(v==0 for v in status['new_execution'].values()))
        files=[p for p in delivery.rglob('*') if p.is_file() and '.mplconfig' not in p.parts and '__pycache__' not in p.parts]
        checks.add('no copied giant raw/model/video files',not any(p.suffix.lower() in {'.npz','.pkl','.pt','.pth','.mp4','.zip'} for p in files))
        checks.flush(out);inputs.flush(out)
        # Preserve every file-only report attempt and its actual elapsed cost.
        attempts=[]
        for p in sorted((HERE/'delivery').glob('*')):
            if not p.is_dir():continue
            if (p/'FAILED.json').is_file():
                x=load(p/'FAILED.json');attempts.append(dict(path=str(p),status='failed_file_only',wall_seconds=x.get('elapsed_seconds'),reason=x.get('error')))
            elif (p/'analysis_costs.json').is_file():
                x=load(p/'analysis_costs.json');attempts.append(dict(path=str(p),status='adopted' if p==delivery else 'preserved_prior_presentation',wall_seconds=x.get('delivery_wall_seconds')))
        cost=load(delivery/'analysis_costs.json');cost['delivery_attempts']=attempts
        early_path=Path(cost['historical_preliminary_history_audit'])
        if early_path.is_file():cost['preliminary_history_audit_costs']=load(early_path)
        proc=psutil.Process()
        cost['file_delivery_review']=dict(wall_seconds=time.perf_counter()-start,memory=proc.memory_info()._asdict(),cpu=proc.cpu_times()._asdict(),io=proc.io_counters()._asdict())
        values=[cost['core_costs']['wall_seconds'],cost['independent_verification_costs']['wall_seconds']]
        if 'preliminary_history_audit_costs' in cost:values.append(cost['preliminary_history_audit_costs']['wall_seconds'])
        values += [x['wall_seconds'] for x in attempts if x.get('wall_seconds') is not None]
        cost['recorded_analysis_process_wall_seconds_sum_before_packaging']=sum(values)+cost['file_delivery_review']['wall_seconds']
        cost['time_note']='Sum of recorded sequential analysis processes; excludes conversation/planning/visual inspection and unmetered ad-hoc file inspection. Not end-to-end user latency or GPU kernel time.'
        save(delivery/'analysis_costs.json',cost,replace=True)
        save(out/'FINAL_STATUS.json',dict(status='passed',new_execution=ZERO,checks=len(checks.rows),scope='artifact transfer, report links, numeric populations and visual-content hash identity'))
        status.update(status='complete',completed_utc=utc(),file_delivery_review=str(out),
            bundle='reproduction_bundle.zip',bundle_receipt='reproduction_receipt.json',
            interpretation='Posthoc BP signal; no causal archive attribution or general preservation method; original85 DO progression hold preserved')
        save(delivery/'FINAL_STATUS.json',status,replace=True)
        # A manifest outside itself is sufficient; the ZIP hash is recorded externally.
        manifest=[]
        for p in sorted(delivery.rglob('*')):
            if p.is_file() and '.mplconfig' not in p.parts and '__pycache__' not in p.parts and p.name not in {'artifact_manifest.jsonl','reproduction_bundle.zip','reproduction_receipt.json'}:
                manifest.append(dict(path=str(p.relative_to(delivery)).replace('\\','/'),bytes=p.stat().st_size,sha256=sha(p)))
        (delivery/'artifact_manifest.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in manifest),encoding='utf-8')
        before_pack=time.perf_counter();bundle=delivery/'reproduction_bundle.zip'
        with zipfile.ZipFile(bundle,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for r in manifest:z.write(delivery/r['path'],arcname=r['path'])
            z.write(delivery/'artifact_manifest.jsonl',arcname='artifact_manifest.jsonl')
        with zipfile.ZipFile(bundle) as z:
            if z.testzip() is not None:raise RuntimeError('Corrupt bundle')
            packed=json.loads(z.read('FINAL_STATUS.json'))
            if packed!=load(delivery/'FINAL_STATUS.json'):raise RuntimeError('Packed status differs')
        save(delivery/'reproduction_receipt.json',dict(status='complete',sha256=sha(bundle),bundle_bytes=bundle.stat().st_size,
            files=len(manifest)+1,uncompressed_artifact_bytes=sum(r['bytes'] for r in manifest),
            all_delivery_files_bytes=sum(p.stat().st_size for p in delivery.rglob('*') if p.is_file()),
            pack_and_crc_seconds=time.perf_counter()-before_pack,
            content='small derived tables/code/config/figures/receipts only; immutable raw inputs referenced by path+hash',
            current_status_in_zip=True,new_execution=ZERO))
        save(HERE/'LATEST.json',dict(status='complete',output=str(delivery),report=str(delivery/'report_ko.md'),
            core_analysis=str(core),reproduction_bundle=str(bundle),new_execution=ZERO),replace=True)
        print(json.dumps(dict(status='complete',output=str(delivery),bundle_bytes=bundle.stat().st_size,new_execution=ZERO),ensure_ascii=False),flush=True)
    except BaseException as ex:
        checks.flush(out);inputs.flush(out)
        save(out/'FAILED.json',dict(error=repr(ex),new_execution=ZERO,elapsed_seconds=time.perf_counter()-start));raise


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--delivery',required=True);ap.add_argument('--visual-review',required=True);a=ap.parse_args()
    run(a.delivery,a.visual_review)
