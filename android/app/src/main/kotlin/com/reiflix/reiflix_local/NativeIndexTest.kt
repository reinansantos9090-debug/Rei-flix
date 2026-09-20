package com.reiflix.reiflix_local

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class NativeIndexTest {
    @Test fun identityUsesVolumeAndRelativePath(){
        val a=JSONObject().put("uri","content://media/1").put("name","same.mkv").put("volumeId","external_primary").put("relativePath","A/same.mkv")
        val b=JSONObject().put("uri","content://media/2").put("name","same.mkv").put("volumeId","external_primary").put("relativePath","B/same.mkv")
        assertTrue(NativeIndex.stableIdentity(a,NativeIndex.SOURCE_MEDIASTORE)!=NativeIndex.stableIdentity(b,NativeIndex.SOURCE_MEDIASTORE))
    }
    @Test fun crossSourceIdentityConverges(){
        val a=JSONObject().put("uri","content://media/1").put("volumeId","external_primary").put("relativePath","Shows/a.mkv")
        val b=JSONObject().put("uri","file:///storage/emulated/0/Shows/a.mkv").put("volumeId","external_primary").put("relativePath","Shows/a.mkv")
        assertEquals(NativeIndex.stableIdentity(a,NativeIndex.SOURCE_MEDIASTORE),NativeIndex.stableIdentity(b,NativeIndex.SOURCE_BROAD))
    }
    @Test fun partialScanKeepsCommittedSnapshot(){
        val c=ApplicationProvider.getApplicationContext<Context>();val scope="native-index-test"
        val first=NativeIndex.prepare(c,NativeIndex.SOURCE_BROAD,scope,JSONArray().put(JSONObject().put("uri","file:///one").put("name","one.mkv").put("relativePath","one.mkv")),true)
        val second=NativeIndex.prepare(c,NativeIndex.SOURCE_BROAD,scope,JSONArray(),false)
        assertEquals(1,NativeIndex.cachedDocuments(c,scope).length());assertTrue(second.generation>first.generation)
    }
}
