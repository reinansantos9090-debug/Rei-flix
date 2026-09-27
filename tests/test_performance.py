import asyncio
import tempfile
import unittest
from pathlib import Path

from core.library_service import LibraryService
from core.library_store import LibraryStore


class TracingLibraryStore(LibraryStore):
    """SQLite statement tracer used only by performance regression tests."""

    def __init__(self, data_dir: str):
        self.sql_trace = []
        super().__init__(data_dir)

    def _conn(self):
        connection = super()._conn()
        connection.set_trace_callback(self.sql_trace.append)
        return connection

    def clear_trace(self):
        self.sql_trace.clear()

    def read_statements(self):
        return [
            statement
            for statement in self.sql_trace
            if statement.lstrip().upper().startswith(("SELECT", "WITH"))
        ]


class StorePaginationTests(unittest.TestCase):
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

    def test_catalog_page_id_only_mode_keeps_page_order_without_count_or_projection(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TracingLibraryStore(directory)
            self._seed(store, 30)
            baseline = store.catalog_page(page=1, page_size=7, sort="Nome A-Z")
            store.clear_trace()

            bounded = store.catalog_page(
                page=1,
                page_size=7,
                sort="Nome A-Z",
                include_total=False,
                project_items=False,
            )

            self.assertEqual(
                [item["id"] for item in baseline["items"]],
                bounded["ids"],
            )
            self.assertIsNone(bounded["total"])
            self.assertFalse(bounded["has_more"])
            self.assertEqual(1, len(store.read_statements()))

    def test_catalog_history_is_projected_without_a_second_grouped_query(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TracingLibraryStore(directory)
            self._seed(store, 2)
            path = "/library/title-001-01.mkv"
            store.save_progress(path, 12, 100, event_created_at=10)
            store.clear_trace()

            catalog = store.catalog(anime_ids=[2])

            self.assertEqual(12, catalog[0]["seasons"][0]["episodes"][0]["progress"])
            self.assertEqual(10.0, catalog[0]["last_played_at"])
            statements = store.read_statements()
            self.assertEqual(5, len(statements))
            self.assertFalse(any("MAX(last_played_at)" in statement for statement in statements))

    def test_home_sections_share_one_catalog_projection_and_keep_section_order(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TracingLibraryStore(directory)
            self._seed(store, 8)
            favorite = 1
            pinned = 2
            movie = 3
            special = 4
            store.toggle_favorite(favorite)
            store.toggle_pinned(pinned)
            with store._conn() as con:
                con.execute("UPDATE anime SET media_kind='movie' WHERE id=?", (movie,))
                con.execute(
                    "UPDATE episodes SET episode_type='special' WHERE anime_id=?",
                    (special,),
                )

            expected = {
                "recently_added": [
                    item["id"]
                    for item in store.catalog_page(page=0, page_size=3, sort="Mais recentes")["items"]
                ],
                "favorites": [
                    item["id"]
                    for item in store.catalog_page(page=0, page_size=3, state="Favoritos", sort="Mais recentes")["items"]
                ],
                "pinned": [
                    item["id"]
                    for item in store.catalog_page(page=0, page_size=3, state="Fixados", sort="Mais recentes")["items"]
                ],
                "series": [
                    item["id"]
                    for item in store.catalog_page(page=0, page_size=3, media_type="Série/Anime", sort="Mais recentes")["items"]
                ],
                "movies": [
                    item["id"]
                    for item in store.catalog_page(page=0, page_size=3, media_type="Filme", sort="Mais recentes")["items"]
                ],
                "specials": [
                    item["id"]
                    for item in store.catalog_page(page=0, page_size=3, media_type="Especial", sort="Mais recentes")["items"]
                ],
            }

            store.clear_trace()
            sections = store.home_sections(limit=3)

            for name, ids in expected.items():
                self.assertEqual(ids, [item["id"] for item in sections[name]])
            self.assertLessEqual(len(store.read_statements()), 14)

    def test_organize_summary_uses_one_episode_aggregate_query(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TracingLibraryStore(directory)
            self._seed(store, 6)
            store.save_progress("/library/title-001-01.mkv", 50, 100)
            store.save_progress("/library/title-002-01.mkv", 100, 100)
            store.toggle_favorite(3)
            store.toggle_pinned(4)
            with store._conn() as con:
                con.execute("UPDATE episodes SET missing=1 WHERE path=?", ("/library/title-005-01.mkv",))

            store.clear_trace()
            summary = store.organize_summary()

            counts = {item["name"]: item["count"] for item in summary["collections"]}
            self.assertEqual(6, counts["Todos"])
            self.assertEqual(1, counts["Favoritos"])
            self.assertEqual(1, counts["Fixados"])
            self.assertEqual(1, counts["Assistidos"])
            self.assertEqual(3, counts["Não iniciados"])
            self.assertLessEqual(len(store.read_statements()), 2)

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

    def test_next_episode_projection_is_sql_bounded_and_excludes_specials(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryStore(directory)
            active = store.upsert_anime("active", {"title": "Active", "genres": "[]"})
            active_path = "/library/active-10.mkv"
            store.upsert_episode(active, active_path, "Active 10", 1, 10)
            store.save_progress(active_path, 20, 100, event_created_at=10)

            queued = store.upsert_anime("queued", {"title": "Queued", "genres": "[]"})
            first = "/library/queued-01.mkv"
            second = "/library/queued-02.mkv"
            special = "/library/queued-sp01.mkv"
            store.upsert_episode(queued, first, "Queued 01", 1, 1)
            store.upsert_episode(queued, second, "Queued 02", 1, 2)
            store.upsert_episode(queued, special, "Queued SP01", 1, 1, episode_type="special")
            store.save_progress(first, 100, 100, event_created_at=11)

            result = store.next_episode_items(limit=10)
            by_title = {item["main_title"]: item for item in result}

            self.assertEqual(active_path, by_title["Active"]["next_episode"]["path"])
            self.assertEqual(second, by_title["Queued"]["next_episode"]["path"])
            self.assertNotIn(special, {item["next_episode"]["path"] for item in result})
            self.assertLessEqual(len(result), 2)

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


class ServiceAndSourceTests(unittest.TestCase):
    def test_service_home_batches_genre_enrichment_across_sections(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TracingLibraryStore(directory)
            self._seed(store, 8)
            service = LibraryService(store)
            store.clear_trace()

            service.media_center_home(limit=3)

            self.assertLessEqual(len(store.read_statements()), 15)

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
        self.assertIn("home_page_size = min(page_size, 48)", source)
        self.assertIn("page_size=home_page_size", source)
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

    def test_details_bounds_initial_episode_render_and_uses_batch_artwork(self):
        source = Path("views/details_view.py").read_text(encoding="utf-8")
        self.assertIn("visible_episode_count = [48]", source)
        self.assertIn("Carregar mais", source)
        self.assertIn("resolve_artwork_batch", source)
        self.assertIn("_prepare_episode_artwork", source)

    def test_home_defers_secondary_projections_and_filter_options(self):
        source = Path("views/home_view.py").read_text(encoding="utf-8")
        self.assertIn("await load_library_page(reset=True)", source)
        self.assertIn('run_tracked(refresh_home_sections, render_generation[0], label="home_sections")', source)
        self.assertIn('run_tracked(load_filter_options, label="filter_options")', source)
        startup = source[source.index("async def load_catalog():"):source.index("search.on_change = on_search")]
        self.assertNotIn("library.media_center_home", startup)
        self.assertNotIn("library.search_options", startup)

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
