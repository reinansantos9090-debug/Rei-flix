import flet as ft

class DetailsView:
    @staticmethod
    def build(page: ft.Page, anime: dict, on_back):
        title = anime.get('title', {}).get('english') or anime.get('title', {}).get('romaji') or "Detalhes"
        cover = anime.get('coverImage', {}).get('extraLarge', '')
        description = anime.get('description', 'Sem sinopse disponível.').replace('<br>', '\n').replace('<i>', '').replace('</i>', '')

        # Botão de Voltar
        back_button = ft.IconButton(
            icon=ft.Icons.ARROW_BACK,
            icon_color=ft.Colors.WHITE,
            on_click=lambda _: on_back()
        )

        # Capa e Título
        header = ft.Row([
            ft.Image(src=cover, width=120, height=170, fit=ft.ImageFit.COVER, border_radius=8),
            ft.Column([
                ft.Text(title, size=18, weight=ft.FontWeight.BOLD, max_lines=3, overflow=ft.TextOverflow.ELLIPSIS, width=200),
                ft.ElevatedButton("▶ Assistir Ep. 1", bgcolor=ft.Colors.RED_600, color=ft.Colors.WHITE)
            ], spacing=10)
        ], spacing=15)

        # Sinopse
        synopsis = ft.Column([
            ft.Text("Sinopse", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE_ACCENT),
            ft.Text(description, size=13, color=ft.Colors.WHITE_70, max_lines=6, overflow=ft.TextOverflow.ELLIPSIS)
        ], spacing=5)

        return ft.Column([
            back_button,
            header,
            ft.Divider(height=20),
            synopsis
        ], expand=True)

