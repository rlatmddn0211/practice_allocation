"""Independent vectorized verification of the descriptive B supplement."""
import csv
import hashlib
import io
import itertools
import json
import shutil
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    start, cpu = time.perf_counter(), time.process_time()
    out = HERE/"results"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_verification_"+uuid.uuid4().hex[:8])
    (out/"source_snapshot").mkdir(parents=True, exist_ok=False)
    for p in list(HERE.glob("*.py"))+[HERE/"analysis_config.json"]:
        shutil.copy2(p, out/"source_snapshot"/p.name)
    inputs, checks = {}, []

    def read(p):
        p = Path(p).resolve()
        b = p.read_bytes()
        inputs[str(p)] = hashlib.sha256(b).hexdigest()
        return b

    def js(p):
        return json.loads(read(p).decode("utf-8-sig"))

    def rows(p):
        return list(csv.DictReader(io.StringIO(read(p).decode("utf-8-sig"))))

    def check(label, condition):
        checks.append(dict(check=label, passed=bool(condition)))
        if not condition:
            raise AssertionError(label)

    def eq(a, b):
        return np.allclose(a, b, atol=1e-10, rtol=0)

    def dump(name, obj):
        (out/name).write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")

    try:
        cfg, ref = js(HERE/"analysis_config.json"), js(HERE/"LATEST_ANALYSIS.json")
        run = Path(ref["run"])
        check("summary_hash", hashlib.sha256(read(run/"summary.json")).hexdigest() == ref["summary_sha256"])
        for name in ("input_hashes.json", "output_hashes.json"):
            for p, h in js(run/name).items():
                p = Path(p) if name.startswith("input") else run/p
                check("unchanged:"+str(p), hashlib.sha256(read(p)).hexdigest() == h)
        s = js(run/"summary.json")
        policies = ["J0", "J8_4201", "J40_4201", "J8_4202", "J40_4202"]
        a = np.zeros((5, 5, 4, 100), dtype=np.int8)
        for r in rows(HERE.parent/cfg["input_run"]/"outcomes_25_policies.csv"):
            a[cfg["parents"].index(int(r["original_seed"])), policies.index(r["policy"]),
              cfg["tasks"].index(r["task"]), int(r["episode_index"])] = int(r["success"])
        means = a.mean(axis=(2, 3))*100
        b, c = means[:, [1, 3]], means[:, [2, 4]]
        h = np.maximum(b, c)
        check("full_means", eq([b.mean(), c.mean(), h.mean()], [s["full"][k] for k in ("J8","J40","hindsight")]))
        best = max(b.mean(), c.mean())
        check("observed_fixed_reference", eq(s["full"]["observed_better_fixed"], best)
              and eq(s["full"]["hindsight_minus_observed_better_fixed"], h.mean()-best))
        for pi, p in enumerate(cfg["parents"]):
            d = s["contributions"][pi]
            stop, cont = (h[pi]-b[pi]).mean()/5, (h[pi]-c[pi]).mean()/5
            check("contribution:"+str(p), eq([d["contribution_vs_stop_pp"],d["contribution_vs_continue_pp"]],
                                            [stop,cont]))
            mask = np.arange(5) != pi
            d = s["leave_one_parent_out"][pi]
            vb, vc, vh = b[mask].mean(), c[mask].mean(), h[mask].mean()
            check("refit_fixed_after_removal:"+str(p), eq([d[k] for k in
                  ("J8","J40","hindsight","hindsight_minus_observed_better_fixed")], [vb,vc,vh,vh-max(vb,vc)])
                  and d["observed_better_fixed_label"] == ("stop8" if vb >= vc else "continue40"))
        check("share_41015", eq(s["contributions"][-1]["fraction_of_full_gain"], (h[-1]-b[-1]).sum()/
                               (h-b).sum()))
        for d in s["task_groups"]:
            inds = list(range(5)) if d["group"] == "all" else ([2] if d["group"] == "only41013" else [0,1,3,4])
            z = a[inds, :, cfg["tasks"].index(d["task"]), :]
            values = [z[:,0].mean()*100,z[:,[1,3]].mean()*100,z[:,[2,4]].mean()*100]
            check("task_group:"+d["group"]+d["task"], eq([d[k] for k in ("J0","J8","J40")],values))
        for d in s["late_components"]:
            inds = list(range(5)) if d["group"] == "all" else [4]
            parent = np.repeat(a[inds,0:1],2,axis=1)
            early, final = a[inds][:,[1,3]], a[inds][:,[2,4]]
            vals = [((parent==0)&(early==0)&(final==1)).mean()*100,
                    ((parent==1)&(early==0)&(final==1)).mean()*100,
                    ((parent==1)&(early==1)&(final==0)).mean()*100,
                    ((parent==0)&(early==1)&(final==0)).mean()*100]
            check("net_components:"+d["group"], eq([d[k] for k in
                ("new_success","recovery","old_success_lost_late","early_gain_lost_late")],vals)
                and eq(vals[0]+vals[1]-vals[2]-vals[3], d["net"]))
        for d in rows(run/"three_time_pattern_counts.csv"):
            pi, ri, ti = cfg["parents"].index(int(d["parent"])),cfg["continuations"].index(int(d["continuation"])),cfg["tasks"].index(d["task"])
            triples = a[pi,[0,1+ri*2,2+ri*2],ti,:].T
            for bits in itertools.product((0,1), repeat=3):
                name = "".join(map(str,bits))
                check("pattern:"+str((pi,ri,ti,name)), int(d["n"+name]) == int(np.all(triples==bits,axis=1).sum()))
        check("no_execution_expansion", s["new_environment_steps"] == s["new_training_steps"] == s["new_SAC_updates"] == 0
              and s["future_repetition_proposal"]["status"] == "proposal_only_not_scheduled")
        check("proposal_cost", s["future_repetition_proposal"]["main_environment_cap"] == 10*32000+10*4*100*500)
        check("savings", eq(s["resource_saving"]["additional_training_fraction"],.8)
              and eq(s["resource_saving"]["total_training_including_parent_fraction"],2/15))
        summary = dict(status="passed", checks_passed=len(checks), failed_checks=0, analysis=ref,
                       new_environment_steps=0, new_training_steps=0, new_SAC_updates=0,
                       scientific_independent_validation=False, wall_seconds=time.perf_counter()-start,
                       CPU_seconds=time.process_time()-cpu, numpy=np.__version__, python=sys.version)
        dump("summary.json",summary)
        dump("checks.json",checks)
        dump("input_hashes.json",inputs)
        dump("source_hashes.json",{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (out/"source_snapshot").iterdir()})
        (HERE/"LATEST_VERIFICATION.json").write_text(json.dumps(dict(run=str(out), summary_sha256=
            hashlib.sha256((out/"summary.json").read_bytes()).hexdigest()),indent=2),encoding="utf-8")
        print(json.dumps(dict(run=str(out),**summary),indent=2))
    except BaseException:
        dump("failure.json",dict(traceback=traceback.format_exc(),checks=checks,input_hashes=inputs,
                                new_environment_steps=0,new_training_steps=0,new_SAC_updates=0))
        raise


if __name__ == "__main__":
    main()
