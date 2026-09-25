import asyncio
import tempfile
import unittest
from pathlib import Path

from core.library_service import LibraryService
from core.library_store import LibraryStore


class Prompt9StorePaginationTests(unittest.TestCase):
    def _seed(self, store, count=40):
        for index in range(count):
            anime_id = store.upsert_anime(
                f"title-{index:03d}",
                {
                    "title": f"Title {index:03d}",
                    "genres": "[]",
                    "media_kind": "series",
                },
            )
            store.upsert_episode(
                anime_id,
                f"/library/title-{index:03d}-01.mkv",
                f"Title {index:03d} - 01.mkv",
                1,
                1,
                file_size=100 + index,
                modified_at=1000 + index,
            )

    def test_catalog_page_only_materializes_requested_page(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryStore(directory)
            self._seed(store, 40)

            first = store.catalog_page(page=0, page_size=12)
            second = store.catalog_page(page=1, page_size=12)

            self.assertEqual(first["total"], 40)
            self.assertEqual(len(first["items"]), 12)
            self.assertEqual(len(second["items"]), 12)
            self.assertTrue(first["has_more"])
            self.assertTrue(second["has_more"])
            self.assertTrue(set(item["id"] for item in first["items"]).isdisjoint(
                item["id"] for item in second["items"]
            ))

    def test_catalog_page_query_and_sort_are_applied_without_full_catalog_projection(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryStore(directory)
            self._seed(store, 30)

            result = store.catalog_page(
                page=0,
                page_size=12,
                query="Title 002",
                sort="Nome Z-A",
            )

            self.assertEqual(result["total"], 1)
            self.assertEqual(len(result["items"]), 1)
            self.assertEqual(result["items"][0]["main_title"], "Title 002")

    def test_paged_states_follow_consumption_completion_ratio(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryStore(directory)
            completed_path = '/library/completed.mkv'
            completed = store.upsert_anime('completed', {'title': 'Completed', 'genres': '[]'})
            store.upsert_episode(completed, completed_path, 'Completed', 1, 1)
            store.save_progress(completed_path, 95, 100)
            active_path = '/library/active.mkv'
            active = store.upsert_anime('active', {'title': 'Active', 'genres': '[]'})
            store.upsert_episode(active, active_path, 'Active', 1, 1)
            store.save_progress(active_path, 50, 100)
            result = store.catalog_page(page=0, page_size=12, state='Concluídos')
            active_result = store.catalog_page(page=0, page_size=12, state='Em andamento')
            self.assertEqual([item['main_title'] for item in result['items']], ['Completed'])
            self.assertEqual([item['main_title'] for item in active_result['items']], ['Active'])
    def test_catalog_anime_ids_is_a_bounded_projection(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryStore(directory)
            self._seed(store, 10)
            page = store.catalog_page(page=0, page_size=3)
            selected_id = page["items"][0]["id"]

            projected = store.catalog(anime_ids=[selected_id])

            self.assertEqual(len(projected), 1)
            self.assertEqual(projected[0]["id"], selected_id)

    def test_home_sections_remain_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryStore(directory)
            self._seed(store, 40)

            sections = store.home_sections(limit=8)

            self.assertLessEqual(len(sections["recently_added"]), 8)
            self.assertLessEqual(len(sections["favorites"]), 8)
            self.assertLessEqual(len(sections["series"]), 8)

    def test_continue_watching_uses_sql_bounded_resumable_projection(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryStore(directory)
            first = store.upsert_anime("first", {"title": "First", "genres": "[]"})
            second = store.upsert_anime("second", {"title": "Second", "genres": "[]"})
            for anime_id, prefix in ((first, "first"), (second, "second")):
                for number in range(1, 80):
                    path = f"/library/{prefix}-{number:03d}.mkv"
                    store.upsert_episode(
                        anime_id, path, path.rsplit("/", 1)[-1], 1, number,
                        file_size=1000 + number, modified_at=number,
                    )
            first_path = "/library/first-079.mkv"
            second_path = "/library/second-078.mkv"
            store.save_progress(first_path, 20, 100, event_created_at=1)
            store.save_progress(second_path, 40, 100, event_created_at=2)

            result = store.continue_watching(limit=1)

            self.assertEqual(1, len(result))
            self.assertEqual(second_path, result[0]["path"])
            self.assertLessEqual(len(store.continue_watching(limit=100)), 2)

    def test_performance_indexes_cover_default_sort_resume_and_episode_query(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryStore(directory)
            with store._conn() as con:
                indexes = {row["name"] for row in con.execute("PRAGMA index_list(anime)").fetchall()}
                episode_indexes = {row["name"] for row in con.execute("PRAGMA index_list(episodes)").fetchall()}
                self.assertIn("idx_anime_added_title", indexes)
                self.assertIn("idx_anime_favorite_added", indexes)
                self.assertIn("idx_episodes_resume", episode_indexes)
                self.assertIn("idx_episodes_season_number", episode_indexes)

                plan = con.execute(
                    "EXPLAIN QUERY PLAN SELECT id FROM anime "
                    "ORDER BY added_at DESC, title COLLATE NOCASE ASC, id DESC LIMIT 36"
                ).fetchall()
                plan_text = " ".join(str(row["detail"]) for row in plan)
                self.assertIn("idx_anime_added_title", plan_text)

    def test_home_sections_keep_next_episode_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryStore(directory)
            anime_id = store.upsert_anime("watch-next", {"title": "Watch Next", "genres": "[]"})
            first = "/library/watch-next-01.mkv"
            second = "/library/watch-next-02.mkv"
            store.upsert_episode(anime_id, first, "Watch Next 01", 1, 1)
            store.upsert_episode(anime_id, second, "Watch Next 02", 1, 2)
            store.save_progress(first, 100, 100)

            sections = store.home_sections(limit=4)

            self.assertEqual(1, len(sections["next_episode"]))
            self.assertEqual(second, sections["next_episode"][0]["next_episode"]["path"])


class Prompt9ServiceAndSourceTests(unittest.TestCase):
    def test_service_exposes_paged_catalog_and_bounded_home_sections(self):
        with tempfile.TemporaryDirectory() as directory:
            service = LibraryService(LibraryStore(directory))
            store = service.store
            anime_id = store.upsert_anime("naruto", {"title": "Naruto", "genres": "[]"})
            store.upsert_episode(anime_id, "/library/naruto-01.mkv", "Naruto 01", 1, 1)

            result = service.browse_catalog_page(page=0, page_size=12)
            home = service.media_center_home(limit=4)

            self.assertEqual(result["total"], 1)
            self.assertEqual(len(result["items"]), 1)
            self.assertLessEqual(len(home["recently_added"]), 4)

    def test_home_uses_page_api_and_does_not_load_full_catalog(self):
        source = Path("views/home_view.py").read_text(encoding="utf-8")

        self.assertIn("browse_catalog_page", source)
        self.assertIn('page_size = settings.get("library.page_size")', source)
        self.assertIn("page_size=page_size", source)
        self.assertIn("on_scroll=on_home_scroll", source)
        self.assertIn("search_generation", source)
        self.assertIn("if token != search_generation[0]:", source)
        self.assertNotIn("library.catalog(", source)

    def test_organize_uses_page_api_and_does_not_load_full_catalog(self):
        source = Path("views/organize_view.py").read_text(encoding="utf-8")

        self.assertIn("browse_catalog_page", source)
        self.assertIn("page_size=36", source)
        self.assertIn("on_collection_scroll", source)
        self.assertIn("search_generation", source)
        self.assertIn("organize_summary_bounded", source)
        self.assertNotIn("library.catalog", source)
        self.assertNotIn("page.run_task(lambda:", source)

    def test_home_library_tree_is_page_bounded_and_mailbox_has_idle_backoff(self):
        home = Path("views/home_view.py").read_text(encoding="utf-8")
        main = Path("main.py").read_text(encoding="utf-8")
        self.assertIn("page_size = settings.get(\"library.page_size\")", home)
        self.assertIn("catalog.extend(fresh_items)", home)
        self.assertIn("if remaining < 800", home)
        self.assertIn("poll_interval = 0.2 if events else min(1.0, poll_interval * 1.5)", main)
        self.assertNotIn("while True:\n            bridge.drain()", main)

    def test_async_stale_generation_contracts_are_present(self):
        home = Path("views/home_view.py").read_text(encoding="utf-8")
        organize = Path("views/organize_view.py").read_text(encoding="utf-8")

        self.assertIn("render_generation", home)
        self.assertIn("if token != render_generation[0]:", home)
        self.assertIn("search_generation", organize)
        self.assertIn("if token != search_generation[0]:", organize)


if __name__ == "__main__":
    unittest.main()
