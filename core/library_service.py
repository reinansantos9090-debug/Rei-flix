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
from core.consumption import consumption_state
from core.artwork import ArtworkEngine
from core.library_parser import VIDEO_EXTENSIONS, parse_video_path
from core.media_identity import identity_from_document
from core.organizer_ai import AnimeOrganizer
from core.search_engine import LibrarySearchEngine

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
    status: str = "completed"
    nomedia_directories: int = 0
    nomedia_files: int = 0

    def message(self):
        if self.videos == 0:
            return "Nenhum vídeo encontrado nas fontes autorizadas."
        return (f"Biblioteca atualizada: {self.episodes} mídias — "
                f"{self.new} novas, {self.updated} atualizadas, {self.unchanged} inalteradas.")

class LibraryService:
    METADATA_CACHE_SECONDS = 30 * 24 * 60 * 60
    COVER_RETRY_SECONDS = 6 * 60 * 60
    REQUEST_DEDUPE_SECONDS = 5

    def __init__(self, store):
        self.store=store; self.anilist=AniListClient(store.cache_dir); self.artwork=ArtworkEngine(store); self._scan_lock=threading.Lock(); self._metadata_lock=threading.RLock()

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

    def _identify(self, lookup_title, display_title, on_status=lambda _ : None, *, allow_network=True):
        """Return local/cached metadata without making the library depend on network."""
        cached = self.store.anime_metadata(lookup_title)
        associated_id = self.store.association(lookup_title)
        if cached:
            if associated_id and cached.get("anilist_id") != associated_id:
                # Keep the durable association authoritative, but do not fetch during scan.
                if allow_network:
                    return self.refresh_metadata(lookup_title, display_title, force=True)
            if self._cached_metadata_is_current(cached, associated_id or cached.get("anilist_id")):
                return cached
            if not allow_network:
                return cached
        if not allow_network:
            return cached or {
                "title": display_title,
                "genres": "[]",
                "metadata_source": "local",
                "metadata_status": "unresolved",
                "metadata_confidence": "low",
            }
        return self.refresh_metadata(lookup_title, display_title, force=False)

    def metadata_state(self, metadata):
        """Expose a stable UI state without changing persisted library data."""
        if not metadata:
            return "unresolved"
        status = str(metadata.get("metadata_status") or "unresolved").casefold()
        if status == "manual":
            return "manual"
        if status in {"ambiguous", "unresolved", "error"}:
            return status
        updated = metadata.get("metadata_updated_at")
        try:
            stale = not updated or (time.time() - float(updated)) >= self.METADATA_CACHE_SECONDS
        except (TypeError, ValueError):
            stale = True
        return "stale" if stale else "available"

    def refresh_metadata(self, lookup_title, display_title, *, force=False, bypass_request_dedupe=False):
        """Resolve AniList metadata explicitly, conservatively and offline-safe."""
        with self._metadata_lock:
            cached = self.store.anime_metadata(lookup_title)
            associated_id = self.store.association(lookup_title)
            cached_id = cached.get("anilist_id") if cached else None
            refresh_id = associated_id or cached_id
            if cached and cached.get("metadata_fetched_at") and not bypass_request_dedupe:
                try:
                    if time.time() - float(cached["metadata_fetched_at"]) < self.REQUEST_DEDUPE_SECONDS:
                        return cached
                except (TypeError, ValueError):
                    pass
            if not force and self._cached_metadata_is_current(cached, refresh_id):
                return cached
            self.store.set_metadata_status(lookup_title, "refreshing") if cached else None
            try:
                if refresh_id:
                    media = self.anilist.by_id(refresh_id)
                    if media:
                        refreshed = self.anilist.metadata_from_media(display_title, media)
                        refreshed["anilist_id"] = refresh_id
                        self.store.upsert_anime(lookup_title, refreshed, source="anilist", confidence="high", status="available", fetched_at=time.time())
                        row = self.store.anime_metadata(lookup_title)
                        if row:
                            self.artwork.sync_anime_metadata(row["id"], row)
                        return self.store.anime_metadata(lookup_title) or refreshed
                    if cached:
                        self.store.set_metadata_status(lookup_title, "stale", confidence=cached.get("metadata_confidence") or "high")
                        return self.store.anime_metadata(lookup_title) or cached
                    return {"title": display_title, "genres": "[]", "metadata_source": "local", "metadata_status": "unresolved", "metadata_confidence": "low"}

                candidates = self.anilist.search(display_title)
                selected, confident, ranked = AnimeOrganizer.choose(display_title, candidates)
                if selected and confident:
                    self.store.set_association(lookup_title, selected["id"])
                    refreshed = self.anilist.metadata_from_media(display_title, selected)
                    refreshed["anilist_id"] = selected["id"]
                    score = float(selected.get("match_score") or 0.0)
                    confidence = "high" if score >= 0.9 else "medium"
                    self.store.upsert_anime(lookup_title, refreshed, source="anilist", confidence=confidence, status="available", fetched_at=time.time())
                    row = self.store.anime_metadata(lookup_title)
                    if row:
                        self.artwork.sync_anime_metadata(row["id"], row)
                    return self.store.anime_metadata(lookup_title) or refreshed
                if ranked:
                    self.store.set_pending_match(lookup_title, display_title, ranked[:5])
                    if cached:
                        self.store.set_metadata_status(lookup_title, "ambiguous", confidence="medium")
                        return cached
                    local = {"title": display_title, "genres": "[]", "metadata_source": "local", "metadata_status": "ambiguous", "metadata_confidence": "low"}
                    self.store.upsert_anime(lookup_title, local, source="local", confidence="low", status="ambiguous")
                    row = self.store.anime_metadata(lookup_title)
                    if row:
                        self.artwork.sync_anime_metadata(row["id"], row)
                    return local
                if cached:
                    self.store.set_metadata_status(lookup_title, "unresolved", confidence="low")
                    return cached
                local = {"title": display_title, "genres": "[]", "metadata_source": "local", "metadata_status": "unresolved", "metadata_confidence": "low"}
                self.store.upsert_anime(lookup_title, local, source="local", confidence="low", status="unresolved")
                row = self.store.anime_metadata(lookup_title)
                if row:
                    self.artwork.sync_anime_metadata(row["id"], row)
                return self.store.anime_metadata(lookup_title) or local
            except Exception as exc:
                logger.warning("Metadata AniList indisponível para %s: %s", display_title, exc)
                if cached:
                    self.store.set_metadata_status(lookup_title, "stale", confidence=cached.get("metadata_confidence") or "low")
                    return cached
                local = {"title": display_title, "genres": "[]", "metadata_source": "local", "metadata_status": "unresolved", "metadata_confidence": "low"}
                self.store.upsert_anime(lookup_title, local, source="local", confidence="low", status="unresolved")
                row = self.store.anime_metadata(lookup_title)
                if row:
                    self.artwork.sync_anime_metadata(row["id"], row)
                return local

    def hydrate_catalog_metadata(self, catalog):
        """Hydrate local items that still need AniList metadata or poster artwork.

        The queue is intentionally sequential and reuses the existing AniListClient,
        ArtworkEngine and SQLite catalog. It never creates a second cache or catalog.
        """
        hydrated = []
        pending_cache = None
        for item in list(catalog or []):
            metadata = dict(item.get('meta') or {})
            lookup_title = str(metadata.get('lookup_title') or item.get('main_title') or '').strip()
            display_title = str(item.get('main_title') or metadata.get('title') or lookup_title).strip()
            if not lookup_title or not display_title: continue

            cached = self.store.anime_metadata(lookup_title) or metadata
            status = str(cached.get('metadata_status') or 'unresolved').casefold()
            anilist_id = self.store.association(lookup_title) or cached.get('anilist_id')
            if status == 'manual' and not anilist_id:
                continue
            cover_cache = str(cached.get('cover_cache') or '').strip()
            cover_valid = bool(cover_cache and os.path.isfile(cover_cache) and os.path.getsize(cover_cache) > 0)
            needs_metadata = not anilist_id or status in {'unresolved', 'error', 'stale'}
            if status == 'ambiguous' and not anilist_id:
                if pending_cache is None: pending_cache = self.store.pending_matches()
                needs_metadata = not any(p.get('lookup_title') == lookup_title for p in pending_cache)
            needs_cover = bool(anilist_id and str(cached.get('cover_url') or '').strip() and not cover_valid)
            if not needs_metadata and not needs_cover: continue
            try:
                metadata_refreshed = False
                cover_attempt_failed = False
                if needs_metadata:
                    cached = self.refresh_metadata(lookup_title, display_title, force=True, bypass_request_dedupe=True)
                    cached = self.store.anime_metadata(lookup_title) or cached or {}
                    status = str(cached.get('metadata_status') or status).casefold()
                    anilist_id = self.store.association(lookup_title) or cached.get('anilist_id')
                    metadata_refreshed = True
                cover_cache = str(cached.get('cover_cache') or '').strip()
                cover_valid = bool(cover_cache and os.path.isfile(cover_cache) and os.path.getsize(cover_cache) > 0)
                cover_url = str(cached.get('cover_url') or '').strip()
                if anilist_id and cover_url and not cover_valid:
                    entity_type = 'movie' if str(cached.get('media_kind') or item.get('media_kind') or 'series').casefold() == 'movie' else 'anime'
                    blocked = False
                    if cached.get('id'):
                        for row in self.artwork.list_for(entity_type, cached['id'], 'poster'):
                            if row.get('source_ref') == cover_url and row.get('status') == 'failed':
                                blocked = time.time() - float(row.get('last_attempt_at') or 0) < self.COVER_RETRY_SECONDS
                                break
                    if not blocked:
                        if metadata_refreshed:
                            # refresh_metadata() already attempted this exact cover URL
                            # through AniListClient.metadata_from_media(). Do not issue
                            # a duplicate HTTP request in the same hydration cycle; record
                            # the failed attempt so the existing ArtworkEngine backoff
                            # governs the next cycle.
                            if cached.get('id') and not cover_valid:
                                cover_attempt_failed = True
                        else:
                            downloaded = self.anilist.cache_cover(cover_url)
                            if downloaded and os.path.isfile(downloaded) and os.path.getsize(downloaded) > 0:
                                self.store.upsert_anime(lookup_title, {'anilist_id': anilist_id, 'cover_url': cover_url, 'cover_cache': downloaded},
                                                        source='anilist', confidence=cached.get('metadata_confidence') or 'medium',
                                                        status=cached.get('metadata_status') or 'available', fetched_at=cached.get('metadata_fetched_at'))
                                cached = self.store.anime_metadata(lookup_title) or cached
                            elif cached.get('id'):
                                cover_attempt_failed = True
                if cached.get('id'):
                    self.artwork.sync_anime_metadata(cached['id'], cached)
                    if cover_attempt_failed:
                        self.artwork.mark_download_failure(entity_type, cached['id'], 'poster', cover_url)
                hydrated.append({'lookup_title': lookup_title, 'id': cached.get('id'), 'metadata': cached})
            except Exception:
                logger.exception('Local metadata/artwork hydration failed', extra={'screen':'home','lookup_title':lookup_title,'library_items':len(catalog)})
        return hydrated
    def set_manual_metadata(self, lookup_title, values):
        return self.store.set_manual_metadata(lookup_title, values)

    def register_generated_thumbnail(self, media_uri, thumbnail_path, *, size=0, modified_at=0):
        return self.artwork.register_generated_thumbnail(media_uri, thumbnail_path, size=size, modified_at=modified_at)

    def resolve_artwork(self, entity_type, entity_id, artwork_type, *, allow_network=True):
        return self.artwork.resolve(entity_type, entity_id, artwork_type, allow_network=allow_network)

    def set_manual_artwork(self, entity_type, entity_id, artwork_type, *, path=None, external_url=None):
        return self.artwork.set_manual(entity_type, entity_id, artwork_type, path=path, external_url=external_url)

    def clear_manual_artwork(self, entity_type, entity_id, artwork_type):
        return self.artwork.clear_manual(entity_type, entity_id, artwork_type)

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

    def _record_document(self, *, document, source_folder, source_kind, metadata, result, affected_anime_ids=None, known_paths=None, scope_kind="source", scope_ref=None, native_generation=None):
        uri = document.get("uri")
        name = document.get("name")
        if not isinstance(uri, str) or not uri or not isinstance(name, str) or not name.strip():
            result.ignored += 1
            result.errors.append("Documento local incompleto recebido da ponte Android.")
            return None

        relative_path = self._document_relative_path(document, name, uri)
        is_local_reference = (
            uri.startswith("content://")
            or uri.startswith("file://")
            or (source_kind == "filesystem" and os.path.isabs(uri))
        )
        if not is_local_reference:
            result.ignored += 1
            result.errors.append(f"Referência local inválida para {name}.")
            return None

        file_size = document.get("size")
        modified_at = document.get("modifiedAt")
        volume_id = document.get("volumeId")
        volume_uuid = document.get("volumeUuid")
        existing = self.store.physical_row(uri)
        observation_scope_ref = scope_ref if scope_ref is not None else (source_folder if scope_kind == "source" else None)
        if self._physical_unchanged(
            existing, source_folder=source_folder, file_size=file_size,
            modified_at=modified_at, relative_path=relative_path, volume_id=volume_id,
        ):
            self.store.record_observation(
                existing["id"],
                source_kind=source_kind,
                scope_kind=scope_kind,
                scope_ref=observation_scope_ref,
                uri=uri,
                volume_id=volume_id,
                native_generation=native_generation or document.get("scanGeneration"),
                fingerprint=document.get("nativeFingerprint"),
            )
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
                metadata[key] = self._identify(key, item.anime_title, lambda message: None, allow_network=False)
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

        identity_uri = uri if uri.startswith(("file://", "content://")) else Path(uri).as_uri()
        native_identity = document.get("stableId")
        identity = native_identity.strip() if isinstance(native_identity, str) and native_identity.strip() else identity_from_document(identity_uri, relative_path, volume_id, source_folder if source_kind == "saf" else None)
        anime_id = self.store.upsert_anime(key, metadata[key], source=metadata[key].get("metadata_source") or "local", confidence=metadata[key].get("metadata_confidence"), status=metadata[key].get("metadata_status"))

        # A move/rename changes the path-derived identity. When Android/storage
        # metadata proves that exactly one missing row for the same title/source/
        # volume has the same size+mtime, carry forward its durable identity.
        if existing is None:
            candidate = self.store.missing_candidate(
                anime_id, source_folder, file_size, modified_at, volume_id,
                excluded_paths=known_paths,
            )
            if candidate and candidate.get("media_identity"):
                identity = candidate["media_identity"]

        row_id = self.store.upsert_episode(
            anime_id, uri, name, item.season, item.episode,
            document.get("mimeType"), file_size, modified_at, source_folder,
            media_identity=identity,
        )
        self.store.apply_episode_identification(
            uri, absolute_number=item.absolute_number, relative_path=relative_path,
            volume_id=volume_id, volume_uuid=volume_uuid,
            episode_type=item.episode_type, episode_title=item.display_title,
            identification_source=item.identification_source,
            identification_confidence=item.confidence,
        )
        self.store.record_observation(
            row_id,
            source_kind=source_kind,
            scope_kind=scope_kind,
            scope_ref=observation_scope_ref,
            uri=uri,
            volume_id=volume_id,
            native_generation=native_generation or document.get("scanGeneration"),
            fingerprint=document.get("nativeFingerprint"),
        )
        # Per-episode thumbnails are discovered immediately. Poster/season
        # discovery is deferred to one pass per affected entity.
        self.artwork.discover_episode(row_id)
        if affected_anime_ids is not None:
            affected_anime_ids.add(anime_id)

        if existing:
            result.updated += 1
        elif row_id is not None:
            result.new += 1
        return uri

    def ingest_documents_batch(self, tree_uri: str, documents: list[dict], *,
                               source_kind="saf", scan_id=None, scope_kind="global", scope_ref=None,
                               scan_generation=None, generation_id=None, request_id=None,
                               batch_id=None, batch_number=0, batch_size=None, folder_name=None, scan_errors=None):
        """Ingest one bounded native batch without destructive reconciliation."""
        with self._scan_lock:
            scan_id = scan_id or str(uuid.uuid4())
            scope_ref = scope_ref or tree_uri
            existing = self.store.scan_by_id(scan_id)
            if existing and str(existing.get("status") or "").casefold() in {"completed","partial","cancelled","error","failed"}:
                return {"scan_id": scan_id, "ignored": True, "reason": "scan_already_finalized"}
            try:
                generation = int(scan_generation) if scan_generation is not None else None
            except (TypeError, ValueError):
                generation = None
            run_id = int(existing["id"]) if existing else self.store.begin_scan(scan_id=scan_id, source_kind=source_kind, scope_kind=scope_kind, scope_ref=scope_ref, native_generation=generation, generation_id=str(generation_id or scan_id))
            if generation is not None:
                latest = self.store.latest_completed_native_generation(source_kind, scope_kind, scope_ref)
                if latest is not None and generation < latest:
                    return {"scan_id": scan_id, "ignored": True, "reason": "stale_generation"}
            self.store.add_folder(tree_uri, name=folder_name or tree_uri.rsplit("/",1)[-1], kind=source_kind, authorization="granted", account_id=self.store.account().get("id"))
            result = ScanResult(catalog=[], scan_id=scan_id)
            metadata, affected_anime_ids, seen = {}, set(), set()
            started = time.time()
            for document in documents or []:
                if not isinstance(document, dict):
                    result.ignored += 1; continue
                uri = document.get("uri")
                if not isinstance(uri, str) or not uri:
                    result.ignored += 1; continue
                if uri in seen:
                    result.duplicates += 1; continue
                seen.add(uri)
                if generation is not None and self.store.has_observation_for_generation(uri, source_kind=source_kind, scope_kind=scope_kind, scope_ref=scope_ref, native_generation=generation):
                    result.duplicates += 1; continue
                accepted = self._record_document(document=document, source_folder=tree_uri, source_kind=source_kind, metadata=metadata, result=result, affected_anime_ids=affected_anime_ids, known_paths=seen, scope_kind=scope_kind, scope_ref=scope_ref, native_generation=generation)
                if accepted: result.videos += 1
            result.errors.extend(str(e) for e in (scan_errors or []))
            elapsed_ms = int((time.time()-started)*1000)
            self.store.update_scan_progress(run_id, result.__dict__, request_id=request_id, source=source_kind, volume_id=scope_ref if scope_kind=="volume" else None, scope=scope_ref, batch_id=batch_id, batch_number=batch_number, batch_size=batch_size if batch_size is not None else len(documents or []), discovered=len(documents or []), processed=result.files, inserted=result.new, elapsed_ms=elapsed_ms, errors=result.errors)
            return {"scan_id":scan_id,"request_id":request_id,"generation_id":generation_id or scan_id,"batch_id":batch_id,"batch_number":batch_number,"batch_size":batch_size if batch_size is not None else len(documents or []),"files":result.files,"videos":result.videos,"processed":result.files,"discovered":len(documents or []),"inserted":result.new,"new":result.new,"updated":result.updated,"unchanged":result.unchanged,"duplicates":result.duplicates,"removed":0,"ignored":result.ignored,"unknown":result.unknown,"errors":result.errors,"elapsed_ms":elapsed_ms,"elapsedMs":elapsed_ms}

    def finish_ingest_documents(self, tree_uri: str, *, source_kind="saf", scan_id=None, scope_kind="global", scope_ref=None, scan_generation=None, generation_id=None, status="completed", folder_name=None, scan_errors=None, scan_stats=None):
        """Finalize a native scan; only a trusted COMPLETE generation reconciles."""
        with self._scan_lock:
            scan_id = scan_id or str(uuid.uuid4()); scope_ref = scope_ref or tree_uri
            row = self.store.scan_by_id(scan_id)
            run_id = int(row["id"]) if row else self.store.begin_scan(scan_id=scan_id, source_kind=source_kind, scope_kind=scope_kind, scope_ref=scope_ref, native_generation=scan_generation, generation_id=str(generation_id or scan_id))
            final_status = str(status or "completed").casefold(); errors = [str(e) for e in (scan_errors or [])]; stats = scan_stats or {}
            row = self.store.scan_by_id(scan_id) or {}
            try:
                historical_errors = json.loads(row.get("errors") or "[]")
            except (TypeError, json.JSONDecodeError):
                historical_errors = []
            if not isinstance(historical_errors, list):
                historical_errors = []
            errors = list(dict.fromkeys([str(e) for e in historical_errors] + errors))
            complete = final_status in {"completed","complete","empty_complete"} and not errors and scan_generation is not None
            generation = int(scan_generation) if scan_generation is not None else None
            reconciled = 0
            if complete:
                reconciled = self.store.reconcile_scope_generation(tree_uri, source_kind=source_kind, scope_kind=scope_kind, scope_ref=scope_ref, native_generation=generation, complete=True)
                for anime_id in sorted(self.store.generation_anime_ids(source_kind=source_kind, scope_kind=scope_kind, scope_ref=scope_ref, native_generation=generation)): self.artwork.reindex_entity(anime_id)
                self.store.update_folder_status(tree_uri, "granted")
            row = self.store.scan_by_id(scan_id) or {}
            result = ScanResult(catalog=[], scan_id=scan_id, status=final_status)
            for attr,col in (("files","files"),("videos","videos"),("new","new_files"),("updated","updated_files"),("unchanged","unchanged_files"),("duplicates","duplicate_files"),("ignored","ignored_files"),("unknown","unknown_files")): setattr(result,attr,int(row.get(col) or stats.get(col,0) or 0))
            result.reconciled = reconciled; result.errors = errors
            summary = dict(result.__dict__); summary.update(discovered=int(row.get("discovered") or result.files), processed=int(row.get("processed") or result.files), inserted=int(row.get("inserted_files") or result.new), removed=reconciled, elapsed_ms=int(row.get("elapsed_ms") or 0))
            self.store.finish_scan(run_id, summary)
            result.catalog = self.store.catalog(); result.animes = len(result.catalog); result.episodes = sum(len(s["episodes"]) for a in result.catalog for s in a["seasons"]) + sum(len(a.get("media_files",[])) for a in result.catalog)
            return result
    def scan(self, on_status=lambda _ : None):
        with self._scan_lock:
            scan_id = str(uuid.uuid4())
            run_id = self.store.begin_scan(scan_id=scan_id, source_kind="filesystem", scope_kind="global", scope_ref=None, generation_id=scan_id)
            result = ScanResult(catalog=[], scan_id=scan_id)
            try:
                parsed = []
                seen_by_source = {}
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
                        self.store.mark_source_unavailable(reference, "folder_unavailable")
                        result.errors.append(f"{folder['name']}: {error}")
                        continue
                    self.store.update_folder_status(reference, "granted")
                    self.store.restore_source(reference)
                    on_status(f"Encontrando vídeos em {folder['name']}…")
                    try:
                        seen = []
                        walk_errors = []
                        def _on_walk_error(error):
                            walk_errors.append(error)
                            result.errors.append(f"{folder['name']}: diretório não pôde ser lido: {getattr(error, 'filename', error)}")
                        for root, dirnames, files in os.walk(reference, onerror=_on_walk_error):
                            names_casefold = {str(name).casefold() for name in files}
                            if ".nomedia" in names_casefold:
                                result.nomedia_directories += 1
                                result.nomedia_files += 1
                                result.ignored += sum(1 for name in files if str(name).casefold() != ".nomedia")
                                dirnames[:] = []
                                continue

                            allowed_dirs = []
                            for dirname in dirnames:
                                child = os.path.join(root, dirname)
                                try:
                                    has_nomedia = os.path.isfile(os.path.join(child, ".nomedia"))
                                except OSError as exc:
                                    walk_errors.append(exc)
                                    result.errors.append(f"{folder['name']}: não foi possível verificar {dirname}: {exc}")
                                    has_nomedia = False
                                if has_nomedia:
                                    result.nomedia_directories += 1
                                    result.nomedia_files += 1
                                    continue
                                allowed_dirs.append(dirname)
                            dirnames[:] = allowed_dirs

                            for name in files:
                                result.files += 1
                                if str(name).casefold() == ".nomedia":
                                    result.ignored += 1
                                    continue
                                if os.path.splitext(name)[1].lower() not in VIDEO_EXTENSIONS:
                                    result.ignored += 1
                                    continue
                                path = os.path.join(root, name)
                                try:
                                    stat = os.stat(path)
                                except OSError as exc:
                                    # An inaccessible file is not evidence of removal.
                                    # Block reconciliation for this source until a complete
                                    # scan can establish absence safely.
                                    walk_errors.append(exc)
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
                        seen_by_source[reference] = set(seen)
                        if not walk_errors:
                            self.store.reconcile_missing(reference, seen, source_kind="filesystem", scope_kind="source", scope_ref=reference, complete=True)
                        else:
                            self.store.update_folder_status(reference, "granted", "Scan parcial; reconciliação de ausência não aplicada.")
                    except OSError as exc:
                        result.errors.append(f"{folder['name']}: erro ao ler pasta: {exc}")
                metadata = {}
                affected_anime_ids = set()
                for document, source_folder, source_kind in parsed:
                    self._record_document(
                        document=document,
                        source_folder=source_folder,
                        source_kind=source_kind,
                        metadata=metadata,
                        result=result,
                        affected_anime_ids=affected_anime_ids,
                        known_paths=seen_by_source.get(source_folder),
                        scope_kind="source",
                        scope_ref=source_folder,
                    )
                for anime_id in sorted(affected_anime_ids):
                    self.artwork.reindex_entity(anime_id)
                result.catalog = self.store.catalog()
                result.animes = len(result.catalog)
                result.episodes = sum(len(s["episodes"]) for a in result.catalog for s in a["seasons"]) + sum(len(a.get("media_files", [])) for a in result.catalog)
                if result.errors:
                    result.status = "partial"
                self.store.finish_scan(run_id, result.__dict__)
                return result
            except Exception as exc:
                result.errors.append(f"Falha geral no scan: {exc}")
                result.status = "error"
                self.store.finish_scan(run_id, result.__dict__)
                raise

    def ingest_documents(self, tree_uri: str, documents: list[dict], on_status=lambda _: None, *,
                         folder_name=None, scan_errors=None, scan_stats=None, source_kind="saf",
                         scan_id=None, scope_kind="global", scope_ref=None, scan_generation=None,
                         scope_scans=None):
        """Index one native source without destructive reconciliation on partial scans."""
        with self._scan_lock:
            scan_id = scan_id or str(uuid.uuid4())
            scope_ref = scope_ref or tree_uri
            previous = self.store.scan_by_id(scan_id)
            if previous and previous.get("status") in {"completed", "partial", "cancelled", "error", "failed"}:
                return self.store.catalog()
            try:
                native_generation = int(scan_generation) if scan_generation is not None else None
            except (TypeError, ValueError):
                native_generation = None
            if native_generation is not None and native_generation > 0:
                latest = self.store.latest_completed_native_generation(source_kind, scope_kind, scope_ref or tree_uri)
                if latest is not None and native_generation < latest:
                    logger.info("Ignoring stale native scan generation %s < %s", native_generation, latest)
                    return self.store.catalog()
            scan_scopes = [scope for scope in (scope_scans or []) if isinstance(scope, dict)]
            scan_errors = list(scan_errors or [])
            scan_stats = scan_stats or {}
            generation_id = str(scan_stats.get("generationId") or scan_stats.get("generation_id") or scan_id)
            run_id = self.store.begin_scan(
                scan_id=scan_id, source_kind=source_kind, scope_kind=scope_kind,
                scope_ref=scope_ref or tree_uri, native_generation=native_generation,
                generation_id=generation_id,
            )
            result = ScanResult(catalog=[], scan_id=scan_id)
            native_scan_state = str(scan_stats.get("status") or scan_stats.get("generationStatus") or "").casefold()
            partial_scan = bool(
                scan_stats.get("partial")
                or scan_stats.get("cancelled")
                or native_scan_state in {"partial", "failed", "cancelled", "canceled", "error", "unavailable", "revoked"}
            )
            try:
                self.store.add_folder(
                    tree_uri,
                    name=folder_name or tree_uri.rsplit("/", 1)[-1],
                    kind=source_kind,
                    authorization="granted",
                    account_id=self.store.account().get("id"),
                )
                metadata = {}
                affected_anime_ids = set()
                seen = set()
                trusted_scope_defs = {}
                trusted_scope_seen = {}
                for scope in scan_scopes:
                    status = str(scope.get("status") or ("completed" if scope.get("complete") else "partial")).casefold()
                    complete_scope = bool(scope.get("complete")) and status in {"completed", "complete", "empty_complete"}
                    skind = str(scope.get("scopeKind") or ("volume" if scope.get("volumeId") else scope_kind)).strip() or scope_kind
                    sref = str(scope.get("scopeRef") or scope.get("volumeId") or "").strip()
                    if complete_scope and sref:
                        key = (skind, sref)
                        trusted_scope_defs[key] = scope
                        trusted_scope_seen[key] = set()
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
                        affected_anime_ids=affected_anime_ids,
                        known_paths=seen,
                        scope_kind=scope_kind,
                        scope_ref=scope_ref,
                        native_generation=native_generation,
                    )
                    if accepted:
                        result.videos += 1
                        volume_id = str((document or {}).get("volumeId") or "").strip() if isinstance(document, dict) else ""
                        physical = self.store.physical_row(uri)
                        if physical:
                            for scope in scan_scopes:
                                skind = str(scope.get("scopeKind") or "").strip().casefold()
                                sref = str(scope.get("scopeRef") or scope.get("volumeId") or "").strip()
                                if not skind or not sref:
                                    continue
                                if skind == "volume" and sref == volume_id:
                                    self.store.record_observation(
                                        physical["id"],
                                        source_kind=source_kind,
                                        scope_kind=skind,
                                        scope_ref=sref,
                                        uri=uri,
                                        volume_id=volume_id,
                                        native_generation=native_generation,
                                        fingerprint=(document or {}).get("nativeFingerprint") if isinstance(document, dict) else None,
                                    )
                                    if scope.get("complete") and str(scope.get("status") or "completed").casefold() in {"completed", "complete", "empty_complete"}:
                                        trusted_scope_seen.setdefault((skind, sref), set()).add(uri)

                for anime_id in sorted(affected_anime_ids):
                    self.artwork.reindex_entity(anime_id)

                result.errors.extend(str(error) for error in scan_errors)
                if scan_stats.get("cancelled") or native_scan_state in {"cancelled", "canceled"}:
                    result.status = "cancelled"
                elif native_scan_state == "revoked":
                    result.status = "revoked"
                elif scan_errors or partial_scan:
                    result.status = "partial" if native_scan_state not in {"failed", "error"} else "error"
                elif native_scan_state == "empty_complete":
                    result.status = "empty_complete"
                if not scan_errors and not partial_scan and trusted_scope_defs:
                    for (skind, sref), _scope in trusted_scope_defs.items():
                        self.store.reconcile_scope(
                            tree_uri,
                            list(trusted_scope_seen.get((skind, sref), set())),
                            source_kind=source_kind,
                            scope_kind=skind,
                            scope_ref=sref,
                            complete=True,
                        )
                        result.reconciled += 1
                    self.store.update_folder_status(tree_uri, "granted")
                elif not scan_errors and not partial_scan:
                    self.store.reconcile_scope(
                        tree_uri,
                        list(seen),
                        source_kind=source_kind,
                        scope_kind=scope_kind,
                        scope_ref=scope_ref,
                        complete=True,
                    )
                    result.reconciled = 1
                    self.store.update_folder_status(tree_uri, "granted")
                else:
                    self.store.update_folder_status(tree_uri, "granted", "; ".join(map(str, scan_errors)))
                catalog = self.store.catalog()
                result.catalog = catalog
                result.folders = 1
                if result.errors and result.status not in {"cancelled", "error"}:
                    result.status = "partial"
                    self.store.update_folder_status(tree_uri, "granted", "; ".join(result.errors[-10:]))
                result.files = int(scan_stats.get("files") or result.files)
                result.videos = int(scan_stats.get("videos") or result.videos)
                result.animes = len(catalog)
                result.episodes = sum(len(season["episodes"]) for anime in catalog for season in anime["seasons"]) + sum(len(anime.get("media_files", [])) for anime in catalog)
                self.store.finish_scan(run_id, result.__dict__)
                return catalog
            except Exception as exc:
                result.errors.append(f"Falha ao indexar a fonte: {exc}")
                result.status = "error"
                self.store.finish_scan(run_id, result.__dict__)
                raise

    def ingest_native_volume_change(self, payload):
        """Persist authoritative native volume availability without touching the catalog."""
        if not isinstance(payload, dict):
            raise ValueError("Native volume event must contain an object payload.")
        current = payload.get("current") or []
        if not isinstance(current, list):
            raise ValueError("Native volume snapshot must be a list.")
        normalized = []
        for item in current:
            if not isinstance(item, dict):
                continue
            volume_id = str(item.get("volumeId") or "").strip()
            if not volume_id:
                continue
            normalized.append({
                "volumeId": volume_id,
                "uuid": str(item.get("uuid") or ""),
                "state": str(item.get("state") or "unknown"),
                "removable": bool(item.get("removable")),
                "emulated": bool(item.get("emulated")),
                "primary": bool(item.get("primary")),
                "directory": str(item.get("directory") or ""),
                "description": str(item.get("description") or ""),
            })
        removed = payload.get("removed") or []
        enriched = {
            "current": normalized,
            "removed": removed,
            "eventTimestamp": payload.get("eventTimestamp") or payload.get("timestamp") or payload.get("observedAt"),
        }
        return self.store.record_native_volume_change(enriched)

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
        self.store.upsert_anime(lookup_title, metadata, source="anilist", confidence="high", status="available", fetched_at=time.time())
        self.store.resolve_match(lookup_title, anilist_id)
        return metadata
    def catalog(self, favorites_only=False): return self.store.catalog(favorites_only)
    def create_backup(self, destination=None): return self.store.create_backup(destination)

    def restore_backup(self, backup_path=None): return self.store.restore_backup(backup_path)


    def media_center_home(self, limit=12, *, catalog=None):
        """Build all Home sections from one already-aggregated local catalog.

        A preloaded catalog can be supplied by callers such as Home to avoid
        materializing the same full SQLite projection twice.
        """
        catalog = self.store.catalog() if catalog is None else catalog
        episodes = [e for anime in catalog for season in anime.get("seasons", [])
                    for e in season.get("episodes", [])]
        specials = [e for anime in catalog for group in anime.get("specials", [])
                    for e in group.get("episodes", [])]
        all_media = episodes + specials + [e for anime in catalog for e in anime.get("media_files", [])]
        by_path = {e.get("path"): e for e in all_media if e.get("path")}
        continue_items = self.store.continue_watching(limit=limit)
        for item in continue_items:
            if item.get("path") in by_path:
                item["next_episode"] = by_path[item["path"]]
        history = self.store.playback_history(limit=limit)
        recently_added = sorted(
            catalog,
            key=lambda a: (a.get("meta", {}).get("added_at") or 0, a.get("last_played_at") or 0),
            reverse=True,
        )[:limit]
        series = [a for a in catalog if a.get("media_kind") != "movie"]
        movies = [a for a in catalog if a.get("media_kind") == "movie"]
        favorites = [a for a in catalog if a.get("favorite")]
        pinned = [a for a in catalog if a.get("is_pinned")]
        next_items = [a for a in series if a.get("next_episode") and not a["next_episode"].get("watched")]
        next_items.sort(key=lambda a: a.get("last_played_at") or 0, reverse=True)
        return {
            "continue_watching": continue_items,
            "next_episode": next_items[:limit],
            "recently_added": recently_added,
            "recently_watched": history,
            "favorites": favorites[:limit],
            "pinned": pinned[:limit],
            "series": series[:limit],
            "movies": movies[:limit],
            "specials": [a for a in catalog if any(a.get("specials"))][:limit],
        }

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
        """Build Organize categories from the same search/filter policy used by collections.

        Counts intentionally come from the reusable search engine so every
        category badge represents exactly the population that its click opens.
        Genre labels are only grouped by the existing matching normalization;
        Prompt 6 remains responsible for a full genre registry.
        """
        catalog = list(catalog or [])
        state_names = (
            "Todos",
            "Favoritos",
            "Fixados",
            "Assistidos",
            "Não assistidos",
            "Em andamento",
            "Concluídos",
        )
        states = [
            {
                "name": name,
                "count": len(LibrarySearchEngine.search(catalog, state=name)),
            }
            for name in state_names
        ]

        genres = {}
        for anime in catalog:
            cover = (anime.get("meta") or {}).get("cover_cache") or (anime.get("meta") or {}).get("cover_url")
            for genre in anime.get("genres") or []:
                label = str(genre or "").strip()
                if not label:
                    continue
                key = " ".join(label.casefold().split())
                entry = genres.setdefault(
                    key,
                    {"name": label, "count": 0, "cover": cover or ""},
                )
                entry["count"] += 1
                if not entry["cover"] and cover:
                    entry["cover"] = cover

        return {
            "genres": sorted(genres.values(), key=lambda item: item["name"].casefold()),
            "states": states,
        }

    @staticmethod
    def browse_catalog(catalog, query="", state="Todos", genre="Todos", sort="Mais recentes", tag="Todos",
                       *, media_type="Todos", season=None, episode_type="Todos", source_kind="Todos",
                       availability="Todos", metadata="Todos", artwork="Todos"):
        """Search/filter/sort the already projected local catalog.

        This compatibility facade keeps Home/Organize callers stable while the
        matching policy lives in the reusable local SearchFilterSort engine.
        """
        return LibrarySearchEngine.search(
            catalog,
            query=query,
            state=state,
            genre=genre,
            sort=sort,
            tag=tag,
            media_type=media_type,
            season=season,
            episode_type=episode_type,
            source_kind=source_kind,
            availability=availability,
            metadata=metadata,
            artwork=artwork,
        )

    @staticmethod
    def search_options(catalog):
        return LibrarySearchEngine.options(catalog)

