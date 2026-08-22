import flet as ft
from views.home_view import HomeView

def main(page: ft.Page):
    page.title = "Rei-Flix"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 15
    page.scroll = ft.ScrollMode.AUTO

    # Barra Superior
    app_bar = ft.Row(
        controls=[
            ft.Text("🎌 Rei-Flix", size=24, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_ACCENT),
            ft.IconButton(icon=ft.Icons.SEARCH, icon_color=ft.Colors.WHITE)
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN
    )

    # Carrega a Tela Inicial
    home_content = HomeView.build(page)

    page.add(
        app_bar,
        ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
        home_content
    )

ft.app(target=main)
