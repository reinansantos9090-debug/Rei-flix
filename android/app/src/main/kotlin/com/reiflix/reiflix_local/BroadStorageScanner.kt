package com.reiflix.reiflix_local

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.os.storage.StorageManager
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.ArrayDeque
import java.util.HashSet

object BroadStorageScanner {
    const val SOURCE = "broad-storage"
    const val DISPLAY_NAME = "Armazenamento local"
    private val videoExtensions = setOf("mp4","mkv","webm","avi","mov","m4v","ts","m2ts","flv","wmv")
    fun hasAccess(context: Context): Boolean = when {
        Build.VERSION.SDK_INT >= 30 -> Environment.isExternalStorageManager()
        Build.VERSION.SDK_INT >= 23 -> context.checkSelfPermission(Manifest.permission.READ_EXTERNAL_STORAGE) == PackageManager.PERMISSION_GRANTED
        else -> true
    }

    /** Compact runtime diagnostics used to explain why local storage is or is not visible. */
    fun accessSnapshot(context: Context): JSONObject {
        val result = JSONObject()
            .put("api", Build.VERSION.SDK_INT)
            .put("hasAccess", hasAccess(context))
        val rootsJson = JSONArray()
        roots(context).forEach { root ->
            val check = JSONObject().put("path", root.path)
                .put("exists", root.exists())
                .put("directory", root.isDirectory)
                .put("readable", root.canRead())
            if (root.exists() && root.isDirectory) {
                check.put("children", runCatching { root.list()?.size ?: 0 }.getOrDefault(-1))
            }
            rootsJson.put(check)
        }
        result.put("roots", rootsJson)
        val volumes = JSONArray()
        if (Build.VERSION.SDK_INT >= 24) {
            context.getSystemService(StorageManager::class.java)?.storageVolumes?.forEach { volume ->
                val item = JSONObject()
                    .put("uuid", volume.uuid ?: "")
                    .put("primary", volume.isPrimary)
                    .put("removable", volume.isRemovable)
                    .put("state", volume.state ?: "unknown")
                runCatching { volume.directory?.canonicalPath }.getOrNull()?.let { item.put("directory", it) }
                volumes.put(item)
            }
        }
        result.put("volumes", volumes)
        return result
    }

    fun roots(context: Context): List<File> {
        val paths = LinkedHashSet<String>()
        Environment.getExternalStorageDirectory().let { if (it.exists()) paths.add(it.absolutePath) }
        if (Build.VERSION.SDK_INT >= 30) {
            Environment.getStorageDirectory().let { if (it.exists()) paths.add(it.absolutePath) }
        }
        if (Build.VERSION.SDK_INT >= 24) {
            context.getSystemService(StorageManager::class.java)?.storageVolumes?.forEach { volume ->
                runCatching { volume.directory?.canonicalPath }.getOrNull()?.let(paths::add)
            }
        }
        return paths.mapNotNull { runCatching { File(it).canonicalFile }.getOrNull() }
    }

    fun isAuthorizedFile(context: Context, uri: Uri): Boolean {
        if (uri.scheme != "file" || !hasAccess(context)) return false
        val file = runCatching { File(uri.path ?: "").canonicalFile }.getOrNull() ?: return false
        return roots(context).any { isInside(file, it) } && !isRestricted(file)
    }

    private fun isInside(file: File, root: File): Boolean =
        file.path == root.path || file.path.startsWith(root.path + File.separator)

    private fun isRestricted(file: File): Boolean {
        val parts = file.path.split(File.separator).filter(String::isNotEmpty)
        val i = parts.indexOfLast { it.equals("Android", true) }
        val child = if (i >= 0) parts.getOrNull(i + 1)?.lowercase() else null
        return child == "data" || child == "obb"
    }

    fun scan(context: Context, onProgress: ((JSONObject) -> Unit)? = null): JSONObject {
        check(hasAccess(context))
        val docs = JSONArray()
        val errors = JSONArray()
        val snapshot = accessSnapshot(context)
        val visited = HashSet<String>()
        val pending = ArrayDeque<File>()
        val rootFiles = roots(context)
        rootFiles.forEach { pending.addLast(it) }
        if (rootFiles.isEmpty()) errors.put("Nenhuma raiz de armazenamento compartilhado foi encontrada.")
        var directories = 0
        var files = 0
        var videos = 0
        onProgress?.invoke(JSONObject().put("phase","started").put("source",SOURCE)
            .put("directories",0).put("files",0).put("videos",0))
        while (pending.isNotEmpty()) {
            val dir = pending.removeLast()
            val canonical = runCatching { dir.canonicalFile }.getOrElse { dir }
            if (!visited.add(canonical.path) || isRestricted(canonical)) continue
            directories++
            val children = try { canonical.listFiles() } catch (_: Exception) { null }
            if (children == null) {
                errors.put("Não foi possível acessar: ${canonical.name}")
                continue
            }
            for (child in children) {
                if (isRestricted(child)) continue
                if (child.isDirectory) { pending.addLast(child); continue }
                files++
                if (!child.isFile || child.extension.lowercase() !in videoExtensions) continue
                val file = runCatching { child.canonicalFile }.getOrNull() ?: continue
                docs.put(JSONObject().put("uri",Uri.fromFile(file).toString()).put("path",file.path)
                    .put("name",file.name).put("relativePath",file.path).put("mimeType",mimeFor(file.extension))
                    .put("size",runCatching{file.length()}.getOrDefault(0L))
                    .put("modifiedAt",runCatching{file.lastModified()}.getOrDefault(0L)))
                videos++
                if (videos % 100 == 0) onProgress?.invoke(JSONObject().put("phase","scanning")
                    .put("source",SOURCE).put("directories",directories).put("files",files).put("videos",videos))
            }
        }
        onProgress?.invoke(JSONObject().put("phase","finished").put("source",SOURCE)
            .put("directories",directories).put("files",files).put("videos",videos))
        return JSONObject().put("source",SOURCE).put("name",DISPLAY_NAME).put("documents",docs)
            .put("stats",JSONObject().put("directories",directories).put("files",files).put("videos",videos).put("errors",errors)
                .put("access", snapshot))
            .put("partial",errors.length()>0)
    }

    private fun mimeFor(ext:String):String = when(ext.lowercase()) {
        "mkv" -> "video/x-matroska"; "webm" -> "video/webm"; "avi" -> "video/x-msvideo"; "mov" -> "video/quicktime"
        "m4v" -> "video/x-m4v"; "ts","m2ts" -> "video/mp2t"; "flv" -> "video/x-flv"; "wmv" -> "video/x-ms-wmv"; else -> "video/mp4"
    }
}
