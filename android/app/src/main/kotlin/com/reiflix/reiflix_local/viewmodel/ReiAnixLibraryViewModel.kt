package com.reiflix.reiflix_local.viewmodel

import android.content.Context
import androidx.annotation.Keep
import com.reiflix.reiflix_local.data.library.ReiAnixLibraryRepository
import com.reiflix.reiflix_local.ui.model.ReiAnixLibraryUiState
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

@Keep
class ReiAnixLibraryViewModel(context: Context) :
    ReiAnixViewModel<ReiAnixLibraryUiState>() {

    private val repository = ReiAnixLibraryRepository(context)
    override val uiState: StateFlow<ReiAnixLibraryUiState> = repository.state.asStateFlow()

    fun refresh() = repository.refresh()

    fun toggleFavorite(animeId: Long) = repository.toggleFavorite(animeId)

    fun setEpisodeWatched(episodeId: Long, watched: Boolean) =
        repository.setEpisodeWatched(episodeId, watched)

    fun openEpisode(episodeId: Long) = repository.openEpisode(episodeId)

    override fun onCleared() {
        repository.close()
        super.onCleared()
    }
}
