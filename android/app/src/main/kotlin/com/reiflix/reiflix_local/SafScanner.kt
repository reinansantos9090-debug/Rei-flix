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

    fun hasPersistedReadPermission(context: Context, treeUri: Uri): Boolean {
        if (treeUri.scheme != "content" || !DocumentsContract.isTreeUri(treeUri)) return false
        val treeDocumentId = runCatching { DocumentsContract.getTreeDocumentId(treeUri) }.getOrNull()
            ?: return false
        return context.contentResolver.persistedUriPermissions.any { permission ->
            if (!permission.isReadPermission) return@any false
            val permissionUri = permission.uri
            if (permissionUri.scheme != "content" || permissionUri.authority != treeUri.authority) return@any false
            runCatching {
                DocumentsContract.isTreeUri(permissionUri) &&
                    DocumentsContract.getTreeDocumentId(permissionUri) == treeDocumentId
            }.getOrDefault(false)
        }
    }

    fun isAuthorizedDocument(context: Context, documentUri: Uri): Boolean {
        if (documentUri.scheme != "content") return false
        val documentId = runCatching { DocumentsContract.getDocumentId(documentUri) }.getOrNull() ?: return false
        return context.contentResolver.persistedUriPermissions.any { permission ->
            if (!permission.isReadPermission || permission.uri.authority != documentUri.authority) return@any false
            val treeDocumentId = runCatching { DocumentsContract.getTreeDocumentId(permission.uri) }.getOrNull()
                ?: return@any false
            val scopedUri = runCatching {
                DocumentsContract.buildDocumentUriUsingTree(permission.uri, documentId)
            }.getOrNull() ?: return@any false
            runCatching {
                // Keep the persisted tree identity explicit before rebuilding
                // the document URI; the provider query remains the final
                // authority/access check for cloud and local providers.
                if (treeDocumentId.isBlank()) return@runCatching false
                context.contentResolver.query(
                    scopedUri,
                    arrayOf(DocumentsContract.Document.COLUMN_DOCUMENT_ID),
                    null,
                    null,
                    null,
                )?.use { cursor -> cursor.moveToFirst() } == true
            }.getOrDefault(false)
        }
    }

    fun scan(context: Context, treeUri: Uri): JSONObject {
        check(hasPersistedReadPermission(context, treeUri)) { "A permissão desta pasta foi removida." }
        val resolver = context.contentResolver
        val root = DocumentFile.fromTreeUri(context, treeUri)
            ?: throw IllegalArgumentException("Árvore SAF inválida")
        val rootDocumentId = runCatching { DocumentsContract.getTreeDocumentId(treeUri) }
            .getOrElse { throw IllegalArgumentException("ID da árvore SAF inválido", it) }

        val files = JSONArray()
        val errors = JSONArray()
        val stats = JSONObject().put("files", 0).put("videos", 0).put("directories", 0).put("errors", errors)

        // Query the provider directly instead of relying on DocumentFile.listFiles().
        // This preserves provider-native document IDs and works for local as well
        // as cloud-backed DocumentsProviders without converting URIs into paths.
        val pending = ArrayDeque<Pair<String, String>>()
        pending.addLast(rootDocumentId to "")

        while (pending.isNotEmpty()) {
            val (parentDocumentId, currentPath) = pending.removeLast()
            stats.put("directories", stats.getInt("directories") + 1)

            val childrenUri = runCatching {
                DocumentsContract.buildChildDocumentsUriUsingTree(treeUri, parentDocumentId)
            }.getOrElse {
                errors.put("Não foi possível abrir a subpasta: $currentPath")
                continue
            }

            try {
                resolver.query(
                    childrenUri,
                    arrayOf(
                        DocumentsContract.Document.COLUMN_DOCUMENT_ID,
                        DocumentsContract.Document.COLUMN_DISPLAY_NAME,
                        DocumentsContract.Document.COLUMN_MIME_TYPE,
                        DocumentsContract.Document.COLUMN_SIZE,
                        DocumentsContract.Document.COLUMN_LAST_MODIFIED,
                    ),
                    null,
                    null,
                    null,
                )?.use { cursor ->
                    val idColumn = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_DOCUMENT_ID)
                    val nameColumn = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_DISPLAY_NAME)
                    val mimeColumn = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_MIME_TYPE)
                    val sizeColumn = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_SIZE)
                    val modifiedColumn = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_LAST_MODIFIED)

                    if (idColumn < 0 || nameColumn < 0 || mimeColumn < 0) {
                        errors.put("O provedor SAF não retornou os dados necessários em: $currentPath")
                        return@use
                    }

                    while (cursor.moveToNext()) {
                        val documentId = cursor.getString(idColumn) ?: continue
                        val name = cursor.getString(nameColumn) ?: documentId
                        val mimeType = cursor.getString(mimeColumn) ?: "application/octet-stream"
                        val relativePath = if (currentPath.isEmpty()) name else "$currentPath/$name"
                        val childUri = runCatching {
                            DocumentsContract.buildDocumentUriUsingTree(treeUri, documentId)
                        }.getOrElse {
                            errors.put("Não foi possível acessar: $relativePath")
                            continue
                        }

                        if (mimeType == DocumentsContract.Document.MIME_TYPE_DIR) {
                            pending.addLast(documentId to relativePath)
                            continue
                        }

                        stats.put("files", stats.getInt("files") + 1)
                        val extension = name.substringAfterLast('.', "").lowercase()
                        val isVideo = extension in videoExtensions || mimeType.startsWith("video/")
                        if (!isVideo) continue

                        val size = if (sizeColumn >= 0 && !cursor.isNull(sizeColumn)) cursor.getLong(sizeColumn) else 0L
                        val modifiedAt = if (modifiedColumn >= 0 && !cursor.isNull(modifiedColumn)) cursor.getLong(modifiedColumn) else 0L
                        files.put(JSONObject()
                            .put("uri", childUri.toString())
                            .put("name", name)
                            .put("relativePath", relativePath)
                            .put("mimeType", mimeType)
                            .put("size", size)
                            .put("modifiedAt", modifiedAt))
                        stats.put("videos", stats.getInt("videos") + 1)
                    }
                } ?: errors.put("O provedor SAF não conseguiu listar: $currentPath")
            } catch (exception: Exception) {
                Log.w(TAG, "SAF provider query failed for $currentPath", exception)
                errors.put("Não foi possível ler: $currentPath")
            }
        }

        val partial = errors.length() > 0
        Log.i(
            TAG,
            "SAF scan finished: directories=${stats.getInt("directories")}, files=${stats.getInt("files")}, videos=${stats.getInt("videos")}, partial=$partial"
        )
        return JSONObject()
            .put("treeUri", treeUri.toString())
            .put("name", root.name ?: treeUri.toString())
            .put("documents", files)
            .put("stats", stats)
            .put("partial", partial)
    }
}
