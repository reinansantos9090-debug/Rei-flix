package com.reiflix.reiflix_local

import android.content.Intent
import android.content.pm.ActivityInfo
import android.net.Uri
import android.os.Bundle
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.widget.FrameLayout
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import org.json.JSONObject

/** Media3/ExoPlayer player for persisted SAF document URIs. */
class NativePlayerActivity : ComponentActivity() {
    private lateinit var player: ExoPlayer
    private lateinit var uri: Uri
    private var lastSaved = 0L
    private val title get() = intent.getStringExtra("title") ?: "Episódio"

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
        window.insetsController?.hide(WindowInsets.Type.statusBars() or WindowInsets.Type.navigationBars())
        window.insetsController?.systemBarsBehavior = WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        uri = Uri.parse(intent.getStringExtra("uri") ?: run { finish(); return })
        player = ExoPlayer.Builder(this).build()
        val view = PlayerView(this).apply { this.player = this@NativePlayerActivity.player; useController = true; controllerShowTimeoutMs = 3500 }
        setContentView(FrameLayout(this).apply { addView(view) })
        player.setMediaItem(MediaItem.fromUri(uri)); player.prepare()
        player.seekTo(intent.getLongExtra("positionMs", 0)); player.playWhenReady = true
        player.addListener(object : Player.Listener {
            override fun onPlayerError(error: PlaybackException) { Toast.makeText(this@NativePlayerActivity, "Não foi possível reproduzir este arquivo neste dispositivo.", Toast.LENGTH_LONG).show(); finish() }
            override fun onPlaybackStateChanged(state: Int) { if (state == Player.STATE_ENDED) finishWithProgress(true) }
        })
    }
    override fun onPause() { super.onPause(); saveProgress(false) }
    override fun onDestroy() { saveProgress(false); player.release(); super.onDestroy() }
    private fun saveProgress(completed: Boolean) {
        if (!::player.isInitialized || player.currentPosition == lastSaved) return
        lastSaved = player.currentPosition
        NativeMailbox.write(this, JSONObject().put("type", "player_progress").put("payload", JSONObject().put("uri", uri.toString()).put("positionMs", player.currentPosition).put("durationMs", player.duration.coerceAtLeast(0)).put("completed", completed)))
    }
    private fun finishWithProgress(completed: Boolean) { saveProgress(completed); setResult(RESULT_OK, Intent().putExtra("completed", completed)); finish() }
}
