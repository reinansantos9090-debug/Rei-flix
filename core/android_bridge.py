"""Bridge protocol shared with the Android host without ever fabricating paths.

The Android overlay writes short JSON events into the application's private
files directory.  Flet invokes it through the app-owned `reiflix://` intent;
Python periodically drains the mailbox and inserts document URIs into SQLite.
Desktop deliberately reports this bridge as unavailable.
"""
from __future__ import annotations
import json
import logging
import os
from pathlib import Path
from urllib.parse import urlencode

logger = logging.getLogger("reiflix.android")
MAILBOX = "reiflix-native-events.json"

class AndroidBridge:
    def __init__(self, data_dir: str, page=None):
        self.data_dir = Path(data_dir); self.page = page
        self.mailbox = self.data_dir / MAILBOX

    @property
    def available(self) -> bool:
        return bool(self.page and getattr(self.page, "platform", None) and str(self.page.platform).lower() == "android")

    def _launch(self, action: str, **params):
        if not self.available:
            raise RuntimeError("A ponte Android está disponível somente no APK ReiFlix.")
        query = urlencode({"action": action, **{k: v for k, v in params.items() if v is not None}})
        self.page.launch_url(f"reiflix://native?{query}")

    def select_tree(self): self._launch("select_tree")
    def rescan_tree(self, tree_uri: str): self._launch("scan_tree", tree_uri=tree_uri)
    def sign_in(self, server_client_id: str): self._launch("google_sign_in", server_client_id=server_client_id)
    def play(self, uri: str, title: str, position_ms: int = 0, *, can_next=False, can_previous=False):
        self._launch("play", uri=uri, title=title, position_ms=max(0, int(position_ms)),
                     can_next=str(bool(can_next)).lower(), can_previous=str(bool(can_previous)).lower())

    def drain(self) -> list[dict]:
        """Atomically consume events. Native events contain no tokens/secrets."""
        consumed = self.mailbox.with_suffix(".consumed")
        try:
            if not self.mailbox.exists(): return []
            self.mailbox.replace(consumed)
            events = json.loads(consumed.read_text(encoding="utf-8"))
            # Ignore malformed/unknown payload shapes; the event loop must not
            # be able to crash because a native queue contains one bad entry.
            return [event for event in events if isinstance(event, dict)] if isinstance(events, list) else []
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("[ANDROID] Failed to read native bridge events: %s", exc)
            return []
        finally:
            try:
                consumed.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("[ANDROID] Failed to remove consumed mailbox: %s", exc)
