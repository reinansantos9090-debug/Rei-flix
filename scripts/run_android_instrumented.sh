#!/usr/bin/env bash
set -euo pipefail

api_level="${1:?missing Android API level}"
output_dir="${2:?missing diagnostics output directory}"

mkdir -p "$output_dir"

echo "Waiting for adb/emulator readiness (API $api_level)..."
serial="${ANDROID_SERIAL:-}"
if [ -z "$serial" ]; then
  serial="emulator-${EMULATOR_PORT:-5554}"
fi
echo "Using emulator serial: $serial"

# android-emulator-runner can expose the emulator as offline during the
# transition from boot to a usable adb transport. Android's adb guidance
# recommends resetting the adb host when a connection is lost, so recovery
# below restarts the host and then waits for the same emulator transport.
ready=0
offline_streak=0
for attempt in $(seq 1 180); do
  if ! adb start-server >/dev/null 2>&1; then
    echo "adb start-server failed on readiness attempt $attempt; retrying."
    sleep 2
    continue
  fi

  state="$(adb -s "$serial" get-state 2>/dev/null)" || state=""

  if [ "$state" = "offline" ]; then
    offline_streak=$((offline_streak + 1))
    echo "adb transport is offline on attempt $attempt (streak=$offline_streak); reconnecting."
    if ! adb reconnect offline >/dev/null 2>&1; then
      echo "adb reconnect offline did not complete."
    fi
    if [ "$((offline_streak % 5))" -eq 0 ]; then
      echo "Resetting adb host after $offline_streak consecutive offline checks."
      if ! adb kill-server >/dev/null 2>&1; then
        echo "adb kill-server returned non-zero during recovery."
      fi
      sleep 2
      if ! adb start-server >/dev/null 2>&1; then
        echo "adb start-server failed after host reset."
        sleep 2
        continue
      fi
    fi
    sleep 2
    state="$(adb -s "$serial" get-state 2>/dev/null)" || state=""
  else
    offline_streak=0
  fi

  if [ "$state" = "device" ]; then
    boot="$(adb -s "$serial" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" || boot=""
    if [ "$boot" = "1" ]; then
      ready=1
      break
    fi
  fi

  if [ "$((attempt % 15))" -eq 0 ]; then
    echo "ADB readiness attempt $attempt/180"
    adb devices -l || echo "adb devices diagnostic failed."
  fi
  sleep 2
done

if [ "$ready" -ne 1 ]; then
  echo "ADB did not become ready after the post-boot readiness window."
  if ! adb devices -l; then
    echo "adb devices diagnostic failed."
  fi
  exit 1
fi

cd "$GITHUB_WORKSPACE/build/flutter/android"

# flet build stages Python dependencies at the repository-level build/site-packages.
# The instrumented jobs restore this directory together with build/flutter so
# Gradle receives the same Serious Python dependency tree used by the build.
site_packages="$GITHUB_WORKSPACE/build/site-packages"
if [ ! -d "$site_packages" ]; then
  echo "Missing staged Serious Python site-packages: $site_packages"
  echo "The rendered-project cache must include build/site-packages."
  exit 1
fi
export SERIOUS_PYTHON_SITE_PACKAGES="$site_packages"
echo "Using Serious Python site-packages: $site_packages"

chmod +x gradlew

log="$output_dir/connectedDebugAndroidTest.log"
set +e
./gradlew :app:connectedDebugAndroidTest --no-daemon --stacktrace 2>&1 | tee "$log"
status=${PIPESTATUS[0]}
set -e

if [ "$status" -ne 0 ]; then
  echo "connectedDebugAndroidTest failed for API $api_level with exit=$status"
  echo "===== ANDROID RUNTIME FAILURE DIAGNOSTICS ====="
  {
    echo "--- adb devices ---"
    adb devices -l || true
    echo "--- foreground activity ---"
    adb -s "$serial" shell dumpsys activity activities | grep -E "mResumedActivity|mCurrentFocus|mFocusedApp" | tail -n 20 || true
    echo "--- package state ---"
    adb -s "$serial" shell dumpsys package com.reiflix.reiflix_local | grep -E "versionName|versionCode|enabled=|stopped=|pkgFlags" | head -n 40 || true
    echo "--- logcat errors ---"
    adb -s "$serial" logcat -d -v threadtime -t 1200 | grep -E "FATAL EXCEPTION|AndroidRuntime|ANR in|Application Not Responding|com.reiflix.reiflix_local|serious_python|flutter" | tail -n 240 || true
  } | tee "$output_dir/runtime-failure-diagnostics.txt"
  exit "$status"
fi

echo "connectedDebugAndroidTest VALIDATED api=$api_level"
