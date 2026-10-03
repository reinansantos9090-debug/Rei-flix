package com.reiflix.reiflix_local.ui.library

import com.reiflix.reiflix_local.ui.model.ReiAnixAnimeUiModel

data class ReiAnixLibraryFilters(
    val query: String = "",
    val selectedGenreKey: String? = null,
    val favoritesOnly: Boolean = false,
    val watchingOnly: Boolean = false,
    val completedOnly: Boolean = false,
) {
    val hasAnyFilter: Boolean
        get() = query.isNotBlank() ||
            selectedGenreKey != null ||
            favoritesOnly ||
            watchingOnly ||
            completedOnly
}

internal object ReiAnixLibraryFilterEngine {
    fun filter(
        animes: List<ReiAnixAnimeUiModel>,
        filters: ReiAnixLibraryFilters,
    ): List<ReiAnixAnimeUiModel> {
        val query = filters.query.trim()
        return animes.filter { anime ->
            val matchesQuery = query.isBlank() ||
                anime.title.contains(query, ignoreCase = true) ||
                anime.genres.any { it.name.contains(query, ignoreCase = true) }
            val matchesGenre = filters.selectedGenreKey == null ||
                anime.genres.any { it.stableKey == filters.selectedGenreKey }
            val matchesFavorite = !filters.favoritesOnly || anime.favorite
            val matchesWatching = !filters.watchingOnly || anime.isWatching
            val matchesCompleted = !filters.completedOnly || anime.isCompleted
            matchesQuery && matchesGenre && matchesFavorite && matchesWatching && matchesCompleted
        }
    }
}
