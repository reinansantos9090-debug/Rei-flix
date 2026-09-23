package com.reiflix.reiflix_local

import android.content.Intent
import android.os.SystemClock
import android.provider.Settings
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class BackAndSettingsReturnInstrumentedTest {
    private lateinit var scenario: ActivityScenario<MainActivity>

    @Before
    fun setUp() {
        scenario = ActivityScenario.launch(MainActivity::class.java)
        awaitState("MainActivity must reach RESUMED before testing external returns") {
            scenario.state == androidx.lifecycle.Lifecycle.State.RESUMED
        }
    }

    @After
    fun tearDown() {
        pressBackBestEffort()
        scenario.close()
    }

    @Test
    fun allFilesSettingsBackReturnsToMainActivity() {
        val wasLaunched = invokeNoArg("openBroadStorageSettings")
        assertTrue("All-files Settings launch method must accept the request while Activity is resumed", wasLaunched)
        awaitState("MainActivity must actually leave RESUMED while Android Settings is visible") {
            scenario.state != androidx.lifecycle.Lifecycle.State.RESUMED
        }
        waitForExternalUiSettle()
        returnFromExternalSurface("com.android.settings")
        awaitState("Closing All Files Settings surface must return to MainActivity") {
            scenario.state == androidx.lifecycle.Lifecycle.State.RESUMED
        }
        scenario.onActivity { activity ->
            assertFalse("MainActivity must not be finishing after Settings Back", activity.isFinishing)
            assertFalse("MainActivity must remain alive after Settings Back", activity.isDestroyed)
        }
    }

    @Test
    fun appInfoSettingsBackReturnsToMainActivity() {
        val target = InstrumentationRegistry.getInstrumentation().targetContext
        val intent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
            .setData(android.net.Uri.parse("package:" + target.packageName))
        val launched = invokeExternalSettings("app_details", intent)
        assertTrue("App Info Settings launch must be accepted", launched)
        awaitState("MainActivity must leave RESUMED while App Info is visible") {
            scenario.state != androidx.lifecycle.Lifecycle.State.RESUMED
        }
        waitForExternalUiSettle()
        returnFromExternalSurface("com.android.settings")
        awaitState("Closing App Info Settings surface must return to MainActivity") {
            scenario.state == androidx.lifecycle.Lifecycle.State.RESUMED
        }
        scenario.onActivity { activity ->
            assertFalse(activity.isFinishing)
            assertFalse(activity.isDestroyed)
        }
    }

    @Test
    fun safPickerBackReturnsToMainActivityAndReleasesPendingState() {
        val launched = invokeNoArg("openTreePicker")
        assertTrue("SAF picker launch method must accept the request while Activity is resumed", launched)
        awaitState("MainActivity must leave RESUMED while DocumentsUI is visible") {
            scenario.state != androidx.lifecycle.Lifecycle.State.RESUMED
        }
        waitForExternalUiSettle()
        returnFromExternalSurface("com.google.android.documentsui", "com.android.documentsui")
        awaitState("Closing SAF picker must return to MainActivity") {
            scenario.state == androidx.lifecycle.Lifecycle.State.RESUMED
        }
        scenario.onActivity { activity ->
            assertFalse(activity.isFinishing)
            assertFalse(activity.isDestroyed)
            val field = MainActivity::class.java.getDeclaredField("safPickerPending")
            field.isAccessible = true
            assertFalse("SAF pending state must be cleared after cancel/back", field.getBoolean(activity))
        }
    }

    private fun invokeNoArg(name: String): Boolean {
        var outcome = false
        scenario.onActivity { activity ->
            val method = MainActivity::class.java.getDeclaredMethod(name)
            method.isAccessible = true
            outcome = (method.invoke(activity) as? Boolean) ?: true
        }
        return outcome
    }

    private fun invokeExternalSettings(kind: String, intent: Intent): Boolean {
        var outcome = false
        scenario.onActivity { activity ->
            val method = MainActivity::class.java.getDeclaredMethod(
                "launchExternalSettings",
                String::class.java,
                String::class.java,
                java.util.List::class.java,
            )
            method.isAccessible = true
            outcome = method.invoke(
                activity,
                kind,
                null,
                listOf("instrumented" to intent),
            ) as Boolean
        }
        return outcome
    }

    private fun returnFromExternalSurface(vararg packageNames: String) {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val packages = packageNames.joinToString(" ")
        val descriptor = instrumentation.uiAutomation.executeShellCommand(
            "for p in $packages; do am force-stop $p >/dev/null 2>&1 || true; done"
        )
        descriptor.close()
        instrumentation.waitForIdleSync()
        SystemClock.sleep(750L)
    }

    private fun waitForExternalUiSettle() {
        InstrumentationRegistry.getInstrumentation().waitForIdleSync()
        SystemClock.sleep(750L)
    }

    private fun awaitState(description: String, timeoutMs: Long = 15_000L, condition: () -> Boolean) {
        val deadline = SystemClock.uptimeMillis() + timeoutMs
        while (SystemClock.uptimeMillis() < deadline) {
            if (condition()) return
            InstrumentationRegistry.getInstrumentation().waitForIdleSync()
            SystemClock.sleep(100L)
        }
        assertTrue(description, false)
    }
}
