package com.reiflix.reiflix_local.ui.library

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.reiflix.reiflix_local.ui.ReiAnixComposeRoot
import com.reiflix.reiflix_local.ui.navigation.ReiAnixNavigationHost
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ReiAnixLibraryNavigationInstrumentedTest {

    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun defaultNavigationHostOpensTheRealLibraryRoute() {
        composeRule.setContent {
            ReiAnixComposeRoot {
                ReiAnixNavigationHost()
            }
        }

        composeRule.onNodeWithText("Biblioteca", useUnmergedTree = true).performClick()
        composeRule.waitForIdle()

        composeRule.onNodeWithText("Seu conteúdo local").assertIsDisplayed()
    }
}
