#!/usr/bin/env bash
set -euo pipefail

api_level="${1:?missing Android API level}"
output_dir="${2:?missing diagnostics output directory}"

mkdir -p "$output_dir"

echo "Waiting for adb/emulator readiness (API $api_level)..."
serial="${ANDROID_SERIAL:-}"
if [ -z "$serial" ]; then
  serial="$(adb devices | awk '$1 ~ /^emulator-[0-9]+$/ { print $1; exit }')"
fi
serial="${serial:-emulator-5554}"
echo "Using emulator serial: $serial"

# The emulator runner can briefly expose the transport as offline even after
# the emulator itself has booted. Reset the host-side connection and then wait
# for the selected transport to become operational.
adb start-server >/dev/null 2>&1 || true
adb reconnect offline >/dev/null 2>&1 || true

ready=0
for attempt in $(seq 1 120); do
  state="$(adb -s "$serial" get-state 2>/dev/null)" || state=""
  if [ "$state" = "offline" ]; then
    adb reconnect offline >/dev/null 2>&1 || true
  fi
  boot="$(adb -s "$serial" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" || boot=""
  if [ "$state" = "device" ] && [ "$boot" = "1" ]; then
    ready=1
    break
  fi
  sleep 2
done

if [ "$ready" -ne 1 ]; then
  echo "ADB did not become ready after the post-boot readiness window."
  adb devices -l || adb_status=$?
  exit 1
fi

adb -s "$serial" shell settings put global window_animation_scale 0.0
adb -s "$serial" shell settings put global transition_animation_scale 0.0
adb -s "$serial" shell settings put global animator_duration_scale 0.0
adb -s "$serial" shell settings get global window_animation_scale
adb -s "$serial" shell settings get global transition_animation_scale
adb -s "$serial" shell settings get global animator_duration_scale

cd "$GITHUB_WORKSPACE/build/flutter/android"

# The rendered Flet Android Gradle project requires the staged Python site-packages path.
# Keep this scoped to the rendered test project so instrumented builds are reproducible.
site_packages="$GITHUB_WORKSPACE/build/flutter/site-packages"
test -d "$site_packages"
export SERIOUS_PYTHON_SITE_PACKAGES="$site_packages"

chmod +x gradlew

log="$output_dir/connectedDebugAndroidTest.log"
set +e
./gradlew :app:connectedDebugAndroidTest --no-daemon --stacktrace 2>&1 | tee "$log"
status=${PIPESTATUS[0]}
set -e

if [ "$status" -ne 0 ]; then
  echo "connectedDebugAndroidTest failed for API $api_level with exit=$status"
  exit "$status"
fi

echo "connectedDebugAndroidTest VALIDATED api=$api_level"
