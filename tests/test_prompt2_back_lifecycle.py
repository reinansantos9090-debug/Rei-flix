from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN_ACTIVITY = ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt"
PLAYER_ACTIVITY = ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/NativePlayerActivity.kt"
MANIFEST = ROOT / "android/app/src/main/AndroidManifest.xml"
MAIN = ROOT / "main.py"


class Prompt2BackLifecycleTests(unittest.TestCase):
    def read(self, path):
        return path.read_text(encoding="utf-8")

    def test_main_activity_does_not_intercept_system_back_for_mailbox_navigation(self):
        source = self.read(MAIN_ACTIVITY)
        self.assertNotIn("OnBackPressedCallback", source)
        self.assertNotIn("backCallback", source)
        self.assertNotIn('put("type", "android_back")', source)
        self.assertNotIn("SystemClock", source)

    def test_flet_is_the_python_navigation_surface_for_system_back(self):
        source = self.read(MAIN)
        self.assertIn("page.views.clear()", source)
        self.assertIn("page.views.extend(views)", source)
        self.assertIn("page.on_view_pop = handle_flet_view_pop", source)
        self.assertNotIn("event_type == 'android_back'", source)
        self.assertNotIn('navigate_back("android_back")', source)

    def test_navigation_controller_remains_single_logical_source_of_truth(self):
        source = self.read(MAIN)
        self.assertIn("navigation = NavigationController()", source)
        self.assertIn("for index, route in enumerate(navigation.stack)", source)
        self.assertIn("handle_flet_view_pop", source)
        self.assertIn('navigate_back("flet_view_pop")', source)

    def test_manifest_uses_single_task_and_predictive_back_enabled(self):
        manifest = self.read(MANIFEST)
        self.assertIn('android:launchMode="singleTask"', manifest)
        self.assertIn('android:documentLaunchMode="never"', manifest)
        self.assertIn('android:enableOnBackInvokedCallback="true"', manifest)

    def test_player_keeps_native_back_dispatch_and_finishes_itself(self):
        source = self.read(PLAYER_ACTIVITY)
        self.assertIn("onBackPressedDispatcher.addCallback(", source)
        self.assertIn('finishPlayer("android_back")', source)
        self.assertIn("player.release()", source)
        self.assertIn("setResult(", source)

    def test_player_launch_is_single_flight(self):
        source = self.read(MAIN_ACTIVITY)
        self.assertIn("if (activePlayerRequestId != null)", source)
        self.assertIn("PLAY_HANDOFF_BUSY", source)
        self.assertIn("PLAY_HANDOFF_DUPLICATE", source)
        self.assertIn("activePlayerRequestId = requestId.takeIf { it.isNotBlank() }", source)

    def test_main_resume_discovery_is_not_unconditional(self):
        source = self.read(MAIN_ACTIVITY)
        start = source.index("override fun onResume()")
        end = source.index("override fun onPause()", start)
        resume = source[start:end]
        self.assertIn("val shouldDiscover = !startupDiscoveryTriggered", resume)
        self.assertIn("if (shouldDiscover || mediaAccessChangedToUsable)", resume)
        self.assertIn("if (shouldDiscover || broadBecameAvailable)", resume)
        self.assertIn("if (shouldDiscover)", resume)


if __name__ == "__main__":
    unittest.main()
