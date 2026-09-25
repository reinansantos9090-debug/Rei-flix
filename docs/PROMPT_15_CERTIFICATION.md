# Rei-Flix — Prompt 15 / 15.1 Certification

This document describes the evidence-first certification path.

## Scope

Prompt 15.1 reuses the existing Python and Android unit-test suites. It does not add emulator/AVD execution and does not classify instrumentation tests as PASS without a real device.

The certification runner is:

    python scripts/prompt15_certification.py

In GitHub Actions, after the real APK is built and the rendered Flet Android project exists, the workflow invokes:

    python scripts/prompt15_certification.py \
      --root . \
      --gradle-root build/flutter/android \
      --apk build/ReiFlix.apk \
      --aapt2 "$ANDROID_HOME/build-tools/36.0.0/aapt2"

## Evidence rules

PASS means the corresponding command or check actually executed and produced the expected result.

PARTIAL means related implementation/tests/contracts exist but isolated evidence for the individual requirement is incomplete.

FAIL means the check executed and failed.

NOT VALIDATED means the required validation was intentionally not executed.

BLOCKED BY ENVIRONMENT means the environment prevented execution.

Instrumentation, emulator/AVD, physical-device install/update, runtime memory profiling, FPS measurements, and Android 14/15/16 runtime validation remain NOT VALIDATED when no device is available.

## Generated evidence

The runner produces:

- build/prompt15-certification.json
- build/prompt15-certification.md
- build/prompt15-201-matrix.json

The matrix contains 201 traceable entries with implementation state, test/evidence source, execution state, result, and limitation.

## APK evidence

When an APK is supplied, the runner records the real file path, size, SHA-256, manifest presence, DEX files, and presence of the Rei-Flix native host classes. The repository's dedicated APK host and manifest verifiers are also executed when their required tools are available.

## Emulator policy

Prompt 15.1 intentionally does not start AVDs, Android emulators, API 34/35/36 matrices, Device Farm jobs, or connected instrumentation runs.

This is a validation-scope restriction only. It does not remove or weaken the Android 14/15/16 production implementation.

## Historical regressions

Historical problems are audited through the existing tests and source contracts, including player launch/exit, system UI, gestures, Back, storage permissions, scanner/catalog protection, StorageCapabilities, Flet launch_url compatibility, parser cases, thumbnail callbacks, NativeMailbox, NativeIndex, lifecycle, rotation, Theme, and Home performance.

A production change is made only when the audit exposes an actual defect.

## Latest completed certification run

- Workflow run: 36158703367
- Final repository HEAD used by the run: ccd053c1c69572e5bfc6e52325bdbec5114eb4af
- Classification: **CERTIFICATION PARTIAL**
- 201-item matrix: 26 PASS, 151 PARTIAL, 0 FAIL, 23 NOT VALIDATED, 0 NOT APPLICABLE, 1 BLOCKED BY ENVIRONMENT.
- Python regression: **848 passed, 10 subtests passed**.
- Python compileall: PASS (the workflow's exact `python -m compileall .` gate passed before certification).
- unittest discovery: PASS.
- Android rendered-project unit tests: PASS; `BUILD SUCCESSFUL`.
- APK forensic inspection: PASS.
- Effective packaged manifest verification: PASS.
- APK: `build/ReiFlix.apk`, 144083010 bytes.
- SHA-256: `f6f35ab9137035f7d498e71c8a20467040a5867c5f1676a8623e7b40a0bb0290`.
- Package: `com.reiflix.reiflix_local`.
- versionName: `0.2.1`; versionCode: `1802`; compileSdk/targetSdk: `36`; minSdk: `24`.
- AGP: `8.6.1`; Kotlin: `2.0.21`; Gradle: `8.14`; JDK: `17`; Flet: `0.86.5`.
- APK signing mode: ephemeral-debug; certificate SHA-256: `8a82a043c654864d6c9e433b36549feba86876be1ddefb63ef2bd8e5a6459c3b`.
- Emulator/AVD: **NOT EXECUTED** by policy.
- Physical device: **NOT VALIDATED**.
- Android 14/15/16 runtime matrix: **NOT VALIDATED**.
- Installation/update/clean-install runtime checks: **NOT VALIDATED**.
- Runtime memory/FPS/profiler measurements: **NOT VALIDATED**.

The run completed without a certification-runner FAIL. The remaining PARTIAL/NOT VALIDATED results are evidence-scope limitations or requirements whose individual behavior needs device/runtime/isolated evidence; they are not silently promoted to PASS.
