import flet as ft
import os

def main(page: ft.Page):
    page.title = "Rei-Flix Local"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = ft.Colors.BLACK
    
    # Caminho padrao da pasta de animes no Android
    ANIME_DIR = "/storage/emulated/0/Download/Animes"
    
    if not os.path.exists(ANIME_DIR):
        page.add(ft.Text(f"Pasta não encontrada: {ANIME_DIR}", color=ft.Colors.RED_ACCENT))
    else:
        folders = os.listdir(ANIME_DIR)
        page.add(ft.Text(f"Animes encontrados no celular: {len(folders)}", color=ft.Colors.GREEN_ACCENT))

ft.app(target=main)
