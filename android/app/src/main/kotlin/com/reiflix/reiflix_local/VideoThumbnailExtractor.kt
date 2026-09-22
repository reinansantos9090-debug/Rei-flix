package com.reiflix.reiflix_local

import android.content.Context
import android.graphics.Bitmap
import android.media.MediaMetadataRetriever
import android.net.Uri
import java.io.File
import java.io.FileOutputStream
import java.security.MessageDigest

/**
 * Extracts a small local poster frame from a video and caches it atomically.
 * The bitmap never crosses the Python/native mailbox boundary.
 */
object VideoThumbnailExtractor {
    fun extract(context: Context, uri: Uri, size: Long = 0L, modifiedAt: Long = 0L): String? {
        val cacheDir = File(context.cacheDir, "reiflix/thumbnails")
        if (!cacheDir.exists() && !cacheDir.mkdirs()) return null

        val key = sha256(uri.toString() + "|" + size + "|" + modifiedAt)
        val target = File(cacheDir, key + ".jpg")
        if (target.isFile && target.length() > 0L) return target.absolutePath
        val temp = File(cacheDir, key + ".tmp")

        val retriever = MediaMetadataRetriever()
        return try {
            when (uri.scheme?.lowercase()) {
                "content" -> retriever.setDataSource(context, uri)
                "file" -> retriever.setDataSource(uri.path ?: return null)
                else -> return null
            }

            val bitmap = if (android.os.Build.VERSION.SDK_INT >= 27) {
                retriever.getScaledFrameAtTime(
                    0L,
                    MediaMetadataRetriever.OPTION_CLOSEST_SYNC,
                    640,
                    360,
                )
            } else {
                retriever.getFrameAtTime(0L, MediaMetadataRetriever.OPTION_CLOSEST_SYNC)
            } ?: return null

            temp.delete()
            FileOutputStream(temp).use { output ->
                if (!bitmap.compress(Bitmap.CompressFormat.JPEG, 84, output)) return null
                output.fd.sync()
            }
            bitmap.recycle()

            if (target.isFile && target.length() > 0L) {
                temp.delete()
                target.absolutePath
            } else if (temp.renameTo(target)) {
                target.absolutePath
            } else {
                temp.delete()
                null
            }
        } catch (_: Exception) {
            temp.delete()
            null
        } finally {
            runCatching { retriever.release() }
        }
    }

    private fun sha256(value: String): String {
        val digest = MessageDigest.getInstance("SHA-256").digest(value.toByteArray(Charsets.UTF_8))
        return digest.joinToString("") { "%02x".format(it) }
    }
}
