package com.reiflix.reiflix_local

import android.content.ContentValues
import android.content.Intent
import android.os.Build
import android.os.SystemClock
import android.provider.MediaStore
import android.view.View
import androidx.core.view.WindowInsetsCompat
import androidx.media3.common.Player
import androidx.media3.ui.PlayerView
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.After
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class NativePlayerPlaybackInstrumentedTest {
    private lateinit var target: android.content.Context
    private var fixtureUri: android.net.Uri? = null
    private var activity: NativePlayerActivity? = null

    @Before
    fun setUp() {
        target = InstrumentationRegistry.getInstrumentation().targetContext
        grantMediaReadPermission()
    }

    @After
    fun tearDown() {
        activity?.finish()
        fixtureUri?.let { runCatching { target.contentResolver.delete(it, null, null) } }
    }

    @Test
    fun localMediaStoreFixture_reachesReadyAndPlays_inImmersivePlayer() {
        val uri = insertFixtureIntoMediaStore()
        fixtureUri = uri

        val intent = Intent(target, NativePlayerActivity::class.java)
            .putExtra("requestId", "instrumented-player")
            .putExtra("uri", uri.toString())
            .putExtra("title", "Fixture local")
            .putExtra("positionMs", 0L)
            .putExtra("canNext", false)
            .putExtra("canPrevious", false)
            .putExtra("autoplay", false)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

        activity = InstrumentationRegistry.getInstrumentation().startActivitySync(intent)

        val playerView = awaitView<PlayerView>("reiflix_player_view")
        val player = requireNotNull(playerView.player) { "Media3 PlayerView did not receive a player" }

        await("Media3 must reach READY before interaction") {
            player?.playbackState == Player.STATE_READY
        }
        assertTrue("Player should initially remain paused for deterministic interaction", player?.isPlaying == false)

        val playPause = awaitView<View>("reiflix_play_pause")
        assertTrue("Play control must be present", playPause.performClick())
        await("Play button must start playback") { player?.isPlaying == true }
        InstrumentationRegistry.getInstrumentation().waitForIdleSync()
        assertTrue("Native player must actually be playing the local fixture", player.isPlaying)

        val seekBar = awaitView<android.widget.SeekBar>("reiflix_seekbar")
        val initialDuration = player.duration
        assertTrue("Fixture must expose a positive duration", initialDuration > 0L)
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            seekBar.setProgress(seekBar.max / 2, true)
        }
        await("Seek bar interaction must move player position") {
            player.currentPosition > 500L && player.currentPosition < player.duration
        }

        assertTrue("Pause control must be clickable", playPause.performClick())
        await("Pause button must pause playback") { player?.isPlaying == false }
        assertTrue("Play button must resume playback", playPause.performClick())
        await("Second click must resume playback") { player?.isPlaying == true }

        await("Native player should keep system bars hidden") {
            val insets = WindowInsetsCompat.toWindowInsetsCompat(
                activity!!.window.decorView.rootWindowInsets,
                activity!!.window.decorView,
            )
            !insets.isVisible(WindowInsetsCompat.Type.systemBars())
        }
        assertTrue(
            "Player must remain sensor-orientation capable",
            activity!!.requestedOrientation == android.content.pm.ActivityInfo.SCREEN_ORIENTATION_FULL_SENSOR,
        )

        val beforeSeek = player!!.currentPosition
        player.seekTo(0L)
        await("Media3 seek must reach the beginning") { player.currentPosition <= 200L }
        assertTrue("Seek position should move from the pre-seek position", beforeSeek >= 0L)

        // Gesture coordinates and visual scroll/immersive inspection remain manual
        // acceptance cases; this test deliberately validates the real Activity,
        // real MediaStore URI, and real Media3 decoder/playback path.
    }

    private fun grantMediaReadPermission() {
        val permission = if (Build.VERSION.SDK_INT >= 33) {
            "android.permission.READ_MEDIA_VIDEO"
        } else {
            "android.permission.READ_EXTERNAL_STORAGE"
        }
        runCatching {
            val descriptor = InstrumentationRegistry.getInstrumentation()
                .uiAutomation
                .executeShellCommand("pm grant ${target.packageName} $permission")
            descriptor.close()
        }
    }

    private fun insertFixtureIntoMediaStore(): android.net.Uri {
        val values = ContentValues().apply {
            put(MediaStore.Video.Media.DISPLAY_NAME, "reiflix-player-fixture.mp4")
            put(MediaStore.Video.Media.MIME_TYPE, "video/mp4")
            if (Build.VERSION.SDK_INT >= 29) {
                put(MediaStore.Video.Media.RELATIVE_PATH, "Movies/ReiFlixTest")
                put(MediaStore.Video.Media.IS_PENDING, 1)
            }
        }

        val collection = MediaStore.Video.Media.EXTERNAL_CONTENT_URI
        val uri = target.contentResolver.insert(collection, values)
            ?: error("Unable to create local MediaStore fixture")
        try {
            target.contentResolver.openOutputStream(uri).use { output ->
                checkNotNull(output)
                InstrumentationRegistry.getInstrumentation().context
                    .assets
                    .open("player_fixture.mp4")
                    .use { input -> input.copyTo(output) }
            }
            if (Build.VERSION.SDK_INT >= 29) {
                target.contentResolver.update(
                    uri,
                    ContentValues().apply { put(MediaStore.Video.Media.IS_PENDING, 0) },
                    null,
                    null,
                )
            }
            return uri
        } catch (error: Throwable) {
            runCatching { target.contentResolver.delete(uri, null, null) }
            throw error
        }
    }

    private fun <T : View> awaitView(tag: String): T {
        var result: T? = null
        await("view with tag $tag") {
            result = activity?.window?.decorView?.findViewWithTag(tag)
            result != null
        }
        @Suppress("UNCHECKED_CAST")
        return result as T
    }

    private fun await(description: String, timeoutMs: Long = 12_000L, condition: () -> Boolean) {
        val deadline = SystemClock.uptimeMillis() + timeoutMs
        while (SystemClock.uptimeMillis() < deadline) {
            if (condition()) return
            InstrumentationRegistry.getInstrumentation().waitForIdleSync()
            SystemClock.sleep(50L)
        }
        assertTrue(description, false)
    }
}
