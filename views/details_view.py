import flet as ft
from core.api import AnimeAPI

class DetailView:
    @staticmethod
    def build(page: ft.Page, anime: dict, on_back):
        title_data = anime.get('title', {})
        title = title_data.get('english') or title_data.get('romaji') or "Anime"
        cover = anime.get('coverImage', {}).get('extraLarge', '')
        anime_id = anime.get('id')
        
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
        
        episodes_list_view = ft.Column(spacing=8)
        loading_eps = ft.ProgressRing(visible=True)

        def load_episodes():
            details = AnimeAPI.get_anime_details(anime_id)
            streaming = details.get('streamingEpisodes', [])
            total_eps = details.get('episodes') or 0

            episodes_list_view.controls.clear()
            
            if streaming:
                for ep in streaming:
                    ep_title = ep.get('title', 'Episódio')
                    ep_url = ep.get('url', '')
                    episodes_list_view.controls.append(
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.PLAY_CIRCLE_FILL, color=ft.Colors.RED_ACCENT),
                            title=ft.Text(ep_title, color=ft.Colors.WHITE, size=14),
                            subtitle=ft.Text(f"Plataforma: {ep.get('site', 'Online')}", color=ft.Colors.GREY_400, size=12),
                            on_click=lambda _, u=ep_url: page.launch_url(u) if u else None
                        )
                    )
            elif total_eps > 0:
                # Se não houver links diretos de streaming na AniList, cria uma listagem genérica baseada na quantidade de episódios
                for i in range(1, min(total_eps + 1, 50)): # Limita a 50 para teste rápido
                    episodes_list_view.controls.append(
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.PLAY_ARROW, color=ft.Colors.RED_ACCENT),
                            title=ft.Text(f"Episódio {i}", color=ft.Colors.WHITE, size=14),
                            on_click=lambda _, num=i: page.snack_bar(ft.SnackBar(content=ft.Text(f"Reproduzindo Episódio {num}"))).open()
                        )
                    )
            else:
                episodes_list_view.controls.append(ft.Text("Nenhum episódio listado no momento.", color=ft.Colors.GREY_400))

            loading_eps.visible = False
            page.update()

        page.run_thread(load_episodes)

        top_section = ft.Row([
            poster, 
            ft.Column([
                ft.Text(title, size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_ACCENT),
                ft.Text(f"Episódios Totais: {anime.get('episodes', 'Desconhecido')}", size=13, color=ft.Colors.GREY_300)
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
            ft.Text("Lista de Episódios", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_ACCENT),
            loading_eps,
            episodes_list_view
        ], scroll=ft.ScrollMode.AUTO, expand=True)

        return ft.Container(content=layout, padding=15)
