from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN_ACTIVITY = ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt"
PLAYER_ACTIVITY = ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/NativePlayerActivity.kt"
MANIFEST = ROOT / "android/app/src/main/AndroidManifest.xml"
MAIN = ROOT / "main.py"


class BackLifecycleTests(unittest.TestCase):
    def read(self, path):
        return path.read_text(encoding="utf-8")

    def test_main_activity_forwards_system_back_to_flet_without_finishing_or_mailbox_navigation(self):
        source = self.read(MAIN_ACTIVITY)
        self.assertIn("import androidx.activity.OnBackPressedCallback", source)
        self.assertIn("onBackPressedDispatcher.addCallback(", source)
        self.assertIn("engine.navigationChannel.popRoute()", source)
        self.assertNotIn('put("type", "android_back")', source)
        handler = source[source.index("private fun installSystemBackHandler"):source.index("private fun persistedSafTreeUris")]
        self.assertNotIn("finish()", handler)

    def test_flet_is_the_python_navigation_surface_for_system_back(self):
        source = self.read(MAIN)
        self.assertIn("page.views.clear()", source)
        self.assertIn("page.views.extend(views)", source)
        self.assertIn("page.on_view_pop = handle_flet_view_pop", source)
        self.assertNotIn("event_type == 'android_back'", source)
        self.assertNotIn('navigate_back("android_back")', source)

    def test_navigation_controller_remains_single_logical_source_of_truth(self):
        source = self.read(MAIN)
        navigation = self.read(ROOT / "core/navigation.py")
        self.assertIn("navigation = NavigationController()", source)
        self.assertIn("for index, route in enumerate(navigation.stack)", source)
        self.assertIn("handle_flet_view_pop", source)
        self.assertIn('navigate_back("flet_view_pop")', source)
        self.assertIn("push_settings", navigation)
        self.assertIn("settings_inner", navigation)
        self.assertNotIn("settings_system_back", source)

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

    def test_legacy_back_overrides_are_absent_from_both_activities(self):
        for path in (MAIN_ACTIVITY, PLAYER_ACTIVITY):
            source = self.read(path)
            self.assertNotIn("override fun onBackPressed()", source)
            self.assertNotIn("KEYCODE_BACK", source)

    def test_settings_is_nested_under_the_same_navigation_controller(self):
        source = self.read(MAIN)
        settings = self.read(ROOT / "views/settings_view.py")
        self.assertIn("on_open_settings_category=navigate_settings_category", source)
        self.assertIn("settings_path_provider=lambda: navigation.settings_path", source)
        self.assertIn("on_open_settings_category=None", settings)
        self.assertNotIn("active_category = [None]", settings)
        self.assertNotIn("on_register_system_back", settings)

    def test_back_has_no_generic_activity_exit_shortcut(self):
        source = self.read(MAIN)
        activity = self.read(MAIN_ACTIVITY)
        self.assertNotIn("finishAffinity(", source)
        self.assertNotIn("finishAffinity(", activity)
        self.assertEqual(source.count("page.on_view_pop = handle_flet_view_pop"), 1)

    def test_navigation_lifecycle_state_is_reconstructible_without_android_objects(self):
        source = self.read(MAIN)
        navigation = self.read(ROOT / "core" / "navigation.py")
        self.assertIn("navigation_state.json", source)
        self.assertIn("navigation.snapshot()", source)
        self.assertIn("navigation.restore(", source)
        self.assertIn("asyncio.to_thread(", source)
        self.assertIn("def snapshot(self)", navigation)
        self.assertIn("def restore(self, state", navigation)
        self.assertNotIn("Activity", navigation)

    def test_android_host_uses_one_lifecycle_back_callback_and_reapplies_ui_without_resetting_python_stack(self):
        activity = self.read(MAIN_ACTIVITY)
        manifest = self.read(MANIFEST)
        self.assertEqual(activity.count("onBackPressedDispatcher.addCallback"), 1)
        self.assertIn("override fun onResume()", activity)
        self.assertIn("override fun onDestroy()", activity)
        self.assertNotIn("finishAffinity(", activity)
        self.assertIn('android:launchMode="singleTask"', manifest)
        self.assertIn('android:documentLaunchMode="never"', manifest)
        self.assertIn('android:enableOnBackInvokedCallback="true"', manifest)

    def test_player_launch_is_single_flight(self):
        source = self.read(MAIN_ACTIVITY)
        self.assertIn("previousActiveRequestId", source)
        self.assertIn("reusingPlayerActivity", source)
        self.assertIn("PLAY_HANDOFF_DUPLICATE", source)
        self.assertIn("activePlayerRequestId = requestId.takeIf { it.isNotBlank() }", source)
        self.assertIn("FLAG_ACTIVITY_REORDER_TO_FRONT", source)

    def test_main_resume_discovery_is_not_unconditional(self):
        source = self.read(MAIN_ACTIVITY)
        start = source.index("override fun onResume()")
        end = source.index("override fun onPause()", start)
        resume = source[start:end]
        self.assertIn("val shouldDiscover = !startupDiscoveryTriggered", resume)
        self.assertIn('publishScanRequest(', resume)
        self.assertIn('"STARTUP"', resume)
        self.assertNotIn("scanMediaStore(null)", resume)
        self.assertNotIn("scanAllStorage(null)", resume)
        self.assertNotIn("scanTree(tree, null)", resume)


if __name__ == "__main__":
    unittest.main()
