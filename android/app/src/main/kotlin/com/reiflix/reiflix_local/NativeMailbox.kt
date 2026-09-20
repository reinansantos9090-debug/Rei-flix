package com.reiflix.reiflix_local

import android.content.Context
import android.util.Log
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.util.UUID

/** Crash-safe, lock-free queue between the native Android host and the embedded Python app. */
object NativeMailbox {
    private const val TAG = "[REIFLIX][ANDROID]"
    private const val QUEUE = "reiflix-native-events"
    private const val PREFIX = "event-"

    @Synchronized
    fun write(context: Context, event: JSONObject) {
        try {
            val dataDirectory = File(context.filesDir, "data")
            check(dataDirectory.isDirectory || dataDirectory.mkdirs()) {
                "Could not create Flet application data directory"
            }
            val queue = File(dataDirectory, QUEUE)
            check(queue.isDirectory || queue.mkdirs()) {
                "Could not create native event queue directory"
            }
            val id = UUID.randomUUID().toString()
            val target = File(queue, "$PREFIX$id.json")
            val temporary = File(queue, "$PREFIX$id.json.tmp")
            val payload = JSONObject(event.toString())
                .put("eventId", id)
                .put("createdAt", System.currentTimeMillis())
            FileOutputStream(temporary).use { stream ->
                stream.write(payload.toString().toByteArray(Charsets.UTF_8))
                stream.fd.sync()
            }
            check(temporary.renameTo(target)) { "Could not publish native event" }
            Log.i(TAG, "Native event queued: ${event.optString("type")}")
        } catch (exception: Exception) {
            temporary.delete()
            Log.e(TAG, "Unable to queue native event", exception)
        }
    }
}
