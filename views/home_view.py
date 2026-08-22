import flet as ft
from core.api import AnimeAPI

class HomeView:
    @staticmethod
    def build(page: ft.Page, on_select_anime):
        # Listas para cada categoria
        trending_list = ft.Row(scroll=ft.ScrollMode.ALWAYS, spacing=12)
        watching_list = ft.Row(scroll=ft.ScrollMode.ALWAYS, spacing=12)
        favorites_list = ft.Row(scroll=ft.ScrollMode.ALWAYS, spacing=12)
        search_results_grid = ft.Row(scroll=ft.ScrollMode.ALWAYS, spacing=12)
        
        loading_trending = ft.ProgressRing(visible=True)
        loading_search = ft.ProgressRing(visible=False)
        
        # Containers das seções
        section_search_container = ft.Column([
            ft.Text("🔍 Resultados da Busca", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_ACCENT),
            loading_search,
            search_results_grid,
            ft.Divider(height=20, color=ft.Colors.TRANSPARENT)
        ], visible=False)

        def create_card(anime):
            title_data = anime.get('title', {})
            title = title_data.get('english') or title_data.get('romaji') or "Anime"
            cover = anime.get('coverImage', {}).get('extraLarge', '')
            
            return ft.GestureDetector(
                on_tap=lambda _, a=anime: on_select_anime(a),
                content=ft.Container(
                    content=ft.Column([
                        ft.Image(src=cover, width=130, height=180, fit=ft.ImageFit.COVER, border_radius=8),
                        ft.Text(title, size=12, weight=ft.FontWeight.BOLD, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS, width=130)
                    ]),
                    padding=5
                )
            )

        def fetch_data():
            # Carrega animes em alta da API Online
            animes = AnimeAPI.get_trending()
            trending_list.controls.clear()
            watching_list.controls.clear()
            favorites_list.controls.clear()

            if animes:
                for i, anime in enumerate(animes):
                    card = create_card(anime)
                    trending_list.controls.append(card)
                    # Simulando categorias para demonstração inicial com dados online
                    if i % 2 == 0:
                        watching_list.controls.append(create_card(anime))
                    else:
                        favorites_list.controls.append(create_card(anime))
            else:
                trending_list.controls.append(ft.Text("Erro ao carregar animes.", color=ft.Colors.RED))

            loading_trending.visible = False
            page.update()

        def do_search(e):
            search_term = search_input.value.strip()
            if not search_term:
                section_search_container.visible = False
                page.update()
                return

            section_search_container.visible = True
            loading_search.visible = True
            search_results_grid.controls.clear()
            page.update()

            def fetch_search():
                results = AnimeAPI.search_anime(search_term)
                search_results_grid.controls.clear()
                if results:
                    for anime in results:
                        search_results_grid.controls.append(create_card(anime))
                else:
                    search_results_grid.controls.append(ft.Text("Nenhum anime encontrado.", color=ft.Colors.GREY_400))
                loading_search.visible = False
                page.update()

            page.run_thread(fetch_search)

        # Barra de Pesquisa Superior
        search_input = ft.TextField(
            hint_text="Buscar anime online (ex: Naruto, One Piece)...",
            expand=True,
            on_submit=do_search,
            border_color=ft.Colors.RED_ACCENT,
            text_size=14
        )
        search_button = ft.IconButton(
            icon=ft.Icons.SEARCH,
            icon_color=ft.Colors.RED_ACCENT,
            on_click=do_search
        )
        search_bar = ft.Row([search_input, search_button], spacing=5)

        # Layout Principal com as Categorias Organizadas
        container_layout = ft.Column([
            search_bar,
            ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
            section_search_container,
            
            # Categoria 1: Assistindo
            ft.Text("📺 Assistindo", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_ACCENT),
            watching_list,
            ft.Divider(height=15, color=ft.Colors.TRANSPARENT),

            # Categoria 2: Em Alta (Online AniList)
            ft.Text("🔥 Animes em Alta", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE_ACCENT),
            loading_trending,
            trending_list,
            ft.Divider(height=15, color=ft.Colors.TRANSPARENT),

            # Categoria 3: Favoritos
            ft.Text("⭐ Favoritos", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.YELLOW_ACCENT),
            favorites_list,
        ], scroll=ft.ScrollMode.AUTO, expand=True)

        page.run_thread(fetch_data)
        return ft.Container(content=container_layout, padding=15)
