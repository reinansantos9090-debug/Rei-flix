import flet as ft
from core.scraper import AnimeScraper

class PlayerView:
    @staticmethod
    def build(page: ft.Page, anime_title: str, on_back):
        # Busca a URL do vídeo no scraper
        video_url = AnimeScraper.get_episode_stream_url(anime_title)

        # Botão de Voltar
        back_button = ft.IconButton(
            icon=ft.Icons.ARROW_BACK,
            icon_color=ft.Colors.WHITE,
            on_click=lambda _: on_back()
        )

        title_text = ft.Text(f"Reproduzindo: {anime_title} - Ep. 1", size=16, weight=ft.FontWeight.BOLD)

        # Player de Vídeo Nativo do Flet
        video_player = ft.Video(
            playlist=[ft.VideoMedia(video_url)],
            playlist_mode=ft.PlaylistMode.LOOP,
            fill_color=ft.Colors.BLACK,
            aspect_ratio=16/9,
            autoplay=True,
            filter_quality=ft.FilterQuality.HIGH,
        )

        return ft.Column([
            ft.Row([back_button, title_text]),
            ft.Divider(),
            ft.Container(
                content=video_player,
                alignment=ft.alignment.center,
                border_radius=10,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS
            )
        ], expand=True)

