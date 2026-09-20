"""Real recursive scanner for references that the Python process can read."""
from __future__ import annotations
import os
import time
import json
import logging
import threading
import uuid
from urllib.parse import unquote, urlparse
from pathlib import Path
from dataclasses import dataclass, field
from core.anilist import AniListClient
from core.library_parser import VIDEO_EXTENSIONS, parse_video_path
from core.media_identity import local_media_identity
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
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    ignored: int = 0
    duplicates: int = 0
    unknown: int = 0
    reconciled: int = 0
    scan_id: str | None = None

    def message(self):
        if self.videos == 0:
            return "Nenhum vídeo encontrado nas fontes autorizadas."
        return (f"Biblioteca atualizada: {self.episodes} mídias — "
                f"{self.new} novas, {self.updated} atualizadas, {self.unchanged} inalteradas.")

class LibraryService:
    METADATA_CACHE_SECONDS = 30 * 24 * 60 * 60
    COVER_RETRY_SECONDS = 6 * 60 * 60

    def __init__(self, store):
        self.store=store; self.anilist=AniListClient(store.cache_dir); self._scan_lock=threading.Lock()

    def _cached_metadata_is_current(self, cached, associated_id):
        if not cached:
            return False
        if cached.get("anilist_id") != associated_id:
            return False

        updated_at = cached.get("metadata_updated_at")
        if not updated_at:
            return False
        try:
            age = time.time() - float(updated_at)
        except (TypeError, ValueError):
            return False

        # A previously expected cover has its own short retry window.
        # This check must happen before the long metadata TTL: metadata can
        # still be fresh while a missing cover is already due for retry.
        cover_cache = (cached.get("cover_cache") or "").strip()
        if cover_cache and not Path(cover_cache).is_file():
            return age < self.COVER_RETRY_SECONDS

        # An empty/missing cover cache is valid metadata state. In that case,
        # only the normal metadata TTL controls freshness.
        return age < self.METADATA_CACHE_SECONDS

    def _identify(self, lookup_title, display_title, on_status):
        """Resolve local title to cached/remote AniList metadata without guessing.

        Existing associations always win.  A stale cache is usable offline, but
        a successful later scan refreshes it by AniList ID rather than relying
        on title order again.
        """
        cached = self.store.anime_metadata(lookup_title)
        associated_id = self.store.association(lookup_title)
        cached_id = cached.get("anilist_id") if cached else None
        refresh_id = associated_id or cached_id
        if self._cached_metadata_is_current(cached, refresh_id):
            return cached

        on_status(f"Identificando {display_title}…")
        if refresh_id:
            media = self.anilist.by_id(refresh_id)
            if media:
                refreshed = self.anilist.metadata_from_media(display_title, media)
                refreshed["anilist_id"] = refresh_id
                if cached:
                    refreshed["cover_cache"] = cached.get("cover_cache") or refreshed.get("cover_cache") or ""
                try:
                    self.store.upsert_anime(lookup_title, refreshed)
                except Exception:
                    logger.exception("Falha ao persistir metadados AniList para %s", display_title)
                return refreshed
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
    @staticmethod
    def _document_relative_path(document, name, uri):
        relative_path = document.get("relativePath") or document.get("path") or name
        if uri.startswith("file://") and not document.get("relativePath") and not document.get("path"):
            relative_path = unquote(urlparse(uri).path)
        return str(relative_path).replace(chr(92), "/").strip("/")

    @staticmethod
    def _physical_unchanged(existing, *, source_folder, file_size, modified_at, relative_path, volume_id):
        if not existing or existing.get("missing"):
            return False
        return (
            existing.get("source_folder") == source_folder
            and existing.get("file_size") == file_size
            and existing.get("modified_at") == modified_at
            and (existing.get("relative_path") or "") == (relative_path or "")
            and (existing.get("volume_id") or "") == (volume_id or "")
        )

    def _record_document(self, *, document, source_folder, source_kind, metadata, result):
        uri = document.get("uri")
        name = document.get("name")
        if not isinstance(uri, str) or not uri or not isinstance(name, str) or not name.strip():
            result.ignored += 1
            result.errors.append("Documento local incompleto recebido da ponte Android.")
            return None

        relative_path = self._document_relative_path(document, name, uri)
        if not (uri.startswith("content://") or uri.startswith("file://")):
            result.ignored += 1
            result.errors.append(f"Referência local inválida para {name}.")
            return None

        file_size = document.get("size")
        modified_at = document.get("modifiedAt")
        volume_id = document.get("volumeId")
        volume_uuid = document.get("volumeUuid")
        existing = self.store.physical_row(uri)
        if self._physical_unchanged(
            existing, source_folder=source_folder, file_size=file_size,
            modified_at=modified_at, relative_path=relative_path, volume_id=volume_id,
        ):
            result.unchanged += 1
            return uri

        try:
            item = parse_video_path(relative_path, source_folder)
        except (OSError, ValueError, UnicodeError) as exc:
            result.ignored += 1
            result.errors.append(f"Não foi possível identificar {name}: {exc}")
            return None

        key = item.anime_title.casefold()
        if item.episode_type == "unknown" or not item.anime_title or item.anime_title == "Arquivo não identificado":
            result.unknown += 1

        if key not in metadata:
            try:
                metadata[key] = self._identify(key, item.anime_title, lambda message: None)
            except Exception as exc:
                metadata[key] = self.store.anime_metadata(key) or {"title": item.anime_title, "genres": "[]"}
                result.errors.append(f"{item.anime_title}: metadata indisponível ({exc})")
            metadata[key] = dict(metadata[key] or {})
            if item.episode_type == "movie":
                metadata[key]["media_kind"] = "movie"
            elif item.episode_type == "unknown":
                metadata[key]["media_kind"] = "unknown"
            else:
                metadata[key]["media_kind"] = metadata[key].get("media_kind") or "series"

        identity_volume = volume_id
        if source_kind == "filesystem":
            identity_volume = source_folder
        identity = local_media_identity(
            uri=uri, source_kind=("broad_storage" if source_kind == "filesystem" else source_kind), relative_path=relative_path,
            size=file_size, modified_at=modified_at, volume_id=identity_volume,
        )
        anime_id = self.store.upsert_anime(key, metadata[key])
        row_id = self.store.upsert_episode(
            anime_id, uri, name, item.season, item.episode,
            document.get("mimeType"), file_size, modified_at, source_folder,
            identity, item.absolute_number, relative_path, volume_id, volume_uuid,
            episode_type=item.episode_type, episode_title=item.display_title,
            identification_source=item.identification_source,
            identification_confidence=item.confidence,
        )
        if existing:
            result.updated += 1
        elif row_id is not None:
            result.new += 1
        return uri

    def scan(self, on_status=lambda _ : None):
        with self._scan_lock:
            scan_id = str(uuid.uuid4())
            run_id = self.store.begin_scan(scan_id=scan_id, source_kind="filesystem", scope_kind="global", scope_ref=None)
            result = ScanResult(catalog=[], scan_id=scan_id)
            try
                parsed = []
                folders = self.store.folders()
                result.folders = len(folders)
                on_status("Verificando pastas autorizadas…")
                for folder in folders:
                    reference = folder["path"]
                    if folder["kind"] == "saf" or reference.startswith("content://"):
                        result.errors.append(f"{folder['name']}: aguardando scanner Android")
                        continue
                    if not os.path.isdir(reference):
                        error = "Pasta indisponível, removida ou sem autorização para este processo."
                        self.store.update_folder_status(reference, "revoked", error)
                        result.errors.append(f"{folder['name']}: {error}")
                        continue
                    self.store.update_folder_status(reference, "granted")
                    on_status(f"Encontrando vídeos em {folder['name']}…")
                    try:
                        seen = []
                        walk_errors = []
                        def _on_walk_error(error):
                            walk_errors.append(error)
                            result.errors.append(f"{folder['name']}: diretório não pôde ser lido: {getattr(error, 'filename', error)}")
                        for root, _, files in os.walk(reference, onerror=_on_walk_error):
                            for name in files:
                                result.files += 1
                                if os.path.splitext(name)[1].lower() not in VIDEO_EXTENSIONS:
                                    result.ignored += 1
                                    continue
                                path = os.path.join(root, name)
                                try:
                                    stat = os.stat(path)
                                except OSError as exc:
                                    result.errors.append(f"{folder['name']}: não foi possível acessar {name}: {exc}")
                                    result.ignored += 1
                                    continue
                                seen.append(path)
                                parsed.append(({
                                    "uri": path,
                                    "name": name,
                                    "relativePath": os.path.relpath(path, reference).replace(os.sep, "/"),
                                    "mimeType": None,
                                    "size": stat.st_size,
                                    "modifiedAt": stat.st_mtime_ns // 1_000_000,
                                }, reference, "filesystem"))
                                result.videos += 1
                        if not walk_errors:
                            self.store.reconcile_missing(reference, seen, scope_kind="source")
                        else:
                            self.store.update_folder_status(reference, "granted", "Scan parcial; reconciliação de ausência não aplicada.")
                    except OSError as exc:
                        result.errors.append(f"{folder['name']}: erro ao ler pasta: {exc}")
                metadata = {}
                for document, source_folder, source_kind in parsed:
                    self._record_document(document=document, source_folder=source_folder, source_kind=source_kind, metadata=metadata, result=result)
                result.catalog = self.store.catalog()
                result.animes = len(result.catalog)
                result.episodes = sum(len(s["episodes"]) for a in result.catalog for s in a["seasons"]) + sum(len(a.get("media_files", [])) for a in result.catalog)
                self.store.finish_scan(run_id, result.__dict__)
                return result
            except Exception as exc:
                result.errors.append(f"Falha geral no scan: {exc}")
                self.store.finish_scan(run_id, result.__dict__)
                raise

    def ingest_documents(self, tree_uri: str, documents: list[dict], on_status=lambda _: None, *,
                         folder_name=None, scan_errors=None, scan_stats=None, source_kind="saf",
                         scan_id=None, scope_kind="global", scope_ref=None):
        """Index one native source without destructive reconciliation on partial scans."""
        with self._scan_lock:
            scan_id = scan_id or str(uuid.uuid4())
            run_id = self.store.begin_scan(scan_id=scan_id, source_kind=source_kind, scope_kind=scope_kind, scope_ref=scope_ref or tree_uri)
            result = ScanResult(catalog=[], scan_id=scan_id)
            scan_errors = list(scan_errors or [])
            scan_stats = scan_stats or {}
            try:
                self.store.add_folder(
                    tree_uri,
                    name=folder_name or tree_uri.rsplit("/", 1)[-1],
                    kind=source_kind,
                    authorization="granted",
                    account_id=self.store.account().get("id"),
                )
                metadata = {}
                seen = set()
                for document in documents or []:
                    uri = document.get("uri") if isinstance(document, dict) else None
                    if uri in seen:
                        result.duplicates += 1
                        continue
                    if isinstance(uri, str) and uri:
                        seen.add(uri)
                    result.files += 1
                    accepted = self._record_document(
                        document=document if isinstance(document, dict) else {},
                        source_folder=tree_uri,
                        source_kind=source_kind,
                        metadata=metadata,
                        result=result,
                    )
                    if accepted:
                        result.videos += 1

                result.errors.extend(str(error) for error in scan_errors)
                if not scan_errors:
                    self.store.reconcile_missing(tree_uri, list(seen), scope_kind=scope_kind, scope_ref=scope_ref)
                    result.reconciled = 1
                    self.store.update_folder_status(tree_uri, "granted")
                else:
                    self.store.update_folder_status(tree_uri, "granted", "; ".join(map(str, scan_errors)))
                catalog = self.store.catalog()
                result.catalog = catalog
                result.folders = 1
                result.videos = int(scan_stats.get("videos") or result.videos)
                result.animes = len(catalog)
                result.episodes = sum(len(season["episodes"]) for anime in catalog for season in anime["seasons"]) + sum(len(anime.get("media_files", [])) for anime in catalog)
                self.store.finish_scan(run_id, result.__dict__)
                return catalog
            except Exception as exc:
                result.errors.append(f"Falha ao indexar a fonte: {exc}")
                self.store.finish_scan(run_id, result.__dict__)
                raise

    def resolve_match(self, lookup_title, anilist_id):
        """Persist an explicit AniList choice and refresh its metadata immediately."""
        try:
            anilist_id = int(anilist_id)
        except (TypeError, ValueError):
            raise ValueError("ID AniList inválido.")
        pending = next(
            (item for item in self.store.pending_matches() if item["lookup_title"] == lookup_title),
            None,
        )
        if not pending:
            raise ValueError("Este candidato não está mais pendente.")
        media = self.anilist.by_id(anilist_id)
        if not media or media.get("id") != anilist_id:
            raise ValueError("O anime escolhido não está disponível no AniList.")
        metadata = self.anilist.metadata_from_media(pending["display_title"], media)
        metadata["anilist_id"] = anilist_id
        self.store.set_association(lookup_title, anilist_id)
        self.store.upsert_anime(lookup_title, metadata)
        self.store.resolve_match(lookup_title, anilist_id)
        return metadata
    def catalog(self, favorites_only=False): return self.store.catalog(favorites_only)
    def continue_watching(self, limit=12): return self.store.continue_watching(limit)
    def playback_history(self, limit=50): return self.store.playback_history(limit)
    def playback_target(self, anime_id): return self.store.playback_target(anime_id)
    def next_episode(self, path): return self.store.next_episode(path)
    def previous_episode(self, path): return self.store.previous_episode(path)
    def set_user_tags(self, anime_id, tags): return self.store.set_user_tags(anime_id, tags)
    def toggle_pinned(self, anime_id): return self.store.toggle_pinned(anime_id)
    def set_personal_note(self, anime_id, note): return self.store.set_personal_note(anime_id, note)
    def library_statistics(self): return self.store.library_statistics()
    def last_scan(self): return self.store.last_scan()

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
    def browse_catalog(catalog, query="", state="Todos", genre="Todos", sort="Mais recentes", tag="Todos"):
        """Filter an already loaded local catalog; never queries AniList or SQLite."""
        query = query.casefold().strip()

        def episodes(anime):
            return [episode for season in anime.get("seasons", []) for episode in season.get("episodes", [])]

        def matches(anime):
            items = episodes(anime)
            available = [item for item in items if not item.get("missing")]
            in_progress = any(item.get("progress", 0) > 0 and not item.get("watched") for item in available)
            completed = bool(available) and all(item.get("watched") for item in available)
            not_started = bool(available) and not any(item.get("progress", 0) > 0 or item.get("watched") for item in available)
            metadata = anime.get("meta", {})
            aliases = metadata.get("aliases") or "[]"
            try:
                aliases = json.loads(aliases) if isinstance(aliases, str) else aliases
            except json.JSONDecodeError:
                aliases = []
            searchable = [anime.get("main_title", ""), metadata.get("romaji", ""), metadata.get("english", ""), metadata.get("native", ""), *aliases, *(anime.get("user_tags") or [])]
            if query and not any(query in str(value).casefold() for value in searchable if value):
                return False
            if genre != "Todos" and genre not in anime.get("genres", []):
                return False
            tags = anime.get("user_tags") or []
            if tag == "Sem etiqueta" and tags:
                return False
            if tag not in ("Todos", "Sem etiqueta") and tag not in tags:
                return False
            return {"Todos": True, "Favoritos": bool(anime.get("favorite")), "Fixados": bool(anime.get("is_pinned")),
                    "Em andamento": in_progress, "Concluídos": completed, "Não iniciados": not_started,
                    "Com nota": bool((anime.get("personal_note") or "").strip()), "Sem nota": not bool((anime.get("personal_note") or "").strip()),
                    "Sem metadata": not bool(metadata.get("anilist_id")),
                    "Sem capa": not bool(metadata.get("cover_cache") or metadata.get("cover_url"))}.get(state, True)

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
        if sort == "Fixados primeiro":
            return sorted(result, key=lambda anime: (not anime.get("is_pinned", False), anime.get("main_title", "").casefold()))
        if sort == "Favoritos primeiro":
            return sorted(result, key=lambda anime: (not anime.get("favorite", False), anime.get("main_title", "").casefold()))
        if sort == "Progresso":
            def progress_value(anime):
                values = [min(float(item.get("progress") or 0) / float(item.get("duration") or 1), 1) for item in episodes(anime) if not item.get("missing") and item.get("duration")]
                return sum(values) / len(values) if values else -1
            return sorted(result, key=lambda anime: (-progress_value(anime), anime.get("main_title", "").casefold()))
        return sorted(result, key=lambda anime: anime.get("meta", {}).get("added_at") or 0, reverse=True)
