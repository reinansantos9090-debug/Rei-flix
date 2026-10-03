package com.reiflix.reiflix_local.ui.search

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
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