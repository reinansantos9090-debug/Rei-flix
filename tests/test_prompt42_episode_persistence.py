import tempfile
import unittest

from core.library_store import LibraryStore


class Prompt42EpisodePersistenceTests(unittest.TestCase):
    def _episodes(self, store, anime_id):
        rows = []
        for number in range(1, 6):
            path = f"content://prompt42/episode{number}"
            episode_id = store.upsert_episode(
                anime_id,
                path,
                f"Show S01E{number:02d}.mkv",
                1,
                number,
                mime_type="video/mp4",
                file_size=1000 + number,
                modified_at=1000 + number,
                source_folder="prompt42-source",
                media_identity=f"prompt42:episode:{number}",
                episode_type="regular",
                identification_source="sxxexx",
                identification_confidence="high",
            )
            rows.append(store.physical_row(path))
            self.assertEqual(episode_id, rows[-1]["id"])
        return rows

    def test_five_episode_restart_keeps_canonical_collection_continue_and_target(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryStore(directory)
            anime_id = store.upsert_anime(
                "prompt42-show",
                {"title": "Prompt 42 Show", "media_kind": "series", "genres": "[]"},
                source="local",
            )
            before = self._episodes(store, anime_id)
            first = before[0]
            self.assertTrue(
                store.save_progress(
                    first["path"],
                    37,
                    100,
                    episode_id=first["id"],
                    event_created_at=1000,
                )
            )

            reopened = LibraryStore(directory)
            group = reopened.catalog(anime_ids=[anime_id])[0]
            episodes = [
                episode
                for season in group["seasons"]
                for episode in season.get("episodes", [])
            ]
            self.assertEqual([row["id"] for row in before], [row["id"] for row in episodes])
            self.assertEqual([1, 2, 3, 4, 5], [int(episode["number"]) for episode in episodes])

            continuing = reopened.continue_watching()
            self.assertEqual([first["id"]], [item["id"] for item in continuing])
            self.assertEqual(37, continuing[0]["progress"])

            target = reopened.playback_target(anime_id)
            self.assertIsNotNone(target)
            self.assertEqual(first["id"], target["id"])
            self.assertEqual(37, target["progress"])

    def test_duplicate_identity_reconciliation_keeps_stronger_semantic_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryStore(directory)
            first_anime = store.upsert_anime(
                "prompt42-dup-a",
                {"title": "Prompt 42 Duplicate A", "media_kind": "series", "genres": "[]"},
                source="local",
            )
            second_anime = store.upsert_anime(
                "prompt42-dup-b",
                {"title": "Prompt 42 Duplicate B", "media_kind": "series", "genres": "[]"},
                source="local",
            )
            stable = "prompt42:duplicate"
            old_id = store.upsert_episode(
                first_anime,
                "content://prompt42/old",
                "Show S01E01.mkv",
                1,
                1,
                source_folder="prompt42-source",
                media_identity=stable,
                episode_type="regular",
                identification_source="sxxexx",
                identification_confidence="high",
                absolute_number=1,
            )
            store.save_progress("content://prompt42/old", 37, 100, episode_id=old_id, event_created_at=1000)
            second_id = store.upsert_episode(
                second_anime,
                "content://prompt42/new",
                "Show 07.mkv",
                2,
                7,
                source_folder="prompt42-source",
                media_identity=stable,
                episode_type="regular",
                identification_source="numeric_suffix",
                identification_confidence="medium",
                absolute_number=7,
            )
            self.assertEqual(old_id, second_id)
            row = store.episode_by_id(old_id)
            self.assertEqual(first_anime, row["anime_id"])
            self.assertEqual(1, row["season"])
            self.assertEqual(1, row["number"])
            self.assertEqual(1, row["absolute_number"])
            self.assertEqual(37, row["progress"])

    def test_lower_confidence_apply_identification_cannot_undo_canonical_state(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryStore(directory)
            anime_id = store.upsert_anime(
                "prompt42-apply",
                {"title": "Prompt 42 Apply", "media_kind": "series", "genres": "[]"},
                source="local",
            )
            path = "content://prompt42/apply"
            episode_id = store.upsert_episode(
                anime_id,
                path,
                "Apply S01E01.mkv",
                1,
                1,
                source_folder="prompt42-source",
                media_identity="prompt42:apply",
                episode_type="regular",
                identification_source="sxxexx",
                identification_confidence="high",
            )
            store.apply_episode_identification(
                path,
                absolute_number=None,
                relative_path="Apply S01E01.mkv",
                episode_type="special",
                episode_title="wrong weaker classification",
                identification_source="legacy",
                identification_confidence="low",
            )
            row = store.episode_by_id(episode_id)
            self.assertEqual(1, row["season"])
            self.assertEqual(1, row["number"])
            self.assertEqual("regular", row["episode_type"])
            self.assertEqual("high", row["identification_confidence"])

    def test_lower_confidence_rescan_does_not_reclassify_existing_stable_episode(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryStore(directory)
            anime_id = store.upsert_anime(
                "prompt42-stable",
                {"title": "Prompt 42 Stable", "media_kind": "series", "genres": "[]"},
                source="local",
            )
            path = "content://prompt42/stable"
            episode_id = store.upsert_episode(
                anime_id,
                path,
                "Stable S01E01.mkv",
                1,
                1,
                source_folder="prompt42-source",
                media_identity="prompt42:stable",
                episode_type="regular",
                identification_source="sxxexx",
                identification_confidence="high",
            )
            self.assertTrue(
                store.save_progress(
                    path,
                    37,
                    100,
                    episode_id=episode_id,
                    event_created_at=1000,
                )
            )

            store.upsert_episode(
                anime_id,
                path,
                "Stable S01E01.mkv",
                2,
                7,
                source_folder="prompt42-source",
                media_identity="prompt42:stable",
                episode_type="regular",
                identification_source="numeric_suffix",
                identification_confidence="medium",
            )

            row = store.episode_by_id(episode_id)
            self.assertIsNotNone(row)
            self.assertEqual(episode_id, row["id"])
            self.assertEqual(1, row["season"])
            self.assertEqual(1, row["number"])
            self.assertEqual(37, row["progress"])
            self.assertEqual("regular", row["episode_type"])


if __name__ == "__main__":
    unittest.main()
