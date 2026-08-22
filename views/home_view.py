import flet as ft
from core.local_scanner import LocalScanner
from core.metadata import MetadataManager
from core.history import HistoryManager

class HomeView:
    @staticmethod
    def build(page: ft.Page, on_select_anime):
        grid = ft.GridView(expand=True, runs_count=3, max_extent=130, child_aspect_ratio=0.7, spacing=10, run_spacing=10)
        loading = ft.ProgressRing(visible=True)

        all_animes = [] # Armazena todos os animes carregados
        only_favs = [False] # Filtro de favoritos ativo/inativo

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

                cover = anime_group.get('meta', {}).get('cover', '')
                card_content = ft.Image(src=cover, fit=ft.ImageFit.COVER, border_radius=8) if cover else ft.Container(bgcolor=ft.Colors.GREY_800, border_radius=8, alignment=ft.alignment.center, content=ft.Text(title, size=10, color=ft.Colors.WHITE, text_align=ft.TextAlign.CENTER))

                card = ft.GestureDetector(
                    on_tap=lambda _, a=anime_group: on_select_anime(a),
                    content=ft.Column([
                        ft.Container(content=card_content, height=150, border_radius=8),
                        ft.Text(title, size=11, weight=ft.FontWeight.BOLD, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, color=ft.Colors.WHITE)
                    ])
                )
                grid.controls.append(card)

            if not grid.controls:
                grid.controls.append(ft.Text("Nenhum anime encontrado.", color=ft.Colors.GREY_400))

            page.update()

        # Barra de Pesquisa
        search_bar = ft.TextField(
            hint_text="Buscar anime local...",
            border_radius=10,
            bgcolor=ft.Colors.GREY_900,
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

        top_bar = ft.Row([
            ft.Text("🍿 Rei-Flix", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_ACCENT),
            fav_btn
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        layout = ft.Column([
            top_bar,
            search_bar,
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

            all_animes = grouped
            loading.visible = False
            render_grid()

        page.run_thread(load_catalog)
        return ft.Container(content=layout, padding=15)
