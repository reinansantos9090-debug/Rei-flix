package com.reiflix.reiflix_local

import android.content.Context
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/** Small, token-free bridge between the native Android host and the embedded Python app. */
object NativeMailbox {
    private const val TAG = "[REIFLIX][ANDROID]"
    private const val FILE = "reiflix-native-events.json"
    fun write(context: Context, event: JSONObject) {
        val target = File(context.filesDir, FILE)
        val list = try { JSONArray(target.readText()) } catch (_: Exception) { JSONArray() }
        list.put(event.put("createdAt", System.currentTimeMillis()))
        // Publish a complete JSON document. The Python bridge consumes this
        // file by renaming it, so it must never observe a partially written
        // event queue.
        val temporary = File(context.filesDir, "$FILE.tmp")
        temporary.writeText(list.toString())
        if (!temporary.renameTo(target)) {
            temporary.copyTo(target, overwrite = true)
            temporary.delete()
        }
        Log.i(TAG, "Native event queued: ${event.optString("type")}")
    }
}
