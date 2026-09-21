#!/usr/bin/env python3
"""Static release audit for the source and CI contract."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

FORBIDDEN_WORKFLOW = ("|| true",)
REQUIRED_CLASSES = (
    "MainActivity",
    "NativeMailbox",
    "NativeRequestState",
    "SafScanner",
    "MediaStoreScanner",
    "BroadStorageScanner",
    "NativeIndex",
    "NativeScanController",
    "NativePlayerActivity",
    "GoogleIdentity",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    root = args.root.resolve()
    failures: list[str] = []

    workflow = (root / ".github/workflows/build_apk.yml").read_text(encoding="utf-8")
    for token in FORBIDDEN_WORKFLOW:
        if token in workflow:
            failures.append(f"workflow contains failure suppression: {token}")

    source_files = list((root / "core").glob("*.py")) + list((root / "views").glob("*.py")) + [root / "main.py"]
    silent_pass = re.compile(r"except\s+Exception\s*:\s*\n\s*pass")
    for path in source_files:
        text = path.read_text(encoding="utf-8")
        if silent_pass.search(text):
            failures.append(f"silent Exception/pass remains in {path.relative_to(root)}")

    build_gradle = (root / "android/app/build.gradle.kts").read_text(encoding="utf-8")
    manifest = (root / "android/app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
    if 'applicationId = "com.reiflix.reiflix_local"' not in build_gradle:
        failures.append("unexpected applicationId")
    if "targetSdk = 36" not in build_gradle:
        failures.append("targetSdk is not 36")
    version_code = re.search(r"versionCode\s*=\s*(\d+)", build_gradle)
    version_name = re.search(r'versionName\s*=\s*"([^"]+)"', build_gradle)
    if not version_code or not version_name:
        failures.append("version contract is incomplete")
    else:
        if int(version_code.group(1)) < 2:
            failures.append("versionCode must be >= 2 for installable updates")
        if version_name.group(1) != "0.2.1":
            failures.append("versionName must be 0.2.1")
    if 'android:name=".MainActivity" android:exported="true"' not in manifest:
        failures.append("MainActivity exported contract missing")
    if 'android:launchMode="singleTask"' not in manifest:
        failures.append("MainActivity launchMode contract missing")
    if 'android:documentLaunchMode="never"' not in manifest:
        failures.append("MainActivity documentLaunchMode contract missing")

    host = (root / "scripts/verify_android_host.py").read_text(encoding="utf-8")
    for class_name in REQUIRED_CLASSES:
        if class_name not in host:
            failures.append(f"APK host gate missing {class_name}")

    if failures:
        for failure in failures:
            print("RELEASE_AUDIT_FAIL:", failure, file=sys.stderr)
        return 1

    print("RELEASE_AUDIT_OK")
    print(f"applicationId=com.reiflix.reiflix_local versionCode={version_code.group(1)} versionName={version_name.group(1)} targetSdk=36")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
