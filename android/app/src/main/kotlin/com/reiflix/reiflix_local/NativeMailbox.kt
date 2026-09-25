package com.reiflix.reiflix_local

import android.content.Context
import android.util.Log
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.util.UUID

/** Crash-safe, atomic queue between the native Android host and embedded Python. */
object NativeMailbox {
    private const val TAG = "[REIFLIX][ANDROID]"
    private const val QUEUE = "reiflix-native-events"
    private const val PREFIX = "event-"
    private const val EVENT_VERSION = 2

    private fun eventType(event: JSONObject): String {
        val type = event.optString("type")
        val payload = event.optJSONObject("payload")
        return when {
            type in setOf("mediastore_permission_request","broad_storage_permission_request","saf_permission_request") ->
                "permission_requested"
            type == "saf_cancelled" -> "permission_cancelled"
            type == "saf_permission" ->
                if (payload?.optBoolean("granted", false) == true) "saf_granted" else "saf_revoked"
            type == "broad_storage_permission" ->
                if (payload?.optBoolean("granted", false) == true) "broad_granted" else "broad_denied"
            type == "mediastore_permission" || type == "broad_storage_status" -> "permission_changed"
            type in setOf("saf_scan_progress","mediastore_scan_progress","broad_storage_scan_progress") &&
                payload?.optString("phase") == "started" -> "scan_started"
            type == "saf_scan" -> when (payload?.optString("status")) {
                "REVOKED" -> "saf_revoked"
                "UNAVAILABLE" -> "saf_unavailable"
                "CANCELLED" -> "scan_cancelled"
                "PARTIAL" -> "scan_partial"
                "FAILED" -> "scan_failed"
                else -> "scan_completed"
            }
            type in setOf("mediastore_scan","broad_storage_scan") -> when (payload?.optString("status") ?: payload?.optString("generationStatus")) {
                "cancelled","CANCELLED" -> "scan_cancelled"
                "partial","PARTIAL" -> "scan_partial"
                "failed","FAILED" -> "scan_failed"
                else -> "scan_completed"
            }
            type == "scan_cancelled" -> "scan_cancelled"
            type in setOf("saf_error","mediastore_error","broad_storage_error") ->
                when (payload?.optString("status")) {
                    "REVOKED" -> "saf_revoked"
                    "UNAVAILABLE" -> "saf_unavailable"
                    "PARTIAL" -> "scan_partial"
                    "CANCELLED" -> "scan_cancelled"
                    else -> if (payload?.has("scanId") == true) "scan_failed" else "permission_failed"
                }
            else -> type.ifBlank { "unknown" }
        }
    }

    @Synchronized
    fun writeOrThrow(context: Context, event: JSONObject) {
        check(write(context, event)) { "Could not publish native event to NativeMailbox" }
    }

    @Synchronized
    fun write(context: Context, event: JSONObject): Boolean {
        var temporary: File?=null
        try{
            val dataDirectory = File(context.filesDir, "data")
            check(dataDirectory.isDirectory||dataDirectory.mkdirs()){"Could not create Flet application data directory"}
            val queue = File(dataDirectory, QUEUE)
            check(queue.isDirectory||queue.mkdirs()){"Could not create native event queue directory"}
            val id=UUID.randomUUID().toString()
            val target = File(queue, "$PREFIX$id.json")
            val temp = File(queue, "$PREFIX$id.json.tmp")
            temporary = temp
            val now=System.currentTimeMillis()
            val payload=JSONObject(event.toString())
                .put("eventId",id)
                .put("eventVersion",EVENT_VERSION)
                .put("eventType", eventType(event))
                .put("createdAt",now)
                .put("timestamp",now)
            val nested = payload.optJSONObject("payload")
            fun promote(name: String, vararg aliases: String) {
                if (payload.has(name) || nested == null) return
                for (alias in aliases) {
                    if (nested.has(alias)) {
                        payload.put(name, nested.get(alias))
                        return
                    }
                }
            }
            val requestId=payload.optString("requestId").ifBlank{
                nested?.optString("requestId").orEmpty()
            }.trim()
            if(requestId.isNotEmpty())payload.put("requestId",requestId)
            promote("scanId", "scanId")
            promote("source", "source")
            promote("scope", "scope", "scopeRef", "scopeKind")
            promote("volumeId", "volumeId", "volumeName")
            promote("state", "state", "status", "generationStatus")
            promote("counts", "counts", "stats")
            promote("errors", "errors")
            promote("generationId", "generationId")
            promote("batchId", "batchId")
            promote("batchNumber", "batchNumber")
            promote("batchSize", "batchSize")
            promote("processed", "processed")
            promote("discovered", "discovered")
            promote("inserted", "inserted", "new")
            promote("updated", "updated", "changed")
            promote("unchanged", "unchanged")
            promote("duplicates", "duplicates")
            promote("removed", "removed")
            promote("elapsedMs", "elapsedMs", "elapsed_ms")
            FileOutputStream(temp).use { stream ->
                stream.write(payload.toString().toByteArray(Charsets.UTF_8))
                stream.fd.sync()
            }
            try {
                Files.move(
                    temp.toPath(),
                    target.toPath(),
                    StandardCopyOption.ATOMIC_MOVE,
                    StandardCopyOption.REPLACE_EXISTING,
                )
            } catch (_: java.nio.file.AtomicMoveNotSupportedException) {
                Files.move(
                    temp.toPath(),
                    target.toPath(),
                    StandardCopyOption.REPLACE_EXISTING,
                )
            }
            Log.i(TAG,"Native event queued: type=${event.optString("type")} eventType=${payload.optString("eventType")} requestId=${requestId.ifEmpty{"-"}}")
        }catch(exception:Exception){
            temporary?.delete()
            Log.e(TAG,"Unable to queue native event",exception)
            return false
        }
        return true
    }
}
