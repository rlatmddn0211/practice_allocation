"""Copy the exact immutable original source into this independent implementation."""
from common import *
guard_file_only()

def main():
    out=new_output('runtime_source_preparation');inputs=Inputs()
    try:
        prep=load(HERE/'LATEST_PREPARATION.json')['output']
        if not load(Path(prep)/'readiness.json')['archive_support_all_receivers']:raise RuntimeError('Archive support gate failed')
        manifest=inputs.json(CAMPAIGN/'runs/R01/checkpoints/full/1000000/checkpoint_manifest.json','baseline source manifest')
        destination=HERE/'baseline81'
        if destination.exists():raise FileExistsError(destination)
        for relative,digest in manifest['source_hashes'].items():
            source=CAMPAIGN/'runs/R01/source_snapshot'/relative
            inputs.ref(source,'exact original source copied into self-contained implementation',expected=digest)
            target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
            if sha(target)!=digest:raise RuntimeError('Copy mismatch')
        save(out/'copied_source_manifest.json',manifest['source_hashes'])
        save(out/'FINAL_STATUS.json',dict(status='complete',new_execution=ZERO_EXECUTION,copied_baseline=str(destination)))
        print(json.dumps(dict(output=str(out),baseline=str(destination))))
    except BaseException as ex:
        save(out/'FAILED.json',dict(error=repr(ex),new_execution=ZERO_EXECUTION));raise
    finally:inputs.flush(out)

if __name__=='__main__':main()
