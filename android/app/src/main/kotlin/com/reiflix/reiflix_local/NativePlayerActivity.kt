package com.reiflix.reiflix_local

import android.content.Intent
import android.content.pm.ActivityInfo
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
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
        if (!((uri.scheme == "content" && SafScanner.isAuthorizedDocument(this, uri)) || MediaStoreScanner.isAuthorizedDocument(this, uri))) {
            reportError("Este arquivo não pertence a uma pasta autorizada pelo Rei-Flix.")
            finish()
            return
        }

        player = ExoPlayer.Builder(this).build()
        val playerView = PlayerView(this).apply {
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
                } else if (state == Player.STATE_ENDED) {
                    saveProgress("player_completed", force = true)
                }
            }
            override fun onPlayerError(error: PlaybackException) {
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
    }

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
        if (::player.isInitialized) {
            if (!suppressExitEvent) saveProgress("player_exited", force = true)
            player.release()
        }
        super.onDestroy()
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
        val position = player.currentPosition.coerceAtLeast(0L)
        if (!force && (position - lastSavedPosition) < PROGRESS_INTERVAL_MS) return
        lastSavedPosition = position
        NativeMailbox.write(this, JSONObject().put("type", eventType).put("payload", JSONObject()
            .put("uri", uri.toString()).put("positionMs", position)
            .put("durationMs", player.duration.coerceAtLeast(0L))))
    }
    private fun reportError(message: String) {
        NativeMailbox.write(this, JSONObject().put("type", "player_error").put("message", message))
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
    }
    companion object { private const val PROGRESS_INTERVAL_MS = 15_000L }
}
