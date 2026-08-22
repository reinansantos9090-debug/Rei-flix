import flet as ft
from views.home_view import HomeView
from views.details_view import DetailsView

def main(page: ft.Page):
    page.title = "Rei-Flix"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 15
    page.scroll = ft.ScrollMode.AUTO

    content_area = ft.Container(expand=True)

    def show_home():
        content_area.content = HomeView.build(page, on_select_anime=show_details)
        page.update()

    def show_details(anime):
        content_area.content = DetailsView.build(page, anime, on_back=show_home)
        page.update()

    # Inicializa na Home
    show_home()

    page.add(
        ft.Row([
            ft.Text("🎌 Rei-Flix", size=24, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_ACCENT)
        ]),
        ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
        content_area
    )

ft.app(target=main)
