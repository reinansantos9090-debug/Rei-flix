package com.reiflix.reiflix_local

import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import androidx.compose.ui.platform.ComposeView
import androidx.compose.ui.platform.ViewCompositionStrategy
import com.reiflix.reiflix_local.ui.ReiAnixComposeRoot
import com.reiflix.reiflix_local.ui.library.ReiAnixLibraryRoute
import com.reiflix.reiflix_local.ui.library.rememberReiAnixLibraryViewModel

/**
 * Reversible presentation bridge for the real Library route.
 *
 * Flutter/Flet remains the application's primary host. This view is attached
 * only while the existing logical navigation route is "library"; all data and
 * commands still flow through the established Python/SQLite projection.
 */
class ReiAnixComposeLibraryHost(
    private val activity: MainActivity,
    private val onOpenDetails: (Long) -> Unit,
) {
    private var composeView: ComposeView? = null

    val isVisible: Boolean
        get() = composeView?.visibility == View.VISIBLE

    fun show() {
        val view = ensureAttached()
        view.visibility = View.VISIBLE
        if (view.tag != CONTENT_TAG) {
            view.setContent {
                ReiAnixComposeRoot {
                    val viewModel = rememberReiAnixLibraryViewModel()
                    ReiAnixLibraryRoute(
                        viewModel = viewModel,
                        onOpenDetails = onOpenDetails,
                    )
                }
            }
            view.tag = CONTENT_TAG
        }
    }

    fun hide() {
        composeView?.visibility = View.GONE
    }

    fun dispose() {
        composeView?.let { view ->
            (view.parent as? ViewGroup)?.removeView(view)
            view.disposeComposition()
        }
        composeView = null
    }

    private fun ensureAttached(): ComposeView {
        composeView?.let { existing ->
            if (existing.parent != null) return existing
        }

        val root = activity.findViewById<ViewGroup>(android.R.id.content)
            ?: error("MainActivity content root is unavailable")

        val view = ComposeView(activity).apply {
            layoutParams = FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT,
            )
            elevation = 100f
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_YES
            visibility = View.GONE
            setViewCompositionStrategy(
                ViewCompositionStrategy.DisposeOnViewTreeLifecycleDestroyed,
            )
        }
        root.addView(view)
        composeView = view
        return view
    }

    private companion object {
        const val CONTENT_TAG = "reianix_compose_library_content"
    }
}
