import flet as ft
from views.home_view import HomeView
from views.detail_view import DetailView

def main(page: ft.Page):
    page.title = "Rei-Flix"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = ft.Colors.BLACK
    page.padding = 0

    def navigate_to_details(anime):
        page.clean()
        detail_ui = DetailView.build(page, anime, on_back=navigate_to_home)
        page.add(detail_ui)
        page.update()

    def navigate_to_home():
        page.clean()
        home_ui = HomeView.build(page, on_select_anime=navigate_to_details)
        page.add(home_ui)
        page.update()

    # Inicializa o app na Home
    navigate_to_home()

ft.app(target=main)
