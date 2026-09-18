import flet as ft

class PlayerView:
    @staticmethod
    def build(page: ft.Page, video_uri: str, ep_title: str, on_back, on_next_episode=None, on_native_play=None, progress_seconds=0):
        def play(_):
            if not on_native_play:
                page.snack_bar=ft.SnackBar(ft.Text("O player nativo está disponível somente no APK Android.")); page.snack_bar.open=True; page.update(); return
            try:
                on_native_play(video_uri, ep_title, int(progress_seconds * 1000))
            except Exception as exc:
                page.snack_bar=ft.SnackBar(ft.Text(f"Não foi possível abrir o player: {exc}")); page.snack_bar.open=True; page.update()
        header=ft.Row([ft.IconButton(icon=ft.Icons.ARROW_BACK,icon_color=ft.Colors.WHITE,on_click=lambda _:on_back()),ft.Column([ft.Text(ep_title,size=15,weight=ft.FontWeight.BOLD,color=ft.Colors.WHITE),ft.Text("Reprodução local",size=11,color="#9DA3B4")],spacing=1)],alignment=ft.MainAxisAlignment.START)
        video=ft.Container(bgcolor=ft.Colors.BLACK,alignment=ft.alignment.center,content=ft.Column([ft.Icon(ft.Icons.PLAY_CIRCLE_OUTLINE,color=ft.Colors.WHITE,size=72),ft.Text("Player local Android",color=ft.Colors.WHITE),ft.FilledButton("Reproduzir",icon=ft.Icons.PLAY_ARROW,on_click=play)],horizontal_alignment=ft.CrossAxisAlignment.CENTER,tight=True))
        return ft.Container(content=ft.Column([header,ft.Container(content=video,alignment=ft.alignment.center,bgcolor=ft.Colors.BLACK,expand=True)],expand=True),padding=12,bgcolor="#0E0D13")
