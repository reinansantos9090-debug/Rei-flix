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
    private val videoExtensions = setOf("mp4", "mkv", "webm", "avi", "mov", "m4v", "ts", "m2ts", "flv", "wmv")

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

    fun displayName(context: Context, treeUri: Uri): String {
        return runCatching {
            DocumentFile.fromTreeUri(context, treeUri)?.name
        }.getOrNull()?.takeIf { it.isNotBlank() } ?: treeUri.toString()
    }

    private fun directoryHasNoMedia(resolver: android.content.ContentResolver, treeUri: Uri, parentDocumentId: String): Boolean {
        val childrenUri = runCatching {
            DocumentsContract.buildChildDocumentsUriUsingTree(treeUri, parentDocumentId)
        }.getOrNull() ?: return false
        return runCatching {
            resolver.query(
                childrenUri,
                arrayOf(DocumentsContract.Document.COLUMN_DISPLAY_NAME),
                null,
                null,
                null,
            )?.use { cursor ->
                val nameColumn = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_DISPLAY_NAME)
                if (nameColumn < 0) return@use false
                while (cursor.moveToNext()) {
                    if (cursor.getString(nameColumn)?.equals(".nomedia", ignoreCase = true) == true) {
                        return@use true
                    }
                }
                false
            } ?: false
        }.getOrDefault(false)
    }

    fun scan(context: Context, treeUri: Uri, onProgress: ((JSONObject) -> Unit)? = null, shouldCancel: () -> Boolean = { false }): JSONObject {
        check(hasPersistedReadPermission(context, treeUri)) { "A permissão desta pasta foi removida." }
        val resolver = context.contentResolver
        val root = DocumentFile.fromTreeUri(context, treeUri)
            ?: throw IllegalArgumentException("Árvore SAF inválida")
        val rootDocumentId = runCatching { DocumentsContract.getTreeDocumentId(treeUri) }
            .getOrElse { throw IllegalArgumentException("ID da árvore SAF inválido", it) }
        val providerVolumeId = if (treeUri.authority == "com.android.externalstorage.documents" && rootDocumentId.contains(":")) {
            val rawVolume = rootDocumentId.substringBefore(":")
            if (rawVolume == "primary") "external_primary" else rawVolume
        } else ""

        val files = JSONArray()
        val errors = JSONArray()
        val stats = JSONObject().put("files", 0).put("videos", 0).put("directories", 0).put("excludedNoMedia", 0).put("errors", errors)

        // Query the provider directly instead of relying on DocumentFile.listFiles().
        // This preserves provider-native document IDs and works for local as well
        // as cloud-backed DocumentsProviders without converting URIs into paths.
        val pending = ArrayDeque<Pair<String, String>>()
        val visited = HashSet<String>()
        pending.addLast(rootDocumentId to "")
        var lastProgressFiles = 0
        var lastProgressDirectories = 0

        var cancelled = false
        while (pending.isNotEmpty()) {
            if (shouldCancel()) { cancelled = true; break }
            val (parentDocumentId, currentPath) = pending.removeLast()
            if (!visited.add(parentDocumentId)) {
                continue
            }
            if (directoryHasNoMedia(resolver, treeUri, parentDocumentId)) {
                stats.put("excludedNoMedia", stats.getInt("excludedNoMedia") + 1)
                continue
            }
            stats.put("directories", stats.getInt("directories") + 1)
            if (stats.getInt("directories") - lastProgressDirectories >= 25) {
                lastProgressDirectories = stats.getInt("directories")
                onProgress?.invoke(JSONObject()
                    .put("directories", lastProgressDirectories)
                    .put("files", stats.getInt("files"))
                    .put("videos", stats.getInt("videos"))
                    .put("pending", pending.size)
                    .put("currentPath", currentPath))
            }

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

                    data class ChildDoc(
                        val documentId: String,
                        val name: String,
                        val mimeType: String,
                        val size: Long,
                        val modifiedAt: Long,
                    )
                    val children = mutableListOf<ChildDoc>()
                    var hasNoMedia = false

                    while (cursor.moveToNext()) {
                        val documentId = cursor.getString(idColumn) ?: continue
                        val name = cursor.getString(nameColumn) ?: documentId
                        if (name.equals(".nomedia", ignoreCase = true)) {
                            hasNoMedia = true
                            break
                        }
                        val mimeType = cursor.getString(mimeColumn) ?: "application/octet-stream"
                        val size = if (sizeColumn >= 0 && !cursor.isNull(sizeColumn)) cursor.getLong(sizeColumn) else 0L
                        val modifiedAt = if (modifiedColumn >= 0 && !cursor.isNull(modifiedColumn)) cursor.getLong(modifiedColumn) else 0L
                        children.add(ChildDoc(documentId, name, mimeType, size, modifiedAt))
                    }

                    if (hasNoMedia) {
                        stats.put("nomediaDirectories", stats.optInt("nomediaDirectories", 0) + 1)
                        return@use
                    }

                    for (child in children) {
                        val relativePath = if (currentPath.isEmpty()) child.name else "$currentPath/${child.name}"
                        val childUri = runCatching {
                            DocumentsContract.buildDocumentUriUsingTree(treeUri, child.documentId)
                        }.getOrElse {
                            errors.put("Não foi possível acessar: $relativePath")
                            continue
                        }

                        if (child.mimeType == DocumentsContract.Document.MIME_TYPE_DIR) {
                            pending.addLast(child.documentId to relativePath)
                            continue
                        }

                        stats.put("files", stats.getInt("files") + 1)
                        if (stats.getInt("files") - lastProgressFiles >= 100) {
                            lastProgressFiles = stats.getInt("files")
                            onProgress?.invoke(JSONObject()
                                .put("directories", stats.getInt("directories"))
                                .put("files", lastProgressFiles)
                                .put("videos", stats.getInt("videos"))
                                .put("pending", pending.size)
                                .put("currentPath", currentPath))
                        }
                        val extension = child.name.substringAfterLast('.', "").lowercase()
                        val isVideo = extension in videoExtensions || child.mimeType.startsWith("video/")
                        if (!isVideo) continue

                        files.put(JSONObject()
                            .put("uri", childUri.toString())
                            .put("treeUri", treeUri.toString())
                            .put("documentId", child.documentId)
                            .put("name", child.name)
                            .put("relativePath", relativePath)
                            .put("volumeId", providerVolumeId)
                            .put("mimeType", child.mimeType)
                            .put("size", child.size)
                            .put("modifiedAt", child.modifiedAt))
                        stats.put("videos", stats.getInt("videos") + 1)
                    }
                } ?: errors.put("O provedor SAF não conseguiu listar: $currentPath")
            } catch (exception: Exception) {
                Log.w(TAG, "SAF provider query failed for $currentPath", exception)
                errors.put("Não foi possível ler: $currentPath")
            }
        }

        onProgress?.invoke(JSONObject()
            .put("directories", stats.getInt("directories"))
            .put("files", stats.getInt("files"))
            .put("videos", stats.getInt("videos"))
            .put("pending", 0)
            .put("currentPath", "").put("cancelled", cancelled))
        val partial = errors.length() > 0 || cancelled
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
            .put("cancelled", cancelled)
    }
}
