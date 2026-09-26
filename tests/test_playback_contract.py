import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAYER = ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/NativePlayerActivity.kt"
MANIFEST = ROOT / "android/app/src/main/AndroidManifest.xml"
MAIN = ROOT / "main.py"


class PlaybackContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.player = PLAYER.read_text(encoding="utf-8")
        cls.manifest = MANIFEST.read_text(encoding="utf-8")
        cls.main = MAIN.read_text(encoding="utf-8")

    def test_progress_events_use_existing_episode_identity_and_media3_state(self):
        for token in (
            '"mediaId", uri.toString()',
            '"episodeId", intent.getStringExtra("episodeId").orEmpty()',
            '"positionMs", position',
            '"durationMs", duration',
            '"playerState", if (::player.isInitialized) player.playbackStateLabel() else "STATE_IDLE"',
            '"isPlaying", if (::player.isInitialized) player.isPlaying else false',
            '"playbackSpeed", if (::player.isInitialized) player.playbackParameters.speed else 1f',
            'saveProgress("player_progress")',
            'saveProgress("player_paused", force = true)',
            'saveProgress("player_completed", force = true)',
        ):
            self.assertIn(token, self.player)

    def test_error_diagnostics_contain_required_runtime_context(self):
        for token in (
            '"timestamp", System.currentTimeMillis()',
            '"mediaId", if (::uri.isInitialized) uri.toString() else intent.getStringExtra("mediaId").orEmpty()',
            '"episodeId", intent.getStringExtra("episodeId").orEmpty()',
            '"playerState", if (::player.isInitialized) player.playbackStateLabel() else "STATE_IDLE"',
            '"isPlaying", if (::player.isInitialized) player.isPlaying else false',
            'private fun publishPlayerError',
            'player_error',
        ):
            self.assertIn(token, self.player)

    def test_consumption_pipeline_has_no_parallel_player_state(self):
        for token in (
            'ConsumptionState.UNWATCHED',
            'ConsumptionState.IN_PROGRESS',
            'ConsumptionState.COMPLETED',
            'ConsumptionState.WATCHED',
            'COMPLETION_RATIO = 0.90',
        ):
            consumption = (ROOT / "core/consumption.py").read_text(encoding="utf-8")
            self.assertIn(token, consumption)
        self.assertNotIn("PLAYER_COMPLETED", (ROOT / "core/consumption.py").read_text(encoding="utf-8"))

    def test_existing_python_event_consumer_updates_single_store(self):
        for token in (
            "elif event_type in {'player_progress', 'player_paused', 'player_completed'}:",
            "store.save_progress",
            "elif event_type == 'player_exited':",
            "library.next_episode(current_path)",
            "library.previous_episode(current_path)",
        ):
            self.assertIn(token, self.main)

    def test_audio_subtitle_speed_and_seek_stay_on_one_media3_player(self):
        for token in (
            'TrackSelectionDialogBuilder(this, label, player, trackType)',
            'player.setPlaybackSpeed',
            'player.playbackParameters.speed',
            'PlayerGesturePolicy.seekTarget',
            'player.trackSelectionParameters',
            'player.setAudioAttributes',
            'C.USAGE_MEDIA',
        ):
            self.assertIn(token, self.player)
        self.assertEqual(1, self.player.count("ExoPlayer.Builder(this).build()"))
        self.assertNotIn("ExoPlayer.Builder(this).build()", self.player[self.player.index("private fun showTrackSelection"):])

    def test_lifecycle_rotation_pip_and_exit_are_single_activity_contracts(self):
        for token in (
            'override fun onSaveInstanceState(outState: Bundle)',
            'override fun onConfigurationChanged',
            'override fun onPictureInPictureModeChanged',
            'saveProgress("player_progress", force = true)',
            'reportPlayerExit("activity_finish")',
            'if (sessionState == SessionState.DESTROYED || exitReported) return',
            'android:supportsPictureInPicture="true"',
        ):
            self.assertIn(token, self.player + self.manifest)

    def test_media3_state_machine_is_explicit(self):
        for token in (
            'Player.STATE_IDLE',
            'Player.STATE_BUFFERING',
            'Player.STATE_READY',
            'Player.STATE_ENDED',
            'onIsPlayingChanged(isPlaying: Boolean)',
            'onPlaybackStateChanged(state: Int)',
            'showPlayerError(',
        ):
            self.assertIn(token, self.player)


if __name__ == "__main__":
    unittest.main()
