import flet as ft
from providers.anime_provider import AnimeProvider

class DetailView:
    @staticmethod
    def build(page: ft.Page, anime: dict, on_play_video, on_back):
        title_data = anime.get('title', {}) if isinstance(anime, dict) else {}
        title = title_data.get('english') or title_data.get('romaji') or "Anime"
        cover = anime.get('coverImage', {}).get('extraLarge', '') if isinstance(anime, dict) else ''
        
        raw_desc = anime.get('description', 'Sem descrição disponível.') or 'Sem descrição disponível.'
        import re
        clean_desc = re.sub('<[^<]+?>', '', raw_desc)

        back_button = ft.IconButton(
            icon=ft.Icons.ARROW_BACK,
            icon_color=ft.Colors.WHITE,
            on_click=lambda _: on_back()
        )

        header = ft.Row([
            back_button,
            ft.Text("Detalhes do Anime", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE)
        ], alignment=ft.MainAxisAlignment.START)

        poster = ft.Image(src=cover, width=140, height=200, fit=ft.ImageFit.COVER, border_radius=12)
        episodes_column = ft.Column(spacing=8)
        loading_eps = ft.ProgressRing(visible=True)

        def fetch_episodes():
            # Busca os episódios no provedor raspador
            episodes = AnimeProvider.search_and_get_episodes(title)
            loading_eps.visible = False
            episodes_column.controls.clear()

            if episodes:
                for ep in episodes:
                    ep_title = ep.get('title', 'Episódio')
                    ep_url = ep.get('url', '')
                    episodes_column.controls.append(
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.PLAY_CIRCLE_FILL, color=ft.Colors.RED_ACCENT),
                            title=ft.Text(ep_title, color=ft.Colors.WHITE, size=14),
                            on_click=lambda _, url=ep_url, t=ep_title: on_play_video(url, t)
                        )
                    )
            else:
                episodes_column.controls.append(
                    ft.Text("Nenhum episódio encontrado no provedor no momento.", color=ft.Colors.GREY_400)
                )
            page.update()

        top_section = ft.Row([
            poster, 
            ft.Column([
                ft.Text(title, size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_ACCENT),
                ft.Text("Status: Online", size=13, color=ft.Colors.GREEN_ACCENT)
            ], expand=True, alignment=ft.MainAxisAlignment.CENTER)
        ], spacing=15, vertical_alignment=ft.CrossAxisAlignment.START)

        layout = ft.Column([
            header,
            ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
            top_section,
            ft.Divider(height=15, color=ft.Colors.TRANSPARENT),
            ft.Text("Sinopse", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE_ACCENT),
            ft.Text(clean_desc, size=13, color=ft.Colors.GREY_300),
            ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
            ft.Text("Episódios Disponíveis", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_ACCENT),
            loading_eps,
            episodes_column
        ], scroll=ft.ScrollMode.AUTO, expand=True)

        # Executa a busca dos episódios ao abrir a tela
        fetch_episodes()

        return ft.Container(content=layout, padding=15)

