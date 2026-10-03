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
for attempt in $(seq 1 180); do
  if ! adb start-server >/dev/null 2>&1; then
    echo "adb start-server failed on readiness attempt $attempt; retrying."
    sleep 2
    continue
  fi

  state="$(adb -s "$serial" get-state 2>/dev/null)" || state=""

  if [ "$state" = "offline" ]; then
    echo "adb transport is offline on attempt $attempt; reconnecting."
    if ! adb reconnect offline >/dev/null 2>&1; then
      echo "adb reconnect offline did not complete; resetting adb host."
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
