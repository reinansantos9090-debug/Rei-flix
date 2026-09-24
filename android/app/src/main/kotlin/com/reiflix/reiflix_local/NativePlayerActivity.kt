package com.reiflix.reiflix_local

import android.app.AlertDialog
import android.app.PictureInPictureParams
import android.content.Context
import android.content.Intent
import android.content.pm.ActivityInfo
import android.content.pm.PackageManager
import android.content.SharedPreferences
import android.content.res.Configuration
import android.graphics.Color
import android.graphics.Matrix
import android.graphics.Typeface
import android.media.AudioManager
import android.net.Uri
import android.os.Build
import java.util.Locale
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.Future
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.MediaStore
import android.view.GestureDetector
import android.view.Gravity
import android.view.MotionEvent
import android.view.VelocityTracker
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
import androidx.media3.common.AudioAttributes
import androidx.media3.common.Format
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.TrackSelectionParameters
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.analytics.AnalyticsListener
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
    private lateinit var lockButton: TextView
    private lateinit var gesturePreferences: SharedPreferences

    private var locked = false
    private var inPictureInPicture = false
    private var sessionState = SessionState.ACTIVE
    private var playerGeneration = 0L
    private var activePlayerListener: Player.Listener? = null
    private var errorPublishedForGeneration = false
    private var gestureSafeLeft = 0
    private var gestureSafeTop = 0
    private var gestureSafeRight = 0
    private var gestureSafeBottom = 0
    private var volumeGesturesEnabled = false
    private var brightnessGesturesEnabled = false
    private var doubleTapEnabled = false
    private var longPressEnabled = false
    private var windowBrightness = WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_NONE
    private var autoHideTimeoutMs = CONTROL_TIMEOUT_MS
    private var immersiveSetting = "always"
    private var pipEnabled = true
    private var preferredAudioLanguage = ""
    private var preferredSubtitleLanguage = ""
    private var subtitleMode = "auto"
    private var doubleTapSeekMs = 10_000L
    private var longPressSpeed = 2f
    private var maxVideoResolution = "auto"
    private var maxVideoFrameRate = 0
    private var maxAudioChannels = 0
    private var subtitleScale = 1f
    private var subtitleBottomPaddingPercent = 8
    private var subtitleEmbeddedStyle = true

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
    private var aspectModeLabel = "Ajustar"
    private var episodeChangePending = false
    private var retryCount = 0
    internal var firstFrameRenderedForTesting = false
        private set
    private var feedbackHideAt = 0L
    private var controlsRestoredFromState = false
    private var contentMimeType: String? = null
    private var mediaDisplayName: String? = null
    private var mediaSizeBytes: Long? = null
    private var decoderVideoName: String? = null
    private var decoderAudioName: String? = null
    private var videoFormatSummary: String? = null
    private var audioFormatSummary: String? = null
    private var subtitleFormatSummary: String? = null
    private var currentErrorCategory = PlayerMediaPolicy.ErrorCategory.UNKNOWN
    private var pendingPreparation: Future<*>? = null
    private val playbackWorker: ExecutorService = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "ReiFlix-PlayerIO").apply { isDaemon = true }
    }
    private var activeAnalyticsListener: AnalyticsListener? = null

    private val titleValue: String
        get() = intent.getStringExtra("title") ?: "Episódio"

    private val controlsHider = object : Runnable {
        override fun run() {
            if (controlsVisible && !errorVisible) {
                val elapsed = System.currentTimeMillis() - lastControlsInteraction
                if (autoHideTimeoutMs > 0L && elapsed >= autoHideTimeoutMs) {
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
        sessionState = SessionState.ACTIVE
        gesturePreferences = getSharedPreferences("reiflix_player_preferences", Context.MODE_PRIVATE)
        volumeGesturesEnabled = intent.getBooleanExtra("setting_gestures_volume",
            gesturePreferences.getBoolean(PREF_GESTURES_VOLUME, false))
        brightnessGesturesEnabled = intent.getBooleanExtra("setting_gestures_brightness",
            gesturePreferences.getBoolean(PREF_GESTURES_BRIGHTNESS, false))
        doubleTapEnabled = intent.getBooleanExtra("setting_gestures_double_tap",
            gesturePreferences.getBoolean(PREF_GESTURES_DOUBLE_TAP, false))
        longPressEnabled = intent.getBooleanExtra("setting_gestures_long_press",
            gesturePreferences.getBoolean(PREF_GESTURES_LONG_PRESS, false))
        immersiveSetting = intent.getStringExtra("setting_player_immersive") ?: "always"
        autoHideTimeoutMs = intent.getIntExtra("setting_player_auto_hide_seconds", 5)
            .coerceIn(0, 300) * 1000L
        pipEnabled = intent.getBooleanExtra("setting_player_pip", true)
        preferredAudioLanguage = intent.getStringExtra("setting_audio_preferred_language")?.trim().orEmpty()
        preferredSubtitleLanguage = intent.getStringExtra("setting_audio_preferred_subtitle_language")?.trim().orEmpty()
        subtitleMode = intent.getStringExtra("setting_audio_subtitles") ?: "auto"
        doubleTapSeekMs = intent.getLongExtra("setting_player_double_tap_seek_seconds", 10L)
            .coerceIn(1L, 120L) * 1000L
        longPressSpeed = intent.getFloatExtra("setting_player_long_press_speed", 2f)
            .coerceIn(1f, 3f)
        maxVideoResolution = intent.getStringExtra("setting_player_max_video_resolution") ?: "auto"
        maxVideoFrameRate = intent.getIntExtra("setting_player_max_video_frame_rate", 0).coerceAtLeast(0)
        maxAudioChannels = intent.getIntExtra("setting_player_max_audio_channels", 0).coerceAtLeast(0)
        subtitleScale = intent.getFloatExtra("setting_audio_subtitle_scale", 1f)
            .coerceIn(0.5f, 2f)
        subtitleBottomPaddingPercent = intent.getIntExtra("setting_audio_subtitle_bottom_padding", 8)
            .coerceIn(0, 50)
        subtitleEmbeddedStyle = intent.getBooleanExtra("setting_audio_subtitle_embedded_style", true)
        locked = savedInstanceState?.getBoolean("lock_mode", false)
            ?: gesturePreferences.getBoolean(PREF_LOCK_MODE, false)
        controlsVisible = savedInstanceState?.getBoolean("controls_visible", true) ?: true
        controlsRestoredFromState = savedInstanceState?.containsKey("controls_visible") == true
        logPlayer(
            "PLAYER_ACTIVITY_ON_CREATE requestId=" + requestId.ifEmpty { "-" } +
                " task=" + taskId +
                " intentAction=" + (intent.action ?: "-") +
                " component=" + (intent.component?.flattenToShortString() ?: "-"),
        )

        applyConfiguredRotation()
        if (shouldUseImmersive()) enterImmersiveMode() else restoreSystemUiBeforeExit()
        configureWindow()
        savedInstanceState?.getFloat("window_brightness", WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_NONE)
            ?.takeIf { it.isFinite() && it >= 0f && it <= 1f }
            ?.let { setWindowBrightness(it) }
        restoredPositionMs = savedInstanceState?.takeIf { it.containsKey("position_ms") }?.getLong("position_ms")
        aspectModeLabel = savedInstanceState?.getString("aspect_mode_label")
            ?: aspectLabelFromSetting(intent.getStringExtra("setting_player_aspect_ratio"))
        root = FrameLayout(this).apply {
            setBackgroundColor(Color.BLACK)
            clipChildren = false
            clipToPadding = false
        }
        setContentView(root)
        installBasePlayerView()
        installGestureLayer()
        installControls()
        setLocked(locked, persist = false, announce = false)
        if (controlsRestoredFromState && !locked) {
            setControlsVisible(controlsVisible)
        }
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
            logPlayer("MEDIA3_PLAYER_CREATE_START requestId=" + requestId.ifEmpty { "-" })
            player = ExoPlayer.Builder(this).build()
            player.setAudioAttributes(
                AudioAttributes.Builder()
                    .setContentType(C.AUDIO_CONTENT_TYPE_MOVIE)
                    .setUsage(C.USAGE_MEDIA)
                    .build(),
                true,
            )
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
            applyGlobalTrackPreferences()
            applyAdvancedTrackConstraints()
            applySubtitlePreferences()
            autoplayNext = savedInstanceState?.takeIf { it.containsKey("autoplay_next") }?.getBoolean("autoplay_next")
                ?: intent.getBooleanExtra("autoplay", true)

            val savedSpeed = savedInstanceState?.takeIf { it.containsKey("playback_speed") }
                ?.getFloat("playback_speed")
                ?: intent.getFloatExtra("setting_player_default_speed", 1f)
            if (savedSpeed > 0f && savedSpeed.isFinite()) {
                player.setPlaybackSpeed(savedSpeed)
            }

            val savedResize = savedInstanceState?.takeIf { it.containsKey("resize_mode") }
                ?.getInt("resize_mode", AspectRatioFrameLayout.RESIZE_MODE_FIT)
                ?: resizeModeFromSetting(intent.getStringExtra("setting_player_aspect_ratio"))
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
        sessionState = SessionState.ACTIVE
        episodeChangePending = false
        lastSavedPosition = -1L
        errorPublishedForGeneration = false
        restoredPositionMs = null
        initialSeekApplied = false
        completionReported = false
        openedReported = false
        exitReported = false
        suppressExitEvent = false
        errorVisible = false
        doubleTapSeekMs = newIntent.getLongExtra("setting_player_double_tap_seek_seconds", doubleTapSeekMs / 1000L)
            .coerceIn(1L, 120L) * 1000L
        longPressSpeed = newIntent.getFloatExtra("setting_player_long_press_speed", longPressSpeed)
            .coerceIn(1f, 3f)
        maxVideoResolution = newIntent.getStringExtra("setting_player_max_video_resolution") ?: maxVideoResolution
        maxVideoFrameRate = newIntent.getIntExtra("setting_player_max_video_frame_rate", maxVideoFrameRate).coerceAtLeast(0)
        maxAudioChannels = newIntent.getIntExtra("setting_player_max_audio_channels", maxAudioChannels).coerceAtLeast(0)
        subtitleScale = newIntent.getFloatExtra("setting_audio_subtitle_scale", subtitleScale).coerceIn(0.5f, 2f)
        subtitleBottomPaddingPercent = newIntent.getIntExtra("setting_audio_subtitle_bottom_padding", subtitleBottomPaddingPercent).coerceIn(0, 50)
        subtitleEmbeddedStyle = newIntent.getBooleanExtra("setting_audio_subtitle_embedded_style", subtitleEmbeddedStyle)
        preferredAudioLanguage = newIntent.getStringExtra("setting_audio_preferred_language")?.trim().orEmpty()
        preferredSubtitleLanguage = newIntent.getStringExtra("setting_audio_preferred_subtitle_language")?.trim().orEmpty()
        subtitleMode = newIntent.getStringExtra("setting_audio_subtitles") ?: subtitleMode
        applyGlobalTrackPreferences()
        applyAdvancedTrackConstraints()
        applySubtitlePreferences()
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

    private fun buildMediaItem(
        mediaUri: Uri,
        mimeType: String?,
        subtitleTracks: List<LocalSubtitleResolver.SubtitleTrack>,
    ): MediaItem {
        val mediaItemBuilder = MediaItem.Builder()
            .setUri(mediaUri)
            .setMediaId(mediaUri.toString())
        mimeType?.takeIf { it.startsWith("video/") }?.let { mediaItemBuilder.setMimeType(it) }
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

    private fun isCurrentPreparation(generation: Long, localUri: Uri): Boolean =
        generation == playerGeneration &&
            sessionState == SessionState.ACTIVE &&
            ::uri.isInitialized &&
            uri == localUri

    private fun prepareCurrentMedia(reason: String, playWhenReadyOverride: Boolean? = null) {
        if (!::player.isInitialized || sessionState == SessionState.DESTROYED) return
        beginPlayerGeneration(reason)
        val generation = playerGeneration
        val localUri = uri
        val shouldPlayWhenReady = playWhenReadyOverride
            ?: intent.getBooleanExtra("autoplay", true)

        initialSeekApplied = false
        completionReported = false
        firstFrameRenderedForTesting = false
        contentMimeType = null
        mediaDisplayName = null
        mediaSizeBytes = null
        decoderVideoName = null
        decoderAudioName = null
        videoFormatSummary = null
        audioFormatSummary = null
        currentErrorCategory = PlayerMediaPolicy.ErrorCategory.UNKNOWN
        pendingPreparation?.cancel(true)
        if (::preparingIndicator.isInitialized) preparingIndicator.visibility = View.VISIBLE
        logPlayer(
            "PREPARE_ASYNC_START generation=$generation requestId=" +
                requestId.ifEmpty { "-" } + " reason=" + reason,
        )

        pendingPreparation = playbackWorker.submit {
            try {
                val displayName = displayNameForUri(localUri)
                val providerMime = runCatching { contentResolver.getType(localUri) }.getOrNull()
                val resolvedMime = PlayerMediaPolicy.resolveVideoMimeType(providerMime, displayName)
                val sizeBytes = localSizeBytes(localUri)
                val subtitleTracks = runCatching {
                    LocalSubtitleResolver.resolve(this@NativePlayerActivity, localUri)
                }.getOrElse { error ->
                    logPlayer("SUBTITLE_RESOLVE_FAILED generation=$generation uri=$localUri", error)
                    emptyList()
                }

                handler.post {
                    if (!isCurrentPreparation(generation, localUri)) return@post

                    contentMimeType = resolvedMime
                    mediaDisplayName = displayName
                    mediaSizeBytes = sizeBytes
                    logPlayer(
                        "MIME_RESOLVED generation=$generation provider=" +
                            providerMime.orEmpty() + " resolved=" + resolvedMime.orEmpty() +
                            " displayName=" + displayName.orEmpty(),
                    )

                    if (sizeBytes == 0L) {
                        showPlayerError(
                            "Este arquivo está vazio e não contém dados de vídeo.",
                            "empty_file",
                            JSONObject().put("sizeBytes", 0),
                            PlayerMediaPolicy.ErrorCategory.SOURCE_UNAVAILABLE,
                        )
                        return@post
                    }

                    val mediaItem = buildMediaItem(localUri, resolvedMime, subtitleTracks)
                    logPlayer(
                        "MEDIA_ITEM requestId=" + requestId.ifEmpty { "-" } +
                            " uri=" + mediaItem.localConfiguration?.uri +
                            " mime=" + resolvedMime.orEmpty() +
                            " subtitleCount=" + subtitleTracks.size +
                            " reason=" + reason,
                    )
                    player.pause()
                    player.setMediaItem(mediaItem)
                    player.playWhenReady = shouldPlayWhenReady
                    logPlayer(
                        "PLAY_WHEN_READY=" + player.playWhenReady +
                            " requestId=" + requestId.ifEmpty { "-" } +
                            " generation=$generation reason=" + reason,
                    )
                    logPlayer(
                        "PREPARE requestId=" + requestId.ifEmpty { "-" } +
                            " generation=$generation reason=" + reason,
                    )
                    player.prepare()
                    logPlayer(
                        "MEDIA3_PREPARE_DISPATCHED requestId=" + requestId.ifEmpty { "-" } +
                            " generation=" + generation +
                            " mediaId=" + mediaItem.mediaId,
                    )
                    updateTrackButtons()
                    updatePlayPauseButton()
                    updateProgressUi()
                }
            } catch (cancelled: java.util.concurrent.CancellationException) {
                logPlayer("PREPARE_ASYNC_CANCELLED generation=$generation reason=$reason")
            } catch (error: Exception) {
                handler.post {
                    if (!isCurrentPreparation(generation, localUri)) return@post
                    logPlayer("PREPARE_ASYNC_FAILED generation=$generation reason=$reason", error)
                    val category = PlayerMediaPolicy.classifyError(
                        error::class.java.simpleName,
                        listOfNotNull(error.cause?.javaClass?.simpleName),
                    )
                    showPlayerError(
                        "Não foi possível preparar este arquivo local.",
                        "prepare_io",
                        JSONObject().put("error", error.message ?: error::class.java.simpleName),
                        category,
                    )
                }
            }
        }
    }

    private fun createPlayerListener(generation: Long): Player.Listener = object : Player.Listener {
        private fun isCurrent(): Boolean =
            generation == playerGeneration && sessionState == SessionState.ACTIVE
        override fun onEvents(player: Player, events: Player.Events) {
            if (!isCurrent()) return
            if (events.contains(Player.EVENT_RENDERED_FIRST_FRAME)) {
                firstFrameRenderedForTesting = true
                if (::preparingIndicator.isInitialized) preparingIndicator.visibility = View.GONE
                logPlayer("FIRST_FRAME_RENDERED requestId=" + requestId.ifEmpty { "-" } +
                    " positionMs=" + player.currentPosition)
            }
        }

        override fun onMediaItemTransition(mediaItem: MediaItem?, reason: Int) {
            if (!isCurrent()) return
            logPlayer(
                "MEDIA_ITEM_TRANSITION generation=$generation reason=$reason mediaId=" +
                    mediaItem?.mediaId.orEmpty(),
            )
        }

        override fun onPlaybackStateChanged(state: Int) {
            if (!isCurrent()) return
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

        override fun onPlaybackParametersChanged(playbackParameters: androidx.media3.common.PlaybackParameters) {
            if (!isCurrent()) return
            logPlayer(
                "PLAYBACK_SPEED_CHANGED generation=$generation speed=" +
                    playbackParameters.speed + " pitch=" + playbackParameters.pitch,
            )
        }

        override fun onIsPlayingChanged(isPlaying: Boolean) {
            if (!isCurrent()) return
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
            if (!isCurrent()) return
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
            if (!isCurrent()) return
            val videoGroups = tracks.groups.count { it.type == C.TRACK_TYPE_VIDEO && it.isSupported }
            val audioGroups = tracks.groups.count { it.type == C.TRACK_TYPE_AUDIO && it.isSupported }
            val textGroups = tracks.groups.count { it.type == C.TRACK_TYPE_TEXT && it.isSupported }
            logPlayer(
                "PLAYER_TRACK_CHANGE requestId=" + requestId.ifEmpty { "-" } +
                    " video=" + videoGroups + " audio=" + audioGroups + " text=" + textGroups,
            )
            if (audioGroups == 0) logPlayer("TRACKS_NO_AUDIO requestId=" + requestId.ifEmpty { "-" })
            if (textGroups == 0) logPlayer("TRACKS_NO_SUBTITLE requestId=" + requestId.ifEmpty { "-" })
            captureTrackFormatSummaries()
            updateTrackButtons()
        }

        override fun onPlayerError(error: PlaybackException) {
            if (!isCurrent()) return
            val code = error.errorCodeName.orEmpty()
            val technicalCode = "media3:" + code
            val detail = error.message?.trim().orEmpty()
            val category = PlayerMediaPolicy.classifyError(
                code,
                listOfNotNull(
                    error.cause?.javaClass?.simpleName,
                    error.cause?.cause?.javaClass?.simpleName,
                ),
            )
            currentErrorCategory = category
            logPlayer(
                "PlaybackException requestId=" + requestId.ifEmpty { "-" } +
                    " code=" + code + " detail=" + detail +
                    " cause=" + (error.cause?.javaClass?.simpleName ?: "-"),
                error,
            )
            saveProgress("player_progress", force = true)
            player.pause()
            showPlayerError(
                when (category) {
                    PlayerMediaPolicy.ErrorCategory.DECODER_UNSUPPORTED ->
                        "Este dispositivo não possui um decoder compatível com este vídeo."
                    PlayerMediaPolicy.ErrorCategory.SOURCE_UNAVAILABLE ->
                        "O arquivo deste episódio não está disponível para leitura."
                    else ->
                        "Não foi possível reproduzir este arquivo neste dispositivo."
                },
                technicalCode,
                diagnosticPayload()
                    .put("uri", uri.toString())
                    .put("errorCode", technicalCode)
                    .put("detail", detail)
                    .put("cause", error.cause?.javaClass?.simpleName ?: ""),
                category,
            )
        }
    }

    private fun createAnalyticsListener(generation: Long): AnalyticsListener =
        object : AnalyticsListener {
            private fun isCurrent(): Boolean =
                generation == playerGeneration && sessionState == SessionState.ACTIVE

            override fun onVideoDecoderInitialized(
                eventTime: AnalyticsListener.EventTime,
                decoderName: String,
                initializedTimestampMs: Long,
                initializationDurationMs: Long,
            ) {
                if (!isCurrent()) return
                decoderVideoName = decoderName
                logPlayer(
                    "VIDEO_DECODER_INITIALIZED generation=$generation decoder=$decoderName " +
                        "durationMs=$initializationDurationMs",
                )
            }

            override fun onAudioDecoderInitialized(
                eventTime: AnalyticsListener.EventTime,
                decoderName: String,
                initializedTimestampMs: Long,
                initializationDurationMs: Long,
            ) {
                if (!isCurrent()) return
                decoderAudioName = decoderName
                logPlayer(
                    "AUDIO_DECODER_INITIALIZED generation=$generation decoder=$decoderName " +
                        "durationMs=$initializationDurationMs",
                )
            }
        }

    private fun beginPlayerGeneration(reason: String) {
        if (!::player.isInitialized || sessionState == SessionState.DESTROYED) return
        activePlayerListener?.let { player.removeListener(it) }
        activeAnalyticsListener?.let { player.removeAnalyticsListener(it) }
        activePlayerListener = null
        activeAnalyticsListener = null
        pendingPreparation?.cancel(true)
        playerGeneration += 1L
        errorPublishedForGeneration = false
        openedReported = false
        lastSavedPosition = -1L
        val generation = playerGeneration
        activePlayerListener = createPlayerListener(generation)
        activeAnalyticsListener = createAnalyticsListener(generation)
        player.addListener(activePlayerListener!!)
        player.addAnalyticsListener(activeAnalyticsListener!!)
        logPlayer("PLAYER_GENERATION_START generation=$generation reason=$reason requestId=" + requestId.ifEmpty { "-" })
    }


    private fun applyGlobalTrackPreferences() {
        if (!::player.isInitialized) return
        val builder = player.trackSelectionParameters.buildUpon()
            .clearOverridesOfType(C.TRACK_TYPE_AUDIO)
            .clearOverridesOfType(C.TRACK_TYPE_TEXT)
            .setPreferredAudioLanguage(preferredAudioLanguage.takeIf { it.isNotBlank() })
        when (subtitleMode) {
            "never" -> builder
                .setPreferredTextLanguage(null)
                .setTrackTypeDisabled(C.TRACK_TYPE_TEXT, true)
            "always" -> builder
                .setTrackTypeDisabled(C.TRACK_TYPE_TEXT, false)
                .setPreferredTextLanguage(preferredSubtitleLanguage.takeIf { it.isNotBlank() })
                .setSelectUndeterminedTextLanguage(true)
            else -> builder
                .setTrackTypeDisabled(C.TRACK_TYPE_TEXT, false)
                .setPreferredTextLanguage(preferredSubtitleLanguage.takeIf { it.isNotBlank() })
        }
        player.trackSelectionParameters = builder.build()
        logPlayer(
            "GLOBAL_TRACK_PREFS audio=" + preferredAudioLanguage.ifBlank { "auto" } +
                " subtitle=" + preferredSubtitleLanguage.ifBlank { "auto" } +
                " mode=" + subtitleMode
        )
    }

    private fun applyAdvancedTrackConstraints() {
        if (!::player.isInitialized) return
        val builder = player.trackSelectionParameters.buildUpon()
        when (maxVideoResolution) {
            "480p" -> builder.setMaxVideoSize(854, 480)
            "720p" -> builder.setMaxVideoSize(1280, 720)
            "1080p" -> builder.setMaxVideoSize(1920, 1080)
            "1440p" -> builder.setMaxVideoSize(2560, 1440)
            "2160p" -> builder.setMaxVideoSize(3840, 2160)
            else -> builder.setMaxVideoSize(Int.MAX_VALUE, Int.MAX_VALUE)
        }
        builder.setMaxVideoFrameRate(
            if (maxVideoFrameRate > 0) maxVideoFrameRate else Int.MAX_VALUE,
        )
        builder.setMaxAudioChannelCount(
            if (maxAudioChannels > 0) maxAudioChannels else Int.MAX_VALUE,
        )
        player.trackSelectionParameters = builder.build()
        logPlayer(
            "ADVANCED_TRACK_CONSTRAINTS resolution=" + maxVideoResolution +
                " fps=" + maxVideoFrameRate +
                " audioChannels=" + maxAudioChannels,
        )
    }

    private fun applySubtitlePreferences() {
        if (!::playerView.isInitialized) return
        playerView.subtitleView?.apply {
            setFractionalTextSize((SubtitleViewFraction.DEFAULT * subtitleScale).coerceIn(0.02f, 0.12f))
            setBottomPaddingFraction((subtitleBottomPaddingPercent / 100f).coerceIn(0f, 0.5f))
            setApplyEmbeddedStyles(subtitleEmbeddedStyle)
            setApplyEmbeddedFontSizes(subtitleEmbeddedStyle)
            setUserDefaultStyle()
        }
        logPlayer(
            "SUBTITLE_PREFS scale=" + subtitleScale +
                " padding=" + subtitleBottomPaddingPercent +
                " embedded=" + subtitleEmbeddedStyle,
        )
    }

    private object SubtitleViewFraction {
        const val DEFAULT = 0.0533f
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
        return pipEnabled &&
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.O &&
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

        lockButton = actionButton(if (locked) "🔒" else "🔓", 48) {
            setLocked(!locked)
        }.apply {
            tag = "reiflix_lock_button"
            contentDescription = if (locked) "Desbloquear controles" else "Bloquear controles"
        }
        topBar.addView(lockButton, weightParams(48))

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
        root.addView(feedback, FrameLayout.LayoutParams(
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

        val previousButton = actionButton("−10", 70) { seekBy(-10_000L, "−10s") }.apply {
            contentDescription = "Voltar 10 segundos"
        }
        previousButton.tag = "reiflix_seek_back"
        centerControls.addView(previousButton, weightParams(70))

        playPauseButton = actionButton("▶", 84) { togglePlayPause() }.apply {
            contentDescription = "Reproduzir ou pausar"
            textSize = 26f
            tag = "reiflix_play_pause"
            minHeight = dp(72)
            minWidth = dp(72)
        }
        centerControls.addView(playPauseButton, weightParams(84))

        val nextButton = actionButton("+10", 70) { seekBy(10_000L, "+10s") }.apply {
            contentDescription = "Avançar 10 segundos"
        }
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

        val volumeGestureButton = actionButton(gestureSettingLabel("Volume", volumeGesturesEnabled), 120) { button ->
            volumeGesturesEnabled = !volumeGesturesEnabled
            gesturePreferences.edit().putBoolean(PREF_GESTURES_VOLUME, volumeGesturesEnabled).apply()
            button.text = gestureSettingLabel("Volume", volumeGesturesEnabled)
            showFeedback(if (volumeGesturesEnabled) "Gesto de volume ligado" else "Gesto de volume desligado")
            touchControls()
        }.apply {
            tag = "reiflix_gesture_volume"
            contentDescription = "Configurar gesto de volume"
        }
        val brightnessGestureButton = actionButton(gestureSettingLabel("Brilho", brightnessGesturesEnabled), 120) { button ->
            brightnessGesturesEnabled = !brightnessGesturesEnabled
            gesturePreferences.edit().putBoolean(PREF_GESTURES_BRIGHTNESS, brightnessGesturesEnabled).apply()
            button.text = gestureSettingLabel("Brilho", brightnessGesturesEnabled)
            showFeedback(if (brightnessGesturesEnabled) "Gesto de brilho ligado" else "Gesto de brilho desligado")
            touchControls()
        }.apply {
            tag = "reiflix_gesture_brightness"
            contentDescription = "Configurar gesto de brilho"
        }
        val doubleTapButton = actionButton(gestureSettingLabel("Double tap", doubleTapEnabled), 120) { button ->
            doubleTapEnabled = !doubleTapEnabled
            gesturePreferences.edit().putBoolean(PREF_GESTURES_DOUBLE_TAP, doubleTapEnabled).apply()
            button.text = gestureSettingLabel("Double tap", doubleTapEnabled)
            showFeedback(if (doubleTapEnabled) "Double tap ligado" else "Double tap desligado")
            touchControls()
        }.apply {
            tag = "reiflix_gesture_double_tap"
            contentDescription = "Configurar double tap"
        }
        val longPressButton = actionButton(gestureSettingLabel("Pressão", longPressEnabled), 120) { button ->
            longPressEnabled = !longPressEnabled
            gesturePreferences.edit().putBoolean(PREF_GESTURES_LONG_PRESS, longPressEnabled).apply()
            button.text = gestureSettingLabel("Pressão", longPressEnabled)
            showFeedback(if (longPressEnabled) "Pressão longa ligada" else "Pressão longa desligada")
            touchControls()
        }.apply {
            tag = "reiflix_gesture_long_press"
            contentDescription = "Configurar pressão longa"
        }
        addMoreRow(volumeGestureButton, brightnessGestureButton)
        addMoreRow(doubleTapButton, longPressButton)
        if (canEnterPictureInPicture()) {
            val pip = actionButton("PIP", 92) { enterPictureInPictureMode() }
            pip.contentDescription = "Picture in Picture"
            addMoreRow(pip)
        }
        addMoreRow(actionButton("Informações", 92) { showTechnicalInfo() }.apply {
            tag = "reiflix_technical_info"
            contentDescription = "Informações técnicas"
        })
        controls.addView(morePanel, FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.WRAP_CONTENT,
            FrameLayout.LayoutParams.WRAP_CONTENT,
        ).apply {
            gravity = Gravity.TOP or Gravity.END
            topMargin = dp(56)
            rightMargin = dp(8)
        })
        controls.bringToFront()
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
        val bars = insets.getInsetsIgnoringVisibility(WindowInsetsCompat.Type.systemBars())
        val cutout = insets.getInsetsIgnoringVisibility(WindowInsetsCompat.Type.displayCutout())
        val mandatoryGestures = insets.getInsetsIgnoringVisibility(
            WindowInsetsCompat.Type.mandatorySystemGestures(),
        )
        gestureSafeLeft = maxOf(bars.left, cutout.left, mandatoryGestures.left)
        gestureSafeTop = maxOf(bars.top, cutout.top, mandatoryGestures.top)
        gestureSafeRight = maxOf(bars.right, cutout.right, mandatoryGestures.right)
        gestureSafeBottom = maxOf(bars.bottom, cutout.bottom, mandatoryGestures.bottom)

        val topParams = topBar.layoutParams as? FrameLayout.LayoutParams
        if (topParams != null) {
            topParams.topMargin = max(dp(4), gestureSafeTop)
            topBar.layoutParams = topParams
        }
        val bottomParams = bottomBar.layoutParams as? FrameLayout.LayoutParams
        if (bottomParams != null) {
            bottomParams.bottomMargin = max(dp(4), gestureSafeBottom)
            bottomBar.layoutParams = bottomParams
        }
        controls.setPadding(
            max(dp(4), gestureSafeLeft),
            0,
            max(dp(4), gestureSafeRight),
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
        val labels = arrayOf("Ajustar", "Preencher")
        val current = when (button.text.toString()) {
            in labels -> button.text.toString()
            "Original", "Auto", "Zoom" -> "Ajustar"
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
            "Preencher" -> AspectRatioFrameLayout.RESIZE_MODE_ZOOM
            else -> AspectRatioFrameLayout.RESIZE_MODE_FIT
        }
        button.text = mode
        showFeedback(mode)
        touchControls()
        playerView.requestLayout()
    }

    private fun captureTrackFormatSummaries() {
        if (!::player.isInitialized) return
        var videoSummary: String? = null
        var audioSummary: String? = null
        for (group in player.currentTracks.groups) {
            for (index in 0 until group.length) {
                if (!group.isTrackSupported(index)) continue
                val format = group.getTrackFormat(index)
                val summary = formatSummary(format, group.isTrackSelected(index))
                when (format.sampleMimeType?.substringBefore('/').orEmpty()) {
                    "video" -> if (videoSummary == null || group.isTrackSelected(index)) videoSummary = summary
                    "audio" -> if (audioSummary == null || group.isTrackSelected(index)) audioSummary = summary
                }
            }
        }
        videoFormatSummary = videoSummary
        audioFormatSummary = audioSummary
        subtitleFormatSummary = player.currentTracks.groups
            .filter { it.type == C.TRACK_TYPE_TEXT && it.isSupported }
            .flatMap { group ->
                (0 until group.length)
                    .filter { group.isTrackSupported(it) && group.isTrackSelected(it) }
                    .map { group.getTrackFormat(it) }
            }
            .firstOrNull()
            ?.let { formatSummary(it, true) }
    }

    private fun formatSummary(format: Format, selected: Boolean): String {
        val codec = formatCodecLabel(format.sampleMimeType, format.codecs)
        val label = format.label?.takeIf { it.isNotBlank() }
        val language = format.language?.takeIf { it.isNotBlank() }
        val size = if (format.width > 0 && format.height > 0) {
            format.width.toString() + "x" + format.height
        } else null
        val frameRate = format.frameRate.takeIf { it > 0f }?.let {
            String.format(Locale.US, "%.3f fps", it)
        }
        val channels = format.channelCount.takeIf { it > 0 }?.let { it.toString() + " ch" }
        val sampleRate = format.sampleRate.takeIf { it > 0 }?.let { it.toString() + " Hz" }
        val bitrate = format.bitrate.takeIf { it > 0 }?.let { it.toString() + " bps" }
        return listOfNotNull(
            if (selected) "selected" else null,
            codec, label, language, size, frameRate, channels, sampleRate, bitrate,
        ).joinToString(" • ")
    }

    private fun formatCodecLabel(sampleMimeType: String?, codecs: String?): String {
        val mime = sampleMimeType.orEmpty().lowercase(Locale.ROOT)
        val codec = codecs?.takeIf { it.isNotBlank() }
        return when (mime) {
            "video/avc" -> "H.264" + if (codec != null) " (" + codec + ")" else ""
            "video/hevc" -> "HEVC" + if (codec != null) " (" + codec + ")" else ""
            "video/x-vnd.on2.vp9" -> "VP9" + if (codec != null) " (" + codec + ")" else ""
            "video/av01" -> "AV1" + if (codec != null) " (" + codec + ")" else ""
            "audio/mp4a-latm" -> "AAC" + if (codec != null) " (" + codec + ")" else ""
            "audio/opus" -> "Opus" + if (codec != null) " (" + codec + ")" else ""
            "audio/vorbis" -> "Vorbis" + if (codec != null) " (" + codec + ")" else ""
            "audio/ac3" -> "AC-3" + if (codec != null) " (" + codec + ")" else ""
            "audio/eac3" -> "E-AC-3" + if (codec != null) " (" + codec + ")" else ""
            "audio/flac" -> "FLAC" + if (codec != null) " (" + codec + ")" else ""
            else -> listOfNotNull(sampleMimeType, codec).joinToString(" / ").ifBlank { "desconhecido" }
        }
    }

    private fun diagnosticPayload(): JSONObject = JSONObject()
        .put("displayName", mediaDisplayName.orEmpty())
        .put("mimeType", contentMimeType.orEmpty())
        .put("sizeBytes", mediaSizeBytes ?: JSONObject.NULL)
        .put("decoderVideo", decoderVideoName.orEmpty())
        .put("decoderAudio", decoderAudioName.orEmpty())
        .put("video", videoFormatSummary.orEmpty())
        .put("audio", audioFormatSummary.orEmpty())
        .put("subtitleSelected", subtitleFormatSummary.orEmpty())
        .put("playbackSpeed", if (::player.isInitialized) player.playbackParameters.speed else 1f)
        .put("audioTrackCount", if (::player.isInitialized) player.currentTracks.groups.count { it.type == C.TRACK_TYPE_AUDIO && it.isSupported } else 0)
        .put("subtitleTrackCount", if (::player.isInitialized) player.currentTracks.groups.count { it.type == C.TRACK_TYPE_TEXT && it.isSupported } else 0)
        .put("durationMs", if (::player.isInitialized) player.duration.coerceAtLeast(0L) else 0L)

    private fun buildTechnicalInfo(): String {
        if (!::player.isInitialized) return "Player ainda não foi inicializado."
        captureTrackFormatSummaries()
        return buildString {
            append("Arquivo: ").append(mediaDisplayName ?: uri.lastPathSegment.orEmpty().ifBlank { "desconhecido" }).append('\n')
            append("MIME: ").append(contentMimeType ?: "não informado").append('\n')
            mediaSizeBytes?.let { append("Tamanho: ").append(it).append(" bytes").append('\n') }
            append("Duração: ").append(formatTime(player.duration.coerceAtLeast(0L))).append('\n')
            append("Velocidade: ").append(String.format(Locale.US, "%.2fx", player.playbackParameters.speed)).append('\n')
            append("Decodificador vídeo: ").append(decoderVideoName ?: "não informado").append('\n')
            append("Decodificador áudio: ").append(decoderAudioName ?: "não informado").append('\n')
            append("Vídeo: ").append(videoFormatSummary ?: "nenhuma faixa detectada").append('\n')
            append("Áudio: ").append(audioFormatSummary ?: "nenhuma faixa detectada").append('\n')
            append("Legenda selecionada: ").append(subtitleFormatSummary ?: "nenhuma").append('\n')
            append("Legendas disponíveis: ").append(player.currentTracks.groups.count { it.type == C.TRACK_TYPE_TEXT && it.isSupported })
        }
    }

    private fun showTechnicalInfo() {
        if (!::player.isInitialized) return
        touchControls()
        AlertDialog.Builder(this)
            .setTitle("Informações técnicas")
            .setMessage(buildTechnicalInfo())
            .setPositiveButton("Fechar", null)
            .show()
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
        if (inPictureInPicture) {
            handler.removeCallbacks(controlsHider)
            moreVisible = false
            findViewByTag<View>("reiflix_more_panel")?.visibility = View.GONE
            controls.visibility = View.INVISIBLE
            topBar.visibility = View.GONE
            centerControls.visibility = View.GONE
            bottomBar.visibility = View.GONE
            return
        }
        if (locked) {
            controls.visibility = View.VISIBLE
            topBar.visibility = View.VISIBLE
            bottomBar.visibility = View.GONE
            centerControls.visibility = View.GONE
            findViewByTag<View>("reiflix_more_panel")?.visibility = View.GONE
            findViewByTag<View>("reiflix_back_button")?.visibility = View.GONE
            findViewByTag<View>("reiflix_more_button")?.visibility = View.GONE
            return
        }

        controls.visibility = if (visible || errorVisible) View.VISIBLE else View.INVISIBLE
        topBar.visibility = if (visible || errorVisible) View.VISIBLE else View.GONE
        bottomBar.visibility = if (visible || errorVisible) View.VISIBLE else View.GONE
        centerControls.visibility = if (visible || errorVisible) View.VISIBLE else View.GONE
        findViewByTag<View>("reiflix_back_button")?.visibility = View.VISIBLE
        findViewByTag<View>("reiflix_more_button")?.visibility = View.VISIBLE
        if (visible) {
            touchControls()
        } else {
            moreVisible = false
            findViewByTag<View>("reiflix_more_panel")?.visibility = View.GONE
        }
    }

    private fun touchControls() {
        if (locked) {
            handler.removeCallbacks(controlsHider)
            setControlsVisible(true)
            return
        }
        controlsVisible = true
        controls.visibility = View.VISIBLE
        topBar.visibility = View.VISIBLE
        bottomBar.visibility = View.VISIBLE
        centerControls.visibility = View.VISIBLE
        lastControlsInteraction = System.currentTimeMillis()
        handler.removeCallbacks(controlsHider)
        if (::player.isInitialized && player.isPlaying && !errorVisible) {
            if (autoHideTimeoutMs > 0L) handler.postDelayed(controlsHider, autoHideTimeoutMs)
        }
    }

    private fun scheduleControlsHide() {
        if (!locked) touchControls()
    }

    private fun setLocked(value: Boolean, persist: Boolean = true, announce: Boolean = true) {
        locked = value
        if (persist) {
            gesturePreferences.edit().putBoolean(PREF_LOCK_MODE, locked).apply()
        }
        findViewByTag<View>("reiflix_gesture_layer")?.let {
            (it as? GestureLayer)?.cancelInteractions()
        }
        if (locked) {
            handler.removeCallbacks(controlsHider)
            moreVisible = false
            findViewByTag<View>("reiflix_more_panel")?.visibility = View.GONE
            findViewByTag<View>("reiflix_back_button")?.visibility = View.GONE
            findViewByTag<View>("reiflix_more_button")?.visibility = View.GONE
            controls.visibility = View.VISIBLE
            topBar.visibility = View.VISIBLE
            centerControls.visibility = View.GONE
            bottomBar.visibility = View.GONE
            if (::feedback.isInitialized) feedback.visibility = View.GONE
        } else {
            findViewByTag<View>("reiflix_back_button")?.visibility = View.VISIBLE
            findViewByTag<View>("reiflix_more_button")?.visibility = View.VISIBLE
            setControlsVisible(true)
        }
        updateLockUi()
        if (announce) showFeedback(if (locked) "Player bloqueado" else "Player desbloqueado")
    }

    private fun updateLockUi() {
        if (!::lockButton.isInitialized) return
        lockButton.text = if (locked) "🔒" else "🔓"
        lockButton.contentDescription = if (locked) "Desbloquear controles" else "Bloquear controles"
    }

    private fun gestureSettingLabel(label: String, enabled: Boolean): String =
        label + " " + if (enabled) "ON" else "OFF"

    private fun setWindowBrightness(value: Float) {
        val safe = value.coerceIn(0f, 1f)
        val attrs = window.attributes
        attrs.screenBrightness = safe
        window.attributes = attrs
        windowBrightness = safe
    }

    private fun adjustBrightness(delta: Float) {
        runCatching {
            var current = window.attributes.screenBrightness
            if (!current.isFinite() || current == WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_NONE) {
                current = 0.5f
            }
            setWindowBrightness((current + delta).coerceIn(0f, 1f))
            val percent = (windowBrightness * 100f).roundToInt().coerceIn(0, 100)
            showFeedback("Brilho $percent%", 900L)
        }.onFailure { error ->
            logPlayer("GESTURE_BRIGHTNESS_IGNORED", error)
        }
    }

    private fun adjustVolumeByFraction(deltaFraction: Float) {
        runCatching {
            val audio = getSystemService(Context.AUDIO_SERVICE) as AudioManager
            val maxVolume = audio.getStreamMaxVolume(AudioManager.STREAM_MUSIC)
            val currentVolume = audio.getStreamVolume(AudioManager.STREAM_MUSIC)
            if (maxVolume <= 0) return@runCatching
            val deltaSteps = max(
                1,
                (maxVolume * abs(deltaFraction)).roundToInt(),
            )
            val target = if (deltaFraction >= 0f) {
                (currentVolume + deltaSteps).coerceAtMost(maxVolume)
            } else {
                (currentVolume - deltaSteps).coerceAtLeast(0)
            }
            audio.setStreamVolume(AudioManager.STREAM_MUSIC, target, 0)
            val percent = (target.toFloat() / maxVolume.toFloat() * 100f).roundToInt()
            showFeedback("Volume $percent%", 900L)
        }.onFailure { error ->
            logPlayer("GESTURE_VOLUME_IGNORED", error)
        }
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
        category: PlayerMediaPolicy.ErrorCategory = PlayerMediaPolicy.ErrorCategory.UNKNOWN,
    ) {
        currentErrorCategory = category
        setLocked(false, persist = true, announce = false)
        errorVisible = true
        if (::preparingIndicator.isInitialized) preparingIndicator.visibility = View.GONE
        if (::player.isInitialized) player.pause()
        setControlsVisible(true)
        findViewByTag<View>("reiflix_error_text")?.let { (it as TextView).text = message }
        findViewByTag<View>("reiflix_error_reason")?.let { (it as TextView).text = "Detalhe: " + reason }
        findViewByTag<View>("reiflix_error_retry")?.visibility =
            if (::player.isInitialized && PlayerMediaPolicy.isRetryable(category)) View.VISIBLE else View.GONE
        findViewByTag<View>("reiflix_error_panel")?.visibility = View.VISIBLE
        findViewByTag<View>("reiflix_error_back")?.requestFocus()
        if (::feedback.isInitialized) feedback.visibility = View.GONE
        val effectivePayload = diagnosticPayload()
        val supplied = JSONObject(payload.toString())
        val keys = supplied.keys()
        while (keys.hasNext()) {
            val key = keys.next()
            effectivePayload.put(key, supplied.opt(key))
        }
        effectivePayload
            .put("uri", if (::uri.isInitialized) uri.toString() else intent.getStringExtra("uri").orEmpty())
            .put("reason", reason)
            .put("category", category.name)
        publishPlayerError(message, effectivePayload)
    }

    private fun publishPlayerError(message: String, payload: JSONObject = JSONObject()) {
        if (errorPublishedForGeneration) return
        errorPublishedForGeneration = true
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
        if (sessionState == SessionState.DESTROYED || exitReported) return
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
        if (sessionState == SessionState.DESTROYED) return
        sessionState = SessionState.EXITING
        findViewByTag<GestureLayer>("reiflix_gesture_layer")?.cancelInteractions()
        handler.removeCallbacks(controlsHider)
        handler.removeCallbacks(feedbackHider)
        restoreSystemUiBeforeExit()
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
        val safePosition = PlayerMediaPolicy.safeResumePosition(savedPositionMs, player.duration)
        if (safePosition > 0L && player.duration > 0L) {
            player.seekTo(safePosition)
            logPlayer(
                "RESUME_APPLIED positionMs=" + safePosition +
                    " durationMs=" + player.duration +
                    " requestId=" + requestId.ifEmpty { "-" },
            )
        } else if (savedPositionMs > 0L) {
            logPlayer(
                "RESUME_CLAMPED requestedMs=" + savedPositionMs +
                    " durationMs=" + player.duration +
                    " requestId=" + requestId.ifEmpty { "-" },
            )
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
        if (!inPictureInPicture && shouldUseImmersive()) enterImmersiveMode()
    }

    override fun onResume() {
        super.onResume()
        logPlayer("onResume requestId=" + requestId.ifEmpty { "-" })
        if (!inPictureInPicture && shouldUseImmersive()) enterImmersiveMode()
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
        if (hasFocus && !inPictureInPicture && shouldUseImmersive()) {
            window.decorView.post { enterImmersiveMode() }
        }
    }

    override fun onPictureInPictureModeChanged(isInPictureInPictureMode: Boolean, newConfig: Configuration) {
        super.onPictureInPictureModeChanged(isInPictureInPictureMode, newConfig)
        logPlayer("PLAYER_PIP inPip=" + isInPictureInPictureMode + " requestId=" + requestId.ifEmpty { "-" })
        inPictureInPicture = isInPictureInPictureMode
        if (isInPictureInPictureMode) {
            handler.removeCallbacks(controlsHider)
            findViewByTag<GestureLayer>("reiflix_gesture_layer")?.cancelInteractions()
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
        outState.putLong("player_generation", playerGeneration)
        if (::player.isInitialized) {
            outState.putString("session_request_id", requestId)
            outState.putString("session_uri", if (::uri.isInitialized) uri.toString() else intent.getStringExtra("uri").orEmpty())
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
        outState.putBoolean("lock_mode", locked)
        outState.putBoolean("controls_visible", controlsVisible)
        outState.putFloat("window_brightness", window.attributes.screenBrightness)
        outState.putString("aspect_mode_label", findViewByTag<TextView>("reiflix_aspect_button")?.text?.toString() ?: "Ajustar")
        super.onSaveInstanceState(outState)
    }

    override fun onDestroy() {
        findViewByTag<GestureLayer>("reiflix_gesture_layer")?.resetZoomToFit()
        findViewByTag<GestureLayer>("reiflix_gesture_layer")?.dispose()
        handler.removeCallbacks(progressReporter)
        handler.removeCallbacks(controlsHider)
        handler.removeCallbacks(feedbackHider)
        restoreSystemUiBeforeExit()
        pendingPreparation?.cancel(true)
        playbackWorker.shutdownNow()
        if (::player.isInitialized) {
            if (isFinishing && !suppressExitEvent && !exitReported && !isChangingConfigurations) {
                reportPlayerExit("activity_finish")
            }
            activePlayerListener?.let { player.removeListener(it) }
            activeAnalyticsListener?.let { player.removeAnalyticsListener(it) }
            activePlayerListener = null
            activeAnalyticsListener = null
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
        sessionState = SessionState.DESTROYED
        super.onDestroy()
    }

    private fun shouldUseImmersive(): Boolean =
        when (immersiveSetting) {
            "never" -> false
            "landscape" -> resources.configuration.orientation == android.content.res.Configuration.ORIENTATION_LANDSCAPE
            else -> true
        }

    private fun applyConfiguredRotation() {
        requestedOrientation = when (intent.getStringExtra("setting_player_rotation") ?: "auto") {
            "portrait" -> ActivityInfo.SCREEN_ORIENTATION_PORTRAIT
            "landscape" -> ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE
            else -> ActivityInfo.SCREEN_ORIENTATION_FULL_SENSOR
        }
    }

    private fun aspectLabelFromSetting(value: String?): String =
        if (value == "fill") "Preencher" else "Ajustar"

    private fun resizeModeFromSetting(value: String?): Int = when (value) {
        "fill" -> AspectRatioFrameLayout.RESIZE_MODE_ZOOM
        else -> AspectRatioFrameLayout.RESIZE_MODE_FIT
    }

    private fun enterImmersiveMode() {
        // Android 15/16 enforce edge-to-edge for target 35+; fullscreen is
        // therefore controlled by WindowInsetsControllerCompat hiding system bars.
        // Keep the decor-fit call only for pre-35 compatibility.
        if (Build.VERSION.SDK_INT < 35) {
            WindowCompat.setDecorFitsSystemWindows(window, false)
        }
        WindowInsetsControllerCompat(window, window.decorView).apply {
            isAppearanceLightStatusBars = false
            isAppearanceLightNavigationBars = false
            systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            hide(WindowInsetsCompat.Type.systemBars())
        }
        ViewCompat.requestApplyInsets(window.decorView)
        logPlayer("PLAYER_IMMERSIVE applied requestId=" + requestId.ifEmpty { "-" })
    }

    private fun restoreSystemUiBeforeExit() {
        runCatching {
            // Do not reveal the Android bars during the hand-off back to MainActivity.
            // MainActivity owns the app-level edge-to-edge policy and will re-apply it
            // in onResume. Keeping this transition hidden avoids a visible bar flash.
            WindowCompat.setDecorFitsSystemWindows(window, false)
            WindowInsetsControllerCompat(window, window.decorView).apply {
                isAppearanceLightStatusBars = false
                isAppearanceLightNavigationBars = false
                systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
                hide(WindowInsetsCompat.Type.systemBars())
            }
            ViewCompat.requestApplyInsets(window.decorView)
            logPlayer("PLAYER_IMMERSIVE kept_hidden_for_exit requestId=" + requestId.ifEmpty { "-" })
        }.onFailure { error ->
            logPlayer("PLAYER_IMMERSIVE_EXIT_POLICY_FAILED", error)
        }
    }

    private fun applyImmersiveAfterLayout() {
        window.decorView.post {
            if (shouldUseImmersive()) enterImmersiveMode() else restoreSystemUiBeforeExit()
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
            contentDescription = label
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

    private fun displayNameForUri(localUri: Uri): String? =
        when (localUri.scheme?.lowercase(Locale.ROOT)) {
            "file" -> runCatching { File(localUri.path ?: "").name }.getOrNull()
            "content" -> runCatching {
                contentResolver.query(
                    localUri,
                    arrayOf(MediaStore.MediaColumns.DISPLAY_NAME),
                    null, null, null,
                )?.use { cursor ->
                    if (!cursor.moveToFirst()) return@use null
                    val index = cursor.getColumnIndex(MediaStore.MediaColumns.DISPLAY_NAME)
                    if (index >= 0) cursor.getString(index) else null
                }
            }.getOrNull()
            else -> null
        } ?: localUri.lastPathSegment?.substringAfterLast('/')

    private fun localSizeBytes(localUri: Uri): Long? =
        when (localUri.scheme?.lowercase(Locale.ROOT)) {
            "file" -> runCatching { File(localUri.path ?: "").length() }.getOrNull()
            "content" -> {
                val descriptorSize = runCatching {
                    contentResolver.openFileDescriptor(localUri, "r")?.use { descriptor ->
                        descriptor.statSize.takeIf { it >= 0L }
                    }
                }.getOrNull()
                descriptorSize ?: runCatching {
                    contentResolver.query(
                        localUri,
                        arrayOf(MediaStore.MediaColumns.SIZE),
                        null, null, null,
                    )?.use { cursor ->
                        if (!cursor.moveToFirst()) return@use null
                        val index = cursor.getColumnIndex(MediaStore.MediaColumns.SIZE)
                        if (index >= 0 && !cursor.isNull(index)) cursor.getLong(index) else null
                    }
                }.getOrNull()
            }
            else -> null
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
        private val touchConfig = ViewConfiguration.get(context)
        private val touchSlop = touchConfig.scaledTouchSlop.toFloat()
        private val minFlingVelocity = touchConfig.scaledMinimumFlingVelocity.toFloat()
        private val scaleDetector = ScaleGestureDetector(
            context,
            object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
                override fun onScaleBegin(detector: ScaleGestureDetector): Boolean {
                    if (!gestureInteractionAllowed() || !::playerView.isInitialized || !::player.isInitialized) {
                        return false
                    }
                    pinchActive = true
                    gestureConsumed = true
                    cancelGestureDetector()
                    lastPanX = detector.focusX
                    lastPanY = detector.focusY
                    logPlayer("GESTURE_START type=pinch requestId=" + requestId.ifEmpty { "-" })
                    touchControls()
                    return true
                }

                override fun onScale(detector: ScaleGestureDetector): Boolean {
                    if (!pinchActive || !gestureInteractionAllowed()) return true
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

        private val gestureDetector = GestureDetector(
            context,
            object : GestureDetector.SimpleOnGestureListener() {
                override fun onDown(event: MotionEvent): Boolean = true

                override fun onSingleTapConfirmed(event: MotionEvent): Boolean {
                    if (!gestureInteractionAllowed() || gestureConsumed || systemGestureEdge) return true
                    handleTap()
                    return true
                }

                override fun onDoubleTap(event: MotionEvent): Boolean {
                    if (!gestureInteractionAllowed() || !doubleTapEnabled || gestureConsumed || systemGestureEdge) {
                        return true
                    }
                    gestureConsumed = true
                    val side = PlayerGesturePolicy.side(event.x, width)
                    when (side) {
                        PlayerGesturePolicy.Side.LEFT -> {
                            logPlayer("PLAYER_DOUBLE_TAP side=left requestId=" + requestId.ifEmpty { "-" })
                            seekBy(-doubleTapSeekMs, "−" + (doubleTapSeekMs / 1000L) + "s")
                        }
                        PlayerGesturePolicy.Side.RIGHT -> {
                            logPlayer("PLAYER_DOUBLE_TAP side=right requestId=" + requestId.ifEmpty { "-" })
                            seekBy(doubleTapSeekMs, "+" + (doubleTapSeekMs / 1000L) + "s")
                        }
                        PlayerGesturePolicy.Side.CENTER -> showFeedback("Double tap ignorado", 500L)
                    }
                    return true
                }

                override fun onLongPress(event: MotionEvent) {
                    if (!gestureInteractionAllowed() || !longPressEnabled || gestureConsumed || systemGestureEdge) return
                    previousSpeedForLongPress = player.playbackParameters.speed
                    longPressActive = true
                    player.setPlaybackSpeed(longPressSpeed)
                    val speedLabel = String.format(java.util.Locale.US, "%.2fx", longPressSpeed)
                    showFeedback(speedLabel, 8_000L)
                    logPlayer("PLAYER_LONG_PRESS speed=" + speedLabel + " requestId=" + requestId.ifEmpty { "-" })
                }
            },
        )

        private var downX = 0f
        private var downY = 0f
        private var gestureConsumed = false
        private var verticalGesture = false
        private var horizontalGesture = false
        private var systemGestureEdge = false
        private var pinchActive = false
        private var lastPanX: Float? = null
        private var lastPanY: Float? = null
        private var zoomScale = 1f
        private var zoomTranslationX = 0f
        private var zoomTranslationY = 0f
        private var zoomAnimator: ValueAnimator? = null
        private var velocityTracker: VelocityTracker? = null
        private var longPressActive = false
        private var previousSpeedForLongPress = 1f
        private var lastTapUpTime = 0L
        private var lastTapX = 0f
        private var lastTapY = 0f
        private var manualDoubleTap = false

        override fun onTouchEvent(event: MotionEvent): Boolean {
            if (inPictureInPicture) return true
            scaleDetector.onTouchEvent(event)

            if (pinchActive || event.pointerCount > 1) {
                when (event.actionMasked) {
                    MotionEvent.ACTION_POINTER_DOWN -> {
                        gestureConsumed = true
                        cancelGestureDetector(event)
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
                finishTouchVelocity(event)
                return true
            }

            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    downX = event.x
                    downY = event.y
                    gestureConsumed = false
                    verticalGesture = false
                    horizontalGesture = false
                    manualDoubleTap = false
                    systemGestureEdge = isSystemGestureEdge(event.x, event.y)
                    velocityTracker?.recycle()
                    velocityTracker = VelocityTracker.obtain().apply { addMovement(event) }

                    val doubleTapDistance = max(touchSlop * 2f, dp(24).toFloat())
                    val withinDoubleTapWindow =
                        doubleTapEnabled &&
                            lastTapUpTime > 0L &&
                            event.eventTime - lastTapUpTime <= ViewConfiguration.getDoubleTapTimeout()
                    val nearPreviousTap =
                        abs(event.x - lastTapX) <= doubleTapDistance &&
                            abs(event.y - lastTapY) <= doubleTapDistance

                    if (withinDoubleTapWindow && nearPreviousTap && !systemGestureEdge && gestureInteractionAllowed()) {
                        manualDoubleTap = true
                        gestureConsumed = true
                        cancelGestureDetector(event)
                    } else if (systemGestureEdge || !gestureInteractionAllowed()) {
                        gestureConsumed = true
                        cancelGestureDetector(event)
                    } else {
                        gestureDetector.onTouchEvent(event)
                    }
                }
                MotionEvent.ACTION_MOVE -> {
                    velocityTracker?.addMovement(event)
                    if (gestureConsumed || systemGestureEdge) return true
                    val dx = event.x - downX
                    val dy = event.y - downY
                    when (PlayerGesturePolicy.direction(dx, dy, touchSlop)) {
                        PlayerGesturePolicy.Direction.VERTICAL -> {
                            if (!verticalGesture) {
                                verticalGesture = true
                                gestureConsumed = true
                                cancelGestureDetector(event)
                                logPlayer("GESTURE_START type=vertical side=" +
                                    PlayerGesturePolicy.side(downX, width).name.lowercase() +
                                    " requestId=" + requestId.ifEmpty { "-" })
                            }
                        }
                        PlayerGesturePolicy.Direction.HORIZONTAL -> {
                            if (!horizontalGesture) {
                                horizontalGesture = true
                                gestureConsumed = true
                                cancelGestureDetector(event)
                                logPlayer("GESTURE_START type=horizontal_ignored requestId=" + requestId.ifEmpty { "-" })
                            }
                        }
                        PlayerGesturePolicy.Direction.NONE -> Unit
                    }
                }
                MotionEvent.ACTION_UP -> {
                    velocityTracker?.addMovement(event)
                    if (manualDoubleTap && gestureInteractionAllowed()) {
                        val side = PlayerGesturePolicy.side(event.x, width)
                        when (side) {
                            PlayerGesturePolicy.Side.LEFT -> {
                                logPlayer("PLAYER_DOUBLE_TAP side=left requestId=" + requestId.ifEmpty { "-" })
                                seekBy(-doubleTapSeekMs, "−" + (doubleTapSeekMs / 1000L) + "s")
                            }
                            PlayerGesturePolicy.Side.RIGHT -> {
                                logPlayer("PLAYER_DOUBLE_TAP side=right requestId=" + requestId.ifEmpty { "-" })
                                seekBy(doubleTapSeekMs, "+" + (doubleTapSeekMs / 1000L) + "s")
                            }
                            PlayerGesturePolicy.Side.CENTER -> showFeedback("Double tap ignorado", 500L)
                        }
                        lastTapUpTime = 0L
                        manualDoubleTap = false
                        restoreLongPressSpeed()
                        finishTouchVelocity(event)
                        return true
                    }

                    if (verticalGesture && gestureInteractionAllowed()) {
                        val velocityY = velocityTracker?.run {
                            computeCurrentVelocity(1000)
                            yVelocity
                        } ?: 0f
                        val dy = event.y - downY
                        val distanceRatio = (abs(dy) / height.coerceAtLeast(1).toFloat()).coerceIn(0f, 0.75f)
                        val strongEnough = abs(dy) >= max(touchSlop * 2f, dp(48).toFloat()) ||
                            abs(velocityY) >= minFlingVelocity * 0.5f
                        if (strongEnough) {
                            handleVerticalGesture(downX, dy, distanceRatio)
                        }
                        logPlayer("GESTURE_END type=vertical_ignored_or_applied requestId=" + requestId.ifEmpty { "-" })
                    } else if (horizontalGesture) {
                        logPlayer("GESTURE_END type=horizontal_ignored requestId=" + requestId.ifEmpty { "-" })
                    }
                    restoreLongPressSpeed()
                    if (!gestureConsumed && gestureInteractionAllowed() && !systemGestureEdge) {
                        lastTapUpTime = event.eventTime
                        lastTapX = event.x
                        lastTapY = event.y
                    }
                    gestureDetector.onTouchEvent(event)
                    finishTouchVelocity(event)
                }
                MotionEvent.ACTION_CANCEL -> {
                    restoreLongPressSpeed()
                    cancelGestureDetector(event)
                    finishTouchVelocity(event)
                    logPlayer("GESTURE_END type=cancel requestId=" + requestId.ifEmpty { "-" })
                    gestureConsumed = true
                    verticalGesture = false
                    horizontalGesture = false
                    systemGestureEdge = false
                }
            }
            return true
        }

        private fun gestureInteractionAllowed(): Boolean =
            !locked && !inPictureInPicture && !errorVisible && ::player.isInitialized

        private fun isSystemGestureEdge(x: Float, y: Float): Boolean =
            x < gestureSafeLeft ||
                x > width - gestureSafeRight ||
                y < gestureSafeTop ||
                y > height - gestureSafeBottom

        private fun handleVerticalGesture(startX: Float, dy: Float, distanceRatio: Float) {
            val side = PlayerGesturePolicy.side(startX, width)
            val directionUp = dy < 0f
            val fraction = max(0.06f, distanceRatio * 0.6f)
            when (side) {
                PlayerGesturePolicy.Side.LEFT -> {
                    if (brightnessGesturesEnabled) {
                        adjustBrightness(if (directionUp) fraction else -fraction)
                    } else {
                        // Disabled gestures are deliberately silent. Do not surface
                        // a toast/overlay/snackbar for an opt-out preference.
                    }
                }
                PlayerGesturePolicy.Side.RIGHT -> {
                    if (volumeGesturesEnabled) {
                        adjustVolumeByFraction(if (directionUp) fraction else -fraction)
                    } else {
                        // Disabled gestures are deliberately silent.
                    }
                }
                PlayerGesturePolicy.Side.CENTER -> {
                    // A vertical swipe in the center has no player action.
                }
            }
        }

        private fun cancelGestureDetector(event: MotionEvent? = null) {
            val cancel = if (event != null) {
                MotionEvent.obtain(event).apply { action = MotionEvent.ACTION_CANCEL }
            } else {
                val now = android.os.SystemClock.uptimeMillis()
                MotionEvent.obtain(now, now, MotionEvent.ACTION_CANCEL, 0f, 0f, 0)
            }
            gestureDetector.onTouchEvent(cancel)
            cancel.recycle()
        }

        private fun finishTouchVelocity(event: MotionEvent) {
            if (event.actionMasked == MotionEvent.ACTION_UP || event.actionMasked == MotionEvent.ACTION_CANCEL) {
                velocityTracker?.recycle()
                velocityTracker = null
            }
        }

        private fun restoreLongPressSpeed() {
            if (!longPressActive || !::player.isInitialized) return
            val restore = previousSpeedForLongPress.takeIf { it > 0f && it.isFinite() } ?: 1f
            player.setPlaybackSpeed(restore)
            longPressActive = false
            showFeedback(
                String.format(java.util.Locale.US, "%.2fx", restore),
                500L,
            )
            logPlayer("PLAYER_LONG_PRESS_END speed=" + restore + " requestId=" + requestId.ifEmpty { "-" })
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

        fun cancelInteractions() {
            gestureConsumed = true
            verticalGesture = false
            horizontalGesture = false
            systemGestureEdge = false
            restoreLongPressSpeed()
            velocityTracker?.recycle()
            velocityTracker = null
            cancelGestureDetector()
            lastPanX = null
            lastPanY = null
            pinchActive = false
        }

        fun dispose() {
            zoomAnimator?.cancel()
            zoomAnimator = null
            cancelInteractions()
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
            gestureConsumed = true
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

    internal object PlayerGesturePolicy {
        enum class Direction { NONE, HORIZONTAL, VERTICAL }
        enum class Side { LEFT, CENTER, RIGHT }

        fun direction(dx: Float, dy: Float, touchSlop: Float, dominance: Float = 1.15f): Direction {
            val ax = abs(dx)
            val ay = abs(dy)
            if (max(ax, ay) < touchSlop) return Direction.NONE
            return when {
                ax > ay * dominance -> Direction.HORIZONTAL
                ay > ax * dominance -> Direction.VERTICAL
                else -> Direction.NONE
            }
        }

        fun side(x: Float, width: Int): Side {
            if (width <= 0) return Side.CENTER
            val fraction = (x / width.toFloat()).coerceIn(0f, 1f)
            return when {
                fraction < 0.40f -> Side.LEFT
                fraction > 0.60f -> Side.RIGHT
                else -> Side.CENTER
            }
        }
    }



    private enum class SessionState { ACTIVE, EXITING, DESTROYED }

    companion object {
        private const val PREF_GESTURES_VOLUME = "gesture_volume"
        private const val PREF_GESTURES_BRIGHTNESS = "gesture_brightness"
        private const val PREF_GESTURES_DOUBLE_TAP = "gesture_double_tap"
        private const val PREF_GESTURES_LONG_PRESS = "gesture_long_press"
        private const val PREF_LOCK_MODE = "player_lock_mode"
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
