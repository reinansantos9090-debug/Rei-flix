package com.reiflix.reiflix_local

import java.util.Locale

/** Pure playback policy helpers; no I/O, Android state, network, or player ownership. */
internal object PlayerMediaPolicy {
    enum class ErrorCategory {
        SOURCE_UNAVAILABLE,
        DECODER_UNSUPPORTED,
        TRANSIENT,
        NON_RECOVERABLE,
        UNKNOWN,
    }

    fun resolveVideoMimeType(providerMime: String?, displayName: String?): String? {
        val provider = providerMime?.trim()?.lowercase(Locale.ROOT).orEmpty()
        if (provider.startsWith("video/")) {
            return provider
        }
        if (provider.isNotBlank() &&
            provider !in setOf("application/octet-stream", "binary/octet-stream", "application/binary")
        ) {
            return provider.takeIf { it.startsWith("video/") }
        }

        val extension = displayName
            ?.substringAfterLast('.', "")
            ?.trim()
            ?.lowercase(Locale.ROOT)
            .orEmpty()
        return when (extension) {
            "mp4", "m4v" -> "video/mp4"
            "mkv", "mk3d" -> "video/x-matroska"
            "webm" -> "video/webm"
            "avi" -> "video/x-msvideo"
            "mov" -> "video/quicktime"
            "mpeg", "mpg", "mpe" -> "video/mpeg"
            "ts", "m2ts", "mts" -> "video/mp2t"
            "3gp", "3gpp" -> "video/3gpp"
            "flv" -> "video/x-flv"
            else -> null
        }
    }

    fun safeResumePosition(requestedMs: Long, durationMs: Long): Long {
        if (requestedMs <= 0L || durationMs <= 0L) return 0L
        val lastPlayable = (durationMs - 1L).coerceAtLeast(0L)
        return requestedMs.coerceIn(0L, lastPlayable)
    }

    fun classifyError(errorCodeName: String?, causeNames: List<String> = emptyList()): ErrorCategory {
        val code = errorCodeName.orEmpty().uppercase(Locale.ROOT)
        val causes = causeNames.joinToString(" ").uppercase(Locale.ROOT)
        val combined = "$code $causes"
        return when {
            combined.contains("DECODER") ||
                combined.contains("MEDIACODEC") -> ErrorCategory.DECODER_UNSUPPORTED
            combined.contains("SOURCE") &&
                (combined.contains("NOT_FOUND") || combined.contains("UNAVAILABLE")) -> ErrorCategory.SOURCE_UNAVAILABLE
            combined.contains("SECURITY") ||
                combined.contains("PERMISSION") ||
                combined.contains("FILE_NOT_FOUND") ||
                combined.contains("NO_PERMISSION") -> ErrorCategory.SOURCE_UNAVAILABLE
            code.startsWith("ERROR_CODE_IO_") ||
                combined.contains("IOEXCEPTION") ||
                combined.contains("TIMEOUT") -> ErrorCategory.TRANSIENT
            combined.contains("MALFORMED") ||
                combined.contains("UNSUPPORTED_FORMAT") ||
                combined.contains("PARSER") -> ErrorCategory.NON_RECOVERABLE
            else -> ErrorCategory.UNKNOWN
        }
    }

    fun isRetryable(category: ErrorCategory): Boolean = when (category) {
        ErrorCategory.SOURCE_UNAVAILABLE,
        ErrorCategory.TRANSIENT,
        ErrorCategory.UNKNOWN -> true
        ErrorCategory.DECODER_UNSUPPORTED,
        ErrorCategory.NON_RECOVERABLE -> false
    }
}
