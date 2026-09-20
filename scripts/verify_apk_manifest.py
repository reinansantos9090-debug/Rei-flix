#!/usr/bin/env python3
"""Validate the effective AndroidManifest.xml packaged in a Rei-Flix APK."""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path


MAIN_ACTIVITY = "com.reiflix.reiflix_local.MainActivity"
REQUIRED_PERMISSIONS = (
    "android.permission.READ_EXTERNAL_STORAGE",
    "android.permission.READ_MEDIA_VIDEO",
    "android.permission.READ_MEDIA_VISUAL_USER_SELECTED",
    "android.permission.MANAGE_EXTERNAL_STORAGE",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("apk", type=Path)
    parser.add_argument(
        "--aapt2",
        type=Path,
        default=Path(shutil.which("aapt2") or ""),
    )
    args = parser.parse_args()

    if not args.apk.is_file():
        parser.error(f"APK not found: {args.apk}")
    if not args.aapt2.is_file():
        parser.error(f"aapt2 not found: {args.aapt2}")

    command = [str(args.aapt2), "dump", "xmltree", str(args.apk), "--file", "AndroidManifest.xml"]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr or result.stdout, file=sys.stderr)
        return result.returncode or 1

    manifest = result.stdout
    activities = re.findall(r"(?ms)^    E: activity\b.*?(?=^    E: activity\b|\Z)", manifest)
    main_block = next(
        (block for block in activities if MAIN_ACTIVITY in block),
        None,
    )
    if main_block is None:
        print(f"MainActivity not found in packaged manifest: {MAIN_ACTIVITY}", file=sys.stderr)
        return 1

    checks = (
        ("launchMode=singleTask", re.search(r"android:launchMode\b.*?0x00000002\b", main_block)),
        ("documentLaunchMode=never", re.search(r"android:documentLaunchMode\b.*?0x00000003\b", main_block)),
        ("exported=true", re.search(r"android:exported\b.*?0xffffffff\b|android:exported\b.*?true", main_block)),
        ("reiflix://native", "reiflix" in main_block and "native" in main_block),
    )
    failed = [name for name, ok in checks if not ok]
    failed.extend(
        permission
        for permission in REQUIRED_PERMISSIONS
        if permission not in manifest
    )
    if failed:
        print("Packaged manifest validation failed:", file=sys.stderr)
        for item in failed:
            print(f"  - {item}", file=sys.stderr)
        print(main_block, file=sys.stderr)
        return 1

    print("Verified packaged AndroidManifest.xml:")
    print(f"  MainActivity: {MAIN_ACTIVITY}")
    print("  launchMode: singleTask (0x00000002)")
    print("  documentLaunchMode: never (0x00000003)")
    print("  exported: true")
    print("  deep-link: reiflix://native")
    for permission in REQUIRED_PERMISSIONS:
        print(f"  permission: {permission}")
    print("  legacy media permission: READ_EXTERNAL_STORAGE (maxSdkVersion<=32 checked by source/template)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
