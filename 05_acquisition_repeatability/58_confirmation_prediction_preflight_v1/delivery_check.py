"""Check the final Markdown package and create an immutable local review ZIP."""
import ast
import hashlib
import re
import zipfile
from pathlib import Path
from record import HERE, ROOT, Run, dump, read, rows, sha


def main():
    run = Run("delivery")
    try:
        cfg = read(HERE / "audit_config.json")
        audit = HERE / "results" / "20261022T053745Z_audit_b4458b32"
        verified = HERE / "results" / "20261022T053915Z_verify_a759a328"
        amended = HERE / "results" / "20261022T053744Z_amend_fe554a64"
        for prior in [amended, audit, verified]:
            run.input(prior / "COMPLETE.json")
            run.check(not (prior / "FAILED.json").exists(), "no_failed_completed_run:" + prior.name)
            for source, digest in read(prior / "source_hashes.json").items():
                run.check(sha(prior / "source_snapshot" / source) == digest, "preserved_source_snapshot:" + prior.name + "/" + source)
            run.check(read(prior / "runtime.json")["new_environment_steps"] == 0, "zero_environment_cost:" + prior.name)
        for filename, prior in [("audit.py", audit), ("verify.py", verified), ("record.py", verified), ("amend_protocol.py", amended)]:
            run.check(sha(HERE / filename) == read(prior / "source_hashes.json")[filename], "ran_delivered_calculation:" + filename)
        run.input(ROOT / "README.md")
        run.input(ROOT / "AGENTS.md")
        run.input(HERE / "protocol.json", "438d2b23889c1242319f1592b86e0ff3ca2fa462992db6a3c9d41e669e8ffc7c")
        run.input(HERE / "inputs" / "frozen_reference_predictions.csv", cfg["prediction_sha256"])
        run.check(sha(ROOT / cfg["prepared_relative"] / "frozen_reference_predictions.csv") == cfg["prediction_sha256"], "57_prediction_preserved")
        run.check(sha(ROOT / cfg["previous_version"] / "protocol.json") == cfg["previous_protocol_sha256"], "57_protocol_preserved")
        for script in HERE.glob("*.py"):
            ast.parse(script.read_text(encoding="utf-8"), filename=str(script))
            run.check(True, "syntax:" + script.name)
        report = (HERE / "report_ko.md").read_text(encoding="utf-8")
        summary = read(audit / "summary.json")
        for field in ["overall_G_upper", "minimum_LOPO_G_upper"]:
            run.check(format(summary[field], ".9f") in report, "report_metric:" + field)
        for bound in rows(audit / "g_bounds.csv"):
            for field in ["G_lower", "G_upper"]:
                rendered = format(float(bound[field]), ".9f").replace("-", "−")
                run.check(rendered in report, "report_bound:" + bound["scope"] + "/" + field)
        for field in ["min_abs_delta_changed", "max_abs_delta_changed", "mean_abs_delta_changed_state_rows", "mean_abs_delta_all_state_rows", "rms_delta_all_state_rows", "parent_equal_mean_abs_delta_all"]:
            run.check(format(summary["correction"][field], ".9f") in report, "report_correction:" + field)
        run.check(format(100 * summary["overall_G_upper_share_parent41011"], ".4f") in report, "report_upper_bound_concentration")
        run.check(read(audit / "COMPLETE.json")["checks_passed"] == 20041 and read(verified / "COMPLETE.json")["checks_passed"] == 13591, "reported_check_counts")
        for document in HERE.glob("*.md"):
            contents = document.read_text(encoding="utf-8")
            run.check("\ufffd" not in contents, "valid_text:" + document.name)
            for match in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", contents):
                target = match.group(1)
                if target.startswith(("https://", "http://", "#")) or target == "review_bundle.zip":
                    continue
                path = (document.parent / target.split("#")[0]).resolve()
                run.check(path.exists(), "document_link:" + document.name + "/" + target)
        new_protocol = read(HERE / "protocol.json")
        run.check(new_protocol["proposed_investment_gate"]["separate_scientific_evidence_and_investment_status"], "positive_evidence_distinguished_from_investment")
        run.check(not new_protocol["execution_authorized"] and not new_protocol["scheduled"], "no_execution_or_schedule")
        package = HERE / "review_bundle.zip"
        manifest = HERE / "review_bundle_manifest.json"
        run.check(not package.exists() and not manifest.exists(), "new_package_only")
        payload = sorted([p for p in HERE.iterdir() if p.is_file() and p.suffix in {".py", ".md", ".json"}])
        payload += sorted(p for p in (HERE / "inputs").rglob("*") if p.is_file())
        for prior in [amended, audit, verified]:
            payload += sorted(p for p in prior.rglob("*") if p.is_file())
        entries = {p.relative_to(HERE).as_posix(): {"sha256": sha(p), "bytes": p.stat().st_size} for p in payload}
        dump(manifest, {"scope": "version58 self-contained current audit; earlier-version links require full repository", "new_environment_steps": 0, "files": entries})
        with zipfile.ZipFile(package, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in payload:
                archive.write(path, path.relative_to(HERE).as_posix())
            archive.write(manifest, manifest.name)
        with zipfile.ZipFile(package) as archive:
            run.check(archive.testzip() is None, "zip_crc")
            run.check(set(archive.namelist()) == set(entries) | {manifest.name}, "zip_exact_members")
            for name, evidence in entries.items():
                run.check(hashlib.sha256(archive.read(name)).hexdigest() == evidence["sha256"], "zip_content_hash:" + name)
            run.check(archive.read("inputs/frozen_reference_predictions.csv") == (HERE / "inputs" / "frozen_reference_predictions.csv").read_bytes(), "zip_locked_predictions_exact")
        run.input(manifest)
        return run.finish({"status": "final_documents_and_local_review_package_checked", "bundle": str(package), "bundle_bytes": package.stat().st_size, "bundle_sha256": sha(package), "files_in_bundle": len(entries) + 1, "markdown_check_scope": "source, equations, numeric tables and local links; no visual browser rendering claimed", "scientific_results": "F3/F4 not executed; only locked-prediction audit", "launch_or_queue_created": False})
    except BaseException as exc:
        return run.finish(exc=exc)


if __name__ == "__main__":
    raise SystemExit(main())
