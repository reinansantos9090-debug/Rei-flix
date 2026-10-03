package com.reiflix.reiflix_local.viewmodel

import android.content.Context
import androidx.annotation.Keep
import androidx.lifecycle.viewModelScope
import com.reiflix.reiflix_local.data.library.ReiAnixLibraryRepository
import com.reiflix.reiflix_local.ui.model.ReiAnixLibraryUiState
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import com.reiflix.reiflix_local.ui.model.ReiAnixHomeLibraryUiState
import com.reiflix.reiflix_local.ui.model.ReiAnixContinueWatchingUiModel
@Keep
class ReiAnixLibraryViewModel(context: Context) :
    ReiAnixViewModel<ReiAnixLibraryUiState>() {

    private val repository = ReiAnixLibraryRepository(context)
    override val uiState: StateFlow<ReiAnixLibraryUiState> = repository.state

    /**
     * Home observes only the fields that can affect its persistent catalog sections.
     * Episode-level progress is deliberately excluded so a playback tick cannot
     * invalidate the whole Home tree.
     */
    val homeState: StateFlow<ReiAnixHomeLibraryUiState> = uiState
        .map { state ->
            ReiAnixHomeLibraryUiState.from(state)
        }
        .distinctUntilChanged()
        .stateIn(
            viewModelScope,
            SharingStarted.Eagerly,
            ReiAnixHomeLibraryUiState.from(uiState.value),
        )

    /** The canonical Continue Watching projection; this is the only Home subtree that observes it. */
    val continueWatching: StateFlow<List<ReiAnixContinueWatchingUiModel>> = uiState
        .map { it.continueWatching }
        .distinctUntilChanged()
        .stateIn(
            viewModelScope,
            SharingStarted.Eagerly,
            uiState.value.continueWatching,
        )

    /** Parent Home only needs this flag to add/remove the section item. */
    val hasContinueWatching: StateFlow<Boolean> = continueWatching
        .map { it.isNotEmpty() }
        .distinctUntilChanged()
        .stateIn(
            viewModelScope,
            SharingStarted.Eagerly,
            uiState.value.continueWatching.isNotEmpty(),
        )

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
