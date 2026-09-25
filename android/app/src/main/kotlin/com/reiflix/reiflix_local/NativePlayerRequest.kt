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
            fromQueryParameters(source::getQueryParameter)

        /**
         * Pure parser used by JVM tests and by the Android URI adapter.
         * Keeping parsing independent of Uri makes the boundary deterministic.
         */
        fun fromQueryParameters(get: (String) -> String?): NativePlayerRequest =
            NativePlayerRequest(
                requestId = get("request_id").orEmpty().trim(),
                episodeUri = get("uri").orEmpty().trim(),
                episodeId = get("episode_id").orEmpty(),
                title = get("title") ?: "Episódio",
                positionMs = get("position_ms")?.toLongOrNull()?.coerceAtLeast(0L) ?: 0L,
                canNext = get("can_next")?.toBooleanStrictOrNull() ?: false,
                canPrevious = get("can_previous")?.toBooleanStrictOrNull() ?: false,
                autoplay = get("autoplay")?.toBooleanStrictOrNull() ?: true,
                defaultSpeed = get("setting_player_default_speed")?.toFloatOrNull()?.takeIf { it > 0f } ?: 1f,
                aspectRatio = get("setting_player_aspect_ratio") ?: "fit",
                immersive = get("setting_player_immersive") ?: "always",
                rotation = get("setting_player_rotation") ?: "auto",
                pip = get("setting_player_pip")?.toBooleanStrictOrNull() ?: true,
                autoHideSeconds = get("setting_player_auto_hide_seconds")?.toIntOrNull()?.coerceIn(0, 300) ?: 5,
                doubleTapSeekSeconds = get("setting_player_double_tap_seek_seconds")?.toLongOrNull()?.coerceIn(1L, 120L) ?: 10L,
                longPressSpeed = get("setting_player_long_press_speed")?.toFloatOrNull()?.coerceIn(1f, 3f) ?: 2f,
                maxVideoResolution = get("setting_player_max_video_resolution") ?: "auto",
                maxVideoFrameRate = get("setting_player_max_video_frame_rate")?.toIntOrNull()?.coerceAtLeast(0) ?: 0,
                maxAudioChannels = get("setting_player_max_audio_channels")?.toIntOrNull()?.coerceAtLeast(0) ?: 0,
                gesturesVolume = get("setting_gestures_volume")?.toBooleanStrictOrNull() ?: false,
                gesturesBrightness = get("setting_gestures_brightness")?.toBooleanStrictOrNull() ?: false,
                gesturesDoubleTap = get("setting_gestures_double_tap")?.toBooleanStrictOrNull() ?: false,
                gesturesLongPress = get("setting_gestures_long_press")?.toBooleanStrictOrNull() ?: false,
                audioPreferredLanguage = get("setting_audio_preferred_language").orEmpty(),
                audioPreferredSubtitleLanguage = get("setting_audio_preferred_subtitle_language").orEmpty(),
                audioSubtitles = get("setting_audio_subtitles") ?: "auto",
                audioSubtitleScale = get("setting_audio_subtitle_scale")?.toFloatOrNull()?.coerceIn(0.5f, 2f) ?: 1f,
                audioSubtitleBottomPadding = get("setting_audio_subtitle_bottom_padding")?.toIntOrNull()?.coerceIn(0, 50) ?: 8,
                audioSubtitleEmbeddedStyle = get("setting_audio_subtitle_embedded_style")?.toBooleanStrictOrNull() ?: true,
            )
    }
}
