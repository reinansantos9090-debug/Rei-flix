"""Real recursive scanner for references that the Python process can read."""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from core.anilist import AniListClient
from core.library_parser import VIDEO_EXTENSIONS, parse_video_path
from core.organizer_ai import AnimeOrganizer

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
    def __init__(self, store): self.store=store; self.anilist=AniListClient(store.cache_dir)
    def scan(self, on_status=lambda _ : None):
        run_id=self.store.begin_scan(); result=ScanResult(catalog=[]); seen=[]; parsed=[]; readable_sources=0
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
            readable_sources += 1; self.store.update_folder_status(reference, 'granted')
            on_status(f"Encontrando vídeos em {folder['name']}…")
            try:
                for root, _, files in os.walk(reference):
                    for name in files:
                        result.files += 1
                        if os.path.splitext(name)[1].lower() in VIDEO_EXTENSIONS:
                            path=os.path.join(root,name); seen.append(path); parsed.append((path,parse_video_path(path,reference))); result.videos += 1
            except OSError as exc:
                error=f'Erro ao ler pasta: {exc}'; self.store.update_folder_status(reference, 'revoked', error); result.errors.append(f"{folder['name']}: {error}")
        if readable_sources:
            self.store.mark_missing(seen)
        metadata={}
        for path,item in parsed:
            key=item.anime_title.casefold()
            if key not in metadata:
                on_status(f'Identificando {item.anime_title}…')
                chosen_id=self.store.association(key)
                if chosen_id: metadata[key]=self.anilist.metadata(item.anime_title,chosen_id)
                else:
                    candidates=self.anilist.search(item.anime_title)
                    selected, confident, ranked=AnimeOrganizer.choose(item.anime_title,candidates)
                    metadata[key]=self.anilist.metadata_from_media(item.anime_title,selected)
                    if selected and confident: self.store.set_association(key,selected['id'])
                    elif ranked: self.store.set_pending_match(key,item.anime_title,ranked[:5])
            anime_id=self.store.upsert_anime(key,metadata[key]); self.store.upsert_episode(anime_id,path,os.path.basename(path),item.season,item.episode)
        result.catalog=self.store.catalog(); result.animes=len(result.catalog); result.episodes=sum(len(s['episodes']) for a in result.catalog for s in a['seasons'])
        self.store.finish_scan(run_id, result.__dict__); on_status(result.message()); return result
    def ingest_documents(self, tree_uri: str, documents: list[dict], on_status=lambda _: None):
        """Persist video document URIs enumerated by Android's ContentResolver."""
        self.store.add_folder(tree_uri, name=tree_uri.rsplit("/", 1)[-1], kind="saf", authorization="granted")
        metadata = {}
        for document in documents:
            uri, name = document.get("uri"), document.get("name")
            if not uri or not name: continue
            item = parse_video_path(name)
            key = item.anime_title.casefold()
            if key not in metadata:
                on_status(f"Identificando {item.anime_title}…")
                selected_id = self.store.association(key)
                if selected_id: metadata[key] = self.anilist.metadata(item.anime_title, selected_id)
                else:
                    candidates = self.anilist.search(item.anime_title)
                    selected, confident, ranked = AnimeOrganizer.choose(item.anime_title, candidates)
                    metadata[key] = self.anilist.metadata_from_media(item.anime_title, selected)
                    if selected and confident: self.store.set_association(key, selected["id"])
                    elif ranked: self.store.set_pending_match(key, item.anime_title, ranked[:5])
            anime_id = self.store.upsert_anime(key, metadata[key])
            self.store.upsert_episode(anime_id, uri, name, item.season, item.episode, document.get("mimeType"), document.get("size"), document.get("modifiedAt"))
        self.store.update_folder_status(tree_uri, "granted")
        return self.store.catalog()

    def resolve_match(self, lookup_title, anilist_id): self.store.resolve_match(lookup_title, anilist_id)
