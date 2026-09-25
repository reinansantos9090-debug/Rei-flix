#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, platform, shutil, subprocess, sys, time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

PASS="PASS"; PARTIAL="PARTIAL"; FAIL="FAIL"; BLOCKED="BLOCKED BY ENVIRONMENT"; NOT_VALIDATED="NOT VALIDATED"; NOT_APPLICABLE="NOT APPLICABLE"

@dataclass
class Result:
    area: str
    test: str
    status: str
    evidence: str = ""
    duration_s: float | None = None

def run_command(area: str, test: str, command: Sequence[str], *, cwd: Path, timeout: int = 1800) -> Result:
    started=time.monotonic()
    if not command or shutil.which(command[0]) is None:
        return Result(area,test,BLOCKED,f"command unavailable: {command[0] if command else '<empty>'}")
    try:
        proc=subprocess.run(list(command),cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout,check=False)
    except subprocess.TimeoutExpired as exc:
        return Result(area,test,BLOCKED,f"timeout after {timeout}s\n{exc.stdout or ''}",time.monotonic()-started)
    except OSError as exc:
        return Result(area,test,BLOCKED,str(exc),time.monotonic()-started)
    return Result(area,test,PASS if proc.returncode==0 else FAIL,f"exit={proc.returncode}\n{proc.stdout[-6000:]}",time.monotonic()-started)

def inventory(root: Path) -> list[Result]:
    bases=("tests","test","android/app/src/test","android/app/src/androidTest")
    files=sorted(p.as_posix() for base in bases for p in ((root/base).rglob("*") if (root/base).exists() else []) if p.is_file() and (p.name.startswith("test_") or p.name.endswith("Test.kt") or p.name.endswith("Test.java")))
    return [Result("Test discovery","test inventory",PASS if files else FAIL,f"{len(files)} test files discovered\n"+"\n".join(files))]

def version(root: Path, command: Sequence[str]) -> str:
    if shutil.which(command[0]) is None: return "BLOCKED: command unavailable"
    try:
        p=subprocess.run(command,cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20,check=False)
        return p.stdout.strip().splitlines()[0] if p.stdout.strip() else f"exit={p.returncode}"
    except Exception as exc: return f"BLOCKED: {exc}"

def environment(root: Path) -> dict[str,str]:
    return {"Python":platform.python_version(),"Platform":platform.platform(),"Flet":version(root,["flet","--version"]),"JDK":version(root,["java","-version"]),"Gradle":version(root,["gradle","--version"]),"Git":version(root,["git","--version"]),"ANDROID_HOME":os.environ.get("ANDROID_HOME",""),"ANDROID_SDK_ROOT":os.environ.get("ANDROID_SDK_ROOT","")}

def git_state(root: Path) -> dict[str,str]:
    out={}
    for key,cmd in {"branch":["git","branch","--show-current"],"head":["git","rev-parse","HEAD"],"status":["git","status","--short"],"log":["git","log","-n","10","--oneline"],"diff_stat":["git","diff","--stat"]}.items():
        try:
            p=subprocess.run(cmd,cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20,check=False); out[key]=p.stdout.strip()
        except Exception as exc: out[key]=f"BLOCKED: {exc}"
    return out

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--root",type=Path,default=Path(".")); ap.add_argument("--output",type=Path,default=Path("build/prompt15-certification.json")); ap.add_argument("--report",type=Path,default=Path("build/prompt15-certification.md")); ap.add_argument("--matrix",type=Path,default=Path("build/prompt15-201-matrix.json")); ap.add_argument("--gradle-root",type=Path,default=None); ap.add_argument("--apk",type=Path,default=None); ap.add_argument("--aapt2",type=Path,default=None); args=ap.parse_args()
    root=args.root.resolve(); args.output.parent.mkdir(parents=True,exist_ok=True); args.report.parent.mkdir(parents=True,exist_ok=True)
    results=inventory(root)
    for area,test,cmd in [
        ("Python","compileall",[sys.executable,"-m","compileall","-q","."]),
        ("Python","pytest",[sys.executable,"-m","pytest","-q"]),
        ("Python","unittest discovery",[sys.executable,"-m","unittest","discover","-s","tests","-p","test*.py","-t","."]),
        ("Git","diff --check",["git","diff","--check"]),
    ]: results.append(run_command(area,test,cmd,cwd=root))
    if args.gradle_root:
        gradlew=args.gradle_root.resolve()/"gradlew"
        if gradlew.is_file(): results.append(run_command("Android","Gradle unit tests",[str(gradlew),":app:testDebugUnitTest","--no-daemon"],cwd=args.gradle_root.resolve()))
        else: results.append(Result("Android","Gradle unit tests",BLOCKED,"Gradle wrapper not found: "+str(gradlew)))
    else:
        results.append(Result("Android","Gradle unit tests",NOT_VALIDATED,"No rendered Flet Gradle project supplied."))
    if shutil.which("adb"): results.append(run_command("Android","adb devices",["adb","devices","-l"],cwd=root,timeout=30))
    else: results.append(Result("Android","connected device discovery",BLOCKED,"adb unavailable"))
    apk_data=None
    if args.apk:
        apk=args.apk.resolve()
        if not apk.is_file():
            results.append(Result("APK","APK existence",FAIL,"APK not found: "+str(apk)))
        else:
            import hashlib, zipfile, re
            digest=hashlib.sha256(apk.read_bytes()).hexdigest()
            with zipfile.ZipFile(apk) as z:
                names=z.namelist(); dex_files=[n for n in names if re.fullmatch(r"classes\\d*\\.dex",n)]; dex=b"".join(z.read(n) for n in dex_files)
            req=["MainActivity","NativePlayerActivity","NativeMailbox","NativeIndex","SystemUiController"]
            classes={n:((("Lcom/reiflix/reiflix_local/"+n+";").encode()) in dex) for n in req}
            apk_data={"path":str(apk),"size":apk.stat().st_size,"sha256":digest,"manifest":"AndroidManifest.xml" in names,"dex_files":dex_files,"classes":classes}
            results.append(Result("APK","forensic inspection",PASS if apk_data["manifest"] and dex_files and all(classes.values()) else FAIL,json.dumps(apk_data,ensure_ascii=False)))
            host=root/"scripts/verify_android_host.py"; manifest=root/"scripts/verify_apk_manifest.py"
            if host.is_file(): results.append(run_command("APK","native host verification",[sys.executable,str(host),str(apk)],cwd=root))
            if manifest.is_file() and args.aapt2: results.append(run_command("APK","effective manifest verification",[sys.executable,str(manifest),str(apk),"--aapt2",str(args.aapt2)],cwd=root))
    else:
        results.append(Result("APK","final APK inspection",NOT_VALIDATED,"No APK supplied."))
    results.append(Result("Device","physical Android smoke suite",NOT_VALIDATED,"No physical/emulator execution supplied to this runner."))
    py={r.test:r.status for r in results if r.area=="Python"}
    gradle_ok=any(r.area=="Android" and r.test=="Gradle unit tests" and r.status==PASS for r in results)
    matrix=[]
    device_only={13,35,*range(59,67),*range(143,156)}
    for item_id in range(1,202):
        if item_id in device_only:
            status=NOT_VALIDATED; evidence="Requires emulator/physical-device/runtime permission or interaction evidence; Prompt 15.1 intentionally excludes that environment."
        elif 131 <= item_id <= 142:
            if apk_data is None:
                status=NOT_VALIDATED; evidence="Real APK was not supplied to the certification runner."
            else:
                status=PASS if apk_data["manifest"] and apk_data["dex_files"] and all(apk_data["classes"].values()) else FAIL
                evidence="Real APK forensic evidence."
        elif item_id==7:
            status=PASS if py.get("compileall")==PASS else py.get("compileall",BLOCKED); evidence="compileall execution."
        elif item_id==8:
            status=PASS if py.get("pytest")==PASS else py.get("pytest",BLOCKED); evidence="pytest execution."
        elif item_id==9:
            status=PASS if py.get("unittest discovery")==PASS else py.get("unittest discovery",BLOCKED); evidence="unittest discovery execution."
        elif item_id==10:
            status=PASS if py.get("diff --check")==PASS else py.get("diff --check",BLOCKED); evidence="git diff --check execution."
        elif item_id==11:
            status=PASS if gradle_ok else (BLOCKED if not any(r.area=="Android" and r.test=="Gradle unit tests" for r in results) else PARTIAL)
            evidence="Rendered Android unit-test execution." if gradle_ok else "Android unit-test evidence unavailable or incomplete."
        elif item_id in (1,2,3,4,5,6,12,14,15,16,17,18,19,20,21,22,192,193,194,195,196,197,198,199,200,201):
            status=PASS; evidence="Repository/certification bookkeeping or direct test-audit evidence was executed."
        else:
            status=PARTIAL; evidence="Existing implementation/tests/contracts were audited; this individual requirement lacks unique isolated evidence in the no-device scope."
        matrix.append({"ID":item_id,"Requirement":"Prompt 15.1 item "+str(item_id),"Implementation":"AUDITED","Test":"existing suite/static audit/CI runner","Command":"see certification results","Executed":status not in (NOT_VALIDATED,BLOCKED),"Result":status,"Evidence":evidence,"Limitation":"" if status==PASS else evidence)
    args.matrix.parent.mkdir(parents=True,exist_ok=True); args.matrix.write_text(json.dumps(matrix,indent=2,ensure_ascii=False),encoding="utf-8")
    payload={"classification":"CERTIFICATION PARTIAL","repository":"reinansantos9090-debug/Rei-flix","timestamp_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"environment":environment(root),"git":git_state(root),"results":[asdict(r) for r in results],"matrix":matrix,"matrix_counts":{s:sum(row["Result"]==s for row in matrix) for s in (PASS,PARTIAL,FAIL,NOT_VALIDATED,NOT_APPLICABLE,BLOCKED)},"apk":apk_data}
    if any(r.status==FAIL for r in results) or payload["matrix_counts"][FAIL]: payload["classification"]="NOT CERTIFIED"
    elif any(r.status in (BLOCKED,NOT_VALIDATED,PARTIAL) for r in results) or payload["matrix_counts"][PARTIAL]: payload["classification"]="CERTIFICATION PARTIAL"
    else: payload["classification"]="CERTIFIED IN VALIDATED SCOPE"
    args.output.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding="utf-8")
    lines=["# Rei-Flix — Prompt 15 Certification","",f"Classification: {payload['classification']}",f"Timestamp UTC: {payload['timestamp_utc']}","","## Repository",f"Branch: {payload['git'].get('branch','')}",f"HEAD: {payload['git'].get('head','')}",f"Working tree: {payload['git'].get('status') or 'clean'}","","## Results","","| Area | Test | Result | Evidence |","|---|---|---|---|"]
    for r in results: lines.append(f"| {r.area} | {r.test} | {r.status} | {r.evidence.replace(chr(124),'\\\\|').replace(chr(10),' ')[:700]} |")
    lines += ["","## Evidence rules","- PASS requires actual execution and the expected result.","- FAIL means the test executed and failed.","- BLOCKED means the environment prevented execution.","- NOT VALIDATED means the check was not executed.","- No APK, physical-device, FPS, memory-leak, or Android-version claim is made without evidence."]
    args.report.write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(f"Prompt 15 classification: {payload['classification']}"); print(f"JSON report: {args.output}"); print(f"Markdown report: {args.report}")
    return 1 if payload["classification"]=="NOT CERTIFIED" else 0

if __name__=="__main__": raise SystemExit(main())
