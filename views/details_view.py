import flet as ft
import re
from core.history import HistoryManager

class DetailView:
    @staticmethod
    def build(page: ft.Page, anime_group: dict, on_play_episode, on_back):
        main_title = anime_group.get('meta', {}).get('title_official') or anime_group.get('main_title')
        cover = anime_group.get('meta', {}).get('cover', '')
        desc = anime_group.get('meta', {}).get('description', 'Sem descrição.')
        clean_desc = re.sub('<[^<]+?>', '', desc)

        seasons = anime_group.get('seasons', [])
        current_season_idx = [0]

        episodes_column = ft.Column(spacing=8)

        def update_episodes_list():
            episodes_column.controls.clear()
            active_season = seasons[current_season_idx[0]]
            
            for ep in active_season.get('episodes', []):
                ep_title = ep.get('title', 'Episódio')
                ep_path = ep.get('path', '')
                
                # Dados de progresso
                prog = HistoryManager.get_progress_data(ep_path)
                
                # Ícone de status (Verde se concluído, Vermelho se em andamento)
                if prog["completed"]:
                    leading_icon = ft.Icon(ft.Icons.CHECK_CIRCLE, color=ft.Colors.GREEN_ACCENT, size=24)
                    status_text = "Concluído"
                elif prog["ratio"] > 0:
                    leading_icon = ft.Icon(ft.Icons.PLAY_CIRCLE_FILL, color=ft.Colors.RED_ACCENT, size=24)
                    status_text = f"Em andamento ({int(prog['ratio'] * 100)}%)"
                else:
                    leading_icon = ft.Icon(ft.Icons.PLAY_CIRCLE_OUTLINE, color=ft.Colors.GREY_500, size=24)
                    status_text = "Não assistido"

                # Barra de progresso visual
                progress_bar = ft.ProgressBar(
                    value=prog["ratio"],
                    color=ft.Colors.RED_ACCENT,
                    bgcolor=ft.Colors.GREY_800,
                    height=3
                ) if prog["ratio"] > 0 else ft.Container()

                item_content = ft.Column([
                    ft.Row([
                        leading_icon,
                        ft.Column([
                            ft.Text(ep_title, color=ft.Colors.WHITE, size=13, weight=ft.FontWeight.BOLD),
                            ft.Text(status_text, color=ft.Colors.GREY_400, size=11)
                        ], expand=True)
                    ], alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    progress_bar
                ], spacing=4)

                episodes_column.controls.append(
                    ft.Container(
                        content=item_content,
                        padding=10,
                        border_radius=8,
                        bgcolor=ft.Colors.GREY_900,
                        on_click=lambda _, path=ep_path, t=ep_title: on_play_episode(path, t)
                    )
                )
            page.update()

        def on_season_change(e):
            current_season_idx[0] = int(e.control.value)
            update_episodes_list()

        season_options = [ft.dropdown.Option(key=str(i), text=s['season_name']) for i, s in enumerate(seasons)]
        season_dropdown = ft.Dropdown(
            value="0",
            options=season_options,
            on_change=on_season_change,
            border_color=ft.Colors.RED_ACCENT,
            color=ft.Colors.WHITE,
            text_size=13
        ) if len(seasons) > 1 else ft.Container()

        back_button = ft.IconButton(icon=ft.Icons.ARROW_BACK, icon_color=ft.Colors.WHITE, on_click=lambda _: on_back())
        header = ft.Row([back_button, ft.Text("Detalhes", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE)], alignment=ft.MainAxisAlignment.START)

        poster = ft.Image(src=cover, width=130, height=190, fit=ft.ImageFit.COVER, border_radius=8) if cover else ft.Container(width=130, height=190, bgcolor=ft.Colors.GREY_800, border_radius=8)

        layout = ft.Column([
            header,
            ft.Row([poster, ft.Column([
                ft.Text(main_title, size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_ACCENT),
                ft.Text(f"{len(seasons)} Temporada(s)", size=12, color=ft.Colors.GREEN_ACCENT)
            ], expand=True)], spacing=15),
            ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
            ft.Text("Sinopse", size=15, weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE_ACCENT),
            ft.Text(clean_desc, size=12, color=ft.Colors.GREY_300, max_lines=3, overflow=ft.TextOverflow.ELLIPSIS),
            ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
            season_dropdown,
            ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
            episodes_column
        ], scroll=ft.ScrollMode.AUTO, expand=True)

        update_episodes_list()
        return ft.Container(content=layout, padding=15)
