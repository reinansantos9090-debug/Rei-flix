package com.reiflix.reiflix_local

import android.view.Window
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat

/**
 * Owns the immersive system-bar policy for the Flet/Flutter host window.
 *
 * The main Rei-Flix shell is edge-to-edge and keeps both system bars hidden
 * during normal navigation. Android may reveal transient bars in response to
 * a system-edge gesture; the controller does not fight that transient state.
 */
class SystemUiController(private val window: Window) {
    private val controller: WindowInsetsControllerCompat
        get() = WindowCompat.getInsetsController(window, window.decorView)

    fun applyImmersive() {
        WindowCompat.setDecorFitsSystemWindows(window, false)

        controller.apply {
            isAppearanceLightStatusBars = false
            isAppearanceLightNavigationBars = false
            systemBarsBehavior =
                WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            hide(WindowInsetsCompat.Type.systemBars())
        }
    }
}
