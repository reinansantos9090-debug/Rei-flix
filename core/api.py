import requests

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
              bannerImage
              description
            }
          }
        }
        """
        try:
            res = requests.post(url, json={'query': query})
            return res.json()['data']['Page']['media']
        except Exception:
            return []

