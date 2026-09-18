import urllib.request
import json

class MetadataManager:
    @staticmethod
    def fetch_anime_info(folder_name: str) -> dict:
        """Busca a capa e sinopse no AniList com base no nome da pasta do celular"""
        query = '''
        query ($search: String) {
          Media (search: $search, type: ANIME) {
            id
            title {
              romaji
              english
            }
            coverImage {
              extraLarge
            }
            description
          }
        }
        '''
        
        # Limpa palavras comuns que podem atrapalhar a busca
        clean_title = folder_name.replace("Dublado", "").replace("Season", "").strip()
        
        variables = {'search': clean_title}
        url = 'https://graphql.anilist.co'
        
        data = json.dumps({'query': query, 'variables': variables}).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0'
        })

        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                result = json.loads(response.read().decode('utf-8'))
                media = result.get('data', {}).get('Media', {})
                if media:
                    return {
                        'cover': media.get('coverImage', {}).get('extraLarge', ''),
                        'description': media.get('description', 'Sem sinopse disponível.'),
                        # O nome da pasta continua sendo a fonte de verdade. A rede é
                        # usada somente para complementar a capa e a sinopse.
                        'title_official': folder_name
                    }
        except Exception:
            pass

        # Retorno padronizado caso esteja sem internet ou não encontre o anime
        return {
            'cover': '',
            'description': 'Anime armazenado localmente.',
            'title_official': folder_name
        }
