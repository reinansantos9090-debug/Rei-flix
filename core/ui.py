"""Small shared visual language for Rei-flix Flet views."""
from __future__ import annotations

import flet as ft

BACKGROUND = "#16151F"
SURFACE = "#252331"
SURFACE_RAISED = "#2D2A3B"
TEXT = "#F7F5FA"
TEXT_MUTED = "#AAA7B6"
ACCENT = "#E50914"
SUCCESS = "#50B982"
WARNING = "#F2B84B"
RADIUS = 14
PAGE_PADDING = 16


def section_title(text: str, icon=None):
    controls = []
    if icon:
        controls.append(ft.Icon(icon, size=16, color=ACCENT))
    controls.append(ft.Text(text.upper(), size=12, weight=ft.FontWeight.BOLD, color=TEXT_MUTED))
    return ft.Row(controls, spacing=6)


def media_artwork(source, height, *, width=None, icon_size=32, label="Sem capa"):
    fallback = ft.Container(
        width=width, height=height, border_radius=RADIUS, bgcolor=SURFACE_RAISED,
        alignment=ft.Alignment(0, 0),
        content=ft.Column([
            ft.Icon(ft.Icons.MOVIE_OUTLINED, color=TEXT_MUTED, size=icon_size),
            ft.Text(label, color=TEXT_MUTED, size=10, visible=height >= 120),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, tight=True, spacing=3),
    )
    if not source:
        return fallback
    return ft.Image(src=source, width=width, height=height, fit=ft.ImageFit.COVER,
                    border_radius=RADIUS, error_content=fallback)


def empty_state(icon, title: str, body: str, action=None):
    controls = [
        ft.Icon(icon, color=TEXT_MUTED, size=42),
        ft.Text(title, color=TEXT, size=16, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
        ft.Text(body, color=TEXT_MUTED, size=12, text_align=ft.TextAlign.CENTER),
    ]
    if action:
        controls.append(action)
    return ft.Container(
        content=ft.Column(controls, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
        alignment=ft.Alignment(0, 0), padding=20, bgcolor=SURFACE, border_radius=RADIUS,
    )


def chip_style(active=False):
    return ft.ButtonStyle(
        color="#FFFFFF", bgcolor=ACCENT if active else SURFACE,
        side=ft.BorderSide(0, "#00000000"),
        shape=ft.RoundedRectangleBorder(radius=18),
        padding=ft.Padding(left=14, right=14, top=4, bottom=4),
    )
