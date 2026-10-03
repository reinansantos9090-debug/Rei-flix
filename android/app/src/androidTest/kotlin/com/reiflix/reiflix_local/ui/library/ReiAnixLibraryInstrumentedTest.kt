package com.reiflix.reiflix_local.ui.library

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.reiflix.reiflix_local.ui.ReiAnixComposeRoot
import com.reiflix.reiflix_local.ui.model.ReiAnixAnimeUiModel
import com.reiflix.reiflix_local.ui.model.ReiAnixArtworkUiModel
import com.reiflix.reiflix_local.ui.model.ReiAnixEpisodeUiModel
import com.reiflix.reiflix_local.ui.model.ReiAnixGenreUiModel
import com.reiflix.reiflix_local.ui.model.ReiAnixLibraryLoadStatus
import com.reiflix.reiflix_local.ui.model.ReiAnixLibraryUiState
import com.reiflix.reiflix_local.ui.model.ReiAnixLocalMediaUiModel
import com.reiflix.reiflix_local.ui.model.ReiAnixMediaAvailability
import com.reiflix.reiflix_local.ui.model.ReiAnixMediaKind
import com.reiflix.reiflix_local.ui.model.ReiAnixMetadataAvailability
import com.reiflix.reiflix_local.ui.model.ReiAnixSeasonUiModel
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ReiAnixLibraryInstrumentedTest {

    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun loadingStateShowsLibraryAndScannerProgress() {
        composeRule.setContent {
            ReiAnixComposeRoot {
                ReiAnixLibraryScreen(
                    state = ReiAnixLibraryUiState(
                        status = ReiAnixLibraryLoadStatus.LOADING,
                        scanInProgress = true,
                        scanState = "SCANNING",
                    ),
                    filters = ReiAnixLibraryFilters(),
                    visibleAnimes = emptyList(),
                    genres = emptyList(),
                    onQueryChange = {},
                    onGenreSelected = {},
                    onToggleFavorites = {},
                    onToggleWatching = {},
                    onToggleCompleted = {},
                    onClearFilters = {},
                    onRefresh = {},
                    onOpenDetails = {},
                )
            }
        }

        composeRule.onNodeWithText("Biblioteca").assertIsDisplayed()
        composeRule.onNodeWithText("Carregando enquanto a biblioteca é atualizada…").assertIsDisplayed()
    }

    @Test
    fun readyCardsShowRealTitleEpisodeCountAndGenre() {
        composeRule.setContent {
            ReiAnixComposeRoot {
                ReiAnixLibraryScreen(
                    state = readyState(),
                    filters = ReiAnixLibraryFilters(),
                    visibleAnimes = listOf(anime(7L, "Example Anime")),
                    genres = listOf(ReiAnixGenreUiModel("action", "Action")),
                    onQueryChange = {},
                    onGenreSelected = {},
                    onToggleFavorites = {},
                    onToggleWatching = {},
                    onToggleCompleted = {},
                    onClearFilters = {},
                    onRefresh = {},
                    onOpenDetails = {},
                )
            }
        }

        composeRule.onNodeWithText("Example Anime").assertIsDisplayed()
        composeRule.onNodeWithText("1 episódio").assertIsDisplayed()
        composeRule.onNodeWithText("Action").assertIsDisplayed()
    }

    @Test
    fun clickingCardEmitsCanonicalAnimeId() {
        var selectedId = -1L
        composeRule.setContent {
            ReiAnixComposeRoot {
                ReiAnixLibraryScreen(
                    state = readyState(),
                    filters = ReiAnixLibraryFilters(),
                    visibleAnimes = listOf(anime(42L, "Clickable")),
                    genres = emptyList(),
                    onQueryChange = {},
                    onGenreSelected = {},
                    onToggleFavorites = {},
                    onToggleWatching = {},
                    onToggleCompleted = {},
                    onClearFilters = {},
                    onRefresh = {},
                    onOpenDetails = { selectedId = it },
                )
            }
        }

        composeRule.onNodeWithText("Clickable").performClick()
        assertEquals(42L, selectedId)
    }

    @Test
    fun missingArtworkShowsExplicitPlaceholder() {
        composeRule.setContent {
            ReiAnixComposeRoot {
                ReiAnixLibraryScreen(
                    state = readyState(),
                    filters = ReiAnixLibraryFilters(),
                    visibleAnimes = listOf(anime(7L, "No Artwork", artwork = null)),
                    genres = emptyList(),
                    onQueryChange = {},
                    onGenreSelected = {},
                    onToggleFavorites = {},
                    onToggleWatching = {},
                    onToggleCompleted = {},
                    onClearFilters = {},
                    onRefresh = {},
                    onOpenDetails = {},
                )
            }
        }

        composeRule.onNodeWithText("Sem arte").assertIsDisplayed()
    }

    @Test
    fun filteredEmptyStateHasRecoveryAction() {
        var cleared = 0
        composeRule.setContent {
            ReiAnixComposeRoot {
                ReiAnixLibraryScreen(
                    state = readyState(),
                    filters = ReiAnixLibraryFilters(query = "does-not-exist"),
                    visibleAnimes = emptyList(),
                    genres = emptyList(),
                    onQueryChange = {},
                    onGenreSelected = {},
                    onToggleFavorites = {},
                    onToggleWatching = {},
                    onToggleCompleted = {},
                    onClearFilters = { cleared++ },
                    onRefresh = {},
                    onOpenDetails = {},
                )
            }
        }

        composeRule.onNodeWithText("Nenhum resultado").assertIsDisplayed()
        composeRule.onNodeWithText("Limpar filtros").performClick()
        assertEquals(1, cleared)
    }

    @Test
    fun errorStateUsesRecoveryAction() {
        var refreshes = 0
        composeRule.setContent {
            ReiAnixComposeRoot {
                ReiAnixLibraryScreen(
                    state = ReiAnixLibraryUiState(
                        status = ReiAnixLibraryLoadStatus.ERROR,
                        error = "Falha real",
                    ),
                    filters = ReiAnixLibraryFilters(),
                    visibleAnimes = emptyList(),
                    genres = emptyList(),
                    onQueryChange = {},
                    onGenreSelected = {},
                    onToggleFavorites = {},
                    onToggleWatching = {},
                    onToggleCompleted = {},
                    onClearFilters = {},
                    onRefresh = { refreshes++ },
                    onOpenDetails = {},
                )
            }
        }

        composeRule.onNodeWithText("Falha real").assertIsDisplayed()
        composeRule.onNodeWithText("Tentar novamente").performClick()
        assertEquals(1, refreshes)
    }

    private fun readyState() = ReiAnixLibraryUiState(
        status = ReiAnixLibraryLoadStatus.READY,
        revision = 1L,
        sourceAvailable = true,
        sourceState = "AVAILABLE",
    )

    private fun anime(
        id: Long,
        title: String,
        artwork: ReiAnixArtworkUiModel? = ReiAnixArtworkUiModel(null, null),
    ) = ReiAnixAnimeUiModel(
        id = id,
        title = title,
        year = 2026,
        genres = listOf(ReiAnixGenreUiModel("action", "Action")),
        favorite = false,
        mediaKind = ReiAnixMediaKind.SERIES,
        artwork = artwork,
        metadataAvailability = ReiAnixMetadataAvailability.UNRESOLVED,
        seasons = listOf(
            ReiAnixSeasonUiModel(
                animeId = id,
                number = 1,
                title = "Season 1",
                episodes = listOf(
                    ReiAnixEpisodeUiModel(
                        id = id * 10 + 1,
                        animeId = id,
                        seasonNumber = 1,
                        number = 1.0,
                        title = "Episode 1",
                        fileName = "episode.mkv",
                        media = ReiAnixLocalMediaUiModel(
                            reference = "content://example/$id",
                            uri = "content://example/$id",
                            path = null,
                            mediaIdentity = "identity-$id",
                            sourceAvailabilityState = "available",
                            availability = ReiAnixMediaAvailability.AVAILABLE,
                        ),
                        progressSeconds = null,
                        durationSeconds = 100.0,
                        watched = false,
                        consumptionState = null,
                        artwork = null,
                    ),
                ),
            ),
        ),
        specials = emptyList(),
        mediaFiles = emptyList(),
        playbackTargetEpisodeId = null,
    )
}
