"""Bridge protocol shared with the Android host without ever fabricating paths.

The Android overlay writes short JSON events into the application's private
files directory. Flet invokes it through the app-owned `reiflix://` intent;
Python periodically drains the mailbox and inserts document URIs into SQLite.
Desktop deliberately reports this bridge as unavailable.
"""
from __future__ import annotations
import json
import logging
from contextlib import contextmanager
import os
from pathlib import Path
from urllib.parse import urlencode

import flet as ft

logger = logging.getLogger("reiflix.android")
MAILBOX = "reiflix-native-events.json"

class AndroidBridge:
    def __init__(self, data_dir: str, page=None):
        self.data_dir = Path(data_dir); self.page = page
        self.mailbox = self.data_dir / MAILBOX
        self.lock_file = self.data_dir / f"{MAILBOX}.lock"
        self._claimed = False

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
        query = urlencode({"action": action, **{k: v for k, v in params.items() if v is not None}})
        url = f"reiflix://native?{query}"
        # Flet's URL launcher is asynchronous. Without await, Android never
        # receives the custom-scheme intent.
        await self.page.launch_url(
            url, mode=ft.LaunchMode.EXTERNAL_NON_BROWSER_APPLICATION
        )

    async def select_tree(self): await self._launch("select_tree")
    async def rescan_tree(self, tree_uri: str): await self._launch("scan_tree", tree_uri=tree_uri)
    async def verify_tree(self, tree_uri: str): await self._launch("verify_tree", tree_uri=tree_uri)
    async def sign_in(self, server_client_id: str): await self._launch("google_sign_in", server_client_id=server_client_id)
    async def play(self, uri: str, title: str, position_ms: int = 0, *, can_next=False, can_previous=False):
        if not self.is_local_media_reference(uri):
            raise ValueError("A reprodução aceita somente arquivos locais ou URIs content://.")
        await self._launch("play", uri=uri, title=title, position_ms=max(0, int(position_ms)),
                           can_next=str(bool(can_next)).lower(), can_previous=str(bool(can_previous)).lower())

    @staticmethod
    def is_local_media_reference(uri: str) -> bool:
        # Android library entries come from SAF and must remain content:// URIs.
        # Reject file:// and raw filesystem paths so the native player cannot
        # be used as a second, unscoped storage-access path.
        return bool(uri) and uri.startswith("content://")

    @contextmanager
    def _mailbox_lock(self):
        # Android and Python share this lock file so a claim/ack cannot race
        # with NativeMailbox read-modify-write publication.
        import fcntl
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with self.lock_file.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def drain(self) -> list[dict]:
        consumed = self.mailbox.with_suffix(".consumed")
        if self._claimed:
            return []
        try:
            with self._mailbox_lock():
                if consumed.exists():
                    pass
                elif self.mailbox.exists():
                    self.mailbox.replace(consumed)
                else:
                    return []
                events = json.loads(consumed.read_text(encoding="utf-8"))
                if not isinstance(events, list):
                    consumed.unlink(missing_ok=True)
                    return []
                self._claimed = True
                return [event for event in events if isinstance(event, dict)]
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("[ANDROID] Failed to read native bridge events: %s", exc)
            try:
                consumed.unlink(missing_ok=True)
            except OSError:
                pass
            return []

    def acknowledge(self) -> None:
        if not self._claimed:
            return
        try:
            with self._mailbox_lock():
                self.mailbox.with_suffix(".consumed").unlink(missing_ok=True)
                self._claimed = False
        except OSError as exc:
            logger.warning("[ANDROID] Failed to acknowledge native events: %s", exc)
