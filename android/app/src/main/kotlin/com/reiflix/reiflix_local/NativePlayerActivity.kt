package com.reiflix.reiflix_local

import android.content.Intent
import android.content.pm.ActivityInfo
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.MediaStore
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.app.PictureInPictureParams
import android.os.Build
import android.view.Gravity
import java.io.File
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
import androidx.media3.common.TrackSelectionParameters
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.AspectRatioFrameLayout
import androidx.media3.ui.TrackSelectionDialogBuilder
import androidx.media3.ui.PlayerView
import org.json.JSONObject
import kotlin.math.abs

/** Full-screen Media3 player for one persisted local, SAF, or MediaStore URI. */
@OptIn(UnstableApi::class)
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
    private var audioButton: Button? = null
    private var subtitleButton: Button? = null
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
        val resolvedUri = normalizeLocalReference(rawUri)
        if (resolvedUri == null) {
            reportError("Referência local inválida.")
            finish()
            return
        }
        uri = resolvedUri
        val preflightError = validateLocalSource(uri)
        if (preflightError != null) {
            reportError(preflightError)
            finish()
            return
        }

        player = ExoPlayer.Builder(this).build()
        savedInstanceState?.getBundle("track_selection_parameters")?.let { bundle ->
            runCatching { TrackSelectionParameters.fromBundle(bundle) }
                .onSuccess { player.trackSelectionParameters = it }
        }
        autoplayNext = savedInstanceState?.takeIf { it.containsKey("autoplay_next") }?.getBoolean("autoplay_next")
            ?: intent.getBooleanExtra("autoplay", true)
        playerView = PlayerView(this).apply {
            player = this@NativePlayerActivity.player
            useController = true
            controllerShowTimeoutMs = 3500
            controllerAutoShow = true
            contentDescription = title
            resizeMode = savedInstanceState?.takeIf { it.containsKey("resize_mode") }?.getInt(
                "resize_mode", AspectRatioFrameLayout.RESIZE_MODE_FIT
            ) ?: AspectRatioFrameLayout.RESIZE_MODE_FIT
        }
        savedInstanceState?.takeIf { it.containsKey("playback_speed") }?.getFloat("playback_speed")?.let { speed ->
            if (speed > 0f && speed.isFinite()) player.setPlaybackSpeed(speed)
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
                        val savedPosition = savedInstanceState?.takeIf { it.containsKey("position_ms") }?.getLong("position_ms")
                        seekToSavedPosition(savedPosition)
                        initialSeekApplied = true
                    }
                    audioButton?.isEnabled = player.currentTracks.groups.any {
                        it.type == C.TRACK_TYPE_AUDIO && it.isSupported
                    }
                    subtitleButton?.isEnabled = player.currentTracks.groups.any {
                        it.type == C.TRACK_TYPE_TEXT && it.isSupported
                    }
                    handler.removeCallbacks(progressReporter)
                    handler.postDelayed(progressReporter, PROGRESS_INTERVAL_MS)
                } else if (state == Player.STATE_ENDED && !completionReported) {
                    completionReported = true
                    saveProgress("player_completed", force = true)
                    if (autoplayNext && intent.getBooleanExtra("canNext", false)) requestEpisode("player_next_request")
                }
            }
            override fun onPositionDiscontinuity(
                oldPosition: Player.PositionInfo,
                newPosition: Player.PositionInfo,
                reason: Int,
            ) {
                if (reason == Player.DISCONTINUITY_REASON_SEEK ||
                    reason == Player.DISCONTINUITY_REASON_SEEK_ADJUSTMENT) {
                    saveProgress("player_progress", force = true)
                }
            }
            override fun onPlayerError(error: PlaybackException) {
                // An error is never completion, but the last reliable position is
                // still useful for Resume. Flush it before leaving the Activity.
                saveProgress("player_progress", force = true)
                suppressExitEvent = true
                reportError("Não foi possível reproduzir este arquivo neste dispositivo.")
                finish()
            }
        })
        player.setMediaItem(MediaItem.Builder().setUri(uri).setMediaId(uri.toString()).build())
        player.prepare()
        player.playWhenReady = savedInstanceState?.takeIf { it.containsKey("play_when_ready") }?.getBoolean("play_when_ready") ?: true
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
        audioButton = Button(this).apply {
            text = "Áudio"
            isEnabled = false
            setOnClickListener { showTrackSelection(C.TRACK_TYPE_AUDIO, "Áudio") }
        }
        root.addView(audioButton, bottomParams(Gravity.CENTER, 214))
        subtitleButton = Button(this).apply {
            text = "Legendas"
            isEnabled = false
            setOnClickListener { showTrackSelection(C.TRACK_TYPE_TEXT, "Legendas") }
        }
        root.addView(subtitleButton, bottomParams(Gravity.CENTER, 276))
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
    private fun showTrackSelection(trackType: Int, label: String) {
        if (!::player.isInitialized) return
        if (!player.currentTracks.groups.any { it.type == trackType && it.isSupported }) return
        TrackSelectionDialogBuilder(this, label, player, trackType)
            .setAllowAdaptiveSelections(false)
            .setAllowMultipleOverrides(false)
            .build()
            .show()
    }

    private fun cycleSpeed(button: Button) {
        val speeds = floatArrayOf(.5f, .75f, 1f, 1.25f, 1.5f, 1.75f, 2f)
        val current = player.playbackParameters.speed
        val next = speeds[((speeds.indexOfFirst { it == current }.takeIf { it >= 0 } ?: 2) + 1) % speeds.size]
        player.setPlaybackSpeed(next); button.text = "${next}x"
    }
    private fun cycleAspect(button: Button) {
        val modes = intArrayOf(AspectRatioFrameLayout.RESIZE_MODE_FIT, AspectRatioFrameLayout.RESIZE_MODE_FILL, AspectRatioFrameLayout.RESIZE_MODE_ZOOM)
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
    private val sleepReporter = object : Runnable {
        override fun run() {
            if (sleepDeadline > 0 && System.currentTimeMillis() >= sleepDeadline) {
                saveProgress("player_paused", force = true)
                player.pause()
                sleepDeadline = 0
                Toast.makeText(this@NativePlayerActivity, "Timer de sono concluído", Toast.LENGTH_SHORT).show()
            } else if (sleepDeadline > 0) {
                handler.postDelayed(this, 1_000L)
            }
        }
    }

    private fun requestEpisode(eventType: String) {
        if (!completionReported) saveProgress("player_progress", force = true)
        // The incoming replacement player owns the next screen state; avoid
        // emitting a misleading normal-exit event while changing episodes.
        suppressExitEvent = true
        NativeMailbox.write(this, JSONObject().put("type", eventType).put("payload", JSONObject().put("uri", uri.toString())))
        finish()
    }

    private fun seekToSavedPosition(savedPositionMs: Long? = null) {
        val requested = (savedPositionMs ?: intent.getLongExtra("positionMs", 0L)).coerceAtLeast(0L)
        val duration = player.duration
        if (requested > 0 && (duration == C.TIME_UNSET || requested < duration)) player.seekTo(requested)
    }

    override fun onSaveInstanceState(outState: Bundle) {
        if (::player.isInitialized) {
            outState.putLong("position_ms", player.currentPosition.coerceAtLeast(0L))
            outState.putLong("duration_ms", player.duration.coerceAtLeast(0L))
            outState.putFloat("playback_speed", player.playbackParameters.speed)
            outState.putBoolean("play_when_ready", player.playWhenReady)
            outState.putBundle("track_selection_parameters", player.trackSelectionParameters.toBundle())
        }
        if (::playerView.isInitialized) outState.putInt("resize_mode", playerView.resizeMode)
        outState.putBoolean("autoplay_next", autoplayNext)
        super.onSaveInstanceState(outState)
    }
    override fun onPause() { saveProgress("player_paused", force = true); super.onPause() }
    override fun onStop() { saveProgress("player_progress", force = true); super.onStop() }
    override fun onDestroy() {
        handler.removeCallbacks(progressReporter)
        handler.removeCallbacks(sleepReporter)
        if (::player.isInitialized) {
            if (!suppressExitEvent && !isChangingConfigurations) {
                saveProgress("player_exited", force = true)
            }
            player.release()
        }
        super.onDestroy()
    }
    override fun onResume() { super.onResume(); enterImmersiveMode() }
    override fun onUserLeaveHint() {
        // Some Android/TV builds omit PiP even on API 26+. Entering PiP without
        // the feature is not a fallback; it can throw and terminate playback.
        if (canEnterPictureInPicture()) {
            runCatching {
                val builder = PictureInPictureParams.Builder()
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                    builder.setAutoEnterEnabled(true)
                    builder.setSeamlessResizeEnabled(true)
                }
                enterPictureInPictureMode(builder.build())
            }.onFailure { error ->
                android.util.Log.w(TAG, "PiP indisponível neste dispositivo.", error)
            }
        }
        super.onUserLeaveHint()
    }

    private fun canEnterPictureInPicture(): Boolean =
        Build.VERSION.SDK_INT >= Build.VERSION_CODES.O &&
            packageManager.hasSystemFeature(PackageManager.FEATURE_PICTURE_IN_PICTURE) &&
            ::player.isInitialized && player.isPlaying
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
        if (force && position == lastSavedPosition &&
            eventType != "player_completed" && eventType != "player_exited") return
        lastSavedPosition = position
        NativeMailbox.write(this, JSONObject().put("type", eventType).put("payload", JSONObject()
            .put("uri", uri.toString()).put("positionMs", position)
            .put("durationMs", duration)))
    }
    private fun reportError(message: String) {
        NativeMailbox.write(this, JSONObject().put("type", "player_error").put("message", message))
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
    }

    private fun normalizeLocalReference(rawReference: String): Uri? {
        val reference = rawReference.trim()
        if (reference.isBlank()) return null
        val parsed = runCatching { Uri.parse(reference) }.getOrNull() ?: return null
        if (parsed.scheme.isNullOrBlank() && reference.startsWith(File.separator)) {
            return runCatching { Uri.fromFile(File(reference).canonicalFile) }.getOrNull()
        }
        return parsed.takeIf {
            it.scheme.equals("content", true) || it.scheme.equals("file", true)
        }
    }

    private fun validateLocalSource(localUri: Uri): String? {
        return when (localUri.scheme?.lowercase()) {
            "content" -> {
                val safAuthorized = runCatching {
                    SafScanner.isAuthorizedDocument(this, localUri)
                }.getOrDefault(false)
                val mediaStoreAuthorized = if (!safAuthorized) {
                    runCatching {
                        MediaStoreScanner.isAuthorizedDocument(this, localUri)
                    }.getOrDefault(false)
                } else false
                if (!safAuthorized && !mediaStoreAuthorized) {
                    if (localUri.authority == MediaStore.AUTHORITY &&
                        !MediaStoreScanner.hasReadPermission(this)) {
                        "A permissão para ler vídeos foi revogada."
                    } else {
                        "A autorização deste arquivo não está mais disponível ou o provedor está indisponível."
                    }
                } else {
                    val readable = runCatching {
                        contentResolver.openFileDescriptor(localUri, "r")?.use { true } == true
                    }.getOrDefault(false)
                    if (!readable) {
                        "O provedor local não está disponível para leitura deste arquivo."
                    } else null
                }
            }
            "file" -> {
                val file = runCatching {
                    File(localUri.path ?: "").canonicalFile
                }.getOrNull() ?: return "Arquivo local inválido."
                when {
                    !file.exists() -> "Arquivo local removido ou indisponível."
                    !file.isFile -> "A referência local não aponta para um arquivo."
                    !BroadStorageScanner.isAuthorizedFile(this, localUri) ->
                        "Este arquivo não pertence a uma pasta autorizada pelo Rei-Flix."
                    !file.canRead() -> "O arquivo local não pode ser lido neste momento."
                    else -> null
                }
            }
            else -> "A reprodução aceita somente referências locais content:// ou file://."
        }
    }

    companion object {
        private const val TAG = "[REIFLIX][PLAYER]"
        private const val PROGRESS_INTERVAL_MS = 15_000L
    }
}
