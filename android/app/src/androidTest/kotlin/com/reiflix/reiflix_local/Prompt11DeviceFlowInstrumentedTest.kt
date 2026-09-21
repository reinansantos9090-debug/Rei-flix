package com.reiflix.reiflix_local

import android.os.Build
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class Prompt11DeviceFlowInstrumentedTest {
    private lateinit var context: android.content.Context

    @Before fun setUp() {
        context = InstrumentationRegistry.getInstrumentation().targetContext
        File(File(context.filesDir, "data"), "reiflix-native-index.json").delete()
    }

    @Test fun runtimeApiAndNativeBatchContract() {
        assertTrue(Build.VERSION.SDK_INT >= 30)
        assertTrue(Build.VERSION.SDK_INT <= 36)
        val sizes = mutableListOf<Int>()
        val batch = NativeBatch.Accumulator(250) { value, _, _ -> sizes += value.length() }
        repeat(1001) { batch.add(JSONObject().put("uri", "content://prompt11/$it")) }
        batch.flush()
        assertEquals(5, sizes.size)
        assertTrue(sizes.all { it <= 250 })
    }

    @Test fun cancelledGenerationPreservesCommittedSnapshot() {
        val scope = "prompt11:instrumented"
        val first = JSONArray().put(JSONObject().put("uri", "content://prompt11/committed").put("name", "committed.mp4"))
        val generation1 = NativeIndex.startGeneration(context, NativeIndex.SOURCE_SAF, scope, JSONObject().put("scanId", "g1"))
        NativeIndex.prepare(context, NativeIndex.SOURCE_SAF, scope, first, true, JSONObject().put("status", NativeIndex.STATUS_COMPLETED).put("scanId", "g1"), generation1, NativeIndex.STATUS_COMPLETED)
        val generation2 = NativeIndex.startGeneration(context, NativeIndex.SOURCE_SAF, scope, JSONObject().put("scanId", "g2"))
        NativeIndex.prepareBatch(context, NativeIndex.SOURCE_SAF, scope, JSONArray().put(JSONObject().put("uri", "content://prompt11/new").put("name", "new.mp4")), generation2, "b1", 1)
        NativeIndex.finishGeneration(context, NativeIndex.SOURCE_SAF, scope, generation2, NativeIndex.STATUS_CANCELLED, JSONObject().put("scanId", "g2"))
        assertEquals(1, NativeIndex.cachedDocuments(context, scope).length())
        assertEquals("content://prompt11/committed", NativeIndex.cachedDocuments(context, scope).getJSONObject(0).getString("uri"))
    }
}
