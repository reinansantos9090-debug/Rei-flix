from __future__ import annotations

import asyncio
import inspect
import logging
import os
import flet as ft

from core.consumption import consumption_state, progress_ratio
from core.settings import SettingsStore
from core.ui import ACCENT, BACKGROUND, PAGE_PADDING, RADIUS, SURFACE, TEXT, TEXT_MUTED, activate_theme_for_page, empty_state, media_artwork, count_label

logger = logging.getLogger(__name__)


class HomeView:
    """CloudStream-inspired local library home with async data access and compact cards."""

    @staticmethod
    def build(page: ft.Page, library, on_select_anime, on_open_settings, on_play_episode, on_open_organize=None,
              view_state=None, on_request_thumbnail=None):
        theme = activate_theme_for_page(page)
        BACKGROUND = theme.background
        SURFACE = theme.surface
        TEXT = theme.text
        TEXT_MUTED = theme.text_muted
        ACCENT = theme.primary
        catalog: list[dict] = []
        continuing: list[dict] = []
        home_data: dict = {}
        view_state = view_state if view_state is not None else {}
        settings = SettingsStore(library.store)
        sort_labels = {
            "added_desc": "Mais recentes",
            "title_asc": "Nome A-Z",
            "title_desc": "Nome Z-A",
            "recently_watched": "Assistidos recentemente",
        }
        selected_state = [view_state.get("state", "Todos")]
        selected_genre = [view_state.get("genre", "Todos")]
        selected_sort = [view_state.get("sort", sort_labels[settings.get("library.sort_default")])]
        selected_media_type = [view_state.get("media_type", "Todos")]
        card_size = {"small": 120, "medium": 146, "large": 172}[settings.get("appearance.card_size")]
        density_gap = {"small": 14, "medium": 10, "large": 6}[settings.get("library.grid_density")]
        card_width = card_size
        card_height = round(card_size * 176 / 146)
        show_thumbnails = settings.get("appearance.show_thumbnails")
        page_size = settings.get("library.page_size")
        selected_tag = [view_state.get("tag", "Todos")]
        selected_season = [view_state.get("season", "Todos")]
        selected_episode_type = [view_state.get("episode_type", "Todos")]
        selected_availability = [view_state.get("availability", "Todos")]
        selected_metadata = [view_state.get("metadata", "Todos")]
        selected_artwork = [view_state.get("artwork", "Todos")]
        search_visible = [bool(view_state.get("search_visible", False))]
        render_generation = [0]
        search_generation = [0]
        current_page = [0]
        has_more = [True]
        total_matches = [0]
        page_loading = [False]
        scan_active = [False]
        home_sections_generation = [0]
        filter_options_loaded = [False]
        artwork_tasks: set[tuple] = set()
        artwork_bindings: dict[tuple, list] = {}

        def save_view_state():
            view_state.update(
                state=selected_state[0], genre=selected_genre[0], sort=selected_sort[0],
                media_type=selected_media_type[0], tag=selected_tag[0], season=selected_season[0],
                episode_type=selected_episode_type[0], availability=selected_availability[0],
                metadata=selected_metadata[0], artwork=selected_artwork[0],
                search_visible=search_visible[0], query=search.value or "",
            )

        def ratio(item):
            return progress_ratio(item)

        grid = ft.Row(wrap=True, spacing=density_gap, run_spacing=max(8, density_gap + 2))
        status = ft.Row(
            [ft.ProgressRing(width=16, height=16, stroke_width=2, color=ACCENT),
             ft.Text("Carregando biblioteca local…", color=TEXT_MUTED, size=12)],
            spacing=8,
        )
        feedback = ft.Container(visible=False)
        hydration_status = ft.Text("", color=TEXT_MUTED, size=11, visible=False)
        library_label = ft.Text("MINHA BIBLIOTECA", size=13, weight=ft.FontWeight.BOLD, color=TEXT_MUTED)
        search = ft.TextField(
            value=view_state.get("query", ""), visible=search_visible[0],
            hint_text="Buscar na sua biblioteca", prefix_icon=ft.Icons.SEARCH,
            border_radius=RADIUS, border_width=0, bgcolor=SURFACE, color=TEXT,
            content_padding=12, text_size=14, autofocus=search_visible[0],
        )
        sort = ft.Dropdown(
            value=selected_sort[0], width=175, dense=True, text_size=12, color=TEXT,
            bgcolor=SURFACE, border_color=theme.border, border_radius=RADIUS,
            options=[ft.dropdown.Option(key=value, text=value) for value in (
                "Mais recentes", "Assistidos recentemente", "Progresso", "Episódio",
                "Temporada + episódio", "Modificação", "Duração", "Tamanho",
                "Favoritos primeiro", "Fixados primeiro", "Nome A-Z", "Nome Z-A",
            )],
        )
        state_filter = ft.Dropdown(value=selected_state[0], label="Estado", width=220, options=[
            ft.dropdown.Option(v) for v in (
                "Todos", "Favoritos", "Fixados", "Não assistidos",
                "Em andamento", "Concluídos", "Assistidos",
            )
        ])
        genre_filter = ft.Dropdown(value=selected_genre[0], label="Gênero", width=220, options=[ft.dropdown.Option("Todos")])
        media_type = ft.Dropdown(value=selected_media_type[0], label="Tipo", width=220, options=[
            ft.dropdown.Option("Todos", "Todos"), *[ft.dropdown.Option(v, v) for v in ("Série/Anime", "Filme", "Especial", "Episódio")]
        ])
        tag = ft.Dropdown(value=selected_tag[0], label="Etiqueta", width=220, options=[ft.dropdown.Option("Todos", "Todos")])
        season = ft.Dropdown(value=selected_season[0], label="Temporada", width=220, options=[ft.dropdown.Option("Todos", "Todos")])
        episode_type = ft.Dropdown(value=selected_episode_type[0], label="Tipo de episódio", width=220, options=[ft.dropdown.Option("Todos", "Todos")])
        availability = ft.Dropdown(value=selected_availability[0], label="Disponibilidade", width=220, options=[
            ft.dropdown.Option(v) for v in ("Todos", "Disponível", "Com missing", "Sem missing")
        ])
        metadata_filter = ft.Dropdown(value=selected_metadata[0], label="Metadata", width=220, options=[
            ft.dropdown.Option(v) for v in ("Todos", "Disponível", "Ausente")
        ])
        artwork_filter = ft.Dropdown(value=selected_artwork[0], label="Capa", width=220, options=[
            ft.dropdown.Option(v) for v in ("Todos", "Disponível", "Ausente")
        ])
        filter_summary = ft.Text(size=11, color=TEXT_MUTED)

        continue_row = ft.Row(scroll=ft.ScrollMode.AUTO, spacing=10)
        continuation_section = ft.Container(
            content=ft.Column([ft.Text("CONTINUAR ASSISTINDO", size=13, weight=ft.FontWeight.BOLD, color=TEXT_MUTED), continue_row], spacing=9),
            visible=False,
        )
        section_rows: dict[str, ft.Row] = {}
        section_cards: dict[str, ft.Container] = {}

        def artwork_holder(item, width, height, *, entity="anime", kind="poster", source=None):
            holder = ft.Container(
                width=width, height=height, border_radius=RADIUS, bgcolor=theme.surface_raised,
                alignment=ft.Alignment(0, 0),
            )
            binding_entity = "movie" if item.get("media_kind") == "movie" and entity == "anime" else entity
            binding_id = item.get("anime_id") if item.get("anime_id") is not None and binding_entity in {"anime", "movie"} else item.get("id")
            if binding_id is not None:
                artwork_bindings.setdefault((binding_entity, int(binding_id), kind), []).append((holder, width, height))

            def apply_source(path):
                if not isinstance(path, str):
                    return False
                if path.startswith(("content://", "file://")):
                    valid = True
                else:
                    try:
                        valid = os.path.isfile(path) and os.path.getsize(path) > 0
                    except OSError:
                        valid = False
                if not valid:
                    return False
                holder.content = ft.Image(src=path, width=width, height=height, fit=ft.BoxFit.COVER, border_radius=RADIUS)
                return True

            if not show_thumbnails:
                holder.content = ft.Icon(ft.Icons.MOVIE_OUTLINED, color=TEXT_MUTED, size=28)
                return holder
            if apply_source(source):
                return holder
            meta = item.get("meta") or {}
            candidate_source = item.get("cover") or meta.get("cover_cache")
            if apply_source(candidate_source):
                return holder

            item_id = item.get("anime_id") if item.get("anime_id") is not None and entity in {"anime", "movie"} else item.get("id")
            if item_id is not None and library is not None:
                key = (entity, int(item_id), kind, width, height)
                if key not in artwork_tasks:
                    artwork_tasks.add(key)
                    request_generation = render_generation[0]
                    async def hydrate():
                        try:
                            resolved = await asyncio.to_thread(
                                library.resolve_artwork, entity, item_id, kind, allow_network=False
                            )
                            if request_generation != render_generation[0]:
                                return
                            path = (resolved or {}).get("local_path")
                            if apply_source(path):
                                meta = item.setdefault("meta", {})
                                meta["cover_cache"] = path
                                item["cover"] = path
                                try:
                                    holder.update()
                                except Exception:
                                    page.update()
                        except Exception:
                            logger.exception(
                                "Artwork render hydration failed",
                                extra={"screen":"home","requestId":"-","item_id":item_id},
                            )
                        finally:
                            artwork_tasks.discard(key)
                    page.run_task(hydrate)
            holder.content = ft.Icon(ft.Icons.MOVIE_OUTLINED, color=TEXT_MUTED, size=28)
            return holder

        def player_episode_title(anime_title, episode):
            if episode.get("episode_type") == "movie":
                return anime_title
            season_value = episode.get("season")
            number_value = episode.get("number")
            if season_value is not None and number_value is not None:
                return f"{anime_title} • T{int(season_value)} E{int(number_value)}"
            if season_value is not None:
                return f"{anime_title} • T{int(season_value)}"
            return anime_title

        def play_continuation(item):
            episode = item.get("episode", item)
            if not episode.get("path") or episode.get("missing"):
                return
            anime_title = item.get("anime_title") or item.get("main_title") or item.get("title") or "Reproduzir"
            on_play_episode(episode["path"], player_episode_title(anime_title, episode), progress_seconds=episode.get("progress", 0) or 0)

        def home_card(item, action=None, episode=False):
            meta = item.get("meta") or {}
            cover = item.get("cover") or meta.get("cover_cache")
            if episode:
                title = item.get("anime_title") or item.get("title") or "Mídia local"
                subtitle = item.get("episode_title") or (f"T{item.get('season')} E{item.get('number')}" if item.get("season") is not None else "Episódio")
            else:
                title = item.get("main_title") or item.get("anime_title") or meta.get("title") or "Mídia local"
                subtitle = "Filme" if item.get("media_kind") == "movie" else (count_label(item.get("available_count", 0), "episódio") if item.get("available_count") else "")
            holder = artwork_holder(item, card_width, card_height, source=cover)
            if not cover and on_request_thumbnail:
                candidate = item.get("episode") or item.get("current_episode")
                if not candidate and item.get("seasons"):
                    candidate = next((ep for season_data in item.get("seasons", []) for ep in season_data.get("episodes", []) if ep.get("path") and not ep.get("missing")), None)
                if candidate:
                    on_request_thumbnail(candidate)
            return ft.Container(
                width=card_width, ink=True, border_radius=RADIUS,
                on_click=(lambda _, value=item: action(value)) if action else None,
                content=ft.Column([holder,
                    ft.Text(title, size=12, weight=ft.FontWeight.BOLD, color=TEXT, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(subtitle, size=10, color=TEXT_MUTED, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.ProgressBar(value=ratio(item), color=ACCENT, bgcolor=theme.surface_variant, height=3, visible=consumption_state(item).value == "in_progress"),
                ], spacing=4),
            )

        def render_section(title, key, items, action=None, episode=False):
            row = section_rows.setdefault(key, ft.Row(scroll=ft.ScrollMode.AUTO, spacing=10))
            row.controls.clear()
            row.controls.extend(home_card(item, action=action, episode=episode) for item in (items or [])[:8])
            if key not in section_cards:
                section_cards[key] = ft.Container(content=ft.Column([ft.Text(title, size=15, weight=ft.FontWeight.BOLD, color=TEXT), row], spacing=9))
            section_cards[key].visible = bool(items)
            section_cards[key].content.controls[1] = row

        def _library_filters():
            return dict(
                query=search.value or "", state=selected_state[0], genre=selected_genre[0], sort=selected_sort[0],
                tag=selected_tag[0], media_type=selected_media_type[0], season=selected_season[0],
                episode_type=selected_episode_type[0], availability=selected_availability[0],
                metadata=selected_metadata[0], artwork=selected_artwork[0],
            )

        async def load_library_page(*, reset=False):
            if page_loading[0] or (not reset and not has_more[0]):
                return
            if reset:
                render_generation[0] += 1
                current_page[0] = 0
                has_more[0] = True
                total_matches[0] = 0
                artwork_bindings.clear()
                catalog.clear()
                grid.controls.clear()
                feedback.visible = False
            page_loading[0] = True
            token = render_generation[0]
            target_page = 0 if reset else current_page[0] + 1
            try:
                result = await asyncio.to_thread(
                    library.browse_catalog_page,
                    page=target_page, page_size=page_size, **_library_filters(),
                )
            except Exception:
                logger.exception("Home paged query failed", extra={"screen":"home","page":target_page})
                if reset:
                    feedback.content = empty_state(ft.Icons.ERROR_OUTLINE, "Não foi possível ler a biblioteca local agora.", "Tente novamente.")
                    feedback.visible = True
                    page.update()
                page_loading[0] = False
                return
            if token != render_generation[0]:
                page_loading[0] = False
                return
            page_items = result.get("items") or []
            existing_ids = {int(item.get("id")) for item in catalog if item.get("id") is not None}
            fresh_items = [item for item in page_items if item.get("id") is None or int(item.get("id")) not in existing_ids]
            catalog.extend(fresh_items)
            current_page[0] = int(result.get("page") or target_page)
            total_matches[0] = int(result.get("total") or 0)
            has_more[0] = bool(result.get("has_more"))
            if catalog:
                library_label.value = f"MINHA BIBLIOTECA • {total_matches[0]}"
                feedback.visible = False
                grid.controls.extend(card(item) for item in fresh_items)
            elif scan_active[0]:
                library_label.value = "DESCOBRINDO BIBLIOTECA LOCAL…"
                feedback.visible = False
            else:
                library_label.value = "MINHA BIBLIOTECA"
                feedback.content = empty_state(ft.Icons.SEARCH_OFF if (search.value or "").strip() else ft.Icons.VIDEO_LIBRARY_OUTLINED, "Nenhum resultado" if (search.value or "").strip() else "Sua biblioteca local está vazia", "Tente alterar a busca ou os filtros." if (search.value or "").strip() else "Adicione uma pasta com animes nas configurações para começar.", ft.FilledButton("Abrir configurações", icon=ft.Icons.SETTINGS, on_click=lambda _: on_open_settings()) if not (search.value or "").strip() else None)
                feedback.visible = True
            active_filters = sum(v not in {None, "", "Todos", "Mais recentes"} for v in (selected_state[0], selected_genre[0], selected_media_type[0], selected_tag[0], selected_season[0], selected_episode_type[0], selected_availability[0], selected_metadata[0], selected_artwork[0]))
            filter_summary.value = f"{active_filters} filtro(s) ativo(s)" if active_filters else "Filtros"
            status.visible = scan_active[0]
            page_loading[0] = False
            page.update()
            await restore_scroll_position()
            if fresh_items:
                async def run_hydration_batch():
                    await hydrate_metadata_and_artwork(list(fresh_items), token)
                schedule_background(run_hydration_batch)

        def schedule_background(coro_factory):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                page.run_task(coro_factory)
                return
            loop.create_task(coro_factory())

        async def load_next_page():
            await load_library_page(reset=False)

        def on_home_scroll(event):
            try:
                view_state["scroll_position"] = float(event.pixels)
                remaining = float(event.max_scroll_extent - event.pixels)
            except (TypeError, ValueError, AttributeError):
                return
            if remaining < 800 and has_more[0] and not page_loading[0]:
                schedule_background(load_next_page)
        def card(anime):
            available_count = int(anime.get("available_count") or 0)
            completed = int(anime.get("watched_count") or 0)
            current = anime.get("current_episode") or {}
            current_state = consumption_state(current) if current else None
            progress = ratio(current)
            cover = (anime.get("meta") or {}).get("cover_cache")
            content_count = int(anime.get("content_count") or 0)
            missing_count = int(anime.get("missing_count") or 0)
            subtitle = "Filme" if anime.get("media_kind") == "movie" else (
                count_label(available_count, "episódio") if missing_count == 0 else f"{available_count}/{content_count} disponíveis"
            )
            status_value = "Concluído" if available_count > 0 and missing_count == 0 and completed == available_count else (f"{completed} concluídos" if completed else subtitle)
            indicators = []
            if anime.get("favorite"):
                indicators.append(ft.Container(ft.Icon(ft.Icons.STAR, color=theme.favorite, size=15), top=5, right=5, bgcolor=theme.overlay, border_radius=12, padding=3))
            if current_state and current_state.value in {"completed", "watched"}:
                indicators.append(ft.Container(ft.Icon(ft.Icons.CHECK, color=theme.text_on_overlay, size=14), bottom=5, right=5, bgcolor=theme.success + "CC", border_radius=12, padding=3))
            if anime.get("is_pinned"):
                indicators.append(ft.Container(
                    ft.Icon(ft.Icons.PUSH_PIN, color=ACCENT, size=14),
                    top=5, left=5, bgcolor=theme.overlay, border_radius=12, padding=3,
                ))
            return ft.Container(
                key=f"anime:{anime.get('id', '-')}",
                width=card_width, ink=True, on_click=lambda _, item=anime: on_select_anime(item), border_radius=RADIUS,
                content=ft.Column([
                    ft.Stack([artwork_holder(anime, card_width, card_height, source=cover), *indicators]),
                    ft.Text(anime.get("main_title", "Anime local"), size=12, weight=ft.FontWeight.BOLD, color=TEXT, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(status_value, size=10, color=TEXT_MUTED, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.ProgressBar(value=progress, color=ACCENT, bgcolor=theme.surface_variant, height=3, visible=current_state is not None and current_state.value == "in_progress"),
                ], spacing=4),
            )

        async def open_continuation_details(item):
            anime = next(
                (candidate for candidate in catalog
                 if candidate.get("id") is not None and candidate.get("id") == item.get("anime_id")),
                None,
            )
            if anime is None and item.get("anime_id") is not None:
                try:
                    projected = await asyncio.to_thread(
                        library.catalog_by_ids, [int(item["anime_id"])]
                    )
                except Exception:
                    logger.exception(
                        "Home continuation details lookup failed",
                        extra={"screen": "home", "anime_id": item.get("anime_id")},
                    )
                    return
                anime = next(iter(projected or []), None)
            if anime is not None:
                on_select_anime(anime)
            else:
                logger.warning(
                    "Continuation details target unavailable",
                    extra={"screen": "home", "anime_id": item.get("anime_id")},
                )

        def request_continuation_details(item):
            async def task():
                await open_continuation_details(item)
            page.run_task(task)

        def render_continue():
            continue_row.controls.clear()
            continuation_section.visible = bool(continuing)
            for item in continuing[:6]:
                progress = ratio(item)
                label = "FILME" if item.get("episode_type") == "movie" else f"T{item.get('season', 1)} • E{item.get('number', '—')}"
                card_control = ft.Container(
                    width=258, bgcolor=SURFACE, border_radius=RADIUS, padding=9, ink=True,
                    on_click=lambda _, entry=item: play_continuation(entry),
                    content=ft.Row([
                        artwork_holder(item, 56, 82),
                        ft.Column([
                            ft.Text(item.get("anime_title", "Anime local"), color=TEXT, size=12, weight=ft.FontWeight.BOLD, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                            ft.Text(label, color=TEXT_MUTED, size=10),
                            ft.ProgressBar(value=progress, color=ACCENT, bgcolor=theme.surface_variant, height=3, visible=bool(item.get("duration"))),
                            ft.Row([
                                ft.TextButton("Continuar", icon=ft.Icons.PLAY_ARROW, on_click=lambda _, entry=item: play_continuation(entry)),
                                ft.TextButton(
                                    "Detalhes",
                                    icon=ft.Icons.INFO_OUTLINE,
                                    on_click=lambda _, entry=item: request_continuation_details(entry),
                                ),
                            ], spacing=0),
                        ], spacing=4, expand=True),
                    ], spacing=8),
                )
                continue_row.controls.append(card_control)

        def refresh_filter_options(options):
            tags = options.get("tags") or []
            seasons = options.get("seasons") or []
            episode_types = options.get("episode_types") or []
            genres = [str(value) for value in (options.get("genres") or []) if value]
            states = [str(value) for value in (options.get("states") or []) if value]
            if "Todos" not in states:
                states.insert(0, "Todos")
            state_filter.options = [ft.dropdown.Option(value, value) for value in states]
            if selected_state[0] not in states:
                selected_state[0] = "Todos"
            state_filter.value = selected_state[0]
            tag.options = [ft.dropdown.Option("Todos", "Todos"), ft.dropdown.Option("Sem etiqueta", "Sem etiqueta")] + [ft.dropdown.Option(v, v) for v in tags]
            season.options = [ft.dropdown.Option("Todos", "Todos")] + [ft.dropdown.Option(str(v), f"Temporada {v}") for v in seasons]
            episode_type.options = [ft.dropdown.Option("Todos", "Todos")] + [ft.dropdown.Option(v, v) for v in episode_types]
            genre_filter.options = [ft.dropdown.Option("Todos", "Todos")] + [ft.dropdown.Option(v, v) for v in genres]
            for control, value_box, fallback, values in (
                (tag, selected_tag, "Todos", {"Todos", "Sem etiqueta", *tags}),
                (season, selected_season, "Todos", {"Todos", *[str(v) for v in seasons]}),
                (episode_type, selected_episode_type, "Todos", {"Todos", *episode_types}),
                (genre_filter, selected_genre, "Todos", {"Todos", *genres}),
            ):
                if value_box[0] not in values:
                    value_box[0] = fallback
                control.value = value_box[0]
            state_filter.value = selected_state[0]
            media_type.value = selected_media_type[0]
            availability.value = selected_availability[0]
            metadata_filter.value = selected_metadata[0]
            artwork_filter.value = selected_artwork[0]

        async def apply_filters(_=None):
            selected_state[0] = state_filter.value or "Todos"
            selected_genre[0] = genre_filter.value or "Todos"
            selected_media_type[0] = media_type.value or "Todos"
            selected_tag[0] = tag.value or "Todos"
            selected_season[0] = season.value or "Todos"
            selected_episode_type[0] = episode_type.value or "Todos"
            selected_availability[0] = availability.value or "Todos"
            selected_metadata[0] = metadata_filter.value or "Todos"
            selected_artwork[0] = artwork_filter.value or "Todos"
            save_view_state()
            page.pop_dialog()
            await load_library_page(reset=True)

        async def clear_filters(_=None):
            selected_state[0] = "Todos"
            selected_genre[0] = "Todos"
            selected_sort[0] = "Mais recentes"
            selected_media_type[0] = "Todos"
            selected_tag[0] = "Todos"
            selected_season[0] = "Todos"
            selected_episode_type[0] = "Todos"
            selected_availability[0] = "Todos"
            selected_metadata[0] = "Todos"
            selected_artwork[0] = "Todos"
            state_filter.value = "Todos"
            genre_filter.value = "Todos"
            sort.value = "Mais recentes"
            media_type.value = "Todos"
            tag.value = "Todos"
            season.value = "Todos"
            episode_type.value = "Todos"
            availability.value = "Todos"
            metadata_filter.value = "Todos"
            artwork_filter.value = "Todos"
            search.value = ""
            search_generation[0] += 1
            save_view_state()
            page.pop_dialog()
            await load_library_page(reset=True)

        def open_filters(_=None):
            page.run_task(load_filter_options)
            dialog = ft.AlertDialog(
                modal=True, title=ft.Text("Filtros da biblioteca"),
                content=ft.Column([
                    ft.Row([state_filter, genre_filter], wrap=True),
                    ft.Row([media_type, tag], wrap=True),
                    ft.Row([season, episode_type], wrap=True),
                    ft.Row([availability, metadata_filter], wrap=True),
                    artwork_filter,
                ], tight=True, width=470),
                actions=[
                    ft.TextButton("Limpar", icon=ft.Icons.CLEAR_ALL, on_click=lambda _: page.run_task(clear_filters)),
                    ft.TextButton("Cancelar", on_click=lambda _: page.pop_dialog()),
                    ft.FilledButton("Aplicar", on_click=apply_filters),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            page.show_dialog(dialog)
            page.update()

        async def toggle_search(_):
            search_visible[0] = not search_visible[0]
            search.visible = search_visible[0]
            search.autofocus = search_visible[0]
            if not search_visible[0]:
                search.value = ""
            save_view_state()
            await load_library_page(reset=True)

        async def on_search(event):
            save_view_state()
            search_generation[0] += 1
            token = search_generation[0]
            await asyncio.sleep(0.18)
            if token != search_generation[0]:
                return
            await load_library_page(reset=True)

        async def on_sort(event):
            selected_sort[0] = event.control.value or "Mais recentes"
            save_view_state()
            await load_library_page(reset=True)

        async def hydrate_metadata_and_artwork(items, token):
            if not items or token != render_generation[0]:
                return
            try:
                results = await asyncio.to_thread(library.hydrate_catalog_metadata, items)
                if token != render_generation[0]:
                    return
                by_id = {int(item.get('id')): item for item in items if item.get('id') is not None}
                updated = 0
                for result in results or []:
                    item_id = result.get('id')
                    target = by_id.get(int(item_id)) if item_id is not None else None
                    metadata = result.get('metadata') or {}
                    if target is None or not metadata:
                        continue
                    target['meta'] = dict(metadata)
                    cover_path = metadata.get('cover_cache')
                    if not cover_path:
                        continue
                    entity = 'movie' if target.get('media_kind') == 'movie' else 'anime'
                    for holder, width, height in artwork_bindings.get((entity, int(item_id), 'poster'), []):
                        try:
                            holder.content = ft.Image(src=cover_path, width=width, height=height, fit=ft.BoxFit.COVER, border_radius=RADIUS)
                            holder.update()
                            updated += 1
                        except Exception:
                            logger.exception('Home localized artwork update failed')
                if updated:
                    logger.info('HOME_ARTWORK_BATCH_UPDATED count=%s', updated)
            except Exception:
                logger.exception('Home metadata/artwork hydration failed', extra={'screen':'home','requestId':'-','library_items':len(items)})

        async def refresh_home_sections(token):
            try:
                loaded = await asyncio.to_thread(library.media_center_home, limit=12)
            except Exception:
                logger.exception("Home secondary sections load failed", extra={"screen":"home"})
                return
            if token != render_generation[0] or token != home_sections_generation[0]:
                return
            home_data.clear()
            home_data.update(loaded or {})
            continuing.clear()
            if settings.get("library.continue_watching"):
                limit = settings.get("library.continue_watching_limit")
                continuing.extend(home_data.get("continue_watching", [])[:limit])
            render_continue()
            for title, key, is_episode in (
                ("PRÓXIMO EPISÓDIO", "next_episode", False),
                ("RECENTEMENTE ADICIONADOS", "recently_added", False),
                ("RECENTEMENTE ASSISTIDOS", "recently_watched", True),
                ("FAVORITOS", "favorites", False),
                ("PINADOS", "pinned", False),
                ("SÉRIES / ANIMES", "series", False),
                ("FILMES", "movies", False),
                ("ESPECIAIS", "specials", False),
            ):
                try:
                    render_section(title, key, home_data.get(key), action=None if is_episode else on_select_anime, episode=is_episode)
                except Exception:
                    logger.exception("Home section render failed", extra={"screen":"home","section":key})
            page.update()

        async def load_filter_options():
            if filter_options_loaded[0]:
                return
            try:
                loaded_options = await asyncio.to_thread(library.search_options)
            except Exception:
                logger.exception("Home filter options load failed", extra={"screen":"home"})
                return
            if filter_options_loaded[0]:
                return
            refresh_filter_options(loaded_options or {})
            filter_options_loaded[0] = True
            page.update()

        async def refresh_from_catalog():
            save_view_state()
            filter_options_loaded[0] = False
            await load_library_page(reset=True)
            home_sections_generation[0] = render_generation[0]
            page.run_task(refresh_home_sections, render_generation[0])

        async def retry_load_catalog(_event=None):
            await load_catalog()

        async def load_catalog():
            status.visible = True
            status.controls = [
                ft.ProgressRing(width=16, height=16, stroke_width=2, color=ACCENT),
                ft.Text("Carregando biblioteca local…", color=TEXT_MUTED, size=12),
            ]
            page.update()
            try:
                last_scan = await asyncio.to_thread(library.last_scan)
            except Exception:
                logger.exception("Home local projections load failed", extra={"screen":"home","requestId":"-"})
                status.controls = [
                    ft.Icon(ft.Icons.ERROR_OUTLINE, color=theme.error, size=18),
                    ft.Text("Não foi possível ler a biblioteca local agora.", color=theme.error, size=12),
                    ft.TextButton("Tentar novamente", on_click=retry_load_catalog),
                ]
                status.visible = True
                page.update()
                return
            scan_active[0] = bool(
                last_scan and str(last_scan.get("status") or "").casefold() in {"running", "started"}
            )
            filter_options_loaded[0] = False
            home_sections_generation[0] = render_generation[0]
            await load_library_page(reset=True)
            status.visible = scan_active[0]
            page.update()
            await restore_scroll_position()
            page.run_task(refresh_home_sections, render_generation[0])

        search.on_change = on_search
        search.on_submit = on_search
        sort.on_select = on_sort
        header = ft.Row([
            ft.Row([
                ft.Container(content=ft.Icon(ft.Icons.PLAY_CIRCLE_FILLED, color=ACCENT, size=29), bgcolor=SURFACE, border_radius=12, padding=5),
                ft.Text("ReiFlix", size=22, weight=ft.FontWeight.BOLD, color=TEXT),
            ], spacing=8),
            ft.Row([
                ft.IconButton(icon=ft.Icons.SEARCH, icon_color=TEXT, tooltip="Pesquisar", on_click=toggle_search),
                ft.IconButton(icon=ft.Icons.DASHBOARD_OUTLINED, icon_color=TEXT, tooltip="Organizar", visible=on_open_organize is not None, on_click=lambda _: on_open_organize() if on_open_organize else None),
                ft.IconButton(icon=ft.Icons.SETTINGS_OUTLINED, icon_color=TEXT, tooltip="Configurações", on_click=lambda _: on_open_settings()),
            ], spacing=0),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, wrap=True, run_spacing=8)
        filter_button = ft.OutlinedButton("Filtros", icon=ft.Icons.TUNE, on_click=open_filters)
        main_library_bar = ft.Row(
            [ft.Row([library_label, filter_summary], spacing=10, wrap=True), sort, filter_button],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            wrap=True,
            spacing=8,
            run_spacing=8,
        )
        sections_column = ft.Column(
            [section_cards.setdefault(key, ft.Container(content=ft.Column([ft.Text(title, size=15, weight=ft.FontWeight.BOLD, color=TEXT), section_rows.setdefault(key, ft.Row(scroll=ft.ScrollMode.AUTO, spacing=10))], spacing=9), visible=False))
             for title, key in (
                ("PRÓXIMO EPISÓDIO", "next_episode"), ("RECENTEMENTE ADICIONADOS", "recently_added"),
                ("RECENTEMENTE ASSISTIDOS", "recently_watched"), ("FAVORITOS", "favorites"),
                ("PINADOS", "pinned"), ("SÉRIES / ANIMES", "series"), ("FILMES", "movies"), ("ESPECIAIS", "specials"),
             )],
            spacing=14,
        )
        layout = ft.Column([
            header, search, ft.Text("Sua biblioteca local, conteúdo primeiro.", size=12, color=TEXT_MUTED),
            status, hydration_status, continuation_section, main_library_bar, feedback, grid, sections_column, ft.Container(height=24),
        ], scroll=ft.ScrollMode.AUTO, expand=True, spacing=12, scroll_interval=60, on_scroll=on_home_scroll)
        async def restore_scroll_position():
            stored = view_state.get("scroll_position")
            if stored is None:
                return
            try:
                result = layout.scroll_to(offset=float(stored), duration=0)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.debug("Home scroll restoration unavailable", exc_info=True)

        def schedule_refresh_from_catalog():
            page.run_task(refresh_from_catalog)

        view_state['_refresh_from_catalog'] = schedule_refresh_from_catalog
        status.visible = True
        page.run_task(load_catalog)
        return ft.Container(
            content=layout, padding=ft.Padding(left=PAGE_PADDING, right=PAGE_PADDING, top=16, bottom=8),
            bgcolor=BACKGROUND, expand=True,
        )