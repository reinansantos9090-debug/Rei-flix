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
        target.writeText(list.toString())
        Log.i(TAG, "Native event queued: ${event.optString("type")}")
    }
}
