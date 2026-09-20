import unittest
from pathlib import Path

from core.dialogs import dismiss_dialog
from core.storage_access import StorageAccessState, storage_access_state

ROOT = Path(__file__).resolve().parents[1]

class StorageOnboardingTests(unittest.TestCase):
    def test_real_permission_snapshot_has_deterministic_states(self):
        self.assertEqual(storage_access_state("denied", False), StorageAccessState.NEEDS_MEDIA_PERMISSION)
        self.assertEqual(storage_access_state("partial", False), StorageAccessState.MEDIA_PARTIAL)
        self.assertEqual(storage_access_state("full", False), StorageAccessState.NEEDS_BROAD_STORAGE)
        self.assertEqual(storage_access_state("full", True), StorageAccessState.READY)
        self.assertEqual(storage_access_state("full", True, dismissed=True), StorageAccessState.DECLINED)

    def test_dismissal_detaches_overlay_without_alertdialog_close_api(self):
        class Dialog: open = True
        class Page:
            def __init__(self): self.overlay = [dialog]; self.updated = 0
            def update(self): self.updated += 1
        dialog = Dialog(); page = Page()
        dismiss_dialog(page, dialog)
        self.assertFalse(dialog.open)
        self.assertEqual([], page.overlay)
        self.assertEqual(1, page.updated)

    def test_project_has_no_invalid_alertdialog_close_calls(self):
        sources = "\n".join(path.read_text(encoding="utf-8") for path in ROOT.rglob("*.py") if "tests" not in path.parts)
        self.assertNotIn("dialog.close(", sources)
        self.assertIn("dismiss_dialog", (ROOT / "views" / "settings_view.py").read_text(encoding="utf-8"))

    def test_permission_intent_is_single_task_and_lifecycle_queued(self):
        manifest = (ROOT / "android/app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
        source = (ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt").read_text(encoding="utf-8")
        self.assertIn('android:launchMode="singleTask"', manifest)
        self.assertIn('android:documentLaunchMode="never"', manifest)
        self.assertIn("setIntent(intent)", source)
        self.assertIn("pendingLifecycleAction", source)
        self.assertIn("override fun onResume()", source)
        self.assertIn("activityResumed", source)
        self.assertIn("LIFECYCLE", source)

    def test_permission_request_is_not_launched_from_a_non_resumed_activity(self):
        source = (ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt").read_text(encoding="utf-8")
        request_block = source.split("private fun requestMediaAccess()", 1)[1].split("private fun publishStorageStatus()", 1)[0]
        self.assertIn('if (!activityResumed)', request_block)
        self.assertIn('pendingLifecycleAction = "request_media_access"', request_block)
        self.assertIn("mediaPermissionRequester.launch(permissions)", request_block)

    def test_broad_permission_event_does_not_reopen_onboarding_after_settings_launch(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        block = source.split("event_type == 'broad_storage_permission':", 1)[1].split("event_type == 'broad_storage_error':", 1)[0]
        self.assertIn("was_waiting = storage_onboarding[\"waiting_for_result\"]", block)
        self.assertIn('storage_onboarding["dismissed"] = True', block)
        self.assertIn("Do not reopen the onboarding modal", block)

    def test_cancel_and_allow_callbacks_are_lifecycle_safe(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        start = source.index("        async def allow(_event):")
        end = source.index("        dialog.actions =", start)
        block = source[start:end]
        self.assertIn('storage_onboarding["waiting_for_result"] = True', block)
        self.assertIn("dismiss_dialog(page, dialog)", block)
        self.assertNotIn("asyncio.sleep(0)", block)
        self.assertIn("async def cancel(_event):", block)
        cancel = block.split("        def cancel(_event):", 1)[1]
        self.assertIn('storage_onboarding["dismissed"] = True', cancel)
        self.assertNotIn("request_video_access", cancel)
        self.assertNotIn("open_broad_storage_access", cancel)

    def test_startup_does_not_self_launch_main_activity_for_storage_snapshot(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        startup = source[source.index("    if bridge.available:"):source.index("    render_current()", source.index("    if bridge.available:"))]
        self.assertNotIn("bridge.check_storage_access", startup)
        self.assertIn("MainActivity publishes the authoritative storage snapshot", startup)

    def test_native_intents_have_unique_request_identity_and_are_deduplicated(self):
        bridge = (ROOT / "core/android_bridge.py").read_text(encoding="utf-8")
        main = (ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt").read_text(encoding="utf-8")
        self.assertIn("uuid.uuid4().hex", bridge)
        self.assertIn('"request_id": request_id', bridge)
        self.assertIn('getQueryParameter("request_id")', main)
        self.assertIn("lastHandledNativeRequestId", main)
        self.assertIn("Ignoring duplicate native request", main)

    def test_activity_preserves_request_state_across_recreation(self):
        source = (ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt").read_text(encoding="utf-8")
        self.assertIn("STATE_LAST_NATIVE_REQUEST_ID", source)
        self.assertIn("STATE_PENDING_LIFECYCLE_ACTION", source)
        self.assertIn("STATE_BROAD_SETTINGS_PENDING", source)
        self.assertIn("savedInstanceState?.getString(STATE_LAST_NATIVE_REQUEST_ID)", source)
        self.assertIn("override fun onSaveInstanceState(outState: Bundle)", source)

    def test_open_settings_does_not_publish_a_false_permission_before_navigation(self):
        source = (ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt").read_text(encoding="utf-8")
        block = source.split("private fun openBroadStorageSettings()", 1)[1].split("private fun openTreePicker()", 1)[0]
        self.assertNotIn('put("granted", false)', block)
        self.assertIn("broadStoragePermissionPending = true", block)
        self.assertIn("publishStorageStatus()", source)

    def test_native_host_rechecks_and_never_scans_before_authorization(self):
        source = (ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt").read_text(encoding="utf-8")
        self.assertIn("override fun onResume()", source)
        self.assertIn("publishStorageStatus()", source)
        self.assertIn("if (!BroadStorageScanner.hasAccess(this))", source)
        self.assertIn("if (!MediaStoreScanner.hasReadPermission(this))", source)
        self.assertIn("mediaPermissionRequestPending", source)
        self.assertIn("ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION", source)

if __name__ == "__main__": unittest.main()
