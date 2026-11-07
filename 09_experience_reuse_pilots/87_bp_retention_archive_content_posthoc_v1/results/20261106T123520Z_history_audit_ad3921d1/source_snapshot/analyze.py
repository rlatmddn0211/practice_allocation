"""Run existing-file87 analyses without importing an RL or physics runtime."""
from __future__ import annotations
from common import *
guard()
import argparse
import traceback
import pandas as pd
import psutil
import histories


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--stage',choices=['histories','all'],default='all');a=ap.parse_args()
    started=time.perf_counter();out=new_output('history_audit' if a.stage=='histories' else 'bp_content_posthoc');inputs=Inputs();checks=Checks()
    print(json.dumps(dict(output=str(out),stage='starting')),flush=True)
    try:
        config=inputs.json(HERE/'analysis_config.json','fixed exploratory analysis definitions');save(out/'analysis_config.json',config)
        status=inputs.json(ANALYSIS/'FINAL_STATUS.json','completed exact85 analysis identity')
        checks.add('exact85 completed',status['status']=='complete' and status['completed_branches']==30 and status['valid_evaluations']==6080)
        result=histories.run(out,inputs,checks)
        print(json.dumps(dict(stage='BP histories complete',paired_histories=len(result['wide']),effects=result['parents'].to_dict('records'))),flush=True)
        if a.stage=='all':
            import physical,exposure,report
            phys=physical.run(out,inputs,checks,result)
            exp=exposure.run(out,inputs,checks,result,phys)
            report.run(out,inputs,checks,result,phys,exp)
        save(out/'FINAL_STATUS.json',dict(status='history_audit_complete' if a.stage=='histories' else 'complete',
            completed_stages=['BP histories/repetition'] if a.stage=='histories' else ['BP repetition/histories','BP physical trajectories','fixed DO content','actual exposure and linkage'],
            campaign=str(CAMPAIGN),source_analysis=str(ANALYSIS),new_execution=ZERO,output=str(out)))
        save(HERE/('LATEST_HISTORY.json' if a.stage=='histories' else 'LATEST.json'),dict(output=str(out),status='history_audit_complete' if a.stage=='histories' else 'complete'),replace=True)
    except BaseException:
        save(out/'FAILED.json',dict(traceback=traceback.format_exc(),new_execution=ZERO));raise
    finally:
        checks.flush(out);inputs.flush(out);p=psutil.Process()
        save(out/'analysis_costs.json',dict(wall_seconds=time.perf_counter()-started,memory=p.memory_info()._asdict(),cpu=p.cpu_times()._asdict(),io=p.io_counters()._asdict(),tracked_input_bytes=inputs.bytes_read,new_execution=ZERO))
        print(json.dumps(dict(output=str(out),wall_seconds=time.perf_counter()-started)),flush=True)


if __name__=='__main__':main()
