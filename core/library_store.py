"""SQLite persistence for the local library and its document-folder diagnostics."""
from __future__ import annotations

import json
import os
import sqlite3
import time


class LibraryStore:
    SCHEMA_VERSION = 18
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
              season TEXT, status TEXT, episodes_count INTEGER, duration INTEGER, score INTEGER, studio TEXT,
              metadata_updated_at REAL, favorite INTEGER NOT NULL DEFAULT 0, user_tags TEXT NOT NULL DEFAULT '[]',
              media_kind TEXT NOT NULL DEFAULT 'series', is_pinned INTEGER NOT NULL DEFAULT 0, personal_note TEXT, added_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS episodes (
              id INTEGER PRIMARY KEY, anime_id INTEGER NOT NULL REFERENCES anime(id) ON DELETE CASCADE,
              path TEXT UNIQUE NOT NULL, file_name TEXT NOT NULL, season INTEGER NOT NULL,
              number REAL, duration REAL DEFAULT 0, progress REAL DEFAULT 0, watched INTEGER DEFAULT 0,
              mime_type TEXT, file_size INTEGER, modified_at REAL, source_folder TEXT,
              identity_key TEXT, absolute_number REAL, relative_path TEXT, volume_id TEXT, volume_uuid TEXT, missing INTEGER DEFAULT 0, last_played_at REAL);
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
            for column, definition in {"aliases": "TEXT DEFAULT '[]'", "score": "INTEGER", "metadata_updated_at": "REAL", "media_kind": "TEXT NOT NULL DEFAULT 'series'", "favorite": "INTEGER NOT NULL DEFAULT 0", "user_tags": "TEXT NOT NULL DEFAULT '[]'", "is_pinned": "INTEGER NOT NULL DEFAULT 0", "personal_note": "TEXT"}.items():
                if column not in anime_columns:
                    c.execute(f"ALTER TABLE anime ADD COLUMN {column} {definition}")
            episode_columns = {r[1] for r in c.execute("PRAGMA table_info(episodes)")}
            for column, definition in {"mime_type": "TEXT", "file_size": "INTEGER", "modified_at": "REAL", "source_folder": "TEXT", "identity_key": "TEXT", "absolute_number": "REAL", "relative_path": "TEXT", "volume_id": "TEXT", "volume_uuid": "TEXT", "last_played_at": "REAL", "episode_type": "TEXT NOT NULL DEFAULT 'regular'", "episode_title": "TEXT", "identification_source": "TEXT NOT NULL DEFAULT 'legacy'", "identification_confidence": "TEXT NOT NULL DEFAULT 'medium'", "manual_override": "INTEGER NOT NULL DEFAULT 0"}.items():
                if column not in episode_columns:
                    c.execute(f"ALTER TABLE episodes ADD COLUMN {column} {definition}")
            c.execute("CREATE INDEX IF NOT EXISTS idx_episodes_anime_playback ON episodes(anime_id, missing, watched, last_played_at)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_episodes_source_folder ON episodes(source_folder)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_episodes_scope_path ON episodes(source_folder, relative_path, volume_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_episodes_physical_state ON episodes(source_folder, file_size, modified_at, missing)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_episodes_identity_key ON episodes(identity_key)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_episodes_identification ON episodes(manual_override, identification_confidence, episode_type)")
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

    def upsert_anime(self, lookup, metadata):
        title = metadata.get("title") or lookup
        incoming_kind = str(metadata.get("media_kind") or "series").casefold()
        if incoming_kind not in {"series", "movie", "unknown"}:
            incoming_kind = "series"
        fields = (metadata.get("anilist_id"), title, metadata.get("romaji"), metadata.get("english"), metadata.get("native"), metadata.get("aliases", "[]"), metadata.get("description", "Anime armazenado localmente."), metadata.get("cover_url", ""), metadata.get("cover_cache", ""), metadata.get("banner_url", ""), metadata.get("genres", "[]"), metadata.get("year"), metadata.get("season"), metadata.get("status"), metadata.get("episodes_count"), metadata.get("duration"), metadata.get("score"), metadata.get("studio"), metadata.get("metadata_updated_at", time.time()), incoming_kind)
        with self._conn() as c:
            row = c.execute("SELECT * FROM anime WHERE lookup_title=?", (lookup,)).fetchone()
            if row:
                # A transient cover-download failure must never erase a previously
                # cached image.  The same rule applies to a missing remote URL.
                cover_cache = metadata.get("cover_cache") or row["cover_cache"] or ""
                cover_url = metadata.get("cover_url") or row["cover_url"] or ""
                media_kind = incoming_kind if incoming_kind == "movie" or not row["media_kind"] or row["media_kind"] == "unknown" else row["media_kind"]
                fields = fields[:7] + (cover_url, cover_cache) + fields[9:]
                c.execute("""UPDATE anime SET anilist_id=?,title=?,romaji=?,english=?,native=?,aliases=?,description=?,cover_url=?,cover_cache=?,banner_url=?,genres=?,year=?,season=?,status=?,episodes_count=?,duration=?,score=?,studio=?,metadata_updated_at=?,media_kind=? WHERE id=?""", fields + (media_kind, row["id"]))
                return row["id"]
            cur = c.execute("""INSERT INTO anime(lookup_title,anilist_id,title,romaji,english,native,aliases,description,cover_url,cover_cache,banner_url,genres,year,season,status,episodes_count,duration,score,studio,metadata_updated_at,media_kind,added_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (lookup,) + fields + (time.time(),))
            return cur.lastrowid

    def upsert_episode(self, anime_id, path, file_name, season, number, mime_type=None, file_size=None, modified_at=None, source_folder=None, identity_key=None, absolute_number=None, relative_path=None, volume_id=None, volume_uuid=None, *, episode_type="regular", episode_title=None, identification_source="legacy", identification_confidence="medium"):
        # Old rows required a non-null season. Zero is the durable representation
        # for an unknown season; catalog presentation maps it to "Sem temporada".
        season = 0 if season is None else int(season)
        with self._conn() as c:
            existing = c.execute("SELECT * FROM episodes WHERE path=?", (path,)).fetchone()
            if existing:
                if existing["manual_override"]:
                    c.execute("UPDATE episodes SET file_name=?,mime_type=?,file_size=?,modified_at=?,source_folder=?,identity_key=COALESCE(?,identity_key),absolute_number=COALESCE(?,absolute_number),relative_path=COALESCE(?,relative_path),volume_id=COALESCE(?,volume_id),volume_uuid=COALESCE(?,volume_uuid),missing=0 WHERE path=?",
                              (file_name, mime_type, file_size, modified_at, source_folder, identity_key, absolute_number, relative_path, volume_id, volume_uuid, path))
                    return existing["id"]
                c.execute("""UPDATE episodes SET anime_id=?,file_name=?,season=?,number=?,mime_type=?,file_size=?,modified_at=?,source_folder=?,identity_key=COALESCE(?,identity_key),absolute_number=COALESCE(?,absolute_number),relative_path=COALESCE(?,relative_path),volume_id=COALESCE(?,volume_id),volume_uuid=COALESCE(?,volume_uuid),missing=0 WHERE path=?""",
                          (anime_id, file_name, season, number, mime_type, file_size, modified_at, source_folder, identity_key, absolute_number, relative_path, volume_id, volume_uuid, path))
                c.execute("UPDATE episodes SET episode_type=?,episode_title=?,identification_source=?,identification_confidence=? WHERE path=?", (episode_type, episode_title, identification_source, identification_confidence, path))
                return existing["id"]

            matching_row = None
            # Filename + size is not identity: two releases can share both.
            # identity_key exists only with a proven local relative path plus
            # size/time evidence; cloud SAF intentionally has no such key.
            if identity_key:
                row = c.execute("SELECT * FROM episodes WHERE identity_key=?", (identity_key,)).fetchone()
                if row:
                    matching_row = dict(row)

            if matching_row:
                if matching_row["manual_override"]:
                    c.execute("UPDATE episodes SET path=?,file_name=?,mime_type=?,file_size=?,modified_at=?,source_folder=?,identity_key=?,absolute_number=COALESCE(?,absolute_number),relative_path=COALESCE(?,relative_path),volume_id=COALESCE(?,volume_id),volume_uuid=COALESCE(?,volume_uuid),missing=0 WHERE id=?", (path, file_name, mime_type, file_size, modified_at, source_folder, identity_key, absolute_number, relative_path, volume_id, volume_uuid, matching_row["id"]))
                    return matching_row["id"]
                c.execute("""UPDATE episodes SET anime_id=?,path=?,file_name=?,season=?,number=?,mime_type=?,file_size=?,modified_at=?,source_folder=?,identity_key=?,absolute_number=COALESCE(?,absolute_number),relative_path=COALESCE(?,relative_path),volume_id=COALESCE(?,volume_id),volume_uuid=COALESCE(?,volume_uuid),missing=0 WHERE id=?""",
                          (anime_id, path, file_name, season, number, mime_type, file_size, modified_at, source_folder, identity_key, absolute_number, relative_path, volume_id, volume_uuid, matching_row["id"]))
                c.execute("UPDATE episodes SET episode_type=?,episode_title=?,identification_source=?,identification_confidence=? WHERE id=?", (episode_type, episode_title, identification_source, identification_confidence, matching_row["id"]))
                return matching_row["id"]

            cur = c.execute("""INSERT INTO episodes(anime_id,path,file_name,season,number,mime_type,file_size,modified_at,source_folder,identity_key,absolute_number,relative_path,volume_id,volume_uuid,episode_type,episode_title,identification_source,identification_confidence,missing) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, ?,0)""",
                            (anime_id, path, file_name, season, number, mime_type, file_size, modified_at, source_folder, identity_key, absolute_number, relative_path, volume_id, volume_uuid, episode_type, episode_title, identification_source, identification_confidence))
            return cur.lastrowid

    def set_episode_identification(self, path, *, season=None, number=None, episode_type="regular", title=None):
        """Persist an explicit user correction which automatic scans cannot replace."""
        season = 0 if season is None else int(season)
        if episode_type not in {"regular", "special", "ova", "oad", "ona", "extra", "movie", "unknown"}:
            raise ValueError("Tipo de episódio inválido.")
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
                    "title": e["file_name"], "episode_title": e["episode_title"], "path": e["path"],
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
                try:
                    user_tags = json.loads(a["user_tags"] or "[]")
                except (TypeError, json.JSONDecodeError):
                    user_tags = []
                season_projection = [{
                    "season_name": f"Temporada {season}" if season else "Sem temporada",
                    "season": season, "folder_path": "",
                    "episodes": sorted(values, key=self._episode_order_key),
                } for season, values in sorted(seasons.items(), key=lambda item: item[0] if item[0] is not None else -1)]
                animes.append({
                    "id": a["id"], "main_title": a["title"], "media_kind": media_kind,
                    "is_movie": media_kind == "movie", "meta": dict(a),
                    "favorite": bool(a["favorite"]), "is_pinned": bool(a["is_pinned"]),
                    "personal_note": a["personal_note"] or "", "user_tags": user_tags, "genres": genres,
                    "seasons": [] if media_kind == "movie" else season_projection,
                    "specials": [{"season_name": "Especiais", "season": 0, "folder_path": "", "episodes": sorted(specials, key=self._episode_order_key)}] if specials else [],
                    "media_files": sorted(movies, key=self._episode_order_key) if media_kind == "movie" else [],
                })
            for anime in animes:
                rows = episodes_by_anime[anime["id"]]
                eligible = [row for row in rows if row["episode_type"] not in {"movie", *special_types}]
                anime["current_episode"] = self._current_from_rows(eligible or [row for row in rows if row["episode_type"] != "movie"])
            return animes

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
