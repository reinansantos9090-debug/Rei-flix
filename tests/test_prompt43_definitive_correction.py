import ast
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Prompt43DefinitiveCorrectionTests(unittest.TestCase):
    def read(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def test_home_metadata_hydration_uses_the_canonical_artwork_resolver(self):
        source = self.read("views/home_view.py")
        start = source.index("async def hydrate_metadata_and_artwork")
        end = source.index("async def refresh_home_sections", start)
        block = source[start:end]
        self.assertIn("_queue_artwork_resolution(entity, item_id, 'poster', target)", block)
        self.assertNotIn("_apply_artwork(holder, width, height, cover_path)", block)
        self.assertNotIn("cover_cache)", block)

    def test_home_artwork_resolution_token_is_identity_scoped(self):
        source = self.read("views/home_view.py")
        self.assertIn("artwork_resolution_token = (", source)
        self.assertIn("entity,", source)
        self.assertIn("normalized_id,", source)
        self.assertIn("kind,", source)
        self.assertIn("artwork_token_counter[0]", source)
        batch = source[source.index("async def _flush_artwork_batch"):source.index("def schedule_artwork_batch_prefetch")]
        self.assertIn("snapshot_tokens.get(key) != artwork_request_tokens.get(key)", batch)
        self.assertIn("STALE_ARTWORK_IGNORED", batch)

    def test_generated_thumbnail_never_promotes_to_anime_poster(self):
        source = self.read("core/artwork.py")
        start = source.index("def register_generated_thumbnail")
        end = source.index("def set_manual", start)
        block = source[start:end]
        self.assertIn('entity_type="episode"', block)
        self.assertIn('artwork_type="episode_thumbnail"', block)
        self.assertIn('source="generated"', block)
        self.assertNotIn("artwork_type='poster'", block)
        self.assertNotIn("entity_type='anime'", block)
        self.assertNotIn("UPDATE anime SET cover_cache", block)

    def test_home_refresh_has_one_intent_entry_point_and_explicit_phases(self):
        source = self.read("main.py")
        self.assertIn("async def refresh_home_library", source)
        self.assertIn("request_home_refresh = refresh_home_library", source)
        self.assertIn("on_refresh_library=request_home_refresh", source)
        for phase in (
            "IDLE",
            "REQUESTED",
            "RUNNING",
            "CATALOG_UPDATING",
            "UI_COMMIT",
            "SUCCESS",
            "ERROR",
            "CANCELLED",
        ):
            self.assertIn(f'"{phase}"', source)
        self.assertIn("def _set_home_refresh_phase", source)
        self.assertIn("HOME_REFRESH_PHASE_CHANGED", source)

    def test_home_refresh_catalog_commit_is_bound_to_the_scan_request(self):
        source = self.read("main.py")
        self.assertIn("refresh_request_id=refresh_request_id", source)
        start = source.index("def on_catalog_changed")
        end = source.index("async def refresh_current_metadata", start) if "async def refresh_current_metadata" in source[start:] else len(source)
        block = source[start:end]
        self.assertIn("refresh_request_id is not None", block)
        self.assertIn("current_refresh_request_id == refresh_request_id", block)
        self.assertIn('_set_home_refresh_phase(', block)
        self.assertIn('"CATALOG_UPDATING"', block)

    def test_player_exit_classification_has_forensic_categories(self):
        source = self.read("android/app/src/main/kotlin/com/reiflix/reiflix_local/NativePlayerActivity.kt")
        for label in (
            "USER_BACK",
            "USER_BUTTON",
            "ANDROID_BACK",
            "ERROR_PANEL_BACK",
            "VALID_PLAYER_TRANSITION",
            "STALE_HANDOFF",
            "INVALID_HANDOFF",
            "PLAYER_ERROR",
            "ACTIVITY_LIFECYCLE",
            "SYSTEM_TASK",
            "PROCESS_DEATH",
            "UNKNOWN",
        ):
            self.assertIn(f'"{label}"', source)
        self.assertIn("PLAYER_FINISH_REQUEST", source)
        self.assertIn("PLAYER_EXIT_CLASSIFICATION=STALE_HANDOFF", source)

    def test_source_files_parse(self):
        ast.parse(self.read("main.py"), filename="main.py")
        ast.parse(self.read("views/home_view.py"), filename="views/home_view.py")


if __name__ == "__main__":
    unittest.main()
