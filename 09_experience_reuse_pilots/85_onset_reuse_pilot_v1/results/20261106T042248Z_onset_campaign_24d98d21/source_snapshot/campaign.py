"""Fixed two-worker queue; every completed valid cell is executed exactly once."""
from __future__ import annotations
from common import *
import argparse
import subprocess

def research_hashes():
    files=list(HERE.glob('*.py'))+[HERE/'protocol_resolved.json']+list((HERE/'baseline81').rglob('*.py'))+list((HERE/'baseline81/configs').glob('*.json'))
    return {p.relative_to(HERE).as_posix():sha(p) for p in sorted(files) if '__pycache__' not in p.parts}

def physical_costs(campaign):
    counters={'train':0,'post_eval':0,'start_eval':0,'technical':0};completed={k:0 for k in counters}
    for path in Path(campaign).rglob('*_control_journal.bin'):
        category=path.name.replace('_control_journal.bin','')
        if category not in counters:continue
        data=path.read_bytes();counters[category]+=data.count(b'I');completed[category]+=data.count(b'C')
    # Technical validation is separate from the campaign folder but charged once.
    for path in (HERE/'results').glob('*technical_validation*/costs/technical_control_journal.bin'):
        data=path.read_bytes();counters['technical']+=data.count(b'I');completed['technical']+=data.count(b'C')
    return dict(issued=counters,completed=completed,total_issued=sum(counters.values()),total_completed=sum(completed.values()),remaining=4970000-sum(counters.values()))

def status(campaign,stage):
    campaign=Path(campaign);jobs=campaign/'jobs'
    complete=[load(p) for p in jobs.glob('*/COMPLETE.json')]
    running=[];failed=[]
    for p in jobs.glob('*/status.json'):
        row=load(p)
        if row.get('state')=='failed':failed.append(row)
        elif row.get('state')!='complete':running.append(row)
    value=dict(stage=stage,at=utc(),completed_branches=sum(r['kind']=='branch' for r in complete),planned_branches=30,
        completed_shared_parents=sum(r['kind']=='shared_start' for r in complete),completed_evaluation_episodes=sum(r['evaluation_episodes'] for r in complete),
        running=running,failures=failed,costs=physical_costs(campaign))
    save(campaign/'status.json',value,replace=True)
    (campaign/'RUNNING_STATUS.md').write_text('# 진행 상태\n\n'+json.dumps(clean(value),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return value

def prepare():
    prep=Path(load(HERE/'LATEST_PREPARATION.json')['output']);tech=Path(load(HERE/'LATEST_TECHNICAL.json')['output'])
    if not load(prep/'readiness.json')['archive_support_all_receivers'] or load(tech/'FINAL_STATUS.json')['status']!='passed':raise RuntimeError('Preparation/technical gates not passed')
    if str(prep)!=load(tech/'FINAL_STATUS.json')['preparation']:raise RuntimeError('Technical validation used another archive')
    # Every runtime module below was part of the passing technical source snapshot.
    tech_source=load(tech/'source_hashes.json')
    for name in ('common.py','detector.py','sampler_contract.py','pilot_runtime.py','pilot_evaluation.py'):
        if sha(HERE/name)!=tech_source[name]['sha256']:raise RuntimeError('Runtime changed after technical certification: '+name)
    out=new_output('onset_campaign')
    shutil.copy2(prep/'execution_plan.csv',out/'execution_plan.csv')
    shutil.copy2(prep/'seed_manifest.json',out/'seed_manifest.json')
    save(out/'research_source_hashes.json',research_hashes())
    payload_bytes=sum(p.stat().st_size for p in (CAMPAIGN/'runs/R01/checkpoints/full/1000000').glob('*') if p.is_file())
    estimate=payload_bytes*30*16+8_000_000_000
    free=shutil.disk_usage(ROOT).free
    if estimate>free:raise RuntimeError('Insufficient preflight disk without deleting original data')
    save(out/'campaign_config.json',dict(preparation=str(prep),technical=str(tech),worker_count=2,
        concurrent_assignment='global fixed seeded order, first two jobs then next whenever a slot completes; one CUDA device, no arm-specific device',
        additional_full_every=4000,additional_full_reason='4k native block barriers limit nonrecoverable repeated work under remaining 5.1k technical/failure reserve',
        checkpoint_extra_storage_estimate_bytes=estimate,free_disk_bytes=free,normal_new_steps=4960000,total_new_cap=4970000,
        original_campaign_cost_not_recounted=6604850))
    save(out/'FINAL_STATUS.json',dict(status='prepared_not_started',completed_branches=0,planned_branches=30),replace=True)
    save(HERE/'ACTIVE_CAMPAIGN.json',dict(campaign=str(out),preparation=str(prep),technical=str(tech),created_at=utc()),replace=True)
    status(out,'prepared')
    print(json.dumps(dict(campaign=str(out))),flush=True)

def run(campaign):
    import pandas as pd
    campaign=Path(campaign).resolve();config=load(campaign/'campaign_config.json')
    def launch(args,key):
        dest=campaign/'launches'/key;dest.mkdir(parents=True,exist_ok=False)
        stdout=(dest/'stdout.log').open('wb');stderr=(dest/'stderr.log').open('wb')
        proc=subprocess.Popen([sys.executable,'-X','utf8',str(HERE/'worker.py'),'--campaign',str(campaign),*args],cwd=ROOT,stdout=stdout,stderr=stderr)
        save(dest/'process.json',dict(pid=proc.pid,started=utc(),arguments=args))
        return proc,stdout,stderr
    # Initial evaluation is an immutable shared observation, never reissued per arm.
    for parent in RUNS:
        key='START_'+parent
        if (campaign/'jobs'/key/'COMPLETE.json').exists():continue
        proc,stdout,stderr=launch(['--start-parent',parent],key)
        while proc.poll() is None:
            status(campaign,'shared_start_evaluation');time.sleep(15)
        stdout.close();stderr.close()
        if proc.returncode!=0:raise RuntimeError('Shared-start worker failed: '+parent)
        status(campaign,'shared_start_evaluation')
    plan=pd.read_csv(campaign/'execution_plan.csv').sort_values('execution_order').to_dict('records')
    pending=[r for r in plan if not (campaign/'jobs'/r['cell_id']/'COMPLETE.json').exists()]
    active=[]
    while pending or active:
        while pending and len(active)<config['worker_count']:
            row=pending.pop(0);proc,out,err=launch(['--cell',row['cell_id']],row['cell_id']);active.append((row,proc,out,err))
        for item in list(active):
            row,proc,out,err=item
            if proc.poll() is None:continue
            out.close();err.close();active.remove(item)
            if proc.returncode!=0:
                # Other already-running fixed cells may finish; no new cells or retries are launched.
                for _,other,_,_ in active:other.wait()
                raise RuntimeError('Research worker requires integrity review: '+row['cell_id'])
        current=status(campaign,'research')
        if current['costs']['total_issued']>4970000:raise RuntimeError('All-attempt cap exceeded')
        if active:time.sleep(15)
    result=status(campaign,'research_complete_pending_analysis')
    save(campaign/'RESEARCH_COMPLETE.json',result)
    save(campaign/'FINAL_STATUS.json',dict(status='research_complete_pending_analysis',**result),replace=True)
    print(json.dumps(dict(campaign=str(campaign),completed=30,costs=result['costs'])),flush=True)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','run']);ap.add_argument('--campaign',type=Path);a=ap.parse_args()
    if a.action=='prepare':prepare()
    else:
        try:run(a.campaign)
        except BaseException as ex:
            status(a.campaign,'integrity_stop');save(a.campaign/'FAILED_OR_INTERRUPTED.json',dict(error=repr(ex),at=utc()));raise

if __name__=='__main__':main()
