package com.reiflix.reiflix_local

import android.content.Intent
import android.content.pm.ActivityInfo
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.app.PictureInPictureParams
import android.os.Build
import android.view.Gravity
import android.widget.Button
import android.widget.FrameLayout
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import org.json.JSONObject
import kotlin.math.abs

/** Full-screen Media3 player for one persisted local, SAF, or MediaStore URI. */
class NativePlayerActivity : ComponentActivity() {
    private lateinit var player: ExoPlayer
    private lateinit var uri: Uri
    private val handler = Handler(Looper.getMainLooper())
    private var lastSavedPosition = -1L
    // Episode replacement suppresses a normal exit only because Python opens
    // the next native activity from the mailbox request. Completion and errors
    // must still publish an exit when the user closes this activity.
    private var suppressExitEvent = false
    private var initialSeekApplied = false
    private var autoplayNext = true
    private var completionReported = false
    private var sleepDeadline = 0L
    private lateinit var playerView: PlayerView
    private val title get() = intent.getStringExtra("title") ?: "Episódio"
    private val progressReporter = object : Runnable {
        override fun run() {
            saveProgress("player_progress")
            if (::player.isInitialized && player.playbackState != Player.STATE_ENDED) {
                handler.postDelayed(this, PROGRESS_INTERVAL_MS)
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
        enterImmersiveMode()
        val rawUri = intent.getStringExtra("uri")
        if (rawUri.isNullOrBlank()) { reportError("Arquivo local inválido."); finish(); return }
        uri = Uri.parse(rawUri)
        if (!((uri.scheme == "content" && SafScanner.isAuthorizedDocument(this, uri)) || MediaStoreScanner.isAuthorizedDocument(this, uri) || BroadStorageScanner.isAuthorizedFile(this, uri))) {
            reportError("Este arquivo não pertence a uma pasta autorizada pelo Rei-Flix.")
            finish()
            return
        }

        player = ExoPlayer.Builder(this).build()
        autoplayNext = intent.getBooleanExtra("autoplay", true)
        playerView = PlayerView(this).apply {
            player = this@NativePlayerActivity.player
            useController = true
            controllerShowTimeoutMs = 3500
            controllerAutoShow = true
            contentDescription = title
        }
        setContentView(FrameLayout(this).apply {
            setBackgroundColor(android.graphics.Color.BLACK)
            addView(playerView, FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT))
            addEpisodeButtons(this)
        })
        player.addListener(object : Player.Listener {
            override fun onPlaybackStateChanged(state: Int) {
                if (state == Player.STATE_READY) {
                    if (!initialSeekApplied) {
                        seekToSavedPosition()
                        initialSeekApplied = true
                    }
                    handler.removeCallbacks(progressReporter)
                    handler.postDelayed(progressReporter, PROGRESS_INTERVAL_MS)
                } else if (state == Player.STATE_ENDED && !completionReported) {
                    completionReported = true
                    saveProgress("player_completed", force = true)
                    if (autoplayNext && intent.getBooleanExtra("canNext", false)) requestEpisode("player_next_request")
                }
            }
            override fun onPlayerError(error: PlaybackException) {
                // player_error is the terminal signal for an unreadable media item.
                // Suppress player_exited here so Python does not navigate back twice.
                suppressExitEvent = true
                reportError("Não foi possível reproduzir este arquivo neste dispositivo.")
                finish()
            }
        })
        player.setMediaItem(MediaItem.Builder().setUri(uri).setMediaId(uri.toString()).build())
        player.prepare()
        player.playWhenReady = true
    }

    private fun addEpisodeButtons(root: FrameLayout) {
        val controls = listOf(
            Triple("Anterior", "player_previous_request", intent.getBooleanExtra("canPrevious", false)),
            Triple("Próximo", "player_next_request", intent.getBooleanExtra("canNext", false)),
        )
        controls.forEachIndexed { index, (label, eventType, enabled) ->
            if (!enabled) return@forEachIndexed
            root.addView(Button(this).apply {
                text = label
                setOnClickListener { requestEpisode(eventType) }
            }, FrameLayout.LayoutParams(FrameLayout.LayoutParams.WRAP_CONTENT, FrameLayout.LayoutParams.WRAP_CONTENT).apply {
                gravity = Gravity.BOTTOM or if (index == 0) Gravity.START else Gravity.END
                setMargins(24, 0, 24, 28)
            })
        }
        root.addView(Button(this).apply {
            text = "1.0x"
            setOnClickListener { cycleSpeed(this) }
        }, bottomParams(Gravity.CENTER, 150))
        root.addView(Button(this).apply {
            text = "Ajustar"
            setOnClickListener { cycleAspect(this) }
        }, bottomParams(Gravity.CENTER, 88))
        root.addView(Button(this).apply {
            text = "Reiniciar"
            setOnClickListener { player.seekTo(0); saveProgress("player_progress", true) }
        }, bottomParams(Gravity.CENTER, 26))
        root.addView(Button(this).apply {
            text = if (autoplayNext) "Autoplay: ON" else "Autoplay: OFF"
            setOnClickListener {
                autoplayNext = !autoplayNext
                text = if (autoplayNext) "Autoplay: ON" else "Autoplay: OFF"
                NativeMailbox.write(this@NativePlayerActivity, JSONObject()
                    .put("type", "player_autoplay_changed")
                    .put("payload", JSONObject().put("enabled", autoplayNext)))
            }
        }, bottomParams(Gravity.TOP or Gravity.END, 24))
        root.addView(Button(this).apply {
            text = "15 min"
            setOnClickListener { setSleepTimer(this) }
        }, bottomParams(Gravity.TOP or Gravity.START, 24))
        root.addView(Button(this).apply {
            text = "Visto"
            setOnClickListener { NativeMailbox.write(this@NativePlayerActivity, JSONObject().put("type", "player_mark_watched").put("payload", JSONObject().put("uri", uri.toString()))); saveProgress("player_progress", true) }
        }, bottomParams(Gravity.CENTER or Gravity.TOP, 24))
        root.addView(Button(this).apply {
            text = "Não visto"
            setOnClickListener { NativeMailbox.write(this@NativePlayerActivity, JSONObject().put("type", "player_mark_unwatched").put("payload", JSONObject().put("uri", uri.toString()))) }
        }, bottomParams(Gravity.CENTER or Gravity.TOP, 76))
    }

    private fun bottomParams(gravity: Int, bottom: Int) = FrameLayout.LayoutParams(FrameLayout.LayoutParams.WRAP_CONTENT, FrameLayout.LayoutParams.WRAP_CONTENT).apply { this.gravity = gravity; setMargins(18, 18, 18, bottom) }
    private fun cycleSpeed(button: Button) {
        val speeds = floatArrayOf(.5f, .75f, 1f, 1.25f, 1.5f, 1.75f, 2f)
        val current = player.playbackParameters.speed
        val next = speeds[((speeds.indexOfFirst { it == current }.takeIf { it >= 0 } ?: 2) + 1) % speeds.size]
        player.setPlaybackSpeed(next); button.text = "${next}x"
    }
    private fun cycleAspect(button: Button) {
        val modes = intArrayOf(PlayerView.RESIZE_MODE_FIT, PlayerView.RESIZE_MODE_FILL, PlayerView.RESIZE_MODE_ZOOM)
        val index = modes.indexOf(playerView.resizeMode)
        playerView.resizeMode = modes[(index + 1) % modes.size]
        button.text = arrayOf("Ajustar", "Preencher", "Zoom")[(index + 1) % modes.size]
    }
    private fun setSleepTimer(button: Button) {
        val minutes = when ((sleepDeadline - System.currentTimeMillis()).coerceAtLeast(0L)) { 0L -> 15; in 1..900_000 -> 30; in 900_001..1_800_000 -> 45; else -> 0 }
        sleepDeadline = if (minutes == 0) 0 else System.currentTimeMillis() + minutes * 60_000L
        button.text = if (minutes == 0) "Timer: off" else "$minutes min"
        handler.removeCallbacks(sleepReporter)
        if (sleepDeadline > 0) handler.postDelayed(sleepReporter, 1_000L)
    }
    private val sleepReporter = object : Runnable { override fun run() { if (sleepDeadline > 0 && System.currentTimeMillis() >= sleepDeadline) { player.pause(); sleepDeadline = 0; Toast.makeText(this@NativePlayerActivity, "Timer de sono concluído", Toast.LENGTH_SHORT).show() } else if (sleepDeadline > 0) handler.postDelayed(this, 1_000L) } }

    private fun requestEpisode(eventType: String) {
        saveProgress("player_progress", force = true)
        // The incoming replacement player owns the next screen state; avoid
        // emitting a misleading normal-exit event while changing episodes.
        suppressExitEvent = true
        NativeMailbox.write(this, JSONObject().put("type", eventType).put("payload", JSONObject().put("uri", uri.toString())))
        finish()
    }

    private fun seekToSavedPosition() {
        val requested = intent.getLongExtra("positionMs", 0L).coerceAtLeast(0L)
        val duration = player.duration
        if (requested > 0 && (duration == C.TIME_UNSET || requested < duration)) player.seekTo(requested)
    }

    override fun onPause() { saveProgress("player_paused", force = true); super.onPause() }
    override fun onStop() { saveProgress("player_progress", force = true); super.onStop() }
    override fun onDestroy() {
        handler.removeCallbacks(progressReporter)
        handler.removeCallbacks(sleepReporter)
        if (::player.isInitialized) {
            if (!suppressExitEvent && !completionReported) saveProgress("player_exited", force = true)
            player.release()
        }
        super.onDestroy()
    }
    override fun onResume() { super.onResume(); enterImmersiveMode() }
    override fun onUserLeaveHint() {
        // Some Android/TV builds omit PiP even on API 26+. Entering PiP without
        // the feature is not a fallback; it can throw and terminate playback.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O &&
            packageManager.hasSystemFeature(PackageManager.FEATURE_PICTURE_IN_PICTURE) &&
            ::player.isInitialized && player.isPlaying) {
            enterPictureInPictureMode(PictureInPictureParams.Builder().build())
        }
        super.onUserLeaveHint()
    }
    override fun onWindowFocusChanged(hasFocus: Boolean) { super.onWindowFocusChanged(hasFocus); if (hasFocus) enterImmersiveMode() }

    private fun enterImmersiveMode() {
        WindowCompat.setDecorFitsSystemWindows(window, false)
        WindowInsetsControllerCompat(window, window.decorView).apply {
            hide(WindowInsetsCompat.Type.systemBars())
            systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        }
    }
    private fun saveProgress(eventType: String, force: Boolean = false) {
        if (!::player.isInitialized) return
        val rawPosition = player.currentPosition
        val rawDuration = player.duration
        val position = rawPosition.takeIf { it >= 0L }?.coerceAtMost(
            rawDuration.takeIf { it > 0L } ?: Long.MAX_VALUE
        ) ?: 0L
        val duration = rawDuration.takeIf { it > 0L } ?: 0L
        if (!force && abs(position - lastSavedPosition) < PROGRESS_INTERVAL_MS) return
        // Lifecycle callbacks can fire back-to-back (pause -> stop -> destroy).
        // Avoid emitting identical snapshots while still flushing meaningful events.
        if (force && position == lastSavedPosition && eventType != "player_completed") return
        lastSavedPosition = position
        NativeMailbox.write(this, JSONObject().put("type", eventType).put("payload", JSONObject()
            .put("uri", uri.toString()).put("positionMs", position)
            .put("durationMs", duration)))
    }
    private fun reportError(message: String) {
        NativeMailbox.write(this, JSONObject().put("type", "player_error").put("message", message))
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
    }
    companion object { private const val PROGRESS_INTERVAL_MS = 15_000L }
}
