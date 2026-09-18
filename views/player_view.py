import flet as ft
from core.history import HistoryManager

class PlayerView:
    @staticmethod
    def build(page: ft.Page, video_path: str, ep_title: str, on_back, on_next_episode=None):
        prog = HistoryManager.get_progress_data(video_path)

        def save_and_exit(go_to_next=False):
            try:
                current_pos = video_player.get_current_position()
                duration = video_player.get_duration()
                
                pos_sec = current_pos.total_seconds() if current_pos else 0
                dur_sec = duration.total_seconds() if duration else 0

                if pos_sec > 0:
                    HistoryManager.save_position(video_path, pos_sec, dur_sec)
            except Exception:
                pass

            if go_to_next and on_next_episode:
                on_next_episode()
            else:
                on_back()

        back_button = ft.IconButton(
            icon=ft.Icons.ARROW_BACK,
            icon_color=ft.Colors.WHITE,
            on_click=lambda _: save_and_exit(go_to_next=False)
        )

        next_button = ft.IconButton(
            icon=ft.Icons.SKIP_NEXT,
            icon_color=ft.Colors.WHITE,
            tooltip="Próximo Episódio",
            on_click=lambda _: save_and_exit(go_to_next=True)
        ) if on_next_episode else ft.Container()

        header = ft.Row([
            ft.Row([back_button, ft.Column([ft.Text(ep_title, size=15, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                                              ft.Text("Reprodução local", size=11, color="#9DA3B4")], spacing=1)]),
            next_button
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        # O controle Video foi removido do pacote Flet 0.86. O botão abaixo usa
        # o resolvedor nativo do Android para abrir o mesmo arquivo local; não
        # há URL de streaming ou provedor externo envolvido.
        def open_local_player(_):
            try:
                page.launch_url(f"file://{video_path}")
            except Exception:
                page.snack_bar = ft.SnackBar(ft.Text("Não foi possível abrir este arquivo local."))
                page.snack_bar.open = True
                page.update()

        video_player = ft.Container(
            bgcolor=ft.Colors.BLACK,
            alignment=ft.alignment.center,
            content=ft.Column([
                ft.Icon(ft.Icons.PLAY_CIRCLE_OUTLINE, color=ft.Colors.WHITE, size=64),
                ft.Text("Abrir no player local do dispositivo", color=ft.Colors.WHITE),
                ft.FilledButton("Reproduzir arquivo local", icon=ft.Icons.PLAY_ARROW, on_click=open_local_player),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, tight=True),
        )

        layout = ft.Column([
            header,
            ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
            ft.Container(
                content=video_player,
                alignment=ft.alignment.center,
                bgcolor=ft.Colors.BLACK,
                expand=True
            )
        ], expand=True)

        return ft.Container(content=layout, padding=12, bgcolor="#0E0D13")
