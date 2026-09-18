"""Local-library exploration view for genres and durable playback states."""
from __future__ import annotations

import flet as ft


class OrganizeView:
    """Organize one loaded SQLite catalog without scanning or contacting AniList."""

    @staticmethod
    def build(page: ft.Page, library, on_select_anime, on_back, on_open_settings):
        catalog = []
        selected_genre, selected_state, selected_sort = ["Todos"], ["Todos"], ["Mais recentes"]
        mode = ["overview"]

        content = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=14)
        status = ft.Text("Carregando sua biblioteca local…", color="#AAA7B6", size=12)

        def artwork(source, height, icon_size=28):
            fallback = ft.Container(
                height=height, bgcolor="#292737", border_radius=14, alignment=ft.Alignment(0, 0),
                content=ft.Icon(ft.Icons.MOVIE_OUTLINED, color="#AAA7B6", size=icon_size),
            )
            return ft.Image(src=source, height=height, fit=ft.ImageFit.COVER, border_radius=14,
                            error_content=fallback) if source else fallback

        def episodes(anime):
            return [episode for season in anime.get("seasons", []) for episode in season.get("episodes", [])]

        def progress(anime):
            current = anime.get("current_episode") or {}
            duration = float(current.get("duration") or 0)
            return min(float(current.get("progress") or 0) / duration, 1.0) if duration > 0 else None

        def anime_card(anime):
            all_episodes = episodes(anime)
            available = [episode for episode in all_episodes if not episode.get("missing")]
            watched = sum(bool(episode.get("watched")) for episode in available)
            ratio = progress(anime)
            cover = (anime.get("meta") or {}).get("cover_cache") or (anime.get("meta") or {}).get("cover_url")
            subtitle = f"{watched}/{len(available)} assistidos" if available else "Sem arquivos disponíveis"
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
                                   visible=ratio is not None and ratio > 0 and not (anime.get("current_episode") or {}).get("watched")),
                ], spacing=5),
            )

        def header(title, back_handler=None):
            left = ft.IconButton(icon=ft.Icons.ARROW_BACK, icon_color="#FFFFFF", tooltip="Voltar",
                                 on_click=lambda _: back_handler()) if back_handler else ft.IconButton(
                                     icon=ft.Icons.HOME_OUTLINED, icon_color="#FFFFFF", tooltip="Início",
                                     on_click=lambda _: on_back())
            return ft.Row([
                left,
                ft.Column([ft.Text(title, size=21, weight=ft.FontWeight.BOLD, color="#F7F5FA"),
                           ft.Text("Explore sua biblioteca local", size=11, color="#AAA7B6")], spacing=1, expand=True),
                ft.IconButton(icon=ft.Icons.SETTINGS_OUTLINED, icon_color="#FFFFFF", tooltip="Configurações",
                              on_click=lambda _: on_open_settings()),
            ])

        def state_button(label, count):
            icons = {"Todos": ft.Icons.GRID_VIEW, "Favoritos": ft.Icons.STAR,
                     "Em andamento": ft.Icons.PLAY_CIRCLE_OUTLINE, "Concluídos": ft.Icons.CHECK_CIRCLE_OUTLINE}
            return ft.Container(
                width=155, padding=12, bgcolor="#252331", border_radius=14, ink=True,
                on_click=lambda _, value=label: open_collection("Todos", value),
                content=ft.Column([
                    ft.Icon(icons[label], color="#E50914", size=23),
                    ft.Text(label, color="#F7F5FA", size=12, weight=ft.FontWeight.BOLD, max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(f"{count} anime{'s' if count != 1 else ''}", color="#AAA7B6", size=10),
                ], spacing=5),
            )

        def genre_card(item):
            label, count, cover = item["name"], item["count"], item.get("cover")
            visual = artwork(cover, 104, 30)
            return ft.Container(
                width=170, height=142, border_radius=14, clip_behavior=ft.ClipBehavior.HARD_EDGE,
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
            return ft.Column([
                ft.Icon(ft.Icons.VIDEO_LIBRARY_OUTLINED, color="#AAA7B6", size=46),
                ft.Text("Seu catálogo está vazio", color="#F7F5FA", size=17, weight=ft.FontWeight.BOLD),
                ft.Text("Adicione uma pasta com animes nas configurações para começar.", color="#AAA7B6", size=12,
                        text_align=ft.TextAlign.CENTER),
                ft.FilledButton("Abrir configurações", icon=ft.Icons.SETTINGS, on_click=lambda _: on_open_settings()),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8)

        def open_collection(genre, state):
            selected_genre[0], selected_state[0], mode[0] = genre, state, "collection"
            render()

        def back_to_overview():
            mode[0] = "overview"
            render()

        def filter_chip(label):
            active = label == selected_state[0]
            return ft.OutlinedButton(
                label, on_click=lambda _, value=label: open_collection(selected_genre[0], value),
                style=ft.ButtonStyle(color="#FFFFFF", bgcolor="#E50914" if active else "#252836",
                                     side=ft.BorderSide(0, "#00000000"),
                                     shape=ft.RoundedRectangleBorder(radius=18),
                                     padding=ft.Padding(left=13, right=13, top=2, bottom=2)),
            )

        def render_overview():
            summary = library.organize_summary(catalog)
            content.controls.extend([header("Organizar"), status])
            if not catalog:
                content.controls.append(empty_catalog())
                return
            content.controls.extend([
                ft.Text("CATEGORIAS", size=12, weight=ft.FontWeight.BOLD, color="#AAA7B6"),
                ft.Row([state_button(item["name"], item["count"]) for item in summary["states"]],
                       scroll=ft.ScrollMode.AUTO, spacing=10),
            ])
            if summary["genres"]:
                content.controls.extend([
                    ft.Text("GÊNEROS", size=12, weight=ft.FontWeight.BOLD, color="#AAA7B6"),
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
                    content=ft.Column([
                        ft.Icon(ft.Icons.FILTER_LIST_OFF, color="#AAA7B6", size=38),
                        ft.Text("Nenhum anime nesta categoria.", color="#AAA7B6", size=13),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6), alignment=ft.Alignment(0, 0), height=170,
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
                status.value = ""
            except Exception as exc:
                status.value = f"Não foi possível carregar a biblioteca: {exc}"
            render()

        page.run_thread(load_catalog)
        return ft.Container(content=content, padding=ft.Padding(left=16, right=16, top=18, bottom=8), bgcolor="#16151F")
