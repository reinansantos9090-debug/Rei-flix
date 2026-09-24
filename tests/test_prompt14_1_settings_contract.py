import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTINGS_VIEW = ROOT / "views/settings_view.py"
SETTINGS = ROOT / "core/settings.py"
MAIN = ROOT / "main.py"
BRIDGE = ROOT / "core/android_bridge.py"
MAIN_ACTIVITY = ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt"
PLAYER = ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/NativePlayerActivity.kt"
HOME = ROOT / "views/home_view.py"


class Prompt141SettingsContractTests(unittest.TestCase):
    def read(self, path):
        return path.read_text(encoding="utf-8")

    def test_settings_export_import_contract_exists(self):
        settings = self.read(SETTINGS)
        view = self.read(SETTINGS_VIEW)
        self.assertIn('EXPORT_FORMAT = "reiflix-settings"', settings)
        self.assertIn("def export_json", settings)
        self.assertIn("def import_json", settings)
        self.assertIn("schema_version", settings)
        self.assertIn("Exportar configurações", view)
        self.assertIn("Importar configurações", view)
        self.assertIn("with_data=True", view)
        self.assertIn("src_bytes=raw", view)

    def test_audio_subtitle_preferences_reach_media3(self):
        settings = self.read(SETTINGS)
        main = self.read(MAIN)
        bridge = self.read(BRIDGE)
        main_activity = self.read(MAIN_ACTIVITY)
        player = self.read(PLAYER)
        self.assertIn('"audio.preferred_language"', settings)
        self.assertIn('"audio.preferred_subtitle_language"', settings)
        self.assertIn('"audio.subtitles"', settings)
        self.assertIn('"audio.preferred_language": settings.get("audio.preferred_language")', main)
        self.assertIn('"audio.preferred_subtitle_language": settings.get("audio.preferred_subtitle_language")', main)
        self.assertIn('"audio.subtitles": settings.get("audio.subtitles")', main)
        self.assertIn("player_settings", bridge)
        self.assertIn('setting_audio_preferred_language', main_activity)
        self.assertIn('setting_audio_preferred_subtitle_language', main_activity)
        self.assertIn('setting_audio_subtitles', main_activity)
        self.assertIn("applyGlobalTrackPreferences()", player)
        self.assertIn("setPreferredAudioLanguage", player)
        self.assertIn("setPreferredTextLanguage", player)
        self.assertIn("setTrackTypeDisabled(C.TRACK_TYPE_TEXT, true)", player)

    def test_prompt14_player_contracts_stay_intact(self):
        player = self.read(PLAYER)
        self.assertIn("horizontal_ignored", player)
        self.assertIn("ExoPlayer.Builder(this).build()", player)
        self.assertIn("MediaItem.Builder()", player)
        self.assertIn("restoreSystemUiBeforeExit", player)
        self.assertIn("canEnterPictureInPicture", player)
        self.assertIn("pipEnabled", player)

    def test_continue_watching_and_theme_contracts(self):
        home = self.read(HOME)
        main = self.read(MAIN)
        self.assertIn('settings.get("library.continue_watching")', home)
        self.assertIn('settings.get("library.continue_watching_limit")', home)
        self.assertIn('settings.get("appearance.theme")', main)


if __name__ == "__main__":
    unittest.main()
