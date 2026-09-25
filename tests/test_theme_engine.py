import tempfile
import unittest
from pathlib import Path

from core.library_store import LibraryStore
from core.settings import SettingsStore
from core.ui import (
    DARK_THEME,
    LIGHT_THEME,
    ThemeTokens,
    effective_theme_mode,
    normalize_theme_mode,
    theme_tokens,
)


ROOT = Path(__file__).resolve().parents[1]


class ThemeEngineTests(unittest.TestCase):
    def test_normalize_theme_mode_has_safe_fallback(self):
        self.assertEqual(normalize_theme_mode("dark"), "dark")
        self.assertEqual(normalize_theme_mode("light"), "light")
        self.assertEqual(normalize_theme_mode("system"), "system")
        self.assertEqual(normalize_theme_mode("invalid"), "system")
        self.assertEqual(normalize_theme_mode(None), "system")

    def test_system_resolves_from_platform_brightness(self):
        self.assertEqual(effective_theme_mode("system", "dark"), "dark")
        self.assertEqual(effective_theme_mode("system", "light"), "light")
        self.assertEqual(effective_theme_mode("system", None), "light")
        self.assertEqual(effective_theme_mode("dark", "light"), "dark")
        self.assertEqual(effective_theme_mode("light", "dark"), "light")

    def test_dark_and_light_have_complete_shared_tokens(self):
        required = {
            "background",
            "surface",
            "surface_variant",
            "surface_raised",
            "text",
            "text_muted",
            "text_on_accent",
            "text_on_overlay",
            "primary",
            "secondary",
            "border",
            "divider",
            "error",
            "success",
            "warning",
            "overlay",
            "favorite",
            "mode",
        }
        for theme in (DARK_THEME, LIGHT_THEME):
            self.assertIsInstance(theme, ThemeTokens)
            self.assertEqual(required, set(theme.__dataclass_fields__))
            for field in required:
                self.assertTrue(getattr(theme, field))

        self.assertNotEqual(DARK_THEME.background, LIGHT_THEME.background)
        self.assertNotEqual(DARK_THEME.surface, LIGHT_THEME.surface)
        self.assertNotEqual(DARK_THEME.text, LIGHT_THEME.text)
        self.assertNotEqual(DARK_THEME.text_muted, LIGHT_THEME.text_muted)

    def test_theme_tokens_resolve_without_parallel_theme_store(self):
        self.assertIs(theme_tokens("dark"), DARK_THEME)
        self.assertIs(theme_tokens("light"), LIGHT_THEME)
        self.assertIs(theme_tokens("system", "dark"), DARK_THEME)
        self.assertIs(theme_tokens("system", "light"), LIGHT_THEME)

    def test_theme_preference_persists_through_existing_settings_store(self):
        with tempfile.TemporaryDirectory() as root:
            store = LibraryStore(root)
            settings = SettingsStore(store)

            settings.set("appearance.theme", "light")
            self.assertEqual(SettingsStore(store).get("appearance.theme"), "light")

            settings.set("appearance.theme", "dark")
            self.assertEqual(SettingsStore(store).get("appearance.theme"), "dark")

            settings.set("appearance.theme", "system")
            self.assertEqual(SettingsStore(store).get("appearance.theme"), "system")

    def test_corrupt_theme_preference_falls_back_without_touching_other_settings(self):
        with tempfile.TemporaryDirectory() as root:
            store = LibraryStore(root)
            store.set_preference("appearance.theme", "definitely-invalid")
            store.set_preference("player.resume", "false")

            settings = SettingsStore(store)
            self.assertEqual(settings.get("appearance.theme"), "dark")
            self.assertFalse(settings.get("player.resume"))

    def test_views_do_not_keep_the_old_competing_dark_palette(self):
        view_paths = (
            ROOT / "views/home_view.py",
            ROOT / "views/details_view.py",
            ROOT / "views/organize_view.py",
            ROOT / "views/settings_view.py",
            ROOT / "views/recovery_view.py",
        )
        legacy_palette = (
            "#16151F",
            "#252331",
            "#2D2A3B",
            "#F7F5FA",
            "#AAA7B6",
            "#39364B",
        )
        for path in view_paths:
            source = path.read_text(encoding="utf-8")
            self.assertIn("activate_theme_for_page", source, path.name)
            for color in legacy_palette:
                self.assertNotIn(color, source, f"{path.name} retains {color}")

    def test_main_owns_runtime_theme_apply_and_system_brightness_hook(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("apply_page_theme(page, settings.get(\"appearance.theme\"))", source)
        self.assertIn('if setting_key == "appearance.theme":', source)
        self.assertIn("page.on_platform_brightness_change", source)
        self.assertNotIn("page.theme_mode =", source)

    def test_settings_has_explicit_three_mode_selection_and_selection_indicator(self):
        source = (ROOT / "views/settings_view.py").read_text(encoding="utf-8")
        for label in ("Sistema", "Claro", "Escuro"):
            self.assertIn(label, source)
        self.assertIn('ft.FilledButton(button_label, on_click=handle)', source)
        self.assertIn('ft.OutlinedButton(button_label, on_click=handle)', source)
        self.assertIn('settings.get("appearance.theme") == mode', source)

    def test_theme_change_does_not_route_through_storage_or_native_player(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        start = source.index("    def apply_settings_runtime")
        end = source.index("    async def remove_folder", start)
        block = source[start:end]
        self.assertNotIn("refresh_library(", block)
        self.assertNotIn("bridge.", block)
        self.assertNotIn("ScanCoordinator", block)
        self.assertNotIn("NativeMailbox", block)
        theme_block = block[:block.index('        if setting_key.startswith(("appearance.", "library.")):')]
        self.assertNotIn("library.configure_settings(settings)", theme_block)


if __name__ == "__main__":
    unittest.main()
