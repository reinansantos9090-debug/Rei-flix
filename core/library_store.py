"""SQLite persistence for the local library and its document-folder diagnostics."""
from __future__ import annotations

import json
import math
import os
import sqlite3
import time

from core.consumption import consumption_state, is_completed, is_in_progress, is_regular_episode


class LibraryStore:
    SCHEMA_VERSION = 21
    def __init__(self, data_dir: str):
        os.makedirs(data_dir, exist_ok=True)
        self.db_path = os.path.join(data_dir, "library.sqlite3")
        self.cache_dir = os.path.join(data_dir, "covers")
        os.makedirs(self.cache_dir, exist_ok=True)
        self._last_playback_event_at = {}
        self._init()

    def _conn(self):
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        return con

    def _init(self):
        with self._conn() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS folders (
              path TEXT PRIMARY KEY, name TEXT, kind TEXT NOT NULL DEFAULT 'path',
              authorization TEXT NOT NULL DEFAULT 'unknown', account_id TEXT, added_at REAL NOT NULL,
              last_scan_at REAL, last_error TEXT
            );
            CREATE TABLE IF NOT EXISTS anime (
              id INTEGER PRIMARY KEY, lookup_title TEXT UNIQUE NOT NULL, anilist_id INTEGER,
              title TEXT NOT NULL, romaji TEXT, english TEXT, native TEXT, aliases TEXT DEFAULT '[]', description TEXT,
              cover_url TEXT, cover_cache TEXT, banner_url TEXT, genres TEXT, year INTEGER,
              season TEXT, status TEXT, episodes_count INTEGER, duration INTEGER, score INTEGER, format TEXT, studio TEXT,
              metadata_updated_at REAL, metadata_fetched_at REAL, metadata_source TEXT NOT NULL DEFAULT 'unknown', metadata_confidence TEXT NOT NULL DEFAULT 'low', metadata_status TEXT NOT NULL DEFAULT 'unresolved', metadata_manual_fields TEXT NOT NULL DEFAULT '[]', favorite INTEGER NOT NULL DEFAULT 0, user_tags TEXT NOT NULL DEFAULT '[]',
              media_kind TEXT NOT NULL DEFAULT 'series', is_pinned INTEGER NOT NULL DEFAULT 0, personal_note TEXT, added_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS episodes (
              id INTEGER PRIMARY KEY, anime_id INTEGER NOT NULL REFERENCES anime(id) ON DELETE CASCADE,
              path TEXT UNIQUE NOT NULL, file_name TEXT NOT NULL, season INTEGER NOT NULL,
              number REAL, duration REAL DEFAULT 0, progress REAL DEFAULT 0, watched INTEGER DEFAULT 0,
              mime_type TEXT, file_size INTEGER, modified_at REAL, source_folder TEXT, absolute_number REAL, relative_path TEXT, volume_id TEXT, volume_uuid TEXT, episode_type TEXT NOT NULL DEFAULT 'regular', episode_title TEXT, identification_source TEXT NOT NULL DEFAULT 'legacy', identification_confidence TEXT NOT NULL DEFAULT 'medium', manual_override INTEGER NOT NULL DEFAULT 0,
              missing INTEGER DEFAULT 0, last_played_at REAL, media_identity TEXT);
            CREATE TABLE IF NOT EXISTS artwork (
              id INTEGER PRIMARY KEY, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
              artwork_type TEXT NOT NULL, source TEXT NOT NULL, source_ref TEXT,
              local_path TEXT, external_url TEXT, manual INTEGER NOT NULL DEFAULT 0,
              priority INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'ready',
              discovered_at REAL NOT NULL, updated_at REAL NOT NULL, last_attempt_at REAL,
              failure_count INTEGER NOT NULL DEFAULT 0,
              UNIQUE(entity_type, entity_id, artwork_type, source_ref)
            );
            CREATE INDEX IF NOT EXISTS idx_artwork_entity
              ON artwork(entity_type, entity_id, artwork_type, priority DESC);
            CREATE INDEX IF NOT EXISTS idx_artwork_status
              ON artwork(status, last_attempt_at);
            CREATE TABLE IF NOT EXISTS associations (lookup_title TEXT PRIMARY KEY, anilist_id INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS pending_matches (lookup_title TEXT PRIMARY KEY, display_title TEXT NOT NULL, candidates TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS account (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS scan_runs (
              id INTEGER PRIMARY KEY, started_at REAL NOT NULL, finished_at REAL, status TEXT NOT NULL DEFAULT 'running', folders INTEGER DEFAULT 0,
              files INTEGER DEFAULT 0, videos INTEGER DEFAULT 0, animes INTEGER DEFAULT 0,
              episodes INTEGER DEFAULT 0, new_files INTEGER DEFAULT 0, updated_files INTEGER DEFAULT 0, unchanged_files INTEGER DEFAULT 0, ignored_files INTEGER DEFAULT 0, duplicate_files INTEGER DEFAULT 0, unknown_files INTEGER DEFAULT 0, reconciled_files INTEGER DEFAULT 0, scan_id TEXT, source_kind TEXT, scope_kind TEXT, scope_ref TEXT, errors TEXT NOT NULL DEFAULT '[]');
            ''')
            # Migration for databases made by earlier versions.
            existing = {r[1] for r in c.execute("PRAGMA table_info(folders)")}
            for column, definition in {
                "name": "TEXT", "kind": "TEXT NOT NULL DEFAULT 'path'", "authorization": "TEXT NOT NULL DEFAULT 'unknown'",
                "last_scan_at": "REAL", "last_error": "TEXT", "account_id": "TEXT",
            }.items():
                if column not in existing:
                    c.execute(f"ALTER TABLE folders ADD COLUMN {column} {definition}")
            anime_columns = {r[1] for r in c.execute("PRAGMA table_info(anime)")}
            for column, definition in {"aliases": "TEXT DEFAULT '[]'", "score": "INTEGER", "format": "TEXT", "metadata_updated_at": "REAL", "metadata_fetched_at": "REAL", "metadata_source": "TEXT NOT NULL DEFAULT 'unknown'", "metadata_confidence": "TEXT NOT NULL DEFAULT 'low'", "metadata_status": "TEXT NOT NULL DEFAULT 'unresolved'", "metadata_manual_fields": "TEXT NOT NULL DEFAULT '[]'", "media_kind": "TEXT NOT NULL DEFAULT 'series'", "favorite": "INTEGER NOT NULL DEFAULT 0", "user_tags": "TEXT NOT NULL DEFAULT '[]'", "is_pinned": "INTEGER NOT NULL DEFAULT 0", "personal_note": "TEXT"}.items():
                if column not in anime_columns:
                    c.execute(f"ALTER TABLE anime ADD COLUMN {column} {definition}")
            episode_columns = {r[1] for r in c.execute("PRAGMA table_info(episodes)")}
            for column, definition in {"mime_type": "TEXT", "file_size": "INTEGER", "modified_at": "REAL", "source_folder": "TEXT", "absolute_number": "REAL", "relative_path": "TEXT", "volume_id": "TEXT", "volume_uuid": "TEXT", "episode_type": "TEXT NOT NULL DEFAULT 'regular'", "episode_title": "TEXT", "identification_source": "TEXT NOT NULL DEFAULT 'legacy'", "identification_confidence": "TEXT NOT NULL DEFAULT 'medium'", "manual_override": "INTEGER NOT NULL DEFAULT 0", "last_played_at": "REAL", "media_identity": "TEXT"}.items():
                if column not in episode_columns:
                    c.execute(f"ALTER TABLE episodes ADD COLUMN {column} {definition}")
            c.execute("CREATE INDEX IF NOT EXISTS idx_episodes_anime_playback ON episodes(anime_id, missing, watched, last_played_at)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_episodes_source_folder ON episodes(source_folder)")
            c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_episodes_media_identity ON episodes(media_identity) WHERE media_identity IS NOT NULL")
            # Version records make additive schema changes auditable
            # while CREATE IF NOT EXISTS keeps all earlier databases intact.
            c.execute("CREATE INDEX IF NOT EXISTS idx_folders_account ON folders(account_id)")
            scan_columns = {r[1] for r in c.execute("PRAGMA table_info(scan_runs)")}
            for column, definition in {
                "status": "TEXT NOT NULL DEFAULT 'running'", "new_files": "INTEGER DEFAULT 0", "updated_files": "INTEGER DEFAULT 0",
                "unchanged_files": "INTEGER DEFAULT 0", "ignored_files": "INTEGER DEFAULT 0", "duplicate_files": "INTEGER DEFAULT 0",
                "unknown_files": "INTEGER DEFAULT 0", "reconciled_files": "INTEGER DEFAULT 0", "scan_id": "TEXT",
                "source_kind": "TEXT", "scope_kind": "TEXT", "scope_ref": "TEXT",
            }.items():
                if column not in scan_columns:
                    c.execute(f"ALTER TABLE scan_runs ADD COLUMN {column} {definition}")
            c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_scan_runs_scan_id ON scan_runs(scan_id) WHERE scan_id IS NOT NULL")
            c.execute("CREATE INDEX IF NOT EXISTS idx_scan_runs_status ON scan_runs(status, started_at)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_anime_pinned ON anime(is_pinned, added_at)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_anime_media_kind ON anime(media_kind, added_at)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_episodes_hierarchy ON episodes(anime_id, episode_type, season, number, absolute_number)")
            c.execute("INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES (?,?)", (self.SCHEMA_VERSION, time.time()))
        # A process can disappear between begin_scan() and finish_scan().
        # Recovering here keeps startup deterministic while leaving the
        # recovery operation testable and reusable by callers.
        self.recover_interrupted_scans()

    def get_preference(self, key, default=None):
        with self._conn() as c:
            row = c.execute("SELECT value FROM preferences WHERE key=?", (key,)).fetchone()
            return row["value"] if row else default

    def set_preference(self, key, value):
        value = str(value)
        with self._conn() as c:
            c.execute("""INSERT INTO preferences(key,value,updated_at) VALUES (?,?,?)
                         ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at""",
                      (key, value, time.time()))

    def remove_preference(self, key):
        with self._conn() as c:
            c.execute("DELETE FROM preferences WHERE key=?", (key,))

    def library_summary(self):
        """Small settings projection; it never loads the full catalog."""
        with self._conn() as c:
            return {
                "folders": c.execute("SELECT COUNT(*) FROM folders").fetchone()[0],
                "animes": c.execute("SELECT COUNT(*) FROM anime").fetchone()[0],
                "episodes": c.execute("SELECT COUNT(*) FROM episodes").fetchone()[0],
                "history": c.execute("SELECT COUNT(*) FROM episodes WHERE last_played_at IS NOT NULL").fetchone()[0],
            }

    def library_statistics(self):
        """Offline aggregate projection for Settings; never opens media or uses network."""
        with self._conn() as c:
            row = c.execute("""SELECT
                COUNT(*) AS animes, SUM(CASE WHEN favorite=1 THEN 1 ELSE 0 END) AS favorites,
                SUM(CASE WHEN is_pinned=1 THEN 1 ELSE 0 END) AS pinned,
                SUM(CASE WHEN NULLIF(TRIM(personal_note), '') IS NOT NULL THEN 1 ELSE 0 END) AS notes,
                SUM(CASE WHEN anilist_id IS NULL THEN 1 ELSE 0 END) AS without_metadata,
                SUM(CASE WHEN NULLIF(TRIM(cover_cache), '') IS NULL AND NULLIF(TRIM(cover_url), '') IS NULL THEN 1 ELSE 0 END) AS without_cover
                FROM anime""").fetchone()
            episodes = c.execute("""SELECT COUNT(*) AS total, SUM(CASE WHEN missing=0 THEN 1 ELSE 0 END) AS available,
                SUM(CASE WHEN missing=0 AND watched=1 THEN 1 ELSE 0 END) AS watched,
                SUM(CASE WHEN missing=0 AND progress>0 AND watched=0 THEN 1 ELSE 0 END) AS active,
                SUM(CASE WHEN missing=0 THEN progress ELSE 0 END) AS recorded_seconds,
                SUM(CASE WHEN missing=0 THEN duration ELSE 0 END) AS duration_seconds FROM episodes""").fetchone()
            tags = c.execute("SELECT user_tags FROM anime").fetchall()
            anime_state_rows = c.execute("""SELECT anime_id,
                SUM(CASE WHEN missing=0 THEN 1 ELSE 0 END) AS available,
                SUM(CASE WHEN missing=0 AND watched=1 THEN 1 ELSE 0 END) AS watched,
                SUM(CASE WHEN missing=0 AND progress>0 AND watched=0 THEN 1 ELSE 0 END) AS active
                FROM episodes GROUP BY anime_id""").fetchall()
        tag_count = len({str(tag).casefold() for entry in tags for tag in self._decode_tags(entry["user_tags"])})
        state_completed = sum(bool(r["available"]) and r["watched"] == r["available"] for r in anime_state_rows)
        state_active = sum(bool(r["active"]) for r in anime_state_rows)
        state_not_started = sum(bool(r["available"]) and not r["watched"] and not r["active"] for r in anime_state_rows)
        available = int(episodes["available"] or 0)
        watched = int(episodes["watched"] or 0)
        return {"animes": int(row["animes"] or 0), "episodes": int(episodes["total"] or 0), "episodes_available": available,
                "episodes_watched": watched, "animes_in_progress": state_active,
                "animes_completed": state_completed, "animes_not_started": state_not_started,
                "favorites": int(row["favorites"] or 0), "pinned": int(row["pinned"] or 0), "notes": int(row["notes"] or 0),
                "tags": tag_count, "without_metadata": int(row["without_metadata"] or 0), "without_cover": int(row["without_cover"] or 0),
                "recorded_seconds": float(episodes["recorded_seconds"] or 0), "available_duration_seconds": float(episodes["duration_seconds"] or 0)}

    @staticmethod
    def _decode_tags(value):
        try:
            decoded = json.loads(value or "[]")
            return decoded if isinstance(decoded, list) else []
        except (TypeError, json.JSONDecodeError):
            return []

    def _anime_state_count(self, state):
        # A single grouped query keeps aggregate state semantics aligned with the catalog.
        with self._conn() as c:
            rows = c.execute("""SELECT anime_id, SUM(CASE WHEN missing=0 THEN 1 ELSE 0 END) available,
                SUM(CASE WHEN missing=0 AND watched=1 THEN 1 ELSE 0 END) watched,
                SUM(CASE WHEN missing=0 AND progress>0 AND watched=0 THEN 1 ELSE 0 END) active FROM episodes GROUP BY anime_id""").fetchall()
        if state == "completed": return sum(bool(r["available"]) and r["watched"] == r["available"] for r in rows)
        if state == "in_progress": return sum(bool(r["active"]) for r in rows)
        return sum(bool(r["available"]) and not r["watched"] and not r["active"] for r in rows)

    def clear_anilist_metadata_cache(self):
        """Expire metadata and cover paths, preserving library rows and associations."""
        with self._conn() as c:
            c.execute("UPDATE anime SET metadata_updated_at=NULL, cover_cache=''")

    def folders(self):
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM folders ORDER BY added_at")]

    def add_folder(self, reference, name=None, kind="path", authorization="granted", account_id=None):
        name = name or os.path.basename(reference.rstrip("/")) or reference
        with self._conn() as c:
            c.execute("""INSERT INTO folders(path,name,kind,authorization,account_id,added_at) VALUES (?,?,?,?,?,?)
                         ON CONFLICT(path) DO UPDATE SET name=excluded.name,kind=excluded.kind,
                         authorization=excluded.authorization,account_id=COALESCE(excluded.account_id,folders.account_id),
                         last_error=NULL""",
                      (reference, name, kind, authorization, account_id, time.time()))

    def update_folder_status(self, reference, authorization, error=None):
        with self._conn() as c:
            c.execute("UPDATE folders SET authorization=?,last_error=?,last_scan_at=? WHERE path=?",
                      (authorization, error, time.time(), reference))

    def remove_folder(self, reference):
        """Remove a configured folder while preserving its episodes as missing.

        Playback progress, favorites and anime metadata remain durable; only
        episodes owned by the removed source stop being playable.
        """
        with self._conn() as c:
            c.execute("UPDATE episodes SET missing=1 WHERE source_folder=?", (reference,))
            c.execute("DELETE FROM folders WHERE path=?", (reference,))

    def begin_scan(self, scan_id=None, *, source_kind=None, scope_kind="global", scope_ref=None):
        import uuid
        scan_id = scan_id or str(uuid.uuid4())
        with self._conn() as c:
            cur = c.execute(
                """INSERT INTO scan_runs(started_at,status,scan_id,source_kind,scope_kind,scope_ref)
                   VALUES (?, 'running', ?, ?, ?, ?)""",
                (time.time(), scan_id, source_kind, scope_kind, scope_ref),
            )
            return cur.lastrowid

    def finish_scan(self, run_id, summary):
        with self._conn() as c:
            c.execute("""UPDATE scan_runs SET finished_at=?,status=?,folders=?,files=?,videos=?,animes=?,episodes=?,
                         new_files=?,updated_files=?,unchanged_files=?,ignored_files=?,duplicate_files=?,unknown_files=?,reconciled_files=?,errors=? WHERE id=?""",
                      (time.time(), summary.get("status", "completed"), summary.get("folders", 0), summary.get("files", 0), summary.get("videos", 0),
                       summary.get("animes", 0), summary.get("episodes", 0), summary.get("new", 0), summary.get("updated", 0),
                       summary.get("unchanged", 0), summary.get("ignored", 0), summary.get("duplicates", 0),
                       summary.get("unknown", 0), summary.get("reconciled", 0), json.dumps(summary.get("errors", []), ensure_ascii=False), run_id))

    def last_scan(self):
        with self._conn() as c:
            row = c.execute("SELECT * FROM scan_runs ORDER BY id DESC LIMIT 1").fetchone()
            return dict(row) if row else None

    def interrupted_scans(self):
        """Return scans that were interrupted by a prior process shutdown."""
        with self._conn() as c:
            return [dict(row) for row in c.execute(
                "SELECT * FROM scan_runs WHERE status='interrupted' ORDER BY id DESC"
            )]

    def recover_interrupted_scans(self):
        """Finalize orphaned scan runs without touching library media rows."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT id FROM scan_runs WHERE status='running' AND finished_at IS NULL"
            ).fetchall()
            if not rows:
                return 0
            c.executemany(
                "UPDATE scan_runs SET status='interrupted',finished_at=? WHERE id=?",
                ((time.time(), row["id"]) for row in rows),
            )
            return len(rows)

    def association(self, lookup):
        with self._conn() as c:
            r = c.execute("SELECT anilist_id FROM associations WHERE lookup_title=?", (lookup,)).fetchone()
            return r[0] if r else None

    def anime_metadata(self, lookup):
        """Return the cached AniList-derived metadata for a local title."""
        with self._conn() as c:
            row = c.execute("SELECT * FROM anime WHERE lookup_title=?", (lookup,)).fetchone()
            return dict(row) if row else None

    def set_association(self, lookup, anilist_id):
        with self._conn() as c: c.execute("INSERT OR REPLACE INTO associations VALUES (?,?)", (lookup, anilist_id))

    def set_pending_match(self, lookup, display_title, candidates):
        with self._conn() as c: c.execute("INSERT OR REPLACE INTO pending_matches VALUES (?,?,?)", (lookup, display_title, json.dumps(candidates, ensure_ascii=False)))

    def pending_matches(self):
        with self._conn() as c:
            return [{"lookup_title": r["lookup_title"], "display_title": r["display_title"], "candidates": json.loads(r["candidates"])} for r in c.execute("SELECT * FROM pending_matches ORDER BY display_title")]

    def resolve_match(self, lookup, anilist_id):
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO associations VALUES (?,?)", (lookup, anilist_id))
            c.execute("DELETE FROM pending_matches WHERE lookup_title=?", (lookup,))

    def toggle_favorite(self, anime_id):
        with self._conn() as c:
            c.execute("UPDATE anime SET favorite=1-favorite WHERE id=?", (anime_id,))
            row = c.execute("SELECT favorite FROM anime WHERE id=?", (anime_id,)).fetchone()
            return bool(row and row[0])

    def toggle_pinned(self, anime_id):
        with self._conn() as c:
            if not c.execute("UPDATE anime SET is_pinned=1-is_pinned WHERE id=?", (anime_id,)).rowcount:
                raise ValueError("Anime local não encontrado.")
            return bool(c.execute("SELECT is_pinned FROM anime WHERE id=?", (anime_id,)).fetchone()[0])

    def set_personal_note(self, anime_id, note):
        note = "" if note is None else str(note).strip()
        if len(note) > 2000:
            raise ValueError("A nota pessoal pode ter no máximo 2000 caracteres.")
        with self._conn() as c:
            if not c.execute("UPDATE anime SET personal_note=? WHERE id=?", (note or None, anime_id)).rowcount:
                raise ValueError("Anime local não encontrado.")
        return note or None

    def is_favorite(self, anime_id):
        with self._conn() as c:
            row = c.execute("SELECT favorite FROM anime WHERE id=?", (anime_id,)).fetchone()
            return bool(row and row[0])

    def set_user_tags(self, anime_id, tags):
        """Persist a small, private set of labels without touching AniList metadata."""
        normalized = []
        for tag in tags or []:
            tag = " ".join(str(tag).split()).strip()
            if tag and tag.casefold() not in {item.casefold() for item in normalized}:
                normalized.append(tag[:40])
        with self._conn() as c:
            if not c.execute("UPDATE anime SET user_tags=? WHERE id=?", (json.dumps(normalized, ensure_ascii=False), anime_id)).rowcount:
                raise ValueError("Anime local não encontrado.")
        return normalized

    def upsert_anime(self, lookup, metadata, *, source=None, confidence=None, status=None, fetched_at=None):
        """Upsert editorial metadata with source-aware, field-level merge safety.

        User metadata (favorites, tags, pins, notes) is stored in separate columns.
        Editorial fields marked manual are protected from automatic sources.
        """
        title = metadata.get("title") or lookup
        incoming_kind = str(metadata.get("media_kind") or "series").casefold()
        if incoming_kind not in {"series", "movie", "unknown"}:
            incoming_kind = "series"
        source = str(source or metadata.get("metadata_source") or "local").casefold()
        if source not in {"local", "anilist", "manual", "unknown"}:
            source = "unknown"
        confidence = str(confidence or metadata.get("metadata_confidence") or ("high" if source == "manual" else "low")).casefold()
        status = str(status or metadata.get("metadata_status") or ("manual" if source == "manual" else "available" if source == "anilist" else "unresolved")).casefold()
        fetched_at = fetched_at if fetched_at is not None else metadata.get("metadata_fetched_at")
        now = time.time()
        metadata_updated_at = metadata.get("metadata_updated_at", now)
        editorial = ("title", "romaji", "english", "native", "aliases", "description", "cover_url", "cover_cache", "banner_url", "genres", "year", "season", "status", "episodes_count", "duration", "score", "format", "studio")
        values = {
            "anilist_id": metadata.get("anilist_id"),
            "title": title,
            "romaji": metadata.get("romaji"),
            "english": metadata.get("english"),
            "native": metadata.get("native"),
            "aliases": metadata.get("aliases", "[]"),
            "description": metadata.get("description"),
            "cover_url": metadata.get("cover_url", ""),
            "cover_cache": metadata.get("cover_cache", ""),
            "banner_url": metadata.get("banner_url", ""),
            "genres": metadata.get("genres", "[]"),
            "year": metadata.get("year"),
            "season": metadata.get("season"),
            "status": metadata.get("status"),
            "episodes_count": metadata.get("episodes_count"),
            "duration": metadata.get("duration"),
            "score": metadata.get("score"),
            "format": metadata.get("format"),
            "studio": metadata.get("studio"),
        }
        with self._conn() as c:
            row = c.execute("SELECT * FROM anime WHERE lookup_title=?", (lookup,)).fetchone()
            if row:
                try:
                    manual_fields = set(json.loads(row["metadata_manual_fields"] or "[]"))
                except (TypeError, json.JSONDecodeError):
                    manual_fields = set()
                if source == "manual":
                    manual_fields.update(k for k in editorial if k in metadata)
                if source == "anilist":
                    # Preserve previously known values when an API response is partial.
                    for key in editorial:
                        incoming = values.get(key)
                        if key not in manual_fields and (key not in metadata or incoming is None or incoming == "" or incoming == "[]"):
                            values[key] = row[key]
                    # Keep a previously cached cover if the network returned none.
                    values["cover_cache"] = values.get("cover_cache") or row["cover_cache"] or ""
                    values["cover_url"] = values.get("cover_url") or row["cover_url"] or ""
                    # External metadata must never replace a manually corrected field.
                    for key in manual_fields:
                        if key in values:
                            values[key] = row[key]
                else:
                    for key in editorial:
                        incoming = values.get(key)
                        if key not in metadata or incoming is None or incoming == "" or incoming == "[]":
                            values[key] = row[key]
                if source == "anilist" and not values.get("anilist_id"):
                    values["anilist_id"] = row["anilist_id"]
                media_kind = incoming_kind if incoming_kind == "movie" or not row["media_kind"] or row["media_kind"] == "unknown" else row["media_kind"]
                if source == "manual":
                    metadata_source = "manual"
                    metadata_status = "manual"
                elif row["metadata_source"] == "manual" and source != "manual":
                    metadata_source = "manual"
                    metadata_status = "manual"
                else:
                    metadata_source = source
                    metadata_status = status
                metadata_fetched = fetched_at if source == "anilist" else row["metadata_fetched_at"]
                metadata_conf = confidence if source in {"anilist", "manual"} else row["metadata_confidence"]
                metadata_updated = now if source in {"anilist", "manual"} else row["metadata_updated_at"]
                c.execute("""UPDATE anime SET anilist_id=?,title=?,romaji=?,english=?,native=?,aliases=?,description=?,cover_url=?,cover_cache=?,banner_url=?,genres=?,year=?,season=?,status=?,episodes_count=?,duration=?,score=?,format=?,studio=?,metadata_updated_at=?,metadata_fetched_at=?,metadata_source=?,metadata_confidence=?,metadata_status=?,metadata_manual_fields=?,media_kind=? WHERE id=?""",
                          (values["anilist_id"], values["title"] or lookup, values["romaji"], values["english"], values["native"], values["aliases"], values["description"], values["cover_url"], values["cover_cache"], values["banner_url"], values["genres"], values["year"], values["season"], values["status"], values["episodes_count"], values["duration"], values["score"], values["format"], values["studio"], metadata_updated, metadata_fetched, metadata_source, metadata_conf, metadata_status, json.dumps(sorted(manual_fields), ensure_ascii=False), media_kind, row["id"]))
                return row["id"]
            c.execute("""INSERT INTO anime(lookup_title,anilist_id,title,romaji,english,native,aliases,description,cover_url,cover_cache,banner_url,genres,year,season,status,episodes_count,duration,score,format,studio,metadata_updated_at,metadata_fetched_at,metadata_source,metadata_confidence,metadata_status,metadata_manual_fields,media_kind,added_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (lookup, values["anilist_id"], values["title"], values["romaji"], values["english"], values["native"], values["aliases"], values["description"], values["cover_url"], values["cover_cache"], values["banner_url"], values["genres"], values["year"], values["season"], values["status"], values["episodes_count"], values["duration"], values["score"], values["format"], values["studio"], metadata_updated_at, fetched_at, source, confidence, status, json.dumps(sorted(k for k in editorial if source == "manual" and k in metadata), ensure_ascii=False), incoming_kind, now))
            return c.execute("SELECT id FROM anime WHERE lookup_title=?", (lookup,)).fetchone()[0]

    def set_metadata_status(self, lookup, status, *, confidence=None):
        with self._conn() as c:
            if confidence is None:
                updated = c.execute("UPDATE anime SET metadata_status=? WHERE lookup_title=?", (status, lookup)).rowcount
            else:
                updated = c.execute("UPDATE anime SET metadata_status=?,metadata_confidence=? WHERE lookup_title=?", (status, confidence, lookup)).rowcount
            return bool(updated)

    def set_manual_metadata(self, lookup, values):
        """Persist explicit editorial corrections without touching user state."""
        allowed = {"title", "romaji", "english", "native", "aliases", "description", "genres", "year", "season", "status", "episodes_count", "duration", "score", "format", "studio"}
        values = {key: value for key, value in (values or {}).items() if key in allowed}
        if not values:
            raise ValueError("Nenhum campo de metadata manual válido foi informado.")
        with self._conn() as c:
            row = c.execute("SELECT * FROM anime WHERE lookup_title=?", (lookup,)).fetchone()
            if not row:
                raise ValueError("Obra local não encontrada.")
            try:
                manual_fields = set(json.loads(row["metadata_manual_fields"] or "[]"))
            except (TypeError, json.JSONDecodeError):
                manual_fields = set()
            manual_fields.update(values)
            assignments = ",".join(f"{key}=?" for key in values)
            params = list(values.values()) + [json.dumps(sorted(manual_fields), ensure_ascii=False), time.time(), "manual", "high", "manual", row["id"]]
            c.execute(f"UPDATE anime SET {assignments},metadata_manual_fields=?,metadata_updated_at=?,metadata_source=?,metadata_confidence=?,metadata_status=? WHERE id=?", tuple(params))
            return dict(c.execute("SELECT * FROM anime WHERE id=?", (row["id"],)).fetchone())

    def clear_manual_metadata(self, lookup, fields=None):
        with self._conn() as c:
            row = c.execute("SELECT * FROM anime WHERE lookup_title=?", (lookup,)).fetchone()
            if not row:
                raise ValueError("Obra local não encontrada.")
            try:
                manual_fields = set(json.loads(row["metadata_manual_fields"] or "[]"))
            except (TypeError, json.JSONDecodeError):
                manual_fields = set()
            remove = set(fields or manual_fields) & manual_fields
            manual_fields -= remove
            c.execute("UPDATE anime SET metadata_manual_fields=?,metadata_status=?,metadata_source=? WHERE id=?", (json.dumps(sorted(manual_fields), ensure_ascii=False), "available" if row["anilist_id"] else "unresolved", "anilist" if row["anilist_id"] else "local", row["id"]))
            return True

    def upsert_episode(self, anime_id, path, file_name, season, number, mime_type=None, file_size=None,
                       modified_at=None, source_folder=None, media_identity=None, absolute_number=None,
                       episode_type="regular", episode_title=None, *, identification_source=None,
                       identification_confidence=None, identity_key=None):
        """Upsert by URI, then by proven cross-source identity.

        Season 0 is the explicit unknown bucket when no season evidence exists;
        it is never treated as Season 1.
        """
        season = 0 if season is None else season
        media_identity = media_identity or identity_key
        with self._conn() as c:
            by_path = c.execute("SELECT * FROM episodes WHERE path=?", (path,)).fetchone()
            by_identity = None
            if media_identity:
                by_identity = c.execute(
                    "SELECT * FROM episodes WHERE media_identity=? ORDER BY id LIMIT 1",
                    (media_identity,),
                ).fetchone()

            def effective_identification(existing):
                manual = bool(existing and existing["manual_override"])
                if manual:
                    return (
                        existing["season"],
                        existing["number"],
                        existing["episode_type"],
                        existing["episode_title"],
                        existing["identification_source"],
                        existing["identification_confidence"],
                    )
                return (
                    season,
                    number,
                    episode_type,
                    episode_title,
                    identification_source or (existing["identification_source"] if existing else "legacy"),
                    identification_confidence or (existing["identification_confidence"] if existing else "medium"),
                )

            def update_existing(row_id, new_path=None):
                existing = c.execute("SELECT * FROM episodes WHERE id=?", (row_id,)).fetchone()
                effective_season, effective_number, effective_type, effective_title, effective_source, effective_confidence = effective_identification(existing)
                if new_path is None:
                    c.execute(
                        """UPDATE episodes SET anime_id=?,file_name=?,season=?,number=?,mime_type=?,
                           file_size=?,modified_at=?,source_folder=?,media_identity=?,absolute_number=?,
                           episode_type=?,episode_title=?,identification_source=?,identification_confidence=?,missing=0 WHERE id=?""",
                        (anime_id,file_name,effective_season,effective_number,mime_type,file_size,modified_at,source_folder,
                         media_identity,absolute_number,effective_type,effective_title,effective_source,effective_confidence,row_id),
                    )
                else:
                    c.execute(
                        """UPDATE episodes SET anime_id=?,path=?,file_name=?,season=?,number=?,mime_type=?,
                           file_size=?,modified_at=?,source_folder=?,media_identity=?,absolute_number=?,
                           episode_type=?,episode_title=?,identification_source=?,identification_confidence=?,missing=0 WHERE id=?""",
                        (anime_id,new_path,file_name,effective_season,effective_number,mime_type,file_size,modified_at,source_folder,
                         media_identity,absolute_number,effective_type,effective_title,effective_source,effective_confidence,row_id),
                    )
                return row_id

            if by_path and by_identity and by_path["id"] != by_identity["id"]:
                progress = max(float(by_path["progress"] or 0), float(by_identity["progress"] or 0))
                watched = max(int(by_path["watched"] or 0), int(by_identity["watched"] or 0))
                last_played = max(float(by_path["last_played_at"] or 0), float(by_identity["last_played_at"] or 0)) or None
                duplicate_source = (
                    by_identity["identification_source"] if by_identity["manual_override"]
                    else by_path["identification_source"] if by_path["manual_override"]
                    else identification_source or "legacy"
                )
                duplicate_confidence = (
                    by_identity["identification_confidence"] if by_identity["manual_override"]
                    else by_path["identification_confidence"] if by_path["manual_override"]
                    else identification_confidence or "medium"
                )
                duplicate_season = (
                    by_identity["season"] if by_identity["manual_override"]
                    else by_path["season"] if by_path["manual_override"]
                    else season
                )
                duplicate_number = (
                    by_identity["number"] if by_identity["manual_override"]
                    else by_path["number"] if by_path["manual_override"]
                    else number
                )
                duplicate_type = (
                    by_identity["episode_type"] if by_identity["manual_override"]
                    else by_path["episode_type"] if by_path["manual_override"]
                    else episode_type
                )
                duplicate_title = (
                    by_identity["episode_title"] if by_identity["manual_override"]
                    else by_path["episode_title"] if by_path["manual_override"]
                    else episode_title
                )
                c.execute(
                    """UPDATE episodes SET anime_id=?,path=?,file_name=?,season=?,number=?,mime_type=?,
                       file_size=?,modified_at=?,source_folder=?,media_identity=?,absolute_number=?,
                       episode_type=?,episode_title=?,identification_source=?,identification_confidence=?,
                       missing=0,progress=?,watched=?,last_played_at=? WHERE id=?""",
                    (anime_id,path,file_name,duplicate_season,duplicate_number,mime_type,file_size,modified_at,source_folder,
                     media_identity,absolute_number,duplicate_type,duplicate_title,duplicate_source,
                     duplicate_confidence,progress,watched,last_played,by_identity["id"]),
                )
                c.execute("DELETE FROM episodes WHERE id=?", (by_path["id"],))
                return by_identity["id"]

            if by_path:
                return update_existing(by_path["id"])
            if by_identity:
                return update_existing(by_identity["id"], new_path=path)

            cur = c.execute(
                """INSERT INTO episodes(anime_id,path,file_name,season,number,mime_type,file_size,modified_at,
                                         source_folder,missing,media_identity,absolute_number,episode_type,episode_title,
                                         identification_source,identification_confidence)
                   VALUES(?,?,?,?,?,?,?,?,?,0,?,?,?,?,?,?)""",
                (anime_id,path,file_name,season,number,mime_type,file_size,modified_at,source_folder,
                 media_identity,absolute_number,episode_type,episode_title,
                 identification_source or "legacy", identification_confidence or "medium"),
            )
            return cur.lastrowid

    def merge_duplicate_media_identities(self):
        """Merge legacy duplicate rows that now resolve to one media identity."""
        with self._conn() as c:
            duplicate_keys = [row[0] for row in c.execute(
                "SELECT media_identity FROM episodes WHERE media_identity IS NOT NULL GROUP BY media_identity HAVING COUNT(*) > 1"
            )]
            merged = 0
            for identity in duplicate_keys:
                rows = c.execute(
                    """SELECT * FROM episodes WHERE media_identity=?
                       ORDER BY CASE WHEN last_played_at IS NULL THEN 0 ELSE 1 END DESC,
                                last_played_at DESC, watched DESC, id ASC""",
                    (identity,),
                ).fetchall()
                if len(rows) < 2:
                    continue
                survivor = rows[0]
                best_progress = max(float(row["progress"] or 0) for row in rows)
                best_watched = max(int(row["watched"] or 0) for row in rows)
                best_played = max((float(row["last_played_at"] or 0) for row in rows), default=0)
                c.execute(
                    "UPDATE episodes SET progress=?,watched=?,last_played_at=?,missing=? WHERE id=?",
                    (best_progress, best_watched, best_played or None, min(int(row["missing"] or 1) for row in rows), survivor["id"]),
                )
                for row in rows[1:]:
                    c.execute("DELETE FROM episodes WHERE id=?", (row["id"],))
                    merged += 1
            return merged

    def mark_missing(self, source_folder, seen):
        """Mark only one successfully scanned source, preserving other folders."""
        with self._conn() as c:
            if not c.execute("UPDATE episodes SET season=?,number=?,episode_type=?,episode_title=?,identification_source='manual',identification_confidence='high',manual_override=1 WHERE path=?", (season, number, episode_type, (title or "").strip() or None, path)).rowcount:
                raise ValueError("Arquivo local não encontrado.")
            c.execute("UPDATE anime SET media_kind=? WHERE id=(SELECT anime_id FROM episodes WHERE path=?) AND ? IN ('series','movie')", ("movie" if episode_type == "movie" else "series", path, "movie" if episode_type == "movie" else "series"))

    def physical_row(self, path):
        with self._conn() as c:
            row = c.execute("SELECT * FROM episodes WHERE path=?", (path,)).fetchone()
            return dict(row) if row else None

    def reconcile_missing(self, source_folder, seen, *, scope_kind="source", scope_ref=None):
        """Mark absence only inside a scope that the caller proved complete."""
        with self._conn() as c:
            params = [source_folder]
            where = "source_folder=?"
            if scope_kind in {"directory", "root"} and scope_ref:
                prefix = str(scope_ref).strip("/").replace("\\", "/")
                where += " AND (relative_path=? OR relative_path LIKE ?)"
                params.extend([prefix, prefix + "/%"])
            elif scope_kind == "volume" and scope_ref:
                where += " AND volume_id=?"
                params.append(scope_ref)
            c.execute(f"UPDATE episodes SET missing=1 WHERE {where}", tuple(params))
            if seen:
                c.executemany("UPDATE episodes SET missing=0 WHERE path=?", ((p,) for p in seen))

    def mark_missing(self, source_folder, seen):
        self.reconcile_missing(source_folder, seen, scope_kind="source")

    def catalog(self, favorites_only=False):
        """Project the local library once into the visual hierarchy used by Home/Details."""
        with self._conn() as c:
            query = "SELECT * FROM anime" + (" WHERE favorite=1" if favorites_only else "") + " ORDER BY added_at DESC, title COLLATE NOCASE"
            anime_rows = c.execute(query).fetchall()
            episode_rows = c.execute("SELECT * FROM episodes ORDER BY anime_id, season, number, absolute_number, file_name").fetchall()
            folder_kinds = {
                row["path"]: row["kind"]
                for row in c.execute("SELECT path, kind FROM folders")
                if row["path"]
            }
            artwork_rows = c.execute(
                "SELECT entity_type, entity_id, local_path FROM artwork WHERE status != 'failed'"
            ).fetchall()
            local_artwork_anime = {
                str(row["entity_id"])
                for row in artwork_rows
                if row["local_path"] and str(row["entity_type"]) in {"anime", "movie"}
            }
            history_rows = c.execute(
                "SELECT anime_id, MAX(last_played_at) AS last_played_at FROM episodes "
                "WHERE last_played_at IS NOT NULL GROUP BY anime_id"
            ).fetchall()
            history = {int(row["anime_id"]): row["last_played_at"] for row in history_rows}

            def project(e):
                return {
                    "id": e["id"], "title": e["file_name"], "file_name": e["file_name"],
                    "episode_title": e["episode_title"], "path": e["path"], "season": e["season"],
                    "number": e["number"], "absolute_number": e["absolute_number"],
                    "episode_type": e["episode_type"], "identification_source": e["identification_source"],
                    "identification_confidence": e["identification_confidence"], "manual_override": bool(e["manual_override"]),
                    "progress": e["progress"], "duration": e["duration"], "watched": bool(e["watched"]),
                    "consumption_state": consumption_state(dict(e)).value,
                    "missing": bool(e["missing"]), "last_played_at": e["last_played_at"],
                    "mime_type": e["mime_type"], "file_size": e["file_size"], "modified_at": e["modified_at"],
                    "source_folder": e["source_folder"], "source_kind": folder_kinds.get(e["source_folder"]),
                    "relative_path": e["relative_path"], "media_identity": e["media_identity"],
                    "volume_id": e["volume_id"], "volume_uuid": e["volume_uuid"],
                }

            by_anime = {}
            for row in episode_rows:
                by_anime.setdefault(row["anime_id"], []).append(project(row))
            special_types = {"special", "ova", "oad", "ona", "extra"}
            result = []
            for a in anime_rows:
                eps = by_anime.get(a["id"], [])
                if not eps:
                    continue
                projected = eps
                special_eps = [e for e in projected if e["episode_type"] in special_types]
                movie_eps = [e for e in projected if e["episode_type"] == "movie"]
                regulars = [e for e in projected if e["episode_type"] not in special_types and e["episode_type"] != "movie"]
                seasons = {}
                for ep in regulars:
                    seasons.setdefault(ep["season"], []).append(ep)
                try:
                    genres = json.loads(a["genres"] or "[]")
                except (TypeError, json.JSONDecodeError):
                    genres = []
                ordered_seasons = []
                for season, values in sorted(seasons.items(), key=lambda item: item[0] if item[0] is not None else -1):
                    values = sorted(values, key=lambda e: (e["number"] if e["number"] is not None else -1, e["file_name"].casefold(), e["path"].casefold()))
                    season_available = [e for e in values if not e["missing"]]
                    season_completed = [e for e in season_available if is_completed(e)]
                    season_active = [e for e in season_available if is_in_progress(e)]
                    ordered_seasons.append({
                        "season_name": f"Temporada {season}" if season is not None else "Temporada especial",
                        "season": season, "folder_path": "", "episodes": values,
                        "available_count": len(season_available),
                        "watched_count": len(season_completed),
                        "active_count": len(season_active),
                        "remaining_count": max(0, len(season_available) - len(season_completed)),
                        "progress_ratio": (len(season_completed) / len(season_available)) if season_available else 0.0,
                    })
                available = [e for e in projected if not e["missing"]]
                watched = [e for e in available if is_completed(e)]
                active = [e for e in available if is_in_progress(e)]
                eligible = [e for e in regulars if not e["missing"]]
                current = self._current_from_rows(eligible or [e for e in projected if e["episode_type"] != "movie"])
                next_ep = None
                if current and not is_completed(current):
                    next_ep = current
                elif watched:
                    # History timestamp determines recency, but sequence
                    # continuation must use the furthest completed local episode.
                    latest = max(watched, key=self._episode_order_key)
                    next_ep = self._adjacent_from_rows(latest, eligible, 1)
                result.append({
                    "id": a["id"], "main_title": a["title"], "meta": dict(a),
                    "favorite": bool(a["favorite"]), "is_pinned": bool(a["is_pinned"]),
                    "user_tags": self._decode_tags(a["user_tags"]),
                    "personal_note": a["personal_note"], "genres": genres,
                    "seasons": ordered_seasons,
                    "specials": [{"season_name": "Especiais", "season": None, "folder_path": "",
                                  "episodes": sorted(special_eps, key=lambda e: (e["number"] if e["number"] is not None else -1, e["file_name"].casefold()))}],
                    "media_files": movie_eps,
                    "artwork_available": (
                        str(a["id"]) in local_artwork_anime
                        or bool(a["cover_cache"])
                    ),
                    "current_episode": current,
                    "next_episode": next_ep,
                    "available_count": len(available), "watched_count": len(watched),
                    "active_count": len(active), "missing_count": len(projected) - len(available),
                    "content_count": len(projected), "regular_count": len(regulars),
                    "special_count": len(special_eps), "movie_file_count": len(movie_eps),
                    "last_played_at": history.get(a["id"]),
                    "media_kind": a["media_kind"] or "series",
                })
            return result

    def set_episode_identification(self, path, *, season=None, number=None, episode_type="regular", title=None):
        """Persist an explicit user identification without changing consumption data."""
        if season is None:
            normalized_season = 0
        else:
            try:
                raw_season = float(season)
            except (TypeError, ValueError):
                raise ValueError("Temporada inválida.")
            if not math.isfinite(raw_season) or raw_season < 0 or not raw_season.is_integer():
                raise ValueError("Temporada inválida.")
            normalized_season = int(raw_season)
        if number is None:
            normalized_number = None
        else:
            try:
                normalized_number = float(number)
            except (TypeError, ValueError):
                raise ValueError("Número do episódio inválido.")
            if not math.isfinite(normalized_number) or normalized_number < 0:
                raise ValueError("Número do episódio inválido.")
        normalized_type = str(episode_type or "regular").casefold()
        allowed = {"regular", "special", "ova", "oad", "ona", "extra", "movie", "unknown"}
        if normalized_type not in allowed:
            raise ValueError("Tipo de episódio inválido.")
        clean_title = (str(title).strip() if title is not None else "") or None
        with self._conn() as c:
            row = c.execute("SELECT id FROM episodes WHERE path=?", (path,)).fetchone()
            if not row:
                raise ValueError("Arquivo local não encontrado.")
            c.execute(
                "UPDATE episodes SET season=?,number=?,episode_type=?,episode_title=?,"
                "identification_source='manual',identification_confidence='high',manual_override=1,missing=0 WHERE id=?",
                (normalized_season, normalized_number, normalized_type, clean_title, row["id"]),
            )
            if normalized_type == "movie":
                c.execute(
                    "UPDATE anime SET media_kind='movie' WHERE id=(SELECT anime_id FROM episodes WHERE id=?)",
                    (row["id"],),
                )
        return True

    def apply_episode_identification(self, path, *, absolute_number=None, relative_path=None, volume_id=None, volume_uuid=None, episode_type="regular", episode_title=None, identification_source="legacy", identification_confidence="medium"):
        with self._conn() as c:
            row=c.execute("SELECT manual_override FROM episodes WHERE path=?",(path,)).fetchone()
            if not row:
                raise ValueError("Arquivo local não encontrado.")
            if row["manual_override"]:
                c.execute("UPDATE episodes SET absolute_number=COALESCE(?,absolute_number),relative_path=COALESCE(?,relative_path),volume_id=COALESCE(?,volume_id),volume_uuid=COALESCE(?,volume_uuid),missing=0 WHERE path=?",(absolute_number,relative_path,volume_id,volume_uuid,path))
            else:
                c.execute("UPDATE episodes SET absolute_number=?,relative_path=COALESCE(?,relative_path),volume_id=COALESCE(?,volume_id),volume_uuid=COALESCE(?,volume_uuid),episode_type=?,episode_title=?,identification_source=?,identification_confidence=?,missing=0 WHERE path=?",(absolute_number,relative_path,volume_id,volume_uuid,episode_type,episode_title,identification_source,identification_confidence,path))
            return True

    def save_progress(self, path, position, duration, *, event_created_at=None):
        """Persist one normalized playback event through the central consumption policy.

        Native events may be duplicated or arrive late.  A newer event is allowed
        to seek backwards (a real user seek), while an older event is ignored so
        a delayed callback cannot regress durable state.
        """
        try:
            position, duration = float(position), float(duration)
            event_time = None if event_created_at is None else float(event_created_at)
        except (TypeError, ValueError):
            return False
        if not (math.isfinite(position) and math.isfinite(duration)):
            return False
        if event_created_at is not None and (event_time is None or not math.isfinite(event_time)):
            return False
        if position < 0 or duration < 0:
            return False
        if duration > 0:
            position = min(position, duration)
        now = time.time()
        if event_time is not None:
            event_time = event_time / 1000.0 if event_time > 10_000_000_000 else event_time
            last_seen = self._last_playback_event_at.get(path, 0.0)
            if event_time <= last_seen:
                return False
            with self._conn() as c:
                row = c.execute("SELECT last_played_at, watched FROM episodes WHERE path=?", (path,)).fetchone()
                if not row:
                    return False
                durable_time = float(row["last_played_at"] or 0.0)
                # last_played_at is also the durable playback-event clock. Older
                # events must never overwrite a newer event, including after a
                # Python process restart. This avoids using wall-clock processing
                # time, which could be later than the event that was just queued.
                if durable_time and event_time < durable_time - 0.001:
                    return False
                updated = c.execute(
                    "UPDATE episodes SET progress=?,duration=?,watched=?,last_played_at=? WHERE path=?",
                    (
                        position,
                        duration,
                        int(is_completed({"progress": position, "duration": duration, "watched": bool(row["watched"])})),
                        event_time,
                        path,
                    ),
                ).rowcount
            self._last_playback_event_at[path] = event_time
            return bool(updated)
        with self._conn() as c:
            row = c.execute("SELECT watched FROM episodes WHERE path=?", (path,)).fetchone()
            if not row:
                return False
            watched = int(is_completed({"progress": position, "duration": duration, "watched": bool(row["watched"])}))
            updated = c.execute(
                "UPDATE episodes SET progress=?,duration=?,watched=?,last_played_at=? WHERE path=?",
                (position, duration, watched, now, path),
            ).rowcount
        return bool(updated)

    @staticmethod
    def consumption_state(episode):
        return consumption_state(episode).value

    @staticmethod
    def is_completed(episode):
        return is_completed(episode)

    @staticmethod
    def is_in_progress(episode):
        return is_in_progress(episode)

    def set_watched(self, path, watched):
        """Set the existing episode completion state without a second player state."""
        with self._conn() as c:
            row = c.execute("SELECT duration FROM episodes WHERE path=?", (path,)).fetchone()
            if not row:
                return False
            duration = float(row["duration"] or 0)
            progress = duration if watched and duration > 0 else (0 if not watched else 0)
            c.execute("UPDATE episodes SET watched=?,progress=?,last_played_at=? WHERE path=?", (int(bool(watched)), progress, time.time(), path))
        return True

    @staticmethod
    def _episode_order_key(episode):
        def numeric(value, default=10**6):
            try:
                number = float(value)
            except (TypeError, ValueError):
                return default
            return number if math.isfinite(number) else default

        season = numeric(episode.get("season"))
        number = numeric(episode.get("number"))
        absolute = numeric(episode.get("absolute_number"))
        identity = str(episode.get("media_identity") or "")
        file_name = str(episode.get("file_name") or "").casefold()
        path = str(episode.get("path") or "").casefold()

        if number < 10**6:
            return (season, 1, number, absolute, identity, file_name, path)
        if absolute < 10**6:
            return (season, 0, absolute, identity, file_name, path)
        return (season, 0, 10**6, identity, file_name, path)

    @staticmethod
    def _adjacent_from_rows(current, available, direction):
        if not current:
            return None
        current_key = LibraryStore._episode_order_key(current)
        ordered = sorted(available, key=LibraryStore._episode_order_key)
        if direction < 0:
            ordered.reverse()
        for episode in ordered:
            key = LibraryStore._episode_order_key(episode)
            if (direction > 0 and key > current_key) or (direction < 0 and key < current_key):
                return episode
        return None

    def adjacent_episode(self, path, direction=1):
        """Return the adjacent playable local episode in catalog order.

        Missing rows deliberately remain in SQLite but are never playback
        destinations.  Keeping this policy here makes the Android bridge a
        transport layer rather than a second episode-ordering implementation.
        """
        if direction not in (-1, 1):
            raise ValueError("direction must be -1 or 1")
        with self._conn() as c:
            current = c.execute("SELECT * FROM episodes WHERE path=?", (path,)).fetchone()
            if not current:
                return None
            if not is_regular_episode(dict(current)):
                return None
            rows = c.execute(
                "SELECT e.*, a.title AS anime_title FROM episodes e JOIN anime a ON a.id=e.anime_id WHERE e.anime_id=? AND e.missing=0 AND e.episode_type NOT IN ('movie','special','ova','oad','ona','extra')",
                (current["anime_id"],),
            ).fetchall()
        # SQLite's NULL ordering differs from the catalog policy. Reusing the
        # same Python ordering here keeps episodes without a parsed number
        # navigable instead of making them invisible to next/previous.
        current_row = dict(current)
        return self._adjacent_from_rows(
            current_row,
            [dict(row) for row in rows],
            direction,
        )

    def next_episode(self, path):
        return self.adjacent_episode(path, 1)

    def previous_episode(self, path):
        return self.adjacent_episode(path, -1)

    @staticmethod
    def _current_from_rows(episodes):
        """Choose a playable current episode using one shared availability policy."""
        available = [episode for episode in episodes
                     if not episode.get("missing", False)
                     and is_regular_episode(episode)]
        available.sort(key=LibraryStore._episode_order_key)
        if not available:
            return None

        partial = next(
            (
                episode for episode in sorted(
                    available,
                    key=lambda entry: entry.get("last_played_at") or 0,
                    reverse=True,
                )
                if is_in_progress(episode)
            ),
            None,
        )
        if partial:
            return partial

        completed = [episode for episode in available if is_completed(episode)]
        if completed:
            # Sequence continuation follows the furthest completed episode,
            # so replaying an older episode cannot move Next Episode backwards.
            furthest_completed = max(completed, key=LibraryStore._episode_order_key)
            next_episode = LibraryStore._adjacent_from_rows(furthest_completed, available, 1)
            if next_episode:
                return next_episode

        for episode in available:
            if not is_completed(episode):
                return episode

        return available[0]

    def current_episode(self, anime_id):
        with self._conn() as c:
            anime = c.execute("SELECT media_kind FROM anime WHERE id=?", (anime_id,)).fetchone()
            rows = c.execute(
                "SELECT * FROM episodes WHERE anime_id=? AND missing=0",
                (anime_id,),
            ).fetchall()
        episodes = [dict(row) for row in rows]
        if anime and str(anime["media_kind"] or "series").casefold() == "movie":
            return episodes[0] if episodes else None
        return self._current_from_rows(episodes)

    def _conn_media_kind(self, anime_id):
        with self._conn() as c:
            row = c.execute("SELECT media_kind FROM anime WHERE id=?", (anime_id,)).fetchone()
            return row["media_kind"] if row else None

    def playback_target(self, anime_id):
        """Return the single local episode the Details primary action should play.

        This intentionally owns the continuation policy so the UI does not need
        to reproduce ordering, completion, or missing-file rules.
        """
        current = self.current_episode(anime_id)
        if current:
            return current
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM episodes WHERE anime_id=? AND missing=0",
                (anime_id,),
            ).fetchall()
        media_kind = str(self._conn_media_kind(anime_id) or "series").casefold()
        candidates = [
            dict(row) for row in rows
            if media_kind == "movie" or is_regular_episode(dict(row))
        ]
        ordered = sorted(candidates, key=self._episode_order_key)
        if ordered:
            return ordered[0]
        # A library containing only specials still needs a valid Details
        # playback target, but specials must never become part of the regular
        # episode sequence used by next/previous/autoplay.
        specials = [
            dict(row) for row in rows
            if str(row["episode_type"] or "").casefold() in {"special", "ova", "oad", "ona", "extra"}
        ]
        return sorted(specials, key=self._episode_order_key)[0] if specials else None

    def continue_watching(self, limit=12):
        """One playable continuation per anime, ordered by latest playback."""
        with self._conn() as c:
            rows = c.execute("""SELECT e.*, a.title AS anime_title, a.media_kind, a.cover_cache, a.cover_url
                FROM episodes e JOIN anime a ON a.id=e.anime_id
                ORDER BY e.anime_id, e.season, e.number, e.file_name""").fetchall()
        groups = {}
        for row in rows:
            groups.setdefault(row["anime_id"], []).append(dict(row))
        items = []
        for anime_id, episodes in groups.items():
            is_movie = str(episodes[0].get("media_kind") or "series").casefold() == "movie"
            available = [
                episode for episode in episodes
                if not episode["missing"] and (is_movie or is_regular_episode(episode))
            ]
            active = [episode for episode in available if is_in_progress(episode)]
            if not active:
                # Continue Watching is strictly a projection of resumable media.
                # The next episode belongs to the separate Next Episode projection.
                continue
            episode = max(active, key=lambda entry: entry.get("last_played_at") or 0)
            first = episodes[0]
            items.append({"anime_id": anime_id, "anime_title": first["anime_title"],
                          "cover": first["cover_cache"] or first["cover_url"], **episode})
        return sorted(items, key=lambda item: item.get("last_played_at") or 0, reverse=True)[:limit]

    def playback_history(self, limit=50):
        """Latest state for played local episodes; one durable row per episode."""
        with self._conn() as c:
            rows = c.execute("""SELECT e.*, a.title AS anime_title FROM episodes e
                JOIN anime a ON a.id=e.anime_id WHERE e.last_played_at IS NOT NULL
                ORDER BY e.last_played_at DESC LIMIT ?""", (limit,)).fetchall()
            return [dict(row) for row in rows]

    def account(self):
        with self._conn() as c: return {r["key"]: r["value"] for r in c.execute("SELECT key,value FROM account")}
    def save_account(self, values):
        with self._conn() as c: c.executemany("INSERT OR REPLACE INTO account(key,value) VALUES (?,?)", values.items())
    def clear_account(self):
        with self._conn() as c: c.execute("DELETE FROM account")
