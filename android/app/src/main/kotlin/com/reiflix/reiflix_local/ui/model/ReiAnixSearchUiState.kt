package com.reiflix.reiflix_local.ui.model

import androidx.annotation.Keep

@Keep
data class ReiAnixSearchUiState(
    val query: String = "",
    val results: List<ReiAnixAnimeUiModel> = emptyList(),
)
