package com.reiflix.reiflix_local

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Test

class NativeIndexTest {
    @Test
    fun stableIdentity_convergesMediaStoreAndBroadOnSamePhysicalFile() {
        val media = JSONObject().put("uri", "content://media/external_primary/1").put("volumeId", "external_primary").put("relativePath", "Shows/a.mkv").put("name", "a.mkv")
        val broad = JSONObject().put("uri", "file:///storage/emulated/0/Shows/a.mkv").put("volumeId", "external_primary").put("relativePath", "Shows/a.mkv").put("name", "a.mkv")
        assertEquals(NativeIndex.stableIdentity(media, NativeIndex.SOURCE_MEDIASTORE), NativeIndex.stableIdentity(broad, NativeIndex.SOURCE_BROAD))
    }

    @Test
    fun stableIdentity_doesNotUseDisplayNameAlone() {
        val a = JSONObject().put("uri", "content://media/1").put("volumeId", "external_primary").put("relativePath", "A/a.mkv").put("name", "a.mkv")
        val b = JSONObject().put("uri", "content://media/2").put("volumeId", "external_primary").put("relativePath", "B/a.mkv").put("name", "a.mkv")
        assertNotEquals(NativeIndex.stableIdentity(a, NativeIndex.SOURCE_MEDIASTORE), NativeIndex.stableIdentity(b, NativeIndex.SOURCE_MEDIASTORE))
    }
}
