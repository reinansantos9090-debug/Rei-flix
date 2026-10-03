package com.reiflix.reiflix_local.ui.navigation

import androidx.activity.ComponentActivity
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNode
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.assertDoesNotExist
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.performClick
import androidx.navigation.compose.ComposeNavigator
import androidx.navigation.testing.TestNavHostController
import com.reiflix.reiflix_local.ui.ReiAnixComposeRoot
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test

class ReiAnixNavigationInstrumentedTest {
    @get:Rule
    val composeRule = createAndroidComposeRule<ComponentActivity>()

    private lateinit var navController: TestNavHostController

    @Before
    fun setUp() {
        val context = composeRule.activity
        navController = TestNavHostController(context).apply {
            navigatorProvider.addNavigator(ComposeNavigator())
        }

        composeRule.setContent {
            ReiAnixComposeRoot {
                ReiAnixNavigationHost(
                    navController = navController,
                    home = { NavigationTestScreen("Início") },
                    library = { NavigationTestScreen("Biblioteca") },
                    search = { NavigationTestScreen("Buscar") },
                    settings = { NavigationTestScreen("Ajustes") },
                    details = { args ->
                        Column {
                            Text("Details")
                            Text("animeId=" + args.animeId)
                            Text("origin=" + args.origin)
                        }
                    },
                    player = { args ->
                        Column {
                            Text("Player")
                            Text("episodeId=" + args.episodeId)
                            Text("animeId=" + args.animeId)
                            Text("origin=" + args.origin)
                        }
                    },
                )
            }
        }

        composeRule.waitForIdle()
    }

    @Test
    fun topLevelNavigationDoesNotDuplicateAnyDestination() {
        listOf(
            "Início" to ReiAnixRoutes.HOME,
            "Biblioteca" to ReiAnixRoutes.LIBRARY,
            "Buscar" to ReiAnixRoutes.SEARCH,
            "Ajustes" to ReiAnixRoutes.SETTINGS,
        ).forEach { (label, route) ->
            clickTopLevel(label)
            clickTopLevel(label)
            clickTopLevel(label)

            assertEquals(route, navController.currentBackStackEntry?.destination?.route)
            if (route == ReiAnixRoutes.HOME) {
                assertTrue(navController.previousBackStackEntry == null)
            } else {
                assertEquals(
                    ReiAnixRoutes.HOME,
                    navController.previousBackStackEntry?.destination?.route,
                )
            }
        }
    }

    @Test
    fun selectedStateIsExposedForEachTopLevelDestination() {
        listOf("Início", "Biblioteca", "Buscar", "Ajustes").forEach { label ->
            clickTopLevel(label)
            composeRule.onNodeWithText(label).assertIsSelected()
        }
    }

    @Test
    fun bottomNavigationOnlyExistsOnTopLevelDestinations() {
        composeRule.onNodeWithContentDescription(ReiAnixRoutes.BOTTOM_NAV_CONTENT_DESCRIPTION)
            .assertIsDisplayed()

        navController.navigateToDetails("42", ReiAnixRoutes.HOME)
        composeRule.waitForIdle()
        composeRule.onNodeWithContentDescription(ReiAnixRoutes.BOTTOM_NAV_CONTENT_DESCRIPTION)
            .assertDoesNotExist()

        composeRule.activity.onBackPressedDispatcher.onBackPressed()
        composeRule.waitForIdle()
        composeRule.onNodeWithContentDescription(ReiAnixRoutes.BOTTOM_NAV_CONTENT_DESCRIPTION)
            .assertIsDisplayed()

        navController.navigateToDetails("42", ReiAnixRoutes.HOME)
        navController.navigateToPlayer("episode-7", "42", ReiAnixRoutes.DETAILS_ORIGIN)
        composeRule.waitForIdle()
        composeRule.onNodeWithContentDescription(ReiAnixRoutes.BOTTOM_NAV_CONTENT_DESCRIPTION)
            .assertDoesNotExist()
    }

    @Test
    fun tabStateIsRestoredAfterSwitchingTabs()
        clickTopLevel("Biblioteca")
        composeRule.onNodeWithText("Biblioteca counter=0").assertExists()
        composeRule.onNodeWithText("Increment Biblioteca").performClick()
        composeRule.onNodeWithText("Biblioteca counter=1").assertExists()

        clickTopLevel("Início")
        clickTopLevel("Biblioteca")

        composeRule.onNodeWithText("Biblioteca counter=1").assertExists()
    }

    @Test
    fun allTopLevelRoutesAreReachable() {
        val destinations = listOf(
            "Biblioteca" to ReiAnixRoutes.LIBRARY,
            "Buscar" to ReiAnixRoutes.SEARCH,
            "Ajustes" to ReiAnixRoutes.SETTINGS,
            "Início" to ReiAnixRoutes.HOME,
        )

        destinations.forEach { (label, route) ->
            clickTopLevel(label)
            assertEquals(route, navController.currentBackStackEntry?.destination?.route)
        }
    }

    @Test
    fun detailsPreservesOriginAndBackReturnsToSource() {
        navController.navigateToTopLevel(ReiAnixRoutes.SEARCH)
        navController.navigateToDetails("42", ReiAnixRoutes.SEARCH)
        composeRule.waitForIdle()

        composeRule.onNodeWithText("animeId=42").assertExists()
        composeRule.onNodeWithText("origin=" + ReiAnixRoutes.SEARCH).assertExists()
        assertTrue(navController.currentBackStackEntry?.destination?.route == ReiAnixRoutes.DETAILS)
        composeRule.onNodeWithText("Biblioteca").assertDoesNotExist()

        composeRule.activity.onBackPressedDispatcher.onBackPressed()
        composeRule.waitForIdle()

        assertEquals(
            ReiAnixRoutes.SEARCH,
            navController.currentBackStackEntry?.destination?.route,
        )
    }

    @Test
    fun detailsFromLibraryPreservesOriginAndBackReturnsToLibrary() {
        navController.navigateToTopLevel(ReiAnixRoutes.LIBRARY)
        navController.navigateToDetails("anime-library-42", ReiAnixRoutes.LIBRARY)
        composeRule.waitForIdle()

        composeRule.onNodeWithText("animeId=anime-library-42").assertExists()
        composeRule.onNodeWithText("origin=" + ReiAnixRoutes.LIBRARY).assertExists()
        composeRule.onNodeWithContentDescription(ReiAnixRoutes.BOTTOM_NAV_CONTENT_DESCRIPTION)
            .assertDoesNotExist()

        composeRule.activity.onBackPressedDispatcher.onBackPressed()
        composeRule.waitForIdle()

        assertEquals(
            ReiAnixRoutes.LIBRARY,
            navController.currentBackStackEntry?.destination?.route,
        )
        composeRule.onNodeWithText("Biblioteca").assertIsSelected()
    }

    @Test
    fun reopeningSameDetailsDoesNotCreateDuplicateEntry() {
        navController.navigateToDetails("42", ReiAnixRoutes.HOME)
        navController.navigateToDetails("42", ReiAnixRoutes.HOME)
        composeRule.waitForIdle()

        assertEquals(
            ReiAnixRoutes.HOME,
            navController.previousBackStackEntry?.destination?.route,
        )

        composeRule.activity.onBackPressedDispatcher.onBackPressed()
        composeRule.waitForIdle()

        assertEquals(
            ReiAnixRoutes.HOME,
            navController.currentBackStackEntry?.destination?.route,
        )
    }

    @Test
    fun playerBackReturnsToDetailsWithStableIds() {
        navController.navigateToTopLevel(ReiAnixRoutes.LIBRARY)
        navController.navigateToDetails("42", ReiAnixRoutes.LIBRARY)
        navController.navigateToPlayer("episode-7", "42", ReiAnixRoutes.DETAILS_ORIGIN)
        composeRule.waitForIdle()

        composeRule.onNodeWithText("episodeId=episode-7").assertExists()
        composeRule.onNodeWithText("animeId=42").assertExists()
        composeRule.onNodeWithText("Biblioteca").assertDoesNotExist()

        composeRule.activity.onBackPressedDispatcher.onBackPressed()
        composeRule.waitForIdle()

        assertEquals(
            ReiAnixRoutes.DETAILS,
            navController.currentBackStackEntry?.destination?.route,
        )
        composeRule.onNodeWithText("animeId=42").assertExists()
        composeRule.onNodeWithText("origin=" + ReiAnixRoutes.LIBRARY).assertExists()

        composeRule.activity.onBackPressedDispatcher.onBackPressed()
        composeRule.waitForIdle()

        assertEquals(
            ReiAnixRoutes.LIBRARY,
            navController.currentBackStackEntry?.destination?.route,
        )
    }

    @Test
    fun encodedArgumentsRoundTripThroughNavBackStackEntry() {
        val animeId = "anime / 07 § especial"
        val episodeId = "episode/ 07?& especial"
        val origin = "details/search source"

        navController.navigateToDetails(animeId, origin)
        composeRule.waitForIdle()

        assertEquals(
            animeId,
            navController.currentBackStackEntry?.arguments?.getString(ReiAnixRoutes.ARG_ANIME_ID),
        )
        assertEquals(
            origin,
            navController.currentBackStackEntry?.arguments?.getString(ReiAnixRoutes.ARG_ORIGIN),
        )

        navController.navigateToPlayer(episodeId, animeId, origin)
        composeRule.waitForIdle()

        assertEquals(
            episodeId,
            navController.currentBackStackEntry?.arguments?.getString(ReiAnixRoutes.ARG_EPISODE_ID),
        )
        assertEquals(
            animeId,
            navController.currentBackStackEntry?.arguments?.getString(ReiAnixRoutes.ARG_ANIME_ID),
        )
        assertEquals(
            origin,
            navController.currentBackStackEntry?.arguments?.getString(ReiAnixRoutes.ARG_ORIGIN),
        )
    }

    @Test
    fun blankNavigationArgumentsAreRejected() {
        org.junit.Assert.assertThrows(IllegalArgumentException::class.java) {
            ReiAnixRoutes.details("  ", ReiAnixRoutes.HOME)
        }
        org.junit.Assert.assertThrows(IllegalArgumentException::class.java) {
            ReiAnixRoutes.player("episode-7", "  ", ReiAnixRoutes.DETAILS_ORIGIN)
        }
        org.junit.Assert.assertThrows(IllegalArgumentException::class.java) {
            ReiAnixRoutes.player("  ", "anime-7", ReiAnixRoutes.DETAILS_ORIGIN)
        }
    }

    @Test
    fun routeBuildersUseStableEncodedArguments() {
        assertEquals(
            "details/anime%2F42?origin=library",
            ReiAnixRoutes.details("anime/42", ReiAnixRoutes.LIBRARY),
        )
        assertEquals(
            "player/episode%2F7?animeId=anime%2F42&origin=details%2Fanime%2F42",
            ReiAnixRoutes.player(
                episodeId = "episode/7",
                animeId = "anime/42",
                origin = "details/anime/42",
            ),
        )
    }

    private fun clickTopLevel(label: String) {
        composeRule.onNode(
            hasText(label) and hasClickAction(),
            useUnmergedTree = true,
        ).performClick()
        composeRule.waitForIdle()
    }

    @Composable
    private fun NavigationTestScreen(label: String) {
        var counter by rememberSaveable { mutableIntStateOf(0) }
        Column {
            Text(label + " counter=" + counter)
            Button(onClick = { counter += 1 }) {
                Text("Increment " + label)
            }
        }
    }
}
