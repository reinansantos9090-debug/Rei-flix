"""Local-library exploration view for genres and durable playback states."""
from __future__ import annotations

import math
import inspect
import flet as ft
from core.consumption import consumption_state, progress_ratio
from core.ui import ACCENT, BACKGROUND, PAGE_PADDING, RADIUS, SURFACE, TEXT, TEXT_MUTED, chip_style, empty_state, media_artwork, section_title, count_label


class OrganizeView:
    """Organize one loaded SQLite catalog without scanning or contacting AniList."""

    @staticmethod
    def build(page: ft.Page, library, on_select_anime, on_back, on_open_settings,
              on_request_storage_access=None, on_scan_storage=None, on_request_video_access=None,
              on_add_folder=None, view_state=None):
        catalog = []
        view_state = view_state if view_state is not None else {}

        async def _invoke_callback(callback):
            if callback:
                result = callback()
                if inspect.isawaitable(result):
                    await result

        async def handle_request_storage(_=None):
            await _invoke_callback(on_request_storage_access)

        async def handle_scan_storage(_=None):
            await _invoke_callback(on_scan_storage)

        async def handle_request_video_access(_=None):
            await _invoke_callback(on_request_video_access)

        async def handle_add_folder(_=None):
            await _invoke_callback(on_add_folder)
        selected_genre = [view_state.get("genre", "Todos")]
        selected_state = [view_state.get("state", "Todos")]
        selected_sort = [view_state.get("sort", "Mais recentes")]
        mode = [view_state.get("mode", "overview")]

        def save_view_state():
            view_state.update(genre=selected_genre[0], state=selected_state[0], sort=selected_sort[0], mode=mode[0])

        content = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=14)
        status = ft.Row([ft.ProgressRing(width=16, height=16, stroke_width=2, color=ACCENT), ft.Text("Carregando sua biblioteca local…", color=TEXT_MUTED, size=12)], spacing=8)

        def artwork(source, height, icon_size=28):
            return media_artwork(source, height, icon_size=icon_size)

        def episodes(anime):
            return [episode for season in anime.get("seasons", []) for episode in season.get("episodes", [])]

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

        def anime_card(anime):
            available_count = int(anime.get("available_count") or 0)
            watched = int(anime.get("watched_count") or 0)
            ratio = progress(anime)
            cover = (anime.get("meta") or {}).get("cover_cache") or (anime.get("meta") or {}).get("cover_url")
            subtitle = f"{watched}/{available_count} assistidos" if available_count else "Sem arquivos disponíveis"
            overlays = []
            if anime.get("favorite"):
                overlays.append(ft.Container(ft.Icon(ft.Icons.STAR, color="#FFD54F", size=16), top=7, right=7,
                                             bgcolor="#181720CC", border_radius=12, padding=4))
            return ft.Container(
                ink=True, on_click=lambda _, item=anime: on_select_anime(item), border_radius=14,
                content=ft.Column([
                    ft.Stack([ft.Container(artwork(cover, 188), height=188), *overlays]),
                    ft.Text(anime.get("main_title") or "Anime local", size=13, weight=ft.FontWeight.BOLD,
                            color="#F7F5FA", max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(subtitle, size=10, color="#AAA7B6", max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.ProgressBar(value=ratio, color="#E50914", bgcolor="#3C3948", bar_height=3,
                                   visible=ratio is not None and ratio > 0 and consumption_state(anime.get("current_episode") or {}).value == "in_progress"),
                ], spacing=5),
            )

        def header(title, back_handler=None):
            left = ft.IconButton(icon=ft.Icons.ARROW_BACK, icon_color="#FFFFFF", tooltip="Voltar",
                                 on_click=lambda _: back_handler()) if back_handler else ft.IconButton(
                                     icon=ft.Icons.HOME_OUTLINED, icon_color="#FFFFFF", tooltip="Início",
                                     on_click=lambda _: on_back())
            actions = []
            if on_request_storage_access:
                actions.append(ft.IconButton(icon=ft.Icons.FOLDER_OPEN_OUTLINED, icon_color="#FFFFFF",
                                             tooltip="Solicitar acesso ao armazenamento",
                                             on_click=handle_request_storage))
            if on_scan_storage:
                actions.append(ft.IconButton(icon=ft.Icons.REFRESH, icon_color="#FFFFFF",
                                             tooltip="Varrer armazenamento",
                                             on_click=handle_scan_storage))
            actions.append(ft.IconButton(icon=ft.Icons.SETTINGS_OUTLINED, icon_color="#FFFFFF", tooltip="Configurações",
                                         on_click=lambda _: on_open_settings()))
            return ft.Row([
                left,
                ft.Column([ft.Text(title, size=21, weight=ft.FontWeight.BOLD, color="#F7F5FA"),
                           ft.Text("Explore sua biblioteca local", size=11, color="#AAA7B6")], spacing=1, expand=True),
                *actions,
            ])

        def state_button(label, count):
            icons = {"Todos": ft.Icons.GRID_VIEW, "Favoritos": ft.Icons.STAR,
                     "Em andamento": ft.Icons.PLAY_CIRCLE_OUTLINE, "Concluídos": ft.Icons.CHECK_CIRCLE_OUTLINE}
            return ft.Container(
                width=155, padding=12, bgcolor=SURFACE, border_radius=RADIUS, ink=True,
                on_click=lambda _, value=label: open_collection("Todos", value),
                content=ft.Column([
                    ft.Icon(icons[label], color=ACCENT, size=23),
                    ft.Text(label, color=TEXT, size=12, weight=ft.FontWeight.BOLD, max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(count_label(count, "anime"), color=TEXT_MUTED, size=10),
                ], spacing=5),
            )

        def genre_card(item):
            label, count, cover = item["name"], item["count"], item.get("cover")
            visual = artwork(cover, 104, 30)
            return ft.Container(
                width=170, height=142, border_radius=RADIUS, clip_behavior=ft.ClipBehavior.HARD_EDGE,
                bgcolor="#292737", ink=True, on_click=lambda _, value=label: open_collection(value, "Todos"),
                content=ft.Stack([
                    ft.Container(visual, height=142, opacity=.55),
                    ft.Container(
                        content=ft.Column([
                            ft.Text(label.upper(), color="#FFFFFF", size=14, weight=ft.FontWeight.BOLD, max_lines=2,
                                    overflow=ft.TextOverflow.ELLIPSIS),
                            ft.Text(f"{count} anime{'s' if count != 1 else ''}", color="#E2DEE9", size=11),
                        ], spacing=3), left=12, right=10, bottom=10,
                    ),
                ]),
            )

        def empty_catalog():
            actions = []
            if on_request_video_access:
                actions.append(ft.FilledButton("Permitir leitura de vídeos", icon=ft.Icons.VIDEO_LIBRARY_OUTLINED, on_click=handle_request_video_access))
            if on_request_storage_access:
                actions.append(ft.OutlinedButton("Acesso amplo", icon=ft.Icons.FOLDER_OPEN_OUTLINED, on_click=handle_request_storage))
            if on_add_folder:
                actions.append(ft.OutlinedButton("Adicionar pasta", icon=ft.Icons.CREATE_NEW_FOLDER, on_click=handle_add_folder))
            if on_scan_storage:
                actions.append(ft.OutlinedButton("Varrer", icon=ft.Icons.REFRESH, on_click=handle_scan_storage))
            actions.append(ft.TextButton("Abrir configurações", icon=ft.Icons.SETTINGS, on_click=lambda _: on_open_settings()))
            return ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.VIDEO_LIBRARY_OUTLINED, size=48, color=ACCENT),
                    ft.Text("Seu catálogo está vazio", size=18, weight=ft.FontWeight.BOLD, color=TEXT),
                    ft.Text("Permita a leitura de vídeos, use acesso amplo quando disponível, ou escolha uma pasta específica para montar sua biblioteca local.", size=12, color=TEXT_MUTED, text_align=ft.TextAlign.CENTER),
                    ft.Column(actions, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=12),
                alignment=ft.Alignment(0, 0), padding=24,
            )

        def open_collection(genre, state):
            selected_genre[0], selected_state[0], mode[0] = genre, state, "collection"
            save_view_state()
            render()

        def back_to_overview():
            mode[0] = "overview"
            save_view_state()
            render()

        def filter_chip(label):
            active = label == selected_state[0]
            return ft.OutlinedButton(
                label, on_click=lambda _, value=label: open_collection(selected_genre[0], value),
                style=chip_style(active),
            )

        def render_overview():
            summary = library.organize_summary(catalog)
            content.controls.extend([header("Organizar"), status])
            if not catalog:
                content.controls.append(empty_catalog())
                return
            content.controls.extend([
                section_title("Categorias", ft.Icons.DASHBOARD_OUTLINED),
                ft.Row([state_button(item["name"], item["count"]) for item in summary["states"]],
                       scroll=ft.ScrollMode.AUTO, spacing=10),
            ])
            if summary["genres"]:
                content.controls.extend([
                    section_title("Gêneros", ft.Icons.LOCAL_OFFER_OUTLINED),
                    ft.Row([genre_card(item) for item in summary["genres"]], wrap=True, spacing=12, run_spacing=12),
                ])
            else:
                content.controls.append(ft.Text("Nenhum gênero está disponível nos metadados locais.", color="#AAA7B6", size=12))

        def render_collection():
            filtered = library.browse_catalog(catalog, state=selected_state[0], genre=selected_genre[0], sort=selected_sort[0])
            title = selected_genre[0].upper() if selected_genre[0] != "Todos" else selected_state[0]
            content.controls.extend([
                header(title, back_to_overview),
                ft.Text(f"{len(filtered)} anime{'s' if len(filtered) != 1 else ''} na sua biblioteca", color="#AAA7B6", size=12),
                ft.Row([filter_chip(label) for label in ("Todos", "Favoritos", "Em andamento", "Concluídos")], scroll=ft.ScrollMode.AUTO, spacing=8),
            ])
            sort = ft.Dropdown(value=selected_sort[0], width=190, dense=True, text_size=12, color="#F5F5F7",
                               bgcolor="#252836", border_color="#39364B", border_radius=12,
                               options=[ft.dropdown.Option(key=value, text=value) for value in
                                        ("Mais recentes", "Assistidos recentemente", "Nome A-Z", "Nome Z-A")])
            def change_sort(event):
                selected_sort[0] = event.control.value or "Mais recentes"
                save_view_state()
                render()
            sort.on_select = change_sort
            content.controls.append(sort)
            if filtered:
                content.controls.append(ft.GridView(controls=[anime_card(anime) for anime in filtered],
                                                    max_extent=168, child_aspect_ratio=.57, spacing=14,
                                                    run_spacing=20, height=max(260, ((len(filtered) + 1) // 2) * 290),
                                                    padding=ft.Padding.only(bottom=24)))
            else:
                content.controls.append(ft.Container(
                content=empty_state(ft.Icons.FILTER_LIST_OFF, "Nenhum anime nesta categoria", "Altere o filtro ou volte para explorar a biblioteca."), alignment=ft.Alignment(0, 0), height=190,
                ))

        def render():
            content.controls.clear()
            if mode[0] == "overview":
                render_overview()
            else:
                render_collection()
            page.update()

        def load_catalog():
            nonlocal catalog
            try:
                catalog = library.catalog()
                status.visible = False
            except Exception as exc:
                status.controls = [ft.Icon(ft.Icons.ERROR_OUTLINE, color="#FFB4AB", size=18), ft.Text("Não foi possível carregar sua biblioteca local.", color="#FFB4AB", size=12)]
            render()

        page.run_thread(load_catalog)
        return ft.Container(content=content, padding=ft.Padding(left=PAGE_PADDING, right=PAGE_PADDING, top=18, bottom=8), bgcolor=BACKGROUND)
