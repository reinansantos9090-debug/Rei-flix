import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
BRIDGE = ROOT / "core/android_bridge.py"
MAIN_ACTIVITY = ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt"
PLAYER = ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/NativePlayerActivity.kt"
REQUEST = ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/NativePlayerRequest.kt"


class Prompt24PreviousTransitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.bridge = BRIDGE.read_text(encoding="utf-8")
        cls.main_activity = MAIN_ACTIVITY.read_text(encoding="utf-8")
        cls.player = PLAYER.read_text(encoding="utf-8")
        cls.request = REQUEST.read_text(encoding="utf-8")

    def previous_transition_block(self):
        start = self.main.index("elif event_type in {'player_next_request', 'player_previous_request'}:")
        end = self.main.index("elif event_type == 'player_error':", start)
        return self.main[start:end]

    def test_previous_state_machine_has_all_required_markers(self):
        required = (
            "PREVIOUS_REQUEST_RECEIVED",
            "PREVIOUS_REQUEST_ACCEPTED",
            "PREVIOUS_REQUEST_REJECTED",
            "PREVIOUS_REQUEST_STALE",
            "PREVIOUS_REQUEST_DUPLICATE",
            "PREVIOUS_REQUEST_CANCELLED",
            "PREVIOUS_TRANSITION_STARTED",
            "PREVIOUS_TRANSITION_INVALIDATED",
            "PREVIOUS_TRANSITION_READY",
            "PREVIOUS_TRANSITION_FIRST_FRAME",
            "PREVIOUS_TRANSITION_COMMITTED",
            "PREVIOUS_TRANSITION_FAILED",
        )
        source = self.main + self.player + self.main_activity
        for token in required:
            self.assertIn(token, source)

    def test_previous_is_single_flight_with_no_pending_queue(self):
        block = self.previous_transition_block()
        self.assertIn("player_transition_inflight["value"]", block)
        self.assertIn("episodeChangePending", self.player)
        self.assertIn("pending_previous_transition", self.main)
        self.assertIn("PREVIOUS_REQUEST_DUPLICATE", block)
        self.assertNotIn("append(", block)
        self.assertNotIn("queue.append(", block)

    def test_previous_and_next_share_the_same_generation_gate(self):
        block = self.previous_transition_block()
        self.assertIn('"python_transition_generation": transition_generation', block)
        self.assertIn("player_transition_generation["value"] += 1", block)
        self.assertIn('"NEXT_REQUEST_STALE" if is_next else "PREVIOUS_REQUEST_STALE"', block)
        self.assertIn('"PLAYER_NEXT_STALE_REJECTED" if is_next else "PLAYER_PREVIOUS_STALE_REJECTED"', block)

    def test_previous_requires_an_active_player_session(self):
        block = self.previous_transition_block()
        self.assertIn('if not player_session_active["value"]:', block)
        self.assertIn('"player_session_not_active"', block)
        self.assertIn("player_active_session_id["value"]", block)
        self.assertIn("source_player_session_id", block)

    def test_previous_is_rejected_after_player_exit(self):
        block = self.previous_transition_block()
        exit_handler = self.main[
            self.main.index("elif event_type == 'player_exited':"):
            self.main.index("elif event_type == 'google_sign_in_started':")
        ]
        self.assertIn('cancel_player_transition("player_exited")', exit_handler)
        self.assertIn('player_session_active["value"] = False', exit_handler)
        self.assertIn('player_active_session_id["value"] = None', exit_handler)
        self.assertIn('"player_session_not_active"', block)

    def test_previous_cannot_cross_into_a_new_player_session(self):
        block = self.previous_transition_block()
        self.assertIn('"reason": "player_session_mismatch"', block)
        self.assertIn("PLAYER_PREVIOUS_STALE_REJECTED", block)
        self.assertIn("origin_player_session_id", self.main_activity + self.player)

    def test_previous_request_identity_carries_monotonic_time_and_direction(self):
        self.assertIn('"monotonicNs"', self.player)
        self.assertIn('"transitionDirection"', self.player)
        self.assertIn("originMonotonicNs", self.player)
        self.assertIn("origin_monotonic_ns", self.bridge)
        self.assertIn("transition_direction", self.bridge)
        self.assertIn("originMonotonicNs", self.request)
        self.assertIn("transitionDirection", self.request)

    def test_bridge_preserves_previous_direction_and_origin(self):
        self.assertIn("transition_direction", self.bridge)
        self.assertIn("origin_monotonic_ns", self.bridge)
        self.assertIn('origin_player_session_id=str(origin_player_session_id)', self.bridge)
        self.assertIn('transitionDirection', self.request)

    def test_previous_uses_canonical_neighbor_lookup(self):
        block = self.previous_transition_block()
        self.assertIn("library.player_navigation", block)
        self.assertNotIn("episode.number - 1", block)
        self.assertNotIn("episode_number - 1", block)

    def test_previous_sqlite_trace_and_stale_result_fencing_exist(self):
        block = self.previous_transition_block()
        self.assertIn("PREVIOUS_SQLITE_QUERY_STARTED", block)
        self.assertIn("PREVIOUS_SQLITE_QUERY_FINISHED", block)
        self.assertIn("current_row_id", block)
        self.assertIn("current_row_anime", block)
        self.assertIn("current_row_path", block)
        self.assertIn("pending_context_replaced", block)

    def test_previous_no_target_invalidates_the_transition(self):
        block = self.previous_transition_block()
        self.assertIn('"no_target"', block)
        self.assertIn('cancel_player_transition("next_no_target" if is_next else "previous_no_target")', block)
        self.assertIn('"PREVIOUS_TRANSITION_FAILED"', block)

    def test_first_episode_previous_is_explicitly_rejected(self):
        request = self.player[
            self.player.index("private fun requestEpisode"):
            self.player.index("private fun seekToSavedPosition")
        ]
        self.assertIn('"canPrevious"', request)
        self.assertIn('"no_previous_episode"', request)

    def test_previous_ready_waits_for_first_frame_before_commit(self):
        ready = self.player[
            self.player.index("Player.STATE_READY -> {"):
            self.player.index("Player.STATE_BUFFERING -> {")
        ]
        first_frame = self.player[
            self.player.index('if (events.contains(Player.EVENT_RENDERED_FIRST_FRAME))'):
            self.player.index("override fun onMediaItemTransition")
        ]
        self.assertIn("PREVIOUS_TRANSITION_READY", ready)
        self.assertNotIn("PREVIOUS_TRANSITION_COMMITTED", ready)
        self.assertIn("PREVIOUS_TRANSITION_FIRST_FRAME", first_frame)
        self.assertIn("PREVIOUS_TRANSITION_COMMITTED", first_frame)

    def test_media3_item_transition_is_not_used_as_navigation_confirmation(self):
        start = self.player.index("override fun onMediaItemTransition")
        end = self.player.index("override fun onPlaybackStateChanged", start)
        block = self.player[start:end]
        self.assertIn("MEDIA_ITEM_TRANSITION", block)
        self.assertNotIn("PREVIOUS_TRANSITION_COMMITTED", block)
        self.assertNotIn("NEXT_TRANSITION_COMMITTED", block)

    def test_previous_timeout_is_diagnostic_only_and_context_bound(self):
        start = self.player.index("private val episodeChangeTimeout")
        end = self.player.index("private var retryCount", start)
        watchdog = self.player[start:end]
        self.assertIn("PREVIOUS_TRANSITION_STALLED", watchdog)
        self.assertIn("episodeChangeTimeoutRequestId != requestId", watchdog)
        self.assertIn("episodeChangeTimeoutUri != uri.toString()", watchdog)
        self.assertIn("episodeChangeTimeoutGeneration != transitionSourceGeneration", watchdog)
        self.assertIn("episodeChangeTimeoutGeneration != transitionGeneration", watchdog)
        self.assertNotIn("episodeChangePending = false", watchdog)

    def test_previous_invalidation_revokes_direction_state(self):
        block = self.player[
            self.player.index("private fun invalidateTransition"):
            self.player.index("private fun isCurrentTransition")
        ]
        self.assertIn("val wasPrevious = previousTransitionActive", block)
        self.assertIn("PREVIOUS_TRANSITION_INVALIDATED", block)
        self.assertIn("PREVIOUS_REQUEST_CANCELLED", block)
        self.assertIn("previousTransitionActive = false", block)
        self.assertIn('transitionSourceDirection = ""', block)
        self.assertIn("transitionSourceMonotonicNs = 0L", block)

    def test_previous_activity_reuse_requires_matching_origin_generation_session_direction_and_monotonic(self):
        reuse = self.player[
            self.player.index("val expectedSuccessorBeforeMutation"):
            self.player.index("autoplayNext =", self.player.index("val expectedSuccessorBeforeMutation"))
        ]
        for token in (
            "incomingOriginTransitionGeneration == transitionPendingGeneration",
            "incomingOriginPlayerSessionId == playerSessionId",
            "incomingOriginMonotonicNs == transitionSourceMonotonicNs",
            "incomingOriginTransitionDirection == transitionSourceDirection",
        ):
            self.assertIn(token, reuse)

    def test_previous_origin_into_new_activity_is_rejected(self):
        create = self.player[
            self.player.index("override fun onCreate(savedInstanceState"):
            self.player.index("val traceEpisodeId")
        ]
        self.assertIn("originRequestId.isNotBlank()", create)
        self.assertIn("PREVIOUS_REQUEST_STALE", create)
        self.assertIn("PLAYER_PREVIOUS_STALE_REJECTED", create)
        self.assertIn("finish()", create)
        self.assertIn("origin_on_new_activity", create)

    def test_previous_prepare_callbacks_are_transition_generation_bound(self):
        self.assertIn("expectedTransitionGeneration", self.player)
        self.assertIn("transitionGeneration == expectedTransitionGeneration", self.player)
        self.assertIn("preparationTransitionGeneration", self.player)
        self.assertIn("isCurrentPreparation(generation, localUri, preparationTransitionGeneration)", self.player)

    def test_previous_progress_save_is_for_current_episode(self):
        request = self.player[
            self.player.index("private fun requestEpisode"):
            self.player.index("private fun seekToSavedPosition")
        ]
        self.assertIn('saveProgress("player_progress", force = true)', request)
        self.assertIn('.put("episodeId", currentEpisodeId())', request)
        self.assertIn('.put("animeId", intent.getStringExtra("animeId").orEmpty())', request)

    def test_previous_error_cancels_the_matching_pending_context(self):
        error = self.main[
            self.main.index("elif event_type == 'player_error':"):
            self.main.index("elif event_type == 'player_exited':")
        ]
        self.assertIn('("PREVIOUS", pending_previous_transition["value"])', error)
        self.assertIn("PREVIOUS_TRANSITION_FAILED", error)
        self.assertIn('cancel_player_transition("player_error")', error)

    def test_previous_exit_recreation_has_no_path_back_to_old_request(self):
        self.assertIn("player_session_not_active", self.main)
        self.assertIn("player_session_mismatch", self.main)
        self.assertIn("PLAYER_PREVIOUS_STALE_REJECTED", self.main_activity + self.player + self.main)
        self.assertIn("originOnNewActivity", self.player) if "originOnNewActivity" in self.player else self.assertIn("origin_on_new_activity", self.player)

    def test_previous_and_next_interactions_are_direction_fenced(self):
        block = self.previous_transition_block()
        self.assertIn("direction_name", block)
        self.assertIn("NEXT_REQUEST_REJECTED" if True else "", block)
        self.assertIn("PREVIOUS_REQUEST_REJECTED", block)
        self.assertIn("NEXT_REQUEST_STALE", block)
        self.assertIn("PREVIOUS_REQUEST_STALE", block)

    def test_previous_logs_are_not_time_based_stale_rejections(self):
        block = self.previous_transition_block()
        self.assertNotIn("mailbox_latency_ms > 5000", block)
        self.assertNotIn("mailbox_latency_ms >= 5000", block)

    def test_previous_tests_are_sleep_free(self):
        source = Path(__file__).read_text(encoding="utf-8")
        self.assertNotIn("time.sleep(", source)
        self.assertNotIn("asyncio.sleep(", source)
        self.assertNotIn("sleep(", source)


if __name__ == "__main__":
    unittest.main()
