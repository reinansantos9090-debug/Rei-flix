import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAYER = ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/NativePlayerActivity.kt"


class Prompt13NativePlayerLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.player = PLAYER.read_text(encoding="utf-8")

    def test_single_exoplayer_creation_and_release_contract(self):
        self.assertEqual(1, self.player.count("ExoPlayer.Builder(this).build()"))
        self.assertIn("playerView.player = player", self.player)
        self.assertIn("if (::playerView.isInitialized && playerView.player === player)", self.player)
        self.assertIn("playerView.player = null", self.player)
        self.assertIn("player.release()", self.player)

    def test_player_listeners_are_replaced_per_generation(self):
        self.assertIn("activePlayerListener?.let { player.removeListener(it) }", self.player)
        self.assertIn("activeAnalyticsListener?.let { player.removeAnalyticsListener(it) }", self.player)
        self.assertIn("activePlayerListener = createPlayerListener(generation)", self.player)
        self.assertIn("activeAnalyticsListener = createAnalyticsListener(generation)", self.player)
        self.assertIn("player.addListener(activePlayerListener!!)", self.player)
        self.assertIn("player.addAnalyticsListener(activeAnalyticsListener!!)", self.player)

    def test_stale_async_preparation_cannot_touch_current_player_generation(self):
        self.assertIn("pendingPreparation?.cancel(true)", self.player)
        self.assertIn("generation == playerGeneration", self.player)
        self.assertIn("sessionState == SessionState.ACTIVE", self.player)
        self.assertIn("uri == localUri", self.player)
        self.assertIn("if (!isCurrentPreparation(generation, localUri)) return@post", self.player)

    def test_resume_is_applied_once_after_ready(self):
        ready = self.player[
            self.player.index("Player.STATE_READY -> {"):
            self.player.index("Player.STATE_BUFFERING -> {")
        ]
        self.assertIn("if (!initialSeekApplied)", ready)
        self.assertIn("seekToSavedPosition(restoredPositionMs ?: savedPosition)", ready)
        self.assertIn("initialSeekApplied = true", ready)
        self.assertEqual(1, ready.count("seekToSavedPosition(restoredPositionMs ?: savedPosition)"))

    def test_background_lifecycle_pauses_without_affecting_pip(self):
        stop = self.player[
            self.player.index("override fun onStop()"):
            self.player.index("override fun onWindowFocusChanged")
        ]
        resume = self.player[
            self.player.index("override fun onResume()"):
            self.player.index("override fun onPause()")
        ]
        self.assertIn("!inPictureInPicture", stop)
        self.assertIn("playbackWasRequestedBeforeStop", stop)
        self.assertIn("player.pause()", stop)
        self.assertIn("PLAYER_BACKGROUND_PAUSE", stop)
        self.assertIn("!inPictureInPicture", resume)
        self.assertIn("playbackWasRequestedBeforeStop", resume)
        self.assertIn("player.playWhenReady = true", resume)
        self.assertIn("PLAYER_FOREGROUND_RESUME", resume)

    def test_completion_does_not_create_a_second_player_or_playlist(self):
        playback = self.player[
            self.player.index("override fun onPlaybackStateChanged"):
            self.player.index("override fun onPlaybackParametersChanged")
        ]
        self.assertIn("Player.STATE_ENDED -> {", playback)
        self.assertIn('saveProgress("player_completed", force = true)', playback)
        self.assertIn('requestEpisode("player_next_request")', playback)
        self.assertNotIn("ExoPlayer.Builder(this).build()", playback)
        self.assertNotIn("player.setMediaItems(", self.player)
        self.assertNotIn("player.addMediaItem(", self.player)

    def test_media3_commands_are_dispatched_from_ui_handler_after_io_preflight(self):
        prepare = self.player[
            self.player.index("private fun prepareCurrentMedia"):
            self.player.index("private fun createPlayerListener")
        ]
        self.assertIn("playbackWorker.submit", prepare)
        self.assertIn("handler.post {", prepare)
        self.assertIn("player.setMediaItem(mediaItem)", prepare)
        self.assertIn("player.prepare()", prepare)

    def test_first_frame_is_generation_correlated(self):
        self.assertIn("generation == playerGeneration && sessionState == SessionState.ACTIVE", self.player)
        self.assertIn("events.contains(Player.EVENT_RENDERED_FIRST_FRAME)", self.player)
        self.assertIn("armFirstFrameDiagnostics(generation)", self.player)
        self.assertIn("cancelFirstFrameDiagnostics("first_frame")", self.player)


if __name__ == "__main__":
    unittest.main()
