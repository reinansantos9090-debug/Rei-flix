import urllib.parse
from core.scraper import BaseScraper

class AnimeProvider:
    BASE_URL = "https://animefire.plus"  # Fonte base para raspar links de episódios

    @staticmethod
    def search_and_get_episodes(anime_title: str):
        """Busca o anime e retorna uma lista com os episódios e links de vídeo"""
        encoded_title = urllib.parse.quote(anime_title)
        search_url = f"{AnimeProvider.BASE_URL}/pesquisar/{encoded_title}"
        soup = BaseScraper.get_html(search_url)

        if not soup:
            return []

        # Tenta localizar o primeiro resultado da busca no site
        anime_link = None
        for a in soup.find_all('a', href=True):
            if '/animes/' in a['href']:
                anime_link = a['href']
                break

        if not anime_link:
            return []

        # Acessa a página principal do anime para pegar os episódios
        anime_page = BaseScraper.get_html(anime_link)
        if not anime_page:
            return []

        episodes = []
        # Procura os links de episódios
        for ep_a in anime_page.find_all('a', href=True):
            href = ep_a['href']
            if '/video/' in href or '-todos-os-episodios' in href:
                ep_title = ep_a.text.strip() or "Episódio"
                episodes.append({
                    'title': ep_title,
                    'url': href
                })

        return episodes

    @staticmethod
    def get_video_stream_url(episode_page_url: str) -> str:
        """Acessa a página do episódio e extrai a URL direta do vídeo (.mp4/.mkv)"""
        soup = BaseScraper.get_html(episode_page_url)
        if not soup:
            return None

        # Procura a tag <video> ou <source>
        video_tag = soup.find('video')
        if video_tag:
            source = video_tag.find('source')
            if source and source.get('src'):
                return source['src']
            if video_tag.get('src'):
                return video_tag['src']

        return None

