import flet as ft
import requests

def main(page: ft.Page):
    page.title = "Rei-flix"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 10

    # Título do App
    title = ft.Text("Rei-Flix Anime", size=24, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_ACCENT)

    # Campo de busca
    search_input = ft.TextField(
        hint_text="Buscar animes...",
        expand=True,
        border_radius=10
    )

    results_grid = ft.GridView(
        expand=True,
        runs_count=3,
        max_extent=160,
        child_aspect_ratio=0.7,
        spacing=10,
        run_spacing=10,
    )

    def search_anime(e):
        query = search_input.value
        if not query:
            return
        
        results_grid.controls.clear()
        page.update()

        # Consumindo API pública do AniList para buscar animes
        url = "https://graphql.anilist.co"
        graphql_query = """
        query ($search: String) {
          Page(perPage: 12) {
            media(search: $search, type: ANIME) {
              id
              title { romaji english }
              coverImage { large }
            }
          }
        }
        """
        response = requests.post(url, json={'query': graphql_query, 'variables': {'search': query}})
        
        if response.status_code == 200:
            data = response.json()
            animes = data['data']['Page']['media']
            for anime in animes:
                title_text = anime['title']['romaji'] or anime['title']['english']
                cover_url = anime['coverImage']['large']
                
                card = ft.Card(
                    content=ft.Container(
                        content=ft.Column([
                            ft.Image(src=cover_url, fit=ft.ImageFit.COVER, height=140, border_radius=8),
                            ft.Text(title_text, size=12, weight=ft.FontWeight.BOLD, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS)
                        ], alignment=ft.MainAxisAlignment.START),
                        padding=5
                    )
                )
                results_grid.controls.append(card)
        page.update()

    search_button = ft.IconButton(
        icon=ft.Icons.SEARCH,
        on_click=search_anime,
        icon_color=ft.Colors.WHITE
    )

    page.add(
        title,
        ft.Row([search_input, search_button]),
        ft.Divider(),
        results_grid
    )

ft.app(target=main)
