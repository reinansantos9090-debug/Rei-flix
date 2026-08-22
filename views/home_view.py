import flet as ft
from core.api import AnimeAPI

class HomeView:
    @staticmethod
    def build(page: ft.Page):
        trending_list = ft.Row(scroll=ft.ScrollMode.ALWAYS, spacing=12)
        loading = ft.ProgressRing()

        def load_data():
            animes = AnimeAPI.get_trending()
            trending_list.controls.clear()
            
            for anime in animes:
                title = anime['title']['english'] or anime['title']['romaji']
                cover = anime['coverImage']['extraLarge']
                
                card = ft.Container(
                    content=ft.Column([
                        ft.Image(src=cover, width=130, height=180, fit=ft.ImageFit.COVER, border_radius=8),
                        ft.Text(title, size=12, weight=ft.FontWeight.BOLD, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS, width=130)
                    ]),
                    padding=5
                )
                trending_list.controls.append(card)
            
            loading.visible = False
            page.update()

        # Chama o carregamento dos animes
        load_data()

        return ft.Column([
            ft.Text("🔥 Animes em Alta", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE_ACCENT),
            loading,
            trending_list
        ], expand=True)

