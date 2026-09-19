import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class TestBroadStorageArchitecture(unittest.TestCase):
    def test_manifest_and_scanner(self):
        manifest = (ROOT / "android/app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
        scanner = (ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/BroadStorageScanner.kt").read_text(encoding="utf-8")
        self.assertIn("MANAGE_EXTERNAL_STORAGE", manifest)
        self.assertIn("Environment.isExternalStorageManager()", scanner)
        self.assertIn('child == "data" || child == "obb"', scanner)

    def test_bridge_accepts_content_and_file_uris(self):
        from core.android_bridge import AndroidBridge
        self.assertTrue(AndroidBridge.is_local_media_reference("content://media/external/video/1"))
        self.assertTrue(AndroidBridge.is_local_media_reference("file:///storage/emulated/0/a.mkv"))
        self.assertFalse(AndroidBridge.is_local_media_reference("/storage/emulated/0/a.mkv"))

    def test_ingestion_accepts_file_uri(self):
        source = (ROOT / "core/library_service.py").read_text(encoding="utf-8")
        self.assertIn("unquote(urlparse(uri).path)", source)
        self.assertIn('uri.startswith("file://")', source)

    def test_refresh_requests_broad_storage(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("await bridge.scan_all_storage()", source)
        self.assertIn("event_type == 'broad_storage_scan'", source)

if __name__ == "__main__":
    unittest.main()
