"""SQLite persistence for the local library and its document-folder diagnostics."""
from __future__ import annotations

import json
import os
import sqlite3
import time


class LibraryStore:
    SCHEMA_VERSION = 20
    def __init__(self, data_dir: str):
        os.makedirs(data_dir, exist_ok=True)
        self.db_path = os.path.join(data_dir, "library.sqlite3")
        self.cache_dir = os.path.join(data_dir, "covers")
        os.makedirs(self.cache_dir, exist_ok=True)
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
        tag_count = len({str(tag).casefold() for entry in tags for tag in self._decode_tags(entry["user_tags"])})
        available = int(episodes["available"] or 0)
        watched = int(episodes["watched"] or 0)
        return {"animes": int(row["animes"] or 0), "episodes": int(episodes["total"] or 0), "episodes_available": available,
                "episodes_watched": watched, "animes_in_progress": self._anime_state_count("in_progress"),
                "animes_completed": self._anime_state_count("completed"), "animes_not_started": self._anime_state_count("not_started"),
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
                        if key not in metadata:
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
            c.execute("""INSERT INTO anime(lookup_title,anilist_id,title,romaji,english,native,aliases,description,cover_url,cover_cache,banner_url,genres,year,season,status,episodes_count,duration,score,format,studio,metadata_updated_at,metadata_fetched_at,metadata_source,metadata_confidence,metadata_status,metadata_manual_fields,media_kind,added_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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

    def upsert_episode(self, anime_id, path, file_name, season, number, mime_type=None, file_size=None, modified_at=None, source_folder=None, media_identity=None, absolute_number=None, episode_type="regular", episode_title=None):
        """Upsert by URI, then by proven cross-source identity."""
        with self._conn() as c:
            by_path = c.execute("SELECT * FROM episodes WHERE path=?", (path,)).fetchone()
            by_identity = None
            if media_identity:
                by_identity = c.execute(
                    "SELECT * FROM episodes WHERE media_identity=? ORDER BY id LIMIT 1",
                    (media_identity,),
                ).fetchone()

            def update_existing(row_id, new_path=None):
                if new_path is None:
                    c.execute(
                        """UPDATE episodes SET anime_id=?,file_name=?,season=?,number=?,mime_type=?,
                           file_size=?,modified_at=?,source_folder=?,media_identity=?,absolute_number=?,
                           episode_type=?,episode_title=?,missing=0 WHERE id=?""",
                        (anime_id,file_name,season,number,mime_type,file_size,modified_at,source_folder,
                         media_identity,absolute_number,episode_type,episode_title,row_id),
                    )
                else:
                    c.execute(
                        """UPDATE episodes SET anime_id=?,path=?,file_name=?,season=?,number=?,mime_type=?,
                           file_size=?,modified_at=?,source_folder=?,media_identity=?,absolute_number=?,
                           episode_type=?,episode_title=?,missing=0 WHERE id=?""",
                        (anime_id,new_path,file_name,season,number,mime_type,file_size,modified_at,source_folder,
                         media_identity,absolute_number,episode_type,episode_title,row_id),
                    )
                return row_id

            if by_path and by_identity and by_path["id"] != by_identity["id"]:
                progress = max(float(by_path["progress"] or 0), float(by_identity["progress"] or 0))
                watched = max(int(by_path["watched"] or 0), int(by_identity["watched"] or 0))
                last_played = max(float(by_path["last_played_at"] or 0), float(by_identity["last_played_at"] or 0)) or None
                c.execute(
                    """UPDATE episodes SET anime_id=?,path=?,file_name=?,season=?,number=?,mime_type=?,
                       file_size=?,modified_at=?,source_folder=?,media_identity=?,absolute_number=?,
                       episode_type=?,episode_title=?,missing=0,progress=?,watched=?,last_played_at=? WHERE id=?""",
                    (anime_id,path,file_name,season,number,mime_type,file_size,modified_at,source_folder,
                     media_identity,absolute_number,episode_type,episode_title,progress,watched,last_played,by_identity["id"]),
                )
                c.execute("DELETE FROM episodes WHERE id=?", (by_path["id"],))
                return by_identity["id"]

            if by_path:
                return update_existing(by_path["id"])
            if by_identity:
                return update_existing(by_identity["id"], new_path=path)

            cur = c.execute(
                """INSERT INTO episodes(anime_id,path,file_name,season,number,mime_type,file_size,modified_at,
                                         source_folder,missing,media_identity,absolute_number,episode_type,episode_title)
                   VALUES(?,?,?,?,?,?,?,?,?,0,?,?,?,?,?)""",
                (anime_id,path,file_name,season,number,mime_type,file_size,modified_at,source_folder,
                 media_identity,absolute_number,episode_type,episode_title),
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
        """Project physical media into the logical local library hierarchy."""
        with self._conn() as c:
            animes = []
            query = "SELECT * FROM anime" + (" WHERE favorite=1" if favorites_only else "") + " ORDER BY added_at DESC, title COLLATE NOCASE"
            anime_rows = c.execute(query).fetchall()
            episode_rows = c.execute("SELECT * FROM episodes ORDER BY anime_id, season, number, absolute_number, file_name").fetchall()
            episodes_by_anime = {}
            for episode in episode_rows:
                episodes_by_anime.setdefault(episode["anime_id"], []).append(dict(episode))

            def project(e):
                return {
                    "title": e["file_name"], "file_name": e["file_name"], "episode_title": e["episode_title"], "path": e["path"],
                    "season": e["season"], "number": e["number"], "absolute_number": e["absolute_number"],
                    "episode_type": e["episode_type"], "identification_source": e["identification_source"],
                    "identification_confidence": e["identification_confidence"], "manual_override": bool(e["manual_override"]),
                    "progress": e["progress"], "duration": e["duration"], "watched": bool(e["watched"]),
                    "missing": bool(e["missing"]), "last_played_at": e["last_played_at"],
                    "mime_type": e["mime_type"], "file_size": e["file_size"], "modified_at": e["modified_at"],
                    "source_folder": e["source_folder"], "relative_path": e["relative_path"], "volume_id": e["volume_id"], "volume_uuid": e["volume_uuid"],
                }

            special_types = {"special", "ova", "oad", "ona", "extra"}
            for a in anime_rows:
                eps = episodes_by_anime.get(a["id"], [])
                if not eps:
                    continue
                projected = [project(e) for e in eps]
                media_kind = a["media_kind"] or "series"
                movies = [item for item in projected if item["episode_type"] == "movie"]
                specials = [item for item in projected if item["episode_type"] in special_types]
                regulars = [item for item in projected if item["episode_type"] not in special_types and item["episode_type"] != "movie"]
                seasons = {}
                for ep in regulars:
                    seasons.setdefault(ep["season"], []).append(ep)
                try:
                    genres = json.loads(a["genres"] or "[]")
                except (TypeError, json.JSONDecodeError):
                    genres = []
                ordered_seasons = sorted(seasons.items(), key=lambda item: item[0] if item[0] is not None else -1)
                animes.append({"id": a["id"], "main_title": a["title"], "meta": dict(a), "favorite": bool(a["favorite"]), "genres": genres, "seasons": [{"season_name": f"Temporada {s}", "season": s, "folder_path": "", "episodes": [{"title": e["file_name"], "path": e["path"], "season": e["season"], "number": e["number"], "progress": e["progress"], "duration": e["duration"], "watched": bool(e["watched"]), "missing": bool(e["missing"]), "last_played_at": e["last_played_at"], "mime_type": e["mime_type"], "file_size": e["file_size"], "modified_at": e["modified_at"], "source_folder": e["source_folder"], "media_identity": e["media_identity"]} for e in sorted(values, key=lambda episode: (episode["number"] if episode["number"] is not None else -1, episode["file_name"].casefold(), episode["path"].casefold()))]} for s, values in ordered_seasons]})
            for anime in animes:
                rows = episodes_by_anime[anime["id"]]
                eligible = [row for row in rows if row["episode_type"] not in {"movie", *special_types}]
                anime["current_episode"] = self._current_from_rows(eligible or [row for row in rows if row["episode_type"] != "movie"])
            return animes

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

    def save_progress(self, path, position, duration):
        try:
            position, duration = float(position), float(duration)
        except (TypeError, ValueError):
            return False
        if position < 0 or duration < 0:
            return False
        if duration == 0:
            position = 0
        else:
            position = min(position, duration)
        watched = int(duration > 0 and position / duration >= .9)
        with self._conn() as c:
            updated = c.execute("UPDATE episodes SET progress=?,duration=?,watched=?,last_played_at=? WHERE path=?", (position, duration, watched, time.time(), path)).rowcount
        return bool(updated)

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
        number = episode.get("number")
        if number is None:
            return (
                episode.get("season") if episode.get("season") is not None else 1,
                0,
                (episode.get("file_name") or "").casefold(),
                (episode.get("path") or "").casefold(),
            )
        return (
            episode.get("season") if episode.get("season") is not None else 1,
            1,
            number,
            (episode.get("file_name") or "").casefold(),
            (episode.get("path") or "").casefold(),
        )

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
        available = [episode for episode in episodes if not episode.get("missing", False)]
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
                if episode.get("progress", 0) > 0 and not episode.get("watched", False)
            ),
            None,
        )
        if partial:
            return partial

        completed = [episode for episode in available if episode.get("watched", False)]
        if completed:
            latest_completed = max(completed, key=lambda entry: entry.get("last_played_at") or 0)
            next_episode = LibraryStore._adjacent_from_rows(latest_completed, available, 1)
            if next_episode:
                return next_episode

        for episode in available:
            if not episode.get("watched", False):
                return episode

        return available[0]

    def current_episode(self, anime_id):
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM episodes WHERE anime_id=?",
                (anime_id,),
            ).fetchall()
        return self._current_from_rows([dict(row) for row in rows])

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
        ordered = sorted(
            (dict(row) for row in rows),
            key=self._episode_order_key,
        )
        return ordered[0] if ordered else None

    def continue_watching(self, limit=12):
        """One playable continuation per anime, ordered by latest playback."""
        with self._conn() as c:
            rows = c.execute("""SELECT e.*, a.title AS anime_title, a.cover_cache, a.cover_url
                FROM episodes e JOIN anime a ON a.id=e.anime_id
                ORDER BY e.anime_id, e.season, e.number, e.file_name""").fetchall()
        groups = {}
        for row in rows:
            groups.setdefault(row["anime_id"], []).append(dict(row))
        items = []
        for anime_id, episodes in groups.items():
            available = [episode for episode in episodes if not episode["missing"]]
            latest_played = max((episode.get("last_played_at") or 0 for episode in available), default=0)
            if not latest_played:
                continue
            active = [episode for episode in available if episode["progress"] > 0 and not episode["watched"]]
            if active:
                episode = max(active, key=lambda entry: entry.get("last_played_at") or 0)
            else:
                completed = [episode for episode in available if episode["watched"]]
                episode = self._adjacent_from_rows(max(completed, key=lambda entry: entry.get("last_played_at") or 0), available, 1) if completed else None
            if not episode:
                continue
            episode = dict(episode)
            episode["last_played_at"] = latest_played
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
