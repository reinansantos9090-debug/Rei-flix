import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN_ACTIVITY = ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt"
PLAYER_ACTIVITY = ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/NativePlayerActivity.kt"
MAIN_PY = ROOT / "main.py"
BRIDGE = ROOT / "core/android_bridge.py"
SCAN = ROOT / "core/scan_coordinator.py"
STORE = ROOT / "core/library_store.py"
SERVICE = ROOT / "core/library_service.py"
HOME = ROOT / "views/home_view.py"
ORGANIZE = ROOT / "views/organize_view.py"


class LifecycleContractTests(unittest.TestCase):
    def test_main_activity_restores_recreation_state_and_limits_scan_cancel_to_true_finish(self):
        source = MAIN_ACTIVITY.read_text(encoding="utf-8")
        for token in (
            "override fun onSaveInstanceState(outState: Bundle)",
            "STATE_PENDING_PLAY_URI",
            "STATE_PENDING_PLAY_POSITION_MS",
            "STATE_ACTIVE_PLAYER_REQUEST_ID",
            "STATE_SEEN_NATIVE_REQUEST_IDS",
            "override fun onNewIntent(intent: Intent)",
            "override fun onConfigurationChanged",
            "if (isFinishing) NativeScanController.cancelAll()",
        ):
            self.assertIn(token, source)
        self.assertNotIn("if (isFinishing || isChangingConfigurations) NativeScanController.cancelAll()", source)

    def test_long_running_native_scan_batch_helper_is_not_bound_to_activity_instance(self):
        source = MAIN_ACTIVITY.read_text(encoding="utf-8")
        batch = source.index("private fun publishNativeScanBatch")
        helper_end = source.index("    /** Native lifecycle/observer", batch)
        helper = source[batch:helper_end]
        self.assertIn("appContext: Context", helper)
        self.assertNotIn("this@", helper)
        self.assertIn("LOG_TAG", helper)
        self.assertNotIn("tag,", helper)
        self.assertIn("NativeMailbox.writeOrThrow", helper)

    def test_saf_inventory_is_process_guarded_and_does_not_retain_activity(self):
        source = MAIN_ACTIVITY.read_text(encoding="utf-8")
        start = source.index("private fun publishSafInventory()")
        end = source.index("private fun handleBroadSettingsReturn", start)
        block = source[start:end]
        self.assertIn("safInventoryInFlight.compareAndSet(false, true)", block)
        self.assertIn("val appContext = applicationContext", block)
        self.assertIn("val lifecycleSnapshot = if (activityResumed)", block)
        self.assertNotIn("this@MainActivity", block)
        self.assertIn("safInventoryInFlight.set(false)", block)
        self.assertIn("private val safInventoryInFlight = AtomicBoolean(false)", source)

    def test_main_activity_unregisters_lifecycle_listeners_and_debounced_callbacks(self):
        source = MAIN_ACTIVITY.read_text(encoding="utf-8")
        self.assertIn("unregisterStorageReceiver()", source)
        self.assertIn("MediaStoreScanner.stopChangeObserver(this)", source)
        self.assertIn("storageReceiverRegistered = false", source)
        self.assertIn("private val mediaStoreRetryHandler", source)
        self.assertIn("private val mediaStoreRetryScheduled = AtomicBoolean(false)", source)
        retry = source[source.index("private fun scheduleMediaStoreScanRequest"):source.index("private fun publishNativeScanBatch")]
        self.assertNotIn("this@MainActivity", retry)
        self.assertNotIn("activityResumed", retry)

    def test_python_mailbox_poller_is_stopped_when_flet_session_disconnects(self):
        source = MAIN_PY.read_text(encoding="utf-8")
        self.assertIn("native_poll_task = [None]", source)
        self.assertIn("def _handle_page_disconnect", source)
        self.assertIn("task.cancel()", source)
        self.assertIn("while ui_alive[0]:", source)
        self.assertIn("native_poll_task[0] = page.run_task(poll_native_bridge)", source)
        self.assertEqual(
            source.count("page.run_task(poll_native_bridge)"),
            1,
            "mailbox poller must be started through the tracked task handle exactly once",
        )

    def test_navigation_snapshot_is_durable_and_disconnect_guarded(self):
        source = MAIN_PY.read_text(encoding="utf-8")
        state_start = source.index("def _write_navigation_state")
        state_end = source.index("def restore_details_context", state_start)
        block = source[state_start:state_end]
        self.assertIn("handle.flush()", block)
        self.assertIn("os.fsync(handle.fileno())", block)
        self.assertIn('and ui_alive[0]', block)
        self.assertIn('if navigation_persist["closing"] or not ui_alive[0]:', block)

    def test_navigation_recovery_restores_reconstructible_view_state(self):
        source = MAIN_PY.read_text(encoding="utf-8")
        self.assertEqual(source.count("load_navigation_state("), 2)
        self.assertIn("load_navigation_state()\n", source)
        self.assertIn('"version": 2', source)
        self.assertIn('"home_state"', source)
        self.assertIn('"organize_state"', source)
        self.assertIn('"settings_state"', source)
        self.assertIn('"details_media_id"', source)
        self.assertIn("json.dump(state", source)
        self.assertIn("os.replace(temporary, navigation_state_path)", source)

    def test_player_recreation_releases_resources_and_preserves_restorable_state(self):
        source = PLAYER_ACTIVITY.read_text(encoding="utf-8")
        for token in (
            "override fun onSaveInstanceState(outState: Bundle)",
            'outState.putLong("position_ms"',
            'outState.putFloat("playback_speed"',
            'outState.putBoolean("play_when_ready"',
            'outState.putBundle("track_selection_parameters"',
            'outState.putInt("resize_mode"',
            "handler.removeCallbacks(progressReporter)",
            "handler.removeCallbacks(controlsHider)",
            "handler.removeCallbacks(feedbackHider)",
            "pendingPreparation?.cancel(true)",
            "playbackWorker.shutdownNow()",
            "player.release()",
        ):
            self.assertIn(token, source)
        self.assertIn("&& !isChangingConfigurations", source)

    def test_player_async_and_media_callbacks_are_generation_guarded(self):
        source = PLAYER_ACTIVITY.read_text(encoding="utf-8")
        for token in (
            "playerGeneration",
            "beginPlayerGeneration",
            "generation == playerGeneration && sessionState == SessionState.ACTIVE",
            "isCurrentPreparation(generation, localUri)",
            "pendingPreparation?.cancel(true)",
            "activePlayerListener?.let { player.removeListener(it) }",
            "activeAnalyticsListener?.let { player.removeAnalyticsListener(it) }",
        ):
            self.assertIn(token, source)

    def test_native_mailbox_recovery_requeues_before_acknowledgement(self):
        bridge = BRIDGE.read_text(encoding="utf-8")
        main = MAIN_PY.read_text(encoding="utf-8")
        self.assertIn("source.replace(consumed)", bridge)
        self.assertIn("consumed.replace(consumed.with_suffix(\".json\"))", bridge)
        self.assertIn("def requeue_event_ids", bridge)
        self.assertIn("def acknowledge", bridge)
        self.assertIn("bridge.requeue_event_ids(failed_event_ids)", main)
        self.assertIn("bridge.acknowledge()", main)
        self.assertLess(
            main.index("bridge.requeue_event_ids(failed_event_ids)"),
            main.index("bridge.acknowledge()"),
        )
        self.assertIn("store.has_native_event(event_id)", main)
        self.assertIn("store.claim_native_event(event_id)", main)

    def test_scan_coordinator_serializes_mutations_and_matches_cancelled_operations(self):
        source = SCAN.read_text(encoding="utf-8")
        for token in (
            "self._lock = asyncio.Lock()",
            "self._active_request: ScanRequest | None = None",
            "self._pending",
            "self._cancel_requested",
            "async def cancel(self)",
            "await self.bridge.cancel_scans()",
            "async def handle_native_event",
        ):
            self.assertIn(token, source)

    def test_catalog_and_progress_recovery_do_not_convert_partial_failures_into_deletion(self):
        store = STORE.read_text(encoding="utf-8")
        service = SERVICE.read_text(encoding="utf-8")
        for token in (
            "def mark_source_unavailable",
            "state='scope_unavailable'",
            "def restore_source",
            "def interrupted_scans",
            "def recover_interrupted_scans",
            "episode_observations",
            "scan_runs",
        ):
            self.assertIn(token, store)
        self.assertIn("only a trusted COMPLETE generation reconciles", service)
        self.assertIn("final_status", service)
        progress_start = store.index("def save_progress")
        progress_block = store[progress_start:progress_start + 4200]
        self.assertIn("event_created_at", progress_block)
        self.assertIn("if event_time <= last_seen", progress_block)
        self.assertIn("durable_time", progress_block)

    def test_thumbnail_callbacks_are_media_version_guarded(self):
        source = MAIN_PY.read_text(encoding="utf-8")
        start = source.index("elif event_type == 'thumbnail_ready':")
        end = source.index("elif event_type == 'player_opened':", start)
        block = source[start:end]
        self.assertIn("thumbnail_key = (uri, size, modified_at)", block)
        self.assertIn("pending_same_uri = any(key[0] == uri for key in thumbnail_requests)", block)
        self.assertIn("if pending_same_uri and thumbnail_key not in thumbnail_requests:", block)
        self.assertIn("thumbnail_requests.discard(thumbnail_key)", block)
        self.assertNotIn("for key in thumbnail_requests if key[0] == uri", block)

    def test_python_stale_screen_work_is_generation_guarded(self):
        home = HOME.read_text(encoding="utf-8")
        organize = ORGANIZE.read_text(encoding="utf-8")
        for token in (
            "render_generation = [0]",
            "search_generation = [0]",
            "if token != render_generation[0]:",
        ):
            self.assertIn(token, home)
        for token in (
            "render_generation = [0]",
            "search_generation = [0]",
            "if token != search_generation[0]:",
        ):
            self.assertIn(token, organize)


    def test_main_activity_background_scan_jobs_do_not_use_activity_bound_job_registry(self):
        source = MAIN_ACTIVITY.read_text(encoding="utf-8")
        self.assertNotIn("activeNativeScanJobs", source)
        self.assertNotIn("private val activeNativeScanJobs", source)
        self.assertNotIn("mutableMapOf<String, Job>()", source)

    def test_media_store_delayed_retry_does_not_capture_activity_instance(self):
        source = MAIN_ACTIVITY.read_text(encoding="utf-8")
        self.assertIn("scheduleMediaStoreScanRequest(", source)
        self.assertIn("private fun scheduleMediaStoreScanRequest", source)
        retry_start = source.index("private fun scheduleMediaStoreScanRequest")
        retry_end = source.index("private fun publishNativeScanBatch", retry_start)
        retry_block = source[retry_start:retry_end]
        self.assertNotIn("this@MainActivity", retry_block)
        self.assertNotIn("activityResumed", retry_block)
        self.assertIn("NativeMailbox.write(", retry_block)
        self.assertIn("appContext", retry_block)

    def test_player_pip_exit_respects_immersive_policy(self):
        source = PLAYER_ACTIVITY.read_text(encoding="utf-8")
        pip_start = source.index("override fun onPictureInPictureModeChanged")
        pip_end = source.index("override fun onConfigurationChanged", pip_start)
        pip_block = source[pip_start:pip_end]
        self.assertIn("applyImmersiveAfterLayout()", pip_block)
        self.assertNotIn("} else {\n            enterImmersiveMode()", pip_block)

if __name__ == "__main__":
    unittest.main()
