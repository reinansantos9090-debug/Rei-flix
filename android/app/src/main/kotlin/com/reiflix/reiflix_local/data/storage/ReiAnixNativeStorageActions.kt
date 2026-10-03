package com.reiflix.reiflix_local.data.storage

import android.content.Context
import com.reiflix.reiflix_local.MainActivity

/**
 * UI-facing storage command facade.
 *
 * It only delegates to MainActivity's existing permission/scanner service
 * boundary; it never touches ContentResolver, MediaStore, SAF or the filesystem.
 */
class ReiAnixNativeStorageActions(context: Context) {
    private val activity = context as? MainActivity

    fun selectSafTree(): Boolean =
        activity?.requestNativeStorageAction("select_tree") ?: false

    fun requestMediaAccess(): Boolean =
        activity?.requestNativeStorageAction("request_media_access") ?: false

    fun openBroadStorageSettings(): Boolean =
        activity?.requestNativeStorageAction("open_broad_storage_settings") ?: false

    fun checkStorageAccess(): Boolean =
        activity?.requestNativeStorageAction("check_storage_access") ?: false
}
