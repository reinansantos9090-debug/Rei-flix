import flet as ft
from core.ui import ACCENT, BACKGROUND, PAGE_PADDING, RADIUS, SUCCESS, SURFACE, TEXT, TEXT_MUTED, chip_style, empty_state, media_artwork, section_title


class HomeView:
    """Local-library home. Data is loaded once, then filtered in memory."""

    @staticmethod
    def build(page: ft.Page, library, on_select_anime, on_open_settings, on_play_episode, on_open_organize=None,
              view_state=None):
        catalog, continuing = [], []
        view_state = view_state if view_state is not None else {}
        selected_state = [view_state.get("state", "Todos")]
        selected_genre = [view_state.get("genre", "Todos")]
        selected_sort = [view_state.get("sort", "Mais recentes")]
        search_visible = [bool(view_state.get("search_visible", False)]

        def save_view_state():
            view_state.update(state=selected_state[0], genre=selected_genre[0], sort=selected_sort[0],
                              search_visible=search_visible[0], query=search.value or "")

        grid = ft.GridView(
            expand=True, max_extent=168, child_aspect_ratio=.57, spacing=14,
            run_spacing=20, padding=ft.Padding.only(bottom=24),
        )
        status = ft.Row([ft.ProgressRing(width=16, height=16, stroke_width=2, color=ACCENT), ft.Text("Carregando biblioteca local…", color=TEXT_MUTED, size=12)], spacing=8)
        genres_row = ft.Row(scroll=ft.ScrollMode.AUTO, spacing=8)
        state_row = ft.Row(scroll=ft.ScrollMode.AUTO, spacing=8)
        library_label = ft.Text("MINHA BIBLIOTECA", size=13, weight=ft.FontWeight.BOLD, color="#AAA7B6")
        feedback = ft.Container(visible=False)
        search = ft.TextField(
            value=view_state.get("query", ""), visible=search_visible[0], hint_text="Buscar na sua biblioteca", prefix_icon=ft.Icons.SEARCH,
            border_radius=RADIUS, border_width=0, bgcolor=SURFACE,
            color=TEXT, content_padding=12, text_size=14,
        )
        sort = ft.Dropdown(
            value=selected_sort[0], width=185, dense=True, text_size=12, color="#F5F5F7",
            bgcolor=SURFACE, border_color="#39364B", border_radius=RADIUS,
            options=[ft.dropdown.Option(key=value, text=value) for value in
                     ["Mais recentes", "Assistidos recentemente", "Nome A-Z", "Nome Z-A"]],
        )
        continue_row = ft.Row(scroll=ft.ScrollMode.AUTO, spacing=10)
        continuation_section = ft.Container(
            content=ft.Column([
                ft.Text("CONTINUAR ASSISTINDO", size=13, weight=ft.FontWeight.BOLD, color="#AAA7B6"),
                continue_row,
            ], spacing=10),
            visible=False,
        )

        def ratio(item):
            duration = float(item.get("duration") or 0)
            return min(float(item.get("progress") or 0) / duration, 1.0) if duration else 0.0

        def chip(label, active, handler, icon=None):
            return ft.OutlinedButton(
                label, icon=icon, on_click=handler,
                style=chip_style(active),
            )

        def artwork(source, height, icon_size=34):
            return media_artwork(source, height, icon_size=icon_size)

        def play_continuation(item):
            on_play_episode(
                item["path"],
                f"{item.get('anime_title', 'Anime local')} • T{item.get('season', 1)} E{item.get('number') if item.get('number') is not None else '—'}",
                progress_seconds=item.get("progress", 0),
            )

        def render_continue():
            continue_row.controls.clear()
            continuation_section.visible = bool(continuing)
            if not continuing:
                return
            for item in continuing[:8]:
                progress = ratio(item)
                episode_label = f"T{item.get('season', 1)} • E{item.get('number') if item.get('number') is not None else '—'}"
                card = ft.Container(
                    width=270, bgcolor=SURFACE, border_radius=RADIUS, padding=10, ink=True,
                    on_click=lambda _, entry=item: play_continuation(entry),
                    content=ft.Row([
                        ft.Container(content=artwork(item.get("cover"), 96, 26), width=68, clip_behavior=ft.ClipBehavior.HARD_EDGE),
                        ft.Column([
                            ft.Text(item.get("anime_title", "Anime local"), color=TEXT, size=13, weight=ft.FontWeight.BOLD, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                            ft.Text(episode_label, color=TEXT_MUTED, size=11),
                            ft.ProgressBar(value=progress, color=ACCENT, bgcolor="#454252", height=4, visible=bool(item.get("duration"))),
                            ft.Text(f"{int(progress * 100)}% assistido" if item.get("duration") else "Progresso indisponível", color=TEXT_MUTED, size=10),
                        ], spacing=5, expand=True),
                    ], spacing=9),
                )
                continue_row.controls.append(card)

        def render_genres():
            genres_row.controls.clear()
            genres = {str(genre) for anime in catalog for genre in anime.get("genres", []) if genre}
            for genre in ["Todos", *sorted(genres, key=str.casefold)]:
                genres_row.controls.append(chip(genre, genre == selected_genre[0], lambda _, value=genre: select_genre(value)))

        def card(anime):
            episodes = [episode for season in anime.get("seasons", []) for episode in season.get("episodes", [])]
            available = [episode for episode in episodes if not episode.get("missing")]
            watched = sum(bool(episode.get("watched")) for episode in available)
            current = anime.get("current_episode") or {}
            progress = ratio(current)
            cover = anime.get("meta", {}).get("cover_cache") or anime.get("meta", {}).get("cover_url")
            subtitle = f"{len(available)} episódios" if len(available) == len(episodes) else f"{len(available)}/{len(episodes)} disponíveis"
            status = "Concluído" if available and watched == len(available) else (f"{watched} vistos" if watched else subtitle)
            indicators = []
            if anime.get("favorite"):
                indicators.append(ft.Container(content=ft.Icon(ft.Icons.STAR, color="#FFD54F", size=16), top=7, right=7, bgcolor="#181720CC", border_radius=12, padding=4))
            if current.get("watched"):
                indicators.append(ft.Container(content=ft.Icon(ft.Icons.CHECK, color="#FFFFFF", size=15), bottom=7, right=7, bgcolor="#27845ACC", border_radius=12, padding=4))
            return ft.Container(
                ink=True, on_click=lambda _, item=anime: on_select_anime(item), border_radius=14,
                content=ft.Column([
                    ft.Stack([ft.Container(content=artwork(cover, 198), height=198), *indicators]),
                    ft.Text(anime.get("main_title", "Anime local"), size=13, weight=ft.FontWeight.BOLD, color=TEXT, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(status, size=11, color=TEXT_MUTED, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.ProgressBar(value=progress, color=ACCENT, bgcolor="#3C3948", height=3, visible=progress > 0 and not current.get("watched")),
                ], spacing=5),
            )

        def render_library():
            grid.controls.clear()
            filtered = library.browse_catalog(catalog, search.value or "", selected_state[0], selected_genre[0], selected_sort[0])
            if not catalog:
                library_label.value = "SUA BIBLIOTECA"
                feedback.content = empty_state(ft.Icons.VIDEO_LIBRARY_OUTLINED, "Sua biblioteca local está vazia", "Adicione uma pasta com animes nas configurações para começar.", ft.FilledButton("Abrir configurações", icon=ft.Icons.SETTINGS, on_click=lambda _: on_open_settings()))
                feedback.visible = True
            elif not filtered:
                library_label.value = "MINHA BIBLIOTECA"
                feedback.content = empty_state(ft.Icons.SEARCH_OFF, "Nenhum resultado", "Tente alterar a busca, os filtros ou o gênero selecionado.")
                feedback.visible = True
            else:
                library_label.value = f"MINHA BIBLIOTECA • {len(filtered)}"
                feedback.visible = False
                grid.controls.extend(card(anime) for anime in filtered)
            page.update()

        def select_state(value):
            selected_state[0] = value
            save_view_state()
            render_states(); render_library()

        def select_genre(value):
            selected_genre[0] = value
            save_view_state()
            render_genres(); render_library()

        def render_states():
            state_row.controls.clear()
            for label, icon in [("Todos", ft.Icons.GRID_VIEW), ("Favoritos", ft.Icons.STAR), ("Em andamento", ft.Icons.PLAY_CIRCLE_OUTLINE), ("Concluídos", ft.Icons.CHECK_CIRCLE_OUTLINE)]:
                state_row.controls.append(chip(label, label == selected_state[0], lambda _, value=label: select_state(value), icon))

        def toggle_search(_):
            search_visible[0] = not search_visible[0]
            search.visible = search_visible[0]
            if not search_visible[0]:
                search.value = ""
            save_view_state()
            render_library()

        def on_search(event):
            if event.control.value == "":
                search.value = ""
            save_view_state()
            render_library()

        def on_sort(event):
            selected_sort[0] = event.control.value or "Mais recentes"
            save_view_state()
            render_library()

        def load_catalog():
            status.controls = [ft.ProgressRing(width=16, height=16, stroke_width=2, color=ACCENT), ft.Text("Carregando biblioteca local…", color=TEXT_MUTED, size=12)]
            status.visible = True
            page.update()
            def work():
                nonlocal catalog, continuing
                try:
                    # Home is strictly a local presentation. Scanning belongs to
                    # the explicit library/SAF flow and must not trigger AniList
                    # work every time the user returns to this screen.
                    catalog = library.catalog()
                    continuing = library.continue_watching(limit=8)
                    status.visible = False
                except Exception:
                    catalog, continuing = [], []
                    status.controls = [
                        ft.Icon(ft.Icons.ERROR_OUTLINE, color="#FFB4AB", size=18),
                        ft.Text("Não foi possível carregar sua biblioteca local.", color="#FFB4AB", size=12),
                        ft.TextButton("Tentar novamente", on_click=lambda _: load_catalog()),
                    ]
                    status.visible = True
                render_genres(); render_states(); render_continue(); render_library()
            page.run_thread(work)

        search.on_change = on_search
        search.on_submit = on_search
        sort.on_select = on_sort
        header = ft.Row([
            ft.Row([ft.Container(content=ft.Icon(ft.Icons.PLAY_CIRCLE_FILLED, color=ACCENT, size=31), bgcolor=SURFACE, border_radius=12, padding=5), ft.Text("ReiFlix", size=23, weight=ft.FontWeight.BOLD, color=TEXT)], spacing=9),
            ft.Row([ft.IconButton(icon=ft.Icons.SEARCH, icon_color="#FFFFFF", tooltip="Pesquisar", on_click=toggle_search), ft.IconButton(icon=ft.Icons.DASHBOARD_OUTLINED, icon_color="#FFFFFF", tooltip="Organizar", visible=on_open_organize is not None, on_click=lambda _: on_open_organize() if on_open_organize else None), ft.IconButton(icon=ft.Icons.SETTINGS_OUTLINED, icon_color="#FFFFFF", tooltip="Configurações", on_click=lambda _: on_open_settings())], spacing=0),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        layout = ft.Column([
            header, search,
            ft.Text("Sua biblioteca local, do seu jeito", size=13, color=TEXT_MUTED),
            status,
            continuation_section,
            section_title("Filtros", ft.Icons.TUNE), state_row, genres_row,
            ft.Row([library_label, sort], alignment=ft.MainAxisAlignment.SPACE_BETWEEN), feedback, grid,
        ], expand=True, spacing=14)

        status.visible = True
        load_catalog()
        return ft.Container(content=layout, padding=ft.Padding(left=PAGE_PADDING, right=PAGE_PADDING, top=18, bottom=8), bgcolor=BACKGROUND)
