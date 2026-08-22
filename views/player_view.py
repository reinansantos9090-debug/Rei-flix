import flet as ft

class PlayerView:
    @staticmethod
    def build(page: ft.Page, video_url: str, ep_title: str, on_back):
        back_button = ft.IconButton(
            icon=ft.Icons.ARROW_BACK,
            icon_color=ft.Colors.WHITE,
            on_click=lambda _: on_back()
        )

        header = ft.Row([
            back_button,
            ft.Text(ep_title, size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE)
        ], alignment=ft.MainAxisAlignment.START)

        # Componente Nativo do Flet para Reprodução de Vídeo
        video_player = ft.Video(
            playlist=[ft.VideoMedia(video_url)],
            playlist_mode=ft.PlaylistMode.LOOP,
            fill_color=ft.Colors.BLACK,
            aspect_ratio=16/9,
            autoplay=True,
            filter_quality=ft.FilterQuality.HIGH,
        )

        layout = ft.Column([
            header,
            ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
            ft.Container(
                content=video_player,
                alignment=ft.alignment.center,
                bgcolor=ft.Colors.BLACK,
                expand=True
            )
        ], expand=True)

        return ft.Container(content=layout, padding=10, bgcolor=ft.Colors.BLACK)
