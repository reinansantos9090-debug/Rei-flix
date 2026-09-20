import tempfile
import time
import unittest

from core.library_store import LibraryStore


class PlaybackConsumptionCycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = LibraryStore(self.tmp.name)
        self.anime = self.store.upsert_anime(
            "cycle",
            {"title": "Cycle", "genres": "[]", "media_kind": "series"},
        )

    def tearDown(self):
        self.tmp.cleanup()

    def episode(self, path, season, number, *, episode_type="regular", missing=False):
        self.store.upsert_episode(
            self.anime, path, f"{path.rsplit('/', 1)[-1]}.mkv",
            season, number, episode_type=episode_type,
        )
        if missing:
            self.store.mark_missing(path, True)
        return path

    def test_resume_completion_history_and_continue_are_one_durable_state(self):
        path = self.episode("content://cycle/1", 1, 1)
        self.store.save_progress(path, 47, 100)
        row = self.store.episode_by_path(path)
        self.assertEqual("in_progress", self.store.consumption_state(row))
        self.assertEqual(path, self.store.continue_watching()[0]["path"])

        self.store.save_progress(path, 90, 100)
        row = self.store.episode_by_path(path)
        self.assertTrue(row["watched"])
        self.assertEqual("watched", self.store.consumption_state(row))
        self.assertEqual([], self.store.continue_watching())
        self.assertEqual(path, self.store.playback_history()[0]["path"])
        self.assertIsNotNone(self.store.playback_history()[0]["last_played_at"])

    def test_progress_boundaries_and_zero_duration_are_safe(self):
        path = self.episode("content://cycle/boundary", 1, 2)
        for position, expected in ((0, "unwatched"), (89, "in_progress"),
                                   (90, "watched"), (99, "watched"), (100, "watched")):
            self.store.save_progress(path, position, 100)
            self.assertEqual(expected, self.store.consumption_state(self.store.episode_by_path(path)))

        self.store.save_progress(path, 25, 0)
        row = self.store.episode_by_path(path)
        self.assertEqual(25, row["progress"])
        self.assertEqual(0, row["duration"])
        self.assertTrue(row["watched"])

    def test_duplicate_and_out_of_order_native_events_do_not_regress_state(self):
        path = self.episode("content://cycle/order", 1, 3)
        t1 = int(time.time() * 1000)
        self.assertTrue(self.store.save_progress(path, 50, 100, event_created_at=t1))
        self.assertFalse(self.store.save_progress(path, 50, 100, event_created_at=t1))
        self.assertFalse(self.store.save_progress(path, 40, 100, event_created_at=t1 - 100))
        self.assertEqual(50, self.store.episode_by_path(path)["progress"])
        self.assertTrue(self.store.save_progress(path, 30, 100, event_created_at=t1 + 100))
        self.assertEqual(30, self.store.episode_by_path(path)["progress"])

    def test_next_episode_skips_missing_and_specials_and_crosses_season(self):
        e1 = self.episode("content://cycle/s1e12", 1, 12)
        self.episode("content://cycle/special", 1, 99, episode_type="ova")
        self.episode("content://cycle/missing", 1, 13, missing=True)
        e2 = self.episode("content://cycle/s2e1", 2, 1)
        self.assertEqual(e2, self.store.next_episode(e1)["path"])
        self.store.save_progress(e1, 90, 100)
        self.assertEqual(e2, self.store.playback_target(self.anime)["path"])

    def test_movie_has_progress_but_never_next_episode(self):
        movie = self.store.upsert_anime(
            "movie", {"title": "Movie", "genres": "[]", "media_kind": "movie"}
        )
        path = "content://movie/file"
        self.store.upsert_episode(movie, path, "Movie.mkv", 1, 1, episode_type="movie")
        self.store.save_progress(path, 50, 100)
        self.assertEqual(path, self.store.continue_watching()[0]["path"])
        self.assertIsNone(self.store.next_episode(path))
        self.store.save_progress(path, 90, 100)
        self.assertEqual([], [x for x in self.store.continue_watching() if x["path"] == path])
        self.assertEqual(path, self.store.playback_history()[0]["path"])

    def test_rescan_style_upsert_preserves_playback_state_for_same_identity(self):
        path = self.episode("content://cycle/move", 1, 4)
        self.store.save_progress(path, 47, 100)
        self.store.upsert_episode(
            self.anime, path, "renamed.mkv", 1, 4,
            media_identity="stable-cycle-4",
        )
        row = self.store.episode_by_path(path)
        self.assertEqual(47, row["progress"])

    def test_native_player_contract_uses_single_autoplay_preference(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        main = (root / "main.py").read_text(encoding="utf-8")
        bridge = (root / "core" / "android_bridge.py").read_text(encoding="utf-8")
        player = (root / "android" / "app" / "src" / "main" / "kotlin" / "com" / "reiflix" / "reiflix_local" / "NativePlayerActivity.kt").read_text(encoding="utf-8")
        self.assertIn('store.get_preference("autoplay_next", "true")', main)
        self.assertIn('autoplay=str(bool(autoplay)).lower()', bridge)
        self.assertIn('intent.getBooleanExtra("autoplay", true)', player)
        self.assertIn('"player_autoplay_changed"', player)
        self.assertNotIn('getSharedPreferences("reiflix_player"', player)


if __name__ == "__main__":
    unittest.main()
