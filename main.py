import flet as ft
from views.home_view import HomeView
from views.details_view import DetailView
from views.player_view import PlayerView
from providers.anime_provider import AnimeProvider

def main(page: ft.Page):
    page.title = "Rei-Flix"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = ft.Colors.BLACK
    page.padding = 0

    current_anime = [None] # Armazena o anime selecionado

    def play_episode_video(ep_page_url, ep_title):
        # Extrai a URL direta de mídia (.mp4) via scraper
        video_url = AnimeProvider.get_video_stream_url(ep_page_url)
        if video_url:
            page.clean()
            player_ui = PlayerView.build(
                page, 
                video_url=video_url, 
                ep_title=ep_title, 
                on_back=lambda: navigate_to_details(current_anime[0])
            )
            page.add(player_ui)
            page.update()
        else:
            page.snack_bar = ft.SnackBar(content=ft.Text("Não foi possível extrair o vídeo deste episódio."))
            page.snack_bar.open = True
            page.update()

    def navigate_to_details(anime):
        current_anime[0] = anime
        page.clean()
        detail_ui = DetailView.build(
            page, 
            anime=anime, 
            on_play_video=play_episode_video, 
            on_back=navigate_to_home
        )
        page.add(detail_ui)
        page.update()

    def navigate_to_home():
        page.clean()
        home_ui = HomeView.build(page, on_select_anime=navigate_to_details)
        page.add(home_ui)
        page.update()

    navigate_to_home()

ft.app(target=main)
