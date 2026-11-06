"""Finish the already-authorized saved-file analysis/report once the fixed queue ends."""
from __future__ import annotations
import sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from common import *
import argparse
import subprocess

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--campaign',type=Path,required=True);a=ap.parse_args();campaign=a.campaign.resolve()
    work=campaign/'postprocessing';work.mkdir(exist_ok=True)
    lock=work/'PIPELINE_STARTED.json'
    if lock.exists():raise RuntimeError('Postprocessing watcher already exists; inspect its process/status rather than duplicate it')
    save(lock,dict(pid=os.getpid(),started=utc(),source=__file__,sha256=sha(__file__)))
    try:
        while not (campaign/'RESEARCH_COMPLETE.json').exists():
            if (campaign/'FAILED_OR_INTERRUPTED.json').exists():
                status=load(campaign/'status.json')
                report='# DO 진행 시작 구간 재사용 파일럿 — 부분 실행 상태\n\n'
                report+='기술 무결성 검토가 필요하여 새 분기를 추가로 시작하지 않았다. 완료된 유효 셀과 원 시도는 모두 보존했다. 전체 주 AUC 비교는 미완료이며 완료 셀만 재가중하여 효과를 주장하지 않는다.\n\n'
                report+='```json\n'+json.dumps(status,ensure_ascii=False,indent=2)+'\n```\n\n'
                report+='중단 근거: '+str(campaign/'FAILED_OR_INTERRUPTED.json')+'\n'
                (work/'report_ko.md').write_text(report,encoding='utf-8')
                save(work/'FINAL_STATUS.json',dict(status='partial_integrity_stop',campaign=str(campaign),report=str(work/'report_ko.md'),actual_status=status))
                return
            time.sleep(15)
        steps=[('analysis',[sys.executable,'-X','utf8',str(Path(__file__).parent/'analyze.py'),'--campaign',str(campaign)])]
        for name,command in steps:
            with (work/(name+'_stdout.log')).open('xb') as stdout,(work/(name+'_stderr.log')).open('xb') as stderr:
                subprocess.run(command,cwd=ROOT,stdout=stdout,stderr=stderr,check=True)
        analysis=Path(load(campaign/'LATEST_ANALYSIS.json')['output'])
        for name in ('verify','finalize'):
            with (work/(name+'_stdout.log')).open('xb') as stdout,(work/(name+'_stderr.log')).open('xb') as stderr:
                subprocess.run([sys.executable,'-X','utf8',str(Path(__file__).parent/(name+'.py')),'--analysis',str(analysis)],
                    cwd=ROOT,stdout=stdout,stderr=stderr,check=True)
        result=load(analysis/'FINAL_STATUS.json')
        save(work/'COMPLETE.json',dict(completed_at=utc(),analysis=str(analysis),report=result['report']))
        # Root index updates are append-only, preserving existing local changes.
        index=ROOT/'README.md';text=index.read_text(encoding='utf-8')
        marker='85_onset_reuse_pilot_v1'
        if marker not in text:
            text+='\n\n## 85. DO 진행 시작 구간 재사용 파일럿\n\n'
            text+='[한국어 보고서]('+Path(result['report']).relative_to(ROOT).as_posix()+') · [실행 상태](85_onset_reuse_pilot_v1/LATEST.json).\n\n'
            text+='기술 완료30/30분기와 운영 신호 판정을 분리해 기록한다. 고정 LOO 성공 저장소·기존16사례 개발 패널의 조건부 결과이며 기초동작·인과효과·일반 우위를 뜻하지 않는다.\n'
            index.write_text(text,encoding='utf-8',newline='\n')
        rules=ROOT/'AGENTS.md';text=rules.read_text(encoding='utf-8')
        if marker not in text:
            text+='\n\n- On 2026-11-06 the user authorized independent85_onset_reuse_pilot_v1: original81 five1M full parents, two futures, BASE/RANDOM_PRE/ONSET,30x64k continuations of the unchanged four-task SAC. Replace only native DO slots at probability0.25 using fixed32-transition pre-success windows from LOO donor successes; no BC/KL/extra update. Fixed detector thresholds and all31 successful source episodes were audited. Correct a reset physical-X mapping error using66 existing numeric snapshots and pinned XML, preserving the first preparation and all original obs/actions. Final eligible25; LOO25/20/20/16/19. Technical4900 steps passed exact restores/zero replacement/resume/evaluation isolation. All30 research branches and6080 evaluation episodes completed. Preserve the exact85 campaign/source/archives and use85 LATEST/report for effect values and the separate nominal operating-signal judgment. Parent bootstrap summaries condition on overlapping LOO stores, fixed random windows and old development panels; no universal skill/causal/state-only/general efficiency claim. No automatic sweep, extra seeds/tasks or follow-on queue. Keep all prior held stages held.\n'
            rules.write_text(text,encoding='utf-8',newline='\n')
        print(json.dumps(dict(status='complete',report=result['report'])),flush=True)
    except BaseException as ex:
        save(work/'PIPELINE_FAILED.json',dict(error=repr(ex),at=utc(),new_environment_or_model_execution=0));raise

if __name__=='__main__':main()
