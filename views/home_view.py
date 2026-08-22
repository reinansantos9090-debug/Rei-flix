import flet as ft
from core.api import AnimeAPI

class HomeView:
    @staticmethod
    def build(page: ft.Page):
        trending_list = ft.Row(scroll=ft.ScrollMode.ALWAYS, spacing=12)
        loading = ft.ProgressRing(visible=True)

        container_layout = ft.Column([
            ft.Text("🔥 Animes em Alta", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE_ACCENT),
            loading,
            trending_list
        ], expand=True)

        def fetch_data():
            animes = AnimeAPI.get_trending()
            trending_list.controls.clear()
            
            if animes:
                for anime in animes:
                    title_data = anime.get('title', {})
                    title = title_data.get('english') or title_data.get('romaji') or "Anime"
                    cover = anime.get('coverImage', {}).get('extraLarge', '')
                    
                    card = ft.Container(
                        content=ft.Column([
                            ft.Image(src=cover, width=130, height=180, fit=ft.ImageFit.COVER, border_radius=8),
                            ft.Text(title, size=12, weight=ft.FontWeight.BOLD, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS, width=130)
                        ]),
                        padding=5
                    )
                    trending_list.controls.append(card)
            else:
                trending_list.controls.append(ft.Text("Erro ao carregar animes. Verifique a conexão.", color=ft.Colors.RED))

            loading.visible = False
            page.update()

        # Executa a busca assim que a tela monta no app
        page.run_thread(fetch_data)

        return container_layout
