"""Check report references, pivotal numeric claims, and plotted data bounds."""
import csv
import hashlib
import json
import re
import shutil
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ANALYSIS = HERE / "results/20261014T053612Z_df5ecad4"
FIGURES = HERE / "results/20261014T054319Z_figures_39560e10"
start = time.perf_counter()
out = HERE / "results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_delivery_") + uuid.uuid4().hex[:8])
out.mkdir(parents=True, exist_ok=False)
checks, inputs = [], {}


def check(name, condition):
    checks.append({"name": name, "passed": bool(condition)})


def capture(path):
    data = path.read_bytes()
    inputs[str(path)] = hashlib.sha256(data).hexdigest()
    return data


def rows(name):
    path = ANALYSIS / name
    capture(path)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


for path in [*HERE.glob("*.py"), *HERE.glob("*.md"), HERE / "protocol.json", HERE / "requirements.txt", HERE.parent / "README.md"]:
    capture(path)
    dest = out / "evidence_inputs" / path.relative_to(HERE.parent)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)
for path in [HERE / "report_ko.md", HERE / "README.md", HERE.parent / "README.md"]:
    body = path.read_text(encoding="utf-8-sig")
    for link in re.findall(r"\[[^\]]*\]\(([^\s)]+)\)", body):
        if not link.startswith(("http://", "https://", "#")):
            check("local reference: " + str(path.name) + " -> " + link, (path.parent / link.split("#")[0]).exists())
report = (HERE / "report_ko.md").read_text(encoding="utf-8")
summaries = rows("selection_summary.csv")


def metric(n, method, field, mode="cross_repeat_20_to_40"):
    return float(next(r for r in summaries if int(r["cases_per_task"]) == n and r["method"] == method and r["mode"] == mode)[field])


for n in [2, 5, 10, 20, 50]:
    for field in ["match_full_D_greedy_pct", "greedy_tie_pct"]:
        value = f'{metric(n, "Greedy", field):.2f}%'
        check("reported sampling metric " + str((n, field)), value in report)
for n in [2, 20]:
    for method in ["Development_fixed", "Greedy", "Gap2_Development_fixed", "Reliability_Development_fixed"]:
        for field in ["vs_uniform_pp", "vs_development_fixed_pp"]:
            value = metric(n, method, field)
            formatted = f"{value:+.2f}%p".replace("-", "−") if abs(value) > 1e-12 else "0.00%p"
            check("reported gate metric " + str((n, method, field)), formatted in report)
keep = 100 - metric(2, "Reliability_Development_fixed", "switch_from_fallback_pct")
check("reported fallback retention", f"{keep:.2f}%" in report)
for n in [2, 20]:
    cost = metric(n, "Greedy", "simulated_diagnostic_eval_steps_mean")
    check("reported simulated evaluation cost " + str(n), f"{cost:,.0f}" in report)
pair_rows = rows("horizon_pairs.csv")
check("all horizon points visible", all(abs(float(r[k])) < 25 for r in pair_rows for k in ["difference_20k_pp", "difference_40k_pp"]))
groups = rows("selection_by_group.csv")
check("all gate bars visible", all(abs(float(r["vs_development_fixed_pp"])) < 6 for r in groups
                                  if r["mode"] == "cross_repeat_20_to_40" and r["cases_per_task"] in ["2", "20"]
                                  and r["method"] in ["Greedy", "Gap2_Development_fixed", "Reliability_Development_fixed"]))
for stem in ["selection_transfer", "gate_by_group", "variation_sources", "horizon_reversals"]:
    for ext in ["png", "svg"]:
        path = FIGURES / (stem + "." + ext)
        check("nonempty export " + path.name, path.exists() and path.stat().st_size > 1000)
        capture(path)
manifest = json.loads(capture(FIGURES / "manifest.json"))
for path, expected in manifest["input_hashes"].items():
    check("plot input still matches " + path, hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected)
review = {
    "final_figure_directory": str(FIGURES),
    "manual_visual_review": "PNG marks, labels, legend, zero lines and footnotes inspected using view_image. Unchanged variation_sources reused the prior identical rendering review. SVG exports retained; no separate browser SVG rendering claimed.",
    "preserved_prior_attempts": [
        {"path": "results/20261014T054108Z_figures_bc718847", "issues": ["minus glyph missing in axis label", "gate legend overlaps bars", "numeric sample counts initially equally spaced"], "resolution": "new output run; no overwrite"},
        {"path": "results/20261014T054227Z_figures_56443aa1", "issues": ["clarified two-repeat versus one-repeat scoring target in legend and footnote"], "resolution": "new final output run"}
    ]
}
summary = {"status": "passed" if all(r["passed"] for r in checks) else "failed", "checks": len(checks),
           "failed": sum(not r["passed"] for r in checks), "wall_seconds": time.perf_counter() - start,
           "python": sys.version, "environment_steps": 0, "learner_updates": 0,
           "scope": "Final document links, key claims, plotted bounds and file provenance; scientific recalculation is in verify_analysis.py."}
for name, data in [("summary.json", summary), ("checks.json", checks), ("input_hashes.json", inputs), ("visual_review.json", review)]:
    with (out / name).open("x", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
print(json.dumps({"output": str(out), **summary}))
raise SystemExit(0 if summary["status"] == "passed" else 1)
