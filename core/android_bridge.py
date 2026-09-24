"""Bridge protocol shared with the Android host without ever fabricating paths.

The Android overlay writes short JSON events into the application's private
files directory. Flet invokes it through the app-owned `reiflix://` intent;
Python periodically drains the mailbox and inserts document URIs into SQLite.
Desktop deliberately reports this bridge as unavailable.
"""
from __future__ import annotations
import json
import logging
import os
import uuid
from pathlib import Path
from urllib.parse import urlencode

import flet as ft

logger = logging.getLogger("reiflix.android")
MAILBOX = "reiflix-native-events.json"


class AndroidBridge:
    def __init__(self, data_dir: str, page=None):
        self.data_dir = Path(data_dir); self.page = page
        self.mailbox = self.data_dir / MAILBOX
        self.queue_dir = self.data_dir / "reiflix-native-events"
        self._claimed: list[Path] = []
        self._retained: set[Path] = set()
        self._recover_unacknowledged_batches()

    def _recover_unacknowledged_batches(self) -> None:
        """Return batches left in .consumed form by a previous Python process."""
        try:
            legacy = self.mailbox.with_suffix(".consumed")
            if legacy.exists() and not self.mailbox.exists():
                legacy.replace(self.mailbox)
            for consumed in sorted(self.queue_dir.glob("event-*.consumed")):
                target = consumed.with_suffix(".json")
                if target.exists():
                    continue
                consumed.replace(target)
        except OSError as exc:
            logger.warning("[ANDROID] Failed to recover unacknowledged batches: %s", exc)

    @property
    def available(self) -> bool:
        platform = getattr(self.page, "platform", None) if self.page else None
        value = getattr(platform, "value", platform)
        return (
            str(value).lower() == "android"
            or os.getenv("FLET_PLATFORM") == "android"
            or os.getenv("ANDROID_ARGUMENT") is not None
        )

    async def _launch(self, action: str, **params):
        if not self.available:
            raise RuntimeError("A ponte Android está disponível somente no APK ReiFlix.")
        request_id = uuid.uuid4().hex
        query = urlencode({"action": action, "request_id": request_id, **{k: v for k, v in params.items() if v is not None}})
        url = f"reiflix://native?{query}"
        logger.info(
            "[ANDROID_BRIDGE] request_id=%s action=%s url=%s python_callback=dispatch",
            request_id,
            action,
            url,
        )
        # Flet 0.86.5 exposes Page.launch_url(url) without a mode parameter.
        try:
            await self.page.launch_url(url)
        except Exception as exc:
            logger.exception(
                "[ANDROID_BRIDGE] launch failed request_id=%s action=%s url=%s",
                request_id,
                action,
                url,
            )
            raise RuntimeError(
                f"Falha ao enviar a ação Android '{action}' (request {request_id})."
            ) from exc
        logger.info("[ANDROID_BRIDGE] launch accepted request_id=%s action=%s", request_id, action)
        return request_id

    async def select_tree(self): return await self._launch("select_tree")
    async def rescan_tree(self, tree_uri: str): return await self._launch("scan_tree", tree_uri=tree_uri)
    async def scan_media_store(self): return await self._launch("scan_media_store")
    async def request_media_access(self): return await self._launch("request_media_access")
    async def check_storage_access(self): return await self._launch("check_storage_access")
    async def open_broad_storage_settings(self): return await self._launch("open_broad_storage_settings")
    async def scan_all_storage(self): return await self._launch("scan_all_storage")
    async def request_thumbnail(self, uri: str, size: int = 0, modified_at: int = 0): return await self._launch("extract_thumbnail", uri=uri, size=max(0, int(size)), modified_at=max(0, int(modified_at)))
    async def cancel_scans(self): return await self._launch("cancel_scan")
    async def verify_tree(self, tree_uri: str): return await self._launch("verify_tree", tree_uri=tree_uri)
    async def release_tree(self, tree_uri: str): return await self._launch("release_tree", tree_uri=tree_uri)
    async def sign_in(self, server_client_id: str): return await self._launch("google_sign_in", server_client_id=server_client_id)

    async def play(self, uri: str, title: str, position_ms: int = 0, *, can_next=False,
                   can_previous=False, autoplay=False, player_settings=None):
        normalized_uri = self.normalize_local_media_reference(uri)
        if normalized_uri is None:
            raise ValueError("A reprodução aceita somente arquivos locais ou URIs content://.")
        return await self._launch(
            "play",
            uri=normalized_uri,
            title=title,
            position_ms=max(0, int(position_ms)),
            can_next=str(bool(can_next)).lower(),
            can_previous=str(bool(can_previous)).lower(),
            autoplay=str(bool(autoplay)).lower(),
            **({
                f"setting_{key.replace('.', '_')}": str(value).lower() if isinstance(value, bool) else str(value)
                for key, value in (player_settings or {}).items()
            }),
        )

    @staticmethod
    def normalize_local_media_reference(reference: str) -> str | None:
        value = str(reference or "").strip()
        if not value:
            return None
        if os.path.isabs(value):
            try:
                return Path(value).resolve().as_uri()
            except (OSError, ValueError):
                return None
        try:
            from urllib.parse import urlsplit, urlunsplit
            parsed = urlsplit(value)
        except ValueError:
            return None
        scheme = parsed.scheme.lower()
        if scheme not in {"content", "file"}:
            return None
        if scheme == "content" and not parsed.netloc:
            return None
        normalized = urlunsplit((scheme, parsed.netloc, parsed.path, parsed.query, parsed.fragment))
        return normalized or None

    @classmethod
    def is_local_media_reference(cls, uri: str) -> bool:
        return cls.normalize_local_media_reference(uri) is not None

    @staticmethod
    def _event_time(event: dict) -> float:
        for key in ("createdAt", "timestamp"):
            value = event.get(key)
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return float("inf")

    def drain(self) -> list[dict]:
        if self._claimed:
            return []
        events: list[dict] = []
        claimed: list[Path] = []
        try:
            self.queue_dir.mkdir(parents=True, exist_ok=True)
            legacy = self.mailbox.with_suffix(".consumed")
            if self.mailbox.exists():
                try:
                    self.mailbox.replace(legacy)
                except OSError as exc:
                    logger.error("[ANDROID] Failed to claim legacy native mailbox: %s", exc)
                else:
                    try:
                        payload = json.loads(legacy.read_text(encoding="utf-8"))
                        if isinstance(payload, list):
                            events.extend(event for event in payload if isinstance(event, dict))
                        elif isinstance(payload, dict):
                            events.append(payload)
                        claimed.append(legacy)
                    except (OSError, json.JSONDecodeError) as exc:
                        logger.error("[ANDROID] Invalid legacy native mailbox batch discarded: %s", exc)
                        legacy.unlink(missing_ok=True)
            for source in sorted(self.queue_dir.glob("event-*.json")):
                consumed = source.with_suffix(".consumed")
                try:
                    source.replace(consumed)
                except OSError:
                    continue
                try:
                    payload = json.loads(consumed.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    logger.error("[ANDROID] Invalid native mailbox event discarded: %s (%s)", consumed.name, exc)
                    consumed.unlink(missing_ok=True)
                    continue
                if isinstance(payload, list):
                    events.extend(event for event in payload if isinstance(event, dict))
                elif isinstance(payload, dict):
                    events.append(payload)
                claimed.append(consumed)
            indexed = list(enumerate(events))
            indexed.sort(key=lambda item: (self._event_time(item[1]), item[0]))
            self._claimed = claimed
            self._retained = set()
            return [event for _, event in indexed]
        except OSError as exc:
            # Never discard a claimed event solely because draining encountered I/O failure.
            logger.error("[ANDROID] Native mailbox drain failed; claimed events will be restored/retried: %s", exc)
            for path in claimed:
                try:
                    if path.suffix == ".consumed":
                        path.replace(path.with_suffix(".json"))
                except OSError as restore_exc:
                    logger.warning("[ANDROID] Failed to restore native event %s: %s", path.name, restore_exc)
            self._claimed = []
            self._retained = set()
            return []

    def requeue_event_ids(self, event_ids: set[str]) -> None:
        wanted = {str(item).strip() for item in event_ids if str(item).strip()}
        if not wanted:
            return
        for consumed in list(self._claimed):
            try:
                payload = json.loads(consumed.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self._retained.add(consumed)
                continue
            if isinstance(payload, dict) and str(payload.get("eventId") or "").strip() in wanted:
                try:
                    consumed.replace(consumed.with_suffix(".json"))
                except OSError as exc:
                    self._retained.add(consumed)
                    logger.warning("[ANDROID] Failed to requeue native event %s: %s", consumed.name, exc)

    def acknowledge(self) -> None:
        if not self._claimed:
            return
        for consumed in self._claimed:
            if consumed in self._retained:
                continue
            try:
                consumed.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("[ANDROID] Failed to acknowledge native event %s: %s", consumed.name, exc)
        self._claimed = []
        self._retained = set()


__all__ = ["AndroidBridge"]
