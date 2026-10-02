package com.reiflix.reiflix_local

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.UiObject2
import androidx.test.uiautomator.UiScrollable
import androidx.test.uiautomator.UiSelector
import androidx.test.uiautomator.Until
import java.io.File
import org.junit.After
import org.junit.Before
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class Prompt43MetadataOwnerInstrumentedTest {
    private lateinit var target: Context
    private lateinit var device: UiDevice
    private lateinit var databaseFile: File

    @Before
    fun setUp() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        target = instrumentation.targetContext
        device = UiDevice.getInstance(instrumentation)
        databaseFile = File(File(target.filesDir, "data"), "library.sqlite3")
        installFixture()
        val intent = android.content.Intent(target, MainActivity::class.java)
            .addFlags(
                android.content.Intent.FLAG_ACTIVITY_NEW_TASK or
                    android.content.Intent.FLAG_ACTIVITY_CLEAR_TOP
            )
        instrumentation.startActivitySync(intent)
        waitForForegroundPackage(target.packageName)
    }

    @After
    fun tearDown() {
        runCatching { device.pressHome() }
    }

    @Test
    fun metadata_refresh_preserves_five_local_episodes_and_progress() {
        val title = By.text("Prompt 43 Fixture")
        assertNotNull("Fixture anime must be rendered on Home", waitFor(title, 20_000L))
        device.findObject(title).click()

        assertNotNull("Details screen must open", waitFor(By.text("Detalhes"), 10_000L))
        assertAllEpisodeLabelsVisible()

        val refresh = By.text("Atualizar metadata")
        assertNotNull("Details must expose the existing metadata refresh action", waitFor(refresh, 10_000L))
        device.findObject(refresh).click()

        // The request may succeed or fail depending on network availability; either
        // result must leave the canonical local collection untouched.
        waitFor(By.text("Atualizar metadata"), 10_000L)
        SystemClock.sleep(750L)

        assertDatabaseInvariant()
        assertAllEpisodeLabelsVisible()

        device.pressBack()
        waitForForegroundPackage(target.packageName)
        assertNotNull("Home must remain mounted after metadata refresh", waitFor(title, 10_000L))
        device.findObject(title).click()
        assertNotNull("Details must reopen after metadata refresh", waitFor(By.text("Detalhes"), 10_000L))
        assertAllEpisodeLabelsVisible()
        assertDatabaseInvariant()
    }

    private fun installFixture() {
        val dataDir = databaseFile.parentFile ?: error("Missing Flet data directory")
        if (!dataDir.exists()) {
            assertTrue("Unable to create Flet data directory", dataDir.mkdirs() || dataDir.isDirectory)
        }
        databaseFile.delete()
        target.assets.open("prompt43_library.sqlite3").use { input ->
            databaseFile.outputStream().use { output -> input.copyTo(output) }
        }
        assertTrue("Prompt 43 SQLite fixture must exist", databaseFile.isFile)
    }

    private fun assertDatabaseInvariant() {
        val db = SQLiteDatabase.openDatabase(databaseFile.path, null, SQLiteDatabase.OPEN_READONLY)
        db.use { database ->
            database.rawQuery(
                "SELECT id, title, anilist_id FROM anime ORDER BY id LIMIT 1",
                null,
            ).use { animeCursor ->
                assertTrue("Fixture anime row must exist", animeCursor.moveToFirst())
                val animeId = animeCursor.getLong(animeCursor.getColumnIndexOrThrow("id"))
                val title = animeCursor.getString(animeCursor.getColumnIndexOrThrow("title"))
                assertEquals("Prompt 43 Fixture", title)
                database.rawQuery(
                    "SELECT id, anime_id, path, media_identity, progress, watched FROM episodes WHERE anime_id=? ORDER BY number",
                    arrayOf(animeId.toString()),
                ).use { episodeCursor ->
                    var count = 0
                    var firstId = -1L
                    var firstProgress = -1.0
                    while (episodeCursor.moveToNext()) {
                        count += 1
                        val episodeId = episodeCursor.getLong(episodeCursor.getColumnIndexOrThrow("id"))
                        val episodeAnimeId = episodeCursor.getLong(episodeCursor.getColumnIndexOrThrow("anime_id"))
                        assertEquals("Every episode must retain the canonical local owner", animeId, episodeAnimeId)
                        assertTrue("Each fixture episode must retain a media identity", episodeCursor.getString(episodeCursor.getColumnIndexOrThrow("media_identity")).isNotBlank())
                        if (count == 1) {
                            firstId = episodeId
                            firstProgress = episodeCursor.getDouble(episodeCursor.getColumnIndexOrThrow("progress"))
                        }
                    }
                    assertEquals("All five local episodes must remain in SQLite", 5, count)
                    assertTrue("EP01 must keep its canonical local id", firstId > 0)
                    assertEquals("EP01 progress must remain 37%", 37.0, firstProgress, 0.01)
                }
            }
        }
    }

    private fun assertAllEpisodeLabelsVisible() {
        for (episode in 1..5) {
            scrollToText("EP ${episode.toString().padStart(2, '0')}")
        }
    }

    private fun scrollToText(text: String) {
        val selector = UiSelector().text(text)
        val scrollable = UiScrollable(UiSelector().scrollable(true))
        runCatching { scrollable.scrollIntoView(selector) }
        assertNotNull("Details must still expose $text", waitFor(By.text(text), 3_000L))
    }

    private fun waitFor(selector: androidx.test.uiautomator.BySelector, timeoutMs: Long): UiObject2? {
        val immediate = device.findObject(selector)
        return immediate ?: device.wait(Until.findObject(selector), timeoutMs)
    }

    private fun waitForForegroundPackage(vararg packages: String, timeoutMs: Long = 15_000L) {
        val deadline = SystemClock.uptimeMillis() + timeoutMs
        val expected = packages.toSet()
        while (SystemClock.uptimeMillis() < deadline) {
            if (expected.contains(device.currentPackageName)) return
            SystemClock.sleep(100L)
        }
        error("Expected foreground Android package ${expected.joinToString()}, got ${device.currentPackageName}")
    }
}
