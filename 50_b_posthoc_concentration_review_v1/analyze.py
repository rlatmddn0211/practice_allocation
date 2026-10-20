"""Existing-file B supplement, exact rational arithmetic, no learner imports."""
import csv
import hashlib
import io
import itertools
import json
import platform
import shutil
import sys
import time
import traceback
import uuid
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction as F
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    start, cpu = time.perf_counter(), time.process_time()
    out = HERE/"results"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_analysis_"+uuid.uuid4().hex[:8])
    snap = out/"source_snapshot"
    snap.mkdir(parents=True, exist_ok=False)
    for p in list(HERE.glob("*.py"))+[HERE/"analysis_config.json"]:
        shutil.copy2(p, snap/p.name)
    inputs, checks = {}, []

    def dump(name, value):
        with (out/name).open("x", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False,
                      default=lambda x: float(x) if isinstance(x, F) else str(x))

    def check(label, condition):
        checks.append(dict(check=label, passed=bool(condition)))
        if not condition:
            raise AssertionError(label)

    def read(p, expected=None):
        p = Path(p).resolve()
        b = p.read_bytes()
        inputs[str(p)] = hashlib.sha256(b).hexdigest()
        if expected:
            check("hash:"+str(p), inputs[str(p)] == expected)
        return b

    def js(p, expected=None):
        return json.loads(read(p, expected).decode("utf-8-sig"))

    def rows(p, expected=None):
        return list(csv.DictReader(io.StringIO(read(p, expected).decode("utf-8-sig"))))

    def table(name, data):
        with (out/name).open("x", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(data[0]))
            w.writeheader()
            w.writerows({k: float(v) if isinstance(v, F) else v for k, v in row.items()} for row in data)

    mean = lambda xs: sum(xs, F(0))/len(xs)
    try:
        cfg = js(HERE/"analysis_config.json")
        source = ROOT/cfg["input_run"]
        pins = cfg["pinned_inputs"]
        prior = js(source/"summary.json", pins["summary.json"])
        raw = rows(source/"outcomes_25_policies.csv", pins["outcomes_25_policies.csv"])
        assets = rows(source/"input_assets.csv", pins["input_assets.csv"])
        provenance = js(source/"checkpoint_provenance.json", pins["checkpoint_provenance.json"])
        parents, repeats, tasks = cfg["parents"], cfg["continuations"], cfg["tasks"]
        observed, case_identity = {}, {}
        for asset in assets:
            p, q = int(asset["original_seed"]), asset["policy"]
            data = rows(asset["path"], asset["sha256"])
            check("coverage:"+str((p, q)), len(data) == 400 and
                  {(r["task"], int(r["episode_index"])) for r in data} ==
                  set(itertools.product(tasks, range(100))))
            for row in data:
                t, i = row["task"], int(row["episode_index"])
                k = p, q, t, i
                check("unique_binary:"+str(k), k not in observed and row["success"] in ("0", "1"))
                observed[k] = int(row["success"])
                sig = row["seed"], row["initial_state_hash"]
                if (p, t, i) in case_identity:
                    check("case_match:"+str(k), case_identity[p, t, i] == sig)
                case_identity[p, t, i] = sig
        check("asset_count", len(assets) == 25 and len(observed) == len(raw) == 10000)
        for row in raw:
            k = int(row["original_seed"]), row["policy"], row["task"], int(row["episode_index"])
            check("derived_vs_original:"+str(k), observed[k] == int(row["success"]))

        def score(p, q, task=None):
            ts = tasks if task is None else [task]
            return F(sum(observed[p, q, t, i] for t in ts for i in range(100)), len(ts))

        paths, transitions = [], []
        for p, r in itertools.product(parents, repeats):
            a, b, c = score(p, "J0"), score(p, f"J8_{r}"), score(p, f"J40_{r}")
            paths.append(dict(parent=p, continuation=r, J0=a, J8=b, J40=c,
                              late=c-b, hindsight=max(b, c), hindsight_minus_stop=max(b, c)-b,
                              hindsight_minus_continue=max(b, c)-c))
            for t in tasks:
                counts = Counter("".join(str(observed[p, q, t, i]) for q in ("J0", f"J8_{r}", f"J40_{r}"))
                                 for i in range(100))
                transitions.append(dict(parent=p, continuation=r, task=t,
                    **{f"n{pattern}": counts[pattern] for pattern in (f"{j:03b}" for j in range(8))}))

        def aggregate(block):
            j8, j40 = mean([x["J8"] for x in block]), mean([x["J40"] for x in block])
            hindsight = mean([x["hindsight"] for x in block])
            return dict(J8=j8, J40=j40, hindsight=hindsight, observed_better_fixed=max(j8, j40),
                        observed_better_fixed_label="stop8" if j8 >= j40 else "continue40",
                        hindsight_minus_stop=hindsight-j8, hindsight_minus_continue=hindsight-j40,
                        hindsight_minus_observed_better_fixed=hindsight-max(j8, j40))

        full = aggregate(paths)
        check("prior_fixed_means", float(full["J8"]) == prior["means"]["J8"]
              and float(full["J40"]) == prior["means"]["J40"])
        contributions, removed, task_groups = [], [], []
        for p in parents:
            block = [x for x in paths if x["parent"] == p]
            stop = mean([x["hindsight_minus_stop"] for x in block])/len(parents)
            cont = mean([x["hindsight_minus_continue"] for x in block])/len(parents)
            selected = stop if full["observed_better_fixed_label"] == "stop8" else cont
            contributions.append(dict(parent=p, contribution_vs_stop_pp=stop,
                contribution_vs_continue_pp=cont, contribution_vs_observed_better_fixed_pp=selected,
                fraction_of_full_gain=None if full["hindsight_minus_observed_better_fixed"] == 0 else
                selected/full["hindsight_minus_observed_better_fixed"]))
            removed.append(dict(excluded_parent=p, remaining_parents=4,
                                **aggregate([x for x in paths if x["parent"] != p])))
        check("contributions_add", sum(x["contribution_vs_stop_pp"] for x in contributions) ==
              full["hindsight_minus_stop"] and sum(x["contribution_vs_continue_pp"] for x in contributions) ==
              full["hindsight_minus_continue"])
        for label, ps in [("all", parents), ("only41013", [41013]),
                          ("without41013", [p for p in parents if p != 41013])]:
            for t in tasks:
                vals = {key: mean([score(p, "J0" if key == "J0" else f"{key}_{r}", t)
                                  for p, r in itertools.product(ps, repeats)]) for key in ("J0", "J8", "J40")}
                task_groups.append(dict(group=label, task=t, parents=len(ps), **vals,
                                        early=vals["J8"]-vals["J0"], late=vals["J40"]-vals["J8"]))
        components = []
        for label, ps in [("all", parents), ("only41015", [41015])]:
            block = [x for x in transitions if x["parent"] in ps]
            parts = {k: mean([F(x["n"+pattern]) for x in block]) for k, pattern in
                     (("new_success", "001"), ("recovery", "101"),
                      ("old_success_lost_late", "110"), ("early_gain_lost_late", "010"))}
            net = parts["new_success"]+parts["recovery"]-parts["old_success_lost_late"]-parts["early_gain_lost_late"]
            check("net_components:"+label, net == mean([x["late"] for x in paths if x["parent"] in ps]))
            components.append(dict(group=label, **parts, net=net, full_mean_weight=F(len(ps), len(parents))))
        check("reported_hindsight_arithmetic", full["hindsight"] == F(36450, 1000)
              and full["hindsight_minus_observed_better_fixed"] == F(1725, 1000))
        check("concentration", contributions[-1]["contribution_vs_observed_better_fixed_pp"] == F(1550, 1000))
        for row in task_groups:
            if row["task"] == "DC" and row["group"] == "without41013":
                check("DC_excluding41013", (row["J0"], row["J8"], row["J40"]) == (F(985, 10), F(98625, 1000), F(100)))
        table("path_hindsight.csv", paths)
        table("parent_contributions.csv", contributions)
        table("leave_one_parent_out.csv", removed)
        table("task_groups.csv", task_groups)
        table("late_net_components.csv", components)
        table("three_time_pattern_counts.csv", transitions)
        dump("checkpoint_provenance.json", provenance)
        summary = dict(execution_status="completed_existing_data_supplement",
            scientific_scope="posthoc_descriptive_not_online_policy_or_population_bound",
            full=full, contributions=contributions, leave_one_parent_out=removed,
            task_groups=task_groups, late_components=components, independent_parents=5,
            future_draws_per_state=1, future_repetition_proposal=dict(states=10, new_futures_per_state=1,
                training_per_state=32000, training_total=320000, evaluation_cap=2000000,
                main_environment_cap=2320000, technical_cap=None, status="proposal_only_not_scheduled"),
            resource_saving=dict(additional_training_fraction=F(32000,40000),
                total_training_including_parent_fraction=F(32000,240000), noninferiority_established=False),
            prior_fixed_comparison_intervals=prior["global_contrasts_uncertainty"],
            current_candidate_expansion="closed_at_current_evidence",
            C="held_not_scheduled", original_stages_2_3="held_not_scheduled",
            new_environment_steps=0, new_training_steps=0, new_SAC_updates=0,
            wall_seconds=time.perf_counter()-start, CPU_seconds=time.process_time()-cpu,
            runtime=dict(python=sys.version, platform=platform.platform(), numerical_method="exact fractions"))
        dump("summary.json", summary)
        dump("checks.json", dict(passed=len(checks), failed=0, checks=checks))
        dump("input_hashes.json", inputs)
        dump("source_hashes.json", {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in snap.iterdir()})
        dump("output_hashes.json", {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in out.rglob("*") if p.is_file()})
        (HERE/"LATEST_ANALYSIS.json").write_text(json.dumps(dict(run=str(out), summary_sha256=
            hashlib.sha256((out/"summary.json").read_bytes()).hexdigest()), indent=2), encoding="utf-8")
        print(json.dumps(dict(run=str(out), full=full, contributions=contributions, checks=len(checks)),
                         indent=2, default=float))
    except BaseException:
        dump("failure.json", dict(traceback=traceback.format_exc(), checks=checks, input_hashes=inputs,
                                 new_environment_steps=0, new_training_steps=0, new_SAC_updates=0))
        raise


if __name__ == "__main__":
    main()
