package com.reiflix.reiflix_local

import android.content.res.Configuration
import android.graphics.Color
import android.os.Build
import android.view.Window
import android.view.WindowManager
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat

/**
 * Single authority for the host Activity system-bar policy.
 *
 * Rei-Flix uses one application-wide edge-to-edge + immersive policy. Both the
 * Flet/MainActivity surface and the native Media3 player restore this policy
 * after lifecycle/configuration boundaries. Android-owned external surfaces
 * (permissions/settings/pickers) may reveal their own system UI while they are
 * in the foreground; the app reapplies its policy when focus returns.
 */
class SystemUiController(private val window: Window) {
    private val controller: WindowInsetsControllerCompat
        get() = WindowCompat.getInsetsController(window, window.decorView)

    /**
     * Reapply the application policy after resume/focus/configuration changes.
     *
     * Android system gestures remain available because transient bars may be
     * revealed by an edge swipe; hiding the bars does not disable system Back.
     */
    fun applyApplicationPolicy(useContextAppearance: Boolean = true) {
        applyEdgeToEdgeWindow()
        if (useContextAppearance) {
            applySystemBarAppearance()
        }
        controller.apply {
            systemBarsBehavior =
                WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            hide(WindowInsetsCompat.Type.systemBars())
        }
    }

    /** Player-specific alias kept for existing call sites and tests. */
    fun applyImmersive() = applyApplicationPolicy()

    /** Explicit non-immersive policy for an Activity that truly needs visible bars. */
    fun applyNormal(useContextAppearance: Boolean = true) {
        applyEdgeToEdgeWindow()
        if (useContextAppearance) {
            applySystemBarAppearance()
        }
        controller.apply {
            systemBarsBehavior =
                WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            show(WindowInsetsCompat.Type.systemBars())
        }
    }

    private fun applyEdgeToEdgeWindow() {
        WindowCompat.setDecorFitsSystemWindows(window, false)
        window.statusBarColor = Color.TRANSPARENT
        window.navigationBarColor = Color.TRANSPARENT
        if (Build.VERSION.SDK_INT >= 29) {
            window.isStatusBarContrastEnforced = false
            window.isNavigationBarContrastEnforced = false
        }
        if (Build.VERSION.SDK_INT >= 30) {
            window.attributes = window.attributes.apply {
                layoutInDisplayCutoutMode =
                    WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_ALWAYS
            }
        }
    }

    private fun applySystemBarAppearance() {
        val nightMode = window.context.resources.configuration.uiMode and
            Configuration.UI_MODE_NIGHT_MASK
        val darkTheme = nightMode == Configuration.UI_MODE_NIGHT_YES
        controller.apply {
            isAppearanceLightStatusBars = !darkTheme
            isAppearanceLightNavigationBars = !darkTheme
        }
    }
}
