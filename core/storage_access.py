"""Deterministic storage authorization states shared by Android onboarding and scanners.
The Android side remains the authority for current permission grants; Python only
interprets snapshots and persisted SAF inventory.
"""
from __future__ import annotations

from enum import Enum


class StorageAccessState(str, Enum):
    UNKNOWN = "unknown"
    MEDIA_DENIED = "media_denied"
    MEDIA_PARTIAL = "media_partial"
    MEDIA_FULL = "media_full"
    SAF_AVAILABLE = "saf_available"
    SAF_REVOKED = "saf_revoked"
    BROAD_STORAGE_AVAILABLE = "broad_storage_available"
    BROAD_STORAGE_UNAVAILABLE = "broad_storage_unavailable"
    NEEDS_MEDIA_PERMISSION = "needs_media_permission"
    NEEDS_BROAD_STORAGE = "needs_broad_storage"
    READY = "ready"
    DECLINED = "declined"


def storage_access_state(
    media_access: str | None,
    broad_granted: bool,
    *,
    dismissed: bool = False,
    require_broad: bool = False,
) -> StorageAccessState:
    """Map an Android snapshot to one deterministic onboarding decision.

    require_broad is deliberately opt-in: MediaStore/SAF can satisfy the
    core local-library flow, so broad filesystem access is never silently made
    a prerequisite.
    """
    if dismissed:
        return StorageAccessState.DECLINED

    access = str(media_access or "denied").casefold()
    if access == "partial":
        return StorageAccessState.MEDIA_PARTIAL
    if access != "full":
        return StorageAccessState.NEEDS_MEDIA_PERMISSION
    if require_broad and not broad_granted:
        return StorageAccessState.NEEDS_BROAD_STORAGE
    return StorageAccessState.READY


def storage_source_states(
    media_access: str | None,
    broad_granted: bool,
    saf_uris: list[str] | tuple[str, ...] | None = None,
    *,
    saf_revoked: bool = False,
) -> dict[str, str]:
    """Represent independent sources without collapsing their authorization."""
    media = str(media_access or "denied").casefold()
    media_state = {
        "full": StorageAccessState.MEDIA_FULL.value,
        "partial": StorageAccessState.MEDIA_PARTIAL.value,
    }.get(media, StorageAccessState.MEDIA_DENIED.value)

    broad_state = (
        StorageAccessState.BROAD_STORAGE_AVAILABLE.value
        if bool(broad_granted)
        else StorageAccessState.BROAD_STORAGE_UNAVAILABLE.value
    )

    if saf_uris:
        saf_state = StorageAccessState.SAF_AVAILABLE.value
    elif saf_revoked:
        saf_state = StorageAccessState.SAF_REVOKED.value
    else:
        saf_state = StorageAccessState.UNKNOWN.value

    return {
        "media": media_state,
        "saf": saf_state,
        "broad": broad_state,
        "effective": storage_access_state(media_access, broad_granted).value,
    }
