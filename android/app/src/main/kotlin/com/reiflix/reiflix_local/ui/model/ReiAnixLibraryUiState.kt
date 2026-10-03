package com.reiflix.reiflix_local.ui.model

import androidx.annotation.Keep

@Keep
enum class ReiAnixLibraryLoadStatus {
    LOADING,
    READY,
    EMPTY,
    SOURCE_UNAVAILABLE,
    ERROR,
}

@Keep
data class ReiAnixLibraryUiState(
    val status: ReiAnixLibraryLoadStatus = ReiAnixLibraryLoadStatus.LOADING,
    val revision: Long = 0L,
    val animes: List<ReiAnixAnimeUiModel> = emptyList(),
    val sourceAvailable: Boolean = false,
    val sourceState: String = "UNKNOWN",
    val error: String? = null,
    val lastCommandId: String? = null,
    val lastCommandAction: String? = null,
    val lastCommandStatus: String? = null,
    val lastCommandError: String? = null,
) {
    val isEmpty: Boolean
        get() = status == ReiAnixLibraryLoadStatus.EMPTY

    val isAvailable: Boolean
        get() = sourceAvailable && status != ReiAnixLibraryLoadStatus.ERROR
}
