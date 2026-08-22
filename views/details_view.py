import flet as ft

class DetailView:
    @staticmethod
    def build(page: ft.Page, anime: dict, on_back):
        title_data = anime.get('title', {})
        title = title_data.get('english') or title_data.get('romaji') or "Anime"
        cover = anime.get('coverImage', {}).get('extraLarge', '')
        
        # Remove tags HTML simples da descrição se houver (como <br>, <i>, etc.)
        raw_desc = anime.get('description', 'Sem descrição disponível.') or 'Sem descrição disponível.'
        import re
        clean_desc = re.sub('<[^<]+?>', '', raw_desc)

        # Botão de voltar
        back_button = ft.IconButton(
            icon=ft.Icons.ARROW_BACK,
            icon_color=ft.Colors.WHITE,
            on_click=lambda _: on_back()
        )

        header = ft.Row([
            back_button,
            ft.Text("Detalhes do Anime", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE)
        ], alignment=ft.MainAxisAlignment.START)

        # Capa e Informações Principais
        poster = ft.Image(src=cover, width=160, height=230, fit=ft.ImageFit.COVER, border_radius=12)
        
        info_column = ft.Column([
            ft.Text(title, size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_ACCENT),
            ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
            ft.ElevatedButton(
                text="Assistir / Episódios",
                icon=ft.Icons.PLAY_ARROW,
                color=ft.Colors.WHITE,
                bgcolor=ft.Colors.RED_700,
                on_click=lambda _: page.snack_bar(ft.SnackBar(content=ft.Text("Provedor de vídeo em breve!"))).open()
            )
        ], expand=True, alignment=ft.MainAxisAlignment.CENTER)

        top_section = ft.Row([poster, info_column], spacing=15, vertical_alignment=ft.CrossAxisAlignment.START)

        # Sinopse
        synopsis_section = ft.Column([
            ft.Text("Sinopse", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE_ACCENT),
            ft.Divider(height=5, color=ft.Colors.TRANSPARENT),
            ft.Text(clean_desc, size=14, color=ft.Colors.GREY_300)
        ])

        layout = ft.Column([
            header,
            ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
            top_section,
            ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
            synopsis_section
        ], scroll=ft.ScrollMode.AUTO, expand=True)

        return ft.Container(content=layout, padding=15)
