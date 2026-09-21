import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class UiStateTests(unittest.TestCase):
    def test_scan_states_are_explicit(self):
        source = (ROOT / "core" / "storage_access.py").read_text(encoding="utf-8")
        for state in ("IDLE", "CHECKING", "SCANNING", "COMPLETED", "PARTIAL", "CANCELLED", "FAILED", "WAITING_FOR_MEDIASTORE", "VOLUME_UNAVAILABLE"):
            self.assertIn(f'{state} = "{state}"', source)

    def test_settings_uses_android_snapshot_not_sqlite_for_permission_state(self):
        source = (ROOT / "views" / "settings_view.py").read_text(encoding="utf-8")
        self.assertIn("storage_snapshot=None", source)
        self.assertIn('getattr(storage_snapshot, "media_read_state"', source)
        self.assertIn('getattr(storage_snapshot, "broad_storage_state"', source)
        self.assertIn("MEDIASTORE:", source)
        self.assertIn("SAF:", source)
        self.assertIn("BROAD STORAGE:", source)

    def test_settings_has_scan_diagnostics(self):
        source = (ROOT / "views" / "settings_view.py").read_text(encoding="utf-8")
        for token in ("SCAN:", "Fonte:", "Volume:", "Encontrados:", "Volumes removíveis:", "Timestamp:"):
            self.assertIn(token, source)

    def test_main_passes_authoritative_snapshots_to_settings(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("storage_snapshot=storage_capabilities[0]", source)
        self.assertIn("scan_snapshot=scan_state[0]", source)

    def test_main_has_lifecycle_safe_page_update(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("def safe_update():", source)
        self.assertIn("ui_alive", source)
        self.assertIn("stale lifecycle callback", source)

    def test_main_does_not_treat_library_rows_as_permission_authority(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        refresh = source[source.index("async def refresh_library"):source.index("async def login")]
        self.assertIn("caps.can_scan", refresh)
        self.assertNotIn("folder.get('authorization') == 'granted'", refresh)

    def test_source_is_valid_python(self):
        for path in (ROOT / "main.py", ROOT / "views" / "settings_view.py", ROOT / "core" / "storage_access.py"):
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


if __name__ == "__main__":
    unittest.main()
