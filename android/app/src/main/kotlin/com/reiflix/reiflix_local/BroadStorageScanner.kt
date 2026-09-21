package com.reiflix.reiflix_local

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.os.storage.StorageManager
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.ArrayDeque
import java.util.HashSet

object BroadStorageScanner {
    private const val TAG = "[REIFLIX][SCANNER]"
    const val SOURCE = "broad-storage"
    const val DISPLAY_NAME = "Armazenamento local"
    private val videoExtensions = setOf("mp4","mkv","webm","avi","mov","m4v","ts","m2ts","flv","wmv")

    /** A physical shared-storage root, not merely a path supplied by one scanner. */
    data class StorageRoot(
        val file: File,
        val volumeId: String,
        val volumeUuid: String?,
        val primary: Boolean,
        val removable: Boolean,
        val emulated: Boolean,
        val state: String,
    )
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
            val check = JSONObject().put("path", root.file.path)
                .put("volumeId", root.volumeId).put("uuid", root.volumeUuid ?: "")
                .put("primary", root.primary).put("removable", root.removable).put("emulated", root.emulated)
                .put("state", root.state).put("exists", root.file.exists())
                .put("directory", root.file.isDirectory).put("readable", root.file.canRead())
            if (root.file.exists() && root.file.isDirectory) {
                check.put("children", runCatching { root.file.list()?.size ?: 0 }.getOrDefault(-1))
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
                if (Build.VERSION.SDK_INT >= 30) {
                    volume.mediaStoreVolumeName?.let { item.put("mediaStoreVolumeName", it) }
                    runCatching { volume.directory?.canonicalPath }.getOrNull()?.let { item.put("directory", it) }
                }
                volumes.put(item)
            }
        }
        result.put("volumes", volumes)
        return result
    }

    fun roots(context: Context): List<StorageRoot> {
        val found = LinkedHashMap<String, StorageRoot>()

        fun addRoot(root: StorageRoot) {
            val canonical = runCatching { root.file.canonicalFile }.getOrNull() ?: root.file
            if (canonical.exists() && canonical.isDirectory) {
                found[canonical.path] = root.copy(file = canonical)
            }
        }

        val primary = runCatching { Environment.getExternalStorageDirectory().canonicalFile }.getOrNull()
        if (primary != null) {
            addRoot(
                StorageRoot(
                    primary,
                    "external_primary",
                    null,
                    primary = true,
                    removable = false,
                    emulated = true,
                    state = Environment.getExternalStorageState(primary),
                )
            )
        }

        if (Build.VERSION.SDK_INT >= 30) {
            context.getSystemService(StorageManager::class.java)?.storageVolumes?.forEach { volume ->
                val directory = runCatching { volume.directory }.getOrNull() ?: return@forEach
                val volumeId = runCatching { volume.mediaStoreVolumeName }.getOrNull()
                    ?.takeIf { it.isNotBlank() }
                    ?: volume.uuid?.takeIf { it.isNotBlank() }
                    ?: if (volume.isPrimary) "external_primary" else "path:" + runCatching { directory.canonicalPath }.getOrDefault(directory.path)
                addRoot(
                    StorageRoot(
                        directory,
                        volumeId,
                        volume.uuid,
                        volume.isPrimary,
                        volume.isRemovable,
                        volume.isEmulated,
                        volume.state ?: Environment.getExternalStorageState(directory),
                    )
                )
            }
        } else if (Build.VERSION.SDK_INT >= 19) {
            // StorageVolume.directory is only public from API 30. On API 19-29,
            // getExternalFilesDirs() is the supported way to enumerate every
            // shared/external volume, including a mounted SD card. Derive the
            // volume root from the app-specific path without persisting that
            // absolute path as the volume identity.
            context.getExternalFilesDirs(null).forEach { appDirectory ->
                val volumeRoot = inferVolumeRoot(context, appDirectory) ?: return@forEach
                val primaryVolume = runCatching {
                    volumeRoot.canonicalFile == primary?.canonicalFile
                }.getOrDefault(false)
                val removable = runCatching { Environment.isExternalStorageRemovable(volumeRoot) }.getOrDefault(false)
                val emulated = runCatching { Environment.isExternalStorageEmulated(volumeRoot) }.getOrDefault(primaryVolume)
                val volumeId = if (primaryVolume) {
                    "external_primary"
                } else {
                    "removable:" + volumeRoot.name
                }
                addRoot(
                    StorageRoot(
                        volumeRoot,
                        volumeId,
                        volumeRoot.name.takeIf { removable },
                        primaryVolume,
                        removable,
                        emulated,
                        Environment.getExternalStorageState(volumeRoot),
                    )
                )
            }
        }
        return found.values.toList()
    }

    private fun inferVolumeRoot(context: Context, appDirectory: File?): File? {
        val directory = appDirectory ?: return null
        val canonical = runCatching { directory.canonicalFile }.getOrNull() ?: return null
        val marker = File.separator + "Android" + File.separator + "data" +
            File.separator + context.packageName + File.separator + "files"
        val path = canonical.path
        val index = path.lastIndexOf(marker)
        if (index <= 0) return null
        return runCatching { File(path.substring(0, index)).canonicalFile }.getOrNull()
    }

    fun isAuthorizedFile(context: Context, uri: Uri): Boolean {
        if (uri.scheme != "file" || !hasAccess(context)) return false
        val file = runCatching { File(uri.path ?: "").canonicalFile }.getOrNull() ?: return false
        return roots(context).any { isReadableState(it.state) && isInside(file, it.file) } && !isRestricted(file)
    }

    private fun isInside(file: File, root: File): Boolean =
        file.path == root.path || file.path.startsWith(root.path + File.separator)

    private fun isRestricted(file: File): Boolean {
        val parts = file.path.split(File.separator).filter(String::isNotEmpty)
        val i = parts.indexOfLast { it.equals("Android", true) }
        val child = if (i >= 0) parts.getOrNull(i + 1)?.lowercase() else null
        return child == "data" || child == "obb"
    }

    private fun isNoMediaDirectory(directory: File): Boolean =
        runCatching { File(directory, ".nomedia").isFile }.getOrDefault(false)

    private fun rootForFile(file: File, roots: List<StorageRoot>): StorageRoot? =
        roots.filter { isInside(file, it.file) && isReadableState(it.state) }.maxByOrNull { it.file.path.length }

    private fun relativePath(file: File, root: File): String =
        runCatching {
            val prefix = root.canonicalPath.trimEnd(File.separatorChar) + File.separator
            file.canonicalPath.removePrefix(prefix).replace(File.separatorChar, '/')
        }.getOrDefault(file.name)

    private fun volumeKey(context: Context, root: File): String {
        val primary = runCatching { Environment.getExternalStorageDirectory().canonicalFile }.getOrNull()
        if (primary != null && primary == runCatching { root.canonicalFile }.getOrNull()) {
            return "external_primary"
        }
        if (Build.VERSION.SDK_INT >= 24) {
            val volume = if (Build.VERSION.SDK_INT >= 30) {
                context.getSystemService(StorageManager::class.java)?.storageVolumes?.firstOrNull {
                    runCatching { it.directory?.canonicalFile == root.canonicalFile }.getOrDefault(false)
                }
            } else {
                null
            }
            if (Build.VERSION.SDK_INT >= 30) {
                volume?.mediaStoreVolumeName?.takeIf { it.isNotBlank() }?.let { return it }
            }
            volume?.uuid?.takeIf { it.isNotBlank() }?.let { return it }
        }
        return "path:" + runCatching { root.canonicalPath }.getOrDefault(root.path)
    }

    fun scan(context: Context, onProgress: ((JSONObject) -> Unit)? = null, shouldCancel: () -> Boolean = { false }): JSONObject {
        val access = hasAccess(context)
        Log.i(TAG, "SCAN_STARTED: api=${Build.VERSION.SDK_INT}, granted=$access")
        check(access) { "Acesso amplo ao armazenamento não foi concedido." }
        val docs = JSONArray()
        val errors = JSONArray()
        val snapshot = accessSnapshot(context)
        val visited = HashSet<String>()
        val pending = ArrayDeque<Pair<File, StorageRoot>>()
        val rootFiles = roots(context)
        rootFiles.forEach { root ->
            if (isReadableState(root.state)) {
                pending.addLast(root.file to root)
            } else {
                errors.put("Volume não disponível: ${root.volumeId} (${root.state}).")
            }
        }
        if (rootFiles.isEmpty()) errors.put("Nenhuma raiz de armazenamento compartilhado foi encontrada.")
        var directories = 0
        var files = 0
        var videos = 0
        var excludedNoMedia = 0
        var cancelled = false
        onProgress?.invoke(JSONObject().put("phase","started").put("source",SOURCE)
            .put("directories",0).put("files",0).put("videos",0).put("excludedNoMedia",0))
        while (pending.isNotEmpty()) {
            if (shouldCancel()) { cancelled = true; break }
            val (dir, root) = pending.removeLast()
            val canonical = runCatching { dir.canonicalFile }.getOrElse { dir }
            if (!visited.add(canonical.path) || isRestricted(canonical)) continue
            if (isNoMediaDirectory(canonical)) {
                excludedNoMedia++
                continue
            }
            directories++
            val children = try { canonical.listFiles() } catch (exception: Exception) {
                Log.w(TAG, "DIRECTORY_ACCESS_DENIED: ${canonical.path}", exception)
                null
            }
            if (children == null) {
                val label = if (rootFiles.any { it.file.path == canonical.path }) "raiz" else "diretório"
                errors.put("Não foi possível acessar $label: ${canonical.path}")
                continue
            }
            if (children.any { it.isFile && it.name.equals(".nomedia", ignoreCase = true) }) {
                excludedNoMedia++
                continue
            }
            for (child in children) {
                if (isRestricted(child)) continue
                if (child.isDirectory) { pending.addLast(child to root); continue }
                files++
                if (!child.isFile || child.extension.lowercase() !in videoExtensions) continue
                val file = runCatching { child.canonicalFile }.getOrNull() ?: continue
                val root = rootForFile(file, rootFiles)
                val volumeName = root?.let { volumeKey(context, it.file) } ?: ""
                val relative = root?.let { relativePath(file, it.file) } ?: file.name
                docs.put(JSONObject().put("uri",Uri.fromFile(file).toString()).put("path",file.path)
                    .put("name",file.name).put("relativePath",relative).put("volumeName",volumeName)
                    .put("mimeType",mimeFor(file.extension))
                    .put("size",runCatching{file.length()}.getOrDefault(0L))
                    .put("modifiedAt",runCatching{file.lastModified()}.getOrDefault(0L))
                    .put("volumeId",volumeName).put("volumeUuid",root?.volumeUuid ?: ""))
                videos++
                if (videos % 100 == 0) {
                    Log.i(TAG, "VIDEO_PROGRESS: videos=$videos, files=$files, directories=$directories")
                }
                if (videos % 100 == 0) onProgress?.invoke(JSONObject().put("phase","scanning")
                    .put("source",SOURCE).put("directories",directories).put("files",files).put("videos",videos).put("excludedNoMedia",excludedNoMedia).put("nomediaDirectories",excludedNoMedia))
            }
        }
        Log.i(TAG, "SCAN_COMPLETED: directories=$directories, files=$files, videos=$videos, nomedia=$excludedNoMedia, errors=${errors.length()}")
        onProgress?.invoke(JSONObject().put("phase","finished").put("source",SOURCE)
            .put("directories",directories).put("files",files).put("videos",videos).put("excludedNoMedia",excludedNoMedia).put("nomediaDirectories",excludedNoMedia))
        return JSONObject().put("source",SOURCE).put("name",DISPLAY_NAME).put("documents",docs)
            .put("stats",JSONObject().put("directories",directories).put("files",files).put("videos",videos)
                .put("excludedNoMedia",excludedNoMedia).put("nomediaDirectories",excludedNoMedia).put("errors",errors).put("access", snapshot))
            .put("partial",errors.length()>0 || cancelled)
            .put("cancelled", cancelled)
    }

    private fun mimeFor(ext:String):String = when(ext.lowercase()) {
        "mkv" -> "video/x-matroska"; "webm" -> "video/webm"; "avi" -> "video/x-msvideo"; "mov" -> "video/quicktime"
        "m4v" -> "video/x-m4v"; "ts","m2ts" -> "video/mp2t"; "flv" -> "video/x-flv"; "wmv" -> "video/x-ms-wmv"; else -> "video/mp4"
    }

    private fun isReadableState(state: String?): Boolean =
        state == Environment.MEDIA_MOUNTED || state == Environment.MEDIA_MOUNTED_READ_ONLY
}
