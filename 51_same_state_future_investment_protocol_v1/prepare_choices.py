"""Prepare fixed old-future choices; never load a learner or run an environment."""
import csv
import hashlib
import io
import json
import shutil
import sys
import time
import traceback
import uuid
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    start, cpu = time.perf_counter(), time.process_time()
    out = HERE / "results" / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "_choice_preparation_" + uuid.uuid4().hex[:8])
    (out / "source_snapshot").mkdir(parents=True, exist_ok=False)
    for p in sorted(HERE.iterdir()):
        if p.is_file() and p.suffix in (".py", ".json", ".md"):
            shutil.copy2(p, out / "source_snapshot" / p.name)
    checks, inputs = [], {}

    def dump(name, data):
        (out / name).write_text(json.dumps(data, ensure_ascii=False, indent=2,
                                         allow_nan=False), encoding="utf-8")

    def read(p):
        p = Path(p)
        data = p.read_bytes()
        inputs[str(p)] = hashlib.sha256(data).hexdigest()
        return data

    def check(label, passed):
        checks.append({"check": label, "passed": bool(passed)})
        if not passed:
            raise AssertionError(label)

    def write_csv(name, rows):
        with (out / name).open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    try:
        cfg = json.loads(read(HERE / "protocol.json"))
        raw = read(ROOT / cfg["source_outcomes"])
        check("pinned_outcomes", hashlib.sha256(raw).hexdigest() == cfg["source_outcomes_sha256"])
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
        check("source_rows", len(rows) == 10000)
        data, identities = {}, {}
        for r in rows:
            key = (int(r["original_seed"]), r["policy"], r["task"], int(r["episode_index"]))
            check("unique_case:" + str(key), key not in data)
            check("binary:" + str(key), r["success"] in ("0", "1"))
            data[key] = int(r["success"])
            ik = (key[0], key[2], key[3])
            identity = (r["seed"], r["initial_state_hash"])
            check("matched_case:" + str(key), ik not in identities or identities[ik] == identity)
            identities[ik] = identity
        check("parent_domain", {k[0] for k in data} == set(cfg["parents"]))
        provenance_raw = read(ROOT / cfg["source_checkpoint_provenance"])
        check("pinned_provenance", hashlib.sha256(provenance_raw).hexdigest()
              == cfg["source_checkpoint_provenance_sha256"])
        provenance = json.loads(provenance_raw)
        check("ten_states", len(provenance) == 10)
        choices, states = [], []
        for pi, parent in enumerate(cfg["parents"]):
            for continuation in cfg["prefix_continuations"]:
                prov = next(p for p in provenance if p["original_seed"] == parent
                            and p["continuation"] == continuation)
                manifest = Path(prov["checkpoint"]["path"]) / "checkpoint_manifest.json"
                check("checkpoint_manifest:" + str((parent, continuation)),
                      hashlib.sha256(read(manifest)).hexdigest() == prov["checkpoint"]["manifest_sha256"])
                check("bank:" + str(parent), hashlib.sha256(read(prov["bank"]["path"])).hexdigest()
                      == prov["bank"]["sha256"])
                new_seed = int(np.random.SeedSequence([510202, 51, parent, continuation]).generate_state(1)[0])
                schedule_seed = int(np.random.SeedSequence([new_seed, 10]).generate_state(1)[0])
                check("different_future_seed:" + str((parent, continuation)),
                      new_seed != prov["continuation_rng_seed"])
                states.append(dict(parent=parent, prefix_continuation=continuation,
                                   old_continuation_rng_seed=prov["continuation_rng_seed"],
                                   proposed_new_future_root_seed=new_seed,
                                   proposed_schedule_seed=schedule_seed,
                                   checkpoint=prov["checkpoint"], bank=prov["bank"],
                                   packages=prov["packages"]))
                for label, lo, hi, scoring in (("A", 0, 49, "B"), ("B", 50, 99, "A"),
                                                ("O100", 0, 99, "O100_secondary")):
                    success = []
                    for policy in (f"J8_{continuation}", f"J40_{continuation}"):
                        success.append(sum(data[(parent, policy, t, i)]
                                           for t in cfg["tasks"] for i in range(lo, hi + 1)))
                    denominator = 4 * (hi - lo + 1)
                    delta = Fraction(100 * (success[1] - success[0]), denominator)
                    choice = "continue" if delta > 0 else "stop"
                    # Independent aggregation through raw rows, without the indexed table.
                    independent = [sum(int(r["success"]) for r in rows
                                       if int(r["original_seed"]) == parent
                                       and r["policy"] == policy and lo <= int(r["episode_index"]) <= hi)
                                   for policy in (f"J8_{continuation}", f"J40_{continuation}")]
                    check("independent_sum:" + str((parent, continuation, label)), independent == success)
                    choices.append(dict(parent=parent, prefix_continuation=continuation,
                                        selection_cases=label, scoring_cases=scoring,
                                        old_J8_percent=100 * success[0] / denominator,
                                        old_J40_percent=100 * success[1] / denominator,
                                        old_late_pp=float(delta), fixed_action=choice))
        check("unique_new_seeds", len({s["proposed_new_future_root_seed"] for s in states}) == 10)
        old_seeds = {s["old_continuation_rng_seed"] for s in states}
        check("no_old_new_seed_overlap", not old_seeds.intersection(s["proposed_new_future_root_seed"] for s in states))
        check("budget", cfg["budget_proposal"]["main_environment_cap"] == 10 * 32000 + 10 * 4 * 100 * 500)
        check("no_execution_authorization", not cfg["execution_authorized"] and not cfg["scheduled"])
        write_csv("fixed_choices.csv", choices)
        dump("state_manifest.json", states)
        lines = ["# 실행 전 고정 선택표", "",
                 "이 표는 기존 미래의 성적을 사용한다. 실제 8k 의사결정 규칙이 아니며 새 미래 성과는 아직 없다.",
                 "A=과제별 사례0–49, B=50–99. 양수일 때 지속, 동률·음수일 때 중단.",
                 "주 분석은 A 선택→새 미래 B 채점과 B 선택→새 미래 A 채점을 모두 평균한다.", "",
                 "| 부모 / 경로 | 기존 전체 후기 변화 %p | O100 보조 선택 | A 선택→B 채점 | B 선택→A 채점 |",
                 "| --- | ---: | --- | --- | --- |"]
        names = {"continue": "지속", "stop": "중단"}
        for state in states:
            subset = {r["selection_cases"]: r for r in choices
                      if r["parent"] == state["parent"] and r["prefix_continuation"] == state["prefix_continuation"]}
            lines.append(f"| {state['parent']} / {state['prefix_continuation']} | "
                         f"{subset['O100']['old_late_pp']:+.2f} | {names[subset['O100']['fixed_action']]} | "
                         f"{names[subset['A']['fixed_action']]} ({subset['A']['old_late_pp']:+.2f}) | "
                         f"{names[subset['B']['fixed_action']]} ({subset['B']['old_late_pp']:+.2f}) |")
        (out / "fixed_choices_ko.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        summary = dict(status="prepared_and_arithmetic_checked_not_executed",
                       states=10, parents=5, fixed_choice_rows=len(choices),
                       full_choices=dict(Counter(r["fixed_action"] for r in choices if r["selection_cases"] == "O100")),
                       primary_half_choices=dict(Counter(r["fixed_action"] for r in choices if r["selection_cases"] != "O100")),
                       checks_passed=len(checks), failed_checks=0,
                       new_environment_steps=0, new_training_steps=0, new_SAC_updates=0,
                       future_outcomes_observed=False, policy_files_loaded=False,
                       wall_seconds=time.perf_counter() - start, CPU_seconds=time.process_time() - cpu,
                       python=sys.version, numpy=np.__version__)
        dump("summary.json", summary)
        dump("checks.json", checks)
        dump("input_hashes.json", inputs)
        dump("source_hashes.json", {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in (out / "source_snapshot").iterdir()})
        dump("output_hashes.json", {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in out.iterdir() if p.is_file()})
        (HERE / "PREPARED_CHOICES.json").write_text(json.dumps(dict(
            run=str(out), summary_sha256=hashlib.sha256((out / "summary.json").read_bytes()).hexdigest(),
            choices_sha256=hashlib.sha256((out / "fixed_choices.csv").read_bytes()).hexdigest(),
            state_manifest_sha256=hashlib.sha256((out / "state_manifest.json").read_bytes()).hexdigest(),
            protocol_sha256=hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest()),
            indent=2), encoding="utf-8")
        print(json.dumps(dict(run=str(out), **summary), indent=2))
    except BaseException:
        dump("failure.json", dict(traceback=traceback.format_exc(), checks=checks, inputs=inputs))
        raise


if __name__ == "__main__":
    main()
