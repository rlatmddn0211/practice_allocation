"""Independent pure-data verification; imports no analysis or RL implementation.

Rebuilds endpoint counts with sets/Fractions, six-label events with a state
machine, and every paired bootstrap draw with integer frequency weights.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
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

ROOT = Path(__file__).resolve().parent
PARENTS = tuple(range(41011, 41016))
TASKS = ("DO", "DC", "PU", "BP")
CONDITIONS = ("dose25", "dose625")
FUTURES = (1, 2)
STEPS = (4000, 8000, 16000, 32000)
METRICS = ("J", "G", "L", "delta", "recovery")
PATH_METRICS = ("late_loss_transitions", "late_recovery_transitions", "ever_loss", "repeated_loss", "loss_then_recovery")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def load_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def save_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")


class Checks:
    def __init__(self):
        self.passed = 0

    def need(self, valid, label):
        if not valid:
            raise AssertionError(label)
        self.passed += 1

    def same(self, actual, expected, label, tolerance=1e-11):
        if expected is None:
            self.need(actual in (None, ""), label+": expected NA")
        else:
            self.need(actual not in (None, "") and abs(float(actual)-float(expected)) <= tolerance,
                      label+": "+str(actual)+" != "+str(expected))


def make_run():
    run = ROOT / "results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+
                              "_verify_"+uuid.uuid4().hex[:8])
    run.mkdir(parents=True, exist_ok=False)
    folder = run / "source_snapshot"
    folder.mkdir()
    for name in ("analyze_baseline.py", "verify_baseline.py"):
        shutil.copy2(ROOT / name, folder / name)
    save_json(run / "source_hashes.json", {name: sha(ROOT/name) for name in ("analyze_baseline.py", "verify_baseline.py")})
    return run


def state_machine(bits):
    """A separate history-state implementation, not the analysis list formula."""
    ever_success = bool(bits[0])
    had_loss = False
    total_gain = total_loss = recovery = late_loss = late_recovery = 0
    first = late_first = None
    previous = bits[0]
    times = (-8000, 0, 4000, 8000, 16000, 32000)
    for index, current in enumerate(bits[1:], 1):
        if previous == 1 and current == 0:
            total_loss += 1
            had_loss = True
            if first is None:
                first = times[index]
            if index >= 2:
                late_loss += 1
                if late_first is None:
                    late_first = (times[index-1], times[index])
        elif previous == 0 and current == 1:
            total_gain += 1
            if ever_success:
                recovery += 1
                if index >= 2:
                    late_recovery += 1
            ever_success = True
        previous = current
    return {"gain_transitions": total_gain, "loss_transitions": total_loss,
            "recovery_transitions": recovery, "late_loss_transitions": late_loss,
            "late_recovery_transitions": late_recovery, "ever_loss": int(had_loss),
            "repeated_loss": int(total_loss >= 2), "loss_then_recovery": int(recovery > 0),
            "first_observed_loss_end": first,
            "first_observed_late_loss_start": late_first[0] if late_first else None,
            "first_observed_late_loss_end": late_first[1] if late_first else None}


def percentile(draws, probability):
    ordered = np.sort(np.asarray(draws), axis=0)
    position = (ordered.shape[0]-1)*probability
    low, high = math.floor(position), math.ceil(position)
    return ordered[low]+(ordered[high]-ordered[low])*(position-low)


def validate(analysis, checks, run):
    analysis = Path(analysis).resolve()
    summary = load_json(analysis / "summary.json")
    assets = load_json(analysis / "input_assets.json")
    # Check both source and retained short copy; data must remain reproducible.
    for item in assets:
        checks.need(sha(item["path"]) == item["sha256"], "Original input changed: "+item["path"])
        checks.need(sha(analysis/item["snapshot"]) == item["sha256"], "Input snapshot mismatch")
    def asset(role):
        candidates = [item for item in assets if item["role"] == role]
        checks.need(len(candidates) == 1, "Unique required input "+role)
        return analysis/candidates[0]["snapshot"]
    baseline_rows = load_csv(asset("P_S_outcomes"))
    raw_cases = load_json(asset("evaluation_subsets"))
    checks.need(isinstance(raw_cases, list), "Frozen flat case schema")
    subsets = {}
    for row in raw_cases:
        identity = (int(row["parent"]), row["task"])
        subsets.setdefault(identity, {"E50": [], "T20": []})
        for subset in ("E50", "T20"):
            if row["in_"+subset] is True or str(row["in_"+subset]).lower() in ("true", "1"):
                subsets[identity][subset].append(int(row["episode_index"]))
    for sets in subsets.values():
        for key in sets:
            sets[key].sort()
    baseline = {}
    for row in baseline_rows:
        key = (int(row["parent"]), row["stage"], row["task"], int(row["episode_index"]))
        checks.need(key not in baseline, "Unique P/S row")
        checks.need(int(row["success"]) in (0, 1), "Binary baseline label")
        baseline[key] = row
    checks.need(len(baseline) == 2000, "P/S coverage")
    jobs = load_json(asset("frozen_jobs"))
    jobs = jobs["jobs"] if isinstance(jobs, dict) else jobs
    checks.need(len(jobs) == 20, "Twenty declared jobs")
    combinations = set()
    for job in jobs:
        parent, condition, future = int(job["parent"]), job["condition"], int(job["future"])
        combinations.add((parent, condition, future))
        seed = int(np.random.SeedSequence([640202, 64, parent, 4201, future]).generate_state(1)[0])
        checks.need(int(job["root_seed"]) == seed, "Frozen exact future seed")
        checks.need(int(job["schedule_seed"]) == int(np.random.SeedSequence([seed,10]).generate_state(1)[0]), "Exact schedule seed")
    checks.need(combinations == {(p,c,f) for p in PARENTS for c in CONDITIONS for f in FUTURES}, "Full paired job coverage")
    outcomes = {}
    lengths = {}
    for item in [item for item in assets if item["role"] == "research_evaluation"]:
        rows = load_csv(analysis/item["snapshot"])
        checks.need(len(rows) == 440, "Four checkpoint episode count")
        job_id = rows[0]["id"]
        lengths[job_id] = sum(int(row["length"]) for row in rows)
        for row in rows:
            p,c,f,t,i = int(row["parent"]),row["condition"],int(row["future"]),row["task"],int(row["episode_index"])
            step = int(row["relative_step"])
            key = (p,c,f,step,t,i)
            checks.need(key not in outcomes, "Unique research case")
            subset = "E50" if step == 32000 else "T20"
            checks.need(step in STEPS and i in subsets[(p,t)][subset], "Frozen evaluated subset")
            ref = baseline[(p,"S",t,i)]
            checks.need((int(row["seed"]),row["initial_state_hash"]) ==
                        (int(ref["seed"]),ref["initial_state_hash"]), "Case reset pairing")
            checks.need(int(row["success"]) in (0,1), "Binary future success")
            outcomes[key] = int(row["success"])
    complete = len(outcomes) == 8800
    checks.need(summary["completed_jobs"] == len(lengths), "Completion status count")
    source_values = {}
    counts_by_group = {}
    t20_expected = {}
    for p in PARENTS:
        for task in TASKS:
            ids = subsets[(p,task)]["E50"]
            checks.need(len(ids) == len(set(ids)) == 50, "Fifty unique E50")
            checks.need(len(subsets[(p,task)]["T20"]) == 20 and set(subsets[(p,task)]["T20"]) <= set(ids), "Nested T20")
            success_p = {i for i in ids if int(baseline[(p,"P",task,i)]["success"])}
            success_s = {i for i in ids if int(baseline[(p,"S",task,i)]["success"])}
            for condition in CONDITIONS:
                for future in FUTURES:
                    key = (p,condition,future,task)
                    available = all((p,condition,future,32000,task,i) in outcomes for i in ids)
                    if not available:
                        source_values[key] = None
                        continue
                    success_f = {i for i in ids if outcomes[(p,condition,future,32000,task,i)]}
                    quantities = (len(success_f),len(success_f-success_s),len(success_s-success_f),
                                  len(success_f)-len(success_s),len((success_p-success_s)&success_f))
                    source_values[key] = tuple(Fraction(n*100,50) for n in quantities)
                    checks.need(quantities[3] == quantities[1]-quantities[2], "Exact integer Delta=G-L")
                    for group in ("00","01","10","11"):
                        selected = {i for i in ids if (i in success_p) == bool(int(group[0])) and (i in success_s) == bool(int(group[1]))}
                        counts_by_group[key+(group,)] = (len(selected),len(selected&success_f))
                    for i in subsets[(p,task)]["T20"]:
                        labels = [int(baseline[(p,stage,task,i)]["success"]) for stage in ("P","S")]
                        labels += [outcomes[(p,condition,future,step,task,i)] for step in STEPS]
                        t20_expected[key+(i,)] = (labels,state_machine(labels))
    for row in load_csv(analysis/"e50_metrics.csv"):
        key=(int(row["parent"]),row["condition"],int(row["future"]),row["task"])
        expected=source_values[key]
        for index,name in enumerate(METRICS):
            checks.same(row[name],expected[index] if expected else None,"Per-path endpoint "+name)
    for row in load_csv(analysis/"e50_groups.csv"):
        key=(int(row["parent"]),row["condition"],int(row["future"]),row["task"],row["P_S_group"])
        expected=counts_by_group.get(key)
        if expected is None:
            checks.same(row["final_success_count"],None,"Incomplete group remains NA")
            continue
        n,yes=expected
        checks.same(row["N"],n,"P/S risk-set count")
        checks.same(row["final_success_count"],yes,"P/S final success count")
        checks.same(row["final_success_rate_percent"],Fraction(yes*100,n) if n else None,"P/S conditional success")
        group=key[-1]
        checks.same(row["conditional_gain_percent"],Fraction(yes*100,n) if n and group[1]=="0" else None,"Conditional gain")
        checks.same(row["conditional_loss_percent"],Fraction((n-yes)*100,n) if n and group[1]=="1" else None,"Conditional loss")
        checks.same(row["conditional_recovery_percent"],Fraction(yes*100,n) if n and group=="10" else None,"Conditional recovery")
    for row in load_csv(analysis/"t20_case_trajectories.csv"):
        key=(int(row["parent"]),row["condition"],int(row["future"]),row["task"],int(row["episode_index"]))
        expected=t20_expected.get(key)
        if not expected:
            checks.need(row["pattern"]=="","Missing trajectory remains NA")
            continue
        bits,features=expected
        checks.need(row["pattern"]=="".join(map(str,bits)),"Exact six-label history")
        for name,value in features.items():
            checks.same(row[name],value,"Independent trajectory state machine "+name)
    if complete:
        overall={}
        for condition in CONDITIONS:
            overall[condition]=[sum(source_values[(p,condition,f,task)][m] for p in PARENTS for f in FUTURES for task in TASKS)/40 for m in range(5)]
            for metric,value in zip(METRICS,overall[condition]):
                checks.same(summary["primary"]["conditions"][condition][metric],value,"Whole-study equal-parent "+metric)
        difference=[a-b for a,b in zip(overall["dose625"],overall["dose25"])]
        for metric,value in zip(METRICS,difference):
            checks.same(summary["primary"]["paired_BP_minus_uniform"][metric],value,"Whole-study paired contrast "+metric)
        stop_value = sum(int(row["success"]) for row in baseline_rows if row["stage"]=="S")/10
        checks.same(summary["primary"]["conditions"]["STOP"]["J"],stop_value,"STOP uses fixed S policy")
        for row in load_csv(analysis/"task_contributions.csv"):
            task,condition=row["task"],row["condition"]
            for m,metric in enumerate(METRICS):
                if condition=="STOP":
                    value=Fraction(sum(int(r["success"]) for r in baseline_rows if r["stage"]=="S" and r["task"]==task)*100,250) if m==0 else Fraction(0)
                else:
                    value=sum(source_values[(p,condition,f,task)][m] for p in PARENTS for f in FUTURES)/10
                checks.same(row[metric],value,"Task contribution "+metric)
        for row in load_csv(analysis/"future_results.csv"):
            for m,metric in enumerate(METRICS):
                value=sum(source_values[(p,row["condition"],int(row["future"]),task)][m] for p in PARENTS for task in TASKS)/20
                checks.same(row[metric],value,"Future-specific outcome "+metric)
        for row in load_csv(analysis/"leave_one_parent_out.csv"):
            selected=[p for p in PARENTS if p != int(row["excluded_parent"])]
            for m,metric in enumerate(METRICS):
                value=sum(source_values[(p,"dose625",f,t)][m]-source_values[(p,"dose25",f,t)][m]
                          for p in selected for f in FUTURES for t in TASKS)/32
                checks.same(row[metric],value,"LOPO descriptive "+metric)
        counts=np.load(analysis/"case_resample_counts.npz")
        recorded=np.load(analysis/"bootstrap_draws.npz")
        n=int(summary["bootstrap"]["draws"])
        rng=np.random.default_rng(640303)
        independent=np.zeros((n,2,5));ind_future=np.zeros((n,2,2,5));ind_task=np.zeros((n,4,2,5))
        ind_stop=np.zeros(n);ind_path=np.zeros((n,2,5))
        for pi,p in enumerate(PARENTS):
            for ti,task in enumerate(TASKS):
                a=rng.multinomial(50,np.full(50,1/50),size=n).astype(np.uint8)
                b=rng.multinomial(20,np.full(20,1/20),size=n).astype(np.uint8)
                checks.need(np.array_equal(a,counts["E50"][pi,ti]),"Every E50 draw reproduces frozen RNG")
                checks.need(np.array_equal(b,counts["T20"][pi,ti]),"Every T20 draw reproduces frozen RNG")
                ids=subsets[(p,task)]["E50"]
                pbits=[int(baseline[(p,"P",task,i)]["success"]) for i in ids]
                sbits=[int(baseline[(p,"S",task,i)]["success"]) for i in ids]
                ind_stop+=(a.astype(np.int32)@np.array(sbits,dtype=np.int32))/10
                for ci,condition in enumerate(CONDITIONS):
                    for fi,future in enumerate(FUTURES):
                        futurebits=[outcomes[(p,condition,future,32000,task,i)] for i in ids]
                        integer_vectors=np.array([[y,int(not s and y),int(s and not y),y-s,int(p0 and not s and y)]
                                                  for p0,s,y in zip(pbits,sbits,futurebits)],dtype=np.int32)
                        weighted=a.astype(np.int32)@integer_vectors
                        independent[:,ci]+=weighted/20  # 100/(50*4tasks*2future*5parent)
                        ind_future[:,ci,fi]+=weighted/10
                        ind_task[:,ti,ci]+=weighted/5
                        feature_vectors=np.array([[t20_expected[(p,condition,future,task,i)][1][name] for name in PATH_METRICS]
                                                  for i in subsets[(p,task)]["T20"]],dtype=np.int32)
                        ind_path[:,ci]+=(b.astype(np.int32)@feature_vectors)/8
        for key,expected in (("endpoint",independent),("paired",independent[:,1]-independent[:,0]),
                             ("future",ind_future),("task",ind_task),("STOP_J",ind_stop),("trajectory",ind_path)):
            checks.need(np.allclose(recorded[key],expected,rtol=0,atol=1e-10),"All bootstrap draws independently match: "+key)
        for row in load_csv(analysis/"case_intervals.csv"):
            kind,condition,metric=row["scope"],row["condition"],row["metric"]
            if kind=="E50":
                if condition=="STOP":values=ind_stop
                elif condition=="dose625_minus_dose25":values=(independent[:,1]-independent[:,0])[:,METRICS.index(metric)]
                else:values=independent[:,CONDITIONS.index(condition),METRICS.index(metric)]
            elif condition=="dose625_minus_dose25":values=(ind_path[:,1]-ind_path[:,0])[:,PATH_METRICS.index(metric)]
            else:values=ind_path[:,CONDITIONS.index(condition),PATH_METRICS.index(metric)]
            checks.same(row["lower"],percentile(values,.025),"Independent sorted lower percentile",1e-10)
            checks.same(row["upper"],percentile(values,.975),"Independent sorted upper percentile",1e-10)
    ledger=load_csv(analysis/"physical_cost_ledger.csv")
    for row in ledger:
        if row["status"]=="completed" and row["id"] in lengths:
            checks.same(row["evaluation_steps"],lengths[row["id"]],"Actual evaluation step sum")
            checks.same(row["training_steps"],32000,"Actual completed training steps")
        checks.same(row["environment_steps"],int(row["training_steps"])+int(row["evaluation_steps"]),"Physical cost identity")
    for key in ("training_steps","evaluation_steps","environment_steps"):
        checks.same(summary["costs_all_research_attempts"][key],sum(int(row[key]) for row in ledger),"All-attempt cost total")
    tech_ledger=load_csv(analysis/"technical_cost_ledger.csv")
    checks.same(summary["technical_steps"],sum(int(row["environment_steps"]) for row in tech_ledger),"Separate technical costs")
    plan=load_json(asset("campaign_plan"))
    checks.same(summary["total_environment_steps_all_attempts"],summary["technical_steps"]+
                summary["costs_all_research_attempts"]["environment_steps"]+int(plan.get("new_P_S_evaluation_steps",0)),"All physical costs reconcile")
    checks.need(summary["analysis_new_environment_steps"]==summary["analysis_SAC_updates"]==0,"Pure-file analysis cost")
    checks.need(summary["future_execution_authorized_by_analysis"] is False,"No effect-based progression")
    save_json(run/"verified_inputs.json",{"analysis":str(analysis),"summary_sha256":sha(analysis/"summary.json"),
                                          "asset_receipt_sha256":sha(analysis/"input_assets.json"),"case_count":len(outcomes)})
    return complete


def self_test(checks):
    for code in range(64):
        bits=list(map(int,format(code,"06b")))
        result=state_machine(bits)
        checks.need(result["gain_transitions"]-result["loss_transitions"]==bits[-1]-bits[0],"Independent trajectory conservation")
    checks.same(percentile(np.array([0,10,20,30]),.25),7.5,"Linear percentile interpolation")
    checks.need(state_machine([1,0,1,0,1,0])["recovery_transitions"]==2,"Multiple recoveries")
    checks.need(state_machine([0,1,1,1,1,1])["recovery_transitions"]==0,"First acquisition is not recovery")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-dir")
    parser.add_argument("--self-test",action="store_true")
    args=parser.parse_args()
    if not args.analysis_dir and not args.self_test:
        parser.error("--analysis-dir or --self-test required")
    run=make_run();started=time.perf_counter();cpu=time.process_time();checks=Checks()
    try:
        if args.self_test:
            self_test(checks);complete=False
        else:
            complete=validate(args.analysis_dir,checks,run)
        save_json(run/"summary.json",{"status":"passed","checks_passed":checks.passed,
                                       "full_campaign":complete,"self_test_only":args.self_test,
                                       "scientific_effect_certified":False,"new_environment_steps":0,
                                       "SAC_updates":0,"wall_seconds":time.perf_counter()-started,
                                       "cpu_seconds":time.process_time()-cpu,"python":sys.version,
                                       "numpy":np.__version__,"platform":platform.platform()})
        save_json(run/"COMPLETE.json",{"status":"completed","summary_sha256":sha(run/"summary.json")})
    except BaseException:
        save_json(run/"FAILED.json",{"checks_passed_before_failure":checks.passed,"traceback":traceback.format_exc(),
                                     "new_environment_steps":0,"wall_seconds":time.perf_counter()-started})
        raise
    print(json.dumps({"verification_dir":str(run),"checks_passed":checks.passed},ensure_ascii=False))


if __name__=="__main__":
    main()
