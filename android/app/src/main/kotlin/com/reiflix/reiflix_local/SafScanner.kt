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
        context.contentResolver.takePersistableUriPermission(uri, granted and Intent.FLAG_GRANT_READ_URI_PERMISSION)
        Log.i(TAG, "Persisted tree permission: $uri")
    }

    fun scan(context: Context, treeUri: Uri): JSONObject {
        val root = DocumentFile.fromTreeUri(context, treeUri) ?: throw IllegalArgumentException("Árvore SAF inválida")
        val files = JSONArray(); val stats = JSONObject().put("files", 0).put("videos", 0).put("errors", JSONArray())
        visit(root, files, stats)
        return JSONObject().put("treeUri", treeUri.toString()).put("name", root.name ?: treeUri.toString()).put("documents", files).put("stats", stats)
    }

    private fun visit(directory: DocumentFile, files: JSONArray, stats: JSONObject) {
        try {
            directory.listFiles().forEach { file ->
                if (file.isDirectory) visit(file, files, stats) else {
                    stats.put("files", stats.getInt("files") + 1)
                    val name = file.name ?: return@forEach
                    val extension = name.substringAfterLast('.', "").lowercase()
                    if (extension in videoExtensions) {
                        files.put(JSONObject()
                            .put("uri", file.uri.toString()).put("name", name)
                            .put("mimeType", file.type ?: "video/*").put("size", file.length())
                            .put("modifiedAt", file.lastModified()))
                        stats.put("videos", stats.getInt("videos") + 1)
                        Log.d(TAG, "Video found: ${file.uri}")
                    }
                }
            }
        } catch (exception: SecurityException) {
            stats.getJSONArray("errors").put("Sem acesso a ${directory.uri}: ${exception.message}")
            Log.w(TAG, "Permission revoked for ${directory.uri}", exception)
        }
    }
}
