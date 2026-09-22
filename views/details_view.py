"""Details presentation for one locally indexed anime.

This module deliberately receives an already loaded local catalog entry.  It
never contacts AniList and delegates playback selection to LibraryService.
"""
from __future__ import annotations

import html
import logging
import math
import re

import flet as ft
from core.consumption import consumption_state, is_completed, is_in_progress, playback_action, progress_ratio
from core.dialogs import dismiss_dialog
from core.ui import ACCENT, BACKGROUND, PAGE_PADDING, RADIUS, SUCCESS, SURFACE, TEXT, TEXT_MUTED, WARNING, media_artwork, section_title


class DetailView:
    _logger = logging.getLogger("reiflix.details")

    @staticmethod
    def build(page: ft.Page, anime_group: dict, on_play_episode, on_back,
              on_toggle_favorite, get_playback_target=None, on_set_user_tags=None,
              on_toggle_pinned=None, on_set_personal_note=None, on_set_episode_identification=None,
              on_identification_saved=None, on_refresh_metadata=None, resolve_artwork=None):
        metadata = anime_group.get("meta") or {}
        title = metadata.get("title_official") or anime_group.get("main_title") or "Anime local"
        alternate_titles = [metadata.get(key) for key in ("english", "romaji", "native")]
        alternate_title = next((value for value in alternate_titles if value and value != title), None)
        seasons = anime_group.get("seasons") or []
        regular_episodes = [episode for season in seasons for episode in season.get("episodes", [])]
        special_episodes = [episode for group in (anime_group.get("specials") or []) for episode in group.get("episodes", [])]
        movie_episodes = list(anime_group.get("media_files") or [])
        episodes = [*regular_episodes, *special_episodes, *movie_episodes]
        available = [episode for episode in episodes if not episode.get("missing")]
        missing_count = len(episodes) - len(available)
        media_kind = str(anime_group.get("media_kind") or metadata.get("media_kind") or "series").casefold()
        is_movie = media_kind == "movie" or bool(movie_episodes and not regular_episodes and not special_episodes)
        favorite = [bool(anime_group.get("favorite"))]
        pinned = [bool(anime_group.get("is_pinned"))]
        selected_season = [0]
        expanded_description = [False]
        current = anime_group.get("current_episode") or {}
        primary_target = get_playback_target(anime_group["id"]) if get_playback_target else (current or next((item for item in available), None))
        last_completed = max(
            (item for item in regular_episodes if is_completed(item) and not item.get("missing")),
            key=lambda item: item.get("last_played_at") or 0,
            default=None,
        )
        is_next_after_completion = bool(
            primary_target and last_completed
            and primary_target.get("path") != last_completed.get("path")
            and not primary_target.get("watched")
        )

        def ratio(episode):
            if not episode:
                return None
            try:
                duration = float(episode.get("duration") or 0)
            except (TypeError, ValueError):
                return None
            return progress_ratio(episode) if math.isfinite(duration) and duration > 0 else None

        def duration_label(episode):
            try:
                seconds = float(episode.get("duration") or 0)
            except (TypeError, ValueError):
                return None
            if not math.isfinite(seconds) or seconds <= 0:
                return None
            total = int(seconds)
            if total >= 3600:
                return f"{total // 3600}h {(total % 3600) // 60:02d}min"
            return f"{total // 60}min"

        def placeholder(height=198):
            return media_artwork(None, height, width=132, icon_size=38)

        cover = metadata.get("cover_cache") or metadata.get("cover_url")
        if resolve_artwork:
            artwork_entity = "movie" if is_movie else "anime"
            resolved_poster = resolve_artwork(artwork_entity, anime_group["id"], "poster", allow_network=False)
            if resolved_poster:
                cover = resolved_poster.get("local_path") or cover
        poster = media_artwork(cover, 198, width=132, icon_size=38)

        backdrop = None
        if resolve_artwork:
            resolved_backdrop = resolve_artwork(artwork_entity, anime_group["id"], "backdrop", allow_network=False)
            if resolved_backdrop:
                backdrop_path = resolved_backdrop.get("local_path") or resolved_backdrop.get("external_url")
                if backdrop_path:
                    backdrop = ft.Container(content=media_artwork(backdrop_path, 150, width=None, icon_size=30),
                                            height=150, border_radius=RADIUS)

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
        pin_button = ft.IconButton(
            icon=ft.Icons.PUSH_PIN if pinned[0] else ft.Icons.PUSH_PIN_OUTLINED,
            icon_color=ACCENT if pinned[0] else "#FFFFFF",
            tooltip="Desafixar anime" if pinned[0] else "Fixar anime", visible=on_toggle_pinned is not None,
        )
        def toggle_pin(_):
            try:
                pinned[0] = bool(on_toggle_pinned(anime_group["id"]))
                anime_group["is_pinned"] = pinned[0]
                pin_button.icon = ft.Icons.PUSH_PIN if pinned[0] else ft.Icons.PUSH_PIN_OUTLINED
                pin_button.icon_color = ACCENT if pinned[0] else "#FFFFFF"
                pin_button.tooltip = "Desafixar anime" if pinned[0] else "Fixar anime"
                page.update()
            except Exception:
                page.snack_bar = ft.SnackBar(ft.Text("Não foi possível alterar o pin.")); page.snack_bar.open = True; page.update()
        pin_button.on_click = toggle_pin

        note_text = [str(anime_group.get("personal_note") or "")]
        note_summary = ft.Text(size=12, color="#C7C5D0", max_lines=3, overflow=ft.TextOverflow.ELLIPSIS)
        note_button = ft.OutlinedButton("Adicionar nota", icon=ft.Icons.NOTE_ADD_OUTLINED)
        def render_note():
            note_summary.value = note_text[0] or "Nenhuma nota pessoal."
            note_button.text = "Editar nota" if note_text[0] else "Adicionar nota"
            note_button.icon = ft.Icons.EDIT_NOTE if note_text[0] else ft.Icons.NOTE_ADD_OUTLINED
        def edit_note(_):
            field = ft.TextField(label="Nota privada", value=note_text[0], multiline=True, min_lines=3, max_lines=8, max_length=2000, autofocus=True)
            dialog = ft.AlertDialog(modal=True, title=ft.Text("Nota pessoal"), content=field)
            def save(_event):
                try:
                    value = on_set_personal_note(anime_group["id"], field.value) if on_set_personal_note else field.value
                    note_text[0] = value or ""; anime_group["personal_note"] = note_text[0]
                    render_note(); dismiss_dialog(page, dialog)
                    page.snack_bar = ft.SnackBar(ft.Text("Nota salva.")); page.snack_bar.open = True; safe_update()
                except ValueError as exc:
                    field.error_text = str(exc); page.update()
                except Exception as exc:
                    DetailView._logger.exception("Failed to save personal note")
                    field.error_text = "Não foi possível salvar a nota."
                    page.update()
            dialog.actions = [ft.TextButton("Cancelar", on_click=lambda _: dismiss_dialog(page, dialog)),
                              ft.TextButton("Apagar", visible=bool(note_text[0]), on_click=lambda _: (setattr(field, "value", ""), save(None))),
                              ft.FilledButton("Salvar", on_click=save)]
            page.overlay.append(dialog); dialog.open = True; page.update()
        note_button.on_click = edit_note
        render_note()

        personal_tags = list(anime_group.get("user_tags") or [])
        tags_row = ft.Row(wrap=True, spacing=6, run_spacing=6)

        def save_tags(tags):
            nonlocal personal_tags
            try:
                personal_tags = on_set_user_tags(anime_group["id"], tags) if on_set_user_tags else tags
                anime_group["user_tags"] = personal_tags
                render_tags()
                page.snack_bar = ft.SnackBar(ft.Text("Etiqueta salva.")); page.snack_bar.open = True
                page.update()
            except Exception:
                page.snack_bar = ft.SnackBar(ft.Text("Não foi possível salvar suas etiquetas."))
                page.snack_bar.open = True
                page.update()

        def render_tags():
            tags_row.controls.clear()
            for tag in personal_tags:
                tags_row.controls.append(ft.OutlinedButton(
                    tag, icon=ft.Icons.CLOSE, tooltip=f"Remover etiqueta {tag}",
                    on_click=lambda _, value=tag: save_tags([item for item in personal_tags if item != value]),
                    style=ft.ButtonStyle(color="#D8D4E3", side=ft.BorderSide(1, "#4A4659")),
                ))

        def add_tag(_):
            field = ft.TextField(label="Etiqueta", hint_text="Ex.: Prioridade", autofocus=True, max_length=40)
            dialog = ft.AlertDialog(
                modal=True, title=ft.Text("Adicionar etiqueta pessoal"), content=field,
                actions=[ft.TextButton("Cancelar", on_click=lambda _: dismiss_dialog(page, dialog)),
                         ft.FilledButton("Adicionar", on_click=lambda _: (
                             dismiss_dialog(page, dialog), save_tags([*personal_tags, field.value or ""])))],
            )
            page.overlay.append(dialog)
            dialog.open = True
            page.update()

        render_tags()

        def play(episode):
            if not episode or episode.get("missing") or not episode.get("path"):
                page.snack_bar = ft.SnackBar(ft.Text("Nenhum episódio local disponível para reprodução."))
                page.snack_bar.open = True
                page.update()
                return
            number = episode.get("number")
            episode_label = f"T{episode.get('season', '—')} E{number if number is not None else '—'}"
            player_title = f"{anime_group.get('main_title') or title} • {episode_label}"
            on_play_episode(episode["path"], player_title,
                            progress_seconds=episode.get("progress") or 0)

        primary_ratio = ratio(primary_target) if primary_target else None
        primary_type = str(primary_target.get("episode_type") or "regular").casefold() if primary_target else ""
        primary_action = playback_action(primary_target) if primary_target else "unavailable"
        if primary_action == "continue":
            primary_label = (
                "Continuar filme" if is_movie
                else "Continuar especial" if primary_type in {"special", "ova", "oad", "ona", "extra"}
                else "Continuar episódio"
            )
        elif is_next_after_completion:
            primary_label = "Próximo episódio"
        elif primary_action == "replay":
            primary_label = (
                "Reassistir filme" if is_movie
                else "Reassistir especial" if primary_type in {"special", "ova", "oad", "ona", "extra"}
                else "Reassistir episódio"
            )
        elif primary_action == "watch":
            primary_label = (
                "Assistir filme" if is_movie
                else "Assistir especial" if primary_type in {"special", "ova", "oad", "ona", "extra"}
                else "Assistir episódio"
            )
        else:
            primary_label = "Sem episódios disponíveis"
        metadata_status = str(metadata.get("metadata_status") or "unresolved").casefold()
        status_labels = {"available": "Metadata disponível", "manual": "Metadata manual", "stale": "Metadata desatualizada", "ambiguous": "Metadata ambígua", "unresolved": "Metadata não encontrada", "refreshing": "Atualizando metadata…"}
        metadata_state = status_labels.get(metadata_status, "Metadata parcial")
        refresh_button = ft.OutlinedButton("Atualizar metadata", icon=ft.Icons.REFRESH, on_click=on_refresh_metadata) if on_refresh_metadata else None

        primary_button = ft.FilledButton(
            primary_label, icon=ft.Icons.PLAY_ARROW, disabled=not bool(primary_target),
            on_click=lambda _: play(primary_target),
            style=ft.ButtonStyle(bgcolor="#E50914", color="#FFFFFF", shape=ft.RoundedRectangleBorder(radius=12)),
        )

        episode_column = ft.Column(spacing=8)

        def edit_identification(episode):
            if not on_set_episode_identification:
                return
            season = ft.TextField(label="Temporada", value="" if not episode.get("season") else str(episode["season"]), width=120)
            number = ft.TextField(label="Episódio", value="" if episode.get("number") is None else str(episode["number"]), width=120)
            kind = ft.Dropdown(label="Tipo", value=episode.get("episode_type") or "regular", width=160,
                               options=[ft.dropdown.Option(key=value, text=value) for value in ("regular", "special", "ova", "oad", "ona", "extra", "movie", "unknown")])
            title_field = ft.TextField(label="Título do episódio (opcional)", value=episode.get("episode_title") or "", width=330)
            dialog = ft.AlertDialog(modal=True, title=ft.Text("Corrigir identificação"), content=ft.Column([season, number, kind, title_field], tight=True))
            def save(_):
                try:
                    parsed_season = int(season.value) if (season.value or "").strip() else None
                    parsed_number = float(number.value) if (number.value or "").strip() else None
                    on_set_episode_identification(episode["path"], season=parsed_season, number=parsed_number, episode_type=kind.value, title=title_field.value)
                    # Keep the current Details projection coherent without a
                    # physical rescan: SQLite owns the value, and this view
                    # updates its already-rendered episode list to match it.
                    dismiss_dialog(page, dialog)
                    if on_identification_saved:
                        on_identification_saved()
                    else:
                        episode.update(season=parsed_season or 0, number=parsed_number,
                                       episode_type=kind.value, episode_title=(title_field.value or "").strip() or None,
                                       identification_source="manual", identification_confidence="high",
                                       manual_override=True)
                        render_episodes()
                    page.snack_bar = ft.SnackBar(ft.Text("Identificação manual salva.")); page.snack_bar.open = True; page.update()
                except (TypeError, ValueError) as exc:
                    number.error_text = str(exc) or "Valores inválidos."; page.update()
            dialog.actions = [ft.TextButton("Cancelar", on_click=lambda _: dismiss_dialog(page, dialog)), ft.FilledButton("Salvar", on_click=save)]
            page.overlay.append(dialog); dialog.open = True; page.update()

        def episode_item(episode):
            episode_ratio = ratio(episode)
            number = episode.get("number")
            episode_type = str(episode.get("episode_type") or "regular").casefold()
            if is_movie:
                number_label = "ARQUIVO LOCAL"
            elif episode_type in {"special", "ova", "oad", "ona", "extra"}:
                number_label = episode_type.upper()
            elif isinstance(number, (int, float)) and math.isfinite(number):
                number_label = f"EP {int(number):02d}" if float(number).is_integer() else f"EP {number:g}"
            else:
                number_label = "EP —"
            state = consumption_state(episode)
            if episode.get("missing"):
                icon, status, color = ft.Icons.ERROR_OUTLINE, "Arquivo indisponível", WARNING
            elif state.value in {"completed", "watched"}:
                icon, status, color = ft.Icons.CHECK_CIRCLE, "Concluído" if state.value == "completed" else "Assistido", SUCCESS
            elif state.value == "in_progress":
                icon, status, color = ft.Icons.PLAY_CIRCLE_FILL, f"Em andamento • {int((episode_ratio or 0) * 100)}%", ACCENT
            else:
                icon, status, color = ft.Icons.PLAY_CIRCLE_OUTLINE, "Disponível localmente", "#AAA7B6"
            if episode.get("manual_override"):
                identification = "✎ Correção manual"
            elif episode.get("identification_confidence") == "low" or episode.get("episode_type") == "unknown":
                identification = "⚠ Precisa revisar"
            else:
                identification = "✓ Identificado"
            thumb = None
            if resolve_artwork and not episode.get("missing"):
                resolved_thumb = resolve_artwork("episode", episode.get("id"), "episode_thumbnail", allow_network=False)
                if resolved_thumb:
                    thumb_path = resolved_thumb.get("local_path") or resolved_thumb.get("external_url")
                    if thumb_path:
                        thumb = media_artwork(thumb_path, 72, width=112, icon_size=20)
            duration = duration_label(episode)
            details = ft.Column([
                ft.Row([
                    ft.Text(number_label, size=10, weight=ft.FontWeight.BOLD, color="#AAA7B6"),
                    ft.Row([ft.Icon(icon, size=17, color=color), ft.IconButton(icon=ft.Icons.EDIT_OUTLINED, icon_size=16, tooltip="Corrigir identificação", visible=on_set_episode_identification is not None and not is_movie, on_click=lambda _, item=episode: edit_identification(item))], tight=True),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Text(episode.get("episode_title") or episode.get("title") or episode.get("file_name") or "Mídia local", size=13, color="#F7F5FA", weight=ft.FontWeight.BOLD,
                        max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(status if not is_movie else ("Concluído" if state.value in {"completed", "watched"} else "Filme local"), size=11, color=color),
                ft.Text(f"Duração • {duration}", size=10, color="#AAA7B6", visible=bool(duration)),
                ft.Text(f"Absoluto • {episode.get('absolute_number')}", size=10, color="#AAA7B6",
                        visible=episode.get("absolute_number") is not None and not is_movie),
                ft.Text(identification, size=10, color="#AAA7B6", visible=not is_movie),
            ], spacing=4, expand=True)
            if episode_ratio is not None and episode_ratio > 0 and not episode.get("missing") and state.value == "in_progress":
                details.controls.append(ft.ProgressBar(value=episode_ratio, color="#E50914", bgcolor="#454252", bar_height=4))
            is_missing = bool(episode.get("missing"))
            clickable = None if is_missing else lambda _, item=episode: play(item)
            content = (ft.Row([thumb, details], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER)
                        if thumb else details)
            return ft.Container(
                content=content, padding=12, border_radius=RADIUS, bgcolor=SURFACE,
                opacity=.58 if is_missing else 1.0, ink=not is_missing,
                on_click=clickable,
            )

        def render_episodes():
            episode_column.controls.clear()
            if is_movie:
                if movie_episodes:
                    episode_column.controls.extend(episode_item(item) for item in movie_episodes)
                else:
                    episode_column.controls.append(ft.Text("Nenhum arquivo de filme foi indexado.", color="#AAA7B6", size=13))
                page.update()
                return
            if not seasons and not special_episodes:
                episode_column.controls.append(ft.Container(
                    content=ft.Text("Nenhum episódio foi indexado para este anime.", color="#AAA7B6", size=13),
                    padding=14, bgcolor=SURFACE, border_radius=RADIUS,
                ))
            else:
                if seasons:
                    selected = seasons[min(selected_season[0], len(seasons) - 1)]
                    if resolve_artwork:
                        season_number = selected.get("season")
                        if season_number is not None:
                            resolved_season = resolve_artwork("season", f"{anime_group['id']}:season:{season_number}", "season_poster", allow_network=False)
                            if resolved_season:
                                season_path = resolved_season.get("local_path") or resolved_season.get("external_url")
                                if season_path:
                                    episode_column.controls.append(media_artwork(season_path, 150, width=100, icon_size=24))
                    season_items = selected.get("episodes", [])
                    episode_column.controls.extend(episode_item(item) for item in season_items)
                if special_episodes:
                    episode_column.controls.append(section_title("Especiais", ft.Icons.STAR_OUTLINE))
                    episode_column.controls.extend(episode_item(item) for item in special_episodes)
            page.update()

        def change_season(event):
            selected_season[0] = int(event.control.value)
            if seasons:
                season_picker.helper_text = season_progress_text(seasons[selected_season[0]])
            render_episodes()

        season_picker = ft.Dropdown(
            value="0", options=[
                ft.dropdown.Option(
                    key=str(index),
                    text=f"{season.get('season_name') or f'Temporada {index + 1}'} • {sum(1 for item in season.get('episodes', []) if not item.get('missing'))}/{len(season.get('episodes', []))} locais",
                )
                for index, season in enumerate(seasons)
            ],
            color="#F7F5FA", text_size=13, bgcolor="#252331",
            border_color="#39364B", border_radius=12, visible=bool(seasons) and len(seasons) > 1 and not is_movie,
        )
        def season_progress_text(season):
            items = season.get("episodes", [])
            available_items = [item for item in items if not item.get("missing")]
            watched_items = [item for item in available_items if is_completed(item)]
            active_items = [item for item in available_items if is_in_progress(item)]
            remaining = max(0, len(available_items) - len(watched_items))
            return (
                f"{len(watched_items)}/{len(available_items)} concluídos • {remaining} restantes"
                + (f" • {len(active_items)} em andamento" if active_items else "")
            )

        season_picker.helper_text = season_progress_text(seasons[0]) if seasons else None
        season_picker.on_select = change_season

        progress_section = []
        if current:
            current_ratio = ratio(current)
            season = current.get("season")
            number = current.get("number")
            current_state = consumption_state(current)
            progress_label = "Concluído" if current_state.value in {"completed", "watched"} else (f"{int((current_ratio or 0) * 100)}% assistido" if current_ratio is not None else "Em andamento")
            progress_section = [
                ft.Text("CONTINUAR", size=12, weight=ft.FontWeight.BOLD, color="#AAA7B6"),
                ft.Container(content=ft.Column([
                    ft.Text(("Filme" if is_movie else f"Temporada {season or '—'} • Episódio {number if number is not None else '—'}"), color="#F7F5FA", size=13, weight=ft.FontWeight.BOLD),
                    ft.Text(progress_label, color="#B9B5C4", size=11),
                    ft.ProgressBar(value=current_ratio, color="#E50914", bgcolor="#454252", bar_height=4,
                                   visible=current_ratio is not None and current_state.value == "in_progress"),
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
            pin_button, favorite_button,
        ])
        hero_text = ft.Column([
            ft.Text(title, size=22, weight=ft.FontWeight.BOLD, color=TEXT, max_lines=4, overflow=ft.TextOverflow.ELLIPSIS),
            ft.Text(alternate_title, size=12, color="#AAA7B6", max_lines=2, overflow=ft.TextOverflow.ELLIPSIS, visible=bool(alternate_title)),
            ft.Row(facts, wrap=True, spacing=6, run_spacing=6),
            ft.Row(genre_controls, wrap=True, spacing=6, run_spacing=6, visible=bool(genre_controls)),
            ft.Row(([ft.Text(metadata_state, size=11, color=TEXT_MUTED)] + ([refresh_button] if refresh_button else [])), spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            primary_button,
            ft.Text(f"{missing_count} indisponível{'is' if missing_count != 1 else ''} na biblioteca local", size=11, color="#D5A84A", visible=missing_count > 0),
        ], spacing=9, expand=True)

        layout_controls = []
        if backdrop:
            layout_controls.append(backdrop)
        layout_controls.extend([
            header,
            ft.Row([poster, hero_text], spacing=14, vertical_alignment=ft.CrossAxisAlignment.START),
        ])
        if description:
            layout_controls.extend([section_title("Sinopse", ft.Icons.SUBJECT_OUTLINED), description_text, expand_button])
        if on_set_user_tags:
            layout_controls.extend([
                section_title("Etiquetas pessoais", ft.Icons.LOCAL_OFFER_OUTLINED),
                ft.Row([tags_row, ft.OutlinedButton("Adicionar", icon=ft.Icons.ADD, on_click=add_tag)], wrap=True, spacing=8),
            ])
        if on_set_personal_note:
            layout_controls.extend([
                section_title("Nota pessoal", ft.Icons.STICKY_NOTE_2_OUTLINED),
                ft.Container(ft.Column([note_summary, note_button], spacing=8), padding=12, bgcolor=SURFACE, border_radius=RADIUS),
            ])
        layout_controls.extend(progress_section)
        layout_controls.extend([
            section_title("Filme" if is_movie else "Episódios", ft.Icons.MOVIE_OUTLINED if is_movie else ft.Icons.FORMAT_LIST_NUMBERED),
            season_picker,
            episode_column,
        ])
        if additional:
            layout_controls.extend([section_title("Informações adicionais", ft.Icons.INFO_OUTLINE),
                                    ft.Container(ft.Column(additional, spacing=9), padding=12, bgcolor=SURFACE, border_radius=RADIUS)])

        layout = ft.Column(layout_controls, scroll=ft.ScrollMode.AUTO, expand=True, spacing=14)
        render_episodes()
        return ft.Container(
            content=layout,
            padding=ft.Padding(left=PAGE_PADDING, right=PAGE_PADDING, top=14, bottom=18),
            bgcolor=BACKGROUND,
            expand=True,
        )
