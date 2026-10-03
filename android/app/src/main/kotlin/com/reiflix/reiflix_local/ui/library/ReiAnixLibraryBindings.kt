package com.reiflix.reiflix_local.ui.library

import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.reiflix.reiflix_local.ui.model.ReiAnixLibraryUiState
import com.reiflix.reiflix_local.viewmodel.ReiAnixLibraryViewModel

/**
 * UI binding intentionally contains no library business rules.
 * State collection follows the Composable lifecycle.
 */
@Composable
fun ReiAnixLibraryRoute(
    viewModel: ReiAnixLibraryViewModel,
    content: @Composable (ReiAnixLibraryUiState) -> Unit,
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    content(state)
}
