"""Aggregate existing process/cost receipts without model or environment imports."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime
from pathlib import Path


def summarize(campaign, technical, episodes, output):
    campaign=Path(campaign);technical=Path(technical);output=Path(output)
    inputs=[]

    def read(path):
        path=Path(path);data=path.read_bytes()
        inputs.append(dict(path=str(path),bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
        return json.loads(data)

    jobs=[];resets={};checkpoint_seconds=0.;checkpoint_bytes=0;checkpoint_writes=0;expected_evaluations=0
    starts=[];ends=[];devices=set()
    for path in sorted((campaign/'jobs').glob('*/COMPLETE.json')):
        meta=read(path);attempt=Path(meta['attempt']);kind=meta['kind'];resources=meta['resource_costs']
        expected_evaluations+=meta['evaluation_episodes']
        launch=read(campaign/'launches'/path.parent.name/'process.json')
        starts.append(datetime.fromisoformat(launch['started']));ends.append(datetime.fromisoformat(meta['completed_at']))
        runtime=read(attempt/'runtime.json');devices.add(runtime.get('gpu','unavailable'))
        cpu=resources['cpu'];io=resources['io'];memory=resources['memory']
        jobs.append(dict(job_id=path.parent.name,kind=kind,parent_id=meta['parent_id'],arm=meta.get('arm'),
            wall_seconds=meta['wall_seconds'],cpu_seconds=cpu['user']+cpu['system'],
            peak_process_working_set_bytes=memory.get('peak_wset',memory['rss']),
            endpoint_process_rss_bytes=memory['rss'],io_read_bytes=io['read_bytes'],io_write_bytes=io['write_bytes']))
        for receipt in sorted((attempt/'costs').glob('*_costs.json')):
            cost=read(receipt);category=cost['category']
            row=resets.setdefault(category,dict(reset_calls=0,environment_creations=0,step_call_seconds=0.,step_calls=0))
            row['reset_calls']+=cost['resets'];row['environment_creations']+=cost['creations']
            row['step_call_seconds']+=cost['step_call_seconds'];row['step_calls']+=cost['step_calls']
        checkpoint_log=attempt/'checkpoint_io.jsonl'
        if checkpoint_log.exists():
            data=checkpoint_log.read_bytes()
            inputs.append(dict(path=str(checkpoint_log),bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
            for line in data.splitlines():
                row=json.loads(line);checkpoint_writes+=1;checkpoint_seconds+=row['seconds'];checkpoint_bytes+=row['bytes']
    technical_receipt=technical/'costs/technical_costs.json'
    if technical_receipt.exists():
        cost=read(technical_receipt)
        resets['technical']=dict(reset_calls=cost['resets'],environment_creations=cost['creations'],
            step_call_seconds=cost['step_call_seconds'],step_calls=cost['step_calls'])
    groups={}
    for kind in ('shared_start','branch'):
        selected=[r for r in jobs if r['kind']==kind]
        groups[kind]=dict(jobs=len(selected),job_wall_seconds_sum=sum(r['wall_seconds'] for r in selected),
            process_cpu_seconds_sum=sum(r['cpu_seconds'] for r in selected))
    if len(episodes)!=expected_evaluations:
        raise RuntimeError('Resource timing scope differs from adopted complete evaluation episodes')
    evaluation_seconds=float(episodes['wall_seconds'].sum())
    summary=dict(normal_queue_elapsed_seconds=(max(ends)-min(starts)).total_seconds(),
        normal_queue_started_utc=min(starts).isoformat(),normal_queue_completed_utc=max(ends).isoformat(),
        jobs=groups,normal_job_wall_seconds_sum=sum(r['wall_seconds'] for r in jobs),
        recorded_evaluation_episode_wall_seconds_sum=evaluation_seconds,
        non_evaluation_job_seconds_including_restore_checkpoint_and_logging=sum(r['wall_seconds'] for r in jobs)-evaluation_seconds,
        process_cpu_seconds_sum=sum(r['cpu_seconds'] for r in jobs),
        max_individual_process_peak_working_set_bytes=max(r['peak_process_working_set_bytes'] for r in jobs),
        normal_job_io_read_bytes_sum=sum(r['io_read_bytes'] for r in jobs),
        normal_job_io_write_bytes_sum=sum(r['io_write_bytes'] for r in jobs),
        full_checkpoint_writes=checkpoint_writes,full_checkpoint_write_seconds_sum=checkpoint_seconds,
        full_checkpoint_bytes_written_sum=checkpoint_bytes,cost_categories=resets,
        gpu_devices=sorted(devices),maximum_configured_concurrent_research_jobs=2,
        limits=['Process wall/CPU sums overlap across concurrent jobs; do not add them to queue elapsed time.',
            'Evaluation episode time includes policy inference, rendering and output; rendering-only time unavailable.',
            'Non-evaluation job time includes restoration, learning, logging and checkpoint I/O; not pure learning kernel time.',
            'Recorded reset calls count outer environment constructions; internal reset physics calls/substeps unmeasured.',
            'Working set is host process memory, not GPU VRAM; GPU peak memory/kernel-only time unavailable.',
            'Step-call elapsed time is not physics-kernel-only compute time.'])
    (output/'compute_resources.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (output/'job_resource_costs.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in jobs),encoding='utf-8')
    (output/'resource_input_manifest.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in inputs),encoding='utf-8')
    return summary
