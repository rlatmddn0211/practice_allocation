"""Synthetic known-answer checks of all automatic scientific summaries."""
import argparse
import csv
import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from campaign import ROOT, REPO, STAGES, LABELS, stamp, write, read, sha, stage_hashes


def worker(request_path):
    request=read(request_path)
    sys.path.insert(0,str(REPO/STAGES[request['stage']]))
    from analyze_stage import analyze
    result=analyze(request,Path(request['output']))
    write(Path(request['output'])/'result.json',result)


def main():
    directory=ROOT/'results'/(stamp()+'_analysis_verification_'+uuid.uuid4().hex[:6])
    directory.mkdir(parents=True,exist_ok=False)
    shutil.copy2(__file__,directory/'source_snapshot.py')
    write(directory/'source_hashes.json',{s:stage_hashes(REPO/d) for s,d in STAGES.items()})
    results={}
    for stage in STAGES:
        out=directory/stage
        out.mkdir()
        inputs=out/'synthetic_inputs'
        inputs.mkdir()
        references=[]
        def record(value):
            path=inputs/f'{len(references):04}.json'
            write(path,value)
            references.append({'path':str(path),'sha256':sha(path)})
            return value
        def evaluate(suite,seed,cp,role,allocation='U',repeat=0,horizon=0,offset=0):
            labels=LABELS[suite]
            rates=dict(zip(labels,[.2,.6,.4,.9]))
            if role=='branch':
                if stage=='E2':
                    rates['DO']+=offset
                else:
                    rates={task:round(value+offset,8) for task,value in rates.items()}
            path=inputs/f'{len(references):04}_episodes.csv'
            with path.open('x',newline='',encoding='utf-8') as stream:
                writer=csv.DictWriter(stream,fieldnames=['task','episode_index','initial_state_hash','success'])
                writer.writeheader()
                for task,rate in rates.items():
                    for index in range(100):
                        writer.writerow(dict(task=task,episode_index=index,initial_state_hash=f'{suite}_{task}_{index}',success=int(index<round(100*rate))))
            return record(dict(id=f'synthetic_{len(references)}',stage=stage,suite=suite,original_seed=seed,checkpoint_step=cp,
                kind='evaluate',role=role,allocation=allocation,continuation_label=repeat,horizon=horizon,
                evaluation={'success_by_task':rates,'macro_success':sum(rates.values())/4},episodes_path=str(path),episodes_sha256=sha(path)))
        suites=['B','C'] if stage=='E3' else ['A']
        seeds=[901] if stage=='E0' else [11,12,13]
        for suite in suites:
            for seed in seeds:
                for cp in ([200000,400000] if stage=='E1' else [200000]):
                    evaluate(suite,seed,cp,'baseline')
                    if stage!='E2':
                        record(dict(id=f'rule_{suite}_{seed}_{cp}',kind='rules',stage=stage,suite=suite,original_seed=seed,checkpoint_step=cp,
                                    rules={'Failure':'F_DO','Progress':'U'}))
                    if stage=='E0':
                        evaluate(suite,seed,cp,'public')
                    repeats=[1901,1902,1903,1904,1905] if stage=='E0' else [2101,2102,2103]
                    allocations=['U','DC_plus_WO_minus','DC_minus_WO_plus'] if stage=='E2' else ['U']+['F_'+t for t in LABELS[suite]]
                    for repeat in repeats:
                        for allocation in allocations:
                            for horizon in ([40000] if stage=='E0' else [20000,40000]):
                                if stage=='E0':
                                    offset={1901:.10,1902:0,1903:.04,1904:.06,1905:.08}[repeat] if allocation=='F_DC' else 0
                                elif stage=='E2':
                                    offset={'U':0,'DC_plus_WO_minus':.1,'DC_minus_WO_plus':-.1}[allocation]
                                else:
                                    offset={11:.04,12:.02,13:-.01}[seed] if allocation=='F_'+LABELS[suite][1] else 0
                                evaluate(suite,seed,cp,'branch',allocation,repeat,horizon,offset)
        request={'stage':stage,'output':str(out),'analysis_inputs':references}
        if stage=='E3':
            request['suite_A_reference']={'path':str(directory/'E1/result.json'),'sha256':sha(directory/'E1/result.json')}
        write(out/'request.json',request)
        with (out/'stdout.log').open('xb') as log:
            proc=subprocess.run([sys.executable,__file__,'--worker',str(out/'request.json')],stdout=log,stderr=subprocess.STDOUT)
        assert proc.returncode==0, str(out/'stdout.log')
        data=read(out/'analysis.json')
        if stage=='E0':
            value=next(r for r in data['summaries'] if r['cohort']=='replication_1903_1905' and r['contrast']=='F_DC minus U / macro')
            assert abs(value['equal_seed_mean_pp']-6)<1e-9 and value['original_seed_count']==1
        if stage=='E1':
            value=next(r for r in data['summaries'] if r['horizon']==40000 and r['contrast']=='F_DC minus U / macro')
            assert abs(value['equal_seed_mean_pp']-5/3)<1e-9 and value['original_seed_count']==3
            assert value['seed_min_pp']<0 and value['positive_seed_count']==2
            with (out/'held_out_rule_results.csv').open(newline='',encoding='utf-8') as stream:
                rules=list(csv.DictReader(stream))
            assert all(r['choice']=='F_DC' for r in rules if r['original_seed']=='13' and r['rule']=='LOSO_global_fixed')
            assert all(r['choice']=='U' for r in rules if r['original_seed']=='13' and r['rule']=='cross_repeat_diagnostic')
        if stage=='E2':
            value=next(r for r in data['summaries'] if r['horizon']==40000 and r['contrast']=='DC_plus_WO_minus minus DC_minus_WO_plus / DO')
            assert abs(value['equal_seed_mean_pp']-20)<1e-9 and value['original_seed_count']==3
        if stage=='E3':
            with (out/'held_out_rule_results.csv').open(newline='',encoding='utf-8') as stream:
                rows=list(csv.DictReader(stream))
            assert not any(row['suite']=='C' and row['rule']=='Fixed_DC' for row in rows)
            assert (out/'shared_task_changes.csv').is_file()
            with (out/'composition_original_seed_results.csv').open(newline='',encoding='utf-8') as stream:
                assert {row['suite'] for row in csv.DictReader(stream)}=={'A','B','C'}
        results[stage]='passed'
        print(stage+' known-answer analysis passed',flush=True)
    write(directory/'verification.json',{'passed':True,'checks':results,'scope':'Synthetic method checks, not measured scientific results'})
    print(json.dumps({'passed':True,'directory':str(directory)}))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--worker',type=Path)
    args=parser.parse_args()
    if args.worker:
        worker(args.worker)
    else:
        main()
