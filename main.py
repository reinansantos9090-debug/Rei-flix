import flet as ft
from views.home_view import HomeView
from views.details_view import DetailView
from views.player_view import PlayerView

def main(page: ft.Page):
    page.title = "Rei-Flix Local"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = ft.Colors.BLACK
    page.padding = 0

    current_anime = [None]

    def play_episode(video_path, ep_title):
        page.clean()
        player_ui = PlayerView.build(
            page, 
            video_path=video_path, 
            ep_title=ep_title, 
            on_back=lambda: navigate_to_details(current_anime[0])
        )
        page.add(player_ui)
        page.update()

    def navigate_to_details(anime):
        current_anime[0] = anime
        page.clean()
        detail_ui = DetailView.build(
            page, 
            anime_data=anime, 
            on_play_episode=play_episode, 
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
