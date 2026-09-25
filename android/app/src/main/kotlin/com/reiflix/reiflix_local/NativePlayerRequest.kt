package com.reiflix.reiflix_local

import android.content.Context
import android.content.Intent
import android.net.Uri

/**
 * Typed contract for the Python/Flet -> Android native-player handoff.
 *
 * The bridge still carries a small URI query string for compatibility with
 * Flet 0.86.5. This class is the Android boundary: query parsing, defaults and
 * Intent extras live here instead of inside MainActivity.
 */
data class NativePlayerRequest(
    val requestId: String,
    val episodeUri: String,
    val episodeId: String,
    val title: String,
    val positionMs: Long,
    val canNext: Boolean,
    val canPrevious: Boolean,
    val autoplay: Boolean,
    val defaultSpeed: Float,
    val aspectRatio: String,
    val immersive: String,
    val rotation: String,
    val pip: Boolean,
    val autoHideSeconds: Int,
    val doubleTapSeekSeconds: Long,
    val longPressSpeed: Float,
    val maxVideoResolution: String,
    val maxVideoFrameRate: Int,
    val maxAudioChannels: Int,
    val gesturesVolume: Boolean,
    val gesturesBrightness: Boolean,
    val gesturesDoubleTap: Boolean,
    val gesturesLongPress: Boolean,
    val audioPreferredLanguage: String,
    val audioPreferredSubtitleLanguage: String,
    val audioSubtitles: String,
    val audioSubtitleScale: Float,
    val audioSubtitleBottomPadding: Int,
    val audioSubtitleEmbeddedStyle: Boolean,
) {
    fun toIntent(context: Context, normalizedUri: Uri): Intent =
        Intent(context, NativePlayerActivity::class.java)
            .putExtra("requestId", requestId)
            .putExtra("uri", normalizedUri.toString())
            .putExtra("mediaId", normalizedUri.toString())
            .putExtra("episodeId", episodeId)
            .putExtra("title", title)
            .putExtra("positionMs", positionMs)
            .putExtra("canNext", canNext)
            .putExtra("canPrevious", canPrevious)
            .putExtra("autoplay", autoplay)
            .putExtra("setting_player_default_speed", defaultSpeed)
            .putExtra("setting_player_aspect_ratio", aspectRatio)
            .putExtra("setting_player_immersive", immersive)
            .putExtra("setting_player_rotation", rotation)
            .putExtra("setting_player_pip", pip)
            .putExtra("setting_player_auto_hide_seconds", autoHideSeconds)
            .putExtra("setting_player_double_tap_seek_seconds", doubleTapSeekSeconds)
            .putExtra("setting_player_long_press_speed", longPressSpeed)
            .putExtra("setting_player_max_video_resolution", maxVideoResolution)
            .putExtra("setting_player_max_video_frame_rate", maxVideoFrameRate)
            .putExtra("setting_player_max_audio_channels", maxAudioChannels)
            .putExtra("setting_gestures_volume", gesturesVolume)
            .putExtra("setting_gestures_brightness", gesturesBrightness)
            .putExtra("setting_gestures_double_tap", gesturesDoubleTap)
            .putExtra("setting_gestures_long_press", gesturesLongPress)
            .putExtra("setting_audio_preferred_language", audioPreferredLanguage)
            .putExtra("setting_audio_preferred_subtitle_language", audioPreferredSubtitleLanguage)
            .putExtra("setting_audio_subtitles", audioSubtitles)
            .putExtra("setting_audio_subtitle_scale", audioSubtitleScale)
            .putExtra("setting_audio_subtitle_bottom_padding", audioSubtitleBottomPadding)
            .putExtra("setting_audio_subtitle_embedded_style", audioSubtitleEmbeddedStyle)

    companion object {
        fun fromBridgeUri(source: Uri): NativePlayerRequest =
            NativePlayerRequest(
                requestId = source.getQueryParameter("request_id").orEmpty().trim(),
                episodeUri = source.getQueryParameter("uri").orEmpty().trim(),
                episodeId = source.getQueryParameter("episode_id").orEmpty(),
                title = source.getQueryParameter("title") ?: "Episódio",
                positionMs = source.getQueryParameter("position_ms")?.toLongOrNull()?.coerceAtLeast(0L) ?: 0L,
                canNext = source.getQueryParameter("can_next")?.toBooleanStrictOrNull() ?: false,
                canPrevious = source.getQueryParameter("can_previous")?.toBooleanStrictOrNull() ?: false,
                autoplay = source.getQueryParameter("autoplay")?.toBooleanStrictOrNull() ?: true,
                defaultSpeed = source.getQueryParameter("setting_player_default_speed")?.toFloatOrNull() ?: 1f,
                aspectRatio = source.getQueryParameter("setting_player_aspect_ratio") ?: "fit",
                immersive = source.getQueryParameter("setting_player_immersive") ?: "always",
                rotation = source.getQueryParameter("setting_player_rotation") ?: "auto",
                pip = source.getQueryParameter("setting_player_pip")?.toBooleanStrictOrNull() ?: true,
                autoHideSeconds = source.getQueryParameter("setting_player_auto_hide_seconds")?.toIntOrNull() ?: 5,
                doubleTapSeekSeconds = source.getQueryParameter("setting_player_double_tap_seek_seconds")?.toLongOrNull() ?: 10L,
                longPressSpeed = source.getQueryParameter("setting_player_long_press_speed")?.toFloatOrNull() ?: 2f,
                maxVideoResolution = source.getQueryParameter("setting_player_max_video_resolution") ?: "auto",
                maxVideoFrameRate = source.getQueryParameter("setting_player_max_video_frame_rate")?.toIntOrNull() ?: 0,
                maxAudioChannels = source.getQueryParameter("setting_player_max_audio_channels")?.toIntOrNull() ?: 0,
                gesturesVolume = source.getQueryParameter("setting_gestures_volume")?.toBooleanStrictOrNull() ?: false,
                gesturesBrightness = source.getQueryParameter("setting_gestures_brightness")?.toBooleanStrictOrNull() ?: false,
                gesturesDoubleTap = source.getQueryParameter("setting_gestures_double_tap")?.toBooleanStrictOrNull() ?: false,
                gesturesLongPress = source.getQueryParameter("setting_gestures_long_press")?.toBooleanStrictOrNull() ?: false,
                audioPreferredLanguage = source.getQueryParameter("setting_audio_preferred_language").orEmpty(),
                audioPreferredSubtitleLanguage = source.getQueryParameter("setting_audio_preferred_subtitle_language").orEmpty(),
                audioSubtitles = source.getQueryParameter("setting_audio_subtitles") ?: "auto",
                audioSubtitleScale = source.getQueryParameter("setting_audio_subtitle_scale")?.toFloatOrNull() ?: 1f,
                audioSubtitleBottomPadding = source.getQueryParameter("setting_audio_subtitle_bottom_padding")?.toIntOrNull() ?: 8,
                audioSubtitleEmbeddedStyle = source.getQueryParameter("setting_audio_subtitle_embedded_style")?.toBooleanStrictOrNull() ?: true,
            )
    }
}
