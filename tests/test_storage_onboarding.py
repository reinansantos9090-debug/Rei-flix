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

    def test_native_host_rechecks_and_never_scans_before_authorization(self):
        source = (ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt").read_text(encoding="utf-8")
        self.assertIn("override fun onResume()", source)
        self.assertIn("publishStorageStatus()", source)
        self.assertIn("if (!BroadStorageScanner.hasAccess(this))", source)
        self.assertIn("if (!MediaStoreScanner.hasReadPermission(this))", source)
        self.assertIn("mediaPermissionRequestPending", source)
        self.assertIn("ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION", source)

if __name__ == "__main__": unittest.main()
