package com.reiflix.reiflix_local.ui.search

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import com.reiflix.reiflix_local.ui.model.ReiAnixAnimeUiModel
import com.reiflix.reiflix_local.ui.model.ReiAnixLibraryLoadStatus
import com.reiflix.reiflix_local.ui.model.ReiAnixLibraryUiState
import com.reiflix.reiflix_local.ui.model.ReiAnixMediaKind
import com.reiflix.reiflix_local.ui.model.ReiAnixMetadataAvailability
import org.junit.Rule
import org.junit.Test

class ReiAnixSearchInstrumentedTest {
    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun emptyQueryDoesNotRenderSyntheticHistory() {
        composeRule.setContent {
            ReiAnixSearchScreen(
                libraryState = readyState(anime(1L, "Local Anime")),
                query = "",
                results = emptyList(),
                showBackButton = false,
            )
        }

        composeRule.onNodeWithText("Pesquise na biblioteca").assertIsDisplayed()
        composeRule.onNodeWithText("1 título local disponível.").assertIsDisplayed()
    }

    @Test
    fun loadingStateIsExplicit() {
        composeRule.setContent {
            ReiAnixSearchScreen(
                libraryState = ReiAnixLibraryUiState(
                    status = ReiAnixLibraryLoadStatus.LOADING,
                    scanInProgress = true,
                    scanState = "SCANNING",
                ),
                query = "",
                results = emptyList(),
                showBackButton = false,
            )
        }

        composeRule.onNodeWithText("Carregando biblioteca enquanto a varredura continua…").assertIsDisplayed()
    }

    @Test
    fun errorStateIsExplicit() {
        composeRule.setContent {
            ReiAnixSearchScreen(
                libraryState = ReiAnixLibraryUiState(
                    status = ReiAnixLibraryLoadStatus.ERROR,
                    error = "Falha local",
                ),
                query = "Local",
                results = emptyList(),
                showBackButton = false,
            )
        }

        composeRule.onNodeWithText("Não foi possível pesquisar").assertIsDisplayed()
        composeRule.onNodeWithText("Falha local").assertIsDisplayed()
    }

    @Test
    fun resultOpensByStableAnimeId() {
        var openedId: Long? = null

        composeRule.setContent {
            ReiAnixSearchScreen(
                libraryState = readyState(anime(42L, "Local Anime")),
                query = "Local",
                results = listOf(anime(42L, "Local Anime")),
                showBackButton = false,
                onOpenDetails = { openedId = it },
            )
        }

        composeRule.onNodeWithContentDescription("Abrir Local Anime").performClick()
        assert(openedId == 42L)
    }

    @Test
    fun noResultsStateIsExplicit() {
        composeRule.setContent {
            ReiAnixSearchScreen(
                libraryState = readyState(anime(2L, "Local Anime")),
                query = "Missing",
                results = emptyList(),
                showBackButton = false,
            )
        }

        composeRule.onNodeWithText("Nenhum resultado").assertIsDisplayed()
        composeRule.onNodeWithText("Nenhum conteúdo local corresponde a \"Missing\".").assertIsDisplayed()
    }

    private fun readyState(anime: ReiAnixAnimeUiModel) = ReiAnixLibraryUiState(
        status = ReiAnixLibraryLoadStatus.READY,
        revision = 1L,
        animes = listOf(anime),
        sourceAvailable = true,
        sourceState = "AVAILABLE",
    )

    private fun anime(id: Long, title: String) = ReiAnixAnimeUiModel(
        id = id,
        title = title,
        year = 2026,
        genres = emptyList(),
        favorite = false,
        mediaKind = ReiAnixMediaKind.SERIES,
        artwork = null,
        metadataAvailability = ReiAnixMetadataAvailability.UNRESOLVED,
        seasons = emptyList(),
        specials = emptyList(),
        mediaFiles = emptyList(),
    )
}