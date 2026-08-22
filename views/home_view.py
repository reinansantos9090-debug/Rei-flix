import flet as ft
from core.local_scanner import LocalScanner
from core.metadata import MetadataManager

class HomeView:
    @staticmethod
    def build(page: ft.Page, on_select_anime):
        grid = ft.GridView(expand=True, runs_count=3, max_extent=130, child_aspect_ratio=0.7, spacing=10, run_spacing=10)
        loading = ft.ProgressRing(visible=True)

        layout = ft.Column([
            ft.Text("🍿 Rei-Flix (Biblioteca Agrupada)", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_ACCENT),
            ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
            loading,
            grid
        ], expand=True)

        def load_catalog():
            grouped_animes = LocalScanner.get_local_animes_grouped()
            grid.controls.clear()

            if not grouped_animes:
                grid.controls.append(ft.Text("Nenhuma pasta de anime encontrada.", color=ft.Colors.GREY_400))
            else:
                for anime_group in grouped_animes:
                    meta = MetadataManager.fetch_anime_info(anime_group['main_title'])
                    anime_group['meta'] = meta

                    title = meta.get('title_official') or anime_group['main_title']
                    cover = meta.get('cover', '')

                    card_content = ft.Image(src=cover, fit=ft.ImageFit.COVER, border_radius=8) if cover else ft.Container(bgcolor=ft.Colors.GREY_800, border_radius=8, alignment=ft.alignment.center, content=ft.Text(title, size=10, color=ft.Colors.WHITE, text_align=ft.TextAlign.CENTER))

                    card = ft.GestureDetector(
                        on_tap=lambda _, a=anime_group: on_select_anime(a),
                        content=ft.Column([
                            ft.Container(content=card_content, height=150, border_radius=8),
                            ft.Text(title, size=11, weight=ft.FontWeight.BOLD, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, color=ft.Colors.WHITE)
                        ])
                    )
                    grid.controls.append(card)

            loading.visible = False
            page.update()

        page.run_thread(load_catalog)
        return ft.Container(content=layout, padding=15)
