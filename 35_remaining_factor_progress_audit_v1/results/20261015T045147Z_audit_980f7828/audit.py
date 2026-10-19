"""Read-only campaign health snapshot and explicitly conditional runtime forecast."""
import csv
import hashlib
import json
import math
import shutil
import statistics
import subprocess
import sys
import time
import traceback
import uuid
from collections import Counter
from datetime import datetime,timedelta,timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
KST=timezone(timedelta(hours=9))
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    now=datetime.now(timezone.utc);out=HERE/'results'/(now.strftime('%Y%m%dT%H%M%SZ')+'_audit_'+uuid.uuid4().hex[:8]);out.mkdir(parents=True)
    print(str(out),flush=True);start=time.perf_counter();cpu=time.process_time();checks=[];inputs={};error=None;result={}
    shutil.copy2(__file__,out/'audit.py')
    def write(name,data):
        with (out/name).open('x',encoding='utf-8') as f:json.dump(data,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n')
    def check(name,ok):
        checks.append({'check':name,'passed':bool(ok)})
        if not ok:raise AssertionError(name)
    def read(p,expected=None):
        p=Path(p);raw=p.read_bytes();digest=hashlib.sha256(raw).hexdigest();inputs[str(p.resolve())]=digest
        if expected is not None:check('referenced file hash',digest==expected)
        return json.loads(raw.decode('utf-8-sig'))
    try:
        active=read(ROOT/'33_remaining_factor_queue_v1/ACTIVE_CAMPAIGN.json');cam=Path(active['campaign'])
        plan=read(cam/'plan.json',read(cam/'plan_integrity.json')['sha256']);status=read(cam/'STATUS.json');write('observed_status.json',status)
        check('no technical stop marker',not (cam/'STOPPED.json').exists())
        check('live status',status['state'] in ['running','completed'])
        if status['state']=='running':check('recent controller heartbeat',(now-datetime.fromisoformat(status['updated_at'])).total_seconds()<60)
        for stage,version in [('F05','31_fixed_horizon_alignment_v1'),('F08','32_dose_order_intervention_v1')]:
            for name,digest in plan['stage_hashes'][stage].items():check('frozen code unchanged '+stage,sha(ROOT/version/name)==digest)
        jobs={j['id']:j for j in plan['jobs']};completed=[];traces=[];counts=Counter();costs=[]
        for p in (cam/'completed').glob('*.json'):
            m=read(p);j=jobs[m['job']];r=read(m['result_ref']['path'],m['result_ref']['sha256']);counts[j['stage']+':'+j['kind']]+=1
            if j['kind'] not in ['analysis','verify_analysis']:
                cost=read(Path(m['attempt'])/'costs.json');check('completed job cost status',cost['status']=='completed');costs.append(cost)
            if j['stage']=='F05' and j['kind']=='measure':
                check('fixed complete diagnostic and unchanged learner',r['new_environment_steps']==56000 and r['learner_unchanged'])
                check('zero persistent updates',cost['costs']['train_iterations']==0)
                vr=read(Path(m['attempt'])/'trace_verified.json');vs=read(vr['path'],vr['sha256']);check('raw trace verified',vs['status']=='completed')
                completed.append(m);traces.append(vs)
        errors=[str(p) for version in ['31_fixed_horizon_alignment_v1','32_dose_order_intervention_v1'] for p in (ROOT/version/'results'/cam.name).rglob('error.json')]
        raw=(cam/'events.jsonl').read_bytes();(out/'events_snapshot.jsonl').write_bytes(raw);events=[json.loads(line) for line in raw.decode('utf-8').splitlines()]
        starts={e['job']:datetime.fromisoformat(e['time']) for e in events if e['event']=='job_started'}
        cycle=[(datetime.fromisoformat(e['time'])-starts[e['job']]).total_seconds() for e in events if e['event']=='job_completed' and jobs[e['job']]['stage']=='F05' and jobs[e['job']]['kind']=='measure']
        partial={};progress_path=Path(status.get('attempt',''))/'progress.jsonl'
        if progress_path.is_file():
            raw=progress_path.read_bytes();(out/'progress_snapshot.jsonl').write_bytes(raw);partial=json.loads(raw.decode('utf-8').splitlines()[-1])
        partial_steps=partial.get('costs',{}).get('environment_steps',0) if jobs.get(status.get('job'),{}).get('kind')=='measure' else 0
        pending=max(0,192-len(completed)-partial_steps/56000)
        mean_cycle=statistics.mean(cycle);remaining05=pending*mean_cycle
        # Historical speed reference: matching200k parents, seed12, E1(A)/E3(B,C), successful20k segments and final O400-case evaluations.
        old=Path(read(ROOT/'13_e0_e3_autonomous_queue_v1/ACTIVE_CAMPAIGN.json')['campaign']);oldplan=read(old/'plan.json',read(old/'plan_integrity.json')['sha256']);reference=[];speeds={}
        for suite in ['A','B','C']:
            speeds[suite]={}
            for kind in ['train','evaluate']:
                sample=[]
                for j in oldplan['jobs']:
                    if not (j['stage']==('E1' if suite=='A' else 'E3') and j.get('suite')==suite and j.get('original_seed')==12 and j.get('checkpoint_step')==200000 and j['kind']==kind and '_r' in j['id'] and j.get('horizon') in ([20000,40000] if kind=='train' else [40000])):continue
                    m=read(old/'completed'/(j['id']+'.json'));rp=Path(m['result_ref']['path']);cost=read(rp.parent/'costs.json')
                    check('historical complete runtime reference',cost['success'] and not cost['technical_smoke'])
                    check('historical matching budget',cost['costs']['train_iterations']==20000 if kind=='train' else cost['costs']['evaluation_episodes']==400)
                    sample.append(cost['wall_seconds']);reference.append({'suite':suite,'kind':kind,'job':j['id'],'path':str(rp.parent/'costs.json'),**cost})
                check('matching sample size',len(sample)==(30 if kind=='train' else 15))
                speeds[suite][kind]={'n':len(sample),'mean_seconds':statistics.mean(sample),'median_seconds':statistics.median(sample),'min_seconds':min(sample),'max_seconds':max(sample)}
        historical08=sum(48*speeds[s]['train']['mean_seconds']+25*speeds[s]['evaluate']['mean_seconds'] for s in speeds)
        # Fixed planning allowances, not confidence intervals: +25% for unobserved F05 suites and full pipeline runtimes.
        stage05_range=[remaining05+300,remaining05*1.25+600]
        stage08_range=[historical08+900,historical08*1.25+1800]
        eta=lambda seconds:(now+timedelta(seconds=seconds)).astimezone(KST).isoformat()
        gpu=subprocess.run(['nvidia-smi','--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu','--format=csv,noheader'],capture_output=True,text=True)
        result={'observed_at_kst':now.astimezone(KST).isoformat(),'campaign':str(cam),'state':status['state'],'current_job':status.get('job'),
          'completed_job_counts':dict(counts),'F05_models_complete':len(completed),'F05_models_total':192,'F05_complete_fraction':len(completed)/192,
          'F05_verified_models':len(traces),'completed_worker_env_steps':sum(c['costs']['environment_steps'] for c in costs),
          'completed_worker_train_updates':sum(c['costs']['train_iterations'] for c in costs),'current_progress':partial,
          'production_error_files':errors,'cycle_seconds':{'mean':mean_cycle,'recent5_mean':statistics.mean(cycle[-5:]),'min':min(cycle),'max':max(cycle)},
          'F05_remaining_hours_range':[x/3600 for x in stage05_range],'F05_completion_kst_range':[eta(x) for x in stage05_range],
          'F08_historical_reference_hours':historical08/3600,'F08_duration_hours_range':[x/3600 for x in stage08_range],
          'full_completion_kst_range':[eta(a+b) for a,b in zip(stage05_range,stage08_range)],
          'forecast_scope':'At this audit F08 is queued. F05 actual cycle average extrapolated; F08 past E1/E3 seed12 timing references. +25% and explicit setup/analysis allowances are planning assumptions, not probabilistic intervals. New schedules, policy success and computer load can change duration. No effect estimate or early stopping rule.',
          'historical_speed_by_suite':speeds,'disk_C_free_GiB':shutil.disk_usage(ROOT).free/2**30,'gpu_snapshot':gpu.stdout.strip(),'gpu_read_returncode':gpu.returncode}
        write('historical_runtime_references.json',reference)
        report=f"# 미실행 후보 실험 중간점검\n\n기준 시각: {result['observed_at_kst']}\n\n⑤는 {len(completed)}/192 모델({len(completed)/192:.1%})의 측정·원자료 검산을 완료했다. 완료 작업 환경 비용은 {result['completed_worker_env_steps']:,} step, 학습 update는 {result['completed_worker_train_updates']:,}회다. 본 실행 오류 파일은 {len(errors)}개다.\n\n모델당 전체 실행은 평균 {mean_cycle:.1f}초, 최근5개 평균 {result['cycle_seconds']['recent5_mean']:.1f}초다. ⑤ 예상 잔여 시간은 {stage05_range[0]/3600:.1f}–{stage05_range[1]/3600:.1f}시간이며, KST 예상 완료는 {result['F05_completion_kst_range']}다.\n\n⑧은 대기 중이다. 과거 같은 SAC·원래 seed12·200k의 성공한20k 학습90구간과 최종 평가45개의 실제 시간으로 72분기의 실행을 추정했다. 과거 속도 그대로의 합은 {historical08/3600:.1f}시간이며, 준비·분석·성능변동 여유를 포함한 계획 범위는 {stage08_range[0]/3600:.1f}–{stage08_range[1]/3600:.1f}시간이다. 전체 완료 예상 KST 범위는 {result['full_completion_kst_range']}다. 이 범위는 통계적 신뢰구간이 아니며 ⑧의 실제 실행 속도에 따라 갱신해야 한다.\n\nGPU 순간값: {result['gpu_snapshot']}. C 여유 공간은 {result['disk_C_free_GiB']:.1f}GiB다. 실행 코드 hash와 완료 결과·trace 검산 출처를 확인했다. 과학적 효과는 이번 중간점검에서 평가하지 않았다.\n\n[수치·가정](summary.json) · [과거 속도 출처](historical_runtime_references.json) · [관측 상태](observed_status.json)\n"
        (out/'report_ko.md').write_text(report,encoding='utf-8')
    except BaseException:error=traceback.format_exc()
    write('input_hashes.json',inputs);write('source_hashes.json',{'audit.py':sha(Path(__file__))});write('checks.json',checks)
    summary={'status':'failed' if error else 'completed','audit':result,'checks_passed':sum(c['passed'] for c in checks),'checks_failed':sum(not c['passed'] for c in checks),
       'wall_seconds':time.perf_counter()-start,'cpu_seconds':time.process_time()-cpu,'new_environment_steps':0,'learner_updates':0,'python':sys.version,'error':error}
    write('summary.json',summary)
    if error:raise RuntimeError(error)
    print(json.dumps({'status':summary['status'],'checks_passed':summary['checks_passed'],**result},indent=2),flush=True)

if __name__=='__main__':main()
