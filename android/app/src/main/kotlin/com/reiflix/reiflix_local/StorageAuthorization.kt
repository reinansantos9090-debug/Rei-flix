package com.reiflix.reiflix_local

/**
 * Pure storage authorization model used by native tests and diagnostic code.
 *
 * The actual Android permission APIs remain the source of truth; this class
 * only maps already-observed facts into explicit states and scanner gates.
 */
enum class MediaAccessLevel {
    DENIED,
    PARTIAL,
    FULL,
}

enum class SafAccessLevel {
    UNKNOWN,
    AVAILABLE,
    REVOKED,
}

object StorageAuthorization {
    fun mediaAccess(
        apiLevel: Int,
        readExternalStorage: Boolean = false,
        readMediaVideo: Boolean = false,
        readSelectedVisualMedia: Boolean = false,
    ): MediaAccessLevel = when {
        apiLevel <= 32 ->
            if (readExternalStorage) MediaAccessLevel.FULL else MediaAccessLevel.DENIED
        apiLevel >= 34 ->
            when {
                readMediaVideo -> MediaAccessLevel.FULL
                readSelectedVisualMedia -> MediaAccessLevel.PARTIAL
                else -> MediaAccessLevel.DENIED
            }
        else ->
            if (readMediaVideo) MediaAccessLevel.FULL else MediaAccessLevel.DENIED
    }

    fun safAccess(
        configuredTreeUri: String?,
        persistedReadUris: Collection<String>,
    ): SafAccessLevel {
        val tree = configuredTreeUri?.trim().takeUnless { it.isNullOrEmpty() }
            ?: return SafAccessLevel.UNKNOWN
        return if (persistedReadUris.contains(tree)) {
            SafAccessLevel.AVAILABLE
        } else {
            SafAccessLevel.REVOKED
        }
    }

    fun broadAccess(hasAllFilesAccess: Boolean): SafAccessLevel =
        if (hasAllFilesAccess) SafAccessLevel.AVAILABLE else SafAccessLevel.REVOKED

    fun canScanMediaStore(access: MediaAccessLevel): Boolean =
        access != MediaAccessLevel.DENIED

    fun canScanSaf(access: SafAccessLevel): Boolean =
        access == SafAccessLevel.AVAILABLE

    fun canScanBroad(hasAllFilesAccess: Boolean): Boolean =
        hasAllFilesAccess
}
