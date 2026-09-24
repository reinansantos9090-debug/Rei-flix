"""Cliente AniList somente para metadados, com falha segura e cache de capas."""
from __future__ import annotations
import hashlib, json, logging, os, tempfile, threading, time, urllib.error, urllib.request

logger = logging.getLogger(__name__)

class AniListClient:
    endpoint='https://graphql.anilist.co'
    media_fields='''id title{romaji english native} synonyms description(asHtml:false) coverImage{extraLarge large} bannerImage genres seasonYear season status episodes duration averageScore format studios(isMain:true){nodes{name}}'''
    query=f'''query($search:String){{Page(perPage:10){{media(search:$search,type:ANIME){{{media_fields}}}}}}}'''
    by_id_query=f'''query($id:Int){{Media(id:$id,type:ANIME){{{media_fields}}}}}'''
    def __init__(self, cache_dir):
        self.cache_dir = cache_dir
        self._rate_lock = threading.RLock()
        self._next_request_at = 0.0
        self._min_interval = 0.7
        self._rate_limit = None
        self._rate_remaining = None
        self._rate_reset = None
        self._transport_backoff_until = 0.0
        self._transport_failures = 0
        self._last_request_status = "idle"

    @staticmethod
    def _header(headers, name):
        if headers is None: return None
        try: return headers.get(name)
        except AttributeError:
            try: return headers.get(name.lower())
            except AttributeError: return None

    def _pace_request(self):
        with self._rate_lock:
            now = time.monotonic()
            backoff = max(0.0, self._transport_backoff_until - now)
            delay = max(backoff, self._next_request_at - now)
        if delay:
            time.sleep(delay)
        with self._rate_lock:
            self._next_request_at = time.monotonic() + self._min_interval

    def _transport_failure(self):
        with self._rate_lock:
            self._transport_failures += 1
            delay = min(300.0, 30.0 * (2 ** (self._transport_failures - 1)))
            self._transport_backoff_until = time.monotonic() + delay
        logger.warning("AniList transporte indisponível; backoff de %.1fs aplicado.", delay)

    def _transport_success(self):
        with self._rate_lock:
            self._transport_failures = 0
            self._transport_backoff_until = 0.0

    def _observe_rate_headers(self, headers):
        limit_raw = self._header(headers, 'X-RateLimit-Limit')
        remaining_raw = self._header(headers, 'X-RateLimit-Remaining')
        reset_raw = self._header(headers, 'X-RateLimit-Reset')
        try: limit = int(limit_raw) if limit_raw is not None else None
        except (TypeError, ValueError): limit = None
        try: remaining = int(remaining_raw) if remaining_raw is not None else None
        except (TypeError, ValueError): remaining = None
        try: reset = float(reset_raw) if reset_raw is not None else None
        except (TypeError, ValueError): reset = None
        with self._rate_lock:
            if limit and limit > 0:
                self._rate_limit = limit
                self._min_interval = max(0.7, min(3.0, 60.0 / float(limit)))
            if remaining is not None: self._rate_remaining = remaining
            if reset is not None: self._rate_reset = reset
            if remaining is not None and remaining <= 2 and reset and reset > time.time():
                window = reset - time.time()
                self._min_interval = max(self._min_interval, min(5.0, window / max(1, remaining + 1)))

    def _retry_delay_from_headers(self, headers):
        retry_after = self._header(headers, 'Retry-After')
        try:
            if retry_after is not None: return max(0.0, min(float(retry_after), 120.0))
        except (TypeError, ValueError): pass
        reset_raw = self._header(headers, 'X-RateLimit-Reset')
        try:
            if reset_raw is not None: return max(0.0, min(float(reset_raw) - time.time(), 120.0))
        except (TypeError, ValueError): pass
        return 0.0
    def _request(self, query, variables):
        self._last_request_status = "pending"
        data = json.dumps({'query': query, 'variables': variables}).encode()
        req = urllib.request.Request(self.endpoint, data=data, headers={'Content-Type':'application/json','Accept':'application/json','User-Agent':'ReiFlix/1.0'})
        with self._rate_lock:
            if time.monotonic() < self._transport_backoff_until:
                logger.info("AniList request skipped during transport backoff.")
                self._last_request_status = "network_error"
                return None
        self._pace_request()
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                raw = response.read()
                self._observe_rate_headers(getattr(response, 'headers', None))
            self._transport_success()
            payload = json.loads(raw)
        except urllib.error.HTTPError as exc:
            self._observe_rate_headers(getattr(exc, 'headers', None))
            if exc.code == 429:
                delay = self._retry_delay_from_headers(getattr(exc, 'headers', None))
                if delay > 0:
                    logger.warning('AniList atingiu rate limit; aguardando %.1fs antes de uma nova tentativa.', delay)
                    time.sleep(delay)
                    with self._rate_lock:
                        self._next_request_at = time.monotonic() + self._min_interval
                    try:
                        with urllib.request.urlopen(req, timeout=10) as retry_response:
                            raw = retry_response.read()
                            self._observe_rate_headers(getattr(retry_response, 'headers', None))
                        payload = json.loads(raw)
                    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as retry_exc:
                        logger.warning('AniList indisponível após rate limit: %s', retry_exc)
                        self._last_request_status = "rate_limited"
                        return None
                    except Exception as retry_exc:
                        logger.warning('Falha inesperada após rate limit do AniList: %s', retry_exc)
                        self._last_request_status = "network_error"
                        return None
                else:
                    logger.warning('AniList retornou HTTP 429 sem um atraso utilizável.')
                    self._last_request_status = "rate_limited"
                    return None
            else:
                self._last_request_status = "rate_limited" if exc.code == 429 else ("network_error" if exc.code >= 500 else "http_error")
                logger.warning('AniList indisponível: HTTP %s', exc.code)
                if exc.code >= 500:
                    self._transport_failure()
                return None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            self._transport_failure()
            self._last_request_status = "network_error"
            logger.warning('AniList indisponível: %s', exc)
            return None
        except json.JSONDecodeError as exc:
            self._last_request_status = "invalid_response"
            logger.warning('AniList retornou JSON inválido: %s', exc)
            return None
        except Exception as exc:
            self._last_request_status = "network_error"
            logger.warning('Falha inesperada na comunicação com AniList: %s', exc)
            return None
        if not isinstance(payload, dict):
            self._last_request_status = "invalid_response"
            logger.warning("AniList retornou uma resposta inválida.")
            return None
        if payload.get('errors'):
            self._last_request_status = "invalid_response"
            logger.warning("AniList retornou erro GraphQL: %s", payload.get('errors'))
            return None
        data = payload.get('data')
        if not isinstance(data, dict):
            self._last_request_status = "invalid_response"
            logger.warning("AniList não retornou dados GraphQL válidos.")
            return None
        self._last_request_status = "ok"
        return data
    @property
    def last_request_status(self):
        return self._last_request_status
    def search_detailed(self, title):
        data = self._request(self.query, {'search': title})
        results = ((data or {}).get('Page') or {}).get('media') or []
        if self._last_request_status == 'pending':
            self._last_request_status = 'ok'
        return {"status": "ok" if self._last_request_status == "ok" else self._last_request_status,
                "results": [item for item in results if isinstance(item, dict)]}
    def search(self,title):
        result = self.search_detailed(title)
        if isinstance(result, dict):
            self._last_request_status = str(result.get("status") or self._last_request_status or "invalid_response")
            return result.get("results") or []
        self._last_request_status = "invalid_response"
        return []
    def by_id(self, anilist_id):
        data=self._request(self.by_id_query, {'id':anilist_id})
        return (data or {}).get('Media')
    def metadata(self,title,chosen_id=None):
        media=self.by_id(chosen_id) if chosen_id else None
        if not media:
            results=self.search(title)
            if chosen_id is not None:
                media = next((m for m in results if m.get('id') == chosen_id), None)
            if media is None and chosen_id is None:
                media = results[0] if results else None
        return self.metadata_from_media(title, media)
    def metadata_from_media(self, title, media):
        if not media: return {'title':title,'genres':'[]'}
        cover=(media.get('coverImage') or {}).get('extraLarge') or (media.get('coverImage') or {}).get('large') or ''
        # ArtworkEngine owns persistent cover downloads. Keep cache_cover() as a
        # compatibility API for older callers/tests, but do not download here.
        cache=''
        t=media.get('title') or {}; studios=((media.get('studios') or {}).get('nodes') or [])
        studios = [studio for studio in studios if isinstance(studio, dict)]
        metadata = {'title':t.get('english') or t.get('romaji') or title,'romaji':t.get('romaji'),'english':t.get('english'),'native':t.get('native'),'aliases':json.dumps(media.get('synonyms') or [],ensure_ascii=False),'description':(media.get('description') or '').strip(),'cover_url':cover,'cover_cache':cache,'banner_url':media.get('bannerImage') or '','genres':json.dumps(media.get('genres') or [],ensure_ascii=False),'year':media.get('seasonYear'),'season':media.get('season'),'status':media.get('status'),'episodes_count':media.get('episodes'),'duration':media.get('duration'),'score':media.get('averageScore'),'format':media.get('format'),'studio':', '.join(x.get('name','') for x in studios)}
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
