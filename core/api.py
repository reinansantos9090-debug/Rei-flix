import requests

class AnimeAPI:
    @staticmethod
    def get_trending():
        url = "https://graphql.anilist.co"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        query = """
        query {
          Page(perPage: 15) {
            media(sort: TRENDING_DESC, type: ANIME) {
              id
              title { romaji english }
              coverImage { extraLarge }
            }
          }
        }
        """
        try:
            res = requests.post(url, json={'query': query}, headers=headers, timeout=10)
            if res.status_code == 200:
                return res.json()['data']['Page']['media']
            return []
        except Exception:
            return []
