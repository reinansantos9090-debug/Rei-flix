import json
import urllib.request

class AnimeAPI:
    @staticmethod
    def _fetch_graphql(query: str, variables: dict = None):
        url = "https://graphql.anilist.co"
        payload = {'query': query}
        if variables:
            payload['variables'] = variables

        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            url, 
            data=data, 
            headers={
                'Content-Type': 'application/json',
                'User-Agent': 'Mozilla/5.0'
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                res_data = json.loads(response.read().decode('utf-8'))
                if 'Media' in res_data.get('data', {}):
                    return res_data['data']['Media']
                return res_data['data']['Page']['media']
        except Exception:
            return []

    @staticmethod
    def get_trending():
        query = """
        query {
          Page(perPage: 15) {
            media(sort: TRENDING_DESC, type: ANIME) {
              id
              title { romaji english }
              coverImage { extraLarge }
              description
              episodes
            }
          }
        }
        """
        result = AnimeAPI._fetch_graphql(query)
        if result:
            return result
        
        return [
            {
                "id": 1,
                "title": {"romaji": "One Piece", "english": "One Piece"},
                "coverImage": {"extraLarge": "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/nx21-rhAsR9GI0FuA.jpg"},
                "description": "Monkey D. Luffy explora os mares em busca do tesouro lendário.",
                "episodes": 1100
            }
        ]

    @staticmethod
    def search_anime(term: str):
        query = """
        query ($search: String) {
          Page(perPage: 15) {
            media(search: $search, type: ANIME) {
              id
              title { romaji english }
              coverImage { extraLarge }
              description
              episodes
            }
          }
        }
        """
        return AnimeAPI._fetch_graphql(query, variables={'search': term})

    @staticmethod
    def get_anime_details(anime_id: int):
        query = """
        query ($id: Int) {
          Media(id: $id, type: ANIME) {
            id
            title { romaji english }
            episodes
            streamingEpisodes {
              title
              url
              site
            }
          }
        }
        """
        url = "https://graphql.anilist.co"
        payload = {'query': query, 'variables': {'id': anime_id}}
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            url, data=data, headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                res_data = json.loads(response.read().decode('utf-8'))
                return res_data.get('data', {}).get('Media', {})
        except Exception:
            return {}
