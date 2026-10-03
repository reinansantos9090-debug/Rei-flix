package com.reiflix.reiflix_local.ui.theme

import androidx.annotation.Keep
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable

private val ReiAnixDarkColorScheme = darkColorScheme(
    primary = ReiAnixTokens.Colors.primary,
    onPrimary = ReiAnixTokens.Colors.onPrimary,
    primaryContainer = ReiAnixTokens.Colors.primaryContainer,
    onPrimaryContainer = ReiAnixTokens.Colors.onPrimaryContainer,
    secondary = ReiAnixTokens.Colors.secondary,
    onSecondary = ReiAnixTokens.Colors.onSecondary,
    secondaryContainer = ReiAnixTokens.Colors.secondaryContainer,
    onSecondaryContainer = ReiAnixTokens.Colors.onSecondaryContainer,
    tertiary = ReiAnixTokens.Colors.tertiary,
    onTertiary = ReiAnixTokens.Colors.onTertiary,
    tertiaryContainer = ReiAnixTokens.Colors.tertiaryContainer,
    onTertiaryContainer = ReiAnixTokens.Colors.onTertiaryContainer,
    error = ReiAnixTokens.Colors.error,
    onError = ReiAnixTokens.Colors.onError,
    errorContainer = ReiAnixTokens.Colors.errorContainer,
    onErrorContainer = ReiAnixTokens.Colors.onErrorContainer,
    background = ReiAnixTokens.Colors.background,
    onBackground = ReiAnixTokens.Colors.text,
    surface = ReiAnixTokens.Colors.surface,
    onSurface = ReiAnixTokens.Colors.text,
    surfaceVariant = ReiAnixTokens.Colors.surfaceVariant,
    onSurfaceVariant = ReiAnixTokens.Colors.textMuted,
    outline = ReiAnixTokens.Colors.border,
    outlineVariant = ReiAnixTokens.Colors.divider,
    inverseSurface = ReiAnixTokens.Colors.inverseSurface,
    inverseOnSurface = ReiAnixTokens.Colors.inverseOnSurface,
    inversePrimary = ReiAnixTokens.Colors.inversePrimary,
    scrim = ReiAnixTokens.Colors.overlay,
)

/**
 * Shared Material 3 theme for all future native ReiAnix screens.
 *
 * This step establishes visual tokens only. It does not select a screen,
 * create navigation, or connect to application/domain state.
 */
@Keep
@Composable
fun ReiAnixComposeTheme(
    content: @Composable () -> Unit,
) {
    MaterialTheme(
        colorScheme = ReiAnixDarkColorScheme,
        typography = ReiAnixTokens.typography,
        shapes = ReiAnixTokens.shapes,
        content = content,
    )
}
