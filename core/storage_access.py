"""Deterministic storage authorization states.

Android is authoritative for current grants. Python consumes the native
capability snapshot for UI, onboarding, Settings and scan orchestration.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


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


class ScanUiState(str, Enum):
    IDLE = "IDLE"
    CHECKING = "CHECKING"
    SCANNING = "SCANNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    WAITING_FOR_MEDIASTORE = "WAITING_FOR_MEDIASTORE"
    VOLUME_UNAVAILABLE = "VOLUME_UNAVAILABLE"


def scan_ui_state_from_native(status: str | None, *, errors: bool = False, cancelled: bool = False,
                              waiting_for_mediastore: bool = False, volume_available: bool = True) -> ScanUiState:
    if waiting_for_mediastore:
        return ScanUiState.WAITING_FOR_MEDIASTORE
    if not volume_available:
        return ScanUiState.VOLUME_UNAVAILABLE
    value = str(status or "").strip().upper()
    if cancelled or value in {"CANCELLED", "CANCELED"}:
        return ScanUiState.CANCELLED
    if value in {"FAILED", "ERROR"}:
        return ScanUiState.FAILED
    if value in {"PARTIAL", "UNAVAILABLE"} or errors:
        return ScanUiState.PARTIAL
    if value in {"COMPLETED", "EMPTY_COMPLETE"}:
        return ScanUiState.COMPLETED
    if value in {"CHECKING"}:
        return ScanUiState.CHECKING
    if value in {"SCANNING", "RUNNING", "STARTED"}:
        return ScanUiState.SCANNING
    return ScanUiState.IDLE


@dataclass(frozen=True)
class StorageCapabilities:
    media_read_state: str = "denied"
    broad_storage_state: str = "unavailable"
    saf_roots: tuple[str, ...] = ()
    removable_volumes: tuple[str, ...] = ()
    scanner_capabilities: frozenset[str] = frozenset()
    reconciliation_capabilities: frozenset[str] = frozenset()
    lifecycle_state: str = "unknown"
    api: int | None = None

    @classmethod
    def unknown(cls) -> "StorageCapabilities":
        return cls()

    @classmethod
    def from_native(cls, payload: dict | None) -> "StorageCapabilities":
        if not isinstance(payload, dict):
            return cls.unknown()
        media = str(payload.get("mediaReadState") or "denied").casefold()
        if media not in {"denied", "partial", "full"}:
            media = "denied"
        broad = str(payload.get("broadStorageState") or "unavailable").casefold()
        if broad not in {"available", "unavailable"}:
            broad = "unavailable"
        saf = tuple(dict.fromkeys(
            str(value).strip() for value in (payload.get("safRoots") or [])
            if str(value).strip()
        ))
        removable = tuple(dict.fromkeys(
            str(value).strip() for value in (payload.get("removableVolumes") or [])
            if str(value).strip()
        ))
        scanners = frozenset(
            str(value).strip() for value in (payload.get("scannerCapabilities") or [])
            if str(value).strip()
        )
        reconciliators = frozenset(
            str(value).strip() for value in (payload.get("reconciliationCapabilities") or [])
            if str(value).strip()
        )
        try:
            api = int(payload["api"]) if payload.get("api") is not None else None
        except (TypeError, ValueError):
            api = None
        return cls(
            media_read_state=media,
            broad_storage_state=broad,
            saf_roots=saf,
            removable_volumes=removable,
            scanner_capabilities=scanners,
            reconciliation_capabilities=reconciliators,
            lifecycle_state=str(payload.get("lifecycleState") or "unknown").casefold(),
            api=api,
        )

    def as_mapping(self) -> dict[str, object]:
        return {
            "mediaReadState": self.media_read_state,
            "broadStorageState": self.broad_storage_state,
            "safRoots": list(self.saf_roots),
            "removableVolumes": list(self.removable_volumes),
            "scannerCapabilities": list(self.scanner_capabilities),
            "reconciliationCapabilities": list(self.reconciliation_capabilities),
            "lifecycleState": self.lifecycle_state,
            "api": self.api,
        }

    def get(self, key: str, default=None):
        if not isinstance(key, str):
            return default
        mapping = {
            "mediaReadState": "media_read_state",
            "broadStorageState": "broad_storage_state",
            "safRoots": "saf_roots",
            "removableVolumes": "removable_volumes",
            "scannerCapabilities": "scanner_capabilities",
            "reconciliationCapabilities": "reconciliation_capabilities",
            "lifecycleState": "lifecycle_state",
            "api": "api",
        }
        attr = mapping.get(key, key)
        if hasattr(self, attr):
            return getattr(self, attr, default)
        return default

    @property
    def known(self) -> bool:
        return self.api is not None or self.lifecycle_state != "unknown"

    def can_scan(self, source: str) -> bool:
        if not isinstance(source, str):
            return False
        value = source.strip().casefold()
        if value == "mediastore":
            return self.media_read_state in {"partial", "full"}
        if value == "broad-storage":
            return self.broad_storage_state == "available"
        if value == "saf":
            return bool(self.saf_roots)
        return value in {str(item).strip().casefold() for item in self.scanner_capabilities}

    def can_reconcile(self, source: str) -> bool:
        if not isinstance(source, str):
            return False
        value = source.strip().casefold()
        if value == "mediastore":
            return self.media_read_state == "full"
        if value == "broad-storage":
            return self.broad_storage_state == "available"
        if value == "saf":
            return bool(self.saf_roots)
        return value in {str(item).strip().casefold() for item in self.reconciliation_capabilities}


def _mapping_from_snapshot(snapshot: Any) -> dict[str, Any]:
    if snapshot is None:
        return {}
    if isinstance(snapshot, dict):
        return snapshot
    if isinstance(snapshot, StorageCapabilities):
        return snapshot.as_mapping()
    candidate = getattr(snapshot, "as_mapping", None)
    if callable(candidate):
        mapped = candidate()
        if isinstance(mapped, dict):
            return mapped
    candidate = getattr(snapshot, "__dict__", None)
    if isinstance(candidate, dict):
        return candidate
    return {}


def normalize_storage_snapshot(snapshot: Any) -> StorageCapabilities:
    if snapshot is None:
        return StorageCapabilities.unknown()
    if isinstance(snapshot, StorageCapabilities):
        return snapshot
    payload = _mapping_from_snapshot(snapshot)
    return StorageCapabilities.from_native(payload)


def storage_access_state(media_access: str | None, broad_granted: bool, saf_available: bool = False, *, dismissed: bool = False) -> StorageAccessState:
    access = str(media_access or "denied").casefold()
    if dismissed:
        return StorageAccessState.DECLINED
    if access == "full":
        return StorageAccessState.READY
    if access == "partial":
        return StorageAccessState.MEDIA_PARTIAL
    if broad_granted and saf_available:
        return StorageAccessState.READY
    if broad_granted:
        return StorageAccessState.BROAD_STORAGE_AVAILABLE
    if saf_available:
        return StorageAccessState.SAF_AVAILABLE
    return StorageAccessState.NEEDS_MEDIA_PERMISSION


__all__ = [
    "StorageAccessState",
    "ScanUiState",
    "scan_ui_state_from_native",
    "StorageCapabilities",
    "normalize_storage_snapshot",
    "storage_access_state",
]
