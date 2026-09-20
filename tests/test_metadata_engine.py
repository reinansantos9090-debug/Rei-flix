import tempfile
import time
import unittest
from unittest.mock import patch

from core.library_service import LibraryService
from core.library_store import LibraryStore


class ProfessionalMetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = LibraryStore(self.tmp.name)
        self.service = LibraryService(self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def _anime(self, title="Attack on Titan", lookup="attack on titan"):
        return self.store.upsert_anime(lookup, {"title": title, "genres": "[]"}, source="local")

    def test_schema_and_metadata_model_are_persistent(self):
        self._anime()
        row = self.store.anime_metadata("attack on titan")
        self.assertEqual(self.store.SCHEMA_VERSION, 19)
        self.assertEqual(row["metadata_source"], "local")
        self.assertEqual(row["metadata_status"], "unresolved")
        self.assertEqual(row["metadata_confidence"], "low")
        reopened = LibraryStore(self.tmp.name).anime_metadata("attack on titan")
        self.assertEqual(reopened["metadata_status"], "unresolved")

    def test_offline_library_ingest_never_calls_anilist(self):
        with patch.object(self.service.anilist, "search", side_effect=AssertionError("network used")),              patch.object(self.service.anilist, "by_id", side_effect=AssertionError("network used")):
            catalog = self.service.ingest_documents(
                "content://offline",
                [{"uri": "content://offline/1", "name": "Show S01E01.mkv", "size": 10, "modifiedAt": 1}],
                source_kind="saf",
            )
        self.assertEqual(len(catalog), 1)
        self.assertEqual(catalog[0]["seasons"][0]["episodes"][0]["number"], 1)
        self.assertEqual(catalog[0]["meta"]["metadata_status"], "unresolved")

    def test_anilist_refresh_normalizes_and_caches(self):
        self._anime()
        media = {
            "id": 16498,
            "title": {"english": "Attack on Titan", "romaji": "Shingeki no Kyojin", "native": "進撃の巨人"},
            "synonyms": ["AOT"],
            "description": "A safe synopsis.",
            "genres": ["Action", "Drama"],
            "seasonYear": 2013,
            "episodes": 25,
            "duration": 24,
            "averageScore": 86,
            "studios": {"nodes": [{"name": "WIT Studio"}]},
        }
        with patch.object(self.service.anilist, "search", return_value=[media]):
            refreshed = self.service.refresh_metadata("attack on titan", "Attack on Titan", force=True)
        self.assertEqual(refreshed["anilist_id"], 16498)
        self.assertEqual(refreshed["metadata_source"], "anilist")
        self.assertEqual(refreshed["metadata_status"], "available")
        self.assertEqual(refreshed["metadata_confidence"], "high")
        self.assertEqual(self.store.association("attack on titan"), 16498)
        self.assertEqual(self.store.anime_metadata("attack on titan")["english"], "Attack on Titan")

    def test_multiple_candidates_are_not_auto_associated(self):
        self._anime("Kanon", "kanon")
        candidates = [
            {"id": 1, "title": {"romaji": "Kanon"}, "synonyms": []},
            {"id": 2, "title": {"romaji": "Kanon"}, "synonyms": []},
        ]
        with patch.object(self.service.anilist, "search", return_value=candidates):
            result = self.service.refresh_metadata("kanon", "Kanon", force=True)
        self.assertIsNone(result.get("anilist_id"))
        self.assertEqual(self.store.association("kanon"), None)
        self.assertEqual(self.store.anime_metadata("kanon")["metadata_status"], "ambiguous")
        self.assertTrue(self.store.pending_matches())

    def test_low_confidence_candidate_stays_unresolved(self):
        self._anime("My Local Show", "my local show")
        candidates = [{"id": 77, "title": {"romaji": "Completely Different"}, "synonyms": []}]
        with patch.object(self.service.anilist, "search", return_value=candidates):
            result = self.service.refresh_metadata("my local show", "My Local Show", force=True)
        self.assertIsNone(result.get("anilist_id"))
        self.assertEqual(self.store.association("my local show"), None)
        self.assertEqual(result["metadata_status"], "unresolved")

    def test_offline_refresh_preserves_cached_metadata(self):
        self._anime()
        with self.store._conn() as con:
            con.execute(
                "UPDATE anime SET anilist_id=?,metadata_source='anilist',metadata_status='available',metadata_confidence='high',metadata_updated_at=? WHERE lookup_title=?",
                (16498, time.time() - 40 * 24 * 60 * 60, "attack on titan"),
            )
        with patch.object(self.service.anilist, "by_id", return_value=None):
            cached = self.service.refresh_metadata("attack on titan", "Attack on Titan", force=True)
        self.assertEqual(cached["anilist_id"], 16498)
        self.assertEqual(cached["metadata_status"], "stale")

    def test_manual_metadata_wins_over_anilist_refresh(self):
        self._anime()
        self.store.set_manual_metadata("attack on titan", {"title": "Meu Título", "description": "Minha descrição", "year": 9999})
        media = {
            "id": 16498,
            "title": {"english": "Attack on Titan", "romaji": "Shingeki no Kyojin", "native": "進撃の巨人"},
            "description": "Remote description",
            "genres": ["Action"],
            "seasonYear": 2013,
        }
        with patch.object(self.service.anilist, "by_id", return_value=media):
            refreshed = self.service.refresh_metadata("attack on titan", "Attack on Titan", force=True)
        self.assertEqual(refreshed["title"], "Meu Título")
        self.assertEqual(refreshed["description"], "Minha descrição")
        self.assertEqual(refreshed["year"], 9999)
        self.assertEqual(refreshed["genres"], "[\"Action\"]")
        self.assertEqual(refreshed["metadata_source"], "manual")

    def test_user_state_survives_metadata_merge(self):
        anime = self._anime()
        self.store.toggle_favorite(anime)
        self.store.toggle_pinned(anime)
        self.store.set_user_tags(anime, ["Favorito", "Rever"])
        self.store.set_personal_note(anime, "Minha nota")
        self.store.upsert_episode(anime, "content://x/1", "Show S01E01.mkv", 1, 1)
        self.store.save_progress("content://x/1", 45, 100)
        self.store.set_watched("content://x/1", True)
        media = {"id": 1, "title": {"english": "Attack on Titan", "romaji": "AOT"}, "genres": ["Action"]}
        with patch.object(self.service.anilist, "by_id", return_value=media):
            self.service.refresh_metadata("attack on titan", "Attack on Titan", force=True)
        row = self.store.catalog()[0]
        episode = row["seasons"][0]["episodes"][0]
        self.assertTrue(row["favorite"])
        self.assertTrue(row["is_pinned"])
        self.assertEqual(row["user_tags"], ["Favorito", "Rever"])
        self.assertEqual(row["personal_note"], "Minha nota")
        self.assertTrue(episode["watched"])
        self.assertEqual(episode["progress"], 100)

    def test_manual_identification_survives_metadata_refresh(self):
        anime = self._anime("Show", "show")
        self.store.upsert_episode(anime, "content://x/1", "Show S01E01.mkv", 1, 1)
        self.store.set_episode_identification("content://x/1", season=2, number=3, episode_type="special", title="Manual")
        media = {"id": 10, "title": {"english": "Show", "romaji": "Show"}, "genres": ["Action"]}
        with patch.object(self.service.anilist, "by_id", return_value=media):
            self.service.refresh_metadata("show", "Show", force=True)
        episode = self.store.physical_row("content://x/1")
        self.assertEqual((episode["season"], episode["number"], episode["episode_type"]), (2, 3, "special"))
        self.assertTrue(episode["manual_override"])

    def test_refresh_is_idempotent(self):
        self._anime()
        media = {"id": 16498, "title": {"english": "Attack on Titan", "romaji": "AOT"}, "genres": ["Action"]}
        with patch.object(self.service.anilist, "by_id", return_value=media) as by_id:
            first = self.service.refresh_metadata("attack on titan", "Attack on Titan", force=True)
            second = self.service.refresh_metadata("attack on titan", "Attack on Titan", force=True)
        self.assertEqual(first["anilist_id"], second["anilist_id"])
        self.assertEqual(self.store.association("attack on titan"), 16498)
        self.assertEqual(by_id.call_count, 2)

    def test_stale_state_is_read_only_and_does_not_fake_refresh(self):
        self._anime()
        with self.store._conn() as con:
            con.execute("UPDATE anime SET anilist_id=?,metadata_source='anilist',metadata_status='available',metadata_updated_at=? WHERE lookup_title=?",
                        (1, time.time() - 40 * 24 * 60 * 60, "attack on titan"))
        metadata = self.service._identify("attack on titan", "Attack on Titan", lambda _: None, allow_network=False)
        self.assertEqual(self.service.metadata_state(metadata), "stale")
        self.assertEqual(metadata["metadata_status"], "available")

    def test_movie_metadata_does_not_create_a_season(self):
        anime = self.store.upsert_anime("film", {"title": "Film", "media_kind": "movie", "genres": "[]"}, source="local")
        self.store.upsert_episode(anime, "content://film", "Film Movie.mkv", 0, None, episode_type="movie")
        catalog = self.store.catalog()[0]
        self.assertEqual(catalog["media_kind"], "movie")
        self.assertEqual(catalog["seasons"], [])
        self.assertEqual(len(catalog["media_files"]), 1)

    def test_unicode_metadata_round_trip(self):
        self._anime("進撃の巨人", "進撃の巨人")
        self.store.set_manual_metadata("進撃の巨人", {"title": "進撃の巨人", "description": "Descrição — 漢字"})
        reopened = LibraryStore(self.tmp.name).anime_metadata("進撃の巨人")
        self.assertEqual(reopened["title"], "進撃の巨人")
        self.assertIn("漢字", reopened["description"])

    def test_metadata_cache_hit_does_not_call_network(self):
        self._anime()
        with self.store._conn() as con:
            con.execute("UPDATE anime SET anilist_id=?,metadata_source='anilist',metadata_status='available',metadata_confidence='high',metadata_updated_at=? WHERE lookup_title=?",
                        (16498, time.time(), "attack on titan"))
        with patch.object(self.service.anilist, "by_id") as by_id:
            result = self.service.refresh_metadata("attack on titan", "Attack on Titan", force=False)
        by_id.assert_not_called()
        self.assertEqual(result["metadata_status"], "available")


if __name__ == "__main__":
    unittest.main()
