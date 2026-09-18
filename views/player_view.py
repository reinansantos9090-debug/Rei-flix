"""Transition screen for the Android local player; playback stays native."""
from __future__ import annotations

import flet as ft

from core.ui import ACCENT, BACKGROUND, PAGE_PADDING, RADIUS, SURFACE, TEXT, TEXT_MUTED


class PlayerView:
    @staticmethod
    def build(page: ft.Page, video_uri: str, ep_title: str, on_back, on_next_episode=None, on_native_play=None, progress_seconds=0):
        opening = [False]
        play_button = ft.FilledButton("Abrir player", icon=ft.Icons.PLAY_ARROW)

        def notice(message):
            page.snack_bar = ft.SnackBar(ft.Text(message))
            page.snack_bar.open = True
            page.update()

        def play(_):
            if opening[0]:
                return
            if not video_uri:
                notice("Este episódio não possui um arquivo local disponível.")
                return
            if not on_native_play:
                notice("O player nativo está disponível somente no APK Android.")
                return
            opening[0] = True
            play_button.disabled = True
            play_button.text = "Abrindo player…"
            page.update()
            try:
                on_native_play(video_uri, ep_title, max(0, int(progress_seconds * 1000)))
            except Exception:
                opening[0] = False
                play_button.disabled = False
                play_button.text = "Tentar novamente"
                notice("Não foi possível abrir o player local.")
                page.update()

        play_button.on_click = play
        header = ft.Row([
            ft.IconButton(icon=ft.Icons.ARROW_BACK, icon_color=TEXT, tooltip="Voltar", on_click=lambda _: on_back()),
            ft.Column([
                ft.Text(ep_title or "Episódio local", size=16, weight=ft.FontWeight.BOLD, color=TEXT,
                        max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text("Reprodução local", size=12, color=TEXT_MUTED),
            ], spacing=2, expand=True),
        ])
        video = ft.Container(
            bgcolor="#0E0D13", border_radius=RADIUS, alignment=ft.Alignment(0, 0), expand=True,
            content=ft.Column([
                ft.Container(ft.Icon(ft.Icons.PLAY_CIRCLE_OUTLINE, color=ACCENT, size=72), bgcolor="#2D2A3B", border_radius=48, padding=14),
                ft.Text("Pronto para reproduzir", color=TEXT, size=18, weight=ft.FontWeight.BOLD),
                ft.Text("O vídeo será aberto no player nativo do seu dispositivo.", color=TEXT_MUTED, size=12,
                        text_align=ft.TextAlign.CENTER),
                play_button,
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=14, tight=True),
        )
        return ft.Container(content=ft.Column([header, video], expand=True, spacing=16),
                            padding=PAGE_PADDING, bgcolor=BACKGROUND)
