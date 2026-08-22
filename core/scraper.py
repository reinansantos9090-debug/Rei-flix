import urllib.request
from bs4 import BeautifulSoup

class BaseScraper:
    @staticmethod
    def get_html(url: str) -> BeautifulSoup:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                html = response.read().decode('utf-8')
                return BeautifulSoup(html, 'html.parser')
        except Exception as e:
            print(f"Erro ao acessar {url}: {e}")
            return None
