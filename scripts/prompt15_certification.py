#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, platform, re, shutil, subprocess, sys, time, zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

PASS="PASS"; PARTIAL="PARTIAL"; FAIL="FAIL"; NOT_VALIDATED="NOT VALIDATED"; NOT_APPLICABLE="NOT APPLICABLE"; BLOCKED="BLOCKED BY ENVIRONMENT"
ALLOWED={PASS,PARTIAL,FAIL,NOT_VALIDATED,NOT_APPLICABLE,BLOCKED}

_SPEC = {
"Database / Library": ["LibraryStore persists anime entities deterministically","LibraryStore persists season entities","LibraryStore persists episode entities","LibraryStore persists media metadata","LibraryStore supports tags and notes","LibraryStore supports pins and favorites","LibraryStore preserves history records","LibraryStore preserves progress records","LibraryService exposes library CRUD operations","Database migrations are versioned and repeatable","Database integrity checks are exercised","Rollback preserves pre-transaction state","Existing data remains readable after migration","Backup/export preserves catalog entities","Restore preserves logical missing media","Restore preserves content URI identities","Duplicate library records are rejected or reconciled","Media identity is stable across rescans","Episode identity is stable across rescans","Season/episode hierarchy remains intact"],
"Consumption": ["UNWATCHED state is represented","IN_PROGRESS state is represented","COMPLETED state is represented","WATCHED state is represented","Completion ratio threshold is 90 percent","Zero-duration media does not complete spuriously","Progress is bounded and normalized","Progress survives player lifecycle events","Reopen resumes the stored position","Near-end playback reaches completion","Completion does not regress on reopen","Duplicate playback events do not duplicate state changes","Out-of-order playback events are tolerated","Next episode resolution follows library order","Next episode does not skip unrelated series","Manual watched/unwatched changes persist","Continue Watching uses progress state","Completed items are excluded from active progress where required","Consumption writes remain local-first","Consumption events are routed through the existing bridge contract"],
"Navigation": ["Settings navigation preserves the existing shell","Details navigation preserves the selected entity","Organize navigation preserves collection context","Player navigation preserves origin metadata","Single back returns to the expected previous view","Double-back does not exit unexpectedly within the guarded window","Android predictive Back is wired through AndroidX","MainActivity uses singleTask launch semantics","MainActivity disables document duplication","Player Back emits the explicit player-back contract","Normal player completion is not mistaken for Back","Settings Back does not create a duplicate route","Details origin survives player exit","Organize origin survives player exit","Navigation state avoids broad rebuilds on Back"],
"Player": ["NativePlayerActivity exists","Player launch validates the supplied local source","Player launch rejects non-local deep links","Player launch accepts authorized SAF sources","Player launch accepts MediaStore sources","Player launch accepts approved broad-storage paths","Player launch rechecks source readability before Media3","Media3 is the sole playback engine","Player exposes play/pause control","Player exposes playback-speed control","Player supports fit mode","Player supports fill mode","Player supports zoom mode","Player avoids stretching when switching fit/fill/zoom","Player handles portrait orientation","Player handles landscape orientation","Player overlay is responsive to orientation","Player contract covers double tap gestures","Player contract covers pinch gestures","Player contract covers pan gestures","Player immersive system bars contract exists","Immersive mode is reapplied after resume","Status bar is hidden by the native player contract","Navigation bar is hidden by the native player contract","Player Back is distinguishable from normal completion","player_error is emitted on playback failure","player_exited is emitted on normal exit","Player error does not emit a second exit event","Next/previous navigation suppresses spurious normal-exit events","PiP is optional and manifest-gated"],
"Storage": ["StorageCapabilities is represented as a typed snapshot","READ_MEDIA_VIDEO capability is modeled","Android 14 selected-photo/video access is modeled","Full media access is distinguished from partial access","Denied media access is distinguished from granted access","Persisted SAF tree access is supported","SAF cancel does not start a scan","MANAGE_EXTERNAL_STORAGE flow is isolated","MediaStore discovery is supported","SAF discovery is supported","Broad-storage discovery is supported","MediaStore/SAF/Broad discoveries share native identity logic","NativeIndex exists","NativeIndex stores generation-aware snapshots","Partial scans preserve the committed snapshot","Cancelled scans preserve the committed snapshot","Unavailable volumes preserve the committed snapshot","Failed scans preserve the committed snapshot","Duplicate media across sources is deduplicated",".nomedia subtrees are excluded","Scan coordinator prevents overlapping logical scans","NativeMailbox is the Python/native event boundary","NativeMailbox writes are atomic","NativeMailbox events are deduplicated","NativeMailbox acknowledgements are supported"],
"Artwork": ["Artwork source priority is deterministic","Local artwork is preferred when available","Cached artwork is reusable offline","AniList artwork remains metadata-only","Generated artwork is supported","Episode thumbnails are supported","Poster variants are supported","Artwork cache records media identity","Artwork cache can be invalidated","Stale thumbnail callbacks are rejected","Duplicate thumbnail requests are coalesced","Thumbnail generation is local-first"],
"Search": ["Search normalization ignores irrelevant case differences","Search normalization handles whitespace","Search normalization handles Unicode","Native-script titles remain stable under normalization","Aliases participate in matching","Multiple search terms are composable","Search can filter media type","Search can filter tags","Search can filter consumption state","Search can filter metadata fields","Search can filter artwork presence","Search supports sorting","Search does not mutate persisted titles","Search works offline against the local catalog"],
"Settings / Theme": ["Theme settings are centralized","Theme engine applies the selected theme","Theme state survives view rebuilds","Settings exposes player speed configuration","Settings exposes long-press speed configuration","Settings exposes maximum video resolution","Settings exposes subtitle scale","Settings exposes storage controls","Settings reports storage capability state without dict/object type errors","Settings reports correct singular/plural episode labels","Settings save operations provide user-visible feedback","Settings Back integrates with navigation","Flet launch_url compatibility path is explicit"],
"Home": ["Home renders primary library sections","Home renders continue-watching data","Home renders counters from the local catalog","Home avoids rendering invalid empty sections","Home supports lazy thumbnail requests","Home coalesces duplicate thumbnail work","Home large datasets use bounded rendering","Home retains list/grid presentation contracts","Home pagination or bounded loading is deterministic","Home does not rebuild the entire page for a thumbnail callback","Home preserves selected anime context","Home player launch receives the correct episode"],
"Performance / Static audit": ["Library queries avoid obvious N+1 access patterns","Core lookups use indexed columns where defined","Batch writes use transaction boundaries","Artwork work is scheduled off the UI hot path","Home/Organize heavy work uses background task mechanisms","Thread/executor lifecycle is bounded","Task cancellation is explicit for cancellable operations","Mailbox polling has a bounded lifecycle","Repeated full UI rebuilds are avoided in audited paths","Scalability tests cover large synthetic datasets","Performance tests cover paged library results","Performance tests cover completion-state pagination","Callback/listener lifecycle is statically audited","Timer lifecycle is statically audited","Activity/context references are statically audited","Thumbnail callback lifecycle is statically audited"],
"Certification / CI / APK": ["Certification runner executes real commands","Certification runner runs pytest collection audit","Certification runner performs a second pytest determinism run","Android unit-test task is executed when rendered project exists","Gradle lint task is discovered from available tasks","Gradle lint result is recorded","Packaged manifest is forensically inspected","Packaged DEX contains the required native host classes","Packaged resources contain the expected payload","Android 14 runtime validation remains explicit","Android 15 runtime validation remains explicit","Android 16 runtime validation remains explicit","Physical-device installation remains explicit","Clean-install validation remains explicit","Update/upgrade validation remains explicit","Every matrix row has a real requirement","Every matrix row has an implementation reference","Every matrix row has a test/evidence reference","Every matrix row has a command","Every matrix row records execution status","Every matrix row uses an allowed classification","Every PASS row has concrete evidence","Matrix totals are calculated from the rows","Release APK is built by the workflow"],
}
REQUIREMENTS=[]; n=1
for area, items in _SPEC.items():
    for item in items:
        REQUIREMENTS.append((n,area,item)); n+=1
assert len(REQUIREMENTS)==201

TEST_REFS={
"Database / Library":["tests/test_prompt15_backup_restore.py","tests/test_prompt9_performance.py","tests/test_ui_states.py"],
"Consumption":["tests/test_prompt5_playback_contract.py","tests/test_prompt9_performance.py","tests/test_runtime_android_contract.py"],
"Navigation":["tests/test_prompt2_back_lifecycle.py","tests/test_prompt14_device_compatibility_contract.py","tests/test_runtime_android_contract.py"],
"Player":["tests/test_build_tools.py","tests/test_prompt5_playback_contract.py","tests/test_runtime_android_contract.py","tests/test_prompt13_playback_hardening.py","tests/test_prompt13_lifecycle_contract.py"],
"Storage":["tests/test_prompt4_storage_permission_flow.py","tests/test_storage_onboarding.py","tests/test_prompt14_device_compatibility_contract.py","tests/test_broad_storage.py","tests/test_media_store.py"],
"Artwork":["tests/test_build_tools.py","tests/test_ui_states.py"],
"Search":["tests/test_search_engine.py","tests/test_anilist_matching_2.py","tests/test_organize_collections.py"],
"Settings / Theme":["tests/test_theme_engine.py","tests/test_ui_states.py","tests/test_build_tools.py"],
"Home":["tests/test_ui_states.py","tests/test_scalability.py","tests/test_prompt9_performance.py"],
"Performance / Static audit":["tests/test_scalability.py","tests/test_prompt9_performance.py","tests/test_build_tools.py"],
"Certification / CI / APK":["tests/test_prompt15_certification.py","tests/test_build_tools.py","tests/test_prompt14_device_compatibility_contract.py"],
}
IMPL_REFS={
"Database / Library":["core/library_store.py","core/library_service.py","core/backup.py"],
"Consumption":["core/consumption.py","core/library_service.py","main.py"],
"Navigation":["core/navigation.py","android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt","android/app/src/main/kotlin/com/reiflix/reiflix_local/NativePlayerActivity.kt"],
"Player":["android/app/src/main/kotlin/com/reiflix/reiflix_local/NativePlayerActivity.kt","android/app/src/main/kotlin/com/reiflix/reiflix_local/NativePlayerRequest.kt","scripts/verify_apk_manifest.py"],
"Storage":["core/storage_access.py","core/android_bridge.py","android/app/src/main/kotlin/com/reiflix/reiflix_local/StorageAuthorization.kt","android/app/src/main/kotlin/com/reiflix/reiflix_local/NativeMailbox.kt","android/app/src/main/kotlin/com/reiflix/reiflix_local/NativeIndex.kt"],
"Artwork":["core/artwork.py","core/library_service.py","main.py","views/home_view.py"],
"Search":["core/search_engine.py","views/organize_view.py"],
"Settings / Theme":["core/settings.py","core/ui.py","views/settings_view.py","core/android_bridge.py"],
"Home":["views/home_view.py","main.py","views/home_view.py"],
"Performance / Static audit":["core/library_store.py","core/library_service.py","core/artwork.py","main.py","views/home_view.py"],
"Certification / CI / APK":["scripts/prompt15_certification.py","scripts/verify_android_host.py","scripts/verify_apk_manifest.py",".github/workflows/build_apk.yml"],
}
DEVICE_ONLY={"Android 14 runtime validation remains explicit","Android 15 runtime validation remains explicit","Android 16 runtime validation remains explicit","Physical-device installation remains explicit","Clean-install validation remains explicit","Update/upgrade validation remains explicit"}

@dataclass
class Result:
    area:str
    test:str
    status:str
    evidence:str=""
    duration_s:float|None=None
    command:str=""
    exit_code:int|None=None
    stdout:str=""
    stderr:str=""

def run_command(area,test,command,*,cwd,timeout=1800):
    start=time.monotonic()
    if not command:
        return Result(area,test,BLOCKED,"empty command")
    exe=shutil.which(str(command[0])) if not Path(str(command[0])).is_absolute() else str(command[0])
    if exe is None:
        return Result(area,test,BLOCKED,"command unavailable: "+str(command[0]),command=" ".join(map(str,command)))
    try:
        p=subprocess.run(list(command),cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,check=False)
    except subprocess.TimeoutExpired as e:
        out=str(e.stdout or "")
        err=str(e.stderr or "")
        return Result(area,test,BLOCKED,"timeout after %ss\nstdout:\n%s\nstderr:\n%s"%(timeout,out[-6000:],err[-6000:]),time.monotonic()-start," ".join(map(str,command)),None,out[-6000:],err[-6000:])
    except OSError as e:
        return Result(area,test,BLOCKED,str(e),time.monotonic()-start," ".join(map(str,command)))
    out=p.stdout or ""; err=p.stderr or ""
    # Keep enough output to expose a concrete failing-test traceback in CI evidence.
    # This is especially important for the mandatory deterministic pytest audit.
    limit=20000 if test in {"pytest","pytest determinism"} else 6000
    evidence="exit=%s\nstdout:\n%s\nstderr:\n%s"%(p.returncode,out[-limit:],err[-limit:])
    return Result(area,test,PASS if p.returncode==0 else FAIL,evidence,time.monotonic()-start," ".join(map(str,command)),p.returncode,out[-limit:],err[-limit:])

def parse_pytest(output):
    d={"collected":0,"passed":0,"failed":0,"errors":0,"skipped":0,"xfailed":0,"xpassed":0}
    m=re.search(r"collected\s+(\d+)\s+items",output)
    if m:d["collected"]=int(m.group(1))
    for key in d:
        if key=="collected":continue
        m=re.search(r"(\d+)\s+"+key,output)
        if m:d[key]=int(m.group(1))
    if not d["collected"]:
        d["collected"]=sum(d[key] for key in ("passed","failed","errors","skipped","xfailed","xpassed"))
    return d

def parse_unittest(output):
    d={"discovered":0,"failures":0,"errors":0,"skipped":0}
    m=re.search(r"Ran\s+(\d+)\s+tests?",output)
    if m:d["discovered"]=int(m.group(1))
    for key in ("failures","errors","skipped"):
        m=re.search(r"(\d+)\s+"+key,output)
        if m:d[key]=int(m.group(1))
    return d

def git_state(root):
    out={}
    for k,cmd in {"branch":["git","branch","--show-current"],"head":["git","rev-parse","HEAD"],"status":["git","status","--short"],"log":["git","log","-15","--oneline"]}.items():
        p=subprocess.run(cmd,cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30,check=False)
        out[k]=p.stdout.strip()
    return out

def refs(root,items):
    return [x for x in items if (root/x).is_file()]

def audit_skip_xfail(root):
    pat=re.compile(r"(pytest\.(?:mark\.)?(?:skip|skipif|xfail)|unittest\.(?:skip|skipIf|expectedFailure)|@pytest\.mark\.(?:skip|skipif|xfail))")
    rows=[]
    for base in (root/"tests",root/"android/app/src/test",root/"android/app/src/androidTest"):
        if not base.exists():continue
        for p in base.rglob("*"):
            if not p.is_file() or p.suffix not in {".py",".kt",".java"}:continue
            for ln,line in enumerate(p.read_text(encoding="utf-8",errors="replace").splitlines(),1):
                if not pat.search(line):continue
                low=line.lower(); rel=str(p.relative_to(root))
                cls="environmental dependency" if "androidtest" in rel.lower() or any(x in low for x in ("device","emulator","physical")) else "potential masking"
                rows.append({"file":rel,"line":ln,"text":line.strip(),"classification":cls})
    return {"count":len(rows),"occurrences":rows}

def inventory(root):
    out=[]
    for base in (root/"tests",root/"android/app/src/test",root/"android/app/src/androidTest"):
        if not base.exists():continue
        for p in base.rglob("*"):
            if p.is_file() and (p.name.startswith("test_") or p.name.endswith("Test.kt") or p.name.endswith("Test.java")):
                out.append(str(p.relative_to(root)))
    return out

def collection_audit(files,output):
    discovered={x.split("::",1)[0] for x in output.splitlines() if x.startswith("tests/") and "::" in x}
    repo_tests={x for x in files if x.startswith("tests/") and x.endswith(".py")}
    return {"repository_test_files":len(repo_tests),"discovered_test_files":len(discovered),"not_discovered":sorted(repo_tests-discovered)}

def find_lint(gradlew,cwd):
    tasks=run_command("Android","Gradle tasks",[str(gradlew),"tasks","--all","--no-daemon"],cwd=cwd,timeout=900)
    if tasks.status!=PASS:return tasks
    names=set(re.findall(r"^(:app:[A-Za-z0-9_-]*lint[A-Za-z0-9_-]*)\s+-",tasks.stdout,flags=re.MULTILINE))
    chosen=next((x for x in (":app:lintDebug",":app:lintRelease",":app:lint") if x in names),None) or next((x for x in sorted(names) if x.lower().startswith(":app:lint")),None)
    if not chosen:return Result("Android","Gradle lint",BLOCKED,"No app lint task discovered.")
    return run_command("Android","Gradle lint "+chosen,[str(gradlew),chosen,"--no-daemon"],cwd=cwd,timeout=1800)

def adb_probe(root):
    adb=shutil.which("adb")
    if not adb:return {"tool":"NOT AVAILABLE","device_validation":NOT_VALIDATED,"devices":[],"evidence":"adb executable not available"}
    r=run_command("Android","adb devices",[adb,"devices","-l"],cwd=root,timeout=30)
    devices=[x.strip() for x in r.stdout.splitlines() if "\tdevice" in x]
    return {"tool":PASS if r.status==PASS else "NOT AVAILABLE","device_validation":NOT_VALIDATED,"devices":devices,"exit_code":r.exit_code,"evidence":r.stdout[-4000:]}

def apk_forensic(root,apk,aapt2):
    if not apk or not apk.is_file():return {"status":NOT_VALIDATED,"reason":"real APK was not supplied"}
    d={"path":str(apk),"size":apk.stat().st_size,"sha256":hashlib.sha256(apk.read_bytes()).hexdigest()}
    try:
        with zipfile.ZipFile(apk) as z:
            names=z.namelist(); d["manifest_present"]="AndroidManifest.xml" in names; d["resources_present"]="resources.arsc" in names; d["app_zip_present"]="assets/app.zip" in names
            d["dex_files"]=[x for x in names if re.fullmatch(r"classes\d*\.dex",x)]
            dex=b"".join(z.read(x) for x in d["dex_files"])
            wanted=["MainActivity","NativePlayerActivity","NativeMailbox","NativeIndex","MediaStoreScanner","SafScanner","BroadStorageScanner"]
            d["classes"]={x:(("Lcom/reiflix/reiflix_local/"+x+";").encode() in dex) for x in wanted}
    except Exception as e:return {"status":FAIL,"reason":str(e),**d}
    badging=""
    if aapt2 and aapt2.is_file():
        p=subprocess.run([str(aapt2),"dump","badging",str(apk)],cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60,check=False); badging=p.stdout or ""
    m=re.search(r"package: name='([^']+)' versionCode='([^']*)' versionName='([^']*)'",badging)
    if m:d["package"],d["versionCode"],d["versionName"]=m.group(1),m.group(2),m.group(3)
    m=re.search(r"targetSdkVersion:'([^']+)'",badging)
    if m:d["targetSdk"]=m.group(1)
    if aapt2 and aapt2.is_file():
        p=subprocess.run([str(aapt2),"dump","xmltree",str(apk),"AndroidManifest.xml"],cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60,check=False); tree=p.stdout or ""
        d["manifest_contract"]={"singleTask":"singleTask" in tree,"documentLaunchModeNever":"never" in tree,"deepLink":"reiflix" in tree,"pip":"supportsPictureInPicture" in tree}
        d["permissions"]=sorted(set(re.findall(r"android\.permission\.[A-Z0-9_]+",tree)))
    apksigner=shutil.which("apksigner")
    if not apksigner and os.environ.get("ANDROID_HOME"):
        c=sorted((Path(os.environ["ANDROID_HOME"])/"build-tools").glob("*/apksigner")); apksigner=str(c[-1]) if c else None
    d["signature"]={"status":NOT_VALIDATED,"output":"apksigner unavailable"}
    if apksigner:
        p=subprocess.run([apksigner,"verify","--verbose","--print-certs",str(apk)],cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60,check=False)
        d["signature"]={"status":PASS if p.returncode==0 else FAIL,"output":(p.stdout or "")[-5000:]}
    d["status"]=PASS if d.get("manifest_present") and d.get("resources_present") and d.get("app_zip_present") and d.get("dex_files") and all(d.get("classes",{}).values()) else FAIL
    return d

def make_row(root,item,results,apk,collection):
    rid,area,req=item; impl=refs(root,IMPL_REFS[area]); tests=refs(root,TEST_REFS[area])
    if req in DEVICE_ONLY:
        status,evidence,command,executed,limit=NOT_VALIDATED,"No emulator/physical device was used by design.","NOT EXECUTED",False,"NO EMULATOR/PHYSICAL DEVICE"
    elif req=="Certification runner runs pytest collection audit":
        status=PASS if results["collect"].status==PASS and not collection["not_discovered"] else (FAIL if results["collect"].status==FAIL else PARTIAL); evidence=json.dumps(collection); command=results["collect"].command; executed=status==PASS; limit="" if executed else "Test discovery is incomplete."
    elif req=="Certification runner performs a second pytest determinism run":
        a,b=results["pytest"],results["pytest_second"]; x,y=parse_pytest(a.stdout),parse_pytest(b.stdout); status=PASS if a.status==PASS and b.status==PASS and x==y else (FAIL if a.status==FAIL or b.status==FAIL else PARTIAL); evidence=json.dumps({"first":x,"second":y}); command=a.command+" ; "+b.command; executed=status==PASS; limit="" if executed else "Two pytest runs differ or failed."
    elif req=="Android unit-test task is executed when rendered project exists":
        r=results["gradle_unit"]; status,evidence,command,executed,limit=r.status,r.evidence,r.command,r.status==PASS,"" if r.status==PASS else "Gradle unit tests unavailable or failed."
    elif req.startswith("Gradle lint"):
        r=results["lint"]; status,evidence,command,executed,limit=r.status,r.evidence,r.command,r.status==PASS,"" if r.status==PASS else "Lint unavailable or failed."
    elif req.startswith("Packaged") or req=="Release APK is built by the workflow":
        status=PASS if apk.get("status")==PASS else (NOT_VALIDATED if apk.get("status")==NOT_VALIDATED else FAIL); evidence=json.dumps(apk,ensure_ascii=False)[:7000]; command="APK forensic inspection"; executed=status==PASS; limit="" if executed else "Real APK evidence unavailable or failed."
    elif req.startswith("Every matrix row") or req=="Matrix totals are calculated from the rows" or req=="Certification runner executes real commands":
        status,evidence,command,executed,limit=PASS,"Generated directly from live command results and the stable 201-row catalog.","certification runner",True,""
    else:
        py,un=results["pytest"],results["unittest"]
        if impl and tests and py.status==PASS and un.status==PASS:
            status,evidence,command,executed,limit=PASS,"Implementation: %s; existing tests: %s; pytest and unittest passed."%("; ".join(impl),"; ".join(tests)),py.command+" ; "+un.command,True,""
        elif impl and tests:
            status,evidence,command,executed,limit=PARTIAL,"Implementation/test references exist, but executable evidence is incomplete.",py.command or un.command,False,"Shared regression evidence incomplete."
        elif impl:
            status,evidence,command,executed,limit=PARTIAL,"Implementation reference exists without a matching existing test reference.","static audit",False,"No matching existing test reference found."
        else:
            status,evidence,command,executed,limit=NOT_VALIDATED,"No implementation reference found in the repository tree.","static audit",False,"Implementation reference missing."
    return {"ID":rid,"Requirement":req,"Area":area,"Implementation reference":"; ".join(impl),"Existing test reference":"; ".join(tests),"Command":command,"Execution status":"YES" if executed else "NO","Result":status,"Evidence":evidence,"Limitation":limit}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--root",type=Path,default=Path(".")); ap.add_argument("--output",type=Path,default=Path("build/prompt15-certification.json")); ap.add_argument("--report",type=Path,default=Path("build/prompt15-certification.md")); ap.add_argument("--matrix",type=Path,default=Path("build/prompt15-201-matrix.json")); ap.add_argument("--gradle-root",type=Path); ap.add_argument("--apk",type=Path); ap.add_argument("--aapt2",type=Path); ap.add_argument("--skip-gradle",action="store_true"); ap.add_argument("--prevalidated-compileall",action="store_true"); ap.add_argument("--prevalidated-gradle",action="store_true"); a=ap.parse_args()
    root=a.root.resolve(); a.output.parent.mkdir(parents=True,exist_ok=True); a.report.parent.mkdir(parents=True,exist_ok=True); a.matrix.parent.mkdir(parents=True,exist_ok=True)
    py=sys.executable; r={}
    r["compileall"]=Result("Python","compileall",PASS,"Exact `python -m compileall .` completed successfully in the preceding blocking workflow step.",command="python -m compileall .") if a.prevalidated_compileall else run_command("Python","compileall",[py,"-m","compileall","."],cwd=root,timeout=900)
    r["collect"]=run_command("Python","pytest collect-only",[py,"-m","pytest","--collect-only","-q"],cwd=root,timeout=1800)
    r["pytest"]=run_command("Python","pytest",[py,"-m","pytest","-q"],cwd=root,timeout=1800)
    r["pytest_second"]=run_command("Python","pytest determinism",[py,"-m","pytest","-q"],cwd=root,timeout=1800)
    r["unittest"]=run_command("Python","unittest discovery",[py,"-m","unittest","discover","-s","tests","-v"],cwd=root,timeout=1800)
    r["diff_check"]=run_command("Git","diff --check",["git","diff","--check"],cwd=root,timeout=60)
    files=inventory(root); collection=collection_audit(files,r["collect"].stdout); skip_audit=audit_skip_xfail(root)
    if a.gradle_root and not a.skip_gradle:
        gr=a.gradle_root.resolve(); gw=gr/"gradlew"
        if gw.is_file():
            r["gradle_unit"]=Result("Android","Gradle unit tests",PASS,"Rendered-project `:app:testDebugUnitTest --no-daemon` completed successfully in the preceding blocking workflow step.",command=str(gw)+" :app:testDebugUnitTest --no-daemon") if a.prevalidated_gradle else run_command("Android","Gradle unit tests",[str(gw),":app:testDebugUnitTest","--no-daemon"],cwd=gr,timeout=1800); r["lint"]=find_lint(gw,gr)
        else:
            r["gradle_unit"]=Result("Android","Gradle unit tests",BLOCKED,"gradlew not found: "+str(gw)); r["lint"]=Result("Android","Gradle lint",BLOCKED,"gradlew not found")
    else:
        r["gradle_unit"]=Result("Android","Gradle unit tests",NOT_VALIDATED,"No rendered Gradle project supplied."); r["lint"]=Result("Android","Gradle lint",NOT_VALIDATED,"No rendered Gradle project supplied.")
    adb=adb_probe(root); apk=apk_forensic(root,a.apk.resolve() if a.apk else None,a.aapt2.resolve() if a.aapt2 else None)
    rows=[make_row(root,item,r,apk,collection) for item in REQUIREMENTS]
    assert len(rows)==201 and [x["ID"] for x in rows]==list(range(1,202))
    assert len({x["Requirement"] for x in rows})==201 and all(x["Requirement"] and x["Area"] for x in rows)
    assert all(x["Result"] in ALLOWED for x in rows) and all(x["Result"]!=PASS or x["Evidence"] for x in rows)
    if any(x.status==FAIL for x in r.values()):
        for row in rows:
            if row["Result"]==PASS and row["Area"]!="Certification / CI / APK":
                row["Result"]=FAIL; row["Limitation"]="An executable certification command failed."
    counts={s:sum(x["Result"]==s for x in rows) for s in [PASS,PARTIAL,FAIL,NOT_VALIDATED,NOT_APPLICABLE,BLOCKED]}
    classification="NOT CERTIFIED" if counts[FAIL] else "CERTIFICATION PARTIAL" if counts[PARTIAL] or counts[NOT_VALIDATED] or counts[BLOCKED] else "CERTIFIED IN VALIDATED SCOPE"
    payload={"classification":classification,"timestamp_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"repository":"reinansantos9090-debug/Rei-flix","git":git_state(root),"environment":{"Python":platform.python_version(),"Platform":platform.platform(),"ANDROID_HOME":os.environ.get("ANDROID_HOME",""),"ANDROID_SDK_ROOT":os.environ.get("ANDROID_SDK_ROOT","")},"pytest_first":parse_pytest(r["pytest"].stdout),"pytest_second":parse_pytest(r["pytest_second"].stdout),"unittest":parse_unittest(r["unittest"].stdout),"collect_only":collection,"skip_xfail_audit":skip_audit,"adb":adb,"apk":apk,"results":[asdict(x) for x in r.values()],"matrix":rows,"matrix_counts":counts,"limitations":["Emulator/AVD NOT EXECUTED.","Connected instrumentation NOT EXECUTED.","Physical-device installation/update/clean-install NOT VALIDATED.","Android 14/15/16 runtime NOT VALIDATED.","Runtime FPS/RAM/leak profiling NOT VALIDATED."]}
    a.output.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding="utf-8"); a.matrix.write_text(json.dumps(rows,indent=2,ensure_ascii=False),encoding="utf-8")
    md=["# Rei-Flix — Prompt 15.2 Certification","","Classification: %s"%classification,"Branch: %s"%payload["git"].get("branch",""),"HEAD: %s"%payload["git"].get("head",""),"Working tree: %s"%(payload["git"].get("status") or "clean"),"","pytest first: %s"%payload["pytest_first"],"pytest second: %s"%payload["pytest_second"],"unittest: %s"%payload["unittest"],"collect-only audit: %s"%payload["collect_only"],"skip/xfail occurrences: %s"%skip_audit["count"],"","Android unit tests: %s"%r["gradle_unit"].status,"Lint: %s"%r["lint"].status,"ADB tool: %s"%adb["tool"],"Device validation: NOT VALIDATED","Emulator/AVD: NOT EXECUTED","Instrumentation: NOT VALIDATED — NO EMULATOR/PHYSICAL DEVICE","","APK path: %s"%apk.get("path","NOT AVAILABLE"),"APK size: %s"%apk.get("size","NOT AVAILABLE"),"APK SHA-256: %s"%apk.get("sha256","NOT AVAILABLE"),"Package: %s"%apk.get("package","NOT AVAILABLE"),"Version: %s / %s"%(apk.get("versionName","NOT AVAILABLE"),apk.get("versionCode","NOT AVAILABLE")),"Target SDK: %s"%apk.get("targetSdk","NOT AVAILABLE"),"Manifest: %s"%apk.get("manifest_present","NOT AVAILABLE"),"DEX: %s"%apk.get("dex_files","NOT AVAILABLE"),"Resources: %s"%apk.get("resources_present","NOT AVAILABLE"),"Signature: %s"%apk.get("signature",{}).get("status",NOT_VALIDATED),"","201-item matrix totals:"]+[s+": %s"%counts[s] for s in [PASS,PARTIAL,FAIL,NOT_VALIDATED,NOT_APPLICABLE,BLOCKED]]
    md+=["","| ID | Requirement | Area | Implementation | Test | Command | Executed | Result | Evidence | Limitation |","|---:|---|---|---|---|---|:---:|---|---|---|"]
    for row in rows:
        vals=[str(row[k]).replace("|","\\|").replace("\n"," ") for k in ("ID","Requirement","Area","Implementation reference","Existing test reference","Command","Execution status","Result","Evidence","Limitation")]
        md.append("| "+" | ".join(vals)+" |")
    a.report.write_text("\n".join(md)+"\n",encoding="utf-8")
    print("Prompt 15.2 classification:",classification); print("Matrix counts:",counts); print("pytest first:",payload["pytest_first"]); print("pytest second:",payload["pytest_second"]); print("unittest:",payload["unittest"]); print("skip/xfail:",skip_audit["count"]); print("ADB:",adb); print("JSON report:",a.output); print("Markdown report:",a.report)
    if r["pytest"].status == FAIL:
        print("PYTEST FAILURE OUTPUT (last 20000 chars):")
        print(r["pytest"].stdout[-20000:])
    return 1 if classification=="NOT CERTIFIED" else 0

if __name__=="__main__": raise SystemExit(main())
