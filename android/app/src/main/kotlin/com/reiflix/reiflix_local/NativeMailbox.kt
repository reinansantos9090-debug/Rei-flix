package com.reiflix.reiflix_local

import android.content.Context
import android.util.Log
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
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
    fun write(context: Context, event: JSONObject) {
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
            val requestId=payload.optString("requestId").ifBlank{
                payload.optJSONObject("payload")?.optString("requestId").orEmpty()
            }.trim()
            if(requestId.isNotEmpty())payload.put("requestId",requestId)
            FileOutputStream(temp).use { stream ->
                stream.write(payload.toString().toByteArray(Charsets.UTF_8))
                stream.fd.sync()
            }
            check(temp.renameTo(target)){"Could not publish native event"}
            Log.i(TAG,"Native event queued: type=${event.optString("type")} eventType=${payload.optString("eventType")} requestId=${requestId.ifEmpty{"-"}}")
        }catch(exception:Exception){
            temporary?.delete()
            Log.e(TAG,"Unable to queue native event",exception)
        }
    }
}
