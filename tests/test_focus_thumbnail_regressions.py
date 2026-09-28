"""Regression contracts for focus stability and incremental thumbnail delivery."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
HOME = (ROOT / "views" / "home_view.py").read_text(encoding="utf-8")
SETTINGS = (ROOT / "views" / "settings_view.py").read_text(encoding="utf-8")
UI = (ROOT / "core" / "ui.py").read_text(encoding="utf-8")
MAIN = (ROOT / "main.py").read_text(encoding="utf-8")
DETAILS = (ROOT / "views" / "details_view.py").read_text(encoding="utf-8")


class FocusAndThumbnailRegressionTests(unittest.TestCase):
    def test_home_has_no_automatic_autofocus(self):
        self.assertNotIn("autofocus", HOME)

    def test_settings_categories_have_no_automatic_autofocus(self):
        category_start = SETTINGS.index("def build_category_tile")
        category_end = SETTINGS.index("def render_settings", category_start)
        self.assertNotIn("autofocus", SETTINGS[category_start:category_end])

    def test_shared_focus_border_is_neutral_and_geometry_stable(self):
        style_start = UI.index("def focus_button_style")
        style_end = UI.index("def empty_state", style_start)
        style = UI[style_start:style_end]
        self.assertIn("ft.ControlState.DEFAULT: ft.BorderSide(1, palette.border)", style)
        self.assertIn("ft.ControlState.FOCUSED: ft.BorderSide(1, palette.border)", style)
        self.assertNotIn("FOCUSED: ft.BorderSide(2, palette.primary)", style)
        self.assertNotIn("FOCUSED: ft.BorderSide(2,", DETAILS)

    def test_thumbnail_ready_dispatches_incremental_home_update_not_catalog_refresh(self):
        start = MAIN.index("elif event_type == 'thumbnail_ready':")
        end = MAIN.index("elif event_type == 'thumbnail_error':", start)
        handler = MAIN[start:end]
        self.assertIn("home_state.get('_update_thumbnail')", handler)
        self.assertIn("update_thumbnail(uri, thumbnail_path)", handler)
        self.assertNotIn("on_catalog_changed(", handler)

    def test_incremental_thumbnail_update_preserves_grid_and_uses_existing_bindings(self):
        start = HOME.index("def update_thumbnail_in_place")
        end = HOME.index("async def refresh_from_catalog", start)
        update = HOME[start:end]
        self.assertIn("artwork_bindings.get", update)
        self.assertIn("holder.content = ft.Image", update)
        self.assertIn("schedule_artwork_ui_update()", update)
        self.assertNotIn("load_library_page", update)
        self.assertNotIn("grid.controls.clear", update)
        self.assertNotIn("browse_catalog_page", update)

    def test_thumbnail_callback_is_exposed_without_rebuild_path(self):
        self.assertIn("view_state['_update_thumbnail'] = update_thumbnail_in_place", HOME)
        self.assertIn("Thumbnail persistence has already completed", HOME)

    def test_existing_thumbnail_generation_guard_remains(self):
        start = MAIN.index("elif event_type == 'thumbnail_ready':")
        end = MAIN.index("elif event_type == 'thumbnail_error':", start)
        handler = MAIN[start:end]
        self.assertIn("thumbnail_key = (uri, size, modified_at)", handler)
        self.assertIn("thumbnail_key != latest_key", handler)
        self.assertIn("THUMBNAIL_STALE", handler)

    def test_multiple_thumbnail_updates_are_idempotent(self):
        start = HOME.index("def update_thumbnail_in_place")
        end = HOME.index("async def refresh_from_catalog", start)
        update = HOME[start:end]
        self.assertIn("if not affected_ids:", update)
        self.assertIn("return bool(updated)", update)
        self.assertNotIn("_refresh_from_catalog", update)


    def test_thumbnail_generation_maps_remain_bounded_while_latest_version_wins(self):
        request_start = MAIN.index("def request_missing_thumbnail")
        request_end = MAIN.index("def storage_state", request_start)
        request = MAIN[request_start:request_end]
        self.assertIn("existing_latest != key", request)
        self.assertIn("thumbnail_requests.discard(existing_latest)", request)
        self.assertIn("thumbnail_latest_key_by_uri[path_ref] = key", request)
        self.assertIn("if len(thumbnail_latest_at) > 1024:", MAIN)
        self.assertIn("if len(thumbnail_completed_request_by_key) > 1024:", MAIN)


if __name__ == "__main__":
    unittest.main()
