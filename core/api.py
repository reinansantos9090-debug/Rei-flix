import json
import urllib.request

class AnimeAPI:
    @staticmethod
    def get_trending():
        url = "https://graphql.anilist.co"
        query = """
        query {
          Page(perPage: 15) {
            media(sort: TRENDING_DESC, type: ANIME) {
              id
              title { romaji english }
              coverImage { extraLarge }
              description
            }
          }
        }
        """
        data = json.dumps({'query': query}).encode('utf-8')
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
                return res_data['data']['Page']['media']
        except Exception as e:
            # Dados de demonstração/fallback caso o celular esteja sem rede
            return [
                {
                    "id": 1,
                    "title": {"romaji": "One Piece", "english": "One Piece"},
                    "coverImage": {"extraLarge": "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/nx21-rhAsR9GI0FuA.jpg"},
                    "description": "Monkey D. Luffy explora os mares em busca do tesouro lendário."
                },
                {
                    "id": 2,
                    "title": {"romaji": "Jujutsu Kaisen", "english": "Jujutsu Kaisen"},
                    "coverImage": {"extraLarge": "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/bx113415-bbBWL4qK233z.png"},
                    "description": "Estudantes enfrentam maldições no mundo das feitiçarias."
                }
            ]
