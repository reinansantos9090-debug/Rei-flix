import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / "scripts" / "verify_android_host.py"
PREPARE_TEMPLATE = ROOT / "scripts" / "prepare_flet_template.py"
DESCRIPTORS = (
    b"Lcom/reiflix/reiflix_local/MainActivity;",
    b"Lcom/reiflix/reiflix_local/NativeMailbox;",
    b"Lcom/reiflix/reiflix_local/SafScanner;",
    b"Lcom/reiflix/reiflix_local/NativePlayerActivity;",
    b"Lcom/reiflix/reiflix_local/GoogleIdentity;",
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

    def test_workflow_prepares_a_real_template_and_keeps_host_gate(self):
        workflow = (ROOT / ".github" / "workflows" / "build_apk.yml").read_text(encoding="utf-8")
        self.assertIn("https://github.com/flet-dev/flet/releases/download/v0.86.5/flet-build-template.zip", workflow)
        self.assertIn("scripts/prepare_flet_template.py --template build/flet-build-template --overlay android", workflow)
        self.assertIn("flet build apk --template build/flet-build-template --yes -v", workflow)
        self.assertNotIn("flet build apk --template .", workflow)
        self.assertIn('python scripts/verify_android_host.py "$apk"', workflow)

    def test_template_preparation_copies_overlay_and_installs_post_generation_hook(self):
        with tempfile.TemporaryDirectory() as d:
            template = Path(d) / "template"; template.mkdir()
            (template / "cookiecutter.json").write_text(json.dumps({"project_name": "demo"}), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(PREPARE_TEMPLATE), "--template", str(template), "--overlay", str(ROOT / "android")],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            copied = template / "reiflix_android_overlay" / "app" / "src" / "main" / "kotlin" / "com" / "reiflix" / "reiflix_local"
            self.assertTrue((copied / "NativeMailbox.kt").is_file())
            hook_path = template / "hooks" / "post_gen_project.py"
            hook = hook_path.read_text(encoding="utf-8")
            self.assertIn("NativePlayerActivity", hook)
            self.assertIn("media3-exoplayer:1.5.1", hook)
            self.assertNotIn("__REIFLIX_OVERLAY_APP__", hook)
            self.assertIn(str((template / "reiflix_android_overlay" / "app").resolve()), hook)

            rendered = Path(d) / "rendered" / "android" / "app"
            (rendered / "src" / "main").mkdir(parents=True)
            (rendered / "build.gradle").write_text("plugins {}\n", encoding="utf-8")
            (rendered / "src" / "main" / "AndroidManifest.xml").write_text(
                '<manifest xmlns:android="http://schemas.android.com/apk/res/android"><application><activity android:name=".MainActivity" /></application></manifest>',
                encoding="utf-8",
            )
            # Cookiecutter executes a temporary copy of the rendered hook.
            # Reproduce that behavior so the test catches __file__-relative paths.
            runtime_hook = Path(d) / "cookiecutter_tmp_post_gen_project.py"
            shutil.copy2(hook_path, runtime_hook)
            hook_result = subprocess.run([sys.executable, str(runtime_hook)],
                                         cwd=rendered.parents[1], capture_output=True, text=True)
            self.assertEqual(hook_result.returncode, 0, hook_result.stderr)
            self.assertIn("NativePlayerActivity", (rendered / "src" / "main" / "AndroidManifest.xml").read_text(encoding="utf-8"))
            self.assertIn("@style/ReiFlixTheme", (rendered / "src" / "main" / "AndroidManifest.xml").read_text(encoding="utf-8"))
            self.assertIn("media3-exoplayer:1.5.1", (rendered / "build.gradle").read_text(encoding="utf-8"))

    def test_native_host_keeps_system_bars_for_flet_and_fullscreen_for_player_only(self):
        main = (ROOT / "android" / "app" / "src" / "main" / "kotlin" / "com" / "reiflix" / "reiflix_local" / "MainActivity.kt").read_text(encoding="utf-8")
        player = (ROOT / "android" / "app" / "src" / "main" / "kotlin" / "com" / "reiflix" / "reiflix_local" / "NativePlayerActivity.kt").read_text(encoding="utf-8")
        self.assertIn("WindowCompat.setDecorFitsSystemWindows(window, true)", main)
        self.assertIn("show(WindowInsetsCompat.Type.systemBars())", main)
        self.assertIn("hide(WindowInsetsCompat.Type.systemBars())", player)

    def test_player_exit_is_not_suppressed_after_normal_completion(self):
        player = (ROOT / "android" / "app" / "src" / "main" / "kotlin" / "com" / "reiflix" / "reiflix_local" / "NativePlayerActivity.kt").read_text(encoding="utf-8")
        self.assertIn("private var suppressExitEvent = false", player)
        self.assertIn("suppressExitEvent = true", player)
        self.assertIn("if (!suppressExitEvent) saveProgress(\"player_exited\", force = true)", player)

    def test_native_mailbox_uses_the_flet_application_data_subdirectory(self):
        mailbox = (ROOT / "android" / "app" / "src" / "main" / "kotlin" / "com" / "reiflix" / "reiflix_local" / "NativeMailbox.kt").read_text(encoding="utf-8")
        self.assertIn('File(context.filesDir, "data")', mailbox)
        self.assertIn('val target = File(dataDirectory, FILE)', mailbox)

    def test_native_player_entry_rejects_non_local_deep_link_uris(self):
        main = (ROOT / "android" / "app" / "src" / "main" / "kotlin" / "com" / "reiflix" / "reiflix_local" / "MainActivity.kt").read_text(encoding="utf-8")
        self.assertIn('localUri.scheme !in setOf("content", "file")', main)
        self.assertIn('"A reprodução aceita somente arquivos locais autorizados."', main)

    def test_google_identity_emits_only_token_free_validated_profile_fields(self):
        source = (ROOT / "android" / "app" / "src" / "main" / "kotlin" / "com" / "reiflix" / "reiflix_local" / "GoogleIdentity.kt").read_text(encoding="utf-8")
        self.assertIn('"google_sign_in_started"', source)
        self.assertIn('validatedSubject(credential.idToken, serverClientId)', source)
        self.assertIn('.put("id", subject)', source)
        self.assertNotIn('.put("idToken"', source)
