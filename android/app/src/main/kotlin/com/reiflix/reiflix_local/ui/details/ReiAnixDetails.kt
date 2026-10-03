package com.reiflix.reiflix_local.ui.details

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.outlined.StarBorder
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavHostController
import com.reiflix.reiflix_local.ui.ReiAnixPrimaryButton
import com.reiflix.reiflix_local.ui.ReiAnixSecondaryButton
import com.reiflix.reiflix_local.ui.artwork.ReiAnixLocalArtwork
import com.reiflix.reiflix_local.ui.model.ReiAnixDetailsAnimeUiModel
import com.reiflix.reiflix_local.ui.model.ReiAnixDetailsLoadStatus
import com.reiflix.reiflix_local.ui.model.ReiAnixDetailsUiState
import com.reiflix.reiflix_local.ui.model.ReiAnixDetailsUiStateProjection
import com.reiflix.reiflix_local.ui.theme.ReiAnixTokens
import com.reiflix.reiflix_local.viewmodel.ReiAnixLibraryViewModel

@Composable
fun ReiAnixDetailsRoute(
    navController: NavHostController,
    viewModel: ReiAnixLibraryViewModel,
    animeId: String,
    origin: String,
) {
    val canonicalId = animeId.trim().toLongOrNull()

    if (canonicalId == null) {
        ReiAnixDetailsScreen(
            state = ReiAnixDetailsUiStateProjection.invalidAnimeId(),
            onBack = { navController.popBackStack() },
            onRetry = {},
            onWatch = {},
            onToggleFavorite = {},
        )
        return
    }

    val detailsStateFlow = remember(viewModel, canonicalId) {
        viewModel.detailsState(canonicalId)
    }
    val state by detailsStateFlow.collectAsStateWithLifecycle()

    ReiAnixDetailsScreen(
        state = state,
        onBack = { navController.popBackStack() },
        onRetry = viewModel::refresh,
        onWatch = viewModel::openEpisode,
        onToggleFavorite = viewModel::toggleFavorite,
    )
}

@Composable
fun ReiAnixDetailsScreen(
    state: ReiAnixDetailsUiState,
    onBack: () -> Unit,
    onRetry: () -> Unit,
    onWatch: (Long) -> Unit,
    onToggleFavorite: (Long) -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(ReiAnixTokens.Colors.background),
    ) {
        ReiAnixDetailsTopBar(
            favorite = state.anime?.favorite ?: false,
            enabled = state.anime != null,
            onBack = onBack,
            onToggleFavorite = {
                state.anime?.id?.let(onToggleFavorite)
            },
        )

        when (state.status) {
            ReiAnixDetailsLoadStatus.LOADING -> DetailsLoading()

            ReiAnixDetailsLoadStatus.READY -> {
                val anime = state.anime
                if (anime != null) {
                    ReiAnixDetailsReady(
                        anime = anime,
                        onWatch = onWatch,
                    )
                } else {
                    DetailsMessage(
                        title = "Detalhes indisponíveis",
                        message = "Os dados do anime não estão disponíveis.",
                        onRetry = onRetry,
                    )
                }
            }

            ReiAnixDetailsLoadStatus.EMPTY -> DetailsMessage(
                title = "Biblioteca vazia",
                message = "Nenhum anime local está disponível.",
                onRetry = onRetry,
            )

            ReiAnixDetailsLoadStatus.SOURCE_UNAVAILABLE -> DetailsMessage(
                title = "Biblioteca local indisponível",
                message = state.error ?: "A fonte local não está disponível agora.",
                onRetry = onRetry,
            )

            ReiAnixDetailsLoadStatus.NOT_FOUND -> DetailsMessage(
                title = "Anime não encontrado",
                message = state.error ?: "O anime não está presente na biblioteca local.",
                onRetry = onRetry,
            )

            ReiAnixDetailsLoadStatus.ERROR -> DetailsMessage(
                title = "Erro nos detalhes",
                message = state.error ?: "Não foi possível carregar os detalhes.",
                onRetry = onRetry,
            )
        }
    }
}

@Composable
private fun ReiAnixDetailsTopBar(
    favorite: Boolean,
    enabled: Boolean,
    onBack: () -> Unit,
    onToggleFavorite: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(
                horizontal = ReiAnixTokens.Spacing.sm,
                vertical = ReiAnixTokens.Spacing.xs,
            ),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        IconButton(
            onClick = onBack,
            modifier = Modifier.semantics {
                contentDescription = "Voltar"
            },
        ) {
            Icon(
                imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                contentDescription = null,
                tint = ReiAnixTokens.Colors.text,
            )
        }
        Text(
            text = "Detalhes",
            style = MaterialTheme.typography.titleLarge,
            color = ReiAnixTokens.Colors.text,
            modifier = Modifier.weight(1f),
        )
        IconButton(
            enabled = enabled,
            onClick = onToggleFavorite,
            modifier = Modifier.semantics {
                contentDescription = if (favorite) {
                    "Remover da Minha Lista"
                } else {
                    "Adicionar à Minha Lista"
                }
            },
        ) {
            Icon(
                imageVector = if (favorite) Icons.Filled.Star else Icons.Outlined.StarBorder,
                contentDescription = null,
                tint = if (favorite) {
                    ReiAnixTokens.Colors.warning
                } else {
                    ReiAnixTokens.Colors.text,
                },
            )
        }
    }
}

@Composable
private fun ReiAnixDetailsReady(
    anime: ReiAnixDetailsAnimeUiModel,
    onWatch: (Long) -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(bottom = ReiAnixTokens.Spacing.xxxl),
    ) {
        ReiAnixLocalArtwork(
            localPath = anime.artwork?.localPath,
            contentDescription = anime.title,
            modifier = Modifier
                .fillMaxWidth()
                .height(250.dp)
                .padding(horizontal = ReiAnixTokens.Spacing.lg),
            contentScale = ContentScale.Crop,
            placeholder = "Sem capa",
            maxDimensionPx = 1024,
        )

        Column(
            modifier = Modifier.padding(
                horizontal = ReiAnixTokens.Spacing.lg,
                vertical = ReiAnixTokens.Spacing.lg,
            ),
        ) {
            Text(
                text = anime.title,
                style = MaterialTheme.typography.headlineSmall,
                color = ReiAnixTokens.Colors.text,
                fontWeight = FontWeight.Bold,
                maxLines = 3,
                overflow = TextOverflow.Ellipsis,
            )

            val facts = buildList {
                anime.year?.let { add(it.toString()) }
                anime.score?.let { add("Nota " + formatScore(it) + "/10") }
                anime.episodeCount?.let { add(it.toString() + " episódios") }
            }
            if (facts.isNotEmpty()) {
                Spacer(modifier = Modifier.height(ReiAnixTokens.Spacing.sm))
                Row(
                    modifier = Modifier.horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(ReiAnixTokens.Spacing.xs),
                ) {
                    facts.forEach { fact ->
                        DetailsFactChip(fact)
                    }
                }
            }

            if (anime.genres.isNotEmpty()) {
                Spacer(modifier = Modifier.height(ReiAnixTokens.Spacing.md))
                Row(
                    modifier = Modifier.horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(ReiAnixTokens.Spacing.xs),
                ) {
                    anime.genres.forEach { genre ->
                        DetailsFactChip(genre.name)
                    }
                }
            }

            Spacer(modifier = Modifier.height(ReiAnixTokens.Spacing.lg))

            val targetId = anime.playbackTargetEpisodeId
            if (targetId != null) {
                ReiAnixPrimaryButton(
                    text = if (anime.shouldContinue) "Continuar" else "Assistir",
                    onClick = {
                        onWatch(targetId)
                    },
                    modifier = Modifier.fillMaxWidth(),
                )
            } else {
                Text(
                    text = "Nenhuma mídia local disponível para reprodução.",
                    style = MaterialTheme.typography.bodySmall,
                    color = ReiAnixTokens.Colors.textMuted,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        }
    }
}

@Composable
private fun DetailsFactChip(
    text: String,
) {
    Surface(
        shape = ReiAnixTokens.Shapes.chip,
        color = ReiAnixTokens.Colors.surfaceVariant,
    ) {
        Text(
            text = text,
            style = MaterialTheme.typography.labelMedium,
            color = ReiAnixTokens.Colors.text,
            modifier = Modifier.padding(
                horizontal = ReiAnixTokens.Spacing.sm,
                vertical = ReiAnixTokens.Spacing.xs,
            ),
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun DetailsLoading() {
    Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        CircularProgressIndicator(color = ReiAnixTokens.Colors.primary)
    }
}

@Composable
private fun DetailsMessage(
    title: String,
    message: String,
    onRetry: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(ReiAnixTokens.Spacing.xxl),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text(
            text = title,
            style = MaterialTheme.typography.headlineSmall,
            color = ReiAnixTokens.Colors.text,
            fontWeight = FontWeight.Bold,
        )
        Spacer(modifier = Modifier.height(ReiAnixTokens.Spacing.sm))
        Text(
            text = message,
            style = MaterialTheme.typography.bodyLarge,
            color = ReiAnixTokens.Colors.textMuted,
            modifier = Modifier.padding(horizontal = ReiAnixTokens.Spacing.md),
        )
        Spacer(modifier = Modifier.height(ReiAnixTokens.Spacing.lg))
        ReiAnixSecondaryButton(
            text = "Atualizar",
            onClick = onRetry,
        )
    }
}

private fun formatScore(value: Double): String =
    String.format(java.util.Locale.ROOT, "%.1f", (value / 10.0).coerceIn(0.0, 10.0))
