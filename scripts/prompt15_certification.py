#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, platform, shutil, subprocess, sys, time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

PASS="PASS"; FAIL="FAIL"; BLOCKED="BLOCKED"; NOT_VALIDATED="NOT VALIDATED"; NOT_APPLICABLE="NOT APPLICABLE"

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
    ap=argparse.ArgumentParser(); ap.add_argument("--root",type=Path,default=Path(".")); ap.add_argument("--output",type=Path,default=Path("build/prompt15-certification.json")); ap.add_argument("--report",type=Path,default=Path("build/prompt15-certification.md")); args=ap.parse_args()
    root=args.root.resolve(); args.output.parent.mkdir(parents=True,exist_ok=True); args.report.parent.mkdir(parents=True,exist_ok=True)
    results=inventory(root)
    for area,test,cmd in [
        ("Python","compileall",[sys.executable,"-m","compileall","-q","."]),
        ("Python","pytest",[sys.executable,"-m","pytest","-q"]),
        ("Python","unittest discovery",[sys.executable,"-m","unittest","discover","-s","tests","-p","test*.py","-t","."]),
        ("Git","diff --check",["git","diff","--check"]),
    ]: results.append(run_command(area,test,cmd,cwd=root))
    gradlew=root/"android"/"gradlew"
    if gradlew.is_file(): results.append(run_command("Android","Gradle unit tests",[str(gradlew),"test","--no-daemon"],cwd=root))
    else: results.append(Result("Android","Gradle unit tests",BLOCKED,"android/gradlew is not present; rendered Flet host is required."))
    if shutil.which("adb"): results.append(run_command("Android","adb devices",["adb","devices","-l"],cwd=root,timeout=30))
    else: results.append(Result("Android","connected device discovery",BLOCKED,"adb unavailable"))
    results.append(Result("APK","final APK inspection",NOT_VALIDATED,"No APK supplied; run verify_android_host.py and verify_apk_manifest.py on the real APK."))
    results.append(Result("Device","physical Android smoke suite",NOT_VALIDATED,"No physical/emulator execution supplied to this runner."))
    payload={"classification":"CERTIFICATION PARTIAL","repository":"reinansantos9090-debug/Rei-flix","timestamp_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"environment":environment(root),"git":git_state(root),"results":[asdict(r) for r in results]}
    payload["counts"]={s:sum(r.status==s for r in results) for s in (PASS,FAIL,BLOCKED,NOT_VALIDATED,NOT_APPLICABLE)}
    if any(r.status==FAIL for r in results): payload["classification"]="NOT CERTIFIED"
    elif any(r.status in (BLOCKED,NOT_VALIDATED) for r in results): payload["classification"]="CERTIFICATION PARTIAL"
    else: payload["classification"]="CERTIFIED IN VALIDATED SCOPE"
    args.output.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding="utf-8")
    lines=["# Rei-Flix — Prompt 15 Certification","",f"Classification: {payload['classification']}",f"Timestamp UTC: {payload['timestamp_utc']}","","## Repository",f"Branch: {payload['git'].get('branch','')}",f"HEAD: {payload['git'].get('head','')}",f"Working tree: {payload['git'].get('status') or 'clean'}","","## Results","","| Area | Test | Result | Evidence |","|---|---|---|---|"]
    for r in results: lines.append(f"| {r.area} | {r.test} | {r.status} | {r.evidence.replace(chr(124),'\\\\|').replace(chr(10),' ')[:700]} |")
    lines += ["","## Evidence rules","- PASS requires actual execution and the expected result.","- FAIL means the test executed and failed.","- BLOCKED means the environment prevented execution.","- NOT VALIDATED means the check was not executed.","- No APK, physical-device, FPS, memory-leak, or Android-version claim is made without evidence."]
    args.report.write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(f"Prompt 15 classification: {payload['classification']}"); print(f"JSON report: {args.output}"); print(f"Markdown report: {args.report}")
    return 1 if payload["classification"]=="NOT CERTIFIED" else 0

if __name__=="__main__": raise SystemExit(main())
