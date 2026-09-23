#!/usr/bin/env bash
set -Eeuo pipefail

WORKSPACE="${GITHUB_WORKSPACE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PACKAGE="com.reiflix.reiflix_local"
DIAG_ROOT="${WORKSPACE}/build/android36-diagnostics"
CLASS_TIMEOUT_SECONDS="${REIFLIX_ANDROID_CLASS_TIMEOUT_SECONDS:-120}"
METHOD_TIMEOUT_SECONDS="${REIFLIX_ANDROID_METHOD_TIMEOUT_SECONDS:-90}"
FULL_TIMEOUT_SECONDS="${REIFLIX_ANDROID_FULL_TIMEOUT_SECONDS:-300}"

mkdir -p "${DIAG_ROOT}"
printf 'Android 36 instrumentation diagnostic run\n' > "${DIAG_ROOT}/summary.txt"

capture() {
    local output="$1"
    shift
    if timeout 20s "$@" >"${output}" 2>&1; then
        return 0
    else
        local status=$?
        printf '\nCOMMAND_EXIT=%s\n' "${status}" >>"${output}"
        return 0
    fi
}

collect_diagnostics() {
    local label="$1"
    local safe_label
    safe_label="$(printf '%s' "${label}" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9._-' '_')"
    local dir="${DIAG_ROOT}/${safe_label}"
    mkdir -p "${dir}"

    {
        printf 'label=%s\n' "${label}"
        printf 'timestamp_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        printf 'git_sha=%s\n' "${GITHUB_SHA:-unknown}"
        printf 'runner=%s\n' "${RUNNER_NAME:-unknown}"
    } >"${dir}/metadata.txt"

    capture "${dir}/adb_devices.txt" adb devices -l
    capture "${dir}/sdk.txt" adb shell getprop ro.build.version.sdk
    capture "${dir}/release.txt" adb shell getprop ro.build.version.release
    capture "${dir}/instrumentation.txt" adb shell pm list instrumentation
    capture "${dir}/activity_top.txt" adb shell dumpsys activity top
    capture "${dir}/window.txt" adb shell dumpsys window
    capture "${dir}/input.txt" adb shell dumpsys input
    capture "${dir}/package.txt" adb shell dumpsys package "${PACKAGE}"
    capture "${dir}/media_session.txt" adb shell dumpsys media_session
    capture "${dir}/surfaceflinger.txt" adb shell dumpsys SurfaceFlinger
    capture "${dir}/gfxinfo.txt" adb shell dumpsys gfxinfo "${PACKAGE}"
    capture "${dir}/media_codec_logcat.txt" adb logcat -d -b all -v threadtime MediaCodec:* ExoPlayer:* ActivityTaskManager:* WindowManager:* '*:S'
    capture "${dir}/logcat_all.txt" adb logcat -d -b all -v threadtime

    local pids
    pids="$(timeout 20s adb shell pidof "${PACKAGE}" 2>/dev/null | tr -d '\r' || true)"
    if [[ -n "${pids}" ]]; then
        {
            for pid in ${pids}; do
                if ! timeout 20s adb shell kill -3 "${pid}"; then
                    printf 'kill -3 failed for pid=%s\n' "${pid}"
                fi
            done
        } >"${dir}/thread_dump_command.txt" 2>&1
        capture "${dir}/logcat_after_thread_dump.txt" adb logcat -d -b all -v threadtime
    fi
}

reset_device_state() {
    for package in "${PACKAGE}" "com.android.settings" "com.android.documentsui" "com.google.android.documentsui"; do
        if ! timeout 20s adb shell am force-stop "${package}"; then
            printf 'force-stop unavailable or failed for %s\n' "${package}"
        fi
    done
    if ! timeout 20s adb logcat -c; then
        printf 'logcat clear failed; continuing with existing logcat\n'
    fi
    if ! timeout 20s adb shell input keyevent 3; then
        printf 'home key dispatch failed; continuing\n'
    fi
}

run_case() {
    local selector="$1"
    local label="$2"
    local timeout_seconds="$3"
    local safe_label
    safe_label="$(printf '%s' "${label}" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9._-' '_')"

    printf '\n=== CASE %s ===\n' "${label}"
    printf 'selector=%s\n' "${selector}"

    reset_device_state
    local status=0
    if [[ -n "${selector}" ]]; then
        if timeout --foreground --signal=TERM --kill-after=30s "${timeout_seconds}s" \
            ./gradlew :app:connectedDebugAndroidTest --no-daemon --stacktrace \
            "-Pandroid.testInstrumentationRunnerArguments.class=${selector}"; then
            status=0
        else
            status=$?
        fi
    else
        if timeout --foreground --signal=TERM --kill-after=30s "${timeout_seconds}s" \
            ./gradlew :app:connectedDebugAndroidTest --no-daemon --stacktrace; then
            status=0
        else
            status=$?
        fi
    fi

    if (( status != 0 )); then
        printf 'CASE_FAILED label=%s selector=%s exit=%s\n' "${label}" "${selector}" "${status}" | tee -a "${DIAG_ROOT}/summary.txt"
        collect_diagnostics "${safe_label}"
    else
        printf 'CASE_PASS label=%s selector=%s\n' "${label}" "${selector}" | tee -a "${DIAG_ROOT}/summary.txt"
    fi

    reset_device_state
    return "${status}"
}

declare -a classes=(
    "back-settings|com.reiflix.reiflix_local.BackAndSettingsReturnInstrumentedTest"
    "device-flow|com.reiflix.reiflix_local.DeviceFlowInstrumentedTest"
    "native-index|com.reiflix.reiflix_local.NativeIndexInstrumentedTest"
    "native-mailbox|com.reiflix.reiflix_local.NativeMailboxInstrumentedTest"
    "native-player|com.reiflix.reiflix_local.NativePlayerPlaybackInstrumentedTest"
)

overall_status=0
failed_classes=()

for entry in "${classes[@]}"; do
    label="${entry%%|*}"
    selector="${entry#*|}"
    if ! run_case "${selector}" "${label}" "${CLASS_TIMEOUT_SECONDS}"; then
        overall_status=1
        failed_classes+=( "${label}" )
    fi
done

run_failed_class_methods() {
    local label="$1"
    local class_name=""
    local methods=()

    case "${label}" in
        back-settings)
            class_name="com.reiflix.reiflix_local.BackAndSettingsReturnInstrumentedTest"
            methods=(
                "allFilesSettingsBackReturnsToMainActivity"
                "appInfoSettingsBackReturnsToMainActivity"
                "safPickerBackReturnsToMainActivityAndReleasesPendingState"
            )
            ;;
        device-flow)
            class_name="com.reiflix.reiflix_local.DeviceFlowInstrumentedTest"
            methods=(
                "runtimeApiAndNativeBatchContract"
                "cancelledGenerationPreservesCommittedSnapshot"
            )
            ;;
        native-index)
            class_name="com.reiflix.reiflix_local.NativeIndexInstrumentedTest"
            methods=("partialScanKeepsCommittedSnapshot")
            ;;
        native-mailbox)
            class_name="com.reiflix.reiflix_local.NativeMailboxInstrumentedTest"
            methods=("mailbox_write_is_atomic_envelope_and_leaves_no_temp_file")
            ;;
        native-player)
            class_name="com.reiflix.reiflix_local.NativePlayerPlaybackInstrumentedTest"
            methods=("localMediaStoreFixture_reachesReadyAndPlays_inImmersivePlayer")
            ;;
    esac

    for method in "${methods[@]}"; do
        if ! run_case "${class_name}#${method}" "${label}__${method}" "${METHOD_TIMEOUT_SECONDS}"; then
            overall_status=1
        fi
    done
}

for label in "${failed_classes[@]}"; do
    printf 'ISOLATING_FAILED_CLASS=%s\n' "${label}" | tee -a "${DIAG_ROOT}/summary.txt"
    run_failed_class_methods "${label}"
done

if (( ${overall_status} == 0 )); then
    if ! run_case "" "api36-full-suite" "${FULL_TIMEOUT_SECONDS}"; then
        overall_status=1
    fi
else
    printf 'FULL_SUITE_SKIPPED_DURING_DIAGNOSTIC_FAILURE: fix isolated case before certification.\n' | tee -a "${DIAG_ROOT}/summary.txt"
fi

printf 'DIAGNOSTIC_EXIT=%s\n' "${overall_status}" | tee -a "${DIAG_ROOT}/summary.txt"
exit "${overall_status}"
