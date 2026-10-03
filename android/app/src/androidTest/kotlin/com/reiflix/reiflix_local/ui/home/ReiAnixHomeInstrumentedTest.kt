package com.reiflix.reiflix_local.ui.home

import androidx.compose.ui.test.assertDoesNotExist
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.swipeLeft
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.reiflix.reiflix_local.ui.ReiAnixComposeRoot
import com.reiflix.reiflix_local.ui.model.ReiAnixAnimeUiModel
import com.reiflix.reiflix_local.ui.model.ReiAnixArtworkUiModel
import com.reiflix.reiflix_local.ui.model.ReiAnixLibraryLoadStatus
import com.reiflix.reiflix_local.ui.model.ReiAnixLibraryUiState
import com.reiflix.reiflix_local.ui.model.ReiAnixMediaKind
import com.reiflix.reiflix_local.ui.model.ReiAnixMetadataAvailability
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ReiAnixHomeInstrumentedTest {

    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun loadingStateIsRendered() {
        composeRule.setContent {
            ReiAnixComposeRoot {
                ReiAnixHomeScreen(
                    state = ReiAnixLibraryUiState(status = ReiAnixLibraryLoadStatus.LOADING),
                    onSearch = {},
                    onOpenDetails = {},
                    onWatch = { _, _ -> },
                    onToggleFavorite = {},
                    onRefresh = {},
                )
            }
        }
        composeRule.onNodeWithText("ReiAnix").assertIsDisplayed()
        composeRule.onNodeWithContentDescription("Pesquisar na biblioteca").assertIsDisplayed()
    }

    @Test
    fun emptyLibraryShowsExplicitEmptyState() {
        composeRule.setContent {
            ReiAnixComposeRoot {
                ReiAnixHomeScreen(
                    state = ReiAnixLibraryUiState(
                        status = ReiAnixLibraryLoadStatus.EMPTY,
                    ),
                    onSearch = {},
                    onOpenDetails = {},
                    onWatch = { _, _ -> },
                    onToggleFavorite = {},
                    onRefresh = {},
                )
            }
        }
        composeRule.onNodeWithText("Biblioteca vazia").assertIsDisplayed()
    }

    @Test
    fun readySingleAnimeDoesNotCreateEmptyHorizontalSection() {
        composeRule.setContent {
            ReiAnixComposeRoot {
                ReiAnixHomeScreen(
                    state = readyState(listOf(anime(7L, "Example Anime", favorite = false))),
                    onSearch = {},
                    onOpenDetails = {},
                    onWatch = { _, _ -> },
                    onToggleFavorite = {},
                    onRefresh = {},
                )
            }
        }
        composeRule.onNodeWithText("Example Anime").assertIsDisplayed()
        composeRule.onNodeWithText("MINHA LISTA").assertDoesNotExist()
        composeRule.onNodeWithText("CONTINUAR ASSISTINDO").assertDoesNotExist()
    }

    @Test
    fun detailsAndWatchCallbacksReceiveCanonicalIds() {
        var selectedAnimeId = -1L
        var selectedEpisodeId = -1L
        var selectedEpisodeAnimeId = -1L
        composeRule.setContent {
            ReiAnixComposeRoot {
                ReiAnixHomeScreen(
                    state = readyState(listOf(anime(7L, "Example Anime", favorite = false, playbackEpisodeId = 71L))),
                    onSearch = {},
                    onOpenDetails = { selectedAnimeId = it },
                    onWatch = { episodeId, animeId ->
                        selectedEpisodeId = episodeId
                        selectedEpisodeAnimeId = animeId
                    },
                    onToggleFavorite = {},
                    onRefresh = {},
                )
            }
        }

        composeRule.onNodeWithText("Detalhes").performClick()
        composeRule.onNodeWithText("Assistir").performClick()

        assertEquals(7L, selectedAnimeId)
        assertEquals(71L, selectedEpisodeId)
        assertEquals(7L, selectedEpisodeAnimeId)
    }

    @Test
    fun favoriteSectionUsesStableItemsAndCanScrollHorizontally() {
        val animes = (1L..8L).map { id ->
            anime(id, "Anime $id", favorite = true)
        }
        composeRule.setContent {
            ReiAnixComposeRoot {
                ReiAnixHomeScreen(
                    state = readyState(animes),
                    onSearch = {},
                    onOpenDetails = {},
                    onWatch = { _, _ -> },
                    onToggleFavorite = {},
                    onRefresh = {},
                )
            }
        }

        composeRule.onNodeWithContentDescription("Home Minha Lista")
            .performTouchInput { swipeLeft() }
        composeRule.onNodeWithText("Anime 8").assertIsDisplayed()
    }

    private fun readyState(animes: List<ReiAnixAnimeUiModel>) =
        ReiAnixLibraryUiState(
            status = ReiAnixLibraryLoadStatus.READY,
            revision = 1L,
            animes = animes,
            sourceAvailable = true,
            sourceState = "AVAILABLE",
        )

    private fun anime(
        id: Long,
        title: String,
        favorite: Boolean,
        playbackEpisodeId: Long? = null,
    ) = ReiAnixAnimeUiModel(
        id = id,
        title = title,
        year = 2026,
        genres = emptyList(),
        favorite = favorite,
        mediaKind = ReiAnixMediaKind.SERIES,
        artwork = ReiAnixArtworkUiModel("/missing/poster.jpg", null),
        metadataAvailability = ReiAnixMetadataAvailability.UNRESOLVED,
        seasons = emptyList(),
        specials = emptyList(),
        mediaFiles = emptyList(),
        playbackTargetEpisodeId = playbackEpisodeId,
    )
}
