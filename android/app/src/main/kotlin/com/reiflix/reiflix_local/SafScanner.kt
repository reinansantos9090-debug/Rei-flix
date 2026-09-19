package com.reiflix.reiflix_local

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.DocumentsContract
import android.util.Log
import androidx.documentfile.provider.DocumentFile
import org.json.JSONArray
import org.json.JSONObject

object SafScanner {
    private const val TAG = "[REIFLIX][SAF]"
    private val videoExtensions = setOf("mp4", "mkv", "webm", "avi", "mov", "m4v")

    fun persistPermission(context: Context, uri: Uri, flags: Int) {
        val granted = flags and (Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
        require(granted and Intent.FLAG_GRANT_READ_URI_PERMISSION != 0) { "A pasta não concedeu permissão de leitura." }
        context.contentResolver.takePersistableUriPermission(uri, granted)
        check(hasPersistedReadPermission(context, uri)) { "A autorização da pasta não foi persistida." }
        Log.i(TAG, "SAF permission persisted")
    }

    fun hasPersistedReadPermission(context: Context, treeUri: Uri): Boolean =
        context.contentResolver.persistedUriPermissions.any { permission ->
            permission.uri == treeUri && permission.isReadPermission
        }

    fun isAuthorizedDocument(context: Context, documentUri: Uri): Boolean {
        if (documentUri.scheme != "content") return false
        val documentId = runCatching { DocumentsContract.getDocumentId(documentUri) }.getOrNull() ?: return false
        return context.contentResolver.persistedUriPermissions.any { permission ->
            if (!permission.isReadPermission || permission.uri.authority != documentUri.authority) return@any false
            val treeId = runCatching { DocumentsContract.getTreeDocumentId(permission.uri) }.getOrNull() ?: return@any false
            documentId == treeId || documentId.startsWith("$treeId:")
        }
    }

    fun scan(context: Context, treeUri: Uri): JSONObject {
        check(hasPersistedReadPermission(context, treeUri)) { "A permissão desta pasta foi removida." }
        val root = DocumentFile.fromTreeUri(context, treeUri) ?: throw IllegalArgumentException("Árvore SAF inválida")
        val files = JSONArray(); val stats = JSONObject().put("files", 0).put("videos", 0).put("directories", 0).put("errors", JSONArray())
        Log.i(TAG, "SAF scan started")
        visit(root, "", files, stats)
        val partial = stats.getJSONArray("errors").length() > 0
        Log.i(TAG, "SAF scan completed: ${stats.getInt("videos")} videos, partial=$partial")
        return JSONObject().put("treeUri", treeUri.toString()).put("name", root.name ?: treeUri.toString()).put("documents", files).put("stats", stats).put("partial", partial)
    }

    private fun visit(directory: DocumentFile, currentPath: String, files: JSONArray, stats: JSONObject) {
        try {
            stats.put("directories", stats.getInt("directories") + 1)
            directory.listFiles().forEach { file ->
                val name = file.name ?: return@forEach
                val relativePath = if (currentPath.isEmpty()) name else "$currentPath/$name"
                if (file.isDirectory) {
                    visit(file, relativePath, files, stats)
                } else {
                    stats.put("files", stats.getInt("files") + 1)
                    val extension = name.substringAfterLast('.', "").lowercase()
                    val isVideo = extension in videoExtensions || (file.type?.startsWith("video/") == true)
                    if (isVideo) {
                        files.put(JSONObject()
                            .put("uri", file.uri.toString())
                            .put("name", name)
                            .put("relativePath", relativePath)
                            .put("mimeType", file.type ?: "video/*")
                            .put("size", file.length())
                            .put("modifiedAt", file.lastModified()))
                        stats.put("videos", stats.getInt("videos") + 1)
                        Log.d(TAG, "Video found: $relativePath (${file.uri})")
                    }
                }
            }
        } catch (exception: Exception) {
            // A failed subtree makes this a partial scan. Python preserves the
            // previous rows instead of marking unseen documents as missing.
            stats.getJSONArray("errors").put("Não foi possível ler uma subpasta: ${exception.message}")
            Log.w(TAG, "Could not read SAF directory $currentPath", exception)
        }
    }
}
