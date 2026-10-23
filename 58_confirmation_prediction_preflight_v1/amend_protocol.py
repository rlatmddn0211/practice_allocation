"""Create new-version documents/inputs once; never mutate version 57."""
import copy
import shutil
from record import HERE, ROOT, Run, dump, read, sha


def main():
    run = Run("amend")
    try:
        cfg = read(HERE / "audit_config.json")
        oldpath = ROOT / cfg["previous_version"] / "protocol.json"
        run.input(oldpath, cfg["previous_protocol_sha256"])
        old = read(oldpath)
        new = copy.deepcopy(old)
        new["version"] = cfg["version"]
        new["status"] = "pre_execution_clarification_and_locked_prediction_feasibility_audit"
        new["question"] = "On cases failed by both 8k states, does reference state-case information within the four-observation common grade improve fresh-future predictions beyond the specified M0 grade and state-specific monotone curves, alongside fresh-future same-minus-cross overlap replication?"
        new["amendment"] = {
            "previous_protocol": str(oldpath.relative_to(ROOT)), "previous_sha256": cfg["previous_protocol_sha256"],
            "prediction_sha256_unchanged": cfg["prediction_sha256"], "jobs_sha256_unchanged": cfg["jobs_sha256"],
            "models_seeds_eligibility_weights_and_numeric_thresholds_unchanged": True,
            "execution_authorized_by_this_amendment": False,
        }
        new["claim_scope"] = {
            "positive_G": "M1 improves new-future Brier prediction relative to THIS M0: total reference successes graded 0..4 plus separately fitted parent/task/state monotone curves",
            "does_not_establish": ["exclusion of all common latent-difficulty explanations", "state-dependent reversal of latent case difficulty ranks", "a state-specific causal learning mechanism", "an online 8k selector or allocation improvement"],
            "remaining_explanation": "within-grade reference state allocation may carry additional information about unobserved common case difficulty under different state response curves, despite both mean-preservation constraints",
            "current_support": "primary M0/M1 differences occur only in PU for parents 41011,41013,41015; G cannot test incremental information in DC or other parents where forecasts are identical",
        }
        new["primary_prediction_score"].update({
            "exact_parent_formula": "BS_p(M)=sum_{t in DC,PU;i in I_pt;s=1,2;f=3,4}(pM_psi-Y_psfi)^2/(4*N_p); N_p=N_pDC+N_pPU",
            "exact_overall_formula": "G=sum_p[BS_p(M0)-BS_p(M1)]/5; leave-one-parent-out uses /4 without refitting",
            "task_weights_within_parent": "N_pt/N_p, not equal task weights; empty task contributes no observations and its conditional score is NA",
            "case_scope": "all 548 eligible DC/PU cases, including zero-correction cases; do not restrict denominator to 49 changed cases",
        })
        new["prediction_feasibility_audit"] = {
            "inputs": "locked prediction CSV only; no F3/F4 labels",
            "observation_gain": "2*d*(y-p)-d*d, d=M1-M0",
            "observation_upper": "max(gain(y=0),gain(y=1)); attained algebraically by y=1 if d>0 and y=0 if d<0",
            "aggregation": "mean over two state rows within each parent's pooled eligible DC/PU cases, then equal parent mean; same forecasts on both future labels",
            "required_outputs": ["changed cases and parent/task/grade distribution", "correction magnitude", "probability bounds and both mean constraints", "overall and all five leave-one-parent-out lower/upper bounds"],
            "interpretation": "label-space bound only, neither forecast nor power analysis nor guarantee of joint D/interval/investment gate feasibility under real learned policies",
        }
        new["proposed_investment_gate"].update({
            "separate_scientific_evidence_and_investment_status": True,
            "positive_but_below_size_threshold": "If a conditional interval lower bound is positive but D<0.10pp or G<0.001, report positive conditional evidence and observed size below investment threshold; hold further investment",
            "positive_but_robustness_gate_failed": "Report positive conditional evidence with parent concentration or future-direction limitation; hold investment, do not relabel as no effect",
            "leave_parent_out_interpretation": "excludes sole dependence on any one parent for that aggregate; does not demonstrate broad replication across parents",
            "missing_confirmation": "not executed/not measured, not failed or null scientific result",
        })
        new["paper_scope"]["primary"] = "starting-state-associated acquisition patterns; any incremental predictive claim is relative to the explicitly specified common-grade M0 only"
        new["paper_scope"]["completion_evidence"][1] = "fresh-future predictive comparison against the specified grade/monotone M0, not elimination of all common latent-difficulty models"
        changes = [key for key in set(old) | set(new) if old.get(key) != new.get(key)]
        run.check(set(changes) <= set(cfg["allowed_protocol_changes"]), "only_allowed_protocol_sections_change")
        for key in ["learning_proposal", "budget_proposal", "primary_D", "models", "uncertainty", "second_bundle", "execution_authorized", "scheduled"]:
            run.check(new[key] == old[key], "preserved:" + key)
        for key, value in old["proposed_investment_gate"].items():
            run.check(new["proposed_investment_gate"][key] == value, "preserved_original_gate:" + key)
        run.check(not (HERE / "protocol.json").exists() and not (HERE / "inputs").exists(), "new_outputs_only")
        (HERE / "inputs").mkdir()
        prep = ROOT / cfg["prepared_relative"]
        sources = [
            (prep / "frozen_reference_predictions.csv", cfg["prediction_sha256"]),
            (prep / "proposed_jobs.csv", cfg["jobs_sha256"]),
            (ROOT / old["reference_csv"], old["reference_csv_sha256"]),
            (ROOT / old["state_manifest"], old["state_manifest_sha256"]),
        ]
        for path, digest in sources:
            run.input(path, digest)
            shutil.copy2(path, HERE / "inputs" / path.name)
        dump(HERE / "inputs" / "provenance.json", run.inputs)
        dump(HERE / "protocol.json", new)
        run.check(sha(oldpath) == cfg["previous_protocol_sha256"], "old_protocol_preserved")
        dump(run.out / "protocol_changes.json", {key: {"before": old.get(key), "after": new.get(key)} for key in sorted(changes)})
        run.input(HERE / "protocol.json")
        return run.finish({"status": "amendment_written_no_execution", "changed_sections": sorted(changes), "new_protocol_sha256": sha(HERE / "protocol.json"), "prediction_sha256": cfg["prediction_sha256"], "launch_or_queue_created": False})
    except BaseException as exc:
        return run.finish(exc=exc)


if __name__ == "__main__":
    raise SystemExit(main())
