from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.anilist import AniListClient
from core.library_store import LibraryStore


ROOT = Path(__file__).resolve().parents[1]
DETAILS = (ROOT / "views" / "details_view.py").read_text(encoding="utf-8")
MAIN = (ROOT / "main.py").read_text(encoding="utf-8")
PLAYER = (ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/NativePlayerActivity.kt").read_text(encoding="utf-8")


class Prompt1RegressionTests(unittest.TestCase):
    def test_details_primary_action_does_not_autofocus_or_rebuild_for_thumbnails(self):
        self.assertNotIn("autofocus=bool(primary_target)", DETAILS)
        self.assertIn("palette_changed = (", DETAILS)
        self.assertIn("on_catalog_changed(refresh_details=False)", MAIN)
        self.assertIn("if navigation.current == \"details\" and not refresh_details:", MAIN)

    def test_next_accepts_file_uri_for_absolute_path_episode(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryStore(directory)
            anime = store.upsert_anime("demo", {"title": "Demo", "genres": "[]"})
            first = "/storage/emulated/0/Anime/Demo S01E01.mkv"
            second = "/storage/emulated/0/Anime/Demo S01E02.mkv"
            store.upsert_episode(anime, first, "Demo S01E01.mkv", 1, 1)
            store.upsert_episode(anime, second, "Demo S01E02.mkv", 1, 2)
            result = store.next_episode("file:///storage/emulated/0/Anime/Demo%20S01E01.mkv")
            self.assertIsNotNone(result)
            self.assertEqual(second, result["path"])

    def test_player_next_has_concurrency_guard_and_native_timeout(self):
        self.assertIn("player_transition_inflight", MAIN)
        self.assertIn("transition_in_progress", MAIN)
        self.assertIn("episodeChangeTimeout", PLAYER)
        self.assertIn("EPISODE_CHANGE_TIMEOUT", PLAYER)
        self.assertIn("handler.postDelayed(episodeChangeTimeout, 5_000L)", PLAYER)

    def test_anilist_ptbr_translation_is_cached(self):
        with tempfile.TemporaryDirectory() as directory:
            client = AniListClient(directory)
            source = "This is the story of a young girl who moves to a new town."
            with patch.object(client, "_translate_chunk_to_pt_br", return_value="Esta é a história de uma jovem que se muda para uma nova cidade.") as translate:
                first = client.localize_description_to_pt_br(source)
                second = client.localize_description_to_pt_br(source)
            self.assertEqual(first, second)
            self.assertEqual(1, translate.call_count)
            cache = Path(directory) / "anilist_description_ptbr.json"
            self.assertTrue(cache.is_file())

    def test_anilist_translation_failure_is_not_retried_immediately(self):
        with tempfile.TemporaryDirectory() as directory:
            client = AniListClient(directory)
            source = "This is the story of a young girl in a new town."
            with patch.object(client, "_translate_chunk_to_pt_br", return_value=None) as translate:
                self.assertEqual(source, client.localize_description_to_pt_br(source))
                self.assertEqual(source, client.localize_description_to_pt_br(source))
            self.assertEqual(1, translate.call_count)

    def test_metadata_localization_is_opt_in_and_uses_translated_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            client = AniListClient(directory)
            media = {
                "id": 7,
                "title": {"romaji": "Example", "english": "Example", "native": "Example"},
                "description": "This is the story of a young hero.",
                "genres": ["Action"],
                "coverImage": {},
            }
            with patch.object(client, "_translate_chunk_to_pt_br", return_value="Esta é a história de um jovem herói."):
                metadata = client.metadata_from_media("Example", media, localize_description=True)
            self.assertEqual("Esta é a história de um jovem herói.", metadata["description"])


if __name__ == "__main__":
    unittest.main()
