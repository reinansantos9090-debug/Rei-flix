# Rei-Flix — Prompt 15

Adds an evidence-first certification runner at scripts/prompt15_certification.py.

The runner inventories test trees, records Git/environment state, executes available Python checks, attempts Android unit tests when the Gradle wrapper is present, and explicitly records unavailable device/APK checks as BLOCKED or NOT VALIDATED.

It never promotes an unavailable environment to PASS. FAIL produces NOT CERTIFIED; missing device/APK evidence produces CERTIFICATION PARTIAL.

Run:

    python scripts/prompt15_certification.py --root .

Outputs:

    build/prompt15-certification.json
    build/prompt15-certification.md

For a real APK:

    python scripts/verify_android_host.py build/ReiFlix.apk
    python scripts/verify_apk_manifest.py build/ReiFlix.apk --aapt2 "$ANDROID_HOME/build-tools/36.0.0/aapt2"
    sha256sum build/ReiFlix.apk

Physical Android 14/15/16 results remain NOT VALIDATED unless actually executed with evidence.
