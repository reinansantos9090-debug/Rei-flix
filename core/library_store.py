"""SQLite persistence for the local library and its document-folder diagnostics."""
from __future__ import annotations

import json
import os
import sqlite3
import time


class LibraryStore:
    SCHEMA_VERSION = 11
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
              metadata_updated_at REAL, favorite INTEGER NOT NULL DEFAULT 0, added_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS episodes (
              id INTEGER PRIMARY KEY, anime_id INTEGER NOT NULL REFERENCES anime(id) ON DELETE CASCADE,
              path TEXT UNIQUE NOT NULL, file_name TEXT NOT NULL, season INTEGER NOT NULL,
              number REAL, duration REAL DEFAULT 0, progress REAL DEFAULT 0, watched INTEGER DEFAULT 0,
              mime_type TEXT, file_size INTEGER, modified_at REAL, source_folder TEXT,
              missing INTEGER DEFAULT 0, last_played_at REAL);
            CREATE TABLE IF NOT EXISTS associations (lookup_title TEXT PRIMARY KEY, anilist_id INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS pending_matches (lookup_title TEXT PRIMARY KEY, display_title TEXT NOT NULL, candidates TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS account (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS scan_runs (
              id INTEGER PRIMARY KEY, started_at REAL NOT NULL, finished_at REAL, folders INTEGER DEFAULT 0,
              files INTEGER DEFAULT 0, videos INTEGER DEFAULT 0, animes INTEGER DEFAULT 0,
              episodes INTEGER DEFAULT 0, errors TEXT NOT NULL DEFAULT '[]');
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
            for column, definition in {"aliases": "TEXT DEFAULT '[]'", "score": "INTEGER", "metadata_updated_at": "REAL", "favorite": "INTEGER NOT NULL DEFAULT 0"}.items():
                if column not in anime_columns:
                    c.execute(f"ALTER TABLE anime ADD COLUMN {column} {definition}")
            episode_columns = {r[1] for r in c.execute("PRAGMA table_info(episodes)")}
            for column, definition in {"mime_type": "TEXT", "file_size": "INTEGER", "modified_at": "REAL", "source_folder": "TEXT", "last_played_at": "REAL"}.items():
                if column not in episode_columns:
                    c.execute(f"ALTER TABLE episodes ADD COLUMN {column} {definition}")
            c.execute("CREATE INDEX IF NOT EXISTS idx_episodes_anime_playback ON episodes(anime_id, missing, watched, last_played_at)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_episodes_source_folder ON episodes(source_folder)")
            # Version records make the additive Phase 10 migration auditable
            # while CREATE IF NOT EXISTS keeps all earlier databases intact.
            c.execute("CREATE INDEX IF NOT EXISTS idx_folders_account ON folders(account_id)")
            c.execute("INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES (?,?)", (self.SCHEMA_VERSION, time.time()))

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

    def begin_scan(self):
        with self._conn() as c:
            cur = c.execute("INSERT INTO scan_runs(started_at) VALUES (?)", (time.time(),))
            return cur.lastrowid

    def finish_scan(self, run_id, summary):
        with self._conn() as c:
            c.execute("""UPDATE scan_runs SET finished_at=?,folders=?,files=?,videos=?,animes=?,episodes=?,errors=? WHERE id=?""",
                      (time.time(), summary["folders"], summary["files"], summary["videos"], summary["animes"],
                       summary["episodes"], json.dumps(summary["errors"], ensure_ascii=False), run_id))

    def last_scan(self):
        with self._conn() as c:
            row = c.execute("SELECT * FROM scan_runs ORDER BY id DESC LIMIT 1").fetchone()
            return dict(row) if row else None

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

    def is_favorite(self, anime_id):
        with self._conn() as c:
            row = c.execute("SELECT favorite FROM anime WHERE id=?", (anime_id,)).fetchone()
            return bool(row and row[0])

    def upsert_anime(self, lookup, metadata):
        title = metadata.get("title") or lookup
        fields = (metadata.get("anilist_id"), title, metadata.get("romaji"), metadata.get("english"), metadata.get("native"), metadata.get("aliases", "[]"), metadata.get("description", "Anime armazenado localmente."), metadata.get("cover_url", ""), metadata.get("cover_cache", ""), metadata.get("banner_url", ""), metadata.get("genres", "[]"), metadata.get("year"), metadata.get("season"), metadata.get("status"), metadata.get("episodes_count"), metadata.get("duration"), metadata.get("score"), metadata.get("studio"), metadata.get("metadata_updated_at", time.time()))
        with self._conn() as c:
            row = c.execute("SELECT * FROM anime WHERE lookup_title=?", (lookup,)).fetchone()
            if row:
                # A transient cover-download failure must never erase a previously
                # cached image.  The same rule applies to a missing remote URL.
                cover_cache = metadata.get("cover_cache") or row["cover_cache"] or ""
                cover_url = metadata.get("cover_url") or row["cover_url"] or ""
                fields = fields[:7] + (cover_url, cover_cache) + fields[9:]
                c.execute("""UPDATE anime SET anilist_id=?,title=?,romaji=?,english=?,native=?,aliases=?,description=?,cover_url=?,cover_cache=?,banner_url=?,genres=?,year=?,season=?,status=?,episodes_count=?,duration=?,score=?,studio=?,metadata_updated_at=? WHERE id=?""", fields + (row["id"],))
                return row["id"]
            cur = c.execute("""INSERT INTO anime(lookup_title,anilist_id,title,romaji,english,native,aliases,description,cover_url,cover_cache,banner_url,genres,year,season,status,episodes_count,duration,score,studio,metadata_updated_at,added_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (lookup,) + fields + (time.time(),))
            return cur.lastrowid

    def upsert_episode(self, anime_id, path, file_name, season, number, mime_type=None, file_size=None, modified_at=None, source_folder=None):
        with self._conn() as c:
            c.execute("""INSERT INTO episodes(anime_id,path,file_name,season,number,mime_type,file_size,modified_at,source_folder,missing) VALUES(?,?,?,?,?,?,?,?,?,0)
                ON CONFLICT(path) DO UPDATE SET anime_id=excluded.anime_id,file_name=excluded.file_name,season=excluded.season,number=excluded.number,mime_type=excluded.mime_type,file_size=excluded.file_size,modified_at=excluded.modified_at,source_folder=excluded.source_folder,missing=0""", (anime_id, path, file_name, season, number, mime_type, file_size, modified_at, source_folder))

    def mark_missing(self, source_folder, seen):
        """Mark only one successfully scanned source, preserving other folders."""
        with self._conn() as c:
            c.execute("UPDATE episodes SET missing=1 WHERE source_folder=?", (source_folder,))
            if seen: c.executemany("UPDATE episodes SET missing=0 WHERE path=?", ((p,) for p in seen))

    def catalog(self, favorites_only=False):
        with self._conn() as c:
            animes = []
            query = "SELECT * FROM anime" + (" WHERE favorite=1" if favorites_only else "") + " ORDER BY added_at DESC, title COLLATE NOCASE"
            anime_rows = c.execute(query).fetchall()
            # One episode query avoids a growing N+1 cost on Home/Organizar.
            episode_rows = c.execute("SELECT * FROM episodes ORDER BY anime_id, season, number, file_name").fetchall()
            episodes_by_anime = {}
            for episode in episode_rows:
                episodes_by_anime.setdefault(episode["anime_id"], []).append(dict(episode))
            for a in anime_rows:
                eps = episodes_by_anime.get(a["id"], [])
                if not eps:
                    continue
                seasons = {}
                for ep in eps:
                    seasons.setdefault(ep["season"], []).append(ep)
                try:
                    genres = json.loads(a["genres"] or "[]")
                except (TypeError, json.JSONDecodeError):
                    genres = []
                ordered_seasons = sorted(seasons.items(), key=lambda item: item[0] if item[0] is not None else -1)
                animes.append({"id": a["id"], "main_title": a["title"], "meta": dict(a), "favorite": bool(a["favorite"]), "genres": genres, "seasons": [{"season_name": f"Temporada {s}", "season": s, "folder_path": "", "episodes": [{"title": e["file_name"], "path": e["path"], "season": e["season"], "number": e["number"], "progress": e["progress"], "duration": e["duration"], "watched": bool(e["watched"]), "missing": bool(e["missing"]), "last_played_at": e["last_played_at"], "mime_type": e["mime_type"], "file_size": e["file_size"], "modified_at": e["modified_at"]} for e in sorted(values, key=lambda episode: (episode["number"] if episode["number"] is not None else -1, episode["file_name"].casefold()))]} for s, values in ordered_seasons]})
            for anime in animes:
                rows = episodes_by_anime[anime["id"]]
                anime["current_episode"] = self._current_from_rows(rows)
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

    @staticmethod
    def _episode_order_key(episode):
        number = episode.get("number")
        return (
            episode.get("season") or 0,
            0 if number is not None else 1,
            number if number is not None else 0,
            (episode.get("file_name") or "").casefold(),
            episode.get("path") or "",
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
                "SELECT e.*, a.title AS anime_title FROM episodes e JOIN anime a ON a.id=e.anime_id WHERE e.anime_id=? AND e.missing=0",
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
