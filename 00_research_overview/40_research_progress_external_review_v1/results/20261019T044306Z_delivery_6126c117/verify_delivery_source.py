"""Bind final portable report to verified source, data and rendered bundle."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, re, shutil, sys, time, uuid

root = Path(__file__).resolve().parent
repo = root.parent
out = root / "results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_delivery_" + uuid.uuid4().hex[:8])
out.mkdir(parents=True, exist_ok=False)
shutil.copyfile(__file__, out / "verify_delivery_source.py")
t0=time.perf_counter()
checks=[]
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
    return json.loads(p.read_text(encoding="utf-8-sig"))
def check(name, passed, detail=None):
    checks.append({"name":name,"passed":bool(passed),"detail":detail})

assembly=root / "results/20261019T044214Z_assemble_3021ca9b"
browser=root / "results/20261019T044215Z_browser_997b92de/verification.json"
md=root / "research_progress_report_ko.md"
snapshot=read(root / "report_app/src/data.json")
build=read(root / "report_app/dist/data-app-build.json")
review=read(assembly / "summary.json")
check("final_assembly_passed", review["status"]=="passed" and review["report_sha256"]==sha(md))
check("final_browser_passed", read(browser)["status"]=="passed" and read(browser)["report_sha256"]==sha(md))
check("exact_build_verified",read(browser)["build"]==build)
check("app_title_and_sections_present",len(snapshot["report"]["sections"])==17 and snapshot["buildStatus"]=="complete")
for rel,record in read(assembly / "input_hashes.json").items():
    check("source_unchanged:"+rel,sha(repo / rel)==record["sha256"])
for field in ["html","snapshot"]:
    item=build[field]
    check("built_"+field,sha(root / "report_app/dist" / item["path"])==item["sha256"])
for page in [root / "README.md",md]:
    for link in re.findall(r"\]\(([^)]+)\)",page.read_text(encoding="utf-8")):
        if link.startswith(("http:","https:","#")):
            continue
        target=(page.parent / link.split('#')[0]).resolve()
        # Portable file is copied below after matching the verified split snapshot.
        if target==root / "research_progress_report_ko.html":
            continue
        check("local_link:"+link,target.exists())
offline=root / "report_app/.data-app-offline/exports/research_progress_report_ko_final.html"
html=offline.read_text(encoding="utf-8")
check("offline_identity",snapshot["id"] in html)
check("offline_final_content", "총 일곱 종류" in html and "93,236,809" in html and "실행·예약하지 않았고" in html)
check("offline_no_snapshot_fetch_reference",build["snapshot"]["path"] not in html)
check("root_index_links_report","40_research_progress_external_review_v1/README.md" in (repo / "README.md").read_text(encoding="utf-8"))
target=root / "research_progress_report_ko.html"
if all(c["passed"] for c in checks):
    if target.exists():
        check("existing_portable_identical",sha(target)==sha(offline))
    else:
        with target.open("xb") as f:
            f.write(offline.read_bytes())
    check("portable_exact_export",sha(target)==sha(offline))
manifest={p.name:{"sha256":sha(p),"bytes":p.stat().st_size} for p in [md,root / "README.md",target] if p.exists()}
status="passed" if all(c["passed"] for c in checks) else "failed"
result={"status":status,"checks":checks,"artifacts":manifest,"app_id":snapshot["id"],"snapshot_sha256":build["snapshot"]["sha256"],
        "wall_seconds":time.perf_counter()-t0,"python":sys.version,"source_sha256":sha(Path(__file__)),
        "environment_steps":0,"persistent_updates":0,"clone_updates":0,"scientific_rerun":False,
        "browser_preview_tool_available":False,"preview_url":"http://127.0.0.1:8740/"}
(out / "delivery.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps({"output":str(out),"status":status,"checks":len(checks),"failed":[c for c in checks if not c["passed"]],"artifacts":manifest},ensure_ascii=False))
if status!="passed":sys.exit(1)
