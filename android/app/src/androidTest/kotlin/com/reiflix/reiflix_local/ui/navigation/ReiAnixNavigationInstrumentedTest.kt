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
    fun topLevelNavigationDoesNotDuplicateAndBackReturnsToHome() {
        clickTopLevel("Biblioteca")
        clickTopLevel("Biblioteca")

        assertEquals(
            ReiAnixRoutes.LIBRARY,
            navController.currentBackStackEntry?.destination?.route,
        )

        composeRule.activity.onBackPressedDispatcher.onBackPressed()
        composeRule.waitForIdle()

        assertEquals(
            ReiAnixRoutes.HOME,
            navController.currentBackStackEntry?.destination?.route,
        )
    }

    @Test
    fun tabStateIsRestoredAfterSwitchingTabs() {
        clickTopLevel("Biblioteca")
        composeRule.onNodeWithText("Biblioteca counter=0").assertExists()
        composeRule.onNodeWithText("Increment Biblioteca").performClick()
        composeRule.onNodeWithText("Biblioteca counter=1").assertExists()

        clickTopLevel("Início")
        clickTopLevel("Biblioteca")

        composeRule.onNodeWithText("Biblioteca counter=1").assertExists()
    }

    @Test
    fun detailsPreservesOriginAndBackReturnsToSource() {
        navController.navigateToDetails("42", ReiAnixRoutes.SEARCH)
        composeRule.waitForIdle()

        composeRule.onNodeWithText("animeId=42").assertExists()
        composeRule.onNodeWithText("origin=" + ReiAnixRoutes.SEARCH).assertExists()
        assertTrue(navController.currentBackStackEntry?.destination?.route == ReiAnixRoutes.DETAILS)

        composeRule.activity.onBackPressedDispatcher.onBackPressed()
        composeRule.waitForIdle()

        assertEquals(
            ReiAnixRoutes.HOME,
            navController.currentBackStackEntry?.destination?.route,
        )
    }

    @Test
    fun reopeningSameDetailsDoesNotCreateDuplicateEntry() {
        navController.navigateToDetails("42", ReiAnixRoutes.HOME)
        navController.navigateToDetails("42", ReiAnixRoutes.HOME)
        composeRule.waitForIdle()

        composeRule.activity.onBackPressedDispatcher.onBackPressed()
        composeRule.waitForIdle()

        assertEquals(
            ReiAnixRoutes.HOME,
            navController.currentBackStackEntry?.destination?.route,
        )
    }

    @Test
    fun playerBackReturnsToDetailsWithStableIds() {
        navController.navigateToDetails("42", ReiAnixRoutes.LIBRARY)
        navController.navigateToPlayer("episode-7", "42", ReiAnixRoutes.DETAILS)
        composeRule.waitForIdle()

        composeRule.onNodeWithText("episodeId=episode-7").assertExists()
        composeRule.onNodeWithText("animeId=42").assertExists()

        composeRule.activity.onBackPressedDispatcher.onBackPressed()
        composeRule.waitForIdle()

        assertEquals(
            ReiAnixRoutes.DETAILS,
            navController.currentBackStackEntry?.destination?.route,
        )
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
