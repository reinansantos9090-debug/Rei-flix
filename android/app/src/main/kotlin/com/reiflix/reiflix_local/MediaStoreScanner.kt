package com.reiflix.reiflix_local

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject

/**
 * Read-only MediaStore projection for device videos.
 *
 * The scanner deliberately exposes MediaStore rows as content:// URIs. It
 * never reads MediaStore.DATA or converts a content URI into a filesystem path.
 */
object MediaStoreScanner {
    const val SOURCE = "mediastore:external:video"
    const val DISPLAY_NAME = "Vídeos do dispositivo"
    private const val TAG = "[REIFLIX][MEDIASTORE]"

    private val videoExtensions = setOf("mp4", "mkv", "webm", "avi", "mov", "m4v", "ts", "m2ts", "flv", "wmv")

    fun requiredPermissions(): Array<String> {
        return when {
            Build.VERSION.SDK_INT >= 34 -> arrayOf(
                Manifest.permission.READ_MEDIA_VIDEO,
                Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED,
            )
            Build.VERSION.SDK_INT >= 33 -> arrayOf(Manifest.permission.READ_MEDIA_VIDEO)
            Build.VERSION.SDK_INT >= 23 -> arrayOf(Manifest.permission.READ_EXTERNAL_STORAGE)
            else -> emptyArray()
        }
    }

    fun hasReadPermission(context: Context): Boolean {
        return when {
            Build.VERSION.SDK_INT >= 34 ->
                has(context, Manifest.permission.READ_MEDIA_VIDEO) ||
                    has(context, Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED)
            Build.VERSION.SDK_INT >= 33 ->
                has(context, Manifest.permission.READ_MEDIA_VIDEO)
            Build.VERSION.SDK_INT >= 23 ->
                has(context, Manifest.permission.READ_EXTERNAL_STORAGE)
            else -> true
        }
    }

    private fun has(context: Context, permission: String): Boolean =
        context.checkSelfPermission(permission) == PackageManager.PERMISSION_GRANTED

    fun accessLevel(context: Context): String {
        return when {
            Build.VERSION.SDK_INT >= 34 && has(context, Manifest.permission.READ_MEDIA_VIDEO) -> "full"
            Build.VERSION.SDK_INT >= 34 && has(context, Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED) -> "partial"
            Build.VERSION.SDK_INT >= 33 && has(context, Manifest.permission.READ_MEDIA_VIDEO) -> "full"
            Build.VERSION.SDK_INT >= 23 && has(context, Manifest.permission.READ_EXTERNAL_STORAGE) -> "full"
            Build.VERSION.SDK_INT < 23 -> "full"
            else -> "denied"
        }
    }

    fun isAuthorizedDocument(context: Context, uri: Uri): Boolean {
        return uri.scheme == "content" &&
            uri.authority == MediaStore.AUTHORITY &&
            hasReadPermission(context)
    }

    fun scan(context: Context, onProgress: ((JSONObject) -> Unit)? = null): JSONObject {
        check(hasReadPermission(context)) { "Permissão de vídeos não concedida." }

        val resolver = context.contentResolver
        // The synthetic MediaStore.VOLUME_EXTERNAL view is deliberately not queried here:
        // per-volume queries keep removable storage provenance explicit for reconciliation.
        // MediaStore.Video.Media.getContentUri(MediaStore.VOLUME_EXTERNAL) remains a valid
        // aggregate API, but is intentionally avoided for the indexer's physical identity.
        val volumeNames = if (Build.VERSION.SDK_INT >= 29) {
            MediaStore.getExternalVolumeNames(context).ifEmpty { setOf(MediaStore.VOLUME_EXTERNAL_PRIMARY) }
        } else {
            setOf(MediaStore.VOLUME_EXTERNAL_PRIMARY)
        }

        val projection = mutableListOf(
            MediaStore.Video.Media._ID,
            MediaStore.Video.Media.DISPLAY_NAME,
            MediaStore.Video.Media.MIME_TYPE,
            MediaStore.Video.Media.SIZE,
            MediaStore.Video.Media.DATE_MODIFIED,
        )
        if (Build.VERSION.SDK_INT >= 29) {
            projection += MediaStore.Video.Media.RELATIVE_PATH
        }

        val documents = JSONArray()
        val errors = JSONArray()
        var files = 0
        var videos = 0

        onProgress?.invoke(JSONObject()
            .put("phase", "started")
            .put("source", SOURCE)
            .put("files", 0)
            .put("videos", 0))

        try {
            for (volumeName in volumeNames) {
                val collection = if (Build.VERSION.SDK_INT >= 29) {
                    MediaStore.Video.Media.getContentUri(volumeName)
                } else {
                    MediaStore.Video.Media.EXTERNAL_CONTENT_URI
                }
                resolver.query(
                    collection,
                    projection.toTypedArray(),
                    null,
                    null,
                    MediaStore.Video.Media.DISPLAY_NAME + " COLLATE NOCASE ASC",
                )?.use { cursor ->
                val idColumn = cursor.getColumnIndex(MediaStore.Video.Media._ID)
                val nameColumn = cursor.getColumnIndex(MediaStore.Video.Media.DISPLAY_NAME)
                val mimeColumn = cursor.getColumnIndex(MediaStore.Video.Media.MIME_TYPE)
                val sizeColumn = cursor.getColumnIndex(MediaStore.Video.Media.SIZE)
                val modifiedColumn = cursor.getColumnIndex(MediaStore.Video.Media.DATE_MODIFIED)
                val relativeColumn = if (Build.VERSION.SDK_INT >= 29) {
                    cursor.getColumnIndex(MediaStore.Video.Media.RELATIVE_PATH)
                } else {
                    -1
                }

                if (idColumn < 0 || nameColumn < 0) {
                    errors.put("O MediaStore não retornou os dados necessários.")
                    return@use
                }

                while (cursor.moveToNext()) {
                    files++
                    val id = cursor.getLong(idColumn)
                    val name = cursor.getString(nameColumn) ?: "video-$id"
                    val mimeType = if (mimeColumn >= 0 && !cursor.isNull(mimeColumn)) {
                        cursor.getString(mimeColumn)
                    } else {
                        "video/*"
                    }
                    val extension = name.substringAfterLast('.', "").lowercase()
                    if (!mimeType.startsWith("video/") && extension !in videoExtensions) continue

                    val relativeDirectory = if (relativeColumn >= 0 && !cursor.isNull(relativeColumn)) {
                        cursor.getString(relativeColumn).orEmpty().trimEnd('/')
                    } else {
                        ""
                    }
                    val relativePath = if (relativeDirectory.isBlank()) {
                        name
                    } else {
                        "$relativeDirectory/$name"
                    }

                    val uri = if (Build.VERSION.SDK_INT >= 29) {
                        MediaStore.Video.Media.getContentUri(volumeName, id)
                    } else {
                        android.content.ContentUris.withAppendedId(
                            MediaStore.Video.Media.EXTERNAL_CONTENT_URI,
                            id,
                        )
                    }

                    val size = if (sizeColumn >= 0 && !cursor.isNull(sizeColumn)) {
                        cursor.getLong(sizeColumn)
                    } else 0L
                    val modifiedAt = if (modifiedColumn >= 0 && !cursor.isNull(modifiedColumn)) {
                        cursor.getLong(modifiedColumn) * 1000L
                    } else 0L

                    documents.put(JSONObject()
                        .put("uri", uri.toString())
                        .put("name", name)
                        .put("relativePath", relativePath)
                        .put("mimeType", mimeType)
                        .put("size", size)
                        .put("modifiedAt", modifiedAt)
                        .put("volumeId", volumeName)
                        .put("volumeUuid", volumeName))
                    videos++

                    if (videos % 100 == 0) {
                        onProgress?.invoke(JSONObject()
                            .put("phase", "scanning")
                            .put("source", SOURCE)
                            .put("files", files)
                            .put("videos", videos))
                    }
                }
                } ?: errors.put("O MediaStore não conseguiu consultar o volume $volumeName.")
            }
        } catch (security: SecurityException) {
            Log.w(TAG, "MediaStore permission/query denied", security)
            errors.put("O acesso aos vídeos do dispositivo foi negado.")
        } catch (exception: Exception) {
            Log.w(TAG, "MediaStore query failed", exception)
            errors.put("Não foi possível consultar os vídeos do dispositivo.")
        }

        val partial = errors.length() > 0
        onProgress?.invoke(JSONObject()
            .put("phase", "finished")
            .put("source", SOURCE)
            .put("files", files)
            .put("videos", videos))

        return JSONObject()
            .put("source", SOURCE)
            .put("name", DISPLAY_NAME)
            .put("documents", documents)
            .put("stats", JSONObject()
                .put("files", files)
                .put("videos", videos)
                .put("errors", errors))
            .put("partial", partial)
    }
}
