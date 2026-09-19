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
        self.assertIn("--template \"$GITHUB_WORKSPACE/build/flet-build-template\"", workflow)
        self.assertIn("--overlay \"$GITHUB_WORKSPACE/android\"", workflow)
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
            self.assertIn("SystemUiController.kt", hook)
            self.assertIn("media3-exoplayer:1.5.1", hook)
            self.assertNotIn("__REIFLIX_OVERLAY_APP__", hook)
            self.assertIn(f'Path({str((template / "reiflix_android_overlay" / "app").resolve())!r})', hook)

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

    def test_main_activity_uses_compatible_back_and_activity_result_callbacks(self):
        main = (ROOT / "android" / "app" / "src" / "main" / "kotlin" / "com" / "reiflix" / "reiflix_local" / "MainActivity.kt").read_text(encoding="utf-8")
        self.assertNotIn("OnBackPressedCallback", main)
        self.assertNotIn("onBackPressedDispatcher", main)
        self.assertNotIn("return@registerForActivityResult", main)
        self.assertIn("handleTreePickerResult(result)", main)
        self.assertIn("override fun onBackPressed()", main)
        self.assertIn("import io.flutter.embedding.android.FlutterFragmentActivity", main)
        self.assertIn("class MainActivity : FlutterFragmentActivity()", main)
        self.assertNotIn("import io.flutter.embedding.android.FlutterActivity", main)

    def test_saf_picker_requests_only_persisted_read_access(self):
        main = (ROOT / "android" / "app" / "src" / "main" / "kotlin" / "com" / "reiflix" / "reiflix_local" / "MainActivity.kt").read_text(encoding="utf-8")
        self.assertIn("Intent.FLAG_GRANT_READ_URI_PERMISSION", main)
        self.assertIn("Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION", main)
        self.assertIn("Intent.FLAG_GRANT_PREFIX_URI_PERMISSION", main)
        self.assertNotIn("Intent.FLAG_GRANT_WRITE_URI_PERMISSION", main)

    def test_startup_saf_permission_verification_is_awaited(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("await bridge.verify_tree(folder['path'])", source)
        self.assertIn("authorization", source)

    def test_main_activity_delegates_system_ui_to_controller_and_reapplies_on_resume(self):
        main = (ROOT / "android" / "app" / "src" / "main" / "kotlin" / "com" / "reiflix" / "reiflix_local" / "MainActivity.kt").read_text(encoding="utf-8")
        controller = (ROOT / "android" / "app" / "src" / "main" / "kotlin" / "com" / "reiflix" / "reiflix_local" / "SystemUiController.kt").read_text(encoding="utf-8")
        styles = (ROOT / "android" / "app" / "src" / "main" / "res" / "values" / "styles.xml").read_text(encoding="utf-8")
        self.assertIn("private lateinit var systemUiController: SystemUiController", main)
        self.assertIn("systemUiController = SystemUiController(window)", main)
        self.assertIn("override fun onResume()", main)
        self.assertIn("applyImmersiveSystemUi()", main)
        self.assertIn("WindowCompat.getInsetsController(window, window.decorView)", controller)
        self.assertIn("BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE", controller)
        self.assertIn("hide(WindowInsetsCompat.Type.systemBars())", controller)
        self.assertIn('<item name="android:windowFullscreen">true</item>', styles)

    def test_native_host_uses_immersive_system_bars_for_flet_and_player(self):
        main = (ROOT / "android" / "app" / "src" / "main" / "kotlin" / "com" / "reiflix" / "reiflix_local" / "MainActivity.kt").read_text(encoding="utf-8")
        player = (ROOT / "android" / "app" / "src" / "main" / "kotlin" / "com" / "reiflix" / "reiflix_local" / "NativePlayerActivity.kt").read_text(encoding="utf-8")
        self.assertIn("WindowCompat.setDecorFitsSystemWindows(window, false)", main)
        self.assertIn("hide(WindowInsetsCompat.Type.systemBars())", main)
        self.assertIn("BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE", main)
        self.assertNotIn("show(WindowInsetsCompat.Type.systemBars())", main)
        self.assertIn("hide(WindowInsetsCompat.Type.systemBars())", player)
        self.assertIn("BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE", player)

    def test_player_exit_is_not_suppressed_after_normal_completion(self):
        player = (ROOT / "android" / "app" / "src" / "main" / "kotlin" / "com" / "reiflix" / "reiflix_local" / "NativePlayerActivity.kt").read_text(encoding="utf-8")
        self.assertIn("private var suppressExitEvent = false", player)
        self.assertIn("suppressExitEvent = true", player)
        self.assertIn("if (!suppressExitEvent) saveProgress(\"player_exited\", force = true)", player)

    def test_template_requires_the_immersive_system_ui_controller(self):
        source = PREPARE_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("SystemUiController.kt", source)
        self.assertIn("immersive host theme", source)

    def test_native_mailbox_uses_the_flet_application_data_subdirectory(self):
        mailbox = (ROOT / "android" / "app" / "src" / "main" / "kotlin" / "com" / "reiflix" / "reiflix_local" / "NativeMailbox.kt").read_text(encoding="utf-8")
        self.assertIn('File(context.filesDir, "data")', mailbox)
        self.assertIn('val target = File(dataDirectory, FILE)', mailbox)

    def test_refresh_recovers_when_a_saf_scan_cannot_start(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        start = source.index("            if saf_folders and bridge.available:")
        end = source.index("            result = await asyncio.to_thread(library.scan)", start)
        block = source[start:end]
        self.assertIn("pending_native_scans[0] = 0", block)
        self.assertIn("except Exception:", block)
        self.assertIn('update_folder_status(folder[\'path\'], "granted"', block)
        self.assertIn("pending_native_scans[0] > 0", block)

    def test_folder_removal_is_blocked_while_refresh_is_active(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        start = source.index("    async def remove_folder(reference):")
        end = source.index("    def account():", start)
        block = source[start:end]
        self.assertIn("if scan_in_progress[0] or saf_selection.pending:", block)
        self.assertIn("store.remove_folder(reference)", block)

    def test_folder_removal_waits_for_native_release_event(self):
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("pending_folder_removals=set()", main)
        self.assertIn("pending_folder_removals.add(reference)", main)
        self.assertIn("event_type == 'saf_released'", main)
        self.assertIn("store.remove_folder(tree_uri)", main)

    def test_folder_removal_releases_saf_permission_before_database_removal(self):
        bridge = (ROOT / "core" / "android_bridge.py").read_text(encoding="utf-8")
        activity = (ROOT / "android" / "app" / "src" / "main" / "kotlin" / "com" / "reiflix" / "reiflix_local" / "MainActivity.kt").read_text(encoding="utf-8")
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn('async def release_tree(self, tree_uri: str)', bridge)
        self.assertIn('"release_tree" -> releaseTree', activity)
        self.assertIn("releasePersistableUriPermission", activity)
        self.assertIn("await bridge.release_tree(reference)", main)

    def test_settings_exposes_folder_removal_callback(self):
        settings = (ROOT / "views" / "settings_view.py").read_text(encoding="utf-8")
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("on_remove_folder", settings)
        self.assertIn("on_remove_folder(reference)", settings)
        self.assertIn("remove_folder", main)

    def test_refresh_library_skips_revoked_saf_trees_until_permission_returns(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("folder.get('kind') == 'saf' and folder.get('authorization') == 'granted'", source)
        self.assertIn("await bridge.verify_tree(folder['path'])", source)

    def test_refresh_library_waits_for_every_saf_scan_result_or_error(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("pending_native_scans[0] = 0", source)
        self.assertIn("pending_native_scans[0] += 1", source)
        self.assertIn("pending_native_scans[0] = max(0, pending_native_scans[0] - 1)", source)
        self.assertIn("if pending_native_scans[0] == 0:", source)
        self.assertIn("if event_type == 'saf_error':", source)
        self.assertIn("finish_native_scan()", source)

    def test_native_player_entry_requires_a_persisted_saf_document(self):
        main = (ROOT / "android" / "app" / "src" / "main" / "kotlin" / "com" / "reiflix" / "reiflix_local" / "MainActivity.kt").read_text(encoding="utf-8")
        scanner = (ROOT / "android" / "app" / "src" / "main" / "kotlin" / "com" / "reiflix" / "reiflix_local" / "SafScanner.kt").read_text(encoding="utf-8")
        self.assertIn("SafScanner.isAuthorizedDocument(this, localUri)", main)
        self.assertIn("DocumentsContract.getDocumentId(documentUri)", scanner)
        self.assertIn("DocumentsContract.getTreeDocumentId(permission.uri)", scanner)

    def test_saf_scanner_uses_iterative_traversal_and_partial_results(self):
        scanner = (ROOT / "android" / "app" / "src" / "main" / "kotlin" / "com" / "reiflix" / "reiflix_local" / "SafScanner.kt").read_text(encoding="utf-8")
        self.assertIn("ArrayDeque<Pair<String, String>>()", scanner)
        self.assertIn("pending.removeLast()", scanner)
        self.assertIn('put("partial", partial)', scanner)
        self.assertIn("DocumentsContract.buildChildDocumentsUriUsingTree", scanner)
        self.assertIn("DocumentsContract.buildDocumentUriUsingTree", scanner)
        self.assertIn("COLUMN_DOCUMENT_ID", scanner)
        self.assertIn("COLUMN_MIME_TYPE", scanner)
        self.assertIn("Log.i(", scanner)

    def test_native_player_entry_rejects_non_local_deep_link_uris(self):
        main = (ROOT / "android" / "app" / "src" / "main" / "kotlin" / "com" / "reiflix" / "reiflix_local" / "MainActivity.kt").read_text(encoding="utf-8")
        self.assertIn('localUri.scheme != "content"', main)
        self.assertIn("SafScanner.isAuthorizedDocument(this, localUri)", main)
        self.assertIn('"Este arquivo não pertence a uma pasta autorizada pelo Rei-Flix."', main)

    def test_native_player_rechecks_saf_authorization_before_media3_start(self):
        player = (ROOT / "android" / "app" / "src" / "main" / "kotlin" / "com" / "reiflix" / "reiflix_local" / "NativePlayerActivity.kt").read_text(encoding="utf-8")
        self.assertIn('uri.scheme != "content"', player)
        self.assertIn("SafScanner.isAuthorizedDocument(this, uri)", player)
        self.assertIn("Este arquivo não pertence a uma pasta autorizada pelo Rei-Flix.", player)

    def test_android_bridge_accepts_only_content_media_references(self):
        from core.android_bridge import AndroidBridge

        self.assertTrue(AndroidBridge.is_local_media_reference(
            "content://com.android.providers.media.documents/document/video%3A1"
        ))
        for value in ("", "/sdcard/video.mkv", "file:///sdcard/video.mkv", "http://example/video.mkv"):
            self.assertFalse(AndroidBridge.is_local_media_reference(value))

    def test_saf_regrant_path_persists_before_scanning_and_reports_revocation(self):
        main = (ROOT / "android" / "app" / "src" / "main" / "kotlin" / "com" / "reiflix" / "reiflix_local" / "MainActivity.kt").read_text(encoding="utf-8")
        scanner = (ROOT / "android" / "app" / "src" / "main" / "kotlin" / "com" / "reiflix" / "reiflix_local" / "SafScanner.kt").read_text(encoding="utf-8")
        self.assertIn("SafScanner.persistPermission(this, uri, resultIntent.flags)", main)
        self.assertIn("scanTree(uri.toString())", main)
        self.assertIn("takePersistableUriPermission(uri, granted)", scanner)
        self.assertIn("check(hasPersistedReadPermission(context, uri))", scanner)
        self.assertIn("if (!SafScanner.hasPersistedReadPermission(this, treeUri))", main)
        self.assertIn("A permissão desta pasta foi removida.", main)

    def test_player_rejects_removed_or_invalid_saf_documents_without_starting_media3(self):
        main = (ROOT / "android" / "app" / "src" / "main" / "kotlin" / "com" / "reiflix" / "reiflix_local" / "MainActivity.kt").read_text(encoding="utf-8")
        player = (ROOT / "android" / "app" / "src" / "main" / "kotlin" / "com" / "reiflix" / "reiflix_local" / "NativePlayerActivity.kt").read_text(encoding="utf-8")
        self.assertIn('localUri.scheme != "content" || !SafScanner.isAuthorizedDocument(this, localUri)', main)
        self.assertIn("startActivity(Intent(this, NativePlayerActivity::class.java)", main)
        player_guard = 'if (uri.scheme != "content" || !SafScanner.isAuthorizedDocument(this, uri))'
        self.assertIn(player_guard, player)
        self.assertIn('reportError("Arquivo local inválido.")', player)
        self.assertIn("finish()", player)

    def test_saf_scanner_contains_provider_error_recovery_for_inaccessible_documents(self):
        scanner = (ROOT / "android" / "app" / "src" / "main" / "kotlin" / "com" / "reiflix" / "reiflix_local" / "SafScanner.kt").read_text(encoding="utf-8")
        self.assertIn("runCatching", scanner)
        self.assertIn("catch (exception: Exception)", scanner)
        self.assertIn('errors.put("Não foi possível ler:', scanner)
        self.assertIn('errors.put("Não foi possível acessar:', scanner)
        self.assertIn('put("partial", partial)', scanner)

    def test_google_identity_emits_only_token_free_validated_profile_fields(self):
        source = (ROOT / "android" / "app" / "src" / "main" / "kotlin" / "com" / "reiflix" / "reiflix_local" / "GoogleIdentity.kt").read_text(encoding="utf-8")
        self.assertIn('"google_sign_in_started"', source)
        self.assertIn('validatedSubject(credential.idToken, serverClientId)', source)
        self.assertIn('.put("id", subject)', source)
        self.assertNotIn('.put("idToken"', source)
