"""Freeze the exact independent, file-only correction for the known64 bug."""
from pathlib import Path
from deferred_queue import ROOT,load,sha,source_hashes
import json

def main():
    path=ROOT/'inputs/upstream_campaign.json';data=load(path)
    if 'analysis_repair' in data:raise RuntimeError('Recovery source is already pinned')
    repair=(ROOT.parent/'67_baseline_analysis_repair_v1').resolve()
    original=(ROOT.parent/'64_gain_loss_recovery_baseline_v1/analyze_baseline.py').read_text(encoding='utf-8')
    line=next(x.strip() for x in original.splitlines() if 'evaluated = sum(row[' in x)
    expected=original.replace('sum(row["length"] for row in worker_rows)',
                              'sum(int(row["length"]) for row in worker_rows)')
    if (repair/'analyze_baseline.py').read_text(encoding='utf-8')!=expected:
        raise RuntimeError('Recovery contains more than the specified integer cast')
    if sha(repair/'verify_baseline.py')!=sha(ROOT.parent/'64_gain_loss_recovery_baseline_v1/verify_baseline.py'):
        raise RuntimeError('Independent baseline verifier changed')
    data['analysis_repair']={'root':str(repair),'source_hashes':source_hashes(repair),
        'analysis_script':'analyze_baseline.py','verification_script':'verify_baseline.py',
        'known_error_message':"unsupported operand type(s) for +: 'int' and 'str'",'known_source_line':line}
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    protocol=ROOT/'protocol.json';value=load(protocol)
    value['input_hashes']['inputs/upstream_campaign.json']=sha(path)
    protocol.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'pinned_repair_source_files':len(data['analysis_repair']['source_hashes']),
                      'new_environment_steps':0,'only_specified_cast_changed':True}))
if __name__=='__main__':main()
