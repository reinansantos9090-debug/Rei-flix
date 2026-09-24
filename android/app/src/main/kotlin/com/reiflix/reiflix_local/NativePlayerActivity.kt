package com.reiflix.reiflix_local

import android.app.AlertDialog
import android.app.PictureInPictureParams
import android.content.Context
import android.content.Intent
import android.content.pm.ActivityInfo
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.graphics.Color
import android.graphics.Matrix
import android.graphics.Typeface
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
import android.view.ScaleGestureDetector
import android.view.TextureView
import android.animation.ValueAnimator
import android.view.ViewConfiguration
import android.view.WindowManager
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ProgressBar
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
    private lateinit var preparingIndicator: ProgressBar

    private val handler = Handler(Looper.getMainLooper())
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
        aspectModeLabel = savedInstanceState?.getString("aspect_mode_label") ?: "Ajustar"
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

            prepareCurrentMedia("initial", savedInstanceState?.takeIf { it.containsKey("play_when_ready") }?.getBoolean("play_when_ready"))
        } catch (exception: Exception) {
            if (::preparingIndicator.isInitialized) preparingIndicator.visibility = View.GONE
            logPlayer("EXOPLAYER_INIT_FAILED requestId=" + requestId.ifEmpty { "-" }, exception)
            showPlayerError("Não foi possível iniciar o player local.", "player_initialization")
        }
    }

    override fun onNewIntent(newIntent: Intent) {
        super.onNewIntent(newIntent)
        setIntent(newIntent)
        logPlayer(
            "PLAYER_REUSE_INTENT requestId=" +
                (newIntent.getStringExtra("requestId")?.trim().orEmpty().ifBlank { "-" }),
        )

        val rawUri = newIntent.getStringExtra("uri")
        if (rawUri.isNullOrBlank()) {
            episodeChangePending = false
            showPlayerError("Arquivo local inválido.", "missing_uri_on_reuse")
            return
        }
        val normalized = normalizeLocalReference(rawUri)
        if (normalized == null) {
            episodeChangePending = false
            showPlayerError("Referência local inválida.", "invalid_uri_on_reuse")
            return
        }
        val preflightError = validateLocalSource(normalized)
        if (preflightError != null) {
            episodeChangePending = false
            showPlayerError(preflightError, "preflight_on_reuse")
            return
        }

        uri = normalized
        requestId = newIntent.getStringExtra("requestId")?.trim().orEmpty()
        episodeChangePending = false
        restoredPositionMs = null
        initialSeekApplied = false
        completionReported = false
        openedReported = false
        exitReported = false
        suppressExitEvent = false
        errorVisible = false
        aspectModeLabel = findViewByTag<TextView>("reiflix_aspect_button")?.text?.toString() ?: aspectModeLabel

        findViewByTag<TextView>("reiflix_player_title")?.text =
            newIntent.getStringExtra("title") ?: "Episódio"
        findViewByTag<TextView>("reiflix_next_episode")?.isEnabled =
            newIntent.getBooleanExtra("canNext", false)
        findViewByTag<TextView>("reiflix_previous_episode")?.isEnabled =
            newIntent.getBooleanExtra("canPrevious", false)
        findViewByTag<View>("reiflix_error_panel")?.visibility = View.GONE
        if (::preparingIndicator.isInitialized) preparingIndicator.visibility = View.VISIBLE
        moreVisible = false
        findViewByTag<View>("reiflix_more_panel")?.visibility = View.GONE
        setControlsVisible(true)

        try {
            prepareCurrentMedia("reuse")
        } catch (exception: Exception) {
            logPlayer("MEDIA_REUSE_FAILED requestId=" + requestId.ifEmpty { "-" }, exception)
            showPlayerError("Não foi possível iniciar o próximo episódio local.", "player_reuse", JSONObject()
                .put("error", exception.message ?: exception::class.java.simpleName))
        }
    }

    private fun buildMediaItem(mediaUri: Uri): MediaItem {
        val mediaItemBuilder = MediaItem.Builder()
            .setUri(mediaUri)
            .setMediaId(mediaUri.toString())
        val subtitleTracks = LocalSubtitleResolver.resolve(this, mediaUri)
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
        return mediaItemBuilder.build()
    }

    private fun prepareCurrentMedia(reason: String, playWhenReadyOverride: Boolean? = null) {
        if (!::player.isInitialized) return
        initialSeekApplied = false
        completionReported = false
        firstFrameRenderedForTesting = false
        if (::preparingIndicator.isInitialized) preparingIndicator.visibility = View.VISIBLE

        val mediaItem = buildMediaItem(uri)
        val shouldPlayWhenReady = playWhenReadyOverride
            ?: intent.getBooleanExtra("autoplay", true)

        logPlayer(
            "MEDIA_ITEM requestId=" + requestId.ifEmpty { "-" } +
                " uri=" + mediaItem.localConfiguration?.uri +
                " reason=" + reason,
        )
        player.pause()
        player.setMediaItem(mediaItem)
        player.playWhenReady = shouldPlayWhenReady
        logPlayer(
            "PLAY_WHEN_READY=" + player.playWhenReady +
                " requestId=" + requestId.ifEmpty { "-" } +
                " reason=" + reason,
        )
        logPlayer("PREPARE requestId=" + requestId.ifEmpty { "-" } + " reason=" + reason)
        player.prepare()
        updateTrackButtons()
        updatePlayPauseButton()
        updateProgressUi()
    }

    private val playerListener = object : Player.Listener {
        override fun onEvents(player: Player, events: Player.Events) {
            if (events.contains(Player.EVENT_RENDERED_FIRST_FRAME)) {
                firstFrameRenderedForTesting = true
                if (::preparingIndicator.isInitialized) preparingIndicator.visibility = View.GONE
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
                    retryCount = 0
                    // READY means the media is prepared, but keep the preparation
                    // indicator until Media3 actually renders the first frame.
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
                                    .put("mediaId", uri.toString())
                                    .put("episodeId", intent.getStringExtra("episodeId").orEmpty())
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
                reason == Player.DISCONTINUITY_REASON_SEEK_ADJUSTMENT
            ) {
                logPlayer(
                    "PLAYER_SEEK requestId=" + requestId.ifEmpty { "-" } +
                        " positionMs=" + newPosition.positionMs,
                )
                saveProgress("player_progress", force = true)
            }
            updateProgressUi()
        }

        override fun onTracksChanged(tracks: androidx.media3.common.Tracks) {
            logPlayer(
                "PLAYER_TRACK_CHANGE requestId=" + requestId.ifEmpty { "-" } +
                    " audio=" + tracks.groups.count { it.type == C.TRACK_TYPE_AUDIO && it.isSupported } +
                    " text=" + tracks.groups.count { it.type == C.TRACK_TYPE_TEXT && it.isSupported },
            )
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
        playerView = layoutInflater.inflate(
            R.layout.native_player_view,
            root,
            false,
        ) as PlayerView
        playerView.apply {
            tag = "reiflix_player_view"
            useController = false
            controllerAutoShow = false
            controllerHideOnTouch = false
            keepScreenOn = true
            setShutterBackgroundColor(Color.BLACK)
            resizeMode = AspectRatioFrameLayout.RESIZE_MODE_FIT
        }
        root.addView(playerView)

        preparingIndicator = ProgressBar(this).apply {
            tag = "reiflix_player_preparing"
            isIndeterminate = true
            visibility = View.VISIBLE
            contentDescription = "Preparando vídeo"
        }
        root.addView(
            preparingIndicator,
            FrameLayout.LayoutParams(dp(48), dp(48)).apply {
                gravity = Gravity.CENTER
            },
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
            tag = "reiflix_controls_root"
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
        controls.bringToFront()

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
            logPlayer("PLAYER_BACK BACK_BUTTON_TOUCH requestId=" + requestId.ifEmpty { "-" })
            finishPlayer("back_button")
        }
        back.tag = "reiflix_back_button"
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
            tag = "reiflix_player_title"
            contentDescription = "Título do episódio"
        }
        topBar.addView(title, LinearLayout.LayoutParams(0, dp(48), 1f))



        val moreButton = actionButton("⋮", 48) {
            moreVisible = !moreVisible
            findViewByTag<View>("reiflix_more_panel")?.visibility = if (moreVisible) View.VISIBLE else View.GONE
            touchControls()
        }
        moreButton.contentDescription = "Mais opções"
        moreButton.tag = "reiflix_more_button"
        topBar.addView(moreButton, weightParams(48))

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
        val errorRetry = actionButton("Tentar novamente", 170) {
            retryCurrentMedia()
        }
        errorRetry.tag = "reiflix_error_retry"
        errorPanel.addView(errorRetry, LinearLayout.LayoutParams(dp(190), dp(48)).apply {
            gravity = Gravity.CENTER_HORIZONTAL
            topMargin = dp(14)
        })

        val errorBack = actionButton("Voltar ao Rei-Flix", 170) {
            finishPlayer("player_error_back")
        }
        errorBack.tag = "reiflix_error_back"
        errorPanel.addView(errorBack, LinearLayout.LayoutParams(dp(190), dp(48)).apply {
            gravity = Gravity.CENTER_HORIZONTAL
            topMargin = dp(8)
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

        val morePanel = LinearLayout(this).apply {
            tag = "reiflix_more_panel"
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(dp(8), dp(8), dp(8), dp(8))
            setBackgroundColor(0xE614141A.toInt())
            visibility = View.GONE
        }
        fun addMoreRow(vararg buttons: View) {
            val row = LinearLayout(this@NativePlayerActivity).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER
            }
            buttons.forEach { row.addView(it, weightParams(96)) }
            morePanel.addView(row)
        }
        val previousEpisode = actionButton("Anterior", 92) {
            if (intent.getBooleanExtra("canPrevious", false)) requestEpisode("player_previous_request")
        }.apply {
            tag = "reiflix_previous_episode"
            isEnabled = intent.getBooleanExtra("canPrevious", false)
        }
        val nextEpisode = actionButton("Próximo", 92) {
            if (intent.getBooleanExtra("canNext", false)) requestEpisode("player_next_request")
        }.apply {
            tag = "reiflix_next_episode"
            isEnabled = intent.getBooleanExtra("canNext", false)
        }
        val audio = actionButton("Áudio", 92) { showTrackSelection(C.TRACK_TYPE_AUDIO, "Áudio") }.apply {
            tag = "reiflix_audio_button"
        }
        val subtitle = actionButton("Legenda", 92) { showTrackSelection(C.TRACK_TYPE_TEXT, "Legendas") }.apply {
            tag = "reiflix_subtitle_button"
        }
        val speed = actionButton("Velocidade", 92) { button -> showSpeedSelection(button) }.apply {
            tag = "reiflix_speed_button"
        }
        val aspect = actionButton("Aspecto", 92) { button -> showAspectSelection(button) }.apply {
            text = aspectModeLabel
            tag = "reiflix_aspect_button"
        }
        addMoreRow(previousEpisode, nextEpisode)
        addMoreRow(audio, subtitle)
        addMoreRow(speed, aspect)
        addMoreRow(actionButton("Reiniciar", 92) {
            if (::player.isInitialized) {
                player.seekTo(0L)
                saveProgress("player_progress", force = true)
                showFeedback("00:00")
            }
        }, actionButton("Autoplay", 92) { button ->
            autoplayNext = !autoplayNext
            button.text = "Autoplay " + if (autoplayNext) "ON" else "OFF"
            NativeMailbox.write(
                this@NativePlayerActivity,
                JSONObject().put("type", "player_autoplay_changed")
                    .put("requestId", requestId)
                    .put("payload", JSONObject().put("enabled", autoplayNext))
            )
            showFeedback(if (autoplayNext) "Autoplay ligado" else "Autoplay desligado")
        })
        if (canEnterPictureInPicture()) {
            val pip = actionButton("PIP", 92) { enterPictureInPictureMode() }
            pip.contentDescription = "Picture in Picture"
            addMoreRow(pip)
        }
        controls.addView(morePanel, FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.WRAP_CONTENT,
            FrameLayout.LayoutParams.WRAP_CONTENT,
        ).apply {
            gravity = Gravity.TOP or Gravity.END
            topMargin = dp(56)
            rightMargin = dp(8)
        })
    }
    private fun installBackHandler() {
        onBackPressedDispatcher.addCallback(
            this,
            object : androidx.activity.OnBackPressedCallback(true) {
                override fun handleOnBackPressed() {
                    logPlayer("PLAYER_BACK ANDROID_BACK requestId=" + requestId.ifEmpty { "-" })
                    if (moreVisible) {
                        moreVisible = false
                        findViewByTag<View>("reiflix_more_panel")?.visibility = View.GONE
                        touchControls()
                        return
                    }
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
        when {
            player.playbackState == Player.STATE_ENDED -> {
                // The UI already exposes the replay affordance (↻) for an ended
                // item, so tapping it must explicitly rewind before playback.
                player.seekTo(0L)
                player.play()
                logPlayer("PLAYER_PLAY requestId=" + requestId.ifEmpty { "-" } + " reason=replay")
            }
            player.isPlaying -> {
                player.pause()
                logPlayer("PLAYER_PAUSE requestId=" + requestId.ifEmpty { "-" })
                saveProgress("player_paused", force = true)
            }
            else -> {
                player.play()
                logPlayer("PLAYER_PLAY requestId=" + requestId.ifEmpty { "-" })
            }
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
        val audioCount = if (::player.isInitialized) {
            player.currentTracks.groups.count { it.type == C.TRACK_TYPE_AUDIO && it.isSupported }
        } else 0
        val subtitleCount = if (::player.isInitialized) {
            player.currentTracks.groups.count { it.type == C.TRACK_TYPE_TEXT && it.isSupported }
        } else 0
        val audioAvailable = audioCount > 1
        val subtitleAvailable = subtitleCount > 0
        findViewByTag<View>("reiflix_audio_button")?.isEnabled = audioAvailable
        findViewByTag<View>("reiflix_subtitle_button")?.isEnabled = subtitleAvailable
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

    private fun showSpeedSelection(button: TextView) {
        if (!::player.isInitialized) return
        val speeds = floatArrayOf(.5f, .75f, 1f, 1.25f, 1.5f, 1.75f, 2f)
        val labels = speeds.map { String.format(java.util.Locale.US, "%.2fx", it) }.toTypedArray()
        val currentIndex = speeds.indices.minByOrNull { abs(speeds[it] - player.playbackParameters.speed) } ?: 2
        touchControls()
        AlertDialog.Builder(this)
            .setTitle("Velocidade")
            .setSingleChoiceItems(labels, currentIndex) { dialog, which ->
                player.setPlaybackSpeed(speeds[which])
                button.text = labels[which]
                showFeedback(labels[which])
                touchControls()
                dialog.dismiss()
            }
            .setNegativeButton("Cancelar", null)
            .show()
    }

    private fun showAspectSelection(button: TextView) {
        val labels = arrayOf("Ajustar", "Preencher", "Zoom", "Original", "Auto")
        val current = when (button.text.toString()) {
            in labels -> button.text.toString()
            else -> "Ajustar"
        }
        val currentIndex = labels.indexOf(current).coerceAtLeast(0)
        touchControls()
        AlertDialog.Builder(this)
            .setTitle("Aspecto")
            .setSingleChoiceItems(labels, currentIndex) { dialog, which ->
                applyAspectMode(labels[which], button)
                dialog.dismiss()
            }
            .setNegativeButton("Cancelar", null)
            .show()
    }

    private fun applyAspectMode(mode: String, button: TextView) {
        if (!::playerView.isInitialized) return
        findViewByTag<GestureLayer>("reiflix_gesture_layer")?.resetZoomToFit()
        playerView.resizeMode = when (mode) {
            "Preencher" -> AspectRatioFrameLayout.RESIZE_MODE_FILL
            "Zoom" -> AspectRatioFrameLayout.RESIZE_MODE_ZOOM
            "Original", "Auto" -> AspectRatioFrameLayout.RESIZE_MODE_FIT
            else -> AspectRatioFrameLayout.RESIZE_MODE_FIT
        }
        button.text = mode
        showFeedback(
            when (mode) {
                "Original", "Auto" -> "$mode • Ajustar"
                else -> mode
            }
        )
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

    private fun retryCurrentMedia() {
        if (!::player.isInitialized) {
            logPlayer("PLAYER_RETRY_UNAVAILABLE requestId=" + requestId.ifEmpty { "-" })
            return
        }
        if (retryCount >= MAX_RETRY_ATTEMPTS) {
            showFeedback("Limite de tentativas atingido", 1400L)
            return
        }
        retryCount += 1
        errorVisible = false
        moreVisible = false
        findViewByTag<View>("reiflix_error_panel")?.visibility = View.GONE
        findViewByTag<View>("reiflix_more_panel")?.visibility = View.GONE
        if (::preparingIndicator.isInitialized) preparingIndicator.visibility = View.VISIBLE
        logPlayer(
            "PLAYER_RETRY requestId=" + requestId.ifEmpty { "-" } +
                " attempt=" + retryCount,
        )
        prepareCurrentMedia(
            "retry",
            playWhenReadyOverride = intent.getBooleanExtra("autoplay", true),
        )
    }

    private fun showPlayerError(
        message: String,
        reason: String,
        payload: JSONObject = JSONObject(),
    ) {
        errorVisible = true
        if (::preparingIndicator.isInitialized) preparingIndicator.visibility = View.GONE
        if (::player.isInitialized) player.pause()
        setControlsVisible(true)
        findViewByTag<View>("reiflix_error_text")?.let { (it as TextView).text = message }
        findViewByTag<View>("reiflix_error_reason")?.let { (it as TextView).text = "Detalhe: " + reason }
        findViewByTag<View>("reiflix_error_retry")?.visibility =
            if (::player.isInitialized) View.VISIBLE else View.GONE
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
        val currentPosition = if (::player.isInitialized) player.currentPosition.coerceAtLeast(0L) else 0L
        val currentDuration = if (::player.isInitialized) player.duration.coerceAtLeast(0L) else 0L
        val payload = JSONObject()
            .put("uri", if (::uri.isInitialized) uri.toString() else intent.getStringExtra("uri").orEmpty())
            .put("mediaId", if (::uri.isInitialized) uri.toString() else intent.getStringExtra("mediaId").orEmpty())
            .put("episodeId", intent.getStringExtra("episodeId").orEmpty())
            .put("positionMs", currentPosition)
            .put("durationMs", currentDuration)
            .put("completion", completionReported)
            .put("reason", reason)
            .put("timestamp", System.currentTimeMillis())
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
        if (!::player.isInitialized || episodeChangePending || errorVisible) return
        if (!completionReported) saveProgress("player_progress", force = true)
        episodeChangePending = true
        val payload = JSONObject()
            .put("uri", uri.toString())
            .put("requestId", requestId)
            .put("positionMs", player.currentPosition.coerceAtLeast(0L))
            .put("durationMs", player.duration.coerceAtLeast(0L))
        NativeMailbox.write(
            this,
            JSONObject().put("type", eventType)
                .put("requestId", requestId)
                .put("payload", payload)
        )
        logPlayer(eventType + " requestId=" + requestId.ifEmpty { "-" } + " uri=" + uri + " keepActivity=true")
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
        findViewByTag<GestureLayer>("reiflix_gesture_layer")?.refreshZoomForLayout()
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
        logPlayer("PLAYER_PIP inPip=" + isInPictureInPictureMode + " requestId=" + requestId.ifEmpty { "-" })
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
        findViewByTag<GestureLayer>("reiflix_gesture_layer")?.refreshZoomForLayout()
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
        outState.putString("aspect_mode_label", findViewByTag<TextView>("reiflix_aspect_button")?.text?.toString() ?: "Ajustar")
        super.onSaveInstanceState(outState)
    }

    override fun onDestroy() {
        findViewByTag<GestureLayer>("reiflix_gesture_layer")?.resetZoomToFit()
        findViewByTag<GestureLayer>("reiflix_gesture_layer")?.dispose()
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

    /**
     * Single owner for player touch arbitration. The order is:
     * tap/double-tap -> single-finger swipe -> two-finger zoom/pan.
     * A pending single tap is delayed so a second tap can cancel it, matching
     * the interaction model used by CloudStream's PlayerGestureHelper.
     */
    private inner class GestureLayer(context: Context) : View(context) {
        private val scaleDetector = ScaleGestureDetector(
            context,
            object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
                override fun onScaleBegin(detector: ScaleGestureDetector): Boolean {
                    if (errorVisible || !::playerView.isInitialized || !::player.isInitialized) {
                        return false
                    }
                    pinchActive = true
                            logPlayer("GESTURE_START type=pinch requestId=" + requestId.ifEmpty { "-" })
                                    touchControls()
                    lastPanX = (detector.focusX)
                    lastPanY = detector.focusY
                    return true
                }

                override fun onScale(detector: ScaleGestureDetector): Boolean {
                    if (!pinchActive || errorVisible) return true
                    val rawFactor = detector.scaleFactor
                    if (!rawFactor.isFinite() || rawFactor <= 0f) return true

                    val previousScale = zoomScale
                    val nextScale = (previousScale * rawFactor).coerceIn(MIN_ZOOM, MAX_ZOOM)
                    val effectiveFactor = if (previousScale <= 0f) 1f else nextScale / previousScale
                    val pivotX = detector.focusX - width * 0.5f
                    val pivotY = detector.focusY - height * 0.5f

                    zoomTranslationX += (1f - effectiveFactor) * (pivotX - zoomTranslationX)
                    zoomTranslationY += (1f - effectiveFactor) * (pivotY - zoomTranslationY)
                    zoomScale = nextScale
                    playerView.resizeMode = AspectRatioFrameLayout.RESIZE_MODE_ZOOM
                    applyZoomTransform()

                    val label = if (zoomScale <= 1.02f) "FIT" else "ZOOM " +
                        String.format(java.util.Locale.US, "%.1fx", zoomScale)
                    showFeedback(label, 250L)
                    return true
                }

                override fun onScaleEnd(detector: ScaleGestureDetector) {
                    if (!pinchActive) return
                    finishPinchGesture()
                }
            },
        )

        private var downX = 0f
        private var downY = 0f
        private var pinchActive = false
        private var wasPinchGesture = false
        private var lastPanX: Float? = null
        private var lastPanY: Float? = null
        private var zoomScale = 1f
        private var zoomTranslationX = 0f
        private var zoomTranslationY = 0f
        private var zoomAnimator: ValueAnimator? = null
        private var ignoredVerticalGesture = false

        override fun onTouchEvent(event: MotionEvent): Boolean {
            scaleDetector.onTouchEvent(event)

            if (pinchActive || event.pointerCount > 1) {
                when (event.actionMasked) {
                    MotionEvent.ACTION_POINTER_DOWN -> {
                        lastPanX = pointerCenterX(event)
                        lastPanY = pointerCenterY(event)
                    }
                    MotionEvent.ACTION_MOVE -> {
                        if (event.pointerCount >= 2) {
                            val centerX = pointerCenterX(event)
                            val centerY = pointerCenterY(event)
                            val previousX = lastPanX
                            val previousY = lastPanY
                            if (previousX != null && previousY != null && zoomScale > 1.01f) {
                                zoomTranslationX += centerX - previousX
                                zoomTranslationY += centerY - previousY
                                applyZoomTransform()
                            }
                            lastPanX = centerX
                            lastPanY = centerY
                        }
                    }
                    MotionEvent.ACTION_POINTER_UP -> if (event.pointerCount <= 2) {
                        lastPanX = null
                        lastPanY = null
                    }
                    MotionEvent.ACTION_CANCEL, MotionEvent.ACTION_UP -> finishPinchGesture()
                }
                return true
            }

            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    downX = event.x
                    downY = event.y
                    ignoredVerticalGesture = false
                }
                MotionEvent.ACTION_MOVE -> {
                    if (errorVisible) return true
                    val dx = event.x - downX
                    val dy = event.y - downY
                    if (!ignoredVerticalGesture && abs(dy) > dp(24) && abs(dy) > abs(dx) * 1.15f) {
                        ignoredVerticalGesture = true
                        logPlayer("GESTURE_START type=vertical_ignored requestId=" + requestId.ifEmpty { "-" })
                    }
                }
                MotionEvent.ACTION_UP -> {
                    if (ignoredVerticalGesture) {
                        logPlayer("GESTURE_END type=vertical_ignored requestId=" + requestId.ifEmpty { "-" })
                    } else if (!wasPinchGesture && !errorVisible) {
                        handleTap()
                    }
                    wasPinchGesture = false
                    ignoredVerticalGesture = false
                }
                MotionEvent.ACTION_CANCEL -> {
                    logPlayer("GESTURE_END type=cancel requestId=" + requestId.ifEmpty { "-" })
                    ignoredVerticalGesture = false
                }
            }
            return true
        }

        fun refreshZoomForLayout() {
            if (zoomScale > 1.01f) {
                applyZoomTransform()
            } else {
                zoomScale = 1f
                zoomTranslationX = 0f
                zoomTranslationY = 0f
                val video = playerView.videoSurfaceView
                if (video is TextureView) {
                    video.setTransform(Matrix())
                } else {
                    video?.apply {
                        scaleX = 1f
                        scaleY = 1f
                        translationX = 0f
                        translationY = 0f
                    }
                }
            }
        }

        fun dispose() {
            zoomAnimator?.cancel()
            zoomAnimator = null
            lastPanX = null
            lastPanY = null
            pinchActive = false
            wasPinchGesture = false
        }

        fun resetZoomToFit() {
            zoomAnimator?.cancel()
            zoomAnimator = null
            zoomScale = 1f
            zoomTranslationX = 0f
            zoomTranslationY = 0f
            if (::playerView.isInitialized) {
                playerView.resizeMode = AspectRatioFrameLayout.RESIZE_MODE_FIT
                val video = playerView.videoSurfaceView
                if (video is TextureView) {
                    video.setTransform(Matrix())
                } else {
                    video?.apply {
                        scaleX = 1f
                        scaleY = 1f
                        translationX = 0f
                        translationY = 0f
                    }
                }
            }
        }

        private fun finishPinchGesture() {
            if (!pinchActive) return
            pinchActive = false
            wasPinchGesture = true
            logPlayer("GESTURE_END type=pinch requestId=" + requestId.ifEmpty { "-" })
            lastPanX = null
            lastPanY = null

            if (zoomScale <= ZOOM_SNAP_THRESHOLD) {
                animateZoomToFit()
            } else {
                playerView.resizeMode = AspectRatioFrameLayout.RESIZE_MODE_ZOOM
                applyZoomTransform()
                showFeedback(
                    "ZOOM " + String.format(java.util.Locale.US, "%.1fx", zoomScale),
                    900L,
                )
            }
            touchControls()
        }

        private fun animateZoomToFit() {
            zoomAnimator?.cancel()
            val startScale = zoomScale
            val startX = zoomTranslationX
            val startY = zoomTranslationY
            zoomAnimator = ValueAnimator.ofFloat(0f, 1f).apply {
                duration = 160L
                addUpdateListener { animator ->
                    val progress = animator.animatedValue as Float
                    zoomScale = startScale + (1f - startScale) * progress
                    zoomTranslationX = startX * (1f - progress)
                    zoomTranslationY = startY * (1f - progress)
                    applyZoomTransform()
                }
                addListener(object : android.animation.AnimatorListenerAdapter() {
                    override fun onAnimationEnd(animation: android.animation.Animator) {
                        zoomScale = 1f
                        zoomTranslationX = 0f
                        zoomTranslationY = 0f
                        playerView.resizeMode = AspectRatioFrameLayout.RESIZE_MODE_FIT
                        applyZoomTransform()
                        showFeedback("FIT", 900L)
                        zoomAnimator = null
                    }
                })
                start()
            }
        }

        private fun handleTap() {
            logPlayer("PLAYER_SINGLE_TAP requestId=" + requestId.ifEmpty { "-" })
            setControlsVisible(!controlsVisible)
        }

        private fun pointerCenterX(event: MotionEvent): Float =
            if (event.pointerCount >= 2) (event.getX(0) + event.getX(1)) * 0.5f else event.x

        private fun pointerCenterY(event: MotionEvent): Float =
            if (event.pointerCount >= 2) (event.getY(0) + event.getY(1)) * 0.5f else event.y

        private fun applyZoomTransform() {
            val video = playerView.videoSurfaceView ?: return

            if (video is TextureView) {
                val matrix = Matrix()
                if (video.width > 1 && video.height > 1 && width > 1 && height > 1) {
                    val maxTx = ((video.width * zoomScale) - width).coerceAtLeast(0f) * 0.5f
                    val maxTy = ((video.height * zoomScale) - height).coerceAtLeast(0f) * 0.5f
                    zoomTranslationX = zoomTranslationX.coerceIn(-maxTx, maxTx)
                    zoomTranslationY = zoomTranslationY.coerceIn(-maxTy, maxTy)
                    matrix.setScale(
                        zoomScale,
                        zoomScale,
                        video.width * 0.5f,
                        video.height * 0.5f,
                    )
                    matrix.postTranslate(zoomTranslationX, zoomTranslationY)
                } else {
                    // Until the TextureView has real dimensions, keep the
                    // surface at identity. Applying a scaled origin here can
                    // place the first frame off-center and look distorted.
                    matrix.reset()
                }
                video.isOpaque = false
                video.setTransform(matrix)
            } else {
                if (video.width <= 1 || video.height <= 1 || width <= 1 || height <= 1) {
                    video.post { applyZoomTransform() }
                    return
                }
                val maxTx = ((video.width * zoomScale) - width).coerceAtLeast(0f) * 0.5f
                val maxTy = ((video.height * zoomScale) - height).coerceAtLeast(0f) * 0.5f
                zoomTranslationX = zoomTranslationX.coerceIn(-maxTx, maxTx)
                zoomTranslationY = zoomTranslationY.coerceIn(-maxTy, maxTy)
                video.pivotX = video.width * 0.5f
                video.pivotY = video.height * 0.5f
                video.scaleX = zoomScale
                video.scaleY = zoomScale
                video.translationX = zoomTranslationX
                video.translationY = zoomTranslationY
            }
            video.invalidate()
        }


    }


    companion object {
        private const val TAG = "[REIFLIX][PLAYER]"
        private const val PROGRESS_INTERVAL_MS = 15_000L
        private const val CONTROL_TIMEOUT_MS = 3_500L
        private const val SEEK_PROGRESS_MAX = 1000
        private const val MIN_ZOOM = 1f
        private const val MAX_ZOOM = 4f
        private const val ZOOM_SNAP_THRESHOLD = 1.07f
        private const val MAX_RETRY_ATTEMPTS = 2
    }
}
