package com.reiflix.reiflix_local

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NativePlayerRequestTest {
    @Test
    fun parsesBridgeContractWithDefaultsAndValidation() {
        val values = mapOf(
            "request_id" to "req-123",
            "uri" to "content://media/video/1",
            "title" to "Episode 1",
            "position_ms" to "-40",
            "can_next" to "true",
            "autoplay" to "false",
            "setting_player_default_speed" to "-2",
            "setting_player_auto_hide_seconds" to "999",
            "setting_player_double_tap_seek_seconds" to "-1",
            "setting_player_long_press_speed" to "0",
            "setting_player_max_video_frame_rate" to "-4",
            "setting_audio_subtitle_scale" to "0",
            "setting_audio_subtitle_bottom_padding" to "-8",
            "setting_audio_subtitle_embedded_style" to "false",
        )

        val request = NativePlayerRequest.fromQueryParameters(values::get)

        assertEquals("req-123", request.requestId)
        assertEquals("content://media/video/1", request.episodeUri)
        assertEquals("Episode 1", request.title)
        assertEquals(0L, request.positionMs)
        assertTrue(request.canNext)
        assertFalse(request.canPrevious)
        assertFalse(request.autoplay)
        assertEquals(1f, request.defaultSpeed)
        assertEquals(300, request.autoHideSeconds)
        assertEquals(10L, request.doubleTapSeekSeconds)
        assertEquals(2f, request.longPressSpeed)
        assertEquals(0, request.maxVideoFrameRate)
        assertEquals(1f, request.audioSubtitleScale)
        assertEquals(0, request.audioSubtitleBottomPadding)
        assertFalse(request.audioSubtitleEmbeddedStyle)
    }

    @Test
    fun keepsExplicitPlayerContractValues() {
        val request = NativePlayerRequest.fromQueryParameters(
            mapOf(
                "request_id" to "req-456",
                "uri" to "file:///storage/emulated/0/episode.mkv",
                "can_next" to "true",
                "can_previous" to "true",
                "autoplay" to "true",
                "setting_player_default_speed" to "1.5",
                "setting_player_aspect_ratio" to "fill",
                "setting_player_immersive" to "always",
                "setting_player_rotation" to "landscape",
                "setting_player_pip" to "false",
                "setting_player_auto_hide_seconds" to "8",
                "setting_player_double_tap_seek_seconds" to "15",
                "setting_player_long_press_speed" to "2.5",
            )::get,
        )

        assertEquals("req-456", request.requestId)
        assertEquals("file:///storage/emulated/0/episode.mkv", request.episodeUri)
        assertTrue(request.canNext)
        assertTrue(request.canPrevious)
        assertTrue(request.autoplay)
        assertEquals(1.5f, request.defaultSpeed)
        assertEquals("fill", request.aspectRatio)
        assertEquals("landscape", request.rotation)
        assertFalse(request.pip)
        assertEquals(8, request.autoHideSeconds)
        assertEquals(15L, request.doubleTapSeekSeconds)
        assertEquals(2.5f, request.longPressSpeed)
    }
}
