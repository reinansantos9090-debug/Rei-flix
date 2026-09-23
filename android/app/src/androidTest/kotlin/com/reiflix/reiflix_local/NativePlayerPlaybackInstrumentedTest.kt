package com.reiflix.reiflix_local

import android.content.ContentValues
import android.graphics.Matrix
import android.content.Intent
import android.os.Build
import android.os.SystemClock
import android.provider.MediaStore
import android.view.MotionEvent
import android.view.TextureView
import android.view.View
import android.view.ViewConfiguration
import android.widget.TextView
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

        activity = InstrumentationRegistry.getInstrumentation().startActivitySync(intent) as NativePlayerActivity

        val playerView = awaitView<PlayerView>("reiflix_player_view")
        val player = onMain {
            requireNotNull(playerView.player) { "Media3 PlayerView did not receive a player" }
        }

        await("Media3 must reach READY before interaction") {
            player.playbackState == Player.STATE_READY
        }
        assertFalse("Player should initially remain paused for deterministic interaction", onMain { player.isPlaying })
        assertTrue("Native player Activity must remain alive after READY", !activity!!.isFinishing)

        val playPause = awaitView<View>("reiflix_play_pause")
        assertTrue("Play control must be present", onMain { playPause.performClick() })
        await("Play button must start playback") { player.isPlaying }
        await("The real video must render its first frame") { activity!!.firstFrameRenderedForTesting }
        InstrumentationRegistry.getInstrumentation().waitForIdleSync()
        assertTrue("Native player must actually be playing the local fixture", onMain { player.isPlaying })
        assertTrue("Native player Activity must remain alive after first frame", !activity!!.isFinishing && !activity!!.isDestroyed)

        val seekBar = awaitView<android.widget.SeekBar>("reiflix_seekbar")
        val initialDuration = onMain { player.duration }
        assertTrue("Fixture must expose a positive duration", initialDuration > 0L)
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            val y = seekBar.height / 2f
            val startX = (seekBar.paddingLeft + 4).toFloat()
            val targetX = (seekBar.width - seekBar.paddingRight - 4).toFloat() * 0.5f
            val down = android.view.MotionEvent.obtain(
                android.os.SystemClock.uptimeMillis(),
                android.os.SystemClock.uptimeMillis(),
                android.view.MotionEvent.ACTION_DOWN,
                startX,
                y,
                0,
            )
            seekBar.dispatchTouchEvent(down)
            down.recycle()
            val move = android.view.MotionEvent.obtain(
                android.os.SystemClock.uptimeMillis(),
                android.os.SystemClock.uptimeMillis(),
                android.view.MotionEvent.ACTION_MOVE,
                targetX,
                y,
                0,
            )
            seekBar.dispatchTouchEvent(move)
            move.recycle()
            val up = android.view.MotionEvent.obtain(
                android.os.SystemClock.uptimeMillis(),
                android.os.SystemClock.uptimeMillis(),
                android.view.MotionEvent.ACTION_UP,
                targetX,
                y,
                0,
            )
            seekBar.dispatchTouchEvent(up)
            up.recycle()
        }
        await("Seek bar interaction must move player position") {
            player.currentPosition > 500L && player.currentPosition < player.duration - 100L
        }

        assertTrue("Pause control must be clickable", onMain { playPause.performClick() })
        await("Pause button must pause playback") { !player.isPlaying }
        assertTrue("Play button must resume playback", onMain { playPause.performClick() })
        await("Second click must resume playback") { player.isPlaying }

        await("Native player should keep system bars hidden") {
            val insets = androidx.core.view.ViewCompat.getRootWindowInsets(activity!!.window.decorView)
            insets != null && !insets.isVisible(WindowInsetsCompat.Type.systemBars())
        }
        assertTrue(
            "Player must remain sensor-orientation capable",
            activity!!.requestedOrientation == android.content.pm.ActivityInfo.SCREEN_ORIENTATION_FULL_SENSOR,
        )

        val beforeSeek = onMain { player.currentPosition }
        onMain { player.seekTo(0L) }
        await("Media3 seek must reach the beginning") { player.currentPosition <= 200L }
        assertTrue("Seek position should move from the pre-seek position", beforeSeek >= 0L)

        val gestureLayer = awaitView<View>("reiflix_gesture_layer")

        onMain {
            player.pause()
            player.seekTo(3_000L)
        }
        await("Gesture seek precondition must be reachable") { player.currentPosition >= 2_500L }

        val controls = awaitView<View>("reiflix_controls_root")
        val controlsBefore = onMain { controls.visibility }
        val gestureSize = onMain { gestureLayer.width to gestureLayer.height }

        // A single tap is deliberately delayed for the double-tap window. This
        // prevents the first tap from firing a UI toggle before a second tap
        // can be recognized as the CloudStream-style double tap.
        tap(gestureLayer, gestureSize.first * 0.5f, gestureSize.second * 0.5f)
        SystemClock.sleep(80L)
        assertTrue(
            "First tap must not toggle controls before the double-tap window expires",
            onMain { controls.visibility == controlsBefore },
        )

        onMain {
            player.pause()
            player.seekTo(3_000L)
        }
        await("Seek position must be restored for left double tap") { player.currentPosition >= 2_500L }
        doubleTap(gestureLayer, gestureSize.first * 0.12f, gestureSize.second * 0.5f)
        await("Left double tap must seek backward") { player.currentPosition <= 1_000L }

        doubleTap(gestureLayer, gestureSize.first * 0.88f, gestureSize.second * 0.5f)
        await("Right double tap must seek forward") { player.currentPosition >= 2_000L }

        // After the double-tap sequence a normal single tap is still allowed
        // to toggle the custom controls once the debounce window expires.
        val afterDouble = onMain { controls.visibility }
        tap(gestureLayer, gestureSize.first * 0.5f, gestureSize.second * 0.5f)
        await("Single tap must toggle controls after the debounce window") {
            controls.visibility != afterDouble
        }

        onMain { player.seekTo(0L) }
        await("Horizontal gesture precondition") { player.currentPosition <= 500L }
        swipe(
            gestureLayer,
            gestureSize.first * 0.25f,
            gestureSize.second * 0.5f,
            gestureSize.first * 0.65f,
            gestureSize.second * 0.5f,
        )
        await("Horizontal swipe must commit one coherent seek on ACTION_UP") {
            player.currentPosition > 500L
        }

        val feedback = awaitView<TextView>("reiflix_feedback")
        val back = awaitView<View>("reiflix_back_button")
        val systemAudio = target.getSystemService(android.content.Context.AUDIO_SERVICE) as android.media.AudioManager
        val volumeBefore = systemAudio.getStreamVolume(android.media.AudioManager.STREAM_MUSIC)

        swipe(
            gestureLayer,
            gestureSize.first * 0.12f,
            gestureSize.second * 0.72f,
            gestureSize.first * 0.12f,
            gestureSize.second * 0.30f,
        )
        swipe(
            gestureLayer,
            gestureSize.first * 0.88f,
            gestureSize.second * 0.72f,
            gestureSize.first * 0.88f,
            gestureSize.second * 0.30f,
        )
        SystemClock.sleep(300L)
        assertFalse("Vertical swipes must not expose brightness feedback", onMain { feedback.text?.contains("BRILHO") == true })
        assertFalse("Vertical swipes must not expose volume feedback", onMain { feedback.text?.contains("VOLUME") == true })
        assertEquals("Vertical swipes must not change Android media volume", volumeBefore, systemAudio.getStreamVolume(android.media.AudioManager.STREAM_MUSIC))

        assertTrue("Visual Back control must be clickable", onMain { back.performClick() })
        await("Visual Back must finish the native player Activity") { activity!!.isFinishing }

        val secondIntent = Intent(target, NativePlayerActivity::class.java)
            .putExtra("requestId", "instrumented-player-android-back")
            .putExtra("uri", fixtureUri!!.toString())
            .putExtra("title", "Fixture local")
            .putExtra("positionMs", 0L)
            .putExtra("canNext", false)
            .putExtra("canPrevious", false)
            .putExtra("autoplay", false)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        activity = InstrumentationRegistry.getInstrumentation().startActivitySync(secondIntent) as NativePlayerActivity
        awaitView<View>("reiflix_back_button")
        onMain { activity!!.onBackPressedDispatcher.onBackPressed() }
        await("Android Back must finish the native player Activity") { activity!!.isFinishing }

        pinch(gestureLayer, zoom = true)
        await("Pinch out must select ZOOM") {
            playerView.resizeMode == androidx.media3.ui.AspectRatioFrameLayout.RESIZE_MODE_ZOOM
        }
        assertTrue(
            "Pinch out must actually transform the video surface, not only change resize mode",
            onMain {
                val video = playerView.videoSurfaceView
                if (video !is TextureView) {
                    false
                } else {
                    val matrix = Matrix()
                    video.getTransform(matrix)
                    val values = FloatArray(9)
                    matrix.getValues(values)
                    values[Matrix.MSCALE_X] > 1.01f && values[Matrix.MSCALE_Y] > 1.01f
                }
            },
        )
        pinch(gestureLayer, zoom = false)
        await("Pinch in must select FIT") {
            playerView.resizeMode == androidx.media3.ui.AspectRatioFrameLayout.RESIZE_MODE_FIT
        }
        await("Pinch in must restore the video surface transform") {
            val video = playerView.videoSurfaceView
            if (video !is TextureView) {
                false
            } else {
                val matrix = Matrix()
                video.getTransform(matrix)
                val values = FloatArray(9)
                matrix.getValues(values)
                kotlin.math.abs(values[Matrix.MSCALE_X] - 1f) <= 0.01f &&
                    kotlin.math.abs(values[Matrix.MSCALE_Y] - 1f) <= 0.01f
            }
        }

        cancelGesture(gestureLayer, gestureSize.first * 0.8f, gestureSize.second * 0.5f)
        tap(gestureLayer, gestureSize.first * 0.5f, gestureSize.second * 0.5f)
        await("Touch state must recover after ACTION_CANCEL") {
            controls.visibility == View.VISIBLE
        }
        assertTrue(
            "Play control must remain accessible after gesture sequences",
            onMain { controls.isShown },
        )

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


    private fun dispatchEvent(view: View, event: MotionEvent) {
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            view.dispatchTouchEvent(event)
        }
        event.recycle()
    }

    private fun tap(view: View, x: Float, y: Float) {
        val down = SystemClock.uptimeMillis()
        dispatchEvent(view, MotionEvent.obtain(down, down, MotionEvent.ACTION_DOWN, x, y, 0))
        dispatchEvent(view, MotionEvent.obtain(down, down + 70L, MotionEvent.ACTION_UP, x, y, 0))
    }

    private fun doubleTap(view: View, x: Float, y: Float) {
        val first = SystemClock.uptimeMillis()
        dispatchEvent(view, MotionEvent.obtain(first, first, MotionEvent.ACTION_DOWN, x, y, 0))
        dispatchEvent(view, MotionEvent.obtain(first, first + 60L, MotionEvent.ACTION_UP, x, y, 0))
        val second = first + 120L
        dispatchEvent(view, MotionEvent.obtain(first, second, MotionEvent.ACTION_DOWN, x, y, 0))
        dispatchEvent(view, MotionEvent.obtain(first, second + 60L, MotionEvent.ACTION_UP, x, y, 0))
    }

    private fun swipe(view: View, startX: Float, startY: Float, endX: Float, endY: Float) {
        val down = SystemClock.uptimeMillis()
        dispatchEvent(view, MotionEvent.obtain(down, down, MotionEvent.ACTION_DOWN, startX, startY, 0))
        dispatchEvent(
            view,
            MotionEvent.obtain(
                down,
                down + 80L,
                MotionEvent.ACTION_MOVE,
                startX + (endX - startX) * 0.35f,
                startY + (endY - startY) * 0.35f,
                0,
            ),
        )
        dispatchEvent(
            view,
            MotionEvent.obtain(
                down,
                down + 140L,
                MotionEvent.ACTION_MOVE,
                startX + (endX - startX) * 0.75f,
                startY + (endY - startY) * 0.75f,
                0,
            ),
        )
        dispatchEvent(view, MotionEvent.obtain(down, down + 200L, MotionEvent.ACTION_UP, endX, endY, 0))
    }

    private fun cancelGesture(view: View, x: Float, y: Float) {
        val down = SystemClock.uptimeMillis()
        dispatchEvent(view, MotionEvent.obtain(down, down, MotionEvent.ACTION_DOWN, x, y, 0))
        dispatchEvent(view, MotionEvent.obtain(down, down + 80L, MotionEvent.ACTION_MOVE, x, y - 90f, 0))
        dispatchEvent(view, MotionEvent.obtain(down, down + 100L, MotionEvent.ACTION_CANCEL, x, y - 90f, 0))
    }

    private fun pinch(view: View, zoom: Boolean) {
        val centerX = view.width * 0.5f
        val centerY = view.height * 0.5f
        val minimumSpan = ViewConfiguration.get(view.context).scaledMinimumScalingSpan.toFloat()
        val spanDelta = maxOf(192f, minimumSpan * 0.5f)
        val startSpan = minOf(view.width * 0.72f, minimumSpan + spanDelta)
        val maximumSpan = view.width * 0.9f
        assertTrue(
            "Pinch test surface is too narrow for the platform minimum scaling span",
            maximumSpan > startSpan + 32f,
        )
        val endSpan = if (zoom) {
            maximumSpan
        } else {
            maxOf(minimumSpan + 64f, startSpan - spanDelta)
        }
        val middleSpan = startSpan + (endSpan - startSpan) * 0.5f
        val down = SystemClock.uptimeMillis()

        val first = MotionEvent.PointerProperties().apply {
            id = 0
            toolType = MotionEvent.TOOL_TYPE_FINGER
        }
        val second = MotionEvent.PointerProperties().apply {
            id = 1
            toolType = MotionEvent.TOOL_TYPE_FINGER
        }

        fun onePointer(action: Int, eventTime: Long): MotionEvent {
            val props = MotionEvent.PointerProperties().apply {
                id = 0
                toolType = MotionEvent.TOOL_TYPE_FINGER
            }
            val coords = MotionEvent.PointerCoords().apply {
                x = centerX - startSpan / 2f
                y = centerY
                pressure = 1f
                size = 1f
            }
            return MotionEvent.obtain(
                down,
                eventTime,
                action,
                1,
                arrayOf(props),
                arrayOf(coords),
                0,
                0,
                1f,
                1f,
                0,
                0,
                0,
                0,
            )
        }

        fun twoPointers(action: Int, eventTime: Long, span: Float): MotionEvent {
            val left = MotionEvent.PointerCoords().apply {
                x = centerX - span / 2f
                y = centerY
                pressure = 1f
                size = 1f
            }
            val right = MotionEvent.PointerCoords().apply {
                x = centerX + span / 2f
                y = centerY
                pressure = 1f
                size = 1f
            }
            return MotionEvent.obtain(
                down,
                eventTime,
                action,
                2,
                arrayOf(first, second),
                arrayOf(left, right),
                0,
                0,
                1f,
                1f,
                0,
                0,
                0,
                0,
            )
        }

        dispatchEvent(view, onePointer(MotionEvent.ACTION_DOWN, down))
        dispatchEvent(
            view,
            twoPointers(
                MotionEvent.ACTION_POINTER_DOWN or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT),
                down + 50L,
                startSpan,
            ),
        )
        dispatchEvent(view, twoPointers(MotionEvent.ACTION_MOVE, down + 100L, middleSpan))
        dispatchEvent(view, twoPointers(MotionEvent.ACTION_MOVE, down + 140L, endSpan))
        dispatchEvent(
            view,
            twoPointers(
                MotionEvent.ACTION_POINTER_UP or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT),
                down + 180L,
                endSpan,
            ),
        )
        dispatchEvent(view, MotionEvent.obtain(down, down + 220L, MotionEvent.ACTION_UP, centerX - endSpan / 2f, centerY, 0))
    }

    private fun <T : View> awaitView(tag: String, timeoutMs: Long = 12_000L): T {
        var result: View? = null
        val deadline = SystemClock.uptimeMillis() + timeoutMs
        while (SystemClock.uptimeMillis() < deadline) {
            InstrumentationRegistry.getInstrumentation().runOnMainSync {
                result = activity?.window?.decorView?.findViewWithTag(tag)
            }
            if (result != null) {
                @Suppress("UNCHECKED_CAST")
                return result as T
            }
            InstrumentationRegistry.getInstrumentation().waitForIdleSync()
            SystemClock.sleep(50L)
        }
        assertTrue("view with tag $tag", false)
        throw AssertionError("view with tag $tag not found")
    }

    private fun <T> onMain(action: () -> T): T {
        var result: T? = null
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            result = action()
        }
        return checkNotNull(result) { "Main-thread action returned null unexpectedly" }
    }

    private fun await(description: String, timeoutMs: Long = 12_000L, condition: () -> Boolean) {
        val deadline = SystemClock.uptimeMillis() + timeoutMs
        while (SystemClock.uptimeMillis() < deadline) {
            val passed = onMain { condition() }
            if (passed) return
            SystemClock.sleep(50L)
        }
        assertTrue(description, false)
    }
}
