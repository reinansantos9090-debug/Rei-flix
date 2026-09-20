import tempfile
import unittest

from core.library_service import LibraryService
from core.library_store import LibraryStore


class ProfessionalIndexerTests(unittest.TestCase):
    def _service(self, directory):
        store = LibraryStore(directory)
        service = LibraryService(store)
        service._identify = lambda lookup, display, on_status: {"title": display, "genres": "[]"}
        return store, service

    def test_same_native_document_twice_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            store, service = self._service(d)
            doc = {
                "uri": "content://media/1",
                "name": "Show S01E01.mkv",
                "relativePath": "Show/Show S01E01.mkv",
                "mimeType": "video/x-matroska",
                "size": 100,
                "modifiedAt": 10,
                "volumeId": "external_primary",
            }
            service.ingest_documents("mediastore:external:video", [doc], source_kind="mediastore")
            service.ingest_documents("mediastore:external:video", [doc], source_kind="mediastore")
            rows = store.catalog()[0]["seasons"][0]["episodes"]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["path"], doc["uri"])
            self.assertGreaterEqual(store.last_scan()["unchanged_files"], 1)

    def test_same_name_on_different_volumes_is_not_merged(self):
        with tempfile.TemporaryDirectory() as d:
            store, service = self._service(d)
            docs = [
                {
                    "uri": "content://media/primary/1",
                    "name": "Show S01E01.mkv",
                    "relativePath": "Show/Show S01E01.mkv",
                    "size": 100,
                    "modifiedAt": 10,
                    "volumeId": "external_primary",
                },
                {
                    "uri": "content://media/sd/1",
                    "name": "Show S01E01.mkv",
                    "relativePath": "Show/Show S01E01.mkv",
                    "size": 100,
                    "modifiedAt": 10,
                    "volumeId": "ABCD-1234",
                },
            ]
            service.ingest_documents("mediastore:external:video", docs, source_kind="mediastore")
            episodes = store.catalog()[0]["seasons"][0]["episodes"]
            self.assertEqual(len(episodes), 2)
            self.assertNotEqual(episodes[0]["volume_id"], episodes[1]["volume_id"])

    def test_partial_scan_does_not_mark_unseen_rows_missing(self):
        with tempfile.TemporaryDirectory() as d:
            store, service = self._service(d)
            docs = [
                {"uri": "content://tree/1", "name": "Show S01E01.mkv", "relativePath": "Show/S01E01.mkv", "size": 100, "modifiedAt": 10},
                {"uri": "content://tree/2", "name": "Show S01E02.mkv", "relativePath": "Show/S01E02.mkv", "size": 100, "modifiedAt": 10},
            ]
            service.ingest_documents("content://tree/show", docs)
            service.ingest_documents(
                "content://tree/show",
                [docs[0]],
                scan_errors=["subpasta inacessível"],
            )
            rows = store.catalog()[0]["seasons"][0]["episodes"]
            self.assertEqual({row["path"] for row in rows}, {"content://tree/1", "content://tree/2"})
            self.assertFalse(any(row["missing"] for row in rows))
            self.assertEqual(store.last_scan()["status"], "partial")

    def test_complete_scan_reconciles_only_that_source(self):
        with tempfile.TemporaryDirectory() as d:
            store, service = self._service(d)
            first = {"uri": "content://tree/1", "name": "Show S01E01.mkv", "relativePath": "Show/S01E01.mkv", "size": 100, "modifiedAt": 10}
            second = {"uri": "content://tree/2", "name": "Show S01E02.mkv", "relativePath": "Show/S01E02.mkv", "size": 100, "modifiedAt": 10}
            other = {"uri": "content://other/1", "name": "Other S01E01.mkv", "relativePath": "Other/S01E01.mkv", "size": 100, "modifiedAt": 10}
            service.ingest_documents("content://tree/show", [first, second])
            service.ingest_documents("content://tree/other", [other])
            service.ingest_documents("content://tree/show", [first])
            rows = {row["path"]: row for anime in store.catalog() for season in anime["seasons"] for row in season["episodes"]}
            self.assertTrue(rows["content://tree/2"]["missing"])
            self.assertFalse(rows["content://other/1"]["missing"])

    def test_modified_file_updates_physical_state_without_destroying_user_state(self):
        with tempfile.TemporaryDirectory() as d:
            store, service = self._service(d)
            doc = {"uri": "file:///library/Show S01E01.mkv", "name": "Show S01E01.mkv", "relativePath": "Show/Show S01E01.mkv", "size": 100, "modifiedAt": 10}
            service.ingest_documents("/library", [doc], source_kind="broad_storage")
            episode = store.catalog()[0]["seasons"][0]["episodes"][0]
            store.save_progress(50 and doc["uri"], 50, 100)
            store.toggle_favorite(store.catalog()[0]["id"])
            store.set_user_tags(store.catalog()[0]["id"], ["keep"])
            store.set_episode_identification(doc["uri"], season=2, number=17)
            changed = dict(doc)
            changed["size"] = 200
            changed["modifiedAt"] = 20
            service.ingest_documents("/library", [changed], source_kind="broad_storage")
            episode = store.catalog()[0]["seasons"][0]["episodes"][0]
            anime = store.catalog()[0]
            self.assertEqual(episode["file_size"], 200)
            self.assertEqual(episode["season"], 2)
            self.assertEqual(episode["number"], 17)
            self.assertEqual(episode["progress"], 50)
            self.assertTrue(anime["favorite"])
            self.assertEqual(anime["user_tags"], ["keep"])

    def test_unknown_file_is_not_forced_into_episode_one(self):
        with tempfile.TemporaryDirectory() as d:
            store, service = self._service(d)
            doc = {"uri": "content://tree/unknown", "name": "video_final.mkv", "relativePath": "Unknown/video_final.mkv", "size": 100, "modifiedAt": 10}
            service.ingest_documents("content://tree/unknown", [doc])
            episode = store.catalog()[0]["seasons"][0]["episodes"][0]
            self.assertIsNone(episode["number"])
            self.assertEqual(store.catalog()[0]["media_kind"], "unknown")

    def test_scan_ids_are_durable_and_distinct(self):
        with tempfile.TemporaryDirectory() as d:
            store, service = self._service(d)
            doc = {"uri": "content://tree/1", "name": "Show S01E01.mkv", "relativePath": "Show/S01E01.mkv", "size": 100, "modifiedAt": 10}
            service.ingest_documents("content://tree/show", [doc])
            first = store.last_scan()["scan_id"]
            service.ingest_documents("content://tree/show", [doc])
            second = store.last_scan()["scan_id"]
            self.assertTrue(first)
            self.assertTrue(second)
            self.assertNotEqual(first, second)

    def test_schema_18_adds_physical_and_scan_fields(self):
        with tempfile.TemporaryDirectory() as d:
            store = LibraryStore(d)
            with store._conn() as con:
                episode_columns = {row[1] for row in con.execute("PRAGMA table_info(episodes)")}
                scan_columns = {row[1] for row in con.execute("PRAGMA table_info(scan_runs)")}
            self.assertTrue({"relative_path", "volume_id", "volume_uuid"} <= episode_columns)
            self.assertTrue({"scan_id", "scope_kind", "scope_ref", "new_files", "unchanged_files"} <= scan_columns)


if __name__ == "__main__":
    unittest.main()
