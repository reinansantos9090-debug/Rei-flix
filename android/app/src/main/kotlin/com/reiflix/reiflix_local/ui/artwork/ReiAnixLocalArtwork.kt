package com.reiflix.reiflix_local.ui.artwork

import android.content.Context
import android.graphics.BitmapFactory
import android.net.Uri
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextOverflow
import com.reiflix.reiflix_local.ui.theme.ReiAnixTokens
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.InputStream
import kotlin.math.max

/**
 * Offline artwork renderer for Compose.
 *
 * The source is the existing local/cache path from the ReiAnix projection.
 * External URLs are deliberately not fetched by the Home UI.
 */
@Composable
fun ReiAnixLocalArtwork(
    localPath: String?,
    contentDescription: String?,
    modifier: Modifier = Modifier,
    contentScale: ContentScale = ContentScale.Crop,
    placeholder: String = "Sem arte",
    maxDimensionPx: Int = 1024,
) {
    val context = LocalContext.current
    val imageBitmap by produceState<ImageBitmap?>(
        initialValue = null,
        key1 = localPath,
        key2 = maxDimensionPx,
    ) {
        value = withContext(Dispatchers.IO) {
            decodeLocalArtwork(context, localPath, maxDimensionPx)
        }
    }

    Box(
        modifier = modifier
            .clip(MaterialTheme.shapes.medium)
            .background(ReiAnixTokens.Colors.surfaceVariant),
        contentAlignment = Alignment.Center,
    ) {
        val bitmap = imageBitmap
        if (bitmap != null) {
            Image(
                bitmap = bitmap,
                contentDescription = contentDescription,
                modifier = Modifier.fillMaxSize(),
                contentScale = contentScale,
            )
        } else {
            Text(
                text = placeholder,
                style = MaterialTheme.typography.labelMedium,
                color = ReiAnixTokens.Colors.textMuted,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

private fun decodeLocalArtwork(
    context: Context,
    rawPath: String?,
    maxDimensionPx: Int,
): ImageBitmap? {
    val path = rawPath?.trim().orEmpty()
    if (path.isEmpty() || maxDimensionPx <= 0) return null

    val bounds = openArtworkStream(context, path)?.use { stream ->
        BitmapFactory.Options().also { options ->
            options.inJustDecodeBounds = true
            BitmapFactory.decodeStream(stream, null, options)
        }
    } ?: return null

    if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return null

    val sample = calculateSampleSize(bounds.outWidth, bounds.outHeight, maxDimensionPx)
    return openArtworkStream(context, path)?.use { stream ->
        val options = BitmapFactory.Options().apply {
            inSampleSize = sample
            inPreferredConfig = android.graphics.Bitmap.Config.ARGB_8888
        }
        BitmapFactory.decodeStream(stream, null, options)?.asImageBitmap()
    }
}

private fun calculateSampleSize(width: Int, height: Int, maxDimensionPx: Int): Int {
    var sample = 1
    val largest = max(width, height)
    while (largest / (sample * 2) >= maxDimensionPx) {
        sample *= 2
    }
    return sample
}

private fun openArtworkStream(context: Context, path: String): InputStream? =
    runCatching {
        if (path.startsWith("content://", ignoreCase = true)) {
            context.contentResolver.openInputStream(Uri.parse(path))
        } else {
            File(path).takeIf { it.isFile && it.canRead() }?.inputStream()
        }
    }.getOrNull()
