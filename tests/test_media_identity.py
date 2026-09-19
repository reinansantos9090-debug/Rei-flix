import tempfile
import unittest

from core.media_identity import identity_from_document
from core.library_store import LibraryStore


class TestMediaIdentity(unittest.TestCase):
    def test_file_mediastore_and_primary_saf_share_identity(self):
        identity_file = identity_from_document(
            "file:///storage/emulated/0/Movies/Anime/E01.mkv",
            "/storage/emulated/0/Movies/Anime/E01.mkv",
        )
        identity_media = identity_from_document(
            "content://media/external/video/media/7",
            "Movies/Anime/E01.mkv",
            "external_primary",
        )
        identity_saf = identity_from_document(
            "content://com.android.externalstorage.documents/tree/primary%3AMovies/document/primary%3AMovies%2FAnime%2FE01.mkv",
            "Anime/E01.mkv",
            None,
            "content://com.android.externalstorage.documents/tree/primary%3AMovies",
        )
        self.assertEqual(identity_file, "shared:primary:movies/anime/e01.mkv")
        self.assertEqual(identity_file, identity_media)
        self.assertEqual(identity_file, identity_saf)

    def test_cloud_saf_relative_path_is_not_assumed_to_be_primary_storage(self):
        identity = identity_from_document(
            "content://com.google.android.apps.docs.storage/document/root%3Afoo",
            "Movies/Anime/E01.mkv",
            None,
            "content://com.google.android.apps.docs.storage/tree/root%3Afoo",
        )
        self.assertTrue(identity.startswith("uri:"))
        self.assertNotEqual(identity, "shared:primary:movies/anime/e01.mkv")

    def test_insert_from_second_source_reuses_existing_episode_and_preserves_progress(self):
        with tempfile.TemporaryDirectory() as data_dir:
            store = LibraryStore(data_dir)
            anime_id = store.upsert_anime("anime", {"title": "Anime"})
            identity = "shared:primary:movies/anime/e01.mkv"
            store.upsert_episode(
                anime_id, "file:///storage/emulated/0/Movies/Anime/E01.mkv",
                "E01.mkv", 1, 1, source_folder="broad-storage",
                media_identity=identity,
            )
            store.save_progress("file:///storage/emulated/0/Movies/Anime/E01.mkv", 120, 600)
            store.upsert_episode(
                anime_id, "content://media/external/video/media/7",
                "E01.mkv", 1, 1, source_folder="mediastore:external:video",
                media_identity=identity,
            )
            rows = store.catalog()[0]["seasons"][0]["episodes"]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["path"], "content://media/external/video/media/7")
            self.assertEqual(rows[0]["progress"], 120)
            self.assertEqual(rows[0]["source_folder"], "mediastore:external:video")

    def test_schema_adds_media_identity_and_index(self):
        with tempfile.TemporaryDirectory() as data_dir:
            store = LibraryStore(data_dir)
            self.assertIn("media_identity", {row["name"] for row in store._conn().execute("PRAGMA table_info(episodes)")})
            indexes = {row["name"] for row in store._conn().execute("PRAGMA index_list(episodes)")}
            self.assertIn("idx_episodes_media_identity", indexes)


if __name__ == "__main__":
    unittest.main()
