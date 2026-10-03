package com.reiflix.reiflix_local.ui.model

/**
 * Immutable presentation models for the existing local library projection.
 *
 * These types intentionally contain only data the Compose UI needs. They are
 * not persistence entities and never become a second source of truth.
 */

enum class ReiAnixMediaKind {
    SERIES,
    MOVIE,
    UNKNOWN,
}

enum class ReiAnixConsumptionState {
    UNWATCHED,
    IN_PROGRESS,
    COMPLETED,
    WATCHED,
    UNKNOWN,
}

enum class ReiAnixMediaAvailability {
    AVAILABLE,
    MISSING,
    SCOPE_UNAVAILABLE,
    VOLUME_UNAVAILABLE,
    UNKNOWN,
}

enum class ReiAnixMetadataAvailability {
    AVAILABLE,
    STALE,
    MANUAL,
    AMBIGUOUS,
    UNRESOLVED,
    ERROR,
    UNKNOWN,
}

data class ReiAnixGenreUiModel(
    val id: String?,
    val name: String,
)

data class ReiAnixArtworkUiModel(
    val localPath: String?,
    val externalUrl: String?,
) {
    val isAvailable: Boolean
        get() = !localPath.isNullOrBlank() || !externalUrl.isNullOrBlank()
}

data class ReiAnixLocalMediaUiModel(
    /** The original local reference exactly as supplied by the source projection. */
    val reference: String?,
    /** Derived only when the original reference is a content URI. */
    val uri: String?,
    /** Derived only when the original reference is a filesystem path. */
    val path: String?,
    /** Persisted/stable media identity from the source, when available. */
    val mediaIdentity: String?,
    /** Exact source availability_state, retained so unknown values are not discarded. */
    val sourceAvailabilityState: String?,
    val availability: ReiAnixMediaAvailability,
)

data class ReiAnixEpisodeUiModel(
    val id: Long,
    val animeId: Long,
    val seasonNumber: Int?,
    val number: Double?,
    val title: String?,
    val fileName: String,
    val media: ReiAnixLocalMediaUiModel,
    val progressSeconds: Double?,
    val durationSeconds: Double?,
    val watched: Boolean?,
    val consumptionState: ReiAnixConsumptionState?,
    val artwork: ReiAnixArtworkUiModel?,
) {
    val isCompleted: Boolean
        get() = consumptionState == ReiAnixConsumptionState.COMPLETED ||
            consumptionState == ReiAnixConsumptionState.WATCHED

    val displayTitle: String
        get() = title?.takeIf { it.isNotBlank() } ?: fileName
}

data class ReiAnixContinueWatchingUiModel(
    val episodeId: Long,
    val animeId: Long,
    val animeTitle: String,
    val seasonNumber: Int?,
    val number: Double?,
    val title: String?,
    val fileName: String,
    val progressSeconds: Double?,
    val durationSeconds: Double?,
    val artwork: ReiAnixArtworkUiModel?,
) {
    val stableKey: String
        get() = "episode:" + episodeId

    val displayTitle: String
        get() = title?.takeIf { it.isNotBlank() } ?: fileName
}

data class ReiAnixSeasonUiModel(
    /** Seasons have no independent SQLite ID in the current source projection. */
    val animeId: Long,
    val number: Int?,
    val title: String,
    val episodes: List<ReiAnixEpisodeUiModel>,
) {
    /** Stable UI key derived from existing identity without persisting a new ID. */
    val stableKey: String
        get() = "anime:" + animeId + ":season:" + (number ?: "special")
}

data class ReiAnixAnimeUiModel(
    val id: Long,
    val title: String,
    val year: Int?,
    val genres: List<ReiAnixGenreUiModel>,
    val favorite: Boolean,
    val mediaKind: ReiAnixMediaKind,
    val artwork: ReiAnixArtworkUiModel?,
    val metadataAvailability: ReiAnixMetadataAvailability,
    val seasons: List<ReiAnixSeasonUiModel>,
    val specials: List<ReiAnixEpisodeUiModel>,
    val mediaFiles: List<ReiAnixEpisodeUiModel>,
    val playbackTargetEpisodeId: Long?,
) {
    val stableKey: String
        get() = "anime:" + id
}
