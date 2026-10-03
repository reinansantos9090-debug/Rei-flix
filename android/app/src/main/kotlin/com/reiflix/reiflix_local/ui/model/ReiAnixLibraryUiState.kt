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
    val continueWatching: List<ReiAnixContinueWatchingUiModel> = emptyList(),
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


@Keep
data class ReiAnixHomeLibraryUiState(
    val status: ReiAnixLibraryLoadStatus = ReiAnixLibraryLoadStatus.LOADING,
    val animes: List<ReiAnixHomeAnimeUiModel> = emptyList(),
    val sourceAvailable: Boolean = false,
    val sourceState: String = "UNKNOWN",
    val error: String? = null,
) {
    companion object {
        fun from(state: ReiAnixLibraryUiState): ReiAnixHomeLibraryUiState =
            ReiAnixHomeLibraryUiState(
                status = state.status,
                animes = state.animes.map { anime ->
                    ReiAnixHomeAnimeUiModel(
                        id = anime.id,
                        title = anime.title,
                        year = anime.year,
                        genres = anime.genres,
                        favorite = anime.favorite,
                        mediaKind = anime.mediaKind,
                        artwork = anime.artwork,
                        playbackTargetEpisodeId = anime.playbackTargetEpisodeId,
                        availableContentCount = anime.seasons.sumOf { season ->
                            season.episodes.count { episode ->
                                episode.media.availability != ReiAnixMediaAvailability.MISSING
                            }
                        } +
                            anime.specials.count { episode ->
                                episode.media.availability != ReiAnixMediaAvailability.MISSING
                            } +
                            anime.mediaFiles.count { episode ->
                                episode.media.availability != ReiAnixMediaAvailability.MISSING
                            },
                    )
                },
                sourceAvailable = state.sourceAvailable,
                sourceState = state.sourceState,
                error = state.error,
            )
    }
}
