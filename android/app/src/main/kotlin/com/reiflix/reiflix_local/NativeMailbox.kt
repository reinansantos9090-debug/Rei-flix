package com.reiflix.reiflix_local

import android.content.Context
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream

/** Small, token-free bridge between the native Android host and the embedded Python app. */
object NativeMailbox {
    private const val TAG = "[REIFLIX][ANDROID]"
    private const val FILE = "reiflix-native-events.json"

    @Synchronized
    fun write(context: Context, event: JSONObject) {
        val target = File(context.filesDir, FILE)
        // Python drains by renaming the queue. If it wins that race, start a
        // fresh queue rather than treating an in-flight consumed file as an error.
        val list = try { JSONArray(target.readText()) } catch (_: Exception) { JSONArray() }
        list.put(event.put("createdAt", System.currentTimeMillis()))
        val temporary = File(context.filesDir, "$FILE.tmp")
        try {
            FileOutputStream(temporary).use { stream ->
                stream.write(list.toString().toByteArray(Charsets.UTF_8))
                stream.fd.sync()
            }
            // renameTo is an atomic same-directory publication on Android's
            // app-private filesystem.  If replacement is unsupported, remove
            // the old complete queue and retry; never copy a partial JSON queue.
            if (!temporary.renameTo(target)) {
                target.delete()
                check(temporary.renameTo(target)) { "Could not publish native event queue" }
            }
            Log.i(TAG, "Native event queued: ${event.optString("type")}")
        } catch (exception: Exception) {
            temporary.delete()
            Log.e(TAG, "Unable to queue native event", exception)
        }
    }
}
