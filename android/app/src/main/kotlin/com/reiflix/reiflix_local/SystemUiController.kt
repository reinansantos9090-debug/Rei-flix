package com.reiflix.reiflix_local

import android.view.Window
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat

/**
 * Owns the system-bar policy for the Rei-Flix host window.
 *
 * Rei-Flix is a full-screen local-media application. Android 15/16 edge-to-edge
 * means the content may occupy the full window; Flutter is responsible for its
 * own safe padding while this controller keeps transient system bars hidden.
 */
class SystemUiController(private val window: Window) {
    private val controller: WindowInsetsControllerCompat
        get() = WindowCompat.getInsetsController(window, window.decorView)

    fun applyImmersive() {
        WindowCompat.setDecorFitsSystemWindows(window, false)
        controller.apply {
            isAppearanceLightStatusBars = false
            isAppearanceLightNavigationBars = false
            hide(WindowInsetsCompat.Type.systemBars())
            systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        }
    }
}
