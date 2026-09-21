package com.reiflix.reiflix_local

/**
 * Single native authorization model.
 *
 * Android framework APIs remain authoritative; this model only translates
 * already-observed facts into explicit source capabilities and lifecycle state.
 */
enum class MediaAccessLevel { DENIED, PARTIAL, FULL }
enum class SafAccessLevel { UNKNOWN, AVAILABLE, REVOKED }
enum class BroadStorageAccessLevel { AVAILABLE, UNAVAILABLE }

enum class StorageLifecycleState {
    UNKNOWN, CHECKING, DENIED, PARTIAL, FULL, REQUESTING, RETURNED,
    REVALIDATED, SCAN_CAPABLE, NOT_SCAN_CAPABLE,
}

data class StorageCapabilities(
    val mediaReadState: MediaAccessLevel,
    val broadStorageState: BroadStorageAccessLevel,
    val safRoots: List<String>,
    val removableVolumes: List<String>,
    val scannerCapabilities: Set<String>,
    val lifecycleState: StorageLifecycleState,
) {
    fun canScan(source: String): Boolean = source in scannerCapabilities
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

    fun safAccess(configuredTreeUri: String?, persistedReadUris: Collection<String>): SafAccessLevel {
        val tree = configuredTreeUri?.trim().takeUnless { it.isNullOrEmpty() }
            ?: return SafAccessLevel.UNKNOWN
        return if (persistedReadUris.contains(tree)) SafAccessLevel.AVAILABLE else SafAccessLevel.REVOKED
    }

    fun broadAccess(hasAllFilesAccess: Boolean): BroadStorageAccessLevel =
        if (hasAllFilesAccess) BroadStorageAccessLevel.AVAILABLE else BroadStorageAccessLevel.UNAVAILABLE

    fun deriveLifecycleState(
        mediaAccess: MediaAccessLevel,
        broadAccess: BroadStorageAccessLevel,
        safRoots: Collection<String>,
    ): StorageLifecycleState {
        val scanCapable = canScanMediaStore(mediaAccess) ||
            broadAccess == BroadStorageAccessLevel.AVAILABLE ||
            safRoots.isNotEmpty()
        return when {
            scanCapable -> StorageLifecycleState.SCAN_CAPABLE
            mediaAccess == MediaAccessLevel.FULL -> StorageLifecycleState.FULL
            mediaAccess == MediaAccessLevel.PARTIAL -> StorageLifecycleState.PARTIAL
            else -> StorageLifecycleState.NOT_SCAN_CAPABLE
        }
    }

    fun capabilities(
        mediaAccess: MediaAccessLevel,
        broadAccess: BroadStorageAccessLevel,
        safRoots: Collection<String> = emptyList(),
        removableVolumes: Collection<String> = emptyList(),
        lifecycleState: StorageLifecycleState? = null,
    ): StorageCapabilities {
        val normalizedSaf = safRoots.map(String::trim).filter(String::isNotEmpty).distinct()
        val normalizedVolumes = removableVolumes.map(String::trim).filter(String::isNotEmpty).distinct()
        val scanners = linkedSetOf<String>()
        if (canScanMediaStore(mediaAccess)) scanners += "mediastore"
        if (broadAccess == BroadStorageAccessLevel.AVAILABLE) scanners += "broad-storage"
        if (normalizedSaf.isNotEmpty()) scanners += "saf"
        return StorageCapabilities(
            mediaReadState = mediaAccess,
            broadStorageState = broadAccess,
            safRoots = normalizedSaf,
            removableVolumes = normalizedVolumes,
            scannerCapabilities = scanners,
            lifecycleState = lifecycleState ?: deriveLifecycleState(mediaAccess, broadAccess, normalizedSaf),
        )
    }

    fun canScanMediaStore(access: MediaAccessLevel): Boolean =
        access == MediaAccessLevel.FULL || access == MediaAccessLevel.PARTIAL

    fun canReconcileMediaStore(access: MediaAccessLevel): Boolean =
        access == MediaAccessLevel.FULL

    fun canScanSaf(access: SafAccessLevel): Boolean =
        access == SafAccessLevel.AVAILABLE

    fun canScanBroad(hasAllFilesAccess: Boolean): Boolean =
        hasAllFilesAccess
}
