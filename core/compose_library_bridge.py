"""Bridge between the real Python/SQLite library and the native Compose UI.

SQLite and LibraryService remain the source of truth. This bridge only publishes
a compact derived projection for Compose and accepts narrow commands from the
native UI. Player launch is delegated back to the existing AndroidBridge so
Media3/player/session rules are not duplicated in Kotlin.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable


class ComposeLibraryBridge:
    SNAPSHOT_DIR_NAME = "reianix-compose"
    SNAPSHOT_FILE_NAME = "library.json"
    COMMAND_RESULT_DIR_NAME = "command-results"
    SCHEMA_VERSION = 1

    def __init__(self, data_dir: str, library, store, *, enabled: bool = True):
        self.data_dir = Path(data_dir)
        self.library = library
        self.store = store
        self.enabled = bool(enabled)
        self.snapshot_dir = self.data_dir / self.SNAPSHOT_DIR_NAME
        self.snapshot_path = self.snapshot_dir / self.SNAPSHOT_FILE_NAME
        self.command_result_dir = self.snapshot_dir / self.COMMAND_RESULT_DIR_NAME
        self._requested_revision = 0
        self._publish_task: asyncio.Task[Any] | None = None
        self._last_published_revision = 0
        if self.enabled:
            self.snapshot_dir.mkdir(parents=True, exist_ok=True)
            self.command_result_dir.mkdir(parents=True, exist_ok=True)

    def request_publish(self, reason: str = "unknown") -> None:
        """Coalesce projection requests onto one cancellable asyncio worker."""
        if not self.enabled:
            return
        self._requested_revision += 1
        if self._publish_task is None or self._publish_task.done():
            self._publish_task = asyncio.create_task(self._publish_loop())

    async def wait_for_idle(self) -> None:
        task = self._publish_task
        if task is not None:
            await task

    async def _publish_loop(self) -> None:
        while True:
            revision = self._requested_revision
            reason = self._pending_reason()
            await asyncio.to_thread(self._build_and_write_snapshot, revision, reason)
            self._last_published_revision = revision
            if revision == self._requested_revision:
                return

    def _pending_reason(self) -> str:
        return "compose_library_update"

    def _build_and_write_snapshot(self, revision: int, reason: str) -> None:
        generated_at = int(time.time() * 1000)
        try:
            catalog = self.library.catalog()
            folders = self.store.folders()
            source_state = self._source_state(folders)
            status = "READY" if catalog else "EMPTY"
            payload = {
                "schemaVersion": self.SCHEMA_VERSION,
                "revision": int(revision),
                "generatedAt": generated_at,
                "reason": str(reason),
                "status": status,
                "sourceState": source_state,
                "sourceAvailable": source_state == "AVAILABLE",
                "error": None,
                "animes": [self._project_anime(item) for item in catalog],
            }
        except Exception as exc:
            payload = {
                "schemaVersion": self.SCHEMA_VERSION,
                "revision": int(revision),
                "generatedAt": generated_at,
                "reason": str(reason),
                "status": "ERROR",
                "sourceState": "UNKNOWN",
                "sourceAvailable": False,
                "error": str(exc)[:500],
                "animes": [],
            }
        self._atomic_write_json(self.snapshot_path, payload)

    @staticmethod
    def _source_state(folders: Any) -> str:
        rows = [row for row in (folders or []) if isinstance(row, dict)]
        if not rows:
            return "NOT_CONFIGURED"
        active = False
        unavailable = True
        for row in rows:
            status = str(row.get("status") or "").strip().lower()
            authorization = str(row.get("authorization") or "").strip().lower()
            if status in {"granted", "available", "active"} or authorization == "granted":
                active = True
            if status not in {"revoked", "unavailable", "error", "removed"}:
                unavailable = False
        if active:
            return "AVAILABLE"
        if unavailable:
            return "UNAVAILABLE"
        return "UNKNOWN"

    @classmethod
    def _project_anime(cls, source: dict[str, Any]) -> dict[str, Any]:
        meta = source.get("meta") if isinstance(source.get("meta"), dict) else {}
        return {
            "id": source.get("id"),
            "main_title": source.get("main_title") or source.get("title"),
            "lookup_title": source.get("lookup_title"),
            "favorite": source.get("favorite"),
            "media_kind": source.get("media_kind") or meta.get("media_kind"),
            "year": source.get("year"),
            "genres": list(source.get("genres") or []),
            "genre_ids": list(source.get("genre_ids") or []),
            "meta": {
                "year": meta.get("year", source.get("year")),
                "metadata_status": meta.get("metadata_status") or source.get("metadata_status"),
                "cover_cache": meta.get("cover_cache"),
                "cover_url": meta.get("cover_url"),
                "banner_url": meta.get("banner_url"),
            },
            "seasons": [
                {
                    "season": season.get("season"),
                    "season_name": season.get("season_name"),
                    "episodes": [cls._project_episode(ep) for ep in (season.get("episodes") or [])],
                }
                for season in (source.get("seasons") or [])
                if isinstance(season, dict)
            ],
            "specials": [
                {
                    "season": group.get("season"),
                    "season_name": group.get("season_name"),
                    "episodes": [cls._project_episode(ep) for ep in (group.get("episodes") or [])],
                }
                for group in (source.get("specials") or [])
                if isinstance(group, dict)
            ],
            "media_files": [cls._project_episode(ep) for ep in (source.get("media_files") or [])],
        }

    @staticmethod
    def _project_episode(source: dict[str, Any]) -> dict[str, Any]:
        artwork = source.get("artwork") if isinstance(source.get("artwork"), dict) else {}
        return {
            "id": source.get("id"),
            "anime_id": source.get("anime_id"),
            "season": source.get("season"),
            "number": source.get("number"),
            "episode_title": source.get("episode_title") or source.get("title"),
            "file_name": source.get("file_name") or source.get("title"),
            "path": source.get("path"),
            "uri": source.get("uri"),
            "media_identity": source.get("media_identity"),
            "availability_state": source.get("availability_state"),
            "missing": source.get("missing"),
            "progress": source.get("progress"),
            "duration": source.get("duration"),
            "watched": source.get("watched"),
            "consumption_state": source.get("consumption_state"),
            "artwork_local_path": (
                source.get("artwork_local_path")
                or artwork.get("localPath")
                or artwork.get("local_path")
            ),
            "artwork_external_url": (
                source.get("artwork_external_url")
                or artwork.get("externalUrl")
                or artwork.get("external_url")
            ),
            "cover_cache": source.get("cover_cache"),
            "cover_url": source.get("cover_url"),
            "banner_url": source.get("banner_url"),
        }

    @staticmethod
    def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        os.replace(temporary, path)

    def write_command_result(
        self,
        request_id: str | None,
        action: str,
        status: str,
        *,
        error: str | None = None,
        message: str | None = None,
    ) -> None:
        if not self.enabled:
            return
        normalized_id = str(request_id or "").strip() or uuid.uuid4().hex
        payload = {
            "schemaVersion": self.SCHEMA_VERSION,
            "requestId": normalized_id,
            "action": str(action or "").strip(),
            "status": str(status or "").upper(),
            "timestamp": int(time.time() * 1000),
            "error": str(error)[:500] if error else None,
            "message": str(message)[:500] if message else None,
        }
        self._atomic_write_json(
            self.command_result_dir / f"command-{normalized_id}.json",
            payload,
        )

    @staticmethod
    async def run_command(
        command_handler: Callable[[str, dict[str, Any]], Any],
        action: str,
        payload: dict[str, Any],
    ) -> Any:
        """Keep command dispatch on the event loop while handlers own their IO."""
        return await command_handler(action, payload)
