package com.reiflix.reiflix_local

import android.view.Window
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat

/**
 * Owns the normal system-bar policy for the Flet/Flutter host window.
 *
 * The main Rei-Flix shell keeps the status/navigation bars visible and lets
 * the window manager apply the normal content insets. The native player owns
 * its own immersive policy and never calls this controller.
 */
class SystemUiController(private val window: Window) {
    private val controller: WindowInsetsControllerCompat
        get() = WindowCompat.getInsetsController(window, window.decorView)

    fun applyNormal() {
        WindowCompat.setDecorFitsSystemWindows(window, true)

        controller.apply {
            isAppearanceLightStatusBars = false
            isAppearanceLightNavigationBars = false
            show(WindowInsetsCompat.Type.systemBars())
        }
    }
}
