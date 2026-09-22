"""Deterministic storage authorization states.

Android is authoritative for current grants. Python consumes the native
capability snapshot for UI, onboarding, Settings and scan orchestration.
"""
from __future__ import annotations

from dataclasses import dataclass
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
        return source in self.scanner_capabilities

    def can_reconcile(self, source: str) -> bool:
        return source in self.reconciliation_capabilities


def normalize_storage_snapshot(snapshot: object) -> StorageCapabilities:
    """Normalize either a legacy dict payload or a typed StorageCapabilities object."""
    if snapshot is None:
        return StorageCapabilities.unknown()
    if isinstance(snapshot, StorageCapabilities):
        return snapshot
    if isinstance(snapshot, dict):
        return StorageCapabilities.from_native(snapshot)

    mapping: dict[str, object] = {}
    for dict_key, attr_names in {
        "mediaReadState": ("media_read_state", "mediaReadState"),
        "broadStorageState": ("broad_storage_state", "broadStorageState"),
        "safRoots": ("saf_roots", "safRoots"),
        "removableVolumes": ("removable_volumes", "removableVolumes"),
        "scannerCapabilities": ("scanner_capabilities", "scannerCapabilities"),
        "reconciliationCapabilities": ("reconciliation_capabilities", "reconciliationCapabilities"),
        "lifecycleState": ("lifecycle_state", "lifecycleState"),
        "api": ("api",),
    }.items():
        for name in attr_names:
            if hasattr(snapshot, name):
                value = getattr(snapshot, name)
                if value is not None:
                    mapping[dict_key] = value
                break
        else:
            if hasattr(snapshot, "get") and callable(snapshot.get):
                value = snapshot.get(dict_key)
                if value is not None:
                    mapping[dict_key] = value
    return StorageCapabilities.from_native(mapping)


def storage_access_state(
    media_access: str | None,
    broad_granted: bool,
    saf_available: bool = False,
    *,
    dismissed: bool = False,
    require_broad: bool = False,
) -> StorageAccessState:
    if dismissed:
        return StorageAccessState.DECLINED
    access = str(media_access or "denied").casefold()
    if require_broad and not broad_granted:
        return StorageAccessState.NEEDS_BROAD_STORAGE
    if saf_available or broad_granted:
        return StorageAccessState.READY
    if access == "partial":
        return StorageAccessState.MEDIA_PARTIAL
    if access != "full":
        return StorageAccessState.NEEDS_MEDIA_PERMISSION
    return StorageAccessState.READY


def storage_source_states(
    media_access: str | None,
    broad_granted: bool,
    saf_uris: list[str] | tuple[str, ...] | None = None,
    *,
    saf_revoked: bool = False,
) -> dict[str, str]:
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
        "effective": storage_access_state(media_access, broad_granted, bool(saf_uris)).value,
    }
