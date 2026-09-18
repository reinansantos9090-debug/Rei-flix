import flet as ft
from core.scraper import LocalScanner
from core.metadata import MetadataManager
from core.history import HistoryManager
from core.genre_classifier import GenreClassifier

class HomeView:
    @staticmethod
    def build(page: ft.Page, on_select_anime):
        grid = ft.GridView(expand=True, runs_count=3, max_extent=150, child_aspect_ratio=0.62, spacing=14, run_spacing=18)
        loading = ft.ProgressRing(visible=True)

        all_animes = [] # Armazena todos os animes carregados
        only_favs = [False] # Filtro de favoritos ativo/inativo
        active_genre = ["Todos"]

        def render_grid(filter_text=""):
            grid.controls.clear()
            
            search_query = filter_text.strip().lower()

            for anime_group in all_animes:
                title = anime_group.get('meta', {}).get('title_official') or anime_group['main_title']
                folder_path = anime_group.get('seasons', [{}])[0].get('folder_path', '')
                
                # Aplica o filtro de busca por texto
                if search_query and search_query not in title.lower() and search_query not in anime_group['main_title'].lower():
                    continue

                # Aplica o filtro de favoritos
                if only_favs[0] and not HistoryManager.is_favorite(folder_path):
                    continue

                if active_genre[0] != "Todos" and active_genre[0] not in anime_group.get("genres", []):
                    continue

                cover = anime_group.get('meta', {}).get('cover', '')
                card_content = ft.Image(src=cover, fit=ft.ImageFit.COVER, border_radius=12) if cover else ft.Container(bgcolor="#252836", border_radius=12, alignment=ft.alignment.center, content=ft.Icon(ft.Icons.MOVIE_OUTLINED, color="#9DA3B4", size=32))

                card = ft.GestureDetector(
                    on_tap=lambda _, a=anime_group: on_select_anime(a),
                    content=ft.Column([
                        ft.Stack([ft.Container(content=card_content, height=205, border_radius=12),
                                  ft.Container(content=ft.Icon(ft.Icons.PLAY_CIRCLE_FILL, color="#FFFFFF", size=34), right=8, bottom=8)]),
                        ft.Text(title, size=12, weight=ft.FontWeight.BOLD, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, color="#F5F5F7"),
                        ft.Text(" • ".join(anime_group.get("genres", ["Local"])[:2]), size=10, color="#9DA3B4", max_lines=1)
                    ], spacing=5)
                )
                grid.controls.append(card)

            if not grid.controls:
                grid.controls.append(ft.Text("Nada encontrado na sua biblioteca local.", color="#9DA3B4"))

            page.update()

        # Barra de Pesquisa
        search_bar = ft.TextField(
            hint_text="Pesquisar na biblioteca",
            prefix_icon=ft.Icons.SEARCH,
            border_radius=14,
            bgcolor="#252836",
            color=ft.Colors.WHITE,
            content_padding=10,
            text_size=13,
            on_change=lambda e: render_grid(e.control.value)
        )

        def toggle_fav_filter(e):
            only_favs[0] = not only_favs[0]
            fav_btn.icon_color = ft.Colors.YELLOW if only_favs[0] else ft.Colors.WHITE
            render_grid(search_bar.value or "")

        fav_btn = ft.IconButton(
            icon=ft.Icons.STAR,
            icon_color=ft.Colors.WHITE,
            tooltip="Apenas Favoritos",
            on_click=toggle_fav_filter
        )

        genres_row = ft.Row(scroll=ft.ScrollMode.AUTO, spacing=8)

        def render_genres():
            genres_row.controls.clear()
            genres = ["Todos"] + sorted({genre for anime in all_animes for genre in anime.get("genres", [])})
            for genre in genres:
                selected = genre == active_genre[0]
                genres_row.controls.append(ft.OutlinedButton(
                    genre, on_click=lambda _, g=genre: select_genre(g),
                    style=ft.ButtonStyle(color="#FFFFFF", bgcolor="#E50914" if selected else "#252836",
                                         shape=ft.RoundedRectangleBorder(radius=18), padding=ft.padding.symmetric(horizontal=16))))

        def select_genre(genre):
            active_genre[0] = genre
            render_genres()
            render_grid(search_bar.value or "")

        top_bar = ft.Row([
            ft.Row([ft.Icon(ft.Icons.PLAY_CIRCLE_FILLED, color="#E50914", size=30), ft.Text("ReiFlix", size=22, weight=ft.FontWeight.BOLD, color="#F5F5F7")]),
            ft.Row([fav_btn, ft.IconButton(icon=ft.Icons.REFRESH, icon_color="#FFFFFF", tooltip="Atualizar biblioteca", on_click=lambda _: load_catalog())])
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        layout = ft.Column([
            top_bar,
            ft.Text("Sua biblioteca, do seu jeito", size=13, color="#9DA3B4"),
            search_bar,
            genres_row,
            ft.Text("TODOS OS TÍTULOS", size=12, weight=ft.FontWeight.BOLD, color="#9DA3B4"),
            ft.Divider(height=5, color=ft.Colors.TRANSPARENT),
            loading,
            grid
        ], expand=True)

        def load_catalog():
            nonlocal all_animes
            grouped = LocalScanner.get_local_animes_grouped()
            
            for anime_group in grouped:
                meta = MetadataManager.fetch_anime_info(anime_group['main_title'])
                anime_group['meta'] = meta
                anime_group['genres'] = GenreClassifier.classify(anime_group['main_title'])

            all_animes = grouped
            loading.visible = False
            render_genres()
            render_grid()

        page.run_thread(load_catalog)
        return ft.Container(content=layout, padding=ft.padding.only(left=16, right=16, top=18, bottom=12), bgcolor="#16151F")
