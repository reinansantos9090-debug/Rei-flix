import unittest
from pathlib import Path

from core.dialogs import dismiss_dialog
from core.storage_access import StorageAccessState, storage_access_state, storage_source_states

ROOT = Path(__file__).resolve().parents[1]

class StorageOnboardingTests(unittest.TestCase):
    def test_real_permission_snapshot_has_deterministic_states(self):
        self.assertEqual(storage_access_state("denied", False), StorageAccessState.NEEDS_MEDIA_PERMISSION)
        self.assertEqual(storage_access_state("partial", False), StorageAccessState.MEDIA_PARTIAL)
        self.assertEqual(storage_access_state("full", False), StorageAccessState.READY)
        self.assertEqual(storage_access_state("full", True), StorageAccessState.READY)
        self.assertEqual(storage_access_state("full", True, dismissed=True), StorageAccessState.DECLINED)

    def test_dismissal_detaches_overlay_without_alertdialog_close_api(self):
        class Dialog: open = True
        class Page:
            def __init__(self): self.overlay = [dialog]; self.updated = 0
            def update(self): self.updated += 1
        dialog = Dialog(); page = Page()
        dismiss_dialog(page, dialog)
        self.assertFalse(dialog.open)
        self.assertEqual([], page.overlay)
        self.assertEqual(1, page.updated)

    def test_project_has_no_invalid_alertdialog_close_calls(self):
        sources = "\n".join(path.read_text(encoding="utf-8") for path in ROOT.rglob("*.py") if "tests" not in path.parts)
        self.assertNotIn("dialog.close(", sources)
        self.assertIn("dismiss_dialog", (ROOT / "views" / "settings_view.py").read_text(encoding="utf-8"))

    def test_permission_intent_is_single_task_and_lifecycle_queued(self):
        manifest = (ROOT / "android/app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
        source = (ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt").read_text(encoding="utf-8")
        self.assertIn('android:launchMode="singleTask"', manifest)
        self.assertIn('android:documentLaunchMode="never"', manifest)
        self.assertIn("setIntent(intent)", source)
        self.assertIn("pendingLifecycleAction", source)
        self.assertIn("override fun onResume()", source)
        self.assertIn("activityResumed", source)
        self.assertIn("LIFECYCLE", source)

    def test_permission_request_is_not_launched_from_a_non_resumed_activity(self):
        source = (ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt").read_text(encoding="utf-8")
        request_block = source.split("private fun requestMediaAccess()", 1)[1].split("private fun publishStorageStatus()", 1)[0]
        self.assertIn('if (!activityResumed)', request_block)
        self.assertIn('queueLifecycleAction("request_media_access")', request_block)
        self.assertIn("mediaPermissionRequester.launch(permissions)", request_block)

    def test_existing_media_permission_continues_to_scan_instead_of_stopping_at_grant_event(self):
        source = (ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt").read_text(encoding="utf-8")
        request_block = source.split("private fun requestMediaAccess()", 1)[1].split("private fun publishStorageStatus()", 1)[0]
        self.assertIn('val currentAccess = MediaStoreScanner.accessLevel(this)', request_block)
        self.assertIn('if (currentAccess != "denied")', request_block)
        self.assertLess(request_block.index('put("type", "mediastore_permission")'), request_block.index("scanMediaStore()"))
        self.assertIn("Existing access must converge to the same permission -> scan -> index -> mailbox path.", request_block)

    def test_saf_picker_is_lifecycle_gated_and_single_shot(self):
        source = (ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt").read_text(encoding="utf-8")
        picker = source.split("private fun openTreePicker()", 1)[1].split("override fun onWindowFocusChanged", 1)[0]
        self.assertIn('if (!activityResumed)', picker)
        self.assertIn('queueLifecycleAction("select_tree")', picker)
        self.assertIn("safPickerPending", picker)
        self.assertIn("treePicker.launch(", picker)
        self.assertIn("safPickerPending = false", source)

    def test_permission_callback_uses_authoritative_access_level(self):
        source = (ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt").read_text(encoding="utf-8")
        callback = source.split("private val mediaPermissionRequester", 1)[1].split("private val legacyBroadPermissionRequester", 1)[0]
        self.assertIn("MediaStoreScanner.accessLevel(this)", callback)
        self.assertIn('val granted = access != "denied"', callback)
        self.assertNotIn('grants.any { it.value } && MediaStoreScanner.hasReadPermission(this)', callback)

    def test_storage_state_machine_keeps_sources_independent(self):
        self.assertEqual(storage_source_states("denied", False)["media"], "media_denied")
        self.assertEqual(storage_source_states("partial", False)["media"], "media_partial")
        self.assertEqual(storage_source_states("full", False)["media"], "media_full")
        self.assertEqual(storage_source_states("full", True)["broad"], "broad_storage_available")
        self.assertEqual(storage_source_states("full", False)["broad"], "broad_storage_unavailable")
        self.assertEqual(storage_source_states("full", False, ["content://tree/one"])["saf"], "saf_available")
        self.assertEqual(storage_source_states("full", False, [], saf_revoked=True)["saf"], "saf_revoked")
        self.assertEqual(storage_access_state("full", False, require_broad=True), StorageAccessState.NEEDS_BROAD_STORAGE)
        self.assertEqual(storage_access_state("full", False), StorageAccessState.READY)

    def test_authorized_alternative_source_suppresses_media_onboarding(self):
        self.assertEqual(
            storage_access_state("denied", False, True),
            StorageAccessState.READY,
        )
        self.assertEqual(
            storage_access_state("denied", True, False),
            StorageAccessState.READY,
        )

    def test_storage_onboarding_offers_saf_alternative(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        onboarding = source[source.index("def maybe_show_storage_onboarding"):source.index("async def refresh_library")]
        self.assertIn("async def choose_folder(_event):", onboarding)
        self.assertIn("await add_folder()", onboarding)
        self.assertIn('ft.TextButton("ESCOLHER PASTA"', onboarding)
        self.assertIn('ft.FilledButton("PERMITIR"', onboarding)
        source_state = source[source.index("def storage_state()"):source.index("def maybe_show_storage_onboarding")]
        self.assertIn("storage_access_state(", source_state)
        self.assertIn('storage_onboarding["saf"] is True', source_state)

    def test_storage_onboarding_cancel_uses_managed_flet_dialog_stack(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        onboarding = source[source.index("def maybe_show_storage_onboarding"):source.index("async def refresh_library")]
        self.assertIn("page.show_dialog(dialog)", onboarding)
        self.assertIn("page.pop_dialog()", onboarding)
        self.assertIn('storage_onboarding["dismissed"] = True', onboarding)
        self.assertNotIn("page.overlay.append(dialog)", onboarding)
        self.assertNotIn("dismiss_dialog(page, dialog)", onboarding)

    def test_storage_permission_dialogs_in_settings_use_managed_flet_stack(self):
        source = (ROOT / "views" / "settings_view.py").read_text(encoding="utf-8")
        media = source[source.index("def show_video_permission_dialog"):source.index("def show_broad_storage_dialog")]
        broad = source[source.index("def show_broad_storage_dialog"):source.index("pending_matches = store.pending_matches()")]
        for block in (media, broad):
            self.assertIn("page.show_dialog(dialog)", block)
            self.assertIn("page.pop_dialog()", block)
            self.assertNotIn("page.overlay.append(dialog)", block)

    def test_startup_never_self_launches_persisted_saf_verification(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertNotIn("await bridge.verify_tree", source)
        self.assertIn("authoritative SAF grant inventory", source)

    def test_saf_completion_clears_onboarding_wait_state(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        cancelled = source[source.index("event_type == 'saf_cancelled'"):source.index("event_type == 'saf_permission'")]
        granted = source[source.index("event_type == 'saf_permission'"):source.index("event_type == 'saf_released'")]
        self.assertIn('storage_onboarding["waiting_for_result"] = False', cancelled)
        self.assertIn('storage_onboarding["waiting_for_result"] = False', granted)

    def test_main_handles_authoritative_saf_inventory_and_marks_revoked_sources(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        block = source[source.index("event_type == 'saf_inventory':"):source.index("event_type == 'saf_cancelled':")]
        self.assertIn("current_uris", block)
        self.assertIn("folder.get('kind') != 'saf'", block)
        self.assertIn("A autorização SAF desta pasta não está mais presente no Android.", block)
        self.assertIn("store.update_folder_status", block)

    def test_broad_permission_event_does_not_reopen_onboarding_after_settings_launch(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        block = source.split("event_type == 'broad_storage_permission':", 1)[1].split("event_type == 'broad_storage_error':", 1)[0]
        self.assertIn("was_waiting = storage_onboarding[\"waiting_for_result\"]", block)
        self.assertIn('storage_onboarding["dismissed"] = True', block)
        self.assertIn("Do not reopen the onboarding modal", block)

    def test_cancel_and_allow_callbacks_are_lifecycle_safe(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        start = source.index("        async def allow_media(_event):")
        end = source.index("        dialog.actions =", start)
        block = source[start:end]
        cancel_end = source.index("        dialog.actions =", source.index("        def cancel(_event):"))
        cancel = source[source.index("        def cancel(_event):"):cancel_end]
        self.assertIn('storage_onboarding["waiting_for_result"] = True', block)
        self.assertIn("page.pop_dialog()", block)
        self.assertNotIn("asyncio.sleep(0)", block)
        self.assertIn("def cancel(_event):", cancel)
        self.assertIn('storage_onboarding["dismissed"] = True', cancel)
        self.assertNotIn("request_video_access", cancel)
        self.assertNotIn("open_broad_storage_access", cancel)

    def test_startup_does_not_self_launch_main_activity_for_storage_snapshot(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        startup = source[source.index("    page.on_login=login_done"):source.rindex("    render_current()")]
        self.assertNotIn("bridge.check_storage_access", startup)
        self.assertNotIn("await bridge.verify_tree", source)
        self.assertIn("authoritative SAF grant inventory", source)

    def test_native_intents_have_unique_request_identity_and_are_deduplicated(self):
        bridge = (ROOT / "core/android_bridge.py").read_text(encoding="utf-8")
        main = (ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt").read_text(encoding="utf-8")
        self.assertIn("uuid.uuid4().hex", bridge)
        self.assertIn('"request_id": request_id', bridge)
        self.assertIn('getQueryParameter("request_id")', main)
        self.assertIn("nativeRequestState", main)
        self.assertIn("NativeRequestState.isSupportedAction", main)
        self.assertIn("Ignoring duplicate native request", main)

    def test_activity_preserves_request_state_across_recreation(self):
        source = (ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt").read_text(encoding="utf-8")
        self.assertIn("STATE_LAST_NATIVE_REQUEST_ID", source)
        self.assertIn("STATE_PENDING_LIFECYCLE_ACTION", source)
        self.assertIn("STATE_BROAD_SETTINGS_PENDING", source)
        self.assertIn("savedInstanceState?.getString(STATE_LAST_NATIVE_REQUEST_ID)", source)
        self.assertIn("override fun onSaveInstanceState(outState: Bundle)", source)

    def test_open_settings_does_not_publish_a_false_permission_before_navigation(self):
        source = (ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt").read_text(encoding="utf-8")
        block = source.split("private fun openBroadStorageSettings()", 1)[1].split("private fun openSettingsIntent", 1)[0]
        self.assertNotIn('put("granted", false)', block)
        self.assertIn("broadStoragePermissionPending = true", block)
        self.assertIn("publishStorageStatus()", source)

    def test_native_host_rechecks_and_never_scans_before_authorization(self):
        source = (ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt").read_text(encoding="utf-8")
        self.assertIn("override fun onResume()", source)
        self.assertIn("publishStorageStatus()", source)
        self.assertIn("if (!BroadStorageScanner.hasAccess(this))", source)
        self.assertIn("if (!MediaStoreScanner.hasReadPermission(this))", source)
        self.assertIn("mediaPermissionRequestPending", source)
        self.assertIn("ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION", source)

    def test_broad_storage_is_optional_for_full_media_access(self):
        self.assertEqual(storage_access_state("full", False), StorageAccessState.READY)
        self.assertEqual(storage_access_state("full", True), StorageAccessState.READY)

    def test_storage_dialogs_do_not_use_artificial_async_lifecycle_delays(self):
        settings = (ROOT / "views" / "settings_view.py").read_text(encoding="utf-8")
        self.assertNotIn("asyncio.sleep(0)", settings)

    def test_refresh_library_gates_broad_scanner_on_authorization(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        refresh = source[source.index("    async def refresh_library"):source.index("    async def login", source.index("    async def refresh_library"))]
        self.assertIn("broad_granted = any(", refresh)
        self.assertIn("if broad_granted:", refresh)

    def test_on_resume_does_not_publish_intermediate_denied_before_pending_request(self):
        source = (ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt").read_text(encoding="utf-8")
        resume = source[source.index("override fun onResume()"):source.index("override fun onPause()", source.index("override fun onResume()"))]
        self.assertLess(resume.index("val pending = nativeRequestState.consumeLifecycleAction()"), resume.index("publishStorageStatus()"))
        self.assertIn("if (pending != null)", resume)
        self.assertIn("return", resume)

    def test_broad_scanner_is_guarded_in_python_refresh_flow(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        refresh = source[source.index("    async def refresh_library"):source.index("    async def login", source.index("    async def refresh_library"))]
        self.assertIn("if broad_granted:", refresh)
        broad_call = refresh.find("await bridge.scan_all_storage()")
        guard = refresh.rfind("if broad_granted:", 0, broad_call)
        self.assertGreaterEqual(broad_call, 0)
        self.assertGreater(guard, -1)

    def test_native_scan_controller_is_process_wide_and_source_scoped(self):
        source = (ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/NativeScanController.kt").read_text(encoding="utf-8")
        main = (ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt").read_text(encoding="utf-8")
        self.assertIn("private val sourceOwners", source)
        self.assertIn("sourceOwners.containsKey(sourceKey)", source)
        self.assertIn("NativeScanController.begin(scanId, scanKey)", main)
        self.assertIn("NativeScanController.begin(scanId, BroadStorageScanner.SOURCE)", main)
        self.assertIn("NativeScanController.begin(scanId, MediaStoreScanner.SOURCE)", main)
        self.assertNotIn("activeNativeScans", main)

    def test_activity_finishing_cancels_native_scans_but_recreation_does_not(self):
        source = (ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt").read_text(encoding="utf-8")
        destroy = source[source.index("override fun onDestroy()"):source.index("override fun onSaveInstanceState", source.index("override fun onDestroy()"))]
        self.assertIn("if (isFinishing) NativeScanController.cancelAll()", destroy)
        self.assertIn("applicationContext", source)

    def test_mediastore_scan_isolates_volume_failures(self):
        source = (ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/MediaStoreScanner.kt").read_text(encoding="utf-8")
        self.assertIn("MediaStore query failed for volume $volumeName", source)
        self.assertIn("for(volumeName in volumeNames)", source)
        self.assertIn("catch(exception:Exception)", source)
    def test_main_imports_os_for_durable_flet_storage_path(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("import os", source)
        self.assertIn('os.getenv("FLET_APP_STORAGE_DATA")', source)

    def test_legacy_external_volume_discovery_contract(self):
        source = (ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/BroadStorageScanner.kt").read_text(encoding="utf-8")
        self.assertIn("getExternalFilesDirs(null)", source)
        self.assertIn("inferVolumeRoot", source)
        self.assertIn("Environment.isExternalStorageRemovable(volumeRoot)", source)

    def test_generated_manifest_normalizes_existing_legacy_permission(self):
        source = (ROOT / "scripts/prepare_flet_template.py").read_text(encoding="utf-8")
        self.assertIn("existing_nodes = [", source)
        self.assertIn('permission == "android.permission.READ_EXTERNAL_STORAGE"', source)
        self.assertIn('node.set("{" + ANDROID + "}maxSdkVersion", max_sdk)', source)

    def test_duplicate_native_scan_reports_already_running(self):
        source = (ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt").read_text(encoding="utf-8")
        self.assertIn('put("phase", "already_running")', source)
        self.assertIn('"saf_scan_progress"', source)
        self.assertIn('"broad_storage_scan_progress"', source)
        self.assertIn('"mediastore_scan_progress"', source)
    def test_long_native_scan_uses_application_context_for_mailbox_callbacks(self):
        source = (ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt").read_text(encoding="utf-8")
        scan_block = source[source.index("private fun scanTree"):source.index("    private fun requestMediaAccess", source.index("private fun scanTree"))]
        broad_block = source[source.index("private fun scanAllStorage"):source.index("    private fun scanMediaStore", source.index("private fun scanAllStorage"))]
        media_block = source[source.index("private fun scanMediaStore"):source.index("    private fun cancelNativeScans", source.index("private fun scanMediaStore"))]
        for block in (scan_block, broad_block, media_block):
            self.assertIn("val appContext = applicationContext", block)
            self.assertNotIn("NativeMailbox.write(this@MainActivity", block)

    def test_native_bridge_orders_events_by_creation_time(self):
        source = (ROOT / "core/android_bridge.py").read_text(encoding="utf-8")
        self.assertIn("def _event_time(event: dict)", source)
        self.assertIn("indexed.sort(key=lambda item: (self._event_time(item[1]), item[0]))", source)
        self.assertIn('"createdAt"', source)

    def test_native_bridge_retains_failed_requeue_events(self):
        source = (ROOT / "core/android_bridge.py").read_text(encoding="utf-8")
        self.assertIn("self._retained: set[Path]", source)
        self.assertIn("self._retained.add(consumed)", source)
        self.assertIn("if consumed in self._retained:", source)

    def test_native_bridge_does_not_delete_claimed_events_on_drain_io_failure(self):
        source = (ROOT / "core/android_bridge.py").read_text(encoding="utf-8")
        block = source[source.index("except OSError as exc:", source.index("def drain")):source.index("    def requeue_event_ids", source.index("def drain"))]
        self.assertIn("Never discard a claimed event", block)
        self.assertIn('path.replace(path.with_suffix(".json"))', block)
        self.assertNotIn("path.unlink(missing_ok=True)", block)

    def test_main_activity_has_no_legacy_saf_scan_guard_reference(self):
        source = (ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt").read_text(encoding="utf-8")
        self.assertNotIn("tryBeginNativeScan", source)
        self.assertIn('NativeScanController.begin(scanId, scanKey)', source)

    def test_main_has_single_os_import_for_storage_configuration(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertEqual(source.count("import os"), 1)

if __name__ == "__main__": unittest.main()
