import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAYER = ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/NativePlayerActivity.kt"
LAYOUT = ROOT / "android/app/src/main/res/layout/native_player_view.xml"


class Prompt3PlayerReconstructionTests(unittest.TestCase):
    def setUp(self):
        self.player = PLAYER.read_text(encoding="utf-8")
        self.layout = LAYOUT.read_text(encoding="utf-8")

    def test_responsive_player_uses_native_layout_and_weighted_controls(self):
        self.assertIn("R.layout.native_player_view", self.player)
        self.assertIn("FrameLayout.LayoutParams.MATCH_PARENT", self.player)
        self.assertIn("LinearLayout.LayoutParams(0, dp(48), 1f)", self.player)
        self.assertIn("LinearLayout.LayoutParams(0, dp(40), 1f)", self.player)
        self.assertIn('app:surface_type="texture_view"', self.layout)
        self.assertNotIn("x = 500", self.player)
        self.assertNotIn("y = 1100", self.player)

    def test_auto_hide_has_one_shared_handler_runnable(self):
        self.assertIn("private val controlsHider = object : Runnable", self.player)
        self.assertIn("handler.removeCallbacks(controlsHider)", self.player)
        self.assertIn("handler.postDelayed(controlsHider", self.player)
        self.assertIn("autoHideTimeoutMs", self.player)

    def test_single_double_and_pinch_gesture_arbitration(self):
        for token in (
            "ScaleGestureDetector",
            "GestureDetector",
            "PLAYER_SINGLE_TAP",
            "PLAYER_DOUBLE_TAP",
            "gestureConsumed",
            "pinchActive",
            "horizontal_ignored",
            "vertical_ignored_or_applied",
        ):
            self.assertIn(token, self.player)
        self.assertNotIn("HORIZONTAL_SEEK", self.player)
        self.assertNotIn("GestureMode.HORIZONTAL_SEEK", self.player)

    def test_double_tap_seek_is_enabled_by_default_and_uses_configured_delta(self):
        self.assertIn("private var doubleTapEnabled = true", self.player)
        self.assertIn("PREF_GESTURES_DOUBLE_TAP, true", self.player)
        self.assertIn("doubleTapSeekMs", self.player)
        self.assertIn("seekBy(-doubleTapSeekMs", self.player)
        self.assertIn("seekBy(doubleTapSeekMs", self.player)
        self.assertIn("showFeedback(feedbackText)", self.player)

    def test_zoom_is_bounded_symmetric_and_pan_is_clamped(self):
        self.assertIn("private const val MAX_ZOOM = 3f", self.player)
        self.assertIn("scaleX = zoomScale", self.player)
        self.assertIn("scaleY = zoomScale", self.player)
        self.assertIn("zoomTranslationX = zoomTranslationX.coerceIn(-maxTx, maxTx)", self.player)
        self.assertIn("zoomTranslationY = zoomTranslationY.coerceIn(-maxTy, maxTy)", self.player)
        self.assertIn("resetZoomToFit", self.player)

    def test_resize_modes_expose_fit_fill_and_zoom_without_stretch(self):
        self.assertIn('arrayOf("Ajustar", "Preencher", "Zoom")', self.player)
        self.assertIn('"Preencher", "Zoom" -> AspectRatioFrameLayout.RESIZE_MODE_ZOOM', self.player)
        self.assertIn('else -> AspectRatioFrameLayout.RESIZE_MODE_FIT', self.player)
        self.assertNotIn("scaleX != scaleY", self.player)

    def test_speed_audio_subtitle_and_seekbar_reflect_real_player(self):
        self.assertIn('actionButton("1.0x"', self.player)
        self.assertIn("onPlaybackParametersChanged", self.player)
        self.assertIn('findViewByTag<TextView>("reiflix_speed_button")', self.player)
        self.assertIn("val audioAvailable = audioCount > 0", self.player)
        self.assertIn("TrackSelectionDialogBuilder", self.player)
        self.assertIn("SEEK_PROGRESS_MAX", self.player)
        self.assertIn("PROGRESS_INTERVAL_MS = 250L", self.player)
        self.assertIn("PROGRESS_PERSIST_INTERVAL_MS = 15_000L", self.player)

    def test_buffering_error_and_first_frame_are_separate_ui_states(self):
        self.assertIn("Player.STATE_BUFFERING", self.player)
        self.assertIn("preparingIndicator.visibility = View.VISIBLE", self.player)
        self.assertIn("Player.EVENT_RENDERED_FIRST_FRAME", self.player)
        self.assertIn("preparingIndicator.visibility = View.GONE", self.player)
        self.assertIn("player_error", self.player)
        self.assertIn("showPlayerError(", self.player)

    def test_native_media3_player_is_not_recreated_for_controls(self):
        self.assertIn("ExoPlayer.Builder(this).build()", self.player)
        self.assertIn("playerView.player = player", self.player)
        self.assertIn("player.setPlaybackSpeed", self.player)
        self.assertIn("player.trackSelectionParameters", self.player)
        self.assertNotIn("ExoPlayer.Builder(this).build()", self.player[self.player.index("private fun showSpeedSelection"):])
        self.assertNotIn("ExoPlayer.Builder(this).build()", self.player[self.player.index("private fun showTrackSelection"):])

    def test_lifecycle_keeps_rotation_and_pip_in_same_activity(self):
        for token in (
            "onConfigurationChanged",
            "onPictureInPictureModeChanged",
            "configurePictureInPicture",
            "restoreSystemUiBeforeExit",
            "enterImmersiveMode",
            "onBackPressedDispatcher",
            "onNewIntent",
        ):
            self.assertIn(token, self.player)

    def test_disabled_vertical_gestures_are_silent(self):
        self.assertIn("if (brightnessGesturesEnabled)", self.player)
        self.assertIn("if (volumeGesturesEnabled)", self.player)
        self.assertIn("Disabled gestures are deliberately silent", self.player)
        self.assertNotIn("Gesto de volume desligado", self.player[self.player.index("private inner class GestureLayer"):])
        self.assertNotIn("Gesto de brilho desligado", self.player[self.player.index("private inner class GestureLayer"):])

    def test_touch_targets_and_accessibility_contract(self):
        self.assertIn("minHeight = dp(44)", self.player)
        for token in (
            'contentDescription = "Voltar"',
            'contentDescription = "Reproduzir ou pausar"',
            'contentDescription = "Barra de progresso"',
            'contentDescription = "Mais opções"',
            'contentDescription = "Picture in Picture"',
        ):
            self.assertIn(token, self.player)


if __name__ == "__main__":
    unittest.main()
