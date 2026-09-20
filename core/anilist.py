"""Cliente AniList somente para metadados, com falha segura e cache de capas."""
from __future__ import annotations
import hashlib, json, logging, os, tempfile, urllib.error, urllib.request

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
                raw = r.read()
            payload = json.loads(raw)
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                retry_after = exc.headers.get("Retry-After")
                try:
                    delay = max(0.0, min(float(retry_after), 60.0))
                except (TypeError, ValueError):
                    delay = 0.0
                if delay:
                    logger.warning("AniList atingiu rate limit; aguardando %.1fs antes de uma nova tentativa.", delay)
                    try:
                        import time
                        time.sleep(delay)
                    except Exception:
                        return None
                    try:
                        with urllib.request.urlopen(req, timeout=10) as retry_response:
                            raw = retry_response.read()
                        payload = json.loads(raw)
                    except Exception as retry_exc:
                        logger.warning("AniList indisponível após rate limit: %s", retry_exc)
                        return None
                else:
                    logger.warning("AniList retornou HTTP 429 sem Retry-After.")
                    return None
            else:
                logger.warning("AniList indisponível: HTTP %s", exc.code)
                return None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            logger.warning("AniList indisponível: %s", exc)
            return None
        except Exception as exc:
            logger.warning("Falha inesperada na comunicação com AniList: %s", exc)
            return None
        if not isinstance(payload, dict):
            logger.warning("AniList retornou uma resposta inválida.")
            return None
        if payload.get('errors'):
            logger.warning("AniList retornou erro GraphQL: %s", payload.get('errors'))
            return None
        data = payload.get('data')
        if not isinstance(data, dict):
            logger.warning("AniList não retornou dados GraphQL válidos.")
            return None
        return data
    def search(self,title):
        data=self._request(self.query, {'search':title})
        return ((data or {}).get('Page') or {}).get('media') or []
    def by_id(self, anilist_id):
        data=self._request(self.by_id_query, {'id':anilist_id})
        return (data or {}).get('Media')
    def metadata(self,title,chosen_id=None):
        media=self.by_id(chosen_id) if chosen_id else None
        if not media:
            results=self.search(title)
            if chosen_id is not None:
                media = next((m for m in results if m.get('id') == chosen_id), None)
            if media is None:
                media = results[0] if results else None
        return self.metadata_from_media(title, media)
    def metadata_from_media(self, title, media):
        if not media: return {'title':title,'genres':'[]'}
        cover=(media.get('coverImage') or {}).get('extraLarge') or (media.get('coverImage') or {}).get('large') or ''
        cache=self.cache_cover(cover) if cover else ''
        t=media.get('title') or {}; studios=((media.get('studios') or {}).get('nodes') or [])
        studios = [studio for studio in studios if isinstance(studio, dict)]
        metadata = {'title':t.get('english') or t.get('romaji') or title,'romaji':t.get('romaji'),'english':t.get('english'),'native':t.get('native'),'aliases':json.dumps(media.get('synonyms') or [],ensure_ascii=False),'description':(media.get('description') or '').strip(),'cover_url':cover,'cover_cache':cache,'banner_url':media.get('bannerImage') or '','genres':json.dumps(media.get('genres') or [],ensure_ascii=False),'year':media.get('seasonYear'),'season':media.get('season'),'status':media.get('status'),'episodes_count':media.get('episodes'),'duration':media.get('duration'),'score':media.get('averageScore'),'studio':', '.join(x.get('name','') for x in studios)}
        if media.get('id') is not None:
            metadata['anilist_id'] = media['id']
        return metadata
    def cache_cover(self,url):
        name=hashlib.sha256(url.encode()).hexdigest()+os.path.splitext(url.split('?')[0])[1][:5]
        target=os.path.join(self.cache_dir,name)
        if os.path.isfile(target) and os.path.getsize(target) > 0: return target
        descriptor, temporary = tempfile.mkstemp(prefix=f".{name}.", suffix=".tmp", dir=self.cache_dir)
        try:
            with os.fdopen(descriptor, 'wb') as f, urllib.request.urlopen(url,timeout=15) as r:
                payload = r.read()
                if not payload:
                    raise ValueError("A capa AniList está vazia.")
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, target)
            return target
        except Exception as exc:
            try: os.unlink(temporary)
            except OSError as cleanup_error: logger.warning("Não foi possível remover capa temporária: %s", cleanup_error)
            logger.warning("Não foi possível baixar capa AniList: %s", exc)
            return ''
