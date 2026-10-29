"""Snapshot before parsing/running an analysis component; retain every failure."""
import ast
import importlib.util
import json
import platform
import shutil
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from io_utils import HERE, dump, sha

def main():
    component=sys.argv[1]
    if component not in ("analyze", "verify", "make_figure", "verify_delivery"):
        raise ValueError(component)
    started=datetime.now(timezone.utc)
    start,cpu=time.perf_counter(),time.process_time()
    out=HERE/"results"/(started.strftime("%Y%m%dT%H%M%SZ")+"_"+component+"_"+uuid.uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    (out/"source_snapshot").mkdir()
    sources={}
    for path in sorted([*HERE.glob("*.py"), *HERE.glob("*.md"), HERE/"analysis_config.json"]):
        shutil.copy2(path,out/"source_snapshot"/path.name); sources[path.name]=sha(path)
    dump(out/"source_hashes.json",sources)
    print(str(out),flush=True)
    success=False
    try:
        for path in HERE.glob("*.py"):
            ast.parse(path.read_text(encoding="utf-8"),filename=str(path))
        path=HERE/(component+".py")
        spec=importlib.util.spec_from_file_location("work_component",path)
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        result=module.run(out,sys.argv[2:])
        dump(out/"COMPLETE.json",{"component":component,"status":"completed","result":result,"new_environment_steps":0})
        print(json.dumps(result,ensure_ascii=False,default=str),flush=True)
        success=True
    except BaseException as exc:
        dump(out/"FAILED.json",{"component":component,"error":repr(exc),"traceback":traceback.format_exc(),"new_environment_steps":0})
        traceback.print_exc()
    finally:
        import numpy as np
        dump(out/"runtime.json",{"started_utc":started.isoformat(),"finished_utc":datetime.now(timezone.utc).isoformat(),"wall_seconds":time.perf_counter()-start,"cpu_seconds":time.process_time()-cpu,"python":sys.version,"numpy":np.__version__,"platform":platform.platform(),"command":sys.argv,"training_steps":0,"evaluation_steps":0,"gpu_used":False,"successful":success})
    return 0 if success else 1

if __name__ == "__main__":
    raise SystemExit(main())
