package com.reiflix.reiflix_local

import android.content.ContentValues
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.provider.MediaStore
import android.view.View
import androidx.media3.common.Player
import androidx.media3.ui.PlayerView
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import org.junit.After
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference

@RunWith(AndroidJUnit4::class)
class EndToEndPlayerHandoffInstrumentedTest {
    private lateinit var target: android.content.Context
    private lateinit var handler: Handler
    private var fixtureUri: Uri? = null

    @Before
    fun setUp() {
        target = InstrumentationRegistry.getInstrumentation().targetContext
        handler = Handler(Looper.getMainLooper())
        grantMediaReadPermission()
        launchMainActivity()
    }

    @After
    fun tearDown() {
        fixtureUri?.let { runCatching { target.contentResolver.delete(it, null, null) } }
        runOnMainBounded {
            currentResumedActivity()?.finish()
        }
    }

    @Test
    fun pythonStyleNativeDeepLink_opensNativePlayerAndBackReturnsToMainActivity() {
        val uri = insertFixtureIntoMediaStore()
        fixtureUri = uri
        val requestId = "e2e-" + UUID.randomUUID().toString()
        val nativeIntent = Intent.parseUri(
            Uri.Builder()
                .scheme("reiflix")
                .authority("native")
                .appendQueryParameter("action", "play")
                .appendQueryParameter("request_id", requestId)
                .appendQueryParameter("uri", uri.toString())
                .appendQueryParameter("title", "E2E Fixture")
                .appendQueryParameter("position_ms", "0")
                .appendQueryParameter("can_next", "false")
                .appendQueryParameter("can_previous", "false")
                .appendQueryParameter("autoplay", "false")
                .build()
                .toString(),
            0,
        )

        invokeHandleNativeIntent(nativeIntent)

        val player = awaitResumedPlayerActivity()
        val playerView = awaitPlayerView(player)
        val mediaPlayer = await(timeoutMs = 12_000L) {
            playerView.player?.takeIf { it.playbackState == Player.STATE_READY }
        }
        assertTrue("Native Media3 player must become READY after the Flet-style handoff", mediaPlayer != null)
        assertTrue("Native PlayerActivity must remain alive", !player.isFinishing && !player.isDestroyed)

        val device = androidx.test.uiautomator.UiDevice.getInstance(
            InstrumentationRegistry.getInstrumentation()
        )
        device.pressBack()
        await(timeoutMs = 8_000L) { isMainActivityResumed() }
        assertFalse("Player must not finish the whole Rei-Flix task", isPlayerActivityResumed())
        assertTrue("Android Back must return to MainActivity", isMainActivityResumed())
    }

    private fun launchMainActivity() {
        val intent = Intent(target, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        InstrumentationRegistry.getInstrumentation().startActivitySync(intent)
        assertTrue("MainActivity must become RESUMED", isMainActivityResumed())
    }

    private fun invokeHandleNativeIntent(intent: Intent) {
        runOnMainBounded {
            val activity = currentResumedMainActivity()
            val method = MainActivity::class.java.getDeclaredMethod(
                "handleNativeIntent",
                Intent::class.java,
            )
            method.isAccessible = true
            method.invoke(activity, intent)
        }
    }

    private fun currentResumedActivity(): android.app.Activity? =
        ActivityLifecycleMonitorRegistry.getInstance()
            .getActivitiesInStage(Stage.RESUMED)
            .firstOrNull()

    private fun currentResumedMainActivity(): MainActivity =
        ActivityLifecycleMonitorRegistry.getInstance()
            .getActivitiesInStage(Stage.RESUMED)
            .firstOrNull { it is MainActivity } as? MainActivity
            ?: error("MainActivity is not RESUMED")

    private fun isMainActivityResumed(): Boolean =
        currentResumedActivity() is MainActivity

    private fun isPlayerActivityResumed(): Boolean =
        currentResumedActivity() is NativePlayerActivity

    private fun awaitResumedPlayerActivity(): NativePlayerActivity =
        await(timeoutMs = 12_000L) {
            currentResumedActivity() as? NativePlayerActivity
        } ?: throw AssertionError("NativePlayerActivity did not become RESUMED")

    private fun awaitPlayerView(activity: NativePlayerActivity): PlayerView =
        await(timeoutMs = 12_000L) {
            activity.window.decorView.findViewWithTag<View>("reiflix_player_view") as? PlayerView
        } ?: throw AssertionError("NativePlayerActivity PlayerView was not created")

    private fun <T> await(timeoutMs: Long, producer: () -> T?): T? {
        val deadline = SystemClock.uptimeMillis() + timeoutMs
        while (SystemClock.uptimeMillis() < deadline) {
            var value: T? = null
            runOnMainBounded { value = producer() }
            if (value != null) return value
            SystemClock.sleep(75L)
        }
        return null
    }

    private fun runOnMainBounded(timeoutMs: Long = 2_000L, action: () -> Unit) {
        val completed = CountDownLatch(1)
        val failure = AtomicReference<Throwable?>(null)
        handler.post {
            try {
                action()
            } catch (error: Throwable) {
                failure.set(error)
            } finally {
                completed.countDown()
            }
        }
        assertTrue(
            "Android main thread did not respond within ${timeoutMs}ms",
            completed.await(timeoutMs, TimeUnit.MILLISECONDS),
        )
        failure.get()?.let { throw AssertionError("Main-thread action failed", it) }
    }

    private fun grantMediaReadPermission() {
        val permission = if (Build.VERSION.SDK_INT >= 33) {
            "android.permission.READ_MEDIA_VIDEO"
        } else {
            "android.permission.READ_EXTERNAL_STORAGE"
        }
        val process = Runtime.getRuntime().exec(arrayOf("sh", "-c", "pm grant ${target.packageName} $permission"))
        process.waitFor(5, TimeUnit.SECONDS)
    }

    private fun insertFixtureIntoMediaStore(): Uri {
        val displayName = "reiflix-e2e-${UUID.randomUUID()}.mp4"
        val values = ContentValues().apply {
            put(MediaStore.Video.Media.DISPLAY_NAME, displayName)
            put(MediaStore.Video.Media.MIME_TYPE, "video/mp4")
            if (Build.VERSION.SDK_INT >= 29) {
                put(MediaStore.Video.Media.RELATIVE_PATH, "Movies/ReiFlixTest")
                put(MediaStore.Video.Media.IS_PENDING, 1)
            }
        }
        val collection = if (Build.VERSION.SDK_INT >= 29) {
            MediaStore.Video.Media.getContentUri(MediaStore.VOLUME_EXTERNAL)
        } else {
            MediaStore.Video.Media.EXTERNAL_CONTENT_URI
        }
        val uri = target.contentResolver.insert(collection, values)
            ?: error("Unable to create MediaStore fixture")
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
}
