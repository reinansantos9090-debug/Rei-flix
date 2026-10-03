package com.reiflix.reiflix_local.ui.theme

import androidx.annotation.Keep
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable

@Keep
/**
 * Shared Compose theme boundary for the native UI migration.
 *
 * Prompt 01 intentionally defines no screen, navigation graph, or domain logic.
 */
@Composable
fun ReiAnixComposeTheme(
    content: @Composable () -> Unit,
) {
    MaterialTheme(content = content)
}
