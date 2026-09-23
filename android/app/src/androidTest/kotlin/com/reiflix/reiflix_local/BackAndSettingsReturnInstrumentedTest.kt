package com.reiflix.reiflix_local

import android.content.Intent
import android.os.SystemClock
import android.provider.Settings
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import androidx.test.uiautomator.UiDevice
import org.junit.After
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class BackAndSettingsReturnInstrumentedTest {
    private lateinit var target: android.content.Context
    private lateinit var device: UiDevice

    @Before
    fun setUp() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        target = instrumentation.targetContext
        device = UiDevice.getInstance(instrumentation)
        launchMainActivity()
        waitForForegroundPackage(target.packageName)
        assertMainActivityAlive()
    }

    @After
    fun tearDown() {
        runCatching { device.pressHome() }
        runCatching { device.executeShellCommand("am force-stop ${target.packageName}").close() }
    }

    @Test
    fun allFilesSettingsBackReturnsToMainActivity() {
        val wasLaunched = invokeNoArg("openBroadStorageSettings")
        assertTrue("All-files Settings launch method must accept the request while Activity is resumed", wasLaunched)
        waitForForegroundPackage("com.android.settings")
        pressBackAcrossApplicationBoundary()
        waitForForegroundPackage(target.packageName)
        assertMainActivityAlive()
    }

    @Test
    fun appInfoSettingsBackReturnsToMainActivity() {
        val intent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
            .setData(android.net.Uri.parse("package:" + target.packageName))
        val launched = invokeExternalSettings("app_details", intent)
        assertTrue("App Info Settings launch must be accepted", launched)
        waitForForegroundPackage("com.android.settings")
        pressBackAcrossApplicationBoundary()
        waitForForegroundPackage(target.packageName)
        assertMainActivityAlive()
    }

    @Test
    fun safPickerBackReturnsToMainActivityAndReleasesPendingState() {
        val launched = invokeNoArg("openTreePicker")
        assertTrue("SAF picker launch method must accept the request while Activity is resumed", launched)
        waitForForegroundPackage(
            "com.android.documentsui",
            "com.google.android.documentsui",
        )
        pressBackAcrossApplicationBoundary()
        waitForForegroundPackage(target.packageName)
        val activity = currentResumedMainActivity()
        assertFalse("MainActivity must not be finishing after DocumentsUI Back", activity.isFinishing)
        assertFalse("MainActivity must remain alive after DocumentsUI Back", activity.isDestroyed)
        val field = MainActivity::class.java.getDeclaredField("safPickerPending")
        field.isAccessible = true
        assertFalse("SAF pending state must be cleared after cancel/back", field.getBoolean(activity))
    }

    @Test
    fun appSystemBackIsHandledInsideReiFlix() {
        assertTrue(
            "UiDevice.pressBack() must dispatch the supported system Back action",
            device.pressBack(),
        )
        waitForForegroundPackage(target.packageName)
        assertMainActivityAlive()
    }

    private fun launchMainActivity() {
        val intent = Intent(target, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        InstrumentationRegistry.getInstrumentation().startActivitySync(intent)
    }

    private fun invokeNoArg(name: String): Boolean {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        var outcome = false
        instrumentation.runOnMainSync {
            val activity = currentResumedMainActivity()
            val method = MainActivity::class.java.getDeclaredMethod(name)
            method.isAccessible = true
            outcome = (method.invoke(activity) as? Boolean) ?: true
        }
        return outcome
    }

    private fun invokeExternalSettings(kind: String, intent: Intent): Boolean {
        var outcome = false
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            val activity = currentResumedMainActivity()
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

    private fun currentResumedMainActivity(): MainActivity {
        var activity: MainActivity? = null
        ActivityLifecycleMonitorRegistry.getInstance()
            .getActivitiesInStage(Stage.RESUMED)
            .firstOrNull { it is MainActivity }
            ?.let { activity = it as MainActivity }
        return checkNotNull(activity) { "MainActivity must be RESUMED when this helper is used" }
    }

    private fun assertMainActivityAlive() {
        var finishing = true
        var destroyed = true
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            val activity = currentResumedMainActivity()
            finishing = activity.isFinishing
            destroyed = activity.isDestroyed
        }
        assertFalse("MainActivity must not be finishing", finishing)
        assertFalse("MainActivity must remain alive", destroyed)
    }

    private fun pressBackAcrossApplicationBoundary() {
        assertTrue(
            "UiDevice.pressBack() must dispatch the supported system Back action",
            device.pressBack(),
        )
    }

    private fun waitForForegroundPackage(vararg packages: String, timeoutMs: Long = 15_000L) {
        val deadline = SystemClock.uptimeMillis() + timeoutMs
        val expected = packages.toSet()
        while (SystemClock.uptimeMillis() < deadline) {
            if (expected.contains(device.currentPackageName)) return
            SystemClock.sleep(100L)
        }
        assertTrue(
            "Expected foreground Android package, got: " + (device.currentPackageName ?: "<none>") +
                "; expected one of: " + packages.joinToString(),
            false,
        )
    }
}