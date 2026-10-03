package com.reiflix.reiflix_local.ui.details

import androidx.compose.ui.test.assertDoesNotExist
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import com.reiflix.reiflix_local.ui.ReiAnixComposeRoot
import com.reiflix.reiflix_local.ui.model.ReiAnixAnimeUiModel
import com.reiflix.reiflix_local.ui.model.ReiAnixArtworkUiModel
import com.reiflix.reiflix_local.ui.model.ReiAnixConsumptionState
import com.reiflix.reiflix_local.ui.model.ReiAnixDetailsAnimeUiModel
import com.reiflix.reiflix_local.ui.model.ReiAnixDetailsLoadStatus
import com.reiflix.reiflix_local.ui.model.ReiAnixDetailsUiState
import com.reiflix.reiflix_local.ui.model.ReiAnixGenreUiModel
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

class ReiAnixDetailsInstrumentedTest {
    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun readyHeroShowsRealMetadataAndDispatchesExistingActions() {
        var watchedEpisodeId: Long? = null
        var favoriteAnimeId: Long? = null
        var backCount = 0

        composeRule.setContent {
            ReiAnixComposeRoot {
                ReiAnixDetailsScreen(
                    state = ReiAnixDetailsUiState(
                        status = ReiAnixDetailsLoadStatus.READY,
                        sourceAvailable = true,
                        sourceState = "AVAILABLE",
                        anime = ReiAnixDetailsAnimeUiModel(
                            id = 42L,
                            title = "ReiAnix Test",
                            year = 2026,
                            genres = listOf(
                                ReiAnixGenreUiModel("action", "Action"),
                                ReiAnixGenreUiModel("drama", "Drama"),
                            ),
                            score = 86.0,
                            favorite = true,
                            artwork = ReiAnixArtworkUiModel(null, null),
                            episodeCount = 12,
                            playbackTargetEpisodeId = 71L,
                            shouldContinue = true,
                        ),
                    ),
                    onBack = { backCount++ },
                    onRetry = {},
                    onWatch = { watchedEpisodeId = it },
                    onToggleFavorite = { favoriteAnimeId = it },
                )
            }
        }

        composeRule.onNodeWithText("ReiAnix Test").assertIsDisplayed()
        composeRule.onNodeWithText("2026").assertIsDisplayed()
        composeRule.onNodeWithText("Nota 8.6/10").assertIsDisplayed()
        composeRule.onNodeWithText("12 episódios").assertIsDisplayed()
        composeRule.onNodeWithText("Action").assertIsDisplayed()
        composeRule.onNodeWithText("Drama").assertIsDisplayed()
        composeRule.onNodeWithText("Continuar").performClick()
        composeRule.onNodeWithContentDescription("Remover da Minha Lista").performClick()
        composeRule.onNodeWithContentDescription("Voltar").performClick()

        assertEquals(71L, watchedEpisodeId)
        assertEquals(42L, favoriteAnimeId)
        assertEquals(1, backCount)
    }

    @Test
    fun missingOptionalMetadataIsNotInvented() {
        composeRule.setContent {
            ReiAnixComposeRoot {
                ReiAnixDetailsScreen(
                    state = ReiAnixDetailsUiState(
                        status = ReiAnixDetailsLoadStatus.READY,
                        sourceAvailable = true,
                        sourceState = "AVAILABLE",
                        anime = ReiAnixDetailsAnimeUiModel(
                            id = 43L,
                            title = "Local Only",
                            year = null,
                            genres = emptyList(),
                            score = null,
                            favorite = false,
                            artwork = null,
                            episodeCount = null,
                            playbackTargetEpisodeId = null,
                            shouldContinue = false,
                        ),
                    ),
                    onBack = {},
                    onRetry = {},
                    onWatch = {},
                    onToggleFavorite = {},
                )
            }
        }

        composeRule.onNodeWithText("Local Only").assertIsDisplayed()
        composeRule.onNodeWithText("Assistir").assertDoesNotExist()
        composeRule.onNodeWithText("2026").assertDoesNotExist()
        composeRule.onNodeWithText("Nota 8.6/10").assertDoesNotExist()
        composeRule.onNodeWithText("episódios").assertDoesNotExist()
        composeRule.onNodeWithContentDescription("Adicionar à Minha Lista").assertIsDisplayed()
        composeRule.onNodeWithText("Nenhuma mídia local disponível para reprodução.").assertIsDisplayed()
    }
}
