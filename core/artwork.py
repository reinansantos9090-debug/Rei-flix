"""Local-first artwork discovery, persistence and deterministic resolution."""
from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path


ARTWORK_TYPES = {"poster", "backdrop", "thumbnail", "season_poster", "episode_thumbnail"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif"}

_SOURCE_PRIORITY = {"manual": 400, "local": 300, "cache": 200, "anilist": 100}
_NAME_HINTS = {
    "poster": {"poster", "cover", "folder", "front"},
    "backdrop": {"backdrop", "fanart", "banner", "background"},
    "thumbnail": {"thumbnail", "thumb", "episode"},
    "season_poster": {"season", "season-poster", "seasonposter"},
    "episode_thumbnail": {"thumbnail", "thumb", "episode"},
}


class ArtworkEngine:
    """Keeps artwork in the existing LibraryStore SQLite/cache domain.

    Videos remain local-only. External artwork is accepted only from metadata
    already resolved by the existing Metadata Engine/AniList adapter.
    """

    SCHEMA_VERSION = 21

    def __init__(self, store):
        self.store = store
        self._ensure_schema()

    def _ensure_schema(self):
        with self.store._conn() as con:
            con.execute(
                """CREATE TABLE IF NOT EXISTS artwork (
                    id INTEGER PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    artwork_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    source_ref TEXT,
                    local_path TEXT,
                    external_url TEXT,
                    manual INTEGER NOT NULL DEFAULT 0,
                    priority INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'ready',
                    discovered_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    last_attempt_at REAL,
                    failure_count INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(entity_type, entity_id, artwork_type, source_ref)
                )"""
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_artwork_entity ON artwork(entity_type, entity_id, artwork_type, priority DESC)"
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_artwork_status ON artwork(status, last_attempt_at)"
            )
            con.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (self.SCHEMA_VERSION, time.time()),
            )

    @staticmethod
    def _entity(entity_type, entity_id):
        if entity_type not in {"anime", "movie", "season", "episode", "special"}:
            raise ValueError("tipo de entidade inválido")
        if entity_id is None:
            raise ValueError("entity_id é obrigatório")
        return entity_type

    @staticmethod
    def _type(artwork_type):
        if artwork_type not in ARTWORK_TYPES:
            raise ValueError("tipo de artwork inválido")
        return artwork_type

    def _upsert(self, *, entity_type, entity_id, artwork_type, source,
                source_ref=None, local_path=None, external_url=None,
                manual=False, status="ready", failure_count=0):
        now = time.time()
        priority = _SOURCE_PRIORITY.get(source, 0)
        with self.store._conn() as con:
            row = con.execute(
                """SELECT id, discovered_at FROM artwork
                   WHERE entity_type=? AND entity_id=? AND artwork_type=? AND source_ref IS ?""",
                (entity_type, str(entity_id), artwork_type, source_ref),
            ).fetchone()
            if row:
                con.execute(
                    """UPDATE artwork SET source=?,local_path=?,external_url=?,manual=?,
                       priority=?,status=?,updated_at=?,failure_count=? WHERE id=?""",
                    (source, local_path, external_url, int(manual), priority, status,
                     now, failure_count, row["id"]),
                )
                return row["id"]
            cur = con.execute(
                """INSERT INTO artwork(entity_type,entity_id,artwork_type,source,source_ref,
                   local_path,external_url,manual,priority,status,discovered_at,updated_at,
                   failure_count) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (entity_type, str(entity_id), artwork_type, source, source_ref, local_path,
                 external_url, int(manual), priority, status, now, now, failure_count),
            )
            return cur.lastrowid

    def add_local(self, entity_type, entity_id, artwork_type, path, *, manual=False):
        artwork_type = self._type(artwork_type)
        path = os.path.abspath(os.fspath(path))
        if not os.path.isfile(path) or Path(path).suffix.casefold() not in IMAGE_EXTENSIONS:
            return False
        self._upsert(
            entity_type=self._entity(entity_type, entity_id),
            entity_id=entity_id,
            artwork_type=artwork_type,
            source="manual" if manual else "local",
            source_ref=path.casefold(),
            local_path=path,
            manual=manual,
        )
        if not manual and entity_type in {"anime", "movie"} and artwork_type == "poster":
            with self.store._conn() as con:
                protected = con.execute(
                    "SELECT 1 FROM artwork WHERE entity_type=? AND entity_id=? AND artwork_type=? AND manual=1 LIMIT 1",
                    (str(entity_type), str(entity_id), artwork_type),
                ).fetchone()
                if not protected:
                    con.execute("UPDATE anime SET cover_cache=? WHERE id=?", (path, int(entity_id)))
        return True

    def set_manual(self, entity_type, entity_id, artwork_type, *, path=None, external_url=None):
        artwork_type = self._type(artwork_type)
        if path is None and not external_url:
            raise ValueError("artwork manual exige path ou external_url")
        if path is not None and not os.path.isfile(path):
            raise FileNotFoundError(path)
        source_ref = os.path.abspath(path).casefold() if path else external_url
        self._upsert(
            entity_type=self._entity(entity_type, entity_id),
            entity_id=entity_id,
            artwork_type=artwork_type,
            source="manual",
            source_ref=source_ref,
            local_path=os.path.abspath(path) if path else None,
            external_url=external_url,
            manual=True,
        )
        return self.resolve(entity_type, entity_id, artwork_type, allow_network=False)

    def clear_manual(self, entity_type, entity_id, artwork_type):
        with self.store._conn() as con:
            con.execute(
                "DELETE FROM artwork WHERE entity_type=? AND entity_id=? AND artwork_type=? AND manual=1",
                (self._entity(entity_type, entity_id), str(entity_id), self._type(artwork_type)),
            )

    def _candidates(self, artwork_type, directory, stem=None):
        directory = Path(directory)
        if not directory.is_dir():
            return []
        hints = _NAME_HINTS[artwork_type]
        wanted = []
        for entry in sorted(directory.iterdir(), key=lambda p: p.name.casefold()):
            if not entry.is_file() or entry.suffix.casefold() not in IMAGE_EXTENSIONS:
                continue
            base = entry.stem.casefold().strip()
            normalized = base.replace("_", "-").replace(" ", "-")
            exact = stem and base == stem.casefold()
            hinted = base in hints or normalized in hints
            if exact or hinted:
                wanted.append((0 if exact else 1, str(entry)))
        return [path for _, path in sorted(wanted, key=lambda item: (item[0], item[1].casefold()))]

    def _episode_row(self, episode_id):
        with self.store._conn() as con:
            row = con.execute("SELECT * FROM episodes WHERE id=?", (int(episode_id),)).fetchone()
            if not row:
                return None
            return dict(row)

    def discover_episode(self, episode_id):
        row = self._episode_row(episode_id)
        if not row:
            return []
        path = row["path"]
        if not isinstance(path, str) or not path.startswith("/") or not os.path.isfile(path):
            return []
        directory = Path(path).parent
        stem = Path(path).stem
        found = []
        for kind in ("episode_thumbnail", "thumbnail"):
            for candidate in self._candidates(kind, directory, stem):
                if self.add_local("episode", episode_id, kind, candidate):
                    found.append(candidate)
        return found

    def discover_anime(self, anime_id):
        with self.store._conn() as con:
            rows = con.execute(
                "SELECT path,season,episode_type FROM episodes WHERE anime_id=? AND missing=0",
                (int(anime_id),),
            ).fetchall()
        directories = []
        for row in rows:
            path = row["path"]
            if isinstance(path, str) and path.startswith("/") and os.path.isfile(path):
                directory = Path(path).parent
                if directory not in directories:
                    directories.append(directory)
        found = []
        for directory in directories:
            for kind in ("poster", "backdrop"):
                for candidate in self._candidates(kind, directory):
                    if self.add_local("anime", anime_id, kind, candidate):
                        found.append(candidate)
        return found

    def discover_season(self, anime_id, season):
        season = int(season)
        with self.store._conn() as con:
            rows = con.execute(
                "SELECT path FROM episodes WHERE anime_id=? AND season=? AND missing=0",
                (int(anime_id), season),
            ).fetchall()
        found = []
        entity_id = f"{anime_id}:season:{season}"
        for row in rows:
            path = row["path"]
            if not isinstance(path, str) or not path.startswith("/") or not os.path.isfile(path):
                continue
            for candidate in self._candidates("season_poster", Path(path).parent):
                if self.add_local("season", entity_id, "season_poster", candidate):
                    found.append(candidate)
        return found

    def sync_anime_metadata(self, anime_id, metadata):
        """Register AniList artwork references without creating a second cache."""
        if not metadata:
            return
        cover_cache = (metadata.get("cover_cache") or "").strip()
        cover_url = (metadata.get("cover_url") or "").strip()
        banner_url = (metadata.get("banner_url") or "").strip()
        if cover_cache and os.path.isfile(cover_cache):
            self._upsert(entity_type="anime", entity_id=anime_id, artwork_type="poster",
                         source="cache", source_ref=cover_url or cover_cache,
                         local_path=cover_cache, external_url=cover_url)
        elif cover_url:
            self._upsert(entity_type="anime", entity_id=anime_id, artwork_type="poster",
                         source="anilist", source_ref=cover_url, external_url=cover_url,
                         status="available")
        if banner_url:
            self._upsert(entity_type="anime", entity_id=anime_id, artwork_type="backdrop",
                         source="anilist", source_ref=banner_url, external_url=banner_url,
                         status="available")
        self.discover_anime(anime_id)

    def reindex_episode(self, episode_id):
        found = self.discover_episode(episode_id)
        row = self._episode_row(episode_id)
        if row:
            self.discover_anime(row["anime_id"])
            if row.get("season") is not None:
                self.discover_season(row["anime_id"], row["season"])
        return found

    def reindex_anime(self, anime_id):
        self.discover_anime(anime_id)
        with self.store._conn() as con:
            rows = con.execute("SELECT id FROM episodes WHERE anime_id=?", (int(anime_id),)).fetchall()
        for row in rows:
            self.discover_episode(row["id"])
        return self.list_for("anime", anime_id)

    def list_for(self, entity_type, entity_id, artwork_type=None):
        entity_type = self._entity(entity_type, entity_id)
        params = [entity_type, str(entity_id)]
        where = "entity_type=? AND entity_id=?"
        if artwork_type:
            where += " AND artwork_type=?"
            params.append(self._type(artwork_type))
        with self.store._conn() as con:
            return [dict(row) for row in con.execute(
                f"SELECT * FROM artwork WHERE {where} ORDER BY priority DESC, updated_at DESC, id DESC",
                params,
            ).fetchall()]

    @staticmethod
    def _usable(row, allow_network):
        if row["local_path"]:
            return os.path.isfile(row["local_path"])
        return bool(row["external_url"]) and allow_network

    def resolve(self, entity_type, entity_id, artwork_type, *, allow_network=True):
        entity_type = self._entity(entity_type, entity_id)
        artwork_type = self._type(artwork_type)
        rows = self.list_for(entity_type, entity_id, artwork_type)
        for row in rows:
            if row["manual"] and self._usable(row, allow_network):
                return row
        for row in rows:
            if self._usable(row, allow_network):
                return row

        # Hierarchical fallbacks never replace a manual choice; they only
        # supply an absent role from an already-known poster/backdrop.
        if artwork_type in {"thumbnail", "episode_thumbnail"}:
            fallback = self.resolve(entity_type, entity_id, "poster", allow_network=allow_network)
            if fallback:
                return dict(fallback, fallback=True)
        if entity_type == "season" and artwork_type == "season_poster":
            anime_id = str(entity_id).split(":season:", 1)[0]
            fallback = self.resolve("anime", anime_id, "poster", allow_network=allow_network)
            if fallback:
                return dict(fallback, fallback=True)
        if artwork_type == "backdrop":
            fallback = self.resolve(entity_type, entity_id, "poster", allow_network=allow_network)
            if fallback:
                return dict(fallback, fallback=True)
        return None

    def mark_download_failure(self, entity_type, entity_id, artwork_type, source_ref):
        with self.store._conn() as con:
            row = con.execute(
                """SELECT id,failure_count FROM artwork WHERE entity_type=? AND entity_id=?
                   AND artwork_type=? AND source_ref=?""",
                (self._entity(entity_type, entity_id), str(entity_id), self._type(artwork_type), source_ref),
            ).fetchone()
            if not row:
                return False
            con.execute(
                "UPDATE artwork SET status='failed',failure_count=?,last_attempt_at=?,updated_at=? WHERE id=?",
                (int(row["failure_count"] or 0) + 1, time.time(), time.time(), row["id"]),
            )
            return True

    def retryable(self, entity_type, entity_id, artwork_type):
        with self.store._conn() as con:
            rows = con.execute(
                """SELECT * FROM artwork WHERE entity_type=? AND entity_id=? AND artwork_type=?
                   AND status='failed' ORDER BY last_attempt_at ASC""",
                (self._entity(entity_type, entity_id), str(entity_id), self._type(artwork_type)),
            ).fetchall()
        return [dict(row) for row in rows]
