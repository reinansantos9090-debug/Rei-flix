#!/usr/bin/env bash
set -euo pipefail

api_level="${1:?missing Android API level}"
output_dir="${2:?missing diagnostics output directory}"

mkdir -p "$output_dir"

echo "Waiting for adb/emulator readiness (API $api_level)..."
ready=0
for attempt in $(seq 1 90); do
  state="$(adb get-state 2>/dev/null)" || state=""
  boot="$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" || boot=""
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

adb shell settings put global window_animation_scale 0.0
adb shell settings put global transition_animation_scale 0.0
adb shell settings put global animator_duration_scale 0.0
adb shell settings get global window_animation_scale
adb shell settings get global transition_animation_scale
adb shell settings get global animator_duration_scale

cd "$GITHUB_WORKSPACE/build/flutter/android"
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
