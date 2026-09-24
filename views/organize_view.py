"""Local-library organization view built on the authoritative catalog and search engine."""
from __future__ import annotations

import asyncio
import inspect
import logging
import math

import flet as ft

from core.consumption import consumption_state, progress_ratio
from core.ui import (
    ACCENT,
    BACKGROUND,
    PAGE_PADDING,
    RADIUS,
    SURFACE,
    TEXT,
    TEXT_MUTED,
    chip_style,
    count_label,
    empty_state,
    media_artwork,
    section_title,
)

logger = logging.getLogger(__name__)


class OrganizeView:
    """Organize one loaded SQLite catalog without scanning or contacting AniList."""

    _STATE_ICONS = {
        "Todos": ft.Icons.GRID_VIEW,
        "Favoritos": ft.Icons.STAR,
        "Fixados": ft.Icons.PUSH_PIN_OUTLINED,
        "Assistidos": ft.Icons.HISTORY,
        "Não assistidos": ft.Icons.LOOKS_ONE_OUTLINED,
        "Em andamento": ft.Icons.PLAY_CIRCLE_OUTLINE,
        "Concluídos": ft.Icons.CHECK_CIRCLE_OUTLINE,
    }
    _STATE_ORDER = (
        "Todos",
        "Favoritos",
        "Fixados",
        "Não assistidos",
        "Em andamento",
        "Concluídos",
        "Assistidos",
    )
    _SORTS = (
        "Mais recentes",
        "Assistidos recentemente",
        "Progresso",
        "Episódio",
        "Temporada + episódio",
        "Modificação",
        "Duração",
        "Tamanho",
        "Favoritos primeiro",
        "Fixados primeiro",
        "Nome A-Z",
        "Nome Z-A",
    )

    @staticmethod
    def build(
        page: ft.Page,
        library,
        on_select_anime,
        on_back,
        on_open_settings,
        on_request_storage_access=None,
        on_scan_storage=None,
        on_request_video_access=None,
        on_add_folder=None,
        view_state=None,
    ):
        catalog: list[dict] = []
        view_state = view_state if view_state is not None else {}
        selected_genre = [view_state.get("genre", "Todos")]
        selected_state = [view_state.get("state", "Todos")]
        selected_sort = [view_state.get("sort", "Mais recentes")]
        query = [view_state.get("query", "")]
        mode = [view_state.get("mode", "overview")]
        render_generation = [0]
        catalog_load_failed = [False]
        scan_active = [False]

        def save_view_state():
            view_state.update(
                genre=selected_genre[0],
                state=selected_state[0],
                sort=selected_sort[0],
                query=query[0],
                mode=mode[0],
            )

        async def _invoke_callback(callback, *args):
            if not callback:
                return
            result = callback(*args)
            if inspect.isawaitable(result):
                await result

        async def handle_request_storage(_event=None):
            await _invoke_callback(on_request_storage_access)

        async def handle_scan_storage(_event=None):
            await _invoke_callback(on_scan_storage)

        async def handle_request_video_access(_event=None):
            await _invoke_callback(on_request_video_access)

        async def handle_add_folder(_event=None):
            await _invoke_callback(on_add_folder)

        content = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=14)
        status = ft.Row(
            [
                ft.ProgressRing(width=16, height=16, stroke_width=2, color=ACCENT),
                ft.Text("Carregando sua biblioteca local…", color=TEXT_MUTED, size=12),
            ],
            spacing=8,
        )

        def artwork(source, height, icon_size=28, width=None):
            return media_artwork(source, height, width=width, icon_size=icon_size)

        def progress(anime):
            current = anime.get("current_episode") or {}
            if not current:
                return None
            try:
                duration = float(current.get("duration") or 0)
            except (TypeError, ValueError):
                return None
            if not math.isfinite(duration) or duration <= 0:
                return None
            return progress_ratio(current)

        async def select_anime(_event, anime):
            try:
                result = on_select_anime(anime)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.exception("Organize anime navigation failed")
                page.snack_bar = ft.SnackBar(ft.Text("Não foi possível abrir esta obra."))
                page.snack_bar.open = True
                page.update()

        def make_anime_click_handler(anime):
            async def handle(event):
                await select_anime(event, anime)
            return handle

        def anime_card(anime):
            available_count = int(anime.get("available_count") or 0)
            watched = int(anime.get("watched_count") or 0)
            ratio = progress(anime)
            meta = anime.get("meta") or {}
            cover = meta.get("cover_cache") or meta.get("cover_url")
            subtitle = (
                count_label(available_count, "episódio")
                if available_count
                else "Sem arquivos disponíveis"
            )
            indicators = []
            if anime.get("favorite"):
                indicators.append(
                    ft.Container(
                        ft.Icon(ft.Icons.STAR, color="#FFD54F", size=16),
                        top=7,
                        right=7,
                        bgcolor="#181720CC",
                        border_radius=12,
                        padding=4,
                    )
                )
            if anime.get("is_pinned"):
                indicators.append(
                    ft.Container(
                        ft.Icon(ft.Icons.PUSH_PIN, color="#FFFFFF", size=15),
                        top=7,
                        left=7,
                        bgcolor="#181720CC",
                        border_radius=12,
                        padding=4,
                    )
                )

            return ft.Container(
                ink=True,
                border_radius=14,
                on_click=make_anime_click_handler(anime),
                content=ft.Column(
                    [
                        ft.Stack(
                            [
                                ft.Container(
                                    artwork(cover, 188, width=None),
                                    height=188,
                                ),
                                *indicators,
                            ]
                        ),
                        ft.Text(
                            anime.get("main_title") or "Anime local",
                            size=13,
                            weight=ft.FontWeight.BOLD,
                            color="#F7F5FA",
                            max_lines=2,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Text(
                            f"{watched}/{available_count} assistidos" if available_count else subtitle,
                            size=10,
                            color="#AAA7B6",
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.ProgressBar(
                            value=ratio,
                            color="#E50914",
                            bgcolor="#3C3948",
                            bar_height=3,
                            visible=(
                                ratio is not None
                                and ratio > 0
                                and consumption_state(anime.get("current_episode") or {}).value
                                == "in_progress"
                            ),
                        ),
                    ],
                    spacing=5,
                ),
            )

        def header(title, back_handler=None):
            if back_handler:
                left = ft.IconButton(
                    icon=ft.Icons.ARROW_BACK,
                    icon_color="#FFFFFF",
                    tooltip="Voltar",
                    on_click=back_handler,
                )
            else:
                left = ft.IconButton(
                    icon=ft.Icons.HOME_OUTLINED,
                    icon_color="#FFFFFF",
                    tooltip="Início",
                    on_click=lambda _event: on_back(),
                )
            actions = []
            if on_request_storage_access:
                actions.append(
                    ft.IconButton(
                        icon=ft.Icons.FOLDER_OPEN_OUTLINED,
                        icon_color="#FFFFFF",
                        tooltip="Solicitar acesso ao armazenamento",
                        on_click=handle_request_storage,
                    )
                )
            if on_scan_storage:
                actions.append(
                    ft.IconButton(
                        icon=ft.Icons.REFRESH,
                        icon_color="#FFFFFF",
                        tooltip="Atualizar biblioteca",
                        on_click=handle_scan_storage,
                    )
                )
            actions.append(
                ft.IconButton(
                    icon=ft.Icons.SETTINGS_OUTLINED,
                    icon_color="#FFFFFF",
                    tooltip="Configurações",
                    on_click=lambda _event: on_open_settings(),
                )
            )
            return ft.Row(
                [
                    left,
                    ft.Column(
                        [
                            ft.Text(
                                title,
                                size=21,
                                weight=ft.FontWeight.BOLD,
                                color="#F7F5FA",
                            ),
                            ft.Text(
                                "Explore sua biblioteca local",
                                size=11,
                                color="#AAA7B6",
                            ),
                        ],
                        spacing=1,
                        expand=True,
                    ),
                    *actions,
                ]
            )

        def state_button(label, count):
            async def handle(_event):
                selected_state[0] = label
                selected_genre[0] = "Todos"
                mode[0] = "collection"
                save_view_state()
                await render()

            return ft.Container(
                width=155,
                padding=12,
                bgcolor=SURFACE,
                border_radius=RADIUS,
                ink=True,
                on_click=handle,
                content=ft.Column(
                    [
                        ft.Icon(
                            OrganizeView._STATE_ICONS.get(label, ft.Icons.DASHBOARD_OUTLINED),
                            color=ACCENT,
                            size=23,
                        ),
                        ft.Text(
                            label,
                            color=TEXT,
                            size=12,
                            weight=ft.FontWeight.BOLD,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Text(
                            count_label(count, "anime"),
                            color=TEXT_MUTED,
                            size=10,
                        ),
                    ],
                    spacing=5,
                ),
            )

        def genre_card(item):
            label = item["name"]
            count = item["count"]
            cover = item.get("cover")

            async def handle(_event):
                selected_genre[0] = label
                selected_state[0] = "Todos"
                mode[0] = "collection"
                save_view_state()
                await render()

            return ft.Container(
                width=170,
                height=142,
                border_radius=RADIUS,
                clip_behavior=ft.ClipBehavior.HARD_EDGE,
                bgcolor="#292737",
                ink=True,
                on_click=handle,
                content=ft.Stack(
                    [
                        ft.Container(artwork(cover, 142), height=142, opacity=0.55),
                        ft.Container(
                            content=ft.Column(
                                [
                                    ft.Text(
                                        label.upper(),
                                        color="#FFFFFF",
                                        size=14,
                                        weight=ft.FontWeight.BOLD,
                                        max_lines=2,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                    ft.Text(
                                        count_label(count, "anime"),
                                        color="#E2DEE9",
                                        size=11,
                                    ),
                                ],
                                spacing=3,
                            ),
                            left=12,
                            right=10,
                            bottom=10,
                        ),
                    ]
                ),
            )

        def empty_catalog():
            actions = []
            if on_request_video_access:
                actions.append(
                    ft.FilledButton(
                        "Permitir leitura de vídeos",
                        icon=ft.Icons.VIDEO_LIBRARY_OUTLINED,
                        on_click=handle_request_video_access,
                    )
                )
            if on_request_storage_access:
                actions.append(
                    ft.OutlinedButton(
                        "Acesso amplo",
                        icon=ft.Icons.FOLDER_OPEN_OUTLINED,
                        on_click=handle_request_storage,
                    )
                )
            if on_add_folder:
                actions.append(
                    ft.OutlinedButton(
                        "Adicionar pasta",
                        icon=ft.Icons.CREATE_NEW_FOLDER,
                        on_click=handle_add_folder,
                    )
                )
            if on_scan_storage:
                actions.append(
                    ft.OutlinedButton(
                        "Atualizar",
                        icon=ft.Icons.REFRESH,
                        on_click=handle_scan_storage,
                    )
                )
            actions.append(
                ft.TextButton(
                    "Abrir configurações",
                    icon=ft.Icons.SETTINGS,
                    on_click=lambda _event: on_open_settings(),
                )
            )
            return ft.Container(
                content=ft.Column(
                    [
                        ft.Icon(ft.Icons.VIDEO_LIBRARY_OUTLINED, size=48, color=ACCENT),
                        ft.Text(
                            "Seu catálogo está vazio",
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            color=TEXT,
                        ),
                        ft.Text(
                            "Permita a leitura de vídeos, use acesso amplo quando disponível, ou escolha uma pasta específica para montar sua biblioteca local.",
                            size=12,
                            color=TEXT_MUTED,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.Column(
                            actions,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=8,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=12,
                ),
                alignment=ft.Alignment(0, 0),
                padding=24,
            )

        async def open_collection(genre=None, state=None):
            if genre is not None:
                selected_genre[0] = genre
            if state is not None:
                selected_state[0] = state
            mode[0] = "collection"
            save_view_state()
            await render()

        async def back_to_overview(_event=None):
            mode[0] = "overview"
            save_view_state()
            await render()

        async def clear_filters(_event=None):
            selected_genre[0] = "Todos"
            selected_state[0] = "Todos"
            selected_sort[0] = "Mais recentes"
            query[0] = ""
            mode[0] = "collection"
            save_view_state()
            await render()

        async def on_search(event):
            query[0] = event.control.value or ""
            save_view_state()
            await render_collection_only()

        async def on_sort(event):
            selected_sort[0] = event.control.value or "Mais recentes"
            save_view_state()
            await render_collection_only()

        async def on_genre_change(event):
            selected_genre[0] = event.control.value or "Todos"
            selected_state[0] = "Todos"
            save_view_state()
            await render_collection_only()

        async def render_overview():
            try:
                summary = await asyncio.to_thread(library.organize_summary, list(catalog))
            except Exception:
                logger.exception(
                    "Organize summary failed",
                    extra={"screen": "organize", "library_items": len(catalog)},
                )
                content.controls.extend(
                    [
                        header("Organizar"),
                        empty_state(
                            ft.Icons.ERROR_OUTLINE,
                            "Não foi possível organizar a biblioteca",
                            "A biblioteca local não pôde ser consultada agora.",
                        ),
                    ]
                )
                return

            content.controls.extend([header("Organizar"), status])
            if catalog_load_failed[0]:
                content.controls.append(
                    empty_state(
                        ft.Icons.ERROR_OUTLINE,
                        "Não foi possível carregar a biblioteca",
                        "Tente novamente para ler o catálogo local.",
                        ft.FilledButton(
                            "Tentar novamente",
                            on_click=lambda _event: page.run_task(load_catalog),
                        ),
                    )
                )
                return
            if not catalog:
                if status.visible:
                    return
                content.controls.append(empty_catalog())
                return

            content.controls.extend(
                [
                    section_title("Categorias", ft.Icons.DASHBOARD_OUTLINED),
                    ft.Row(
                        [
                            state_button(
                                item["name"],
                                item["count"],
                            )
                            for item in summary.get("states", [])
                        ],
                        scroll=ft.ScrollMode.AUTO,
                        spacing=10,
                    ),
                ]
            )
            if summary.get("genres"):
                content.controls.extend(
                    [
                        section_title("Gêneros", ft.Icons.LOCAL_OFFER_OUTLINED),
                        ft.Row(
                            [
                                genre_card(item)
                                for item in summary["genres"]
                            ],
                            wrap=True,
                            spacing=12,
                            run_spacing=12,
                        ),
                    ]
                )
            else:
                content.controls.append(
                    ft.Text(
                        "Nenhum gênero está disponível nos metadados locais.",
                        color=TEXT_MUTED,
                        size=12,
                    )
                )

        def state_chip(label):
            active = (
                label == selected_state[0]
                and selected_genre[0] == "Todos"
            )

            async def handle(_event):
                await open_collection("Todos", label)

            return ft.OutlinedButton(
                label,
                on_click=handle,
                style=chip_style(active),
            )

        async def render_collection():
            token = render_generation[0]
            try:
                filtered = await asyncio.to_thread(
                    library.browse_catalog,
                    list(catalog),
                    query[0],
                    selected_state[0],
                    selected_genre[0],
                    selected_sort[0],
                )
            except Exception:
                logger.exception(
                    "Organize collection projection failed",
                    extra={"screen": "organize", "library_items": len(catalog)},
                )
                filtered = []
                projection_failed = True
            else:
                projection_failed = False

            if token != render_generation[0]:
                return

            title = (
                selected_genre[0]
                if selected_genre[0] != "Todos"
                else selected_state[0]
            )
            content.controls.extend(
                [
                    header(title, back_to_overview),
                    status if status.visible else ft.Container(height=0),
                ]
            )

            search_field = ft.TextField(
                value=query[0],
                hint_text="Buscar título, gênero, alias ou episódio",
                prefix_icon=ft.Icons.SEARCH,
                border_radius=RADIUS,
                border_width=0,
                bgcolor=SURFACE,
                color=TEXT,
                content_padding=12,
                text_size=14,
                expand=True,
                on_change=on_search,
                on_submit=on_search,
            )
            clear_button = ft.TextButton(
                "Limpar",
                icon=ft.Icons.CLEAR_ALL,
                on_click=clear_filters,
                visible=(
                    bool(query[0].strip())
                    or selected_state[0] != "Todos"
                    or selected_genre[0] != "Todos"
                    or selected_sort[0] != "Mais recentes"
                ),
            )
            content.controls.append(
                ft.Row([search_field, clear_button], spacing=8)
            )
            content.controls.append(
                ft.Row(
                    [state_chip(label) for label in OrganizeView._STATE_ORDER],
                    scroll=ft.ScrollMode.AUTO,
                    spacing=8,
                )
            )

            summary = await asyncio.to_thread(library.organize_summary, list(catalog))
            genres = ["Todos"] + [item["name"] for item in summary.get("genres", [])]
            if selected_genre[0] not in genres:
                selected_genre[0] = "Todos"
                save_view_state()
            genre = ft.Dropdown(
                value=selected_genre[0],
                label="Gênero",
                width=235,
                options=[ft.dropdown.Option(value, value) for value in genres],
                on_change=on_genre_change,
            )
            sort = ft.Dropdown(
                value=selected_sort[0],
                label="Ordenar",
                width=235,
                options=[
                    ft.dropdown.Option(value, value)
                    for value in OrganizeView._SORTS
                ],
                on_select=on_sort,
            )
            content.controls.append(ft.Row([genre, sort], wrap=True, spacing=8))

            active_description = []
            if query[0].strip():
                active_description.append(f'busca "{query[0].strip()}"')
            if selected_genre[0] != "Todos":
                active_description.append(f'gênero {selected_genre[0]}')
            if selected_state[0] != "Todos":
                active_description.append(selected_state[0].lower())
            if selected_sort[0] != "Mais recentes":
                active_description.append(selected_sort[0].lower())
            summary_text = " • ".join(active_description) if active_description else "Todos os itens da biblioteca"
            content.controls.append(
                ft.Text(
                    f"{count_label(len(filtered), 'anime')} • {summary_text}",
                    color=TEXT_MUTED,
                    size=12,
                )
            )

            if projection_failed:
                content.controls.append(
                    empty_state(
                        ft.Icons.ERROR_OUTLINE,
                        "Não foi possível aplicar os filtros",
                        "A biblioteca continua preservada. Tente novamente.",
                    )
                )
            elif filtered:
                content.controls.append(
                    ft.Row(
                        wrap=True,
                        spacing=14,
                        run_spacing=20,
                        controls=[anime_card(anime) for anime in filtered],
                    )
                )
            else:
                if query[0].strip():
                    title_empty = "Nenhum resultado encontrado"
                    body_empty = "Tente outro título, episódio ou termo de busca."
                elif selected_state[0] != "Todos" or selected_genre[0] != "Todos":
                    title_empty = "Nenhum anime nesta coleção"
                    body_empty = "Altere os filtros ou volte para todas as obras."
                else:
                    title_empty = "Sua biblioteca está vazia"
                    body_empty = "Adicione vídeos locais para começar a organizar."
                content.controls.append(
                    ft.Container(
                        empty_state(
                            ft.Icons.FILTER_LIST_OFF,
                            title_empty,
                            body_empty,
                        ),
                        alignment=ft.Alignment(0, 0),
                        height=190,
                    )
                )

        async def render_collection_only():
            if mode[0] != "collection":
                mode[0] = "collection"
                save_view_state()
            render_generation[0] += 1
            content.controls.clear()
            await render_collection()
            page.update()

        async def render():
            render_generation[0] += 1
            content.controls.clear()
            if mode[0] == "overview":
                await render_overview()
            else:
                await render_collection()
            page.update()

        async def load_catalog():
            try:
                loaded = await asyncio.to_thread(library.catalog)
                last_scan = await asyncio.to_thread(library.last_scan)
            except Exception:
                logger.exception(
                    "Organize catalog load failed",
                    extra={"screen": "organize", "library_items": len(catalog)},
                )
                catalog_load_failed[0] = True
                status.visible = False
                await render()
                return

            catalog_load_failed[0] = False
            catalog.clear()
            catalog.extend(loaded or [])
            scan_active[0] = bool(
                last_scan
                and str(last_scan.get("status") or "").casefold()
                in {"running", "started"}
            )
            status.visible = scan_active[0]
            if scan_active[0]:
                status.controls = [
                    ft.ProgressRing(width=16, height=16, stroke_width=2, color=ACCENT),
                    ft.Text(
                        "Descobrindo vídeos locais…",
                        color=TEXT_MUTED,
                        size=12,
                    ),
                ]
            await render()

        save_view_state()
        render_generation[0] += 1
        page.run_task(load_catalog)
        return ft.Container(
            content=content,
            padding=ft.Padding(
                left=PAGE_PADDING,
                right=PAGE_PADDING,
                top=18,
                bottom=8,
            ),
            bgcolor=BACKGROUND,
            expand=True,
        )
