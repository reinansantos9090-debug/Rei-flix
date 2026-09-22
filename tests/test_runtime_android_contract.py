import ast
import unittest
from pathlib import Path

from core.android_bridge import AndroidBridge


ROOT = Path(__file__).resolve().parents[1]
MAIN_ACTIVITY = ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt"
PLAYER_ACTIVITY = ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/NativePlayerActivity.kt"
SYSTEM_UI = ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/SystemUiController.kt"


class RuntimeAndroidContractTests(unittest.TestCase):
    def test_python_normalizer_preserves_content_uri_identity(self):
        source = "content://media/external/video/media/42"
        self.assertEqual(AndroidBridge.normalize_local_media_reference(source), source)

    def test_python_normalizer_accepts_case_insensitive_local_uri_scheme(self):
        self.assertEqual(
            AndroidBridge.normalize_local_media_reference("CONTENT://media/external/video/media/42"),
            "content://media/external/video/media/42",
        )
        self.assertEqual(
            AndroidBridge.normalize_local_media_reference("FILE:///storage/emulated/0/Anime/Ep 01.mp4"),
            "file:///storage/emulated/0/Anime/Ep 01.mp4",
        )

    def test_python_normalizer_rejects_remote_sources(self):
        for value in ("https://example.invalid/video.mp4", "rtsp://example.invalid/video", "reiflix://native?action=play"):
            self.assertIsNone(AndroidBridge.normalize_local_media_reference(value))

    def test_python_normalizer_accepts_absolute_local_path(self):
        value = AndroidBridge.normalize_local_media_reference("/tmp/reiflix-episode.mp4")
        self.assertTrue(value.startswith("file:///"))
        self.assertTrue(value.endswith("/tmp/reiflix-episode.mp4"))

    def test_main_player_handoff_is_request_id_idempotent(self):
        source = MAIN_ACTIVITY.read_text(encoding="utf-8")
        self.assertIn("activePlayerRequestId", source)
        self.assertIn("PLAY_HANDOFF_ACCEPTED", source)
        self.assertIn("PLAY_HANDOFF_DUPLICATE", source)
        self.assertNotIn("playerLaunchActive", source)
        self.assertNotIn("applyNormalSystemUi", source)
        self.assertIn("applyImmersiveSystemUi()", source)
        self.assertIn("registerForActivityResult(ActivityResultContracts.StartActivityForResult())", source)
        self.assertIn("playerActivityLauncher.launch(intent)", source)

    def test_native_player_has_structured_lifecycle_and_playback_diagnostics(self):
        source = PLAYER_ACTIVITY.read_text(encoding="utf-8")
        required = (
            "URI_RECEIVED",
            "URI_NORMALIZED",
            "PREFLIGHT_START",
            "PREFLIGHT_OK",
            "PREFLIGHT_FAILED",
            "EXOPLAYER_CREATE",
            "MEDIA_ITEM",
            "PREPARE",
            "PLAYBACK_STATE=",
            "PlaybackException",
            "player_error",
            "player_exit_reported",
            "player_exited",
            "onCreate",
            "onStart",
            "onResume",
            "onPause",
            "onStop",
            "onWindowFocusChanged",
            "onConfigurationChanged",
        )
        for token in required:
            self.assertIn(token, source)
        self.assertIn("WindowInsetsCompat.Type.systemBars()", source)
        self.assertIn("WindowInsetsCompat.Type.displayCutout()", source)
        self.assertIn("BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE", source)
        self.assertIn("playerView.player = player", source)
        self.assertIn("playerView.player === player", source)
        self.assertIn("PLAYER_VIEW_ATTACHED", source)
        self.assertIn("FIRST_FRAME_RENDERED", source)
        self.assertIn("ViewCompat.getRootWindowInsets(window.decorView)", source)
        self.assertNotIn("Gravity.CENTER + fixed", source)
        self.assertNotIn("sleep(", source)

    def test_native_player_supports_all_local_source_families(self):
        source = PLAYER_ACTIVITY.read_text(encoding="utf-8")
        self.assertIn('sourceFor(uri)', source)
        self.assertIn('MediaStore.AUTHORITY -> "mediastore"', source)
        self.assertIn('-> "broad_storage"', source)
        self.assertIn("SafScanner.isAuthorizedDocument", source)
        self.assertIn("MediaStoreScanner.isAuthorizedDocument", source)
        self.assertIn("BroadStorageScanner.isAuthorizedFile", source)
        self.assertIn("contentResolver.openFileDescriptor", source)

    def test_native_player_gesture_contract_is_continuous_and_non_stretching(self):
        source = PLAYER_ACTIVITY.read_text(encoding="utf-8")
        for token in (
            "HORIZONTAL_SEEK",
            "VERTICAL_BRIGHTNESS",
            "VERTICAL_VOLUME",
            "ScaleGestureDetector",
            "RESIZE_MODE_ZOOM",
            "RESIZE_MODE_FIT",
            "adjustBrightness",
            "adjustVolumeByFraction",
            "showFeedback",
            "setControlsVisible",
            "CONTROL_TIMEOUT_MS",
            "pendingSeekPosition",
            "ViewConfiguration.getDoubleTapTimeout()",
        ):
            self.assertIn(token, source)
        self.assertNotIn("RESIZE_MODE_FILL", source)

    def test_scroll_architecture_has_one_vertical_owner_per_main_screen(self):
        views = {
            "home_view.py": "views/home_view.py",
            "details_view.py": "views/details_view.py",
            "organize_view.py": "views/organize_view.py",
            "settings_view.py": "views/settings_view.py",
        }
        for label, relative in views.items():
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("scroll=ft.ScrollMode.AUTO", source, label)
            tree = ast.parse(source)
            self.assertTrue(tree.body, label)
            vertical_columns = [
                node for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "Column"
                and any(
                    kw.arg == "scroll"
                    and isinstance(kw.value, ast.Attribute)
                    and kw.value.attr == "AUTO"
                    for kw in node.keywords
                )
            ]
            self.assertEqual(
                1,
                len(vertical_columns),
                f"{label} must have exactly one primary vertical scroll owner",
            )
        home = (ROOT / "views/home_view.py").read_text(encoding="utf-8")
        organize = (ROOT / "views/organize_view.py").read_text(encoding="utf-8")
        self.assertIn('grid = ft.Row(', home)
        self.assertIn('content = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO', organize)
        self.assertIn("content=layout,", home)
        self.assertIn("content=content,", organize)
        self.assertIn("content=layout,", (ROOT / "views/details_view.py").read_text(encoding="utf-8"))
        self.assertIn("content=content,", (ROOT / "views/settings_view.py").read_text(encoding="utf-8"))
        for source in (home, organize, (ROOT / "views/details_view.py").read_text(encoding="utf-8"), (ROOT / "views/settings_view.py").read_text(encoding="utf-8")):
            self.assertIn("expand=True", source)

    def test_python_handles_native_player_state_and_navigation_events(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        for token in (
            "event_type in {'player_progress', 'player_paused', 'player_completed'}",
            "store.save_progress",
            "event_type == 'player_mark_watched'",
            "store.set_watched",
            "event_type == 'player_autoplay_changed'",
            "store.set_preference",
            "event_type in {'player_next_request', 'player_previous_request'}",
            "library.next_episode(current_path)",
            "library.previous_episode(current_path)",
            "await start_native_player(",
            "event_type == 'player_exited'",
            "on_catalog_changed()",
        ):
            self.assertIn(token, source)

    def test_scan_ui_only_calls_running_a_snapshot_not_final(self):
        settings = (ROOT / "views/settings_view.py").read_text(encoding="utf-8")
        self.assertIn("Varredura em andamento:", settings)
        self.assertIn('runtime_status in {"CHECKING", "SCANNING", "WAITING_FOR_MEDIASTORE"}', settings)
        self.assertIn("Última varredura:", settings)
        self.assertIn("Status:", settings)

    def test_system_ui_is_immersive_and_not_normal_bars(self):
        main = MAIN_ACTIVITY.read_text(encoding="utf-8")
        system_ui = SYSTEM_UI.read_text(encoding="utf-8")
        self.assertNotIn("applyNormalSystemUi", main)
        self.assertNotIn("applyNormal()", system_ui)
        self.assertIn("applyImmersive()", system_ui)
        self.assertIn("WindowCompat.setDecorFitsSystemWindows(window, false)", system_ui)
        self.assertIn("hide(WindowInsetsCompat.Type.systemBars())", system_ui)
        self.assertIn("BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE", system_ui)

    def test_no_silent_exception_suppression_in_runtime_android_sources(self):
        for path in (MAIN_ACTIVITY, PLAYER_ACTIVITY, SYSTEM_UI):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("except Exception: pass", source)
            self.assertNotIn("catch (Exception) { pass }", source)

if __name__ == "__main__":
    unittest.main()
