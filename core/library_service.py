from __future__ import annotations
import os
from core.anilist import AniListClient
from core.library_parser import VIDEO_EXTENSIONS, parse_video_path
from core.organizer_ai import AnimeOrganizer

class LibraryService:
    def __init__(self, store): self.store=store; self.anilist=AniListClient(store.cache_dir)
    def scan(self, on_status=lambda _ : None):
        seen=[]; parsed=[]
        folders=self.store.folders(); on_status('Escaneando biblioteca...')
        for root_folder in folders:
            if not os.path.isdir(root_folder): continue
            for root, _, files in os.walk(root_folder):
                for name in files:
                    path=os.path.join(root,name)
                    if os.path.splitext(name)[1].lower() in VIDEO_EXTENSIONS:
                        seen.append(path); parsed.append((path,parse_video_path(path,root_folder)))
        self.store.mark_missing(seen)
        metadata={}
        for path,item in parsed:
            key=item.anime_title.casefold()
            if key not in metadata:
                on_status(f'Encontrando informações: {item.anime_title}...')
                chosen_id=self.store.association(key)
                if chosen_id:
                    metadata[key]=self.anilist.metadata(item.anime_title,chosen_id)
                else:
                    candidates=self.anilist.search(item.anime_title)
                    selected, confident, ranked=AnimeOrganizer.choose(item.anime_title,candidates)
                    metadata[key]=self.anilist.metadata_from_media(item.anime_title,selected)
                    if selected and confident:
                        self.store.set_association(key,selected['id'])
                    elif ranked:
                        self.store.set_pending_match(key,item.anime_title,ranked[:5])
            anime_id=self.store.upsert_anime(key,metadata[key]); self.store.upsert_episode(anime_id,path,os.path.basename(path),item.season,item.episode)
        on_status('Biblioteca atualizada.')
        return self.store.catalog()
    def resolve_match(self, lookup_title, anilist_id):
        """Confirma a escolha manual; o próximo scan atualiza capa/metadados."""
        self.store.resolve_match(lookup_title, anilist_id)
