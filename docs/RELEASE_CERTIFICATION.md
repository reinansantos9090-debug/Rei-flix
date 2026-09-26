# Rei-Flix — Release Certification

## Scope

Release certification finalizes the evidence-first certification started in earlier certification stage. It corrects the observed certification failure and tightens requirement-specific evidence without rewriting production architecture.

The certification runner is:

    python scripts/release_certification.py

The runner now owns the executable certification evidence for Python, pytest collection, deterministic repeated pytest execution, unittest discovery, skip/xfail auditing, Android unit tests, Gradle lint discovery/execution, ADB availability, APK forensic inspection, and the 201-item matrix.

## 201-item matrix

The 201 IDs are stable and contain real requirements grouped by area:

- Database / Library
- Consumption
- Navigation
- Player
- Storage
- Artwork
- Search
- Settings / Theme
- Home
- Performance / Static audit
- Certification / CI / APK

Every row records:

ID, Requirement, Area, Implementation reference, Existing test reference, Command, Execution status, Result, Evidence, Limitation.

The runner rejects the old generic form such as "Certification requirement N" and derives totals directly from the generated rows.

## Evidence rules

Only these result classifications are permitted:

- PASS
- PARTIAL
- FAIL
- NOT VALIDATED
- NOT APPLICABLE
- BLOCKED

PASS requires executable evidence. A source path by itself does not become PASS.

PARTIAL means the implementation/test surface exists but complete executable evidence is incomplete.

FAIL means an executable check ran and failed.

NOT VALIDATED is used for deliberately excluded runtime checks such as physical-device validation, Android 14/15/16 runtime validation, installation/update validation, and profiler-only measurements.

BLOCKED is reserved for an executable check that the environment prevented from running.

## No-device policy

This certification does not start:

- Android Emulator / AVD
- connected instrumentation
- Device Farm
- API 34/35/36 runtime matrices

adb devices -l is split into:

- ADB tool availability
- physical/emulator device validation

A zero-device ADB result is never treated as device PASS.

## Executable checks

The runner executes, when the corresponding environment exists:

    python -m compileall .
    pytest --collect-only -q
    pytest -q
    pytest -q
    python -m unittest discover -s tests -v
    ./gradlew :app:testDebugUnitTest --no-daemon
    ./gradlew tasks --all --no-daemon
    ./gradlew <discovered app lint task> --no-daemon

The two pytest executions are compared for test counts and result consistency.

The collection audit compares repository Python test files with pytest-discovered test files.

The skip/xfail audit covers Python and Android test trees and records an explicit classification for each occurrence.

## APK evidence

When the workflow supplies the real APK, the runner records:

- APK path
- file size
- SHA-256
- package
- versionName
- versionCode
- target SDK
- manifest presence and selected manifest contracts
- DEX files and required native host classes
- packaged resources
- APK signature verification when apksigner is available

No device installation is required for these APK-only checks.

## Historical regressions

The certification reuses existing tests and source contracts for the previously reported problem areas, including:

- player launch / exit
- player error events
- status and navigation bars
- immersive lifecycle
- gestures
- Back and predictive Back
- PiP contract
- StorageCapabilities
- Flet launch_url
- permission/cancel/scan flows
- catalog-preservation rules
- NativeMailbox / NativeIndex
- parser and thumbnail regressions
- Theme / Home / performance contracts

Production code is changed only when the executable/static audit exposes an actual defect.

## Generated artifacts

The certification run writes:

- build/release-certification.json
- build/release-certification.md
- build/release-certification-matrix.json

The GitHub Actions workflow uploads the three certification artifacts with the release-certification artifact name.

## Final status

The final classification and 201-item totals in this document are intentionally sourced from the actual earlier certification stage workflow run rather than manually copied numbers. The workflow is blocking on executable failures, while explicit no-device limitations remain NOT VALIDATED.

## Release certification evidence rule

A functional row is not promoted to PASS merely because its implementation file exists and the shared pytest suite passes. PASS requires a requirement-specific static assertion, targeted evidence, package/manifest forensic result, or another objective check recorded in the row. Shared suite coverage without that direct proof remains PARTIAL.
