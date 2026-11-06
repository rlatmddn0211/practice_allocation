"""Outcome-independent publication selection for the completed85 campaign."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
VERSION='85_onset_reuse_pilot_v1'
GROUP='09_experience_reuse_pilots'
PUBLIC=GROUP+'/'+VERSION
CAMPAIGN_ID='20261106T042248Z_onset_campaign_24d98d21'
CAMPAIGN=ROOT/VERSION/'results'/CAMPAIGN_ID
ANALYSIS=CAMPAIGN/'analysis/20261106T111509Z_paired_3db89d3f'
PREP=ROOT/VERSION/'results/20261106T040844Z_preparation_31c9735e'
SMALL={'.py','.json','.jsonl','.csv','.md','.txt','.log','.parquet','.png','.svg','.npz','.bin'}


def selections():
    selected={};media=[];sources=[]
    def add(path,target=None,role='original85 result'):
        path=Path(path)
        if not path.is_file() or '__pycache__' in path.parts or '.mplconfig' in path.parts:return
        target=target or GROUP+'/'+path.relative_to(ROOT).as_posix()
        previous=selected.get(target)
        if previous and previous['source']!=str(path):raise RuntimeError('Duplicate publication target '+target)
        selected[target]=dict(source=str(path),public_path=target,bytes=path.stat().st_size,role=role)
    def folder(path,role,zip_ok=False):
        for p in Path(path).rglob('*'):
            if p.is_file() and p.suffix in SMALL|({'.zip'} if zip_ok else set()):add(p,role=role)
    base=ROOT/VERSION
    for p in base.iterdir():
        if p.is_file() and p.suffix in {'.py','.json','.md'}:add(p,role='runtime source or pointer')
    folder(base/'baseline81','exact original81 runtime source')
    folder(base/'analysis_tools','analysis and audit code')
    folder(ANALYSIS,'immutable complete analysis and verification',zip_ok=True)
    for name in ['20261106T040104Z_preparation_414ba39d','20261106T040844Z_preparation_31c9735e',
        '20261106T040755Z_initial_state_mapping_audit_44a7c57f','20261106T040440Z_independent_verification_0f40a039',
        '20261106T040923Z_independent_verification_579af5f1']:
        folder(base/'results'/name,'preparation including preserved corrected attempt')
    technical=base/'results/20261106T041847Z_technical_validation_4f512db1'
    for p in technical.rglob('*'):
        if p.is_file() and p.suffix in SMALL-{'.npz'}:add(p,role='technical receipts and cost ledger; model payload excluded')
    for p in CAMPAIGN.iterdir():
        if p.is_file() and p.suffix in SMALL:add(p,role='frozen plan and final campaign status')
    folder(CAMPAIGN/'source_snapshot','frozen research source snapshot')
    folder(CAMPAIGN/'postprocessing','analysis execution receipts')
    folder(CAMPAIGN/'verification','preserved file-only and delivery audits')
    adopted=json.loads((ANALYSIS/'adopted_jobs.json').read_text(encoding='utf-8'))
    for item in adopted:
        attempt=Path(item['attempt']);job=attempt.parent
        for p in job.iterdir():
            if p.is_file() and p.suffix in SMALL:add(p,role='job adoption or completion metadata')
        for p in attempt.iterdir():
            if p.is_file() and p.suffix in SMALL:add(p,role='attempt provenance and resource counters')
        for section in ['costs','evaluation_episodes','evaluation_receipts','episodes','schema']:
            folder(attempt/section,'actual results, schema or costs')
        for p in (attempt/'checkpoints').rglob('*.json'):add(p,role='checkpoint metadata; payload stays local')
        for p in (attempt/'archive_usage').rglob('*'):
            if p.is_file() and p.suffix in {'.json','.parquet'}:add(p,role='actual archive exposure at fixed checkpoints')
        if item['kind']=='branch':
            for p in (attempt/'videos').iterdir():
                if p.suffix in {'.mp4','.json'}:add(p,role='pre-outcome selected final evaluation media')
                if p.suffix=='.mp4':
                    trace=attempt/'evaluation_transitions'/(p.stem+'.npz')
                    for q in [trace,trace.with_suffix('.json')]:add(q,role='original numeric trajectory corresponding to fixed video')
                    media.append(dict(parent_id=item['parent_id'],future_id=item['future_id'],arm=item['arm'],
                        episode_id=p.stem,video=GROUP+'/'+p.relative_to(ROOT).as_posix(),
                        numeric_trajectory=GROUP+'/'+trace.relative_to(ROOT).as_posix(),selection='frozen first two physical cases/task, final64k'))
        else:
            for p in (attempt/'evaluation_transitions').glob('*_DO_*.npz'):
                add(p,role='all80 shared-start DO trajectories for initial-coordinate correction')
                add(p.with_suffix('.json'),role='shared-start DO numeric metadata')
    episodes=pd.read_parquet(PREP/'source_success_episodes.parquet')
    for row in episodes.to_dict('records'):
        original=Path(row['trajectory_ref']);target=PUBLIC+'/source_episode_subset/'+row['donor_run']+'/'+original.name
        add(original,target,'all31 original successful training DO source episodes; not evaluation')
        add(original.with_suffix('.json'),str(Path(target).with_suffix('.json')).replace('\\','/'),'source trajectory sidecar')
        sources.append(dict(permanent_episode_id=row['permanent_episode_id'],donor_run=row['donor_run'],
            original_path=str(original),public_path=target,source_role='original81 DO training, complete through1M'))
    if len(media)!=240 or len(sources)!=31:raise RuntimeError('Publication selection coverage differs')
    rows=sorted(selected.values(),key=lambda r:r['public_path'])
    if sum(r['bytes'] for r in rows)>512*1024**2:raise RuntimeError('Unexpected publication payload size; review selection')
    return rows,media,sources


if __name__=='__main__':
    rows,media,sources=selections()
    print(json.dumps(dict(files=len(rows),bytes=sum(r['bytes'] for r in rows),videos=len(media),source_episodes=len(sources))))
