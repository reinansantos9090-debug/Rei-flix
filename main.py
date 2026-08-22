import flet as ft
import requests

def main(page: ft.Page):
    page.title = "OtakuHub Python"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 20

    search_input = ft.TextField(
        hint_text="Digite o nome do anime...",
        expand=True,
        autofocus=True
    )
    
    results_list = ft.ListView(expand=True, spacing=10)
    loading_indicator = ft.ProgressRing(visible=False)

    def search_anime(e):
        query = search_input.value.strip()
        if not query:
            return

        loading_indicator.visible = True
        results_list.controls.clear()
        page.update()

        graphql_query = '''
        query ($search: String) {
          Page(perPage: 10) {
            media(search: $search, type: ANIME) {
              id
              title { romaji english }
              coverImage { large }
              episodes
              status
            }
          }
        }
        '''
        
        try:
            response = requests.post(
                'https://graphql.anilist.co',
                json={'query': graphql_query, 'variables': {'search': query}},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                media_list = data['data']['Page']['media']

                for anime in media_list:
                    title = anime['title']['english'] or anime['title']['romaji']
                    img_url = anime['coverImage']['large']
                    episodes = anime['episodes'] or '?'
                    status = anime['status']

                    card = ft.Card(
                        content=ft.ListTile(
                            leading=ft.Image(src=img_url, width=50, fit=ft.ImageFit.COVER),
                            title=ft.Text(title, weight=ft.FontWeight.BOLD),
                            subtitle=ft.Text(f"Episódios: {episodes} | Status: {status}")
                        )
                    )
                    results_list.controls.append(card)
            else:
                results_list.controls.append(ft.Text("Erro ao buscar dados."))
        except Exception as err:
            results_list.controls.append(ft.Text(f"Erro de conexão: {err}"))
        finally:
            loading_indicator.visible = False
            page.update()

    search_button = ft.IconButton(
        icon=ft.icons.SEARCH,
        icon_color=ft.colors.PURPLE_ACCENT,
        on_pressed=search_anime
    )

    page.add(
        ft.Text("🎌 OtakuHub Python", size=24, weight=ft.FontWeight.BOLD, color=ft.colors.PURPLE_200),
        ft.Row([search_input, search_button]),
        loading_indicator,
        results_list
    )

ft.app(target=main)

