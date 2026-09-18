"""Details presentation for one locally indexed anime.

This module deliberately receives an already loaded local catalog entry.  It
never contacts AniList and delegates playback selection to LibraryService.
"""
from __future__ import annotations

import html
import re

import flet as ft
from core.ui import ACCENT, BACKGROUND, PAGE_PADDING, RADIUS, SUCCESS, SURFACE, TEXT, TEXT_MUTED, WARNING, media_artwork, section_title


class DetailView:
    @staticmethod
    def build(page: ft.Page, anime_group: dict, on_play_episode, on_back,
              on_toggle_favorite, get_playback_target=None):
        metadata = anime_group.get("meta") or {}
        title = metadata.get("title_official") or anime_group.get("main_title") or "Anime local"
        alternate_titles = [metadata.get(key) for key in ("english", "romaji", "native")]
        alternate_title = next((value for value in alternate_titles if value and value != title), None)
        seasons = anime_group.get("seasons") or []
        episodes = [episode for season in seasons for episode in season.get("episodes", [])]
        available = [episode for episode in episodes if not episode.get("missing")]
        missing_count = len(episodes) - len(available)
        favorite = [bool(anime_group.get("favorite"))]
        selected_season = [0]
        expanded_description = [False]
        current = anime_group.get("current_episode") or {}
        primary_target = get_playback_target(anime_group["id"]) if get_playback_target else (current or next((item for item in available), None))

        def ratio(episode):
            duration = float(episode.get("duration") or 0)
            return min(float(episode.get("progress") or 0) / duration, 1.0) if duration > 0 else None

        def placeholder(height=198):
            return media_artwork(None, height, width=132, icon_size=38)

        cover = metadata.get("cover_cache") or metadata.get("cover_url")
        poster = media_artwork(cover, 198, width=132, icon_size=38)

        def meta_chip(label, icon=None):
            return ft.Container(
                content=ft.Row(([ft.Icon(icon, size=14, color="#D8D4E3")] if icon else []) + [
                    ft.Text(str(label), size=11, color="#D8D4E3")
                ], tight=True, spacing=4),
                padding=ft.Padding.symmetric(horizontal=9, vertical=5), bgcolor="#2D2A3B", border_radius=RADIUS,
            )

        facts = []
        if metadata.get("year"):
            facts.append(meta_chip(metadata["year"], ft.Icons.CALENDAR_TODAY_OUTLINED))
        if metadata.get("status"):
            facts.append(meta_chip(metadata["status"], ft.Icons.INFO_OUTLINE))
        if available:
            facts.append(meta_chip(f"{len(available)} episódio local" if len(available) == 1 else f"{len(available)} episódios locais", ft.Icons.VIDEO_LIBRARY_OUTLINED))
        if metadata.get("episodes_count"):
            facts.append(meta_chip(f"{metadata['episodes_count']} no total", ft.Icons.FORMAT_LIST_NUMBERED))
        if metadata.get("duration"):
            facts.append(meta_chip(f"{metadata['duration']} min", ft.Icons.SCHEDULE_OUTLINED))
        if metadata.get("score") is not None:
            facts.append(meta_chip(f"{float(metadata['score']) / 10:g}", ft.Icons.STAR_OUTLINED))

        genres = anime_group.get("genres") or []
        genre_controls = [
            ft.Container(ft.Text(genre, size=11, color="#F5F3F8"), bgcolor="#39364B", border_radius=14,
                         padding=ft.Padding.symmetric(horizontal=10, vertical=5))
            for genre in genres if genre
        ]

        description = html.unescape(re.sub(r"<[^>]+>", "", metadata.get("description") or "")).strip()
        description_text = ft.Text(description, size=13, color="#C7C5D0", max_lines=5,
                                   overflow=ft.TextOverflow.ELLIPSIS, visible=bool(description))
        expand_button = ft.TextButton("Ler mais", visible=len(description) > 300)

        def toggle_description(_):
            expanded_description[0] = not expanded_description[0]
            description_text.max_lines = None if expanded_description[0] else 5
            description_text.overflow = None if expanded_description[0] else ft.TextOverflow.ELLIPSIS
            expand_button.content = "Mostrar menos" if expanded_description[0] else "Ler mais"
            page.update()

        expand_button.on_click = toggle_description
        favorite_button = ft.IconButton(
            icon=ft.Icons.STAR if favorite[0] else ft.Icons.STAR_BORDER,
            icon_color="#FFD54F" if favorite[0] else "#FFFFFF",
            tooltip="Remover dos favoritos" if favorite[0] else "Adicionar aos favoritos",
        )

        def toggle_favorite(_):
            favorite[0] = bool(on_toggle_favorite(anime_group["id"]))
            anime_group["favorite"] = favorite[0]
            favorite_button.icon = ft.Icons.STAR if favorite[0] else ft.Icons.STAR_BORDER
            favorite_button.icon_color = "#FFD54F" if favorite[0] else "#FFFFFF"
            favorite_button.tooltip = "Remover dos favoritos" if favorite[0] else "Adicionar aos favoritos"
            page.update()

        favorite_button.on_click = toggle_favorite

        def play(episode):
            if not episode or episode.get("missing") or not episode.get("path"):
                page.snack_bar = ft.SnackBar(ft.Text("Nenhum episódio local disponível para reprodução."))
                page.snack_bar.open = True
                page.update()
                return
            on_play_episode(episode["path"], episode.get("title") or "Episódio",
                            progress_seconds=episode.get("progress") or 0)

        primary_ratio = ratio(primary_target) if primary_target else None
        if primary_target and primary_ratio and primary_ratio > 0 and not primary_target.get("watched"):
            primary_label = "Continuar assistindo"
        elif primary_target and current and current.get("watched"):
            primary_label = "Próximo episódio"
        elif primary_target and available and all(item.get("watched") for item in available):
            primary_label = "Reassistir episódio"
        elif primary_target:
            primary_label = "Assistir episódio"
        else:
            primary_label = "Sem episódios disponíveis"
        primary_button = ft.FilledButton(
            primary_label, icon=ft.Icons.PLAY_ARROW, disabled=not bool(primary_target),
            on_click=lambda _: play(primary_target),
            style=ft.ButtonStyle(bgcolor="#E50914", color="#FFFFFF", shape=ft.RoundedRectangleBorder(radius=12)),
        )

        episode_column = ft.Column(spacing=8)

        def episode_item(episode):
            episode_ratio = ratio(episode)
            number = episode.get("number")
            number_label = f"EP {int(number):02d}" if isinstance(number, (int, float)) else "EP —"
            if episode.get("missing"):
                icon, status, color = ft.Icons.ERROR_OUTLINE, "Arquivo indisponível", WARNING
            elif episode.get("watched"):
                icon, status, color = ft.Icons.CHECK_CIRCLE, "Assistido", SUCCESS
            elif episode_ratio is not None and episode_ratio > 0:
                icon, status, color = ft.Icons.PLAY_CIRCLE_FILL, f"Em andamento • {int(episode_ratio * 100)}%", ACCENT
            else:
                icon, status, color = ft.Icons.PLAY_CIRCLE_OUTLINE, "Disponível localmente", "#AAA7B6"
            details = ft.Column([
                ft.Row([
                    ft.Text(number_label, size=10, weight=ft.FontWeight.BOLD, color="#AAA7B6"),
                    ft.Icon(icon, size=17, color=color),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Text(episode.get("title") or "Episódio", size=13, color="#F7F5FA", weight=ft.FontWeight.BOLD,
                        max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(status, size=11, color=color),
            ], spacing=4, expand=True)
            if episode_ratio is not None and episode_ratio > 0 and not episode.get("missing"):
                details.controls.append(ft.ProgressBar(value=episode_ratio, color="#E50914", bgcolor="#454252", bar_height=4))
            return ft.Container(
                content=details, padding=12, border_radius=RADIUS, bgcolor=SURFACE,
                opacity=.58 if episode.get("missing") else 1, ink=not episode.get("missing"),
                on_click=None if episode.get("missing") else lambda _, item=episode: play(item),
            )

        def render_episodes():
            episode_column.controls.clear()
            if not seasons:
                episode_column.controls.append(ft.Container(
                    content=ft.Text("Nenhum episódio foi indexado para este anime.", color="#AAA7B6", size=13),
                    padding=14, bgcolor=SURFACE, border_radius=RADIUS,
                ))
            else:
                episode_column.controls.extend(episode_item(item) for item in seasons[selected_season[0]].get("episodes", []))
            page.update()

        def change_season(event):
            selected_season[0] = int(event.control.value)
            render_episodes()

        season_picker = ft.Dropdown(
            value="0", options=[ft.dropdown.Option(key=str(index), text=season.get("season_name") or f"Temporada {index + 1}")
                                for index, season in enumerate(seasons)],
            color="#F7F5FA", text_size=13, bgcolor="#252331",
            border_color="#39364B", border_radius=12, visible=len(seasons) > 1,
        )
        season_picker.on_select = change_season

        progress_section = []
        if current:
            current_ratio = ratio(current)
            season = current.get("season")
            number = current.get("number")
            progress_label = "Concluído" if current.get("watched") else (f"{int(current_ratio * 100)}% assistido" if current_ratio is not None else "Em andamento")
            progress_section = [
                ft.Text("CONTINUAR", size=12, weight=ft.FontWeight.BOLD, color="#AAA7B6"),
                ft.Container(content=ft.Column([
                    ft.Text(f"Temporada {season or '—'} • Episódio {number if number is not None else '—'}", color="#F7F5FA", size=13, weight=ft.FontWeight.BOLD),
                    ft.Text(progress_label, color="#B9B5C4", size=11),
                    ft.ProgressBar(value=current_ratio, color="#E50914", bgcolor="#454252", bar_height=4,
                                   visible=current_ratio is not None and not current.get("watched")),
                ], spacing=6), padding=12, bgcolor=SURFACE, border_radius=RADIUS),
            ]

        additional = []
        for label, value in (("Estúdio", metadata.get("studio")), ("Temporada", metadata.get("season")), ("Título alternativo", alternate_title)):
            if value:
                additional.append(ft.Row([
                    ft.Text(label, color="#AAA7B6", size=12, width=120),
                    ft.Text(str(value), color="#F7F5FA", size=12, expand=True, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                ], vertical_alignment=ft.CrossAxisAlignment.START))

        header = ft.Row([
            ft.IconButton(icon=ft.Icons.ARROW_BACK, icon_color="#FFFFFF", tooltip="Voltar", on_click=lambda _: on_back()),
            ft.Text("Detalhes", size=17, weight=ft.FontWeight.BOLD, color=TEXT, expand=True),
            favorite_button,
        ])
        hero_text = ft.Column([
            ft.Text(title, size=22, weight=ft.FontWeight.BOLD, color=TEXT, max_lines=4, overflow=ft.TextOverflow.ELLIPSIS),
            ft.Text(alternate_title, size=12, color="#AAA7B6", max_lines=2, overflow=ft.TextOverflow.ELLIPSIS, visible=bool(alternate_title)),
            ft.Row(facts, wrap=True, spacing=6, run_spacing=6),
            ft.Row(genre_controls, wrap=True, spacing=6, run_spacing=6, visible=bool(genre_controls)),
            primary_button,
            ft.Text(f"{missing_count} indisponível{'is' if missing_count != 1 else ''} na biblioteca local", size=11, color="#D5A84A", visible=missing_count > 0),
        ], spacing=9, expand=True)

        layout_controls = [
            header,
            ft.Row([poster, hero_text], spacing=14, vertical_alignment=ft.CrossAxisAlignment.START),
        ]
        if description:
            layout_controls.extend([section_title("Sinopse", ft.Icons.SUBJECT_OUTLINED), description_text, expand_button])
        layout_controls.extend(progress_section)
        layout_controls.extend([
            section_title("Episódios", ft.Icons.FORMAT_LIST_NUMBERED),
            season_picker,
            episode_column,
        ])
        if additional:
            layout_controls.extend([section_title("Informações adicionais", ft.Icons.INFO_OUTLINE),
                                    ft.Container(ft.Column(additional, spacing=9), padding=12, bgcolor=SURFACE, border_radius=RADIUS)])

        layout = ft.Column(layout_controls, scroll=ft.ScrollMode.AUTO, expand=True, spacing=14)
        render_episodes()
        return ft.Container(content=layout, padding=ft.Padding(left=PAGE_PADDING, right=PAGE_PADDING, top=14, bottom=18), bgcolor=BACKGROUND)
