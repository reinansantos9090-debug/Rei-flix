import tempfile
import unittest

from core.library_store import LibraryStore
from core.settings import SettingsStore, SettingsValidationError


class SettingsStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = LibraryStore(self.tmp.name)
        self.settings = SettingsStore(self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def test_defaults_and_persistence(self):
        self.assertEqual(self.settings.get("player.default_speed"), 1.0)
        self.assertTrue(self.settings.get("player.resume"))
        self.settings.set("player.default_speed", 1.5)
        self.assertEqual(SettingsStore(self.store).get("player.default_speed"), 1.5)

    def test_boolean_and_enum_types(self):
        self.settings.set("gestures.volume", True)
        self.assertIs(self.settings.get("gestures.volume"), True)
        self.settings.set("player.aspect_ratio", "zoom")
        self.assertEqual(self.settings.get("player.aspect_ratio"), "zoom")

    def test_invalid_values_rejected(self):
        with self.assertRaises(SettingsValidationError):
            self.settings.set("player.default_speed", 9.0)
        with self.assertRaises(SettingsValidationError):
            self.settings.set("player.auto_hide_seconds", -1)
        with self.assertRaises(SettingsValidationError):
            self.settings.set("player.aspect_ratio", "stretch")

    def test_reset_category_preserves_library(self):
        self.settings.set("player.default_speed", 2.0)
        self.settings.set("appearance.theme", "light")
        self.settings.reset_category("player")
        self.assertEqual(self.settings.get("player.default_speed"), 1.0)
        self.assertEqual(self.settings.get("appearance.theme"), "light")

    def test_legacy_preferences_are_migrated(self):
        self.store.set_preference("resume_playback", "false")
        migrated = SettingsStore(self.store)
        self.assertFalse(migrated.get("player.resume"))

    def test_single_corrupt_key_falls_back_only_for_that_key(self):
        self.store.set_preference("player.default_speed", "not-a-speed")
        self.store.set_preference("player.resume", "false")
        settings = SettingsStore(self.store)
        self.assertEqual(settings.get("player.default_speed"), 1.0)
        self.assertFalse(settings.get("player.resume"))


if __name__ == "__main__":
    unittest.main()
