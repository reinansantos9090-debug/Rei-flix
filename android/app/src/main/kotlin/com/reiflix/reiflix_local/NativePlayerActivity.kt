package com.reiflix.reiflix_local

import android.app.PictureInPictureParams
import android.content.Context
import android.content.Intent
import android.content.pm.ActivityInfo
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.graphics.Color
import android.graphics.Typeface
import android.media.AudioManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.MediaStore
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.view.GestureDetector
import android.view.ScaleGestureDetector
import android.view.ViewConfiguration
import android.view.WindowManager
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.SeekBar
import android.widget.TextView
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.core.view.ViewCompat
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
import androidx.media3.ui.PlayerView
import androidx.media3.ui.TrackSelectionDialogBuilder
import org.json.JSONObject
import java.io.File
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/** Full-screen Media3 player for one persisted local, SAF, or MediaStore URI. */
@OptIn(UnstableApi::class)
class NativePlayerActivity : ComponentActivity() {
    private lateinit var player: ExoPlayer
    private lateinit var uri: Uri
    private lateinit var playerView: PlayerView
    private lateinit var root: FrameLayout
    private lateinit var controls: FrameLayout
    private lateinit var centerControls: LinearLayout
    private lateinit var topBar: LinearLayout
    private lateinit var bottomBar: LinearLayout
    private lateinit var playPauseButton: TextView
    private lateinit var seekBar: SeekBar
    private lateinit var positionLabel: TextView
    private lateinit var durationLabel: TextView
    private lateinit var feedback: TextView
    private lateinit var errorPanel: LinearLayout

    private val handler = Handler(Looper.getMainLooper())
    private val audioManager by lazy { getSystemService(AudioManager::class.java) }
    private var lastSavedPosition = -1L
    private var suppressExitEvent = false
    private var exitReported = false
    private var initialSeekApplied = false
    private var autoplayNext = true
    private var completionReported = false
    private var controlsVisible = true
    private var moreVisible = false
    private var lastControlsInteraction = 0L
    private var requestId = ""
    private var errorVisible = false
    private var openedReported = false
    private var restoredPositionMs: Long? = null
    internal var firstFrameRenderedForTesting = false
        private set
    private enum class GestureMode { NONE, HORIZONTAL_SEEK, VERTICAL_BRIGHTNESS, VERTICAL_VOLUME }
    private var brightnessLevel = 0.5f
    private var pendingSeekPosition: Long? = null
    private var feedbackHideAt = 0L

    private val titleValue: String
        get() = intent.getStringExtra("title") ?: "Episódio"

    private val controlsHider = object : Runnable {
        override fun run() {
            if (controlsVisible && !errorVisible) {
                val elapsed = System.currentTimeMillis() - lastControlsInteraction
                if (elapsed >= CONTROL_TIMEOUT_MS) {
                    setControlsVisible(false)
                } else {
                    handler.postDelayed(this, CONTROL_TIMEOUT_MS - elapsed)
                }
            }
        }
    }

    private val feedbackHider = object : Runnable {
        override fun run() {
            if (feedbackHideAt > 0L && System.currentTimeMillis() >= feedbackHideAt) {
                feedbackHideAt = 0L
                if (::feedback.isInitialized) feedback.visibility = View.GONE
            } else if (feedbackHideAt > 0L) {
                handler.postDelayed(this, 120L)
            }
        }
    }

    private val progressReporter = object : Runnable {
        override fun run() {
            saveProgress("player_progress")
            updateProgressUi()
            if (::player.isInitialized && player.playbackState != Player.STATE_ENDED) {
                handler.postDelayed(this, PROGRESS_INTERVAL_MS)
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_FULL_SENSOR
        requestId = intent.getStringExtra("requestId")?.trim().orEmpty()
        logPlayer("onCreate requestId=" + requestId.ifEmpty { "-" } + " task=" + taskId)

        enterImmersiveMode()
        configureWindow()
        restoredPositionMs = savedInstanceState?.takeIf { it.containsKey("position_ms") }?.getLong("position_ms")
        brightnessLevel = window.attributes.screenBrightness
            .takeIf { it.isFinite() && it >= 0f }
            ?.coerceIn(0f, 1f)
            ?: 0.5f

        root = FrameLayout(this).apply {
            setBackgroundColor(Color.BLACK)
            clipChildren = false
            clipToPadding = false
        }
        setContentView(root)
        installBasePlayerView()
        installGestureLayer()
        installControls()
        installBackHandler()
        configurePictureInPicture()
        ViewCompat.getRootWindowInsets(window.decorView)?.let { applyRootInsets(it) }

        val rawUri = intent.getStringExtra("uri")
        logPlayer("URI_RECEIVED requestId=" + requestId.ifEmpty { "-" } +
            " uriOriginal=" + rawUri.orEmpty())
        if (rawUri.isNullOrBlank()) {
            showPlayerError("Arquivo local inválido.", "missing_uri")
            return
        }

        val resolvedUri = normalizeLocalReference(rawUri)
        logPlayer("URI_NORMALIZED requestId=" + requestId.ifEmpty { "-" } +
            " uriNormalized=" + resolvedUri +
            " scheme=" + (resolvedUri?.scheme ?: "-") +
            " authority=" + (resolvedUri?.authority ?: "-"))
        if (resolvedUri == null) {
            showPlayerError("Referência local inválida.", "invalid_uri")
            return
        }
        uri = resolvedUri

        val source = sourceFor(uri)
        logPlayer("PREFLIGHT_START requestId=" + requestId.ifEmpty { "-" } +
            " source=" + source + " scheme=" + uri.scheme + " authority=" + (uri.authority ?: "-"))
        val preflightError = validateLocalSource(uri)
        if (preflightError != null) {
            logPlayer("PREFLIGHT_FAILED requestId=" + requestId.ifEmpty { "-" } +
                " source=" + source + " error=" + preflightError)
            showPlayerError(preflightError, "unauthorized_or_unreadable")
            return
        }
        logPlayer("PREFLIGHT_OK requestId=" + requestId.ifEmpty { "-" } + " source=" + source)

        try {
            logPlayer("EXOPLAYER_CREATE requestId=" + requestId.ifEmpty { "-" })
            player = ExoPlayer.Builder(this).build()
            // PlayerView owns the video surface/subtitle rendering. Attach the
            // real ExoPlayer before assigning media or preparing it.
            playerView.player = player
            check(playerView.player === player) {
                "PlayerView failed to attach the ExoPlayer instance"
            }
            logPlayer("PLAYER_VIEW_ATTACHED requestId=" + requestId.ifEmpty { "-" } +
                " sameInstance=" + (playerView.player === player))
            savedInstanceState?.getBundle("track_selection_parameters")?.let { bundle ->
                runCatching { TrackSelectionParameters.fromBundle(bundle) }
                    .onSuccess { player.trackSelectionParameters = it }
                    .onFailure { error -> logPlayer("TRACK_SELECTION_RESTORE_FAILED " + error) }
            }
            autoplayNext = savedInstanceState?.takeIf { it.containsKey("autoplay_next") }?.getBoolean("autoplay_next")
                ?: intent.getBooleanExtra("autoplay", true)

            player.addListener(playerListener)

            val savedSpeed = savedInstanceState?.takeIf { it.containsKey("playback_speed") }
                ?.getFloat("playback_speed") ?: 1f
            if (savedSpeed > 0f && savedSpeed.isFinite()) {
                player.setPlaybackSpeed(savedSpeed)
            }

            val savedResize = savedInstanceState?.takeIf { it.containsKey("resize_mode") }
                ?.getInt("resize_mode", AspectRatioFrameLayout.RESIZE_MODE_FIT)
                ?: AspectRatioFrameLayout.RESIZE_MODE_FIT
            playerView.resizeMode = savedResize

            val subtitleTracks = LocalSubtitleResolver.resolve(this, uri)
            val mediaItemBuilder = MediaItem.Builder()
                .setUri(uri)
                .setMediaId(uri.toString())
            if (subtitleTracks.isNotEmpty()) {
                mediaItemBuilder.setSubtitleConfigurations(
                    subtitleTracks.map { track ->
                        MediaItem.SubtitleConfiguration.Builder(track.uri)
                            .setMimeType(track.mimeType)
                            .setLanguage(track.language)
                            .setSelectionFlags(if (track.isDefault) C.SELECTION_FLAG_DEFAULT else 0)
                            .build()
                    }
                )
            }

            val mediaItem = mediaItemBuilder.build()
            logPlayer("MEDIA_ITEM requestId=" + requestId.ifEmpty { "-" } + " uri=" + mediaItem.localConfiguration?.uri)
            val shouldPlayWhenReady = savedInstanceState?.takeIf { it.containsKey("play_when_ready") }
                ?.getBoolean("play_when_ready")
                ?: intent.getBooleanExtra("autoplay", true)
            player.setMediaItem(mediaItem)
            // Set the desired playWhenReady state before prepare(). This prevents a
            // transient autoplay race when callers explicitly request autoplay=false.
            player.playWhenReady = shouldPlayWhenReady
            logPlayer("PLAY_WHEN_READY=" + player.playWhenReady + " requestId=" + requestId.ifEmpty { "-" })
            logPlayer("PREPARE requestId=" + requestId.ifEmpty { "-" })
            player.prepare()
        } catch (exception: Exception) {
            logPlayer("EXOPLAYER_INIT_FAILED requestId=" + requestId.ifEmpty { "-" }, exception)
            showPlayerError("Não foi possível iniciar o player local.", "player_initialization")
        }
    }

    private val playerListener = object : Player.Listener {
        override fun onEvents(player: Player, events: Player.Events) {
            if (events.contains(Player.EVENT_RENDERED_FIRST_FRAME)) {
                firstFrameRenderedForTesting = true
                logPlayer("FIRST_FRAME_RENDERED requestId=" + requestId.ifEmpty { "-" } +
                    " positionMs=" + player.currentPosition)
            }
        }

        override fun onPlaybackStateChanged(state: Int) {
            val label = when (state) {
                Player.STATE_IDLE -> "STATE_IDLE"
                Player.STATE_BUFFERING -> "STATE_BUFFERING"
                Player.STATE_READY -> "STATE_READY"
                Player.STATE_ENDED -> "STATE_ENDED"
                else -> "STATE_UNKNOWN"
            }
            logPlayer("PLAYBACK_STATE=" + label + " requestId=" + requestId.ifEmpty { "-" } +
                " positionMs=" + if (::player.isInitialized) player.currentPosition else 0L)
            when (state) {
                Player.STATE_READY -> {
                    if (!openedReported) {
                        openedReported = true
                        val opened = NativeMailbox.write(
                            this@NativePlayerActivity,
                            JSONObject().put("type", "player_opened")
                                .put("requestId", requestId)
                                .put("payload", JSONObject()
                                    .put("uri", uri.toString())
                                    .put("source", sourceFor(uri))
                                    .put("title", titleValue)
                                    .put("state", "READY"))
                        )
                        if (!opened) {
                            logPlayer("FAILED_TO_PUBLISH player_opened requestId=" + requestId.ifEmpty { "-" })
                        }
                    }
                    if (!initialSeekApplied) {
                        val savedPosition = intent.getLongExtra("positionMs", 0L)
                        seekToSavedPosition(restoredPositionMs ?: savedPosition)
                        initialSeekApplied = true
                    }
                    completionReported = false
                    updateTrackButtons()
                    updatePlayPauseButton()
                    updateProgressUi()
                    startProgressReporting()
                    if (!errorVisible) scheduleControlsHide()
                }
                Player.STATE_BUFFERING -> {
                    updatePlayPauseButton()
                    if (!errorVisible) scheduleControlsHide()
                }
                Player.STATE_ENDED -> {
                    completionReported = true
                    saveProgress("player_completed", force = true)
                    updatePlayPauseButton()
                    if (autoplayNext && intent.getBooleanExtra("canNext", false)) {
                        requestEpisode("player_next_request")
                    }
                }
                Player.STATE_IDLE -> updatePlayPauseButton()
            }
        }

        override fun onIsPlayingChanged(isPlaying: Boolean) {
            logPlayer("IS_PLAYING_CHANGED=" + isPlaying)
            updatePlayPauseButton()
            if (!errorVisible) {
                scheduleControlsHide()
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
            updateProgressUi()
        }

        override fun onTracksChanged(tracks: androidx.media3.common.Tracks) {
            updateTrackButtons()
        }

        override fun onPlayerError(error: PlaybackException) {
            val code = error.errorCodeName.orEmpty()
            val technicalCode = "media3:" + code
            val detail = error.message?.trim().orEmpty()
            logPlayer(
                "PlaybackException requestId=" + requestId.ifEmpty { "-" } +
                    " code=" + code + " detail=" + detail +
                    " cause=" + (error.cause?.javaClass?.simpleName ?: "-"),
                error,
            )
            saveProgress("player_progress", force = true)
            player.pause()
            showPlayerError(
                "Não foi possível reproduzir este arquivo neste dispositivo.",
                technicalCode,
                JSONObject()
                    .put("uri", uri.toString())
                    .put("errorCode", technicalCode)
                    .put("detail", detail)
                    .put("cause", error.cause?.javaClass?.simpleName ?: ""),
            )
        }
    }

    private fun configureWindow() {
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        window.statusBarColor = Color.TRANSPARENT
        window.navigationBarColor = Color.TRANSPARENT
        if (Build.VERSION.SDK_INT >= 29) {
            window.isStatusBarContrastEnforced = false
            window.isNavigationBarContrastEnforced = false
        }
    }

    private fun canEnterPictureInPicture(): Boolean {
        return Build.VERSION.SDK_INT >= Build.VERSION_CODES.O &&
            packageManager.hasSystemFeature(PackageManager.FEATURE_PICTURE_IN_PICTURE)
    }

    private fun configurePictureInPicture() {
        if (!canEnterPictureInPicture()) return
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val builder = PictureInPictureParams.Builder()
                .setAutoEnterEnabled(true)
            setPictureInPictureParams(builder.build())
        }
    }

    private fun installBasePlayerView() {
        playerView = PlayerView(this).apply {
            tag = "reiflix_player_view"
            useController = false
            controllerAutoShow = false
            controllerHideOnTouch = false
            keepScreenOn = true
            setShutterBackgroundColor(Color.BLACK)
            resizeMode = AspectRatioFrameLayout.RESIZE_MODE_FIT
        }
        root.addView(
            playerView,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT,
            )
        )
    }

    private fun installGestureLayer() {
        val gestureLayer = GestureLayer(this).apply {
            tag = "reiflix_gesture_layer"
        }
        root.addView(
            gestureLayer,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT,
            )
        )
    }

    private fun installControls() {
        controls = FrameLayout(this).apply {
            setBackgroundColor(Color.TRANSPARENT)
            isClickable = false
        }
        root.addView(
            controls,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT,
            )
        )

        topBar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(8), dp(6), dp(8), dp(6))
            setBackgroundColor(0x88000000.toInt())
        }
        val topParams = FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT,
            FrameLayout.LayoutParams.WRAP_CONTENT,
        ).apply { gravity = Gravity.TOP }
        controls.addView(topBar, topParams)

        val back = actionButton("‹", 44) {
            finishPlayer("back_button")
        }
        back.contentDescription = "Voltar"
        topBar.addView(back, weightParams(44))

        val title = TextView(this).apply {
            text = titleValue
            textSize = 15f
            setTextColor(Color.WHITE)
            typeface = Typeface.DEFAULT_BOLD
            maxLines = 1
            ellipsize = android.text.TextUtils.TruncateAt.END
            gravity = Gravity.CENTER_VERTICAL
            contentDescription = "Título do episódio"
        }
        topBar.addView(title, LinearLayout.LayoutParams(0, dp(48), 1f))

        val audioButton = actionButton("Áudio", 64) {
            showTrackSelection(C.TRACK_TYPE_AUDIO, "Áudio")
        }
        audioButton.tag = "reiflix_audio_button"
        topBar.addView(audioButton, weightParams(64))

        val subtitleButton = actionButton("Legenda", 72) {
            showTrackSelection(C.TRACK_TYPE_TEXT, "Legendas")
        }
        subtitleButton.tag = "reiflix_subtitle_button"
        topBar.addView(subtitleButton, weightParams(72))

        val speedButton = actionButton("1.0x", 58) { button ->
            cycleSpeed(button)
        }
        speedButton.tag = "reiflix_speed_button"
        topBar.addView(speedButton, weightParams(58))

        val aspectButton = actionButton("Ajustar", 68) { button ->
            cycleAspect(button)
        }
        aspectButton.tag = "reiflix_aspect_button"
        topBar.addView(aspectButton, weightParams(68))

        if (canEnterPictureInPicture()) {
            val pipButton = actionButton("PIP", 48) {
                enterPictureInPictureMode()
            }
            pipButton.contentDescription = "Picture in Picture"
            topBar.addView(pipButton, weightParams(48))
        }

        val moreButton = actionButton("Mais", 54) {
            moreVisible = !moreVisible
            findViewByTag<View>("reiflix_more_panel")?.visibility = if (moreVisible) View.VISIBLE else View.GONE
            touchControls()
        }
        topBar.addView(moreButton, weightParams(54))

        centerControls = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
        }
        val centerParams = FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.WRAP_CONTENT,
            FrameLayout.LayoutParams.WRAP_CONTENT,
        ).apply { gravity = Gravity.CENTER }
        controls.addView(centerControls, centerParams)

        feedback = TextView(this).apply {
            tag = "reiflix_feedback"
            textSize = 18f
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
            setTypeface(Typeface.DEFAULT_BOLD)
            setPadding(dp(18), dp(10), dp(18), dp(10))
            setBackgroundColor(0xAA000000.toInt())
            visibility = View.GONE
            isClickable = false
        }
        controls.addView(feedback, FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.WRAP_CONTENT,
            FrameLayout.LayoutParams.WRAP_CONTENT,
        ).apply {
            gravity = Gravity.CENTER
            topMargin = dp(96)
        })

        errorPanel = LinearLayout(this).apply {
            tag = "reiflix_error_panel"
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(dp(20), dp(18), dp(20), dp(18))
            setBackgroundColor(0xEE0B0A0F.toInt())
            visibility = View.GONE
            isFocusable = true
        }
        errorPanel.addView(TextView(this).apply {
            tag = "reiflix_error_text"
            textSize = 17f
            setTextColor(Color.WHITE)
            typeface = Typeface.DEFAULT_BOLD
            gravity = Gravity.CENTER
        }, LinearLayout.LayoutParams(dp(320), ViewGroup.LayoutParams.WRAP_CONTENT))
        errorPanel.addView(TextView(this).apply {
            tag = "reiflix_error_reason"
            textSize = 10f
            setTextColor(0xFFBDB8C9.toInt())
            gravity = Gravity.CENTER
        }, LinearLayout.LayoutParams(dp(320), ViewGroup.LayoutParams.WRAP_CONTENT).apply {
            topMargin = dp(8)
        })
        val errorBack = actionButton("Voltar ao Rei-Flix", 170) {
            finishPlayer("player_error_back")
        }
        errorBack.tag = "reiflix_error_back"
        errorPanel.addView(errorBack, LinearLayout.LayoutParams(dp(190), dp(48)).apply {
            gravity = Gravity.CENTER_HORIZONTAL
            topMargin = dp(14)
        })
        controls.addView(errorPanel, FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.WRAP_CONTENT,
            FrameLayout.LayoutParams.WRAP_CONTENT,
        ).apply {
            gravity = Gravity.CENTER
            leftMargin = dp(18)
            rightMargin = dp(18)
        })

        val previousButton = actionButton("−10", 70) { seekBy(-10_000L, "−10s") }
        previousButton.tag = "reiflix_seek_back"
        centerControls.addView(previousButton, weightParams(70))

        playPauseButton = actionButton("▶", 84) { togglePlayPause() }.apply {
            textSize = 26f
            tag = "reiflix_play_pause"
            minHeight = dp(72)
            minWidth = dp(72)
        }
        centerControls.addView(playPauseButton, weightParams(84))

        val nextButton = actionButton("+10", 70) { seekBy(10_000L, "+10s") }
        nextButton.tag = "reiflix_seek_forward"
        centerControls.addView(nextButton, weightParams(70))

        bottomBar = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(8), dp(4), dp(8), dp(8))
            setBackgroundColor(0x88000000.toInt())
        }
        val bottomParams = FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT,
            FrameLayout.LayoutParams.WRAP_CONTENT,
        ).apply { gravity = Gravity.BOTTOM }
        controls.addView(bottomBar, bottomParams)

        val seekRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        positionLabel = TextView(this).apply {
            text = "00:00"
            textSize = 11f
            setTextColor(Color.WHITE)
            tag = "reiflix_position"
        }
        durationLabel = TextView(this).apply {
            text = "00:00"
            textSize = 11f
            setTextColor(Color.WHITE)
            tag = "reiflix_duration"
        }
        seekBar = SeekBar(this).apply {
            max = SEEK_PROGRESS_MAX
            contentDescription = "Barra de progresso"
            tag = "reiflix_seekbar"
            setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
                override fun onProgressChanged(bar: SeekBar?, progress: Int, fromUser: Boolean) {
                    if (fromUser && ::player.isInitialized && player.duration > 0L) {
                        val target = player.duration * progress.toLong() / SEEK_PROGRESS_MAX
                        positionLabel.text = formatTime(target)
                    }
                }

                override fun onStartTrackingTouch(bar: SeekBar?) {
                    touchControls()
                }

                override fun onStopTrackingTouch(bar: SeekBar?) {
                    if (!::player.isInitialized || player.duration <= 0L) return
                    val target = player.duration * seekBar.progress.toLong() / SEEK_PROGRESS_MAX
                    player.seekTo(target.coerceIn(0L, player.duration))
                    saveProgress("player_progress", force = true)
                    showFeedback(formatTime(target))
                    scheduleControlsHide()
                }
            })
        }
        seekRow.addView(positionLabel, LinearLayout.LayoutParams(dp(48), dp(40)))
        seekRow.addView(seekBar, LinearLayout.LayoutParams(0, dp(40), 1f))
        seekRow.addView(durationLabel, LinearLayout.LayoutParams(dp(48), dp(40)))
        bottomBar.addView(seekRow)

        val actionsRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
        }
        val prevEpisode = actionButton("Anterior", 82) {
            if (intent.getBooleanExtra("canPrevious", false)) requestEpisode("player_previous_request")
        }
        prevEpisode.tag = "reiflix_previous_episode"
        prevEpisode.isEnabled = intent.getBooleanExtra("canPrevious", false)
        actionsRow.addView(prevEpisode, weightParams(82))

        val audio = actionButton("Áudio", 72) { showTrackSelection(C.TRACK_TYPE_AUDIO, "Áudio") }
        audio.tag = "reiflix_audio_bottom"
        actionsRow.addView(audio, weightParams(72))

        val nextEpisode = actionButton("Próximo", 82) {
            if (intent.getBooleanExtra("canNext", false)) requestEpisode("player_next_request")
        }
        nextEpisode.tag = "reiflix_next_episode"
        nextEpisode.isEnabled = intent.getBooleanExtra("canNext", false)
        actionsRow.addView(nextEpisode, weightParams(82))

        val watched = actionButton("Visto", 62) {
            NativeMailbox.write(
                this,
                JSONObject().put("type", "player_mark_watched")
                    .put("requestId", requestId)
                    .put("payload", JSONObject().put("uri", uri.toString()))
            )
            saveProgress("player_progress", force = true)
            showFeedback("Visto")
        }
        actionsRow.addView(watched, weightParams(62))
        bottomBar.addView(actionsRow)

        val morePanel = LinearLayout(this).apply {
            tag = "reiflix_more_panel"
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
            visibility = View.GONE
        }
        morePanel.addView(actionButton("Reiniciar", 72) {
            if (::player.isInitialized) {
                player.seekTo(0L)
                saveProgress("player_progress", force = true)
                showFeedback("00:00")
            }
        }, weightParams(72))
        morePanel.addView(actionButton("Autoplay " + if (autoplayNext) "ON" else "OFF", 92) { button ->
            autoplayNext = !autoplayNext
            button.text = "Autoplay " + if (autoplayNext) "ON" else "OFF"
            NativeMailbox.write(
                this@NativePlayerActivity,
                JSONObject().put("type", "player_autoplay_changed")
                    .put("requestId", requestId)
                    .put("payload", JSONObject().put("enabled", autoplayNext))
            )
            showFeedback(if (autoplayNext) "Autoplay ligado" else "Autoplay desligado")
        }, weightParams(92))
        morePanel.addView(actionButton("Timer 15m", 82) {
            showFeedback("Timer de sono não interrompe a reprodução automaticamente")
        }, weightParams(82))
        bottomBar.addView(morePanel)
    }

    private fun installBackHandler() {
        onBackPressedDispatcher.addCallback(
            this,
            object : androidx.activity.OnBackPressedCallback(true) {
                override fun handleOnBackPressed() {
                    finishPlayer("android_back")
                }
            },
        )
    }

    private fun applyRootInsets(insets: WindowInsetsCompat) {
        // System bars remain hidden. Reserve only physical display-cutout
        // safe insets so immersive mode never creates artificial gaps.
        val safe = insets.getInsets(WindowInsetsCompat.Type.displayCutout())
        val topParams = topBar.layoutParams as? FrameLayout.LayoutParams
        if (topParams != null) {
            topParams.topMargin = max(dp(4), safe.top)
            topBar.layoutParams = topParams
        }
        val bottomParams = bottomBar.layoutParams as? FrameLayout.LayoutParams
        if (bottomParams != null) {
            bottomParams.bottomMargin = max(dp(4), safe.bottom)
            bottomBar.layoutParams = bottomParams
        }
        controls.setPadding(
            max(dp(4), safe.left),
            0,
            max(dp(4), safe.right),
            0,
        )
    }

    private fun togglePlayPause() {
        if (!::player.isInitialized || errorVisible) return
        if (player.isPlaying) {
            player.pause()
            saveProgress("player_paused", force = true)
        } else {
            player.play()
        }
        touchControls()
        updatePlayPauseButton()
    }

    private fun updatePlayPauseButton() {
        if (!::playPauseButton.isInitialized) return
        playPauseButton.text = when {
            !::player.isInitialized -> "▶"
            player.isPlaying -> "❚❚"
            player.playbackState == Player.STATE_ENDED -> "↻"
            else -> "▶"
        }
    }

    private fun updateTrackButtons() {
        val audioAvailable = ::player.isInitialized && player.currentTracks.groups.any {
            it.type == C.TRACK_TYPE_AUDIO && it.isSupported
        }
        val subtitleAvailable = ::player.isInitialized && player.currentTracks.groups.any {
            it.type == C.TRACK_TYPE_TEXT && it.isSupported
        }
        findViewByTag<View>("reiflix_audio_button")?.isEnabled = audioAvailable
        findViewByTag<View>("reiflix_subtitle_button")?.isEnabled = subtitleAvailable
        findViewByTag<View>("reiflix_audio_bottom")?.isEnabled = audioAvailable
    }

    private fun updateProgressUi() {
        if (!::seekBar.isInitialized || !::player.isInitialized) return
        val duration = player.duration
        val position = player.currentPosition.coerceAtLeast(0L)
        if (duration > 0L) {
            seekBar.progress = ((position.toDouble() / duration.toDouble()) * SEEK_PROGRESS_MAX)
                .roundToInt().coerceIn(0, SEEK_PROGRESS_MAX)
        } else {
            seekBar.progress = 0
        }
        positionLabel.text = formatTime(position)
        durationLabel.text = formatTime(duration.coerceAtLeast(0L))
    }

    private fun startProgressReporting() {
        handler.removeCallbacks(progressReporter)
        handler.post(progressReporter)
    }

    private fun cycleSpeed(button: TextView) {
        if (!::player.isInitialized) return
        val speeds = floatArrayOf(.5f, .75f, 1f, 1.25f, 1.5f, 1.75f, 2f)
        val current = player.playbackParameters.speed
        val index = speeds.indexOfFirst { abs(it - current) < 0.01f }.takeIf { it >= 0 } ?: 2
        val next = speeds[(index + 1) % speeds.size]
        player.setPlaybackSpeed(next)
        button.text = String.format(java.util.Locale.US, "%.2fx", next)
        showFeedback(button.text.toString())
        touchControls()
    }

    private fun cycleAspect(button: TextView) {
        if (!::playerView.isInitialized) return
        val next = if (playerView.resizeMode == AspectRatioFrameLayout.RESIZE_MODE_ZOOM) {
            AspectRatioFrameLayout.RESIZE_MODE_FIT
        } else {
            AspectRatioFrameLayout.RESIZE_MODE_ZOOM
        }
        playerView.resizeMode = next
        button.text = if (next == AspectRatioFrameLayout.RESIZE_MODE_ZOOM) "Preencher" else "Ajustar"
        showFeedback(button.text.toString())
        touchControls()
        playerView.requestLayout()
    }

    private fun showTrackSelection(trackType: Int, label: String) {
        if (!::player.isInitialized) return
        if (!player.currentTracks.groups.any { it.type == trackType && it.isSupported }) {
            showFeedback("Nenhuma faixa disponível")
            return
        }
        TrackSelectionDialogBuilder(this, label, player, trackType)
            .setAllowAdaptiveSelections(false)
            .setAllowMultipleOverrides(false)
            .build()
            .show()
    }

    private fun seekBy(deltaMs: Long, feedbackText: String) {
        if (!::player.isInitialized || player.duration <= 0L) return
        val target = (player.currentPosition + deltaMs).coerceIn(0L, player.duration)
        player.seekTo(target)
        saveProgress("player_progress", force = true)
        showFeedback(feedbackText)
        touchControls()
    }

    private fun adjustBrightness(deltaPercent: Float) {
        val target = (brightnessLevel + deltaPercent).coerceIn(0.05f, 1f)
        runCatching {
            val attributes = window.attributes
            attributes.screenBrightness = target
            window.attributes = attributes
            brightnessLevel = target
        }.onSuccess {
            showAdjustment("BRILHO", brightnessLevel)
        }.onFailure { error ->
            logPlayer("BRIGHTNESS_CHANGE_FAILED", error)
            showFeedback("BRILHO\nIndisponível neste dispositivo", 1100L)
        }
    }

    private fun adjustVolume(deltaSteps: Int) {
        val manager = audioManager ?: return
        val maxVolume = manager.getStreamMaxVolume(AudioManager.STREAM_MUSIC).coerceAtLeast(1)
        val current = manager.getStreamVolume(AudioManager.STREAM_MUSIC)
        val next = (current + deltaSteps).coerceIn(0, maxVolume)
        runCatching {
            if (next != current) {
                manager.setStreamVolume(AudioManager.STREAM_MUSIC, next, 0)
            }
        }.onFailure { error ->
            logPlayer("VOLUME_CHANGE_FAILED", error)
            showFeedback("VOLUME\nIndisponível neste dispositivo", 1100L)
            return
        }
        showAdjustment("VOLUME", next.toFloat() / maxVolume.toFloat())
    }

    private fun adjustVolumeByFraction(fraction: Float) {
        val manager = audioManager ?: return
        val maxVolume = manager.getStreamMaxVolume(AudioManager.STREAM_MUSIC).coerceAtLeast(1)
        val current = manager.getStreamVolume(AudioManager.STREAM_MUSIC)
        val deltaSteps = (fraction * maxVolume).roundToInt()
        runCatching {
            if (deltaSteps != 0) {
                manager.setStreamVolume(
                    AudioManager.STREAM_MUSIC,
                    (current + deltaSteps).coerceIn(0, maxVolume),
                    0,
                )
            }
        }.onFailure { error ->
            logPlayer("VOLUME_CHANGE_FAILED", error)
            showFeedback("VOLUME\\nIndisponível neste dispositivo", 1100L)
            return
        }
        val effective = manager.getStreamVolume(AudioManager.STREAM_MUSIC)
        showAdjustment("VOLUME", effective.toFloat() / maxVolume)
    }

    private fun currentVolumeSummary(): String {
        val manager = audioManager ?: return "VOLUME"
        val maxVolume = manager.getStreamMaxVolume(AudioManager.STREAM_MUSIC).coerceAtLeast(1)
        return adjustmentSummary("VOLUME", manager.getStreamVolume(AudioManager.STREAM_MUSIC).toFloat() / maxVolume)
    }

    private fun adjustmentSummary(label: String, ratio: Float): String {
        val percent = (ratio.coerceIn(0f, 1f) * 100f).roundToInt()
        val bars = 10
        val filled = ((percent / 100f) * bars).roundToInt().coerceIn(0, bars)
        return label + "\n" + "█".repeat(filled) + "░".repeat(bars - filled) + "\n" + percent + "%"
    }

    private fun showAdjustment(label: String, ratio: Float) {
        showFeedback(adjustmentSummary(label, ratio), 1100L)
    }

    private fun showFeedback(message: String, durationMs: Long = 900L) {
        if (!::feedback.isInitialized) return
        feedback.text = message
        feedback.visibility = View.VISIBLE
        feedbackHideAt = System.currentTimeMillis() + durationMs
        handler.removeCallbacks(feedbackHider)
        handler.post(feedbackHider)
    }

    private fun setControlsVisible(visible: Boolean) {
        controlsVisible = visible
        controls.visibility = if (visible) View.VISIBLE else View.INVISIBLE
        if (visible) {
            touchControls()
        } else {
            moreVisible = false
            findViewByTag<View>("reiflix_more_panel")?.visibility = View.GONE
        }
    }

    private fun touchControls() {
        controlsVisible = true
        controls.visibility = View.VISIBLE
        lastControlsInteraction = System.currentTimeMillis()
        handler.removeCallbacks(controlsHider)
        if (::player.isInitialized && player.isPlaying && !errorVisible) {
            handler.postDelayed(controlsHider, CONTROL_TIMEOUT_MS)
        }
    }

    private fun scheduleControlsHide() {
        touchControls()
    }

    private fun showPlayerError(
        message: String,
        reason: String,
        payload: JSONObject = JSONObject(),
    ) {
        errorVisible = true
        if (::player.isInitialized) player.pause()
        setControlsVisible(true)
        findViewByTag<View>("reiflix_error_text")?.let { (it as TextView).text = message }
        findViewByTag<View>("reiflix_error_reason")?.let { (it as TextView).text = "Detalhe: " + reason }
        findViewByTag<View>("reiflix_error_panel")?.visibility = View.VISIBLE
        findViewByTag<View>("reiflix_error_back")?.requestFocus()
        if (::feedback.isInitialized) feedback.visibility = View.GONE
        val effectivePayload = JSONObject(payload.toString())
            .put("uri", if (::uri.isInitialized) uri.toString() else intent.getStringExtra("uri").orEmpty())
            .put("reason", reason)
        publishPlayerError(message, effectivePayload)
    }

    private fun publishPlayerError(message: String, payload: JSONObject = JSONObject()) {
        val ok = NativeMailbox.write(
            this,
            JSONObject()
                .put("type", "player_error")
                .put("requestId", requestId)
                .put("message", message)
                .put("payload", payload),
        )
        if (!ok) logPlayer("FAILED_TO_PUBLISH player_error requestId=" + requestId.ifEmpty { "-" })
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
    }

    private fun reportPlayerExit(reason: String) {
        if (exitReported) return
        exitReported = true
        suppressExitEvent = true
        val payload = JSONObject()
            .put("uri", if (::uri.isInitialized) uri.toString() else intent.getStringExtra("uri").orEmpty())
            .put("reason", reason)
        val ok = NativeMailbox.write(
            this,
            JSONObject().put("type", "player_exited")
                .put("requestId", requestId)
                .put("payload", payload),
        )
        if (!ok) logPlayer("FAILED_TO_PUBLISH player_exited requestId=" + requestId.ifEmpty { "-" })
        logPlayer("player_exit_reported reason=" + reason + " requestId=" + requestId.ifEmpty { "-" })
    }

    private fun finishPlayer(reason: String) {
        reportPlayerExit(reason)
        setResult(
            RESULT_OK,
            Intent()
                .putExtra("requestId", requestId)
                .putExtra("reason", reason),
        )
        finish()
    }

    private fun requestEpisode(eventType: String) {
        if (!::player.isInitialized) return
        if (!completionReported) saveProgress("player_progress", force = true)
        suppressExitEvent = true
        val payload = JSONObject()
            .put("uri", uri.toString())
            .put("requestId", requestId)
        NativeMailbox.write(
            this,
            JSONObject().put("type", eventType)
                .put("requestId", requestId)
                .put("payload", payload)
        )
        logPlayer(eventType + " requestId=" + requestId.ifEmpty { "-" } + " uri=" + uri)
        setResult(
            RESULT_OK,
            Intent()
                .putExtra("requestId", requestId)
                .putExtra("reason", eventType),
        )
        finish()
    }

    private fun seekToSavedPosition(savedPositionMs: Long) {
        if (!::player.isInitialized) return
        val requested = savedPositionMs.coerceAtLeast(0L)
        val duration = player.duration
        if (requested > 0L && (duration <= 0L || requested < duration)) {
            player.seekTo(requested)
        }
    }

    private fun saveProgress(eventType: String, force: Boolean = false) {
        if (!::player.isInitialized) return
        val position = player.currentPosition.coerceAtLeast(0L)
        val duration = player.duration.coerceAtLeast(0L)
        if (!force && lastSavedPosition >= 0L && abs(position - lastSavedPosition) < PROGRESS_INTERVAL_MS) return
        if (force && position == lastSavedPosition &&
            eventType != "player_completed" && eventType != "player_exited") {
            return
        }
        lastSavedPosition = position
        val ok = NativeMailbox.write(
            this,
            JSONObject().put("type", eventType)
                .put("requestId", requestId)
                .put(
                    "payload",
                    JSONObject().put("uri", uri.toString())
                        .put("positionMs", position)
                        .put("durationMs", duration),
                ),
        )
        if (!ok) logPlayer("FAILED_TO_PUBLISH " + eventType + " requestId=" + requestId.ifEmpty { "-" })
    }

    override fun onStart() {
        super.onStart()
        logPlayer("onStart requestId=" + requestId.ifEmpty { "-" })
        enterImmersiveMode()
    }

    override fun onResume() {
        super.onResume()
        logPlayer("onResume requestId=" + requestId.ifEmpty { "-" })
        enterImmersiveMode()
        if (::player.isInitialized && !errorVisible) {
            updateProgressUi()
            updatePlayPauseButton()
        }
    }

    override fun onPause() {
        saveProgress("player_paused", force = true)
        logPlayer("onPause requestId=" + requestId.ifEmpty { "-" })
        super.onPause()
    }

    override fun onStop() {
        saveProgress("player_progress", force = true)
        logPlayer("onStop finishing=" + isFinishing + " changingConfig=" + isChangingConfigurations)
        super.onStop()
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        logPlayer("onWindowFocusChanged hasFocus=" + hasFocus +
            " finishing=" + isFinishing + " resumed=" + !isFinishing)
        if (hasFocus) enterImmersiveMode()
    }

    override fun onPictureInPictureModeChanged(isInPictureInPictureMode: Boolean, newConfig: Configuration) {
        super.onPictureInPictureModeChanged(isInPictureInPictureMode, newConfig)
        logPlayer("onPictureInPictureModeChanged inPip=" + isInPictureInPictureMode)
        if (isInPictureInPictureMode) {
            handler.removeCallbacks(controlsHider)
            setControlsVisible(false)
        } else {
            enterImmersiveMode()
            if (::player.isInitialized && player.isPlaying && !errorVisible) {
                touchControls()
            }
            ViewCompat.requestApplyInsets(root)
        }
    }

    override fun onConfigurationChanged(newConfig: Configuration) {
        super.onConfigurationChanged(newConfig)
        logPlayer("onConfigurationChanged orientation=" + newConfig.orientation)
        ViewCompat.requestApplyInsets(root)
        applyImmersiveAfterLayout()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        if (::player.isInitialized) {
            outState.putLong("position_ms", player.currentPosition.coerceAtLeast(0L))
            outState.putLong("duration_ms", player.duration.coerceAtLeast(0L))
            outState.putFloat("playback_speed", player.playbackParameters.speed)
            outState.putBoolean("play_when_ready", player.playWhenReady)
            outState.putBundle("track_selection_parameters", player.trackSelectionParameters.toBundle())
        }
        if (::playerView.isInitialized) {
            outState.putInt("resize_mode", playerView.resizeMode)
        }
        outState.putBoolean("autoplay_next", autoplayNext)
        super.onSaveInstanceState(outState)
    }

    override fun onDestroy() {
        handler.removeCallbacks(progressReporter)
        handler.removeCallbacks(controlsHider)
        handler.removeCallbacks(feedbackHider)
        if (::player.isInitialized) {
            if (isFinishing && !suppressExitEvent && !exitReported && !isChangingConfigurations) {
                reportPlayerExit("activity_finish")
            }
            if (::playerView.isInitialized && playerView.player === player) {
                playerView.player = null
                logPlayer("PLAYER_VIEW_DETACHED requestId=" + requestId.ifEmpty { "-" })
            }
            player.release()
            logPlayer("player.release requestId=" + requestId.ifEmpty { "-" })
        } else if (isFinishing && !exitReported && !isChangingConfigurations) {
            reportPlayerExit("activity_finish_without_player")
        }
        logPlayer("onDestroy finishing=" + isFinishing + " changingConfig=" + isChangingConfigurations)
        super.onDestroy()
    }

    private fun enterImmersiveMode() {
        WindowCompat.setDecorFitsSystemWindows(window, false)
        WindowInsetsControllerCompat(window, window.decorView).apply {
            hide(WindowInsetsCompat.Type.systemBars())
            systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        }
        ViewCompat.requestApplyInsets(window.decorView)
    }

    private fun applyImmersiveAfterLayout() {
        window.decorView.post {
            enterImmersiveMode()
            if (::root.isInitialized) {
                val rootInsets = ViewCompat.getRootWindowInsets(window.decorView)
                if (rootInsets != null) {
                    applyRootInsets(rootInsets)
                    root.requestLayout()
                    logPlayer("ROOT_INSETS_APPLIED requestId=" + requestId.ifEmpty { "-" })
                } else {
                    logPlayer("ROOT_INSETS_UNAVAILABLE requestId=" + requestId.ifEmpty { "-" } +
                        " lifecycle=post_layout")
                }
            }
        }
    }

    private fun formatTime(valueMs: Long): String {
        val totalSeconds = (valueMs / 1000L).coerceAtLeast(0L)
        val seconds = totalSeconds % 60L
        val minutes = (totalSeconds / 60L) % 60L
        val hours = totalSeconds / 3600L
        return if (hours > 0L) {
            String.format(java.util.Locale.US, "%d:%02d:%02d", hours, minutes, seconds)
        } else {
            String.format(java.util.Locale.US, "%02d:%02d", minutes, seconds)
        }
    }

    private fun actionButton(label: String, widthDp: Int, action: (TextView) -> Unit): TextView {
        return TextView(this).apply {
            text = label
            textSize = 11f
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
            setPadding(dp(4), dp(2), dp(4), dp(2))
            isClickable = true
            isFocusable = true
            setBackgroundColor(0x66000000)
            minWidth = dp(widthDp)
            minHeight = dp(44)
            setOnClickListener { action(this) }
        }
    }

    private fun weightParams(widthDp: Int): LinearLayout.LayoutParams =
        LinearLayout.LayoutParams(0, dp(44), 1f).apply {
            marginStart = dp(2)
            marginEnd = dp(2)
        }

    private fun dp(value: Int): Int =
        (value * resources.displayMetrics.density).roundToInt().coerceAtLeast(1)

    private fun sourceFor(localUri: Uri): String {
        return when {
            localUri.scheme.equals("content", true) && localUri.authority == MediaStore.AUTHORITY -> "mediastore"
            localUri.scheme.equals("content", true) -> "saf"
            localUri.scheme.equals("file", true) -> "broad_storage"
            else -> "unknown"
        }
    }

    private fun normalizeLocalReference(rawReference: String): Uri? {
        val reference = rawReference.trim()
        if (reference.isBlank()) return null
        val parsed = runCatching { Uri.parse(reference) }.getOrNull() ?: return null
        if (parsed.scheme.isNullOrBlank() && reference.startsWith(File.separator)) {
            return runCatching { Uri.fromFile(File(reference).canonicalFile) }.getOrNull()
        }
        val scheme = parsed.scheme?.lowercase()
        if (scheme != "content" && scheme != "file") return null
        return if (parsed.scheme == scheme) parsed else parsed.buildUpon().scheme(scheme).build()
    }

    private fun validateLocalSource(localUri: Uri): String? {
        val result = when (localUri.scheme?.lowercase()) {
            "content" -> {
                val safAuthorized = runCatching {
                    SafScanner.isAuthorizedDocument(this, localUri)
                }.getOrDefault(false)
                val mediaStoreAuthorized = if (!safAuthorized) {
                    runCatching {
                        MediaStoreScanner.isAuthorizedDocument(this, localUri)
                    }.getOrDefault(false)
                } else false
                logPlayer("AUTH_CHECK uri=" + localUri + " saf=" + safAuthorized + " mediastore=" + mediaStoreAuthorized)
                if (!safAuthorized && !mediaStoreAuthorized) {
                    if (localUri.authority == MediaStore.AUTHORITY &&
                        !MediaStoreScanner.hasReadPermission(this)) {
                        "A permissão para ler vídeos foi revogada."
                    } else {
                        "A autorização deste arquivo não está mais disponível ou o provedor local está indisponível."
                    }
                } else {
                    val readable = runCatching {
                        contentResolver.openFileDescriptor(localUri, "r")?.use { true } == true
                    }.onFailure { error ->
                        logPlayer("CONTENT_READ_PREFLIGHT_FAILED uri=" + localUri, error)
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
                val authorized = runCatching {
                    BroadStorageScanner.isAuthorizedFile(this, localUri)
                }.getOrDefault(false)
                logPlayer("AUTH_CHECK uri=" + localUri + " broad=" + authorized + " exists=" + file.exists())
                when {
                    !file.exists() -> "Arquivo local removido ou indisponível."
                    !file.isFile -> "A referência local não aponta para um arquivo."
                    !authorized -> "Este arquivo não pertence a uma pasta autorizada pelo Rei-Flix."
                    !file.canRead() -> "O arquivo local não pode ser lido neste momento."
                    else -> null
                }
            }
            else -> "A reprodução aceita somente referências locais content:// ou file://."
        }
        logPlayer("validateLocalSource result=" + (result ?: "OK") + " uri=" + localUri)
        return result
    }

    private fun <T : View> findViewByTag(tagValue: String): T? =
        root.findViewWithTag(tagValue)

    private fun logPlayer(message: String, error: Throwable? = null) {
        if (error != null) {
            android.util.Log.e(TAG, message, error)
        } else {
            android.util.Log.i(TAG, message)
        }
    }

    private inner class GestureLayer(context: Context) : View(context) {
        private val gestureDetector = GestureDetector(
            context,
            object : GestureDetector.SimpleOnGestureListener() {
                override fun onDown(e: MotionEvent): Boolean = true

                override fun onDoubleTap(e: MotionEvent): Boolean {
                    if (errorVisible || gestureMode != GestureMode.NONE || !::player.isInitialized) return true
                    val leftZone = width * 0.32f
                    val rightZone = width * 0.68f
                    when {
                        e.x < leftZone -> seekBy(-10_000L, "−10s")
                        e.x > rightZone -> seekBy(10_000L, "+10s")
                        else -> togglePlayPause()
                    }
                    gestureConsumed = true
                    suppressTapUntil = android.os.SystemClock.uptimeMillis() +
                        ViewConfiguration.getDoubleTapTimeout() + 80L
                    touchControls()
                    return true
                }

                override fun onSingleTapConfirmed(e: MotionEvent): Boolean {
                    if (!errorVisible &&
                        gestureMode == GestureMode.NONE &&
                        !gestureConsumed &&
                        android.os.SystemClock.uptimeMillis() >= suppressTapUntil
                    ) {
                        setControlsVisible(!controlsVisible)
                    }
                    return true
                }
            },
        )

        private val scaleDetector = ScaleGestureDetector(
            context,
            object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
                override fun onScaleBegin(detector: ScaleGestureDetector): Boolean {
                    gestureConsumed = true
                    gestureMode = GestureMode.NONE
                    touchControls()
                    return true
                }

                override fun onScale(detector: ScaleGestureDetector): Boolean {
                    if (errorVisible) return true
                    if (detector.scaleFactor > 1.02f) {
                        playerView.resizeMode = AspectRatioFrameLayout.RESIZE_MODE_ZOOM
                        showFeedback("ZOOM")
                    } else if (detector.scaleFactor < 0.98f) {
                        playerView.resizeMode = AspectRatioFrameLayout.RESIZE_MODE_FIT
                        showFeedback("FIT")
                    }
                    touchControls()
                    return true
                }

                override fun onScaleEnd(detector: ScaleGestureDetector) {
                    showFeedback(if (playerView.resizeMode == AspectRatioFrameLayout.RESIZE_MODE_ZOOM) "ZOOM" else "FIT")
                }
            },
        )

        private var downX = 0f
        private var downY = 0f
        private var lastX = 0f
        private var lastY = 0f
        private var downAt = 0L
        private var seekStartPosition = 0L
        private var gestureMode = GestureMode.NONE
        private var gestureConsumed = false
        private var suppressTapUntil = 0L
        private var scaled = false

        override fun onTouchEvent(event: MotionEvent): Boolean {
            scaleDetector.onTouchEvent(event)
            if (event.pointerCount > 1) {
                scaled = true
                gestureConsumed = true
                return true
            }

            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    downX = event.x
                    downY = event.y
                    lastX = event.x
                    lastY = event.y
                    downAt = System.currentTimeMillis()
                    seekStartPosition = if (::player.isInitialized) player.currentPosition else 0L
                    gestureMode = GestureMode.NONE
                    if (android.os.SystemClock.uptimeMillis() >= suppressTapUntil) {
                        gestureConsumed = false
                    }
                    scaled = false
                }

                MotionEvent.ACTION_MOVE -> {
                    if (scaled || errorVisible) return true
                    val dx = event.x - downX
                    val dy = event.y - downY
                    val absX = abs(dx)
                    val absY = abs(dy)
                    if (gestureMode == GestureMode.NONE &&
                        (absX > dp(28) || absY > dp(28))) {
                        gestureConsumed = true
                        gestureMode = when {
                            absX > absY * 1.15f && absX > dp(44) -> GestureMode.HORIZONTAL_SEEK
                            absY > absX * 1.15f && absY > dp(44) ->
                                if (downX < width / 2f) GestureMode.VERTICAL_BRIGHTNESS
                                else GestureMode.VERTICAL_VOLUME
                            else -> GestureMode.NONE
                        }
                        if (gestureMode != GestureMode.NONE) touchControls()
                    }

                    when (gestureMode) {
                        GestureMode.HORIZONTAL_SEEK -> {
                            if (!::player.isInitialized || player.duration <= 0L) return true
                            val previewDelta = (dx / resources.displayMetrics.density * 40L)
                                .roundToInt().toLong()
                            val target = (seekStartPosition + previewDelta)
                                .coerceIn(0L, player.duration)
                            pendingSeekPosition = target
                            showFeedback(
                                if (previewDelta < 0) "−" + formatTime(abs(previewDelta))
                                else "+" + formatTime(abs(previewDelta)),
                                700L,
                            )
                        }
                        GestureMode.VERTICAL_BRIGHTNESS -> {
                            val deltaY = event.y - lastY
                            adjustBrightness((-deltaY / height.coerceAtLeast(1).toFloat()) * 1.25f)
                        }
                        GestureMode.VERTICAL_VOLUME -> {
                            val deltaY = event.y - lastY
                            adjustVolumeByFraction(-deltaY / height.coerceAtLeast(1).toFloat())
                        }
                        GestureMode.NONE -> Unit
                    }
                    lastX = event.x
                    lastY = event.y
                }

                MotionEvent.ACTION_UP -> {
                    if (!scaled && gestureMode != GestureMode.NONE) {
                        if (gestureMode == GestureMode.HORIZONTAL_SEEK) {
                            pendingSeekPosition?.let { target ->
                                if (::player.isInitialized && player.duration > 0L) {
                                    player.seekTo(target.coerceIn(0L, player.duration))
                                    saveProgress("player_progress", force = true)
                                }
                            }
                        }
                        showFeedback(
                            when (gestureMode) {
                                GestureMode.VERTICAL_BRIGHTNESS -> adjustmentSummary("BRILHO", brightnessLevel)
                                GestureMode.VERTICAL_VOLUME -> currentVolumeSummary()
                                GestureMode.HORIZONTAL_SEEK -> pendingSeekPosition?.let(::formatTime)
                                    ?: if (::player.isInitialized) formatTime(player.currentPosition) else ""
                                else -> if (::player.isInitialized) formatTime(player.currentPosition) else ""
                            },
                            900L,
                        )
                        touchControls()
                    }
                    val wasGesture = gestureConsumed || scaled || gestureMode != GestureMode.NONE
                    gestureMode = GestureMode.NONE
                    scaled = false
                    pendingSeekPosition = null
                    if (wasGesture) {
                        gestureConsumed = true
                        suppressTapUntil =
                            android.os.SystemClock.uptimeMillis() + ViewConfiguration.getDoubleTapTimeout() + 80L
                    }
                }

                MotionEvent.ACTION_CANCEL -> {
                    gestureMode = GestureMode.NONE
                    scaled = false
                    pendingSeekPosition = null
                    gestureConsumed = true
                    suppressTapUntil =
                        android.os.SystemClock.uptimeMillis() + ViewConfiguration.getDoubleTapTimeout()
                }
            }

            gestureDetector.onTouchEvent(event)
            return true
        }
    }

    companion object {
        private const val TAG = "[REIFLIX][PLAYER]"
        private const val PROGRESS_INTERVAL_MS = 15_000L
        private const val CONTROL_TIMEOUT_MS = 3_500L
        private const val SEEK_PROGRESS_MAX = 1000
    }
}
