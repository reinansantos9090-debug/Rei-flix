package com.reiflix.reiflix_local

import android.content.Context
import android.os.Build
import android.os.storage.StorageManager
import android.provider.MediaStore
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.security.MessageDigest

/**
 * Durable native physical index. This is not a catalogue/database: only physical
 * discovery snapshots, generations, volume state and source metadata live here.
 */
object NativeIndex {
    const val SOURCE_MEDIASTORE = "mediastore"
    const val SOURCE_SAF = "saf"
    const val SOURCE_BROAD = "broad_storage"
    private const val VERSION = 2
    private const val FILE_NAME = "reiflix-native-index.json"
    private const val DATA_DIR = "data"

    data class NativePrepared(
        val documents: JSONArray, val generation: Long, val newItems: Int,
        val changedItems: Int, val unchangedItems: Int, val duplicates: Int, val removedItems: Int,
        val status: String = STATUS_COMPLETED,
        val scopeKey: String = "",
    )

    const val STATUS_STARTED = "STARTED"
    const val STATUS_RUNNING = "RUNNING"
    const val STATUS_COMPLETED = "COMPLETED"
    const val STATUS_PARTIAL = "PARTIAL"
    const val STATUS_CANCELLED = "CANCELLED"
    const val STATUS_FAILED = "FAILED"

    private fun file(context: Context) = File(File(context.filesDir, DATA_DIR), FILE_NAME)

    private fun read(context: Context): JSONObject {
        val target = file(context)
        if (!target.isFile) return JSONObject().put("version", VERSION)
        return runCatching { JSONObject(target.readText(Charsets.UTF_8)) }.getOrElse {
            JSONObject().put("version", VERSION)
        }.also {
            val storedVersion = it.optInt("version", 1)
            if (storedVersion < VERSION) {
                it.put("version", VERSION)
            } else if (storedVersion > VERSION) {
                it.remove("scopes"); it.remove("generationCounters"); it.remove("volumes"); it.put("version", VERSION)
            }
        }
    }

    private fun write(context: Context, state: JSONObject) {
        val dir = File(context.filesDir, DATA_DIR)
        check(dir.isDirectory || dir.mkdirs()) { "Could not create native index directory" }
        val temp = File(dir, FILE_NAME + ".tmp")
        FileOutputStream(temp).use {
            it.write(state.toString().toByteArray(Charsets.UTF_8))
            it.fd.sync()
        }
        check(temp.renameTo(file(context))) { "Could not publish native index snapshot" }
    }

    private fun sha256(value: String): String =
        MessageDigest.getInstance("SHA-256").digest(value.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it) }

    private fun cleanPath(value: String) = value.trim().replace('\\', '/').trim('/')

    fun stableIdentity(document: JSONObject, source: String): String {
        val explicit = document.optString("stableId").trim()
        if (explicit.isNotEmpty()) return explicit
        val volume = document.optString("volumeId").trim()
        val relative = cleanPath(document.optString("relativePath"))
        val tree = document.optString("treeUri").trim()
        val documentId = document.optString("documentId").trim()
        if (source == SOURCE_SAF && documentId.isNotEmpty()) {
            if (volume.isNotEmpty() && documentId.contains(":")) {
                val documentPath = cleanPath(documentId.substringAfter(":"))
                if (documentPath.isNotEmpty()) return "shared:" + volume + ":" + documentPath
            }
            if (tree.isNotEmpty()) return "saf:" + tree + ":" + documentId
        }
        if (volume.isNotEmpty() && relative.isNotEmpty()) return "shared:" + volume + ":" + relative
        val uri = document.optString("uri").trim()
        return if (uri.isNotEmpty()) "uri:" + uri else "opaque:" + sha256(document.toString())
    }

    private fun fingerprint(document: JSONObject, stableId: String): String =
        sha256(
            stableId + "|" + document.optString("name") + "|" + document.optString("size") + "|" +
                document.optString("modifiedAt") + "|" + document.optString("mediaId") + "|" + document.optString("mimeType") + "|" +
                document.optString("relativePath")
        )

    private fun scopes(state: JSONObject) =
        state.optJSONObject("scopes") ?: JSONObject().also { state.put("scopes", it) }

    private fun counters(state: JSONObject) =
        state.optJSONObject("generationCounters") ?: JSONObject().also { state.put("generationCounters", it) }

    private fun nextGeneration(state: JSONObject, scopeKey: String): Long {
        val map = counters(state)
        val next = map.optLong(scopeKey, 0L) + 1L
        map.put(scopeKey, next)
        return next
    }

    fun startGeneration(context: Context, source: String, scopeKey: String, metadata: JSONObject = JSONObject()): Long = synchronized(this) {
        val state = read(context)
        val scopeMap = scopes(state)
        val scope = scopeMap.optJSONObject(scopeKey) ?: JSONObject().also { scopeMap.put(scopeKey, it) }
        val generation = nextGeneration(state, scopeKey)
        val now = System.currentTimeMillis()
        scope.put("generation", generation)
            .put("status", STATUS_STARTED)
            .put("source", source)
            .put("scopeKey", scopeKey)
            .put("startedAt", now)
            .put("finishedAt", JSONObject.NULL)
            .put("metadata", JSONObject(metadata.toString()))
        write(context, state)
        generation
    }

    fun markGenerationRunning(context: Context, source: String, scopeKey: String, generation: Long) = synchronized(this) {
        val state = read(context)
        val scopeMap = scopes(state)
        val scope = scopeMap.optJSONObject(scopeKey) ?: JSONObject().also { scopeMap.put(scopeKey, it) }
        if (scope.optLong("generation", 0L) == generation) {
            scope.put("status", STATUS_RUNNING).put("source", source).put("scopeKey", scopeKey)
            write(context, state)
        }
    }

    fun prepare(context: Context, source: String, scopeKey: String, input: JSONArray, complete: Boolean,
                metadata: JSONObject = JSONObject(), generation: Long = 0L, status: String = ""): NativePrepared = synchronized(this) {
        val state = read(context)
        val scopeMap = scopes(state)
        val scope = scopeMap.optJSONObject(scopeKey) ?: JSONObject().also { scopeMap.put(scopeKey, it) }
        val previous = scope.optJSONObject("items") ?: JSONObject()
        val effectiveGeneration = if (generation > 0L) generation else nextGeneration(state, scopeKey)
        val output = JSONArray()
        val seen = HashSet<String>()
        var newItems = 0; var changedItems = 0; var unchangedItems = 0; var duplicates = 0

        for (i in 0 until input.length()) {
            val raw = input.optJSONObject(i) ?: continue
            val document = JSONObject(raw.toString())
            val stableId = stableIdentity(document, source)
            if (!seen.add(stableId)) { duplicates++; continue }
            val fp = fingerprint(document, stableId)
            val before = previous.optJSONObject(stableId)
            val change = when {
                before == null -> "NEW"
                before.optString("fingerprint") == fp -> "UNCHANGED"
                else -> "CHANGED"
            }
            when (change) { "NEW" -> newItems++; "CHANGED" -> changedItems++; else -> unchangedItems++ }
            document.put("stableId", stableId).put("nativeFingerprint", fp)
                .put("nativeChange", change).put("scanGeneration", effectiveGeneration)
                .put("source", source).put("scopeKey", scopeKey)
            output.put(document)
        }

        val oldKeys = previous.keys().asSequence().toSet()
        val removedItems = oldKeys.count { !seen.contains(it) }
        val normalizedStatus = when {
            complete -> STATUS_COMPLETED
            status.equals(STATUS_CANCELLED, ignoreCase = true) || status.equals("cancelled", ignoreCase = true) -> STATUS_CANCELLED
            status.equals(STATUS_FAILED, ignoreCase = true) || status.equals("failed", ignoreCase = true) -> STATUS_FAILED
            else -> STATUS_PARTIAL
        }
        val now = System.currentTimeMillis()
        scope.put("generation", effectiveGeneration)
            .put("status", normalizedStatus)
            .put("source", source)
            .put("scopeKey", scopeKey)
            .put("finishedAt", now)
            .put("metadata", JSONObject(metadata.toString()))
            .put("counts", JSONObject()
                .put("new", newItems)
                .put("changed", changedItems)
                .put("unchanged", unchangedItems)
                .put("duplicates", duplicates)
                .put("removed", removedItems)
                .put("observed", output.length()))
        if (complete) {
            val items = JSONObject()
            for (i in 0 until output.length()) {
                val doc = output.getJSONObject(i)
                items.put(doc.getString("stableId"), JSONObject(doc.toString()).put("fingerprint", doc.getString("nativeFingerprint")))
            }
            scope.put("updatedAt", now).put("items", items)
        }
        write(context, state)
        NativePrepared(output, effectiveGeneration, newItems, changedItems, unchangedItems, duplicates, removedItems, normalizedStatus, scopeKey)
    }

    fun failGeneration(context: Context, source: String, scopeKey: String, generation: Long, error: String, metadata: JSONObject = JSONObject()) = synchronized(this) {
        val state = read(context)
        val scopeMap = scopes(state)
        val scope = scopeMap.optJSONObject(scopeKey) ?: JSONObject().also { scopeMap.put(scopeKey, it) }
        scope.put("generation", generation)
            .put("status", STATUS_FAILED)
            .put("source", source)
            .put("scopeKey", scopeKey)
            .put("finishedAt", System.currentTimeMillis())
            .put("error", error)
            .put("metadata", JSONObject(metadata.toString()))
        write(context, state)
    }

    fun cachedDocuments(context: Context, scopeKey: String): JSONArray = synchronized(this) {
        val items = scopes(read(context)).optJSONObject(scopeKey)?.optJSONObject("items")
            ?: return@synchronized JSONArray()
        val output = JSONArray()
        val keys = items.keys()
        while (keys.hasNext()) {
            val item = items.optJSONObject(keys.next()) ?: continue
            val document = JSONObject(item.toString())
            document.remove("fingerprint")
            output.put(document)
        }
        output
    }

    fun cachedGeneration(context: Context, scopeKey: String): Long = synchronized(this) {
        scopes(read(context)).optJSONObject(scopeKey)?.optLong("generation", 0L) ?: 0L
    }

    fun canReuseMediaStoreVolume(context: Context, volumeName: String, accessLevel: String,
                                 currentVersion: String, currentGeneration: Long): Boolean = synchronized(this) {
        if (Build.VERSION.SDK_INT < 30 || accessLevel != "full" || currentVersion.isBlank() || currentGeneration <= 0L) return@synchronized false
        val scope = scopes(read(context)).optJSONObject("mediastore:" + volumeName) ?: return@synchronized false
        if (scope.optString("status") != STATUS_COMPLETED) return@synchronized false
        val meta = scope.optJSONObject("metadata") ?: return@synchronized false
        meta.optString("mediaStoreVersion") == currentVersion &&
            meta.optLong("mediaStoreGeneration", -1L) == currentGeneration &&
            meta.optString("accessLevel") == "full" && scope.optString("status") == STATUS_COMPLETED
    }

    fun volumeSnapshot(context: Context): JSONArray {
        val output = JSONArray()
        if (Build.VERSION.SDK_INT < 24) return output
        val manager = context.getSystemService(StorageManager::class.java) ?: return output
        manager.storageVolumes.forEach { volume ->
            val mediaStoreName = if (Build.VERSION.SDK_INT >= 30) volume.mediaStoreVolumeName else null
            val uuid = volume.uuid
            val id = when {
                !mediaStoreName.isNullOrBlank() -> mediaStoreName
                !uuid.isNullOrBlank() -> uuid
                volume.isPrimary -> MediaStore.VOLUME_EXTERNAL_PRIMARY
                else -> ""
            }
            if (id.isBlank()) return@forEach
            val volumeState = volume.state ?: "unknown"
            val available = volumeState == "mounted" || volumeState == "mounted_ro"
            val item = JSONObject().put("volumeId", id).put("uuid", uuid ?: "")
                .put("mediaStoreVolumeName", mediaStoreName ?: "")
                .put("primary", volume.isPrimary).put("removable", volume.isRemovable)
                .put("emulated", volume.isEmulated).put("state", volumeState)
                .put("available", available)
                .put("observedAt", System.currentTimeMillis())
            runCatching { volume.directory?.canonicalPath }.getOrNull()?.let { item.put("directory", it) }
            runCatching { item.put("description", volume.getDescription(context)) }
            output.put(item)
        }
        return output
    }

    private fun volumeSemantics(item: JSONObject): String {
        val normalized = JSONObject(item.toString())
        normalized.remove("observedAt")
        normalized.remove("lastObservedAt")
        return normalized.toString()
    }

    fun updateVolumeSnapshot(context: Context, current: JSONArray): JSONObject = synchronized(this) {
        val state = read(context)
        val previous = state.optJSONObject("volumes") ?: JSONObject()
        if (current.length() == 0 && previous.length() > 0) {
            return JSONObject()
                .put("changed", false)
                .put("added", JSONArray())
                .put("removed", JSONArray())
                .put("changedVolumes", JSONArray())
                .put("current", JSONArray())
                .put("observedAt", System.currentTimeMillis())
                .put("observationComplete", false)
        }
        val next = JSONObject()
        val added = JSONArray(); val removed = JSONArray(); val changed = JSONArray(); val seen = HashSet<String>()
        for (i in 0 until current.length()) {
            val item = current.optJSONObject(i) ?: continue
            val id = item.optString("volumeId").trim()
            if (id.isEmpty() || !seen.add(id)) continue
            next.put(id, item)
            val before = previous.optJSONObject(id)
            when {
                before == null -> added.put(item)
                before != null && volumeSemantics(before) != volumeSemantics(item) ->
                    changed.put(JSONObject().put("before", JSONObject(before.toString())).put("after", item))
            }
        }
        val now = System.currentTimeMillis()
        val oldKeys = previous.keys()
        while (oldKeys.hasNext()) {
            val id = oldKeys.next()
            if (!seen.contains(id)) {
                val before = previous.optJSONObject(id)
                val wasAvailable = before?.let {
                    if (it.has("available")) it.optBoolean("available", false)
                    else !it.optString("state").equals("unavailable", ignoreCase = true)
                } ?: true
                val unavailable = if (before != null) JSONObject(before.toString()) else JSONObject().put("volumeId", id)
                unavailable.put("state", "unavailable")
                    .put("available", false)
                    .put("unavailableAt", if (before?.has("unavailableAt") == true) before.optLong("unavailableAt", now) else now)
                    .put("lastObservedAt", now)
                    .put("reason", "volume_removed_from_observation")
                next.put(id, unavailable)
                if (wasAvailable) removed.put(unavailable)
            }
        }
        state.put("volumes", next)
        state.put("volumeSnapshotAt", now)
        write(context, state)
        JSONObject().put("changed", added.length() + removed.length() + changed.length() > 0)
            .put("added", added).put("removed", removed).put("changedVolumes", changed).put("current", current)
            .put("observedAt", now)
            .put("observationComplete", true)
    }
}
