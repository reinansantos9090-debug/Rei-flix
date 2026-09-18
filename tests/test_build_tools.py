import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / "scripts" / "verify_android_host.py"
DESCRIPTORS = (
    b"Lcom/reiflix/reiflix_local/MainActivity;",
    b"Lcom/reiflix/reiflix_local/NativeMailbox;",
    b"Lcom/reiflix/reiflix_local/SafScanner;",
    b"Lcom/reiflix/reiflix_local/NativePlayerActivity;",
)


class AndroidHostVerificationTests(unittest.TestCase):
    def _apk(self, descriptors):
        path = Path(self.tmp.name) / "app.apk"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("AndroidManifest.xml", b"manifest")
            archive.writestr("classes.dex", b"dex\n" + b"\n".join(descriptors))
        return path

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_accepts_apk_with_all_native_host_classes(self):
        result = subprocess.run([sys.executable, str(VERIFY), str(self._apk(DESCRIPTORS))],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Verified native ReiFlix host", result.stdout)

    def test_rejects_stock_apk_without_native_host_classes(self):
        result = subprocess.run([sys.executable, str(VERIFY), str(self._apk(DESCRIPTORS[:1]))],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Native ReiFlix host was not packaged", result.stderr)
