"""SQLite persistence for the local library and its document-folder diagnostics."""
from __future__ import annotations

import json
import os
import sqlite3
import time


class LibraryStore:
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
              authorization TEXT NOT NULL DEFAULT 'unknown', added_at REAL NOT NULL,
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
            CREATE TABLE IF NOT EXISTS scan_runs (
              id INTEGER PRIMARY KEY, started_at REAL NOT NULL, finished_at REAL, folders INTEGER DEFAULT 0,
              files INTEGER DEFAULT 0, videos INTEGER DEFAULT 0, animes INTEGER DEFAULT 0,
              episodes INTEGER DEFAULT 0, errors TEXT NOT NULL DEFAULT '[]');
            ''')
            # Migration for databases made by earlier versions.
            existing = {r[1] for r in c.execute("PRAGMA table_info(folders)")}
            for column, definition in {
                "name": "TEXT", "kind": "TEXT NOT NULL DEFAULT 'path'", "authorization": "TEXT NOT NULL DEFAULT 'unknown'",
                "last_scan_at": "REAL", "last_error": "TEXT",
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

    def folders(self):
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM folders ORDER BY added_at")]

    def add_folder(self, reference, name=None, kind="path", authorization="granted"):
        name = name or os.path.basename(reference.rstrip("/")) or reference
        with self._conn() as c:
            c.execute("""INSERT INTO folders(path,name,kind,authorization,added_at) VALUES (?,?,?,?,?)
                         ON CONFLICT(path) DO UPDATE SET name=excluded.name,kind=excluded.kind,
                         authorization=excluded.authorization,last_error=NULL""",
                      (reference, name, kind, authorization, time.time()))

    def update_folder_status(self, reference, authorization, error=None):
        with self._conn() as c:
            c.execute("UPDATE folders SET authorization=?,last_error=?,last_scan_at=? WHERE path=?",
                      (authorization, error, time.time(), reference))

    def remove_folder(self, reference):
        with self._conn() as c:
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
            row = c.execute("SELECT id FROM anime WHERE lookup_title=?", (lookup,)).fetchone()
            if row:
                c.execute("""UPDATE anime SET anilist_id=?,title=?,romaji=?,english=?,native=?,aliases=?,description=?,cover_url=?,cover_cache=?,banner_url=?,genres=?,year=?,season=?,status=?,episodes_count=?,duration=?,score=?,studio=?,metadata_updated_at=? WHERE id=?""", fields + (row[0],))
                return row[0]
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
            for a in c.execute(query):
                eps = c.execute("SELECT * FROM episodes WHERE anime_id=? ORDER BY season, number, file_name", (a["id"],)).fetchall()
                if not eps: continue
                seasons = {}
                for ep in eps: seasons.setdefault(ep["season"], []).append(dict(ep))
                animes.append({"id": a["id"], "main_title": a["title"], "meta": dict(a), "favorite": bool(a["favorite"]), "genres": json.loads(a["genres"] or "[]"), "seasons": [{"season_name": f"Temporada {s}", "season": s, "folder_path": "", "episodes": [{"title": e["file_name"], "path": e["path"], "season": e["season"], "number": e["number"], "progress": e["progress"], "duration": e["duration"], "watched": bool(e["watched"]), "missing": bool(e["missing"]), "last_played_at": e["last_played_at"], "mime_type": e["mime_type"], "file_size": e["file_size"], "modified_at": e["modified_at"]} for e in values]} for s, values in seasons.items()]})
            for anime in animes:
                anime["current_episode"] = self.current_episode(anime["id"])
            return animes

    def save_progress(self, path, position, duration):
        watched = int(duration > 0 and position / duration >= .9)
        with self._conn() as c: c.execute("UPDATE episodes SET progress=?,duration=?,watched=?,last_played_at=? WHERE path=?", (position, duration, watched, time.time(), path))

    def adjacent_episode(self, path, direction=1):
        """Return the adjacent playable local episode in catalog order.

        Missing rows deliberately remain in SQLite but are never playback
        destinations.  Keeping this policy here makes the Android bridge a
        transport layer rather than a second episode-ordering implementation.
        """
        if direction not in (-1, 1):
            raise ValueError("direction must be -1 or 1")
        comparison = "<" if direction < 0 else ">"
        ordering = "DESC" if direction < 0 else "ASC"
        with self._conn() as c:
            current = c.execute("SELECT anime_id,season,number FROM episodes WHERE path=?", (path,)).fetchone()
            if not current:
                return None
            number = current["number"] if current["number"] is not None else (-1 if direction > 0 else float("inf"))
            row = c.execute(f"""SELECT * FROM episodes WHERE anime_id=? AND missing=0
                AND (season {comparison} ? OR (season=? AND number {comparison} ?))
                ORDER BY season {ordering}, number {ordering}, file_name {ordering} LIMIT 1""",
                (current["anime_id"], current["season"], current["season"], number)).fetchone()
            return dict(row) if row else None

    def next_episode(self, path):
        return self.adjacent_episode(path, 1)

    def previous_episode(self, path):
        return self.adjacent_episode(path, -1)

    def current_episode(self, anime_id):
        with self._conn() as c:
            active = c.execute("""SELECT * FROM episodes WHERE anime_id=? AND missing=0 AND progress>0 AND watched=0
                ORDER BY last_played_at DESC LIMIT 1""", (anime_id,)).fetchone()
            if active:
                return dict(active)
            completed = c.execute("""SELECT * FROM episodes WHERE anime_id=? AND watched=1
                ORDER BY last_played_at DESC LIMIT 1""", (anime_id,)).fetchone()
        return self.next_episode(completed["path"]) if completed else None

    def playback_target(self, anime_id):
        """Return the single local episode the Details primary action should play.

        This intentionally owns the continuation policy so the UI does not need
        to reproduce ordering, completion, or missing-file rules.
        """
        current = self.current_episode(anime_id)
        if current:
            return current
        with self._conn() as c:
            first = c.execute("""SELECT * FROM episodes WHERE anime_id=? AND missing=0
                ORDER BY season, number, file_name LIMIT 1""", (anime_id,)).fetchone()
        return dict(first) if first else None

    def continue_watching(self, limit=12):
        """One playable continuation per anime, ordered by latest playback."""
        with self._conn() as c:
            recent = c.execute("""SELECT DISTINCT anime_id FROM episodes WHERE last_played_at IS NOT NULL
                ORDER BY last_played_at DESC""").fetchall()
        items = []
        for row in recent:
            episode = self.current_episode(row["anime_id"])
            if not episode or episode["missing"]:
                continue
            if not episode["watched"] and episode["progress"] <= 0:
                # A finished episode may advance to an unstarted next item; it
                # is still a valid continuation, ordered by the completion time.
                latest = episode
                with self._conn() as c:
                    latest = c.execute("SELECT last_played_at FROM episodes WHERE anime_id=? ORDER BY last_played_at DESC LIMIT 1", (row["anime_id"],)).fetchone()
                episode["last_played_at"] = latest["last_played_at"] if latest else None
            with self._conn() as c:
                anime = c.execute("SELECT id,title,cover_cache,cover_url FROM anime WHERE id=?", (row["anime_id"],)).fetchone()
            items.append({"anime_id": anime["id"], "anime_title": anime["title"], "cover": anime["cover_cache"] or anime["cover_url"], **episode})
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
