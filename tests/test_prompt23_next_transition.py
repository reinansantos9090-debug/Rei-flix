import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
BRIDGE = ROOT / "core/android_bridge.py"
MAIN_ACTIVITY = ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt"
PLAYER = ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/NativePlayerActivity.kt"
REQUEST = ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/NativePlayerRequest.kt"


class Prompt23NextTransitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.bridge = BRIDGE.read_text(encoding="utf-8")
        cls.main_activity = MAIN_ACTIVITY.read_text(encoding="utf-8")
        cls.player = PLAYER.read_text(encoding="utf-8")
        cls.request = REQUEST.read_text(encoding="utf-8")

    def test_required_next_state_machine_markers_exist(self):
        for token in (
            "NEXT_REQUEST_ACCEPTED",
            "NEXT_REQUEST_REJECTED",
            "NEXT_REQUEST_STALE",
            "NEXT_REQUEST_DUPLICATE",
            "NEXT_REQUEST_CANCELLED",
            "NEXT_TRANSITION_STARTED",
            "NEXT_TRANSITION_INVALIDATED",
            "NEXT_TRANSITION_READY",
            "NEXT_TRANSITION_FIRST_FRAME",
            "NEXT_TRANSITION_COMMITTED",
            "NEXT_TRANSITION_FAILED",
            "PLAYER_NEXT_STALE_REJECTED",
        ):
            self.assertIn(token, self.main + self.player + self.main_activity)

    def test_native_timeout_is_diagnostic_only(self):
        start = self.player.index("private val episodeChangeTimeout")
        end = self.player.index("private var retryCount", start)
        watchdog = self.player[start:end]
        self.assertIn("NEXT_TRANSITION_STALLED", watchdog)
        self.assertIn("diagnostic-only", watchdog)
        next_branch = watchdog[watchdog.index("if (nextTransitionActive)"):watchdog.index("} else {", watchdog.index("if (nextTransitionActive)"))]
        self.assertNotIn("episodeChangePending = false", next_branch)

    def test_native_next_is_single_flight_and_session_scoped(self):
        start = self.player.index("private fun requestEpisode")
        end = self.player.index("private fun seekToSavedPosition", start)
        request = self.player[start:end]
        self.assertIn("episodeChangePending", request)
        self.assertIn("NEXT_REQUEST_DUPLICATE", request)
        self.assertIn("NEXT_REQUEST_ACCEPTED", request)
        self.assertIn("NEXT_TRANSITION_STARTED", request)
        self.assertIn("playerSessionId", request)
        self.assertIn("transitionGeneration", request)

    def test_transition_identity_checks_request_uri_generation_and_session(self):
        start = self.player.index("private fun isCurrentTransition")
        end = self.player.index("private fun requestEpisode", start)
        block = self.player[start:end]
        for token in (
            "generation == transitionGeneration",
            "requestId == expectedRequestId",
            "uri.toString() == expectedUri",
            "playerSessionId == expectedSessionId",
            "sessionState == SessionState.ACTIVE",
        ):
            self.assertIn(token, block)

    def test_reuse_requires_original_player_session(self):
        reuse = self.player[
            self.player.index("val expectedSuccessor"):
            self.player.index("autoplayNext =", self.player.index("val expectedSuccessor"))
        ]
        self.assertIn("originPlayerSessionId.isNotBlank()", reuse)
        self.assertIn("originPlayerSessionId == playerSessionId", reuse)

    def test_ready_does_not_commit_and_first_frame_does(self):
        ready_start = self.player.index("Player.STATE_READY -> {")
        ready_end = self.player.index("Player.STATE_BUFFERING -> {", ready_start)
        ready = self.player[ready_start:ready_end]
        next_ready_start = ready.index("nextTransitionActive &&")
        next_ready_end = ready.index("if (\n                        !nextTransitionActive", next_ready_start)
        next_ready = ready[next_ready_start:next_ready_end]
        self.assertIn("NEXT_TRANSITION_READY", next_ready)
        self.assertNotIn("EPISODE_CHANGE_COMMITTED", next_ready)

        first_start = self.player.index('if (events.contains(Player.EVENT_RENDERED_FIRST_FRAME))')
        first_end = self.player.index("override fun onMediaItemTransition", first_start)
        first = self.player[first_start:first_end]
        self.assertIn("NEXT_TRANSITION_FIRST_FRAME", first)
        self.assertIn("NEXT_TRANSITION_COMMITTED", first)
        self.assertIn("EPISODE_CHANGE_COMMITTED", first)

    def test_python_next_has_pre_sqlite_post_sqlite_and_pre_bridge_guards(self):
        transition = self.main[
            self.main.index("elif event_type in {'player_next_request', 'player_previous_request'}:"):
            self.main.index("elif event_type == 'player_error':")
        ]
        self.assertIn("source_player_session_id", transition)
        self.assertIn("await asyncio.to_thread(", transition)
        self.assertIn("library.player_navigation", transition)
        self.assertIn("current_row_id", transition)
        self.assertIn("transition_guard=current_is_valid", transition)
        self.assertIn("target_request_id = await start_native_player", transition)

    def test_python_cancellation_invalidates_pending_next_without_canceling_itself(self):
        start = self.main.index("def cancel_player_transition")
        end = self.main.index("async def start_native_player", start)
        block = self.main[start:end]
        self.assertIn("current_task = asyncio.current_task()", block)
        self.assertIn("task is not current_task", block)
        self.assertIn("pending_next_transition", block)
        self.assertIn("NEXT_TRANSITION_INVALIDATED", block)
        self.assertIn("NEXT_REQUEST_CANCELLED", block)

    def test_new_activity_rejects_nonempty_next_origin(self):
        start = self.player.index("override fun onCreate(savedInstanceState")
        end = self.player.index("val traceEpisodeId", start)
        create = self.player[start:end]
        self.assertIn("originRequestId.isNotBlank()", create)
        self.assertIn('NEXT_REQUEST_STALE', create)
        self.assertIn('PLAYER_NEXT_STALE_REJECTED', create)
        self.assertIn('origin_on_new_activity', create)
        self.assertIn("finish()", create)
        self.assertIn("suppressExitEvent = true", create)

    def test_activity_exit_and_recreation_have_native_session_authorization(self):
        for token in (
            "notePlayerSession",
            "notePlayerExit",
            "activePlayerSessionId",
            "stale_origin_player_session",
            "lastPlayerExitAtMs",
            "PLAYER_NEXT_STALE_REJECTED",
        ):
            self.assertIn(token, self.main_activity)
        self.assertIn("originPlayerSessionId", self.request)
        self.assertIn('putExtra("originPlayerSessionId", originPlayerSessionId)', self.request)
        self.assertIn("originPlayerSessionId", self.player)
        self.assertIn("MainActivity.notePlayerSession", self.player)
        self.assertIn("MainActivity.notePlayerExit", self.player)

    def test_bridge_propagates_origin_player_session(self):
        self.assertIn("origin_player_session_id", self.bridge)
        self.assertIn("created_monotonic_ns", self.bridge)
        self.assertIn('expected_event = "PLAYER_HANDOFF_DISPATCHED" if action == "play"', self.bridge)

    def test_no_time_based_stale_rejection_for_active_slow_transition(self):
        transition = self.main[
            self.main.index("elif event_type in {'player_next_request', 'player_previous_request'}:"):
            self.main.index("elif event_type == 'player_error':")
        ]
        self.assertIn("mailbox_latency_ms", transition)
        self.assertNotIn("mailbox_latency_ms > 5000", transition)
        self.assertNotIn("mailbox_latency_ms >= 5000", transition)

    def test_next_stale_logs_carry_origin_and_current_generation(self):
        for source in (self.main, self.player, self.main_activity):
            if "PLAYER_NEXT_STALE_REJECTED" in source:
                self.assertTrue("origin_generation" in source or "originGeneration" in source)
                self.assertTrue("current_generation" in source or "currentGeneration" in source)

    def test_tests_are_sleep_free(self):
        source = Path(__file__).read_text(encoding="utf-8")
        self.assertNotIn("time.sleep(", source)
        self.assertNotIn("asyncio.sleep(", source)


if __name__ == "__main__":
    unittest.main()
