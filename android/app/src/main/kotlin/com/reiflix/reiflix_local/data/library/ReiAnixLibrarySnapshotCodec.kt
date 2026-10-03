package com.reiflix.reiflix_local.data.library

import com.reiflix.reiflix_local.ui.mapper.LibraryUiMappers
import com.reiflix.reiflix_local.ui.model.ReiAnixAnimeUiModel
import com.reiflix.reiflix_local.ui.model.ReiAnixLibraryLoadStatus
import com.reiflix.reiflix_local.ui.model.ReiAnixLibraryUiState
import org.json.JSONArray
import org.json.JSONObject

internal object ReiAnixLibrarySnapshotCodec {

    fun decode(raw: String, previousRevision: Long = 0L): ReiAnixLibraryUiState {
        val root = JSONObject(raw)
        val schemaVersion = root.optInt("schemaVersion", 0)
        require(schemaVersion == 1) { "Unsupported Compose library snapshot schema: $schemaVersion" }

        val revision = root.optLong("revision", 0L)
        require(revision >= previousRevision) {
            "Stale Compose library snapshot revision=$revision previous=$previousRevision"
        }

        val sourceState = root.optString("sourceState").trim().ifEmpty { "UNKNOWN" }
        val sourceAvailable = root.optBoolean("sourceAvailable", sourceState == "AVAILABLE")
        val scanState = root.optString("scanState").trim().uppercase().ifEmpty { "IDLE" }
        val scanInProgress = root.optBoolean(
            "scanInProgress",
            scanState in setOf("CHECKING", "SCANNING", "WAITING_FOR_MEDIASTORE"),
        )
        val snapshotStatus = root.optString("status").trim().uppercase()
        val error = root.optString("error").trim().takeIf { it.isNotEmpty() && it != "null" }

        val rawAnimes = root.optJSONArray("animes") ?: JSONArray()
        val animes = buildList(rawAnimes.length()) {
            for (index in 0 until rawAnimes.length()) {
                val item = rawAnimes.optJSONObject(index)
                    ?: error("Malformed anime at snapshot index=$index")
                @Suppress("UNCHECKED_CAST")
                add(LibraryUiMappers.anime(item.toMap()))
            }
        }

        val rawContinueWatching = root.optJSONArray("continue_watching") ?: JSONArray()
        val continueWatching = buildList(rawContinueWatching.length()) {
            for (index in 0 until rawContinueWatching.length()) {
                val item = rawContinueWatching.optJSONObject(index)
                    ?: error("Malformed continue-watching item at snapshot index=$index")
                @Suppress("UNCHECKED_CAST")
                add(LibraryUiMappers.continueWatching(item.toMap()))
            }
        }

        val status = when {
            snapshotStatus == "ERROR" -> ReiAnixLibraryLoadStatus.ERROR
            sourceState == "UNAVAILABLE" -> ReiAnixLibraryLoadStatus.SOURCE_UNAVAILABLE
            animes.isNotEmpty() -> ReiAnixLibraryLoadStatus.READY
            else -> ReiAnixLibraryLoadStatus.EMPTY
        }

        return ReiAnixLibraryUiState(
            status = status,
            revision = revision,
            animes = animes,
            continueWatching = continueWatching,
            sourceAvailable = sourceAvailable,
            sourceState = sourceState,
            scanInProgress = scanInProgress,
            scanState = scanState,
            error = error,
        )
    }

    fun decodeCommandResult(raw: String): CommandResult {
        val root = JSONObject(raw)
        require(root.optInt("schemaVersion", 0) == 1) {
            "Unsupported Compose command-result schema"
        }
        return CommandResult(
            requestId = root.optString("requestId").trim().takeIf { it.isNotEmpty() },
            action = root.optString("action").trim().takeIf { it.isNotEmpty() },
            status = root.optString("status").trim().uppercase().ifEmpty { "UNKNOWN" },
            error = root.optString("error").trim().takeIf { it.isNotEmpty() && it != "null" },
        )
    }

    data class CommandResult(
        val requestId: String?,
        val action: String?,
        val status: String,
        val error: String?,
    )
}

private fun JSONObject.toMap(): Map<String, Any?> =
    keys().asSequence().associateWith { key -> jsonValueToKotlin(opt(key)) }

private fun JSONArray.toListValue(): List<Any?> =
    buildList(length()) {
        for (index in 0 until length()) {
            add(jsonValueToKotlin(opt(index)))
        }
    }

private fun jsonValueToKotlin(value: Any?): Any? = when (value) {
    null, JSONObject.NULL -> null
    is JSONObject -> value.toMap()
    is JSONArray -> value.toListValue()
    else -> value
}
