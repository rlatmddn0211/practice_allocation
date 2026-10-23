"""Independent exact-arithmetic reaggregation and paired-bootstrap verification.

Does not import analyze.py. Uses raw CSV snapshots, not its derived outcome table.
"""
import csv
import hashlib
import itertools
import json
import platform
import shutil
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def csvrows(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def save(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    analysis = Path(sys.argv[1]).resolve()
    started, cpu = time.perf_counter(), time.process_time()
    out = HERE / "results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_verification_" + uuid.uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    (out / "source_snapshot").mkdir()
    shutil.copy2(Path(__file__), out / "source_snapshot/verify.py")
    checks = []

    def check(ok, label):
        checks.append({"check": label, "passed": bool(ok)})
        if not ok:
            raise AssertionError(label)

    try:
        summary = load(analysis / "summary.json")
        snap = analysis / "input_snapshot"
        rawold = csvrows(snap / "outcomes_25_policies.csv")
        frozen = csvrows(snap / "fixed_choices.csv")
        protocol = load(snap / "protocol51.json")
        config = load(HERE / "analysis_config.json")
        check(digest(snap / "fixed_choices.csv") == config["fixed_choices_sha256"], "choices_unchanged")
        check(digest(snap / "outcomes_25_policies.csv") == protocol["source_outcomes_sha256"], "old_data_unchanged")
        for name, expected in load(analysis / "source_hashes.json").items():
            check(digest(analysis / "source_snapshot" / name) == expected, "analysis_source_snapshot:"+name)
        inputhashes = load(analysis / "input_hashes.json")
        parents, repeats, tasks = protocol["parents"], protocol["prefix_continuations"], protocol["tasks"]
        old = {(int(z["original_seed"]), int(z["continuation"]), int(z["horizon"]), z["task"], int(z["episode_index"])): z for z in rawold}
        new, base = {}, {}
        for p in parents:
            for r in repeats:
                path = snap / f"B_s{p}_r{r}_new_future.csv"
                expected = [value for name, value in inputhashes.items() if f"/B_s{p}_r{r}_new_future/" in name and name.endswith("/evaluation_episodes.csv")]
                check(len(expected) == 1 and digest(path) == expected[0], f"new_raw_hash:{p}:{r}")
                for z in csvrows(path):
                    k = (p,r,z["task"],int(z["episode_index"]))
                    new[k] = int(z["success"])
                    b = old[(p,r,8000,k[2],k[3])]
                    base[k] = int(b["success"])
                    check((z["seed"], z["initial_state_hash"]) == (b["seed"], b["initial_state_hash"]), f"case_identity:{k}")
        exact_rows, actions = [], {}
        for row in frozen:
            p,r = int(row["parent"]), int(row["prefix_continuation"])
            sh = row["scoring_cases"]
            cases = range(50) if sh == "A" else range(50,100) if sh == "B" else range(100)
            keys = [(p,r,t,i) for t in tasks for i in cases]
            stop = Fraction(100 * sum(base[k] for k in keys), len(keys))
            cont = Fraction(100 * sum(new[k] for k in keys), len(keys))
            pick = stop if row["fixed_action"] == "stop" else cont
            exact_rows.append((p,r,sh,stop,cont,pick,pick-stop,pick-cont))
            if sh in ("A", "B"):
                actions[(p,r,sh)] = int(row["fixed_action"] == "continue")
        reported_rows = csvrows(analysis / "frozen_choice_scores.csv")
        for e,z in zip(exact_rows,reported_rows):
            check(all(abs(float(value) - float(z[name])) < 1e-10 for value,name in zip(e[3:], ["new_stop_percent","new_continue_percent","selected_percent","G_stop_pp","G_continue_pp"])), f"exact_row:{e[:3]}")
        primary = [e for e in exact_rows if e[2] in ("A","B")]
        exact = [sum(e[col] for e in primary)/20 for col in range(3,8)]
        for expected, measured in zip(exact, [summary["means_percent"]["stop8"],summary["means_percent"]["new_continue40"],summary["means_percent"]["primary_fixed_choice"],*summary["primary_gains_pp"].values()]):
            check(abs(float(expected)-measured)<1e-10, f"overall_exact:{expected}")
        pg = []
        for p in parents:
            units = [e for e in primary if e[0] == p]
            pg.append([float(sum(e[col] for e in units)/4) for col in [6,7]])
        pg = np.array(pg)
        check(np.allclose(pg, [[z["G_stop_pp"],z["G_continue_pp"]] for z in summary["parent_results"]], atol=1e-10), "parent_aggregation")
        draws = np.load(analysis / "bootstrap_draws.npz")
        indices = draws["indices"]
        count = protocol["uncertainty"]["case_bootstrap_replicates"]
        totals = np.zeros((count,2),dtype=np.int64)
        rng = np.random.default_rng(protocol["uncertainty"]["case_bootstrap_seed"])
        for pi,p in enumerate(parents):
            for ti,t in enumerate(tasks):
                for hi,h in enumerate(["A","B"]):
                    idx = indices[pi,ti,hi].astype(np.int64)
                    check(np.array_equal(idx,rng.integers(0,50,size=(count,50))), f"seeded_draws:{p}:{t}:{h}")
                    for r in repeats:
                        delta = np.array([new[(p,r,t,i)]-base[(p,r,t,i)] for i in range(hi*50,(hi+1)*50)],dtype=np.int64)
                        sampled_sums = delta[idx].sum(axis=1)
                        a = actions[(p,r,h)]
                        totals[:,0] += a * sampled_sums
                        totals[:,1] += (a-1) * sampled_sums
        boot = totals / 40.0  # integer successes over 4000 equally weighted cases, in pp
        check(np.allclose(boot,draws["case_estimates"],atol=1e-10,rtol=0), "all_20000_bootstrap_vectors_independent_aggregation")
        theta = np.array([float(exact[3]),float(exact[4])])
        q = np.quantile(np.maximum(theta[0]-boot[:,0],theta[1]-boot[:,1]),0.95,method="linear")
        lower = theta-q
        check(np.allclose(lower,summary["conditional_case_joint_lower_bounds_pp"],atol=1e-10), "joint_lower_bound_formula")
        indices_parent = list(itertools.product(range(5),repeat=5))
        parent_boot = np.array([[sum(pg[i,b] for i in ix)/5 for b in [0,1]] for ix in indices_parent])
        check(np.allclose(parent_boot,draws["parent_estimates"],atol=1e-10), "all_3125_parent_draws")
        removals=[]
        for pi,p in enumerate(parents):
            units = [e for e in primary if e[0] != p]
            scores = [sum(e[col] for e in units)/16 for col in range(3,8)]
            removals.append([float(scores[3]),float(scores[4])])
            z = summary["leave_one_parent_out"][pi]
            check(all(abs(float(v)-z[k])<1e-10 for v,k in zip(scores,["stop_percent","continue_percent","selected_percent","G_stop_pp","G_continue_pp"])),f"parent_removed:{p}")
        shares=[float(max(max(v,0) for v in pg[:,b])/sum(max(v,0) for v in pg[:,b])) for b in [0,1]]
        check(np.allclose(shares,summary["maximum_positive_parent_contribution_shares"],atol=1e-10), "concentration")
        gate = protocol["proposed_investment_gate"]
        expected_conditions=[min(theta)>=gate["minimum_each_primary_gain_pp"],min(lower)>0,np.min(removals)>0,max(shares)<=gate["maximum_positive_parent_contribution_share_each"],not load(analysis/"checks.json")["failed"]]
        check(expected_conditions == list(summary["gate_conditions"].values()),"investment_gate")
        for future in ["old","new"]:
            counts = {f"{i:03b}":0 for i in range(8)}
            for key in base:
                p,r,t,i=key
                start = int(old[(p,0,0,t,i)]["success"])
                final = new[key] if future == "new" else int(old[(p,r,40000,t,i)]["success"])
                counts[f"{start}{base[key]}{final}"]+=1
            for pattern,n in counts.items():
                check(abs(n/40-summary["success_pattern_totals"][future][pattern])<1e-10,f"trajectory:{future}:{pattern}")
        result={"status":"passed","checks":len(checks),"failed_checks":[],"exact_primary_scores":[str(x) for x in exact],"joint_lower_bounds_pp":lower.tolist(),"source_hashes":{"verify.py":digest(Path(__file__))},"analysis":str(analysis),"analysis_summary_sha256":digest(analysis/"summary.json"),"bootstrap_file_sha256":digest(analysis/"bootstrap_draws.npz"),"python":sys.version,"numpy":np.__version__,"platform":platform.platform(),"wall_seconds":time.perf_counter()-started,"cpu_seconds":time.process_time()-cpu,"environment_steps":0,"SAC_updates":0}
        save(out/"summary.json",result)
        save(out/"VERIFIED.json",{"summary_sha256":digest(out/"summary.json"),"analysis_summary_sha256":result["analysis_summary_sha256"]})
        print(json.dumps({"output":str(out),"status":"passed","checks":len(checks),"exact_scores":result["exact_primary_scores"]},indent=2))
    except Exception:
        save(out/"FAILED.json",{"traceback":traceback.format_exc(),"source_sha256":digest(Path(__file__)),"environment_steps":0})
        raise
    finally:
        save(out/"checks.json",checks)


if __name__ == "__main__":
    main()
