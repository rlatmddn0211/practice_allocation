"""Freeze and run the authorized ten evaluations; no learning or C scheduling."""
import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

os.environ["PRACTICE_SUITE"] = "B"
from practice_allocation.core import ROOT, source_hashes, file_sha256, write_json, utc_now
from practice_allocation.study_io import source_snapshot


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def reference(path):
    return {"path": str(Path(path).resolve()), "sha256": file_sha256(Path(path))}


def atomic(path, data):
    path = Path(path)
    tmp = path.with_name(path.name+"."+uuid.uuid4().hex[:8]+".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    os.replace(tmp, path)


def unique(parent, label):
    p = parent/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+label+"_"+uuid.uuid4().hex[:8])
    p.mkdir(parents=True, exist_ok=False)
    return p


def prepare():
    out = unique(ROOT/"results", "B_evaluation")
    source_snapshot(out)
    hashes = source_hashes()
    protocol = read(ROOT/"protocol.json")
    inputs = {}

    def checked(path, expected=None):
        path = Path(path).resolve()
        h = file_sha256(path)
        inputs[str(path)] = h
        if expected and expected != h:
            raise RuntimeError("Input hash mismatch: "+str(path))
        return read(path)

    old = Path(checked(ROOT.parent/"44_selection_value_stage1_checkpoint36_v2/ACTIVE_CAMPAIGN.json")["campaign"])
    complete = checked(old/"COMPLETE.json")
    completion = checked(complete["summary"]["path"], complete["summary"]["sha256"])
    if completion["execution_status"] != "completed":
        raise RuntimeError("Stage 1 incomplete")
    frozen = checked(old/"plan.json", checked(old/"plan_integrity.json")["sha256"])
    jobmap = {j["id"]: j for j in frozen["jobs"]}

    def result(jobid):
        marker = checked(old/"completed"/(jobid+".json"))
        value = checked(marker["result_ref"]["path"], marker["result_ref"]["sha256"])
        return value, Path(marker["attempt"])

    jobs, baseline, banks = [], [], []
    for p in protocol["original_seeds"]:
        bankresult, _ = result(f"B_s{p}_bank")
        bank = bankresult["bank"]
        checked(bank["path"], bank["sha256"])
        banks.append({"original_seed": p, "bank": bank})
        original, _ = result(f"B_s{p}_parent_O")
        inputs[original["episodes_path"]] = file_sha256(Path(original["episodes_path"]))
        if inputs[original["episodes_path"]] != original["episodes_sha256"]:
            raise RuntimeError("Parent outcome hash mismatch")
        baseline.append(dict(original_seed=p, continuation=0, horizon=0,
                             outcome={"path": original["episodes_path"], "sha256": original["episodes_sha256"]}))
        for r in protocol["continuations"]:
            jobid = f"B_s{p}_r{r}_dose625_t8000"
            train, attempt = result(jobid)
            cp = train["checkpoint"]
            manifest = checked(Path(cp["path"])/"checkpoint_manifest.json", cp["manifest_sha256"])
            if manifest["step"] != 208000:
                raise RuntimeError("Not an 8k checkpoint")
            for name, expected in manifest["files"].items():
                path = Path(cp["path"])/name
                actual = file_sha256(path)
                inputs[str(path)] = actual
                if actual != expected:
                    raise RuntimeError("Checkpoint binary hash mismatch")
            runtime = checked(attempt/"runtime.json")
            config = {**runtime["config"], "version": ROOT.name}
            seed = jobmap[f"B_s{p}_r{r}_dose625_t4000"]["continuation_rng_seed"]
            final, _ = result(f"B_s{p}_r{r}_dose625_O")
            inputs[final["episodes_path"]] = file_sha256(Path(final["episodes_path"]))
            if inputs[final["episodes_path"]] != final["episodes_sha256"]:
                raise RuntimeError("Final outcome hash mismatch")
            baseline.append(dict(original_seed=p, continuation=r, horizon=40000,
                                 outcome={"path": final["episodes_path"], "sha256": final["episodes_sha256"]}))
            jobs.append(dict(id=f"B_s{p}_r{r}_dose625_8k_O100", kind="research_8k_evaluation",
                             original_seed=p, continuation=r, continuation_rng_seed=seed,
                             horizon=8000, expected_absolute_step=208000, config=config,
                             checkpoint=cp, bank=bank, cases_per_task=100, chunk_cases_per_task=10))
    known, known_attempt = result("B_s41011_r4201_dose625_O")
    finalcp, _ = result("B_s41011_r4201_dose625_t40000")
    cpmanifest = checked(Path(finalcp["checkpoint"]["path"])/"checkpoint_manifest.json",
                         finalcp["checkpoint"]["manifest_sha256"])
    for name, expected in cpmanifest["files"].items():
        path = Path(finalcp["checkpoint"]["path"])/name
        inputs[str(path)] = file_sha256(path)
        if inputs[str(path)] != expected:
            raise RuntimeError("Known checkpoint binary mismatch")
    technical = {**jobs[0], "id": "known_BP40k_41011_4201_first2", "kind": "technical_known_policy",
                 "horizon": 40000, "expected_absolute_step": 240000,
                 "checkpoint": finalcp["checkpoint"], "cases_per_task": 2, "chunk_cases_per_task": 1,
                 "known_outcome": {"path": known["episodes_path"], "sha256": known["episodes_sha256"]}}
    plan = dict(version=ROOT.name, created_at=utc_now(), source_hashes=hashes, jobs=jobs,
                technical=technical, baselines=baseline, banks=banks, prior_campaign=str(old),
                protocol=protocol, execution_scope="B evaluation only")
    write_json(out/"plan.json", plan)
    write_json(out/"plan_integrity.json", reference(out/"plan.json"))
    write_json(out/"input_hashes.json", inputs)
    for name in ("completed", "jobs", "launches"):
        (out/name).mkdir()
    atomic(out/"STATUS.json", {"status": "prepared", "completed": 0, "total": 10, "new_training_steps": 0,
                              "research_evaluation_upper": 2000000, "created_at": utc_now()})
    atomic(ROOT/"ACTIVE_CAMPAIGN.json", {"campaign": str(out), "created_at": utc_now()})
    print(json.dumps({"campaign": str(out), "policies": len(jobs), "research_evaluation_upper": 2000000,
                      "technical_evaluation_upper": 4000, "new_training_steps": 0}, indent=2), flush=True)


def launch_job(cam, job, hashes):
    attempt = unique(cam/"jobs"/job["id"], "attempt")
    q = {**job, "output": str(attempt), "source_hashes": hashes}
    write_json(attempt/"request.json", q)
    stdout = (attempt/"stdout.log").open("x", encoding="utf-8")
    stderr = (attempt/"stderr.log").open("x", encoding="utf-8")
    env = dict(os.environ)
    env.update(PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
               PRACTICE_SUITE="B", CUBLAS_WORKSPACE_CONFIG=":4096:8")
    proc = subprocess.Popen([sys.executable, "-u", "-B", str(cam/"source_snapshot/worker.py"),
                             "--request", str(attempt/"request.json")], cwd=ROOT.parent,
                            stdout=stdout, stderr=stderr, env=env,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    write_json(attempt/"process.json", {"pid": proc.pid, "started_at": utc_now()})
    return {"job": job, "attempt": attempt, "proc": proc, "stdout": stdout, "stderr": stderr}


def finalize_job(cam, entry):
    attempt, job = entry["attempt"], entry["job"]
    entry["stdout"].close()
    entry["stderr"].close()
    if entry["proc"].returncode != 0 or not (attempt/"result.json").exists():
        return False
    cost = read(attempt/"costs.json")
    result = read(attempt/"result.json")
    if cost["status"] != "completed" or cost["costs"]["train_iterations"] != 0:
        return False
    if not result["evaluation_state_unchanged"] or result["evaluation"]["episodes"] != job["cases_per_task"]*4:
        return False
    write_json(cam/"completed"/(job["id"]+".json"), {
        "id": job["id"], "attempt": str(attempt), "result_ref": reference(attempt/"result.json"),
        "cost_ref": reference(attempt/"costs.json"), "completed_at": utc_now()})
    return True


def run_campaign(cam):
    cam = Path(cam).resolve()
    # OS-backed controller lock releases on process exit; no duplicate coordinator.
    import msvcrt
    lock = (cam/"controller.lock").open("a+b")
    if lock.tell() == 0:
        lock.write(b"0")
        lock.flush()
    lock.seek(0)
    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    planref = read(cam/"plan_integrity.json")
    if file_sha256(cam/"plan.json") != planref["sha256"]:
        raise RuntimeError("Plan changed after freeze")
    plan = read(cam/"plan.json")
    if source_hashes() != plan["source_hashes"]:
        raise RuntimeError("48 source changed after freeze")
    # Refuse to duplicate any incomplete attempt; recovery must inspect it first.
    for job in [plan["technical"]]+plan["jobs"]:
        existing = list((cam/"jobs"/job["id"]).glob("*"))
        if existing and not (cam/"completed"/(job["id"]+".json")).exists():
            raise RuntimeError("Incomplete preserved attempt needs inspection: "+job["id"])
    start = time.perf_counter()
    technical = plan["technical"]
    if not (cam/"completed"/(technical["id"]+".json")).exists():
        atomic(cam/"STATUS.json", {"status": "technical_validation", "completed": 0, "total": 10})
        entry = launch_job(cam, technical, plan["source_hashes"])
        entry["proc"].wait()
        if not finalize_job(cam, entry):
            atomic(cam/"STATUS.json", {"status": "technical_integrity_failed", "attempt": str(entry["attempt"])})
            return 1
    write_json(cam/("readiness_"+uuid.uuid4().hex[:8]+".json"),
               {"time": utc_now(), "technical_completed": technical["id"], "scope": "evaluation equivalence, not scientific effect"})
    pending = [j for j in plan["jobs"] if not (cam/"completed"/(j["id"]+".json")).exists()]
    active, failed = [], []
    while pending or active:
        while pending and len(active) < plan["protocol"]["evaluation"]["parallel_workers"] and not failed:
            active.append(launch_job(cam, pending.pop(0), plan["source_hashes"]))
        for entry in list(active):
            if entry["proc"].poll() is None:
                continue
            if not finalize_job(cam, entry):
                failed.append({"job": entry["job"]["id"], "attempt": str(entry["attempt"])})
            active.remove(entry)
        complete = [j for j in plan["jobs"] if (cam/"completed"/(j["id"]+".json")).exists()]
        costs = [read(read(cam/"completed"/(j["id"]+".json"))["cost_ref"]["path"]) for j in complete]
        running = []
        for e in active:
            progress = e["attempt"]/"progress.jsonl"
            last = None
            if progress.exists():
                lines = progress.read_text(encoding="utf-8").splitlines()
                if lines:
                    try:
                        last = json.loads(lines[-1])
                    except json.JSONDecodeError:
                        pass
            running.append({"job": e["job"]["id"], "pid": e["proc"].pid, "attempt": str(e["attempt"]), "latest": last})
        atomic(cam/"STATUS.json", dict(status="draining_after_failure" if failed else "evaluating",
                                      updated_at=utc_now(), completed=len(complete), total=10,
                                      running=running, pending=[j["id"] for j in pending], failures=failed,
                                      research_steps_completed=sum(c["costs"]["environment_steps"] for c in costs),
                                      new_training_steps=0, elapsed_seconds=time.perf_counter()-start))
        if failed and not active:
            atomic(cam/"STATUS.json", {"status": "failed", "failures": failed, "completed": len(complete), "total": 10})
            return 1
        if pending or active:
            time.sleep(3)
    cost_rows = []
    for job in [technical]+plan["jobs"]:
        marker = read(cam/"completed"/(job["id"]+".json"))
        cost = read(marker["cost_ref"]["path"])
        cost_rows.append({"id": job["id"], **cost})
    research = sum(c["costs"]["environment_steps"] for c in cost_rows if c["research"])
    technical_steps = sum(c["costs"]["environment_steps"] for c in cost_rows if not c["research"])
    if research > 2000000 or technical_steps > 4000 or any(c["costs"]["train_iterations"] for c in cost_rows):
        raise RuntimeError("Evaluation/training budget violation")
    summary = dict(execution_status="completed", completed_at=utc_now(), policies=10, research_episodes=4000,
                   research_evaluation_steps=research, technical_evaluation_steps=technical_steps,
                   total_new_environment_steps=research+technical_steps, new_training_steps=0, new_SAC_updates=0,
                   elapsed_seconds=time.perf_counter()-start, costs=cost_rows,
                   C="held_not_scheduled", original_stages_2_3="held_not_scheduled",
                   analysis="independent version49, no selector fitting")
    target = cam/("completion_"+uuid.uuid4().hex[:8]+".json")
    write_json(target, summary)
    write_json(cam/"COMPLETE.json", {"summary": reference(target), "completed_at": utc_now()})
    atomic(cam/"STATUS.json", {"status": "completed", "completed": 10, "total": 10,
                              "research_evaluation_steps": research, "technical_evaluation_steps": technical_steps,
                              "new_SAC_updates": 0, "updated_at": utc_now()})
    print(json.dumps(summary, indent=2), flush=True)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=("prepare", "run"))
    ap.add_argument("--campaign")
    args = ap.parse_args()
    if args.command == "prepare":
        prepare()
        return 0
    cam = args.campaign or read(ROOT/"ACTIVE_CAMPAIGN.json")["campaign"]
    return run_campaign(cam)


if __name__ == "__main__":
    raise SystemExit(main())
