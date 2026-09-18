"""Cliente AniList somente para metadados, com falha segura e cache de capas."""
from __future__ import annotations
import hashlib, json, logging, os, urllib.request

logger = logging.getLogger(__name__)

class AniListClient:
    endpoint='https://graphql.anilist.co'
    media_fields='''id title{romaji english native} synonyms description(asHtml:false) coverImage{extraLarge large} bannerImage genres seasonYear season status episodes duration averageScore studios(isMain:true){nodes{name}}'''
    query=f'''query($search:String){{Page(perPage:5){{media(search:$search,type:ANIME){{{media_fields}}}}}}}'''
    by_id_query=f'''query($id:Int){{Media(id:$id,type:ANIME){{{media_fields}}}}}'''
    def __init__(self, cache_dir): self.cache_dir=cache_dir
    def _request(self, query, variables):
        data=json.dumps({'query':query,'variables':variables}).encode()
        req=urllib.request.Request(self.endpoint,data=data,headers={'Content-Type':'application/json','Accept':'application/json','User-Agent':'ReiFlix/1.0'})
        try:
            with urllib.request.urlopen(req,timeout=10) as r:
                payload=json.loads(r.read())
            if payload.get('errors') or not isinstance(payload.get('data'), dict):
                logger.warning("AniList retornou erro GraphQL: %s", payload.get('errors'))
                return None
            return payload['data']
        except Exception as exc:
            logger.warning("AniList indisponível: %s", exc)
            return None
    def search(self,title):
        data=self._request(self.query, {'search':title})
        return ((data or {}).get('Page') or {}).get('media') or []
    def by_id(self, anilist_id):
        data=self._request(self.by_id_query, {'id':anilist_id})
        return (data or {}).get('Media')
    def metadata(self,title,chosen_id=None):
        media=self.by_id(chosen_id) if chosen_id else None
        if not media:
            results=self.search(title); media=next((m for m in results if m['id']==chosen_id),results[0] if results else None)
        return self.metadata_from_media(title, media)
    def metadata_from_media(self, title, media):
        if not media: return {'title':title,'genres':'[]'}
        cover=(media.get('coverImage') or {}).get('extraLarge') or (media.get('coverImage') or {}).get('large') or ''
        cache=self.cache_cover(cover) if cover else ''
        t=media.get('title') or {}; studios=((media.get('studios') or {}).get('nodes') or [])
        return {'anilist_id':media['id'],'title':t.get('english') or t.get('romaji') or title,'romaji':t.get('romaji'),'english':t.get('english'),'native':t.get('native'),'aliases':json.dumps(media.get('synonyms') or [],ensure_ascii=False),'description':media.get('description') or 'Sem sinopse disponível.','cover_url':cover,'cover_cache':cache,'banner_url':media.get('bannerImage') or '','genres':json.dumps(media.get('genres') or [],ensure_ascii=False),'year':media.get('seasonYear'),'season':media.get('season'),'status':media.get('status'),'episodes_count':media.get('episodes'),'duration':media.get('duration'),'score':media.get('averageScore'),'studio':', '.join(x.get('name','') for x in studios)}
    def cache_cover(self,url):
        name=hashlib.sha256(url.encode()).hexdigest()+os.path.splitext(url.split('?')[0])[1][:5]
        target=os.path.join(self.cache_dir,name)
        if os.path.exists(target): return target
        try:
            with urllib.request.urlopen(url,timeout=15) as r, open(target,'wb') as f: f.write(r.read())
            return target
        except Exception as exc:
            logger.warning("Não foi possível baixar capa AniList: %s", exc)
            return ''
