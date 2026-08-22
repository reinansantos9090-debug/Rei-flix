import flet as ft
import re
from core.history import HistoryManager

class DetailView:
    @staticmethod
    def build(page: ft.Page, anime_data: dict, on_play_episode, on_back):
        title = anime_data.get('meta', {}).get('title_official') or anime_data.get('title')
        cover = anime_data.get('meta', {}).get('cover', '')
        desc = anime_data.get('meta', {}).get('description', 'Sem descrição.')
        clean_desc = re.sub('<[^<]+?>', '', desc)
        
        episodes = anime_data.get('episodes', [])
        folder_path = anime_data.get('folder_path', '')

        is_fav = HistoryManager.is_favorite(folder_path)

        def toggle_fav(e):
            nonlocal is_fav
            is_fav = HistoryManager.toggle_favorite(folder_path)
            fav_button.icon = ft.Icons.STAR if is_fav else ft.Icons.STAR_BORDER
            fav_button.icon_color = ft.Colors.YELLOW if is_fav else ft.Colors.WHITE
            page.update()

        back_button = ft.IconButton(icon=ft.Icons.ARROW_BACK, icon_color=ft.Colors.WHITE, on_click=lambda _: on_back())
        fav_button = ft.IconButton(
            icon=ft.Icons.STAR if is_fav else ft.Icons.STAR_BORDER,
            icon_color=ft.Colors.YELLOW if is_fav else ft.Colors.WHITE,
            on_click=toggle_fav
        )

        header = ft.Row([back_button, ft.Text("Detalhes", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE), fav_button], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        poster = ft.Image(src=cover, width=130, height=190, fit=ft.ImageFit.COVER, border_radius=8) if cover else ft.Container(width=130, height=190, bgcolor=ft.Colors.GREY_800, border_radius=8, content=ft.Icon(ft.Icons.MOVIE, size=50, color=ft.Colors.WHITE54))

        episodes_list = ft.Column(spacing=5)
        for ep in episodes:
            ep_title = ep.get('title', 'Episódio')
            ep_path = ep.get('path', '')
            
            # Verifica se ja tem progresso salvo
            pos = HistoryManager.get_position(ep_path)
            subtitle = "Assistido em parte" if pos > 0 else "Não assistido"

            episodes_list.controls.append(
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.PLAY_CIRCLE_FILL, color=ft.Colors.RED_ACCENT),
                    title=ft.Text(ep_title, color=ft.Colors.WHITE, size=14, weight=ft.FontWeight.BOLD),
                    subtitle=ft.Text(subtitle, color=ft.Colors.GREY_400, size=12),
                    on_click=lambda _, path=ep_path, t=ep_title: on_play_episode(path, t)
                )
            )

        layout = ft.Column([
            header,
            ft.Row([poster, ft.Column([ft.Text(title, size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_ACCENT), ft.Text(f"{len(episodes)} Episódios Locais", size=12, color=ft.Colors.GREEN_ACCENT)], expand=True)], spacing=15),
            ft.Divider(height=15, color=ft.Colors.TRANSPARENT),
            ft.Text("Sinopse", size=15, weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE_ACCENT),
            ft.Text(clean_desc, size=12, color=ft.Colors.GREY_300, max_lines=4, overflow=ft.TextOverflow.ELLIPSIS),
            ft.Divider(height=15, color=ft.Colors.TRANSPARENT),
            ft.Text("Episódios no Celular", size=15, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
            episodes_list
        ], scroll=ft.ScrollMode.AUTO, expand=True)

        return ft.Container(content=layout, padding=15)
