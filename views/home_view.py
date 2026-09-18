import flet as ft


class HomeView:
    """Local-library home. Data is loaded once, then filtered in memory."""

    @staticmethod
    def build(page: ft.Page, library, on_select_anime, on_open_settings, on_play_episode):
        catalog, continuing = [], []
        selected_state, selected_genre, selected_sort = ["Todos"], ["Todos"], ["Mais recentes"]
        search_visible = [False]

        grid = ft.GridView(
            expand=True, max_extent=168, child_aspect_ratio=.57, spacing=14,
            run_spacing=20, padding=ft.Padding.only(bottom=24),
        )
        status = ft.Text("Carregando biblioteca local…", color="#AAA7B6", size=11)
        genres_row = ft.Row(scroll=ft.ScrollMode.AUTO, spacing=8)
        state_row = ft.Row(scroll=ft.ScrollMode.AUTO, spacing=8)
        library_label = ft.Text("MINHA BIBLIOTECA", size=13, weight=ft.FontWeight.BOLD, color="#AAA7B6")
        feedback = ft.Container(visible=False)
        search = ft.TextField(
            visible=False, hint_text="Buscar na sua biblioteca", prefix_icon=ft.Icons.SEARCH,
            suffix_icon=ft.Icons.CLOSE, border_radius=14, border_width=0, bgcolor="#252836",
            color="#FFFFFF", content_padding=12, text_size=14,
        )
        sort = ft.Dropdown(
            value="Mais recentes", width=185, dense=True, text_size=12, color="#F5F5F7",
            bgcolor="#252836", border_color="#39364B", border_radius=12,
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
                style=ft.ButtonStyle(
                    color="#FFFFFF", bgcolor="#E50914" if active else "#252836",
                    side=ft.BorderSide(0, "#00000000"),
                    shape=ft.RoundedRectangleBorder(radius=18),
                    padding=ft.Padding(left=15, right=15, top=2, bottom=2),
                ),
            )

        def artwork(source, height, icon_size=34):
            if source:
                return ft.Image(src=source, fit=ft.ImageFit.COVER, height=height, border_radius=14)
            return ft.Container(
                height=height, alignment=ft.alignment.center, border_radius=14, bgcolor="#292737",
                content=ft.Icon(ft.Icons.MOVIE_OUTLINED, color="#A8A4B7", size=icon_size),
            )

        def play_continuation(item):
            on_play_episode(item["path"], item["file_name"], progress_seconds=item.get("progress", 0))

        def render_continue():
            continue_row.controls.clear()
            continuation_section.visible = bool(continuing)
            if not continuing:
                return
            for item in continuing[:8]:
                progress = ratio(item)
                episode_label = f"T{item.get('season', 1)} • E{item.get('number') if item.get('number') is not None else '—'}"
                card = ft.Container(
                    width=260, bgcolor="#242331", border_radius=14, padding=8, ink=True,
                    on_click=lambda _, entry=item: play_continuation(entry),
                    content=ft.Row([
                        ft.Container(content=artwork(item.get("cover"), 96, 26), width=68, clip_behavior=ft.ClipBehavior.HARD_EDGE),
                        ft.Column([
                            ft.Text(item.get("anime_title", "Anime local"), color="#F7F5FA", size=13, weight=ft.FontWeight.BOLD, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                            ft.Text(episode_label, color="#B4B0C0", size=11),
                            ft.ProgressBar(value=progress, color="#E50914", bgcolor="#454252", height=4),
                            ft.Text(f"{int(progress * 100)}% assistido", color="#B4B0C0", size=10),
                        ], spacing=5, expand=True),
                    ], spacing=9),
                )
                continue_row.controls.append(card)

        def render_genres():
            genres_row.controls.clear()
            for genre in ["Todos", *sorted({genre for anime in catalog for genre in anime.get("genres", [])})]:
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
                    ft.Text(anime.get("main_title", "Anime local"), size=13, weight=ft.FontWeight.BOLD, color="#F7F5FA", max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(status, size=10, color="#AAA7B6", max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.ProgressBar(value=progress, color="#E50914", bgcolor="#3C3948", height=3, visible=progress > 0 and not current.get("watched")),
                ], spacing=5),
            )

        def render_library():
            grid.controls.clear()
            filtered = library.browse_catalog(catalog, search.value or "", selected_state[0], selected_genre[0], selected_sort[0])
            if not catalog:
                library_label.value = "SUA BIBLIOTECA"
                feedback.content = ft.Column([
                    ft.Icon(ft.Icons.VIDEO_LIBRARY_OUTLINED, color="#AAA7B6", size=42),
                    ft.Text("Sua biblioteca local está vazia", color="#F7F5FA", size=16, weight=ft.FontWeight.BOLD),
                    ft.Text("Adicione uma pasta com animes nas configurações para começar.", color="#AAA7B6", size=12, text_align=ft.TextAlign.CENTER),
                    ft.FilledButton("Abrir configurações", icon=ft.Icons.SETTINGS, on_click=lambda _: on_open_settings()),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8)
                feedback.visible = True
            elif not filtered:
                library_label.value = "MINHA BIBLIOTECA"
                feedback.content = ft.Column([
                    ft.Icon(ft.Icons.SEARCH_OFF, color="#AAA7B6", size=36),
                    ft.Text("Nenhum anime encontrado neste filtro.", color="#AAA7B6", size=13),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6)
                feedback.visible = True
            else:
                library_label.value = f"MINHA BIBLIOTECA • {len(filtered)}"
                feedback.visible = False
                grid.controls.extend(card(anime) for anime in filtered)
            page.update()

        def select_state(value):
            selected_state[0] = value
            render_states(); render_library()

        def select_genre(value):
            selected_genre[0] = value
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
            render_library()

        def on_search(event):
            if event.control.value == "":
                search.value = ""
            render_library()

        def on_sort(event):
            selected_sort[0] = event.control.value or "Mais recentes"
            render_library()

        def load_catalog():
            status.value = "Carregando biblioteca local…"
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
                    status.value = ""
                    status.visible = False
                except Exception as exc:
                    catalog, continuing = [], []
                    status.value = f"Não foi possível carregar a biblioteca: {exc}"
                    status.visible = True
                render_genres(); render_states(); render_continue(); render_library()
            page.run_thread(work)

        search.on_change = on_search
        search.on_submit = on_search
        sort.on_select = on_sort
        header = ft.Row([
            ft.Row([ft.Container(content=ft.Icon(ft.Icons.PLAY_CIRCLE_FILLED, color="#E50914", size=31), bgcolor="#292737", border_radius=12, padding=5), ft.Text("ReiFlix", size=23, weight=ft.FontWeight.BOLD, color="#F7F5FA")], spacing=9),
            ft.Row([ft.IconButton(icon=ft.Icons.SEARCH, icon_color="#FFFFFF", tooltip="Pesquisar", on_click=toggle_search), ft.IconButton(icon=ft.Icons.SETTINGS_OUTLINED, icon_color="#FFFFFF", tooltip="Configurações", on_click=lambda _: on_open_settings())], spacing=0),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        layout = ft.Column([
            header, search,
            ft.Text("Sua biblioteca local, do seu jeito", size=13, color="#AAA7B6"),
            status,
            continuation_section,
            ft.Text("FILTROS", size=12, weight=ft.FontWeight.BOLD, color="#AAA7B6"), state_row, genres_row,
            ft.Row([library_label, sort], alignment=ft.MainAxisAlignment.SPACE_BETWEEN), feedback, grid,
        ], expand=True, spacing=14)

        # Refresh is intentionally delayed to the end so all controls exist.
        status.visible = True
        load_catalog()
        return ft.Container(content=layout, padding=ft.Padding(left=16, right=16, top=18, bottom=8), bgcolor="#16151F")
