"""Real recursive scanner for references that the Python process can read."""
from __future__ import annotations
import os
import time
import json
import logging
from dataclasses import dataclass, field
from core.anilist import AniListClient
from core.library_parser import VIDEO_EXTENSIONS, parse_video_path
from core.organizer_ai import AnimeOrganizer

logger = logging.getLogger(__name__)

@dataclass
class ScanResult:
    catalog: list
    folders: int = 0
    files: int = 0
    videos: int = 0
    animes: int = 0
    episodes: int = 0
    errors: list[str] = field(default_factory=list)

    def message(self):
        if self.videos == 0:
            return "Nenhum vídeo encontrado nas pastas autorizadas."
        return f"Biblioteca atualizada: {self.animes} animes, {self.episodes} episódios."

class LibraryService:
    METADATA_CACHE_SECONDS = 30 * 24 * 60 * 60
    COVER_RETRY_SECONDS = 6 * 60 * 60

    def __init__(self, store): self.store=store; self.anilist=AniListClient(store.cache_dir)

    def _cached_metadata_is_current(self, cached, associated_id):
        if not cached or not cached.get("anilist_id"):
            return False
        if associated_id and cached["anilist_id"] != associated_id:
            return False
        updated_at = cached.get("metadata_updated_at")
        if not updated_at:
            return False
        age = time.time() - updated_at
        cover_cache = cached.get("cover_cache") or ""
        cover_url = cached.get("cover_url") or ""
        if cover_url and (not os.path.isfile(cover_cache) or os.path.getsize(cover_cache) <= 0):
            # A first cover download can fail while the metadata itself succeeds.
            # Retry that missing artifact after a short interval instead of
            # suppressing recovery for the full metadata TTL.
            return age < self.COVER_RETRY_SECONDS
        return age < self.METADATA_CACHE_SECONDS

    def _identify(self, lookup_title, display_title, on_status):
        """Resolve local title to cached/remote AniList metadata without guessing.

        Existing associations always win.  A stale cache is usable offline, but
        a successful later scan refreshes it by AniList ID rather than relying
        on title order again.
        """
        cached = self.store.anime_metadata(lookup_title)
        associated_id = self.store.association(lookup_title)
        if self._cached_metadata_is_current(cached, associated_id):
            return cached

        on_status(f"Identificando {display_title}…")
        if associated_id:
            media = self.anilist.by_id(associated_id)
            if media:
                return self.anilist.metadata_from_media(display_title, media)
            return cached or {"title": display_title, "genres": "[]"}

        candidates = self.anilist.search(display_title)
        selected, confident, ranked = AnimeOrganizer.choose(display_title, candidates)
        if selected and confident:
            self.store.set_association(lookup_title, selected["id"])
            return self.anilist.metadata_from_media(display_title, selected)
        if ranked:
            self.store.set_pending_match(lookup_title, display_title, ranked[:5])
        # Never persist an uncertain result as if it were a confirmed anime.
        # A previously cached record remains useful when the network is down.
        return cached or {"title": display_title, "genres": "[]"}
    def scan(self, on_status=lambda _ : None):
        run_id=self.store.begin_scan(); result=ScanResult(catalog=[]); parsed=[]
        folders=self.store.folders(); result.folders=len(folders); on_status('Verificando pastas autorizadas…')
        for folder in folders:
            reference=folder['path']
            # A content:// URI is deliberately not converted into a fake filesystem path.
            # A Flet-only APK has no ContentResolver bridge to enumerate it.
            if folder['kind'] == 'saf' or reference.startswith('content://'):
                error='A URI SAF exige a ponte Android ContentResolver; não foi tratada como caminho.'
                # Native scan results are ingested through AndroidBridge; do not revoke its persisted grant here.
                result.errors.append(f"{folder['name']}: aguardando scanner Android"); continue
            if not os.path.isdir(reference):
                error='Pasta indisponível, removida ou sem autorização para este processo.'
                self.store.update_folder_status(reference, 'revoked', error); result.errors.append(f"{folder['name']}: {error}"); continue
            self.store.update_folder_status(reference, 'granted')
            on_status(f"Encontrando vídeos em {folder['name']}…")
            try:
                seen = []
                for root, _, files in os.walk(reference):
                    for name in files:
                        result.files += 1
                        if os.path.splitext(name)[1].lower() in VIDEO_EXTENSIONS:
                            path = os.path.join(root, name)
                            try:
                                item = parse_video_path(path, reference)
                            except (OSError, ValueError, UnicodeError) as exc:
                                result.errors.append(f"{folder['name']}: não foi possível ler {name}: {exc}")
                                continue
                            seen.append(path); parsed.append((path, item, reference)); result.videos += 1
                # A successful scan may legitimately find no videos.  Limit the
                # missing update to this folder so another unavailable folder
                # cannot hide its saved episodes.
                self.store.mark_missing(reference, seen)
            except OSError as exc:
                error=f'Erro ao ler pasta: {exc}'; self.store.update_folder_status(reference, 'revoked', error); result.errors.append(f"{folder['name']}: {error}")
        metadata={}
        for path,item,source_folder in parsed:
            key=item.anime_title.casefold()
            if key not in metadata:
                try:
                    metadata[key] = self._identify(key, item.anime_title, on_status)
                except Exception as exc:
                    # Metadata must never make a locally readable file vanish.
                    metadata[key] = self.store.anime_metadata(key) or {"title": item.anime_title, "genres": "[]"}
                    result.errors.append(f"{item.anime_title}: AniList indisponível ({exc})")
                    logger.warning("Metadata lookup failed for local title %s: %s", item.anime_title, exc)
            anime_id=self.store.upsert_anime(key,metadata[key]); self.store.upsert_episode(anime_id,path,os.path.basename(path),item.season,item.episode,source_folder=source_folder)
        result.catalog=self.store.catalog(); result.animes=len(result.catalog); result.episodes=sum(len(s['episodes']) for a in result.catalog for s in a['seasons'])
        self.store.finish_scan(run_id, result.__dict__); on_status(result.message()); return result
    def ingest_documents(self, tree_uri: str, documents: list[dict], on_status=lambda _: None, *, folder_name=None, scan_errors=None, scan_stats=None):
        """Persist video document URIs enumerated by Android's ContentResolver."""
        run_id = self.store.begin_scan()
        scan_errors = list(scan_errors or [])
        scan_stats = scan_stats or {}
        self.store.add_folder(
            tree_uri,
            name=folder_name or tree_uri.rsplit("/", 1)[-1],
            kind="saf",
            authorization="granted",
            account_id=self.store.account().get("id"),
        )
        metadata = {}
        seen = []
        for document in documents:
            uri, name = document.get("uri"), document.get("name")
            relative_path = document.get("relativePath") or document.get("path") or name
            if not uri or not name: continue
            seen.append(uri)
            try:
                item = parse_video_path(relative_path, tree_uri)
            except (OSError, ValueError, UnicodeError) as exc:
                scan_errors.append(f"Não foi possível ler {name}: {exc}")
                continue
            key = item.anime_title.casefold()
            if key not in metadata:
                try:
                    metadata[key] = self._identify(key, item.anime_title, on_status)
                except Exception as exc:
                    metadata[key] = self.store.anime_metadata(key) or {"title": item.anime_title, "genres": "[]"}
                    logger.warning("Metadata lookup failed for SAF title %s: %s", item.anime_title, exc)
            anime_id = self.store.upsert_anime(key, metadata[key])
            self.store.upsert_episode(anime_id, uri, name, item.season, item.episode, document.get("mimeType"), document.get("size"), document.get("modifiedAt"), tree_uri)
        # Do not infer removals from a partial SAF scan: a SecurityException in
        # one subdirectory means its previous documents may simply be unreadable.
        # On a complete scan, absent documents become missing while keeping their
        # SQLite progress so they can be restored later.
        if scan_errors:
            self.store.update_folder_status(tree_uri, "granted", "; ".join(map(str, scan_errors)))
        else:
            self.store.mark_missing(tree_uri, seen)
            self.store.update_folder_status(tree_uri, "granted")
        catalog = self.store.catalog()
        result = ScanResult(
            catalog=catalog,
            folders=1,
            files=int(scan_stats.get("files") or len(documents)),
            videos=int(scan_stats.get("videos") or len(documents)),
            animes=len(catalog),
            episodes=sum(len(season["episodes"]) for anime in catalog for season in anime["seasons"]),
            errors=scan_errors,
        )
        self.store.finish_scan(run_id, result.__dict__)
        return catalog

    def resolve_match(self, lookup_title, anilist_id): self.store.resolve_match(lookup_title, anilist_id)
    def catalog(self, favorites_only=False): return self.store.catalog(favorites_only)
    def continue_watching(self, limit=12): return self.store.continue_watching(limit)
    def playback_history(self, limit=50): return self.store.playback_history(limit)
    def playback_target(self, anime_id): return self.store.playback_target(anime_id)
    def next_episode(self, path): return self.store.next_episode(path)
    def previous_episode(self, path): return self.store.previous_episode(path)

    def clear_anilist_cache(self):
        """Clear only refreshable AniList artifacts, never local library state.

        Confirmed ``associations`` are intentionally retained so a later scan
        refreshes the same manually chosen AniList record.  Metadata rows stay
        attached to their local anime and are merely marked stale.
        """
        removed = 0
        try:
            for entry in os.scandir(self.store.cache_dir):
                if entry.is_file():
                    os.unlink(entry.path)
                    removed += 1
        except OSError as exc:
            raise RuntimeError("Não foi possível limpar o cache de capas.") from exc
        self.store.clear_anilist_metadata_cache()
        return removed

    @staticmethod
    def organize_summary(catalog):
        """Summarize one loaded local catalog for the Organizar landing page.

        This is deliberately an in-memory projection: it makes no database or
        network requests, and all state counts reuse ``browse_catalog`` so Home
        and Organizar cannot disagree about favorite/progress semantics.
        """
        genres = {}
        for anime in catalog:
            cover = (anime.get("meta") or {}).get("cover_cache") or (anime.get("meta") or {}).get("cover_url")
            for genre in anime.get("genres") or []:
                if not genre:
                    continue
                entry = genres.setdefault(genre, {"name": genre, "count": 0, "cover": cover or ""})
                entry["count"] += 1
                if not entry["cover"] and cover:
                    entry["cover"] = cover
        states = [
            {"name": state, "count": len(LibraryService.browse_catalog(catalog, state=state))}
            for state in ("Todos", "Favoritos", "Em andamento", "Concluídos")
        ]
        return {"genres": sorted(genres.values(), key=lambda item: item["name"].casefold()), "states": states}

    @staticmethod
    def browse_catalog(catalog, query="", state="Todos", genre="Todos", sort="Mais recentes"):
        """Filter an already loaded local catalog; never queries AniList or SQLite."""
        query = query.casefold().strip()

        def episodes(anime):
            return [episode for season in anime.get("seasons", []) for episode in season.get("episodes", [])]

        def matches(anime):
            items = episodes(anime)
            available = [item for item in items if not item.get("missing")]
            in_progress = any(item.get("progress", 0) > 0 and not item.get("watched") for item in available)
            completed = bool(available) and all(item.get("watched") for item in available)
            metadata = anime.get("meta", {})
            aliases = metadata.get("aliases") or "[]"
            try:
                aliases = json.loads(aliases) if isinstance(aliases, str) else aliases
            except json.JSONDecodeError:
                aliases = []
            searchable = [anime.get("main_title", ""), metadata.get("romaji", ""), metadata.get("english", ""), metadata.get("native", ""), *aliases]
            if query and not any(query in str(value).casefold() for value in searchable if value):
                return False
            if genre != "Todos" and genre not in anime.get("genres", []):
                return False
            return {"Todos": True, "Favoritos": bool(anime.get("favorite")), "Em andamento": in_progress, "Concluídos": completed}.get(state, True)

        result = [anime for anime in catalog if matches(anime)]
        if sort == "Nome A-Z":
            return sorted(result, key=lambda anime: anime.get("main_title", "").casefold())
        if sort == "Nome Z-A":
            return sorted(result, key=lambda anime: anime.get("main_title", "").casefold(), reverse=True)
        if sort == "Assistidos recentemente":
            return sorted(
                result,
                key=lambda anime: max(
                    (episode.get("last_played_at") or 0
                     for episode in episodes(anime)
                     if not episode.get("missing")),
                    default=0,
                ),
                reverse=True,
            )
        return sorted(result, key=lambda anime: anime.get("meta", {}).get("added_at") or 0, reverse=True)
