package com.reiflix.reiflix_local.ui

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AssistChip
import androidx.compose.material3.AssistChipDefaults
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.painter.Painter
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.reiflix.reiflix_local.ui.theme.ReiAnixTokens

@Composable
fun ReiAnixCard(
    modifier: Modifier = Modifier,
    content: @Composable ColumnScope.() -> Unit,
) {
    Card(
        modifier = modifier.heightIn(min = ReiAnixTokens.Dimensions.cardMinHeight),
        shape = MaterialTheme.shapes.medium,
        colors = CardDefaults.cardColors(
            containerColor = ReiAnixTokens.Colors.surface,
        ),
        elevation = CardDefaults.cardElevation(
            defaultElevation = ReiAnixTokens.Elevation.card,
        ),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(ReiAnixTokens.Spacing.lg),
            content = content,
        )
    }
}

@Composable
fun ReiAnixPrimaryButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
) {
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.heightIn(min = ReiAnixTokens.Dimensions.buttonMinHeight),
        shape = MaterialTheme.shapes.small,
        colors = ButtonDefaults.buttonColors(
            containerColor = ReiAnixTokens.Colors.primary,
            contentColor = ReiAnixTokens.Colors.onPrimary,
        ),
    ) {
        Text(
            text = text,
            style = MaterialTheme.typography.labelLarge,
            maxLines = 1,
            overflow = TextOverflow.EllIPSIS,
        )
    }
}

@Composable
fun ReiAnixSecondaryButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
) {
    OutlinedButton(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.heightIn(min = ReiAnixTokens.Dimensions.buttonMinHeight),
        shape = MaterialTheme.shapes.small,
        colors = ButtonDefaults.outlinedButtonColors(
            contentColor = ReiAnixTokens.Colors.text,
        ),
        border = androidx.compose.foundation.BorderStroke(
            width = 1.dp,
            color = ReiAnixTokens.Colors.border,
        ),
    ) {
        Text(
            text = text,
            style = MaterialTheme.typography.labelLarge,
            maxLines = 1,
            overflow = TextOverflow.EllIPSIS,
        )
    }
}

@Composable
fun ReiAnixChip(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
) {
    AssistChip(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.heightIn(min = ReiAnixTokens.Dimensions.chipMinHeight),
        label = {
            Text(
                text = text,
                style = MaterialTheme.typography.labelMedium,
                maxLines = 1,
                overflow = TextOverflow.EllIPSIS,
            )
        },
        shape = ReiAnixTokens.Shapes.chip,
        colors = AssistChipDefaults.assistChipColors(
            containerColor = ReiAnixTokens.Colors.surfaceVariant,
            labelColor = ReiAnixTokens.Colors.text,
            disabledContainerColor = ReiAnixTokens.Colors.surfaceVariant.copy(alpha = 0.45f),
            disabledLabelColor = ReiAnixTokens.Colors.textMuted,
        ),
        border = AssistChipDefaults.assistChipBorder(
            enabled = enabled,
            borderColor = ReiAnixTokens.Colors.border,
            disabledBorderColor = ReiAnixTokens.Colors.divider,
        ),
    )
}

@Composable
fun ReiAnixSectionTitle(
    title: String,
    modifier: Modifier = Modifier,
    subtitle: String? = null,
) {
    Column(
        modifier = modifier.fillMaxWidth(),
    ) {
        Text(
            text = title,
            style = MaterialTheme.typography.titleLarge,
            color = ReiAnixTokens.Colors.text,
            maxLines = 1,
            overflow = TextOverflow.EllIPSIS,
        )
        if (!subtitle.isNullOrBlank()) {
            Text(
                text = subtitle,
                style = MaterialTheme.typography.bodyMedium,
                color = ReiAnixTokens.Colors.textMuted,
                modifier = Modifier.padding(top = ReiAnixTokens.Spacing.xs),
                maxLines = 2,
                overflow = TextOverflow.EllIPSIS,
            )
        }
    }
}

@Composable
fun ReiAnixArtwork(
    painter: Painter?,
    contentDescription: String?,
    modifier: Modifier = Modifier,
    contentScale: ContentScale = ContentScale.Crop,
) {
    val shape = MaterialTheme.shapes.small
    Box(
        modifier = modifier
            .aspectRatio(0.7f)
            .clip(shape)
            .background(ReiAnixTokens.Colors.surfaceVariant),
        contentAlignment = Alignment.Center,
    ) {
        if (painter != null) {
            Image(
                painter = painter,
                contentDescription = contentDescription,
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(shape),
                contentScale = contentScale,
            )
        } else {
            Text(
                text = "Sem arte",
                style = MaterialTheme.typography.labelMedium,
                color = ReiAnixTokens.Colors.textMuted,
            )
        }
    }
}

@Composable
fun ReiAnixProgressIndicator(
    progress: Float,
    modifier: Modifier = Modifier,
    visible: Boolean = true,
) {
    if (!visible) {
        return
    }
    val clampedProgress = progress.coerceIn(0f, 1f)
    LinearProgressIndicator(
        progress = { clampedProgress },
        modifier = modifier
            .fillMaxWidth()
            .heightIn(min = ReiAnixTokens.Dimensions.progressHeight),
        color = ReiAnixTokens.Colors.primary,
        trackColor = ReiAnixTokens.Colors.surfaceVariant,
    )
}

@Composable
fun ReiAnixScreen(
    modifier: Modifier = Modifier,
    content: @Composable ColumnScope.() -> Unit,
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = ReiAnixTokens.Dimensions.screenHorizontalPadding),
        content = content,
    )
}
