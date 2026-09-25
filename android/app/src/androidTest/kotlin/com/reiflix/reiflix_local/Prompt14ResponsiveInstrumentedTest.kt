package com.reiflix.reiflix_local

import android.content.Context
import android.content.Intent
import android.content.res.Configuration
import android.os.Bundle
import android.os.SystemClock
import android.view.inputmethod.InputMethodManager
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.concurrent.TimeUnit

@RunWith(AndroidJUnit4::class)
class Prompt14ResponsiveInstrumentedTest {
    private lateinit var target: android.content.Context
    private lateinit var device: UiDevice

    @Before
    fun setUp() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        target = instrumentation.targetContext
        device = UiDevice.getInstance(instrumentation)
        launchMainActivity()
    }

    @After
    fun tearDown() {
        runCatching { device.unfreezeRotation() }
        runCatching { device.pressHome() }
    }

    @Test
    fun primaryUiAndSystemInsetsRemainUsableAtCurrentScale() {
        val activity = currentResumedMainActivity()
        val root = activity.window.decorView
        val insets = await("Window insets must be available") {
            ViewCompat.getRootWindowInsets(root)
        }
        assertNotNull(insets)
        val currentInsets = requireNotNull(insets)
        assertTrue(
            "Normal MainActivity must keep the status bar visible",
            currentInsets.isVisible(WindowInsetsCompat.Type.statusBars()),
        )
        assertTrue("MainActivity content must have a measured width", root.width > 0)
        assertTrue("MainActivity content must have a measured height", root.height > 0)

        val fontScale = activity.resources.configuration.fontScale
        assertTrue(
            "Unexpected test font scale: $fontScale",
            fontScale >= 0.99f && fontScale <= 1.51f,
        )

        assertHomeIsVisible()
        openSearchAndExerciseIme()
        openOrganizeAndReturn()
        openSettingsAndReturn()
        assertHomeIsVisible()

        rotateTo(Configuration.ORIENTATION_LANDSCAPE)
        assertTrue(
            "MainActivity must stay alive in landscape",
            !currentResumedMainActivity().isFinishing && !currentResumedMainActivity().isDestroyed,
        )
        assertHomeIsVisible()

        rotateTo(Configuration.ORIENTATION_PORTRAIT)
        assertTrue(
            "MainActivity must stay alive after returning to portrait",
            !currentResumedMainActivity().isFinishing && !currentResumedMainActivity().isDestroyed,
        )
        assertHomeIsVisible()
    }

    @Test
    fun imeBackClosesKeyboardBeforeLeavingHome() {
        val search = findSearchButton()
        click(search)
        val field = awaitObject(
            By.textContains("Buscar na sua biblioteca"),
            "Search field must be rendered as an actual editable surface",
        )
        click(field)
        await("IME must become visible") {
            ViewCompat.getRootWindowInsets(currentResumedMainActivity().window.decorView)
                ?.isVisible(WindowInsetsCompat.Type.ime()) == true
        }

        device.pressBack()
        await("Back must close the IME before navigating") {
            ViewCompat.getRootWindowInsets(currentResumedMainActivity().window.decorView)
                ?.isVisible(WindowInsetsCompat.Type.ime()) != true
        }
        assertHomeIsVisible()
    }

    private fun openSearchAndExerciseIme() {
        val search = findSearchButton()
        click(search)
        val field = awaitObject(
            By.textContains("Buscar na sua biblioteca"),
            "Search field must be visible after pressing Search",
        )
        click(field)
        await("Search IME must open") {
            ViewCompat.getRootWindowInsets(currentResumedMainActivity().window.decorView)
                ?.isVisible(WindowInsetsCompat.Type.ime()) == true
        }
        device.pressBack()
        await("Search IME must close on Back") {
            ViewCompat.getRootWindowInsets(currentResumedMainActivity().window.decorView)
                ?.isVisible(WindowInsetsCompat.Type.ime()) != true
        }
        assertHomeIsVisible()
    }

    private fun openOrganizeAndReturn() {
        val button = awaitObject(By.descContains("Organizar"), "Organize action must be accessible from Home")
        click(button)
        awaitText("Organizar", "Organize screen must render")
        device.pressBack()
        awaitText("ReiFlix", "Back must return to Home after Organize")
    }

    private fun openSettingsAndReturn() {
        val button = awaitObject(By.descContains("Configurações"), "Settings action must be accessible from Home")
        click(button)
        awaitText("Configurações", "Settings screen must render")
        device.pressBack()
        awaitText("ReiFlix", "Back must return to Home after Settings")
    }

    private fun assertHomeIsVisible() {
        awaitText("ReiFlix", "Home header must render")
        val search = device.findObject(By.descContains("Pesquisar"))
        val settings = device.findObject(By.descContains("Configurações"))
        assertTrue("Home must expose Search accessibility action", search != null)
        assertTrue("Home must expose Settings accessibility action", settings != null)
    }

    private fun findSearchButton() =
        awaitObject(By.descContains("Pesquisar"), "Search action must be accessible from Home")

    private fun click(node: androidx.test.uiautomator.UiObject2) {
        assertTrue("UI node must be clickable", node.isClickable)
        node.click()
    }

    private fun awaitText(text: String, message: String, timeoutMs: Long = 15_000L) {
        await(message, timeoutMs) { device.findObject(By.textContains(text)) != null }
    }

    private fun awaitObject(
        selector: androidx.test.uiautomator.BySelector,
        message: String,
        timeoutMs: Long = 15_000L,
    ): androidx.test.uiautomator.UiObject2 {
        return checkNotNull(
            await(message, timeoutMs) { device.findObject(selector) },
        )
    }

    private fun <T> await(
        message: String,
        timeoutMs: Long = 15_000L,
        condition: () -> T?,
    ): T? {
        val deadline = SystemClock.uptimeMillis() + timeoutMs
        var value = condition()
        while (value == null && SystemClock.uptimeMillis() < deadline) {
            SystemClock.sleep(100L)
            value = condition()
        }
        if (value == null) {
            throw AssertionError(message)
        }
        return value
    }

    private fun launchMainActivity() {
        val intent = Intent(target, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        InstrumentationRegistry.getInstrumentation().startActivitySync(intent)
        await("MainActivity must reach RESUMED") {
            runCatching { currentResumedMainActivity() }.getOrNull()
        }
    }

    private fun currentResumedMainActivity(): MainActivity {
        return checkNotNull(
            ActivityLifecycleMonitorRegistry.getInstance()
                .getActivitiesInStage(Stage.RESUMED)
                .filterIsInstance<MainActivity>()
                .firstOrNull(),
        ) { "MainActivity must be RESUMED" }
    }

    private fun rotateTo(expectedOrientation: Int) {
        if (expectedOrientation == Configuration.ORIENTATION_LANDSCAPE) {
            device.setOrientationLeft()
        } else {
            device.setOrientationNatural()
        }
        await("Requested orientation must be applied") {
            currentResumedMainActivity().resources.configuration.orientation == expectedOrientation
        }
    }
}
