import tempfile
import unittest
from core.library_store import LibraryStore
from core.library_service import LibraryService

class LibraryIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = LibraryStore(self.tmp.name)
        self.anime = self.store.upsert_anime("demo", {"title": "Demo", "genres": "[]"})
        self.store.upsert_episode(self.anime, "content://demo/1", "Demo E01.mkv", 1, 1)
        self.service = LibraryService(self.store)
    def tearDown(self): self.tmp.cleanup()

    def test_pin_note_and_reopen_are_private_and_durable(self):
        self.assertTrue(self.store.toggle_pinned(self.anime))
        self.assertEqual("assistir com Ana", self.store.set_personal_note(self.anime, "  assistir com Ana  "))
        reopened = LibraryStore(self.tmp.name).catalog()[0]
        self.assertTrue(reopened["is_pinned"])
        self.assertEqual("assistir com Ana", reopened["personal_note"])
        self.assertFalse(self.store.toggle_pinned(self.anime))
        self.assertIsNone(self.store.set_personal_note(self.anime, "   "))

    def test_note_limit_and_filters_are_safe(self):
        with self.assertRaises(ValueError): self.store.set_personal_note(self.anime, "x" * 2001)
        self.store.toggle_favorite(self.anime); self.store.toggle_pinned(self.anime)
        self.store.set_user_tags(self.anime, ["Prioridade"]); self.store.set_personal_note(self.anime, "nota")
        catalog = self.store.catalog()
        self.assertEqual(1, len(self.service.browse_catalog(catalog, state="Fixados", tag="Prioridade")))
        self.assertEqual(1, len(self.service.browse_catalog(catalog, state="Com nota")))
        self.assertEqual(0, len(self.service.browse_catalog(catalog, tag="Sem etiqueta")))


    def test_media_center_home_sections_group_entities_and_preserve_state(self):
        self.store.save_progress("content://demo/1", 40, 100)
        self.store.toggle_favorite(self.anime)
        self.store.toggle_pinned(self.anime)
        home = self.service.media_center_home()
        self.assertEqual(1, len(home["continue_watching"]))
        self.assertEqual(1, len(home["favorites"]))
        self.assertEqual(1, len(home["pinned"]))
        self.assertEqual(1, len(home["series"]))
        self.assertEqual(0, len(home["movies"]))
        self.assertEqual(1, len(home["next_episode"]))
        self.assertEqual("Demo", home["series"][0]["main_title"])
        self.assertEqual(1, home["series"][0]["active_count"])

    def test_media_center_home_empty_is_safe(self):
        empty_tmp = tempfile.TemporaryDirectory()
        try:
            empty_service = LibraryService(LibraryStore(empty_tmp.name))
            home = empty_service.media_center_home()
            self.assertTrue(all(not value for value in home.values()))
        finally:
            empty_tmp.cleanup()

    def test_statistics_and_last_scan_use_only_local_rows(self):
        self.store.save_progress("content://demo/1", 100, 100)
        self.store.toggle_pinned(self.anime); self.store.set_personal_note(self.anime, "n")
        stats = self.store.library_statistics()
        self.assertEqual(1, stats["animes"]); self.assertEqual(1, stats["episodes_watched"])
        self.assertEqual(1, stats["pinned"]); self.assertEqual(1, stats["notes"])
        self.assertIsNone(self.store.last_scan())

if __name__ == "__main__": unittest.main()
