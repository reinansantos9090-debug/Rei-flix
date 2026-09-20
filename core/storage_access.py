"""Deterministic, platform-independent storage onboarding decisions."""
from __future__ import annotations

from enum import Enum


class StorageAccessState(str, Enum):
    UNKNOWN = "unknown"
    NEEDS_MEDIA_PERMISSION = "needs_media_permission"
    MEDIA_PARTIAL = "media_partial"
    NEEDS_BROAD_STORAGE = "needs_broad_storage"
    READY = "ready"
    DECLINED = "declined"


def storage_access_state(media_access: str | None, broad_granted: bool, *, dismissed=False) -> StorageAccessState:
    """Map Android's real permission snapshot to one UI decision.

    A dismissal only suppresses automatic onboarding; it never claims a
    permission exists and Settings may always start a new request.
    """
    if dismissed:
        return StorageAccessState.DECLINED
    if media_access == "partial":
        return StorageAccessState.MEDIA_PARTIAL
    if media_access != "full":
        return StorageAccessState.NEEDS_MEDIA_PERMISSION
    if not broad_granted:
        return StorageAccessState.NEEDS_BROAD_STORAGE
    return StorageAccessState.READY
