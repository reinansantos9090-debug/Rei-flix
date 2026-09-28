import tempfile
import time
import unittest
from pathlib import Path

from core.library_store import LibraryStore
from core.settings import SettingsStore


ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "main.py").read_text(encoding="utf-8")
DETAILS = (ROOT / "views" / "details_view.py").read_text(encoding="utf-8")
ANILIST = (ROOT / "core" / "anilist.py").read_text(encoding="utf-8")
STORE = (ROOT / "core" / "library_store.py").read_text(encoding="utf-8")
MAIN_ACTIVITY = (ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt").read_text(encoding="utf-8")
PLAYER = (ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/NativePlayerActivity.kt").read_text(encoding="utf-8")
SYSTEM_UI = (ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/SystemUiController.kt").read_text(encoding="utf-8")


class Prompt2StabilizationTests(unittest.TestCase):
    def _episode_store(self):
        tmp = tempfile.TemporaryDirectory()
        store = LibraryStore(tmp.name)
        anime = store.upsert_anime(
            "prompt2",
            {"title": "Prompt 2", "genres": "[]", "media_kind": "series"},
        )
        path = "/storage/emulated/0/Anime/Prompt 2 S01E01.mkv"
        store.upsert_episode(anime, path, "Prompt 2 S01E01.mkv", 1, 1)
        return tmp, store, path

    def test_prompt1_details_guards_remain(self):
        self.assertNotIn("autofocus=bool(primary_target)", DETAILS)
        self.assertIn("palette_changed = (", DETAILS)
        self.assertIn("on_catalog_changed(refresh_details=False)", MAIN)
        self.assertIn("player_transition_inflight", MAIN)
        self.assertIn("episodeChangeTimeout", PLAYER)
        self.assertIn("resolveImmersivePolicy", PLAYER)

    def test_host_is_immersive_and_lifecycle_reapplies_the_central_policy(self):
        self.assertIn("applyApplicationImmersivePolicy(useContextAppearance = false)", MAIN_ACTIVITY)
        self.assertIn("override fun onStart()", MAIN_ACTIVITY)
        self.assertIn("override fun onResume()", MAIN_ACTIVITY)
        self.assertIn("override fun onWindowFocusChanged(hasFocus: Boolean)", MAIN_ACTIVITY)
        self.assertIn("override fun onConfigurationChanged", MAIN_ACTIVITY)
        self.assertIn("applyApplicationImmersivePolicy", SYSTEM_UI)
        self.assertIn("hide(WindowInsetsCompat.Type.systemBars())", SYSTEM_UI)
        self.assertIn("show(WindowInsetsCompat.Type.systemBars())", SYSTEM_UI)

    def test_player_startup_applies_final_system_ui_policy_without_normal_flash(self):
        bootstrap = PLAYER[PLAYER.index("override fun onCreate"):PLAYER.index("override fun onNewIntent")]
        self.assertNotIn("systemUiController.applyApplicationPolicy()", bootstrap)
        self.assertIn('if (shouldUseImmersive()) enterImmersiveMode() else restoreSystemUiBeforeExit()', bootstrap)

    def test_native_player_transition_write_failure_clears_pending_state(self):
        start = PLAYER.index("private fun requestEpisode")
        end = PLAYER.index("private fun seekToSavedPosition", start)
        block = PLAYER[start:end]
        self.assertIn("val published = NativeMailbox.write(", block)
        self.assertIn("if (!published)", block)
        self.assertIn("episodeChangePending = false", block)
        self.assertIn("handler.removeCallbacks(episodeChangeTimeout)", block)
        destroy = PLAYER[PLAYER.index("override fun onDestroy"):PLAYER.index("private fun shouldUseImmersive")]
        self.assertIn("handler.removeCallbacks(episodeChangeTimeout)", destroy)

    def test_player_overlaid_events_do_not_rebuild_flet_under_the_native_activity(self):
        watched_start = MAIN.index("elif event_type == 'player_mark_watched':")
        watched_end = MAIN.index("elif event_type == 'player_mark_unwatched':", watched_start)
        unwatched_end = MAIN.index("elif event_type == 'player_autoplay_changed':", watched_end)
        watched = MAIN[watched_start:watched_end]
        unwatched = MAIN[watched_end:unwatched_end]
        self.assertNotIn("render_current()", watched)
        self.assertNotIn("render_current()", unwatched)
        self.assertIn("elif event_type == 'player_exited':", MAIN)
        self.assertIn("on_catalog_changed()", MAIN[MAIN.index("elif event_type == 'player_exited':"):])

    def test_autoplay_event_updates_canonical_settings_key(self):
        start = MAIN.index("elif event_type == 'player_autoplay_changed':")
        end = MAIN.index("elif event_type in {'player_next_request', 'player_previous_request'}:", start)
        block = MAIN[start:end]
        self.assertIn('settings.set("player.autoplay_next", enabled)', block)
        self.assertNotIn("store.set_preference('autoplay_next'", block)

        with tempfile.TemporaryDirectory() as directory:
            store = LibraryStore(directory)
            settings = SettingsStore(store)
            settings.set("player.autoplay_next", False)
            self.assertFalse(settings.get("player.autoplay_next"))
            self.assertIsNone(store.get_preference("autoplay_next"))

    def test_file_uri_updates_absolute_path_progress_and_watched_state(self):
        tmp, store, path = self._episode_store()
        self.addCleanup(tmp.cleanup)
        uri = "file:///storage/emulated/0/Anime/Prompt%202%20S01E01.mkv"
        now = int(time.time() * 1000)
        self.assertTrue(store.save_progress(uri, 30, 100, event_created_at=now))
        self.assertEqual(30, store.physical_row(path)["progress"])
        self.assertTrue(store.set_watched(uri, True))
        row = store.physical_row(path)
        self.assertTrue(row["watched"])
        self.assertEqual(100, row["progress"])

    def test_playback_event_ordering_is_atomic_across_uri_representations(self):
        tmp, store, path = self._episode_store()
        self.addCleanup(tmp.cleanup)
        uri = "file:///storage/emulated/0/Anime/Prompt%202%20S01E01.mkv"
        t1 = int(time.time() * 1000)
        self.assertTrue(store.save_progress(uri, 80, 100, event_created_at=t1))
        self.assertFalse(store.save_progress(path, 40, 100, event_created_at=t1 - 100))
        self.assertEqual(80, store.physical_row(path)["progress"])
        self.assertTrue(store.save_progress(path, 25, 100, event_created_at=t1 + 100))
        self.assertEqual(25, store.physical_row(path)["progress"])

    def test_details_metadata_and_palette_tasks_have_stale_result_guards(self):
        self.assertIn("navigation.current != \"details\"", MAIN)
        self.assertIn("(current[0] or {}).get(\"id\") != anime_id", MAIN)
        self.assertIn("is_active=None", DETAILS)
        self.assertIn("callable(is_active) and not is_active()", DETAILS)
        self.assertIn("details_instance_generation", MAIN)
        self.assertIn("detail_instance_token", MAIN)

    def test_anilist_translation_does_not_hold_the_rate_limit_lock(self):
        start = ANILIST.index("def localize_description_to_pt_br")
        end = ANILIST.index("    @staticmethod\n    def _header", start)
        block = ANILIST[start:end]
        self.assertIn("with self._translation_lock:", block)
        self.assertNotIn("with self._rate_lock:", block)
        self.assertIn("self._translation_lock = threading.RLock()", ANILIST)

    def test_google_sign_in_job_is_cancelled_with_main_activity(self):
        self.assertIn("googleSignInJob?.cancel()", MAIN_ACTIVITY)
        self.assertIn("googleSignInJob = null", MAIN_ACTIVITY)
        self.assertIn("val job = CoroutineScope(Dispatchers.Main).launch", MAIN_ACTIVITY)
        self.assertIn("googleSignInJob = job", MAIN_ACTIVITY)

    def test_navigation_controller_behavioral_back_flow(self):
        from core.navigation import NavigationController

        nav = NavigationController(clock=lambda: 100.0)
        nav.push("details")
        nav.push("settings")
        nav.push_settings("player")
        self.assertEqual("settings_inner", nav.back())
        self.assertEqual("previous", nav.back())
        self.assertEqual("previous", nav.back())
        self.assertEqual("prompt_exit", nav.back())


if __name__ == "__main__":
    unittest.main()
