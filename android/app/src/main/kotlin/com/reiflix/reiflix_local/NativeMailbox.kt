package com.reiflix.reiflix_local

import android.content.Context
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.nio.channels.FileChannel
import java.nio.file.StandardOpenOption

/** Small, token-free bridge between the native Android host and the embedded Python app. */
object NativeMailbox {
    private const val TAG = "[REIFLIX][ANDROID]"
    private const val FILE = "reiflix-native-events.json"

    @Synchronized
    fun write(context: Context, event: JSONObject) {
        // Flet exports FLET_APP_STORAGE_DATA as the "data" child of its
        // application-support directory. On Android that support directory is
        // filesDir, so writing at filesDir itself made native events invisible
        // to the embedded Python process (which polls filesDir/data).
        val dataDirectory = File(context.filesDir, "data")
        check(dataDirectory.isDirectory || dataDirectory.mkdirs()) {
            "Could not create Flet application data directory"
        }
        val lock = File(dataDirectory, "$FILE.lock")
        FileChannel.open(lock.toPath(), StandardOpenOption.CREATE, StandardOpenOption.WRITE).use { channel ->
            channel.lock().use {
                writeLocked(dataDirectory, event)
            }
        }
    }

    private fun writeLocked(dataDirectory: File, event: JSONObject) {
        val target = File(dataDirectory, FILE)
        // Python drains by renaming the queue. If it wins that race, start a
        // fresh queue rather than treating an in-flight consumed file as an error.
        val list = try { JSONArray(target.readText()) } catch (_: Exception) { JSONArray() }
        list.put(event.put("createdAt", System.currentTimeMillis()))
        val temporary = File(dataDirectory, "$FILE.tmp")
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
