import os
import flet as ft
from core.consumption import consumption_state, progress_ratio
from core.ui import ACCENT, BACKGROUND, PAGE_PADDING, RADIUS, SURFACE, TEXT, TEXT_MUTED, chip_style, empty_state, media_artwork, section_title, count_label


class HomeView:
    """Local-library home. Data is loaded once, then filtered in memory."""

    @staticmethod
    def build(page: ft.Page, library, on_select_anime, on_open_settings, on_play_episode, on_open_organize=None,
              view_state=None, on_request_thumbnail=None):
        catalog, continuing, home_data = [], [], {}
        view_state = view_state if view_state is not None else {}
        selected_state = [view_state.get("state", "Todos")]
        selected_genre = [view_state.get("genre", "Todos")]
        selected_sort = [view_state.get("sort", "Mais recentes")]
        selected_media_type = [view_state.get("media_type", "Todos")]
        selected_tag = [view_state.get("tag", "Todos")]
        selected_season = [view_state.get("season", "Todos")]
        selected_episode_type = [view_state.get("episode_type", "Todos")]
        selected_availability = [view_state.get("availability", "Todos")]
        selected_metadata = [view_state.get("metadata", "Todos")]
        selected_artwork = [view_state.get("artwork", "Todos")]
        search_visible = [bool(view_state.get("search_visible", False))]

        def save_view_state():
            view_state.update(
                state=selected_state[0], genre=selected_genre[0], sort=selected_sort[0],
                media_type=selected_media_type[0], tag=selected_tag[0],
                season=selected_season[0], episode_type=selected_episode_type[0],
                availability=selected_availability[0], metadata=selected_metadata[0],
                artwork=selected_artwork[0], search_visible=search_visible[0],
                query=search.value or "",
            )

        grid = ft.Row(
            wrap=True, spacing=14, run_spacing=20,
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
                     ["Mais recentes", "Assistidos recentemente", "Progresso", "Episódio",
                      "Temporada + episódio", "Modificação", "Duração", "Tamanho",
                      "Favoritos primeiro", "Fixados primeiro", "Nome A-Z", "Nome Z-A"]],
        )
        media_type = ft.Dropdown(value=selected_media_type[0], width=155, dense=True, text_size=12, color="#F5F5F7",
                                 bgcolor=SURFACE, border_color="#39364B", border_radius=RADIUS,
                                 options=[ft.dropdown.Option("Todos", "Tipo")] + [ft.dropdown.Option(v, v) for v in
                                         ["Série/Anime", "Filme", "Especial", "Episódio"]])
        tag = ft.Dropdown(value=selected_tag[0], width=155, dense=True, text_size=12, color="#F5F5F7",
                          bgcolor=SURFACE, border_color="#39364B", border_radius=RADIUS,
                          options=[ft.dropdown.Option("Todos", "Etiqueta")])
        season = ft.Dropdown(value=selected_season[0], width=145, dense=True, text_size=12, color="#F5F5F7",
                             bgcolor=SURFACE, border_color="#39364B", border_radius=RADIUS,
                             options=[ft.dropdown.Option("Todos", "Temporada")])
        episode_type = ft.Dropdown(value=selected_episode_type[0], width=150, dense=True, text_size=12, color="#F5F5F7",
                                   bgcolor=SURFACE, border_color="#39364B", border_radius=RADIUS,
                                   options=[ft.dropdown.Option("Todos", "Tipo de episódio")])
        availability = ft.Dropdown(value=selected_availability[0], width=145, dense=True, text_size=12, color="#F5F5F7",
                                   bgcolor=SURFACE, border_color="#39364B", border_radius=RADIUS,
                                   options=[ft.dropdown.Option(v, v) for v in ["Todos", "Disponível", "Com missing", "Sem missing"]])
        metadata_filter = ft.Dropdown(value=selected_metadata[0], width=140, dense=True, text_size=12, color="#F5F5F7",
                                      bgcolor=SURFACE, border_color="#39364B", border_radius=RADIUS,
                                      options=[ft.dropdown.Option(v, v) for v in ["Todos", "Disponível", "Ausente"]])
        artwork_filter = ft.Dropdown(value=selected_artwork[0], width=140, dense=True, text_size=12, color="#F5F5F7",
                                     bgcolor=SURFACE, border_color="#39364B", border_radius=RADIUS,
                                     options=[ft.dropdown.Option(v, v) for v in ["Todos", "Disponível", "Ausente"]])
        continue_row = ft.Row(scroll=ft.ScrollMode.AUTO, spacing=10)
        section_rows = {}

        def home_card(item, action=None, wide=False, episode=False):
            meta = item.get("meta") or {}
            cover = item.get("cover") or meta.get("cover_cache") or meta.get("cover_url")
            remote_cover = bool(isinstance(cover, str) and cover.startswith(("http://", "https://")))
            local_cover_missing = bool(
                cover and isinstance(cover, str) and
                not remote_cover and not cover.startswith("content://") and
                not os.path.isfile(cover)
            )
            if (not cover or local_cover_missing or remote_cover) and library is not None and item.get("id") is not None:
                try:
                    entity = "movie" if item.get("media_kind") == "movie" else "anime"
                    resolved = library.resolve_artwork(entity, item.get("id"), "poster", allow_network=False)
                    cover = (resolved or {}).get("local_path")
                except Exception:
                    resolved = None
                if not cover:
                    cover = None
            if not cover and on_request_thumbnail:
                candidate = item.get("episode") or item.get("current_episode")
                if not candidate and item.get("seasons"):
                    candidate = next((ep for season in item.get("seasons", []) for ep in season.get("episodes", []) if ep.get("path") and not ep.get("missing")), None)
                if candidate:
                    on_request_thumbnail(candidate)
            if episode:
                title = item.get("anime_title") or item.get("title") or "Mídia local"
                subtitle = item.get("episode_title") or (f"T{item.get('season')} E{item.get('number')}" if item.get("season") is not None else "Episódio")
            else:
                title = item.get("main_title") or item.get("anime_title") or meta.get("title") or "Mídia local"
                subtitle = "Filme" if item.get("media_kind") == "movie" else (count_label(item.get("available_count", 0), "episódio") if item.get("available_count") else "")
            return ft.Container(
                width=170 if not wide else 220, ink=True, border_radius=RADIUS,
                on_click=(lambda _, value=item: action(value)) if action else None,
                content=ft.Column([
                    ft.Container(content=media_artwork(cover, 220 if not wide else 170, width=170 if not wide else 220, icon_size=34),
                                 height=220 if not wide else 170, clip_behavior=ft.ClipBehavior.HARD_EDGE),
                    ft.Text(title, size=13, weight=ft.FontWeight.BOLD, color=TEXT, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(subtitle, size=11, color=TEXT_MUTED, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.ProgressBar(value=ratio(item), color=ACCENT, bgcolor="#3C3948", height=3,
                                   visible=consumption_state(item).value == "in_progress"),
                ], spacing=5)
            )

        def section(title, key, items, action=None, episode=False):
            row = ft.Row(scroll=ft.ScrollMode.AUTO, spacing=12)
            row.controls.extend(home_card(item, action=action, episode=episode) for item in items)
            section_rows[key] = row
            return ft.Container(content=ft.Column([
                ft.Text(title, size=15, weight=ft.FontWeight.BOLD, color=TEXT),
                row,
            ], spacing=9), visible=bool(items))


        continuation_section = ft.Container(
            content=ft.Column([
                ft.Text("CONTINUAR ASSISTINDO", size=13, weight=ft.FontWeight.BOLD, color="#AAA7B6"),
                continue_row,
            ], spacing=10),
            visible=False,
        )

        def ratio(item):
            return progress_ratio(item)

        def chip(label, active, handler, icon=None):
            return ft.OutlinedButton(
                label, icon=icon, on_click=handler,
                style=chip_style(active),
            )

        def artwork(source, height, icon_size=34):
            return media_artwork(source, height, icon_size=icon_size)

        def player_episode_title(anime_title, episode):
            if episode.get("episode_type") == "movie":
                return anime_title
            season = episode.get("season")
            number = episode.get("number")
            if season is not None and number is not None:
                return f"{anime_title} • T{int(season)} E{int(number)}"
            if season is not None:
                return f"{anime_title} • T{int(season)}"
            return anime_title

        def play_continuation(item):
            episode = item.get("episode", item)
            anime_title = (
                item.get("anime_title")
                or item.get("main_title")
                or item.get("title")
                or episode.get("anime_title")
                or "Reproduzir"
            )
            on_play_episode(
                episode["path"],
                player_episode_title(anime_title, episode),
                progress_seconds=episode.get("progress", 0) or 0,
            )

        catalog_by_id = {}
        
        def render_continue():
            continue_row.controls.clear()
            continuation_section.visible = bool(continuing)
            if not continuing:
                return
            for item in continuing[:8]:
                progress = ratio(item)
                episode_label = "FILME" if item.get("episode_type") == "movie" else f"T{item.get('season', 1)} • E{item.get('number') if item.get('number') is not None else '—'}"
                owner = catalog_by_id.get(item.get("anime_id"))
                continue_button = ft.OutlinedButton(
                    "Continuar", icon=ft.Icons.PLAY_ARROW,
                    on_click=lambda _, entry=item: play_continuation(entry),
                )
                details_button = ft.TextButton(
                    "Detalhes",
                    icon=ft.Icons.INFO_OUTLINE,
                    on_click=lambda _, entry=owner: on_select_anime(entry) if entry else None,
                )
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
                            ft.Row([continue_button, details_button], spacing=4),
                        ], spacing=5, expand=True),
                    ], spacing=9),
                )
                continue_row.controls.append(card)

        catalog_by_id = {}

        def render_genres():
            genres_row.controls.clear()
            genres = {str(genre) for anime in catalog for genre in anime.get("genres", []) if genre}
            for genre in ["Todos", *sorted(genres, key=str.casefold)]:
                genres_row.controls.append(chip(genre, genre == selected_genre[0], lambda _, value=genre: select_genre(value)))

        def card(anime):
            available_count = int(anime.get("available_count") or 0)
            completed = int(anime.get("watched_count") or 0)
            current = anime.get("current_episode") or {}
            current_state = consumption_state(current) if current else None
            progress = ratio(current)
            cover = anime.get("meta", {}).get("cover_cache") or anime.get("meta", {}).get("cover_url")
            content_count = int(anime.get("content_count") or 0)
            missing_count = int(anime.get("missing_count") or 0)
            subtitle = "Filme" if anime.get("media_kind") == "movie" else (
                count_label(available_count, "episódio") if missing_count == 0 else f"{available_count}/{content_count} disponíveis"
            )
            status = "Concluído" if available_count > 0 and missing_count == 0 and completed == available_count else (f"{completed} concluídos" if completed else subtitle)
            indicators = []
            if anime.get("favorite"):
                indicators.append(ft.Container(content=ft.Icon(ft.Icons.STAR, color="#FFD54F", size=16), top=7, right=7, bgcolor="#181720CC", border_radius=12, padding=4))
            if current_state and current_state.value in {"completed", "watched"}:
                indicators.append(ft.Container(content=ft.Icon(ft.Icons.CHECK, color="#FFFFFF", size=15), bottom=7, right=7, bgcolor="#27845ACC", border_radius=12, padding=4))
            return ft.Container(
                ink=True, on_click=lambda _, item=anime: on_select_anime(item), border_radius=14,
                content=ft.Column([
                    ft.Stack([ft.Container(content=artwork(cover, 198), height=198), *indicators]),
                    ft.Text(anime.get("main_title", "Anime local"), size=13, weight=ft.FontWeight.BOLD, color=TEXT, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(status, size=11, color=TEXT_MUTED, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.ProgressBar(value=progress, color=ACCENT, bgcolor="#3C3948", height=3, visible=current_state is not None and current_state.value == "in_progress"),
                ], spacing=5),
            )

        def render_library():
            grid.controls.clear()
            filtered = library.browse_catalog(
                catalog, search.value or "", selected_state[0], selected_genre[0], selected_sort[0],
                selected_tag[0], media_type=selected_media_type[0], season=selected_season[0],
                episode_type=selected_episode_type[0], availability=selected_availability[0],
                metadata=selected_metadata[0], artwork=selected_artwork[0],
            )
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

        def select_filter(target, value):
            target[0] = value
            save_view_state()
            render_library()

        media_type.on_select = lambda e: select_filter(selected_media_type, e.control.value or "Todos")
        tag.on_select = lambda e: select_filter(selected_tag, e.control.value or "Todos")
        season.on_select = lambda e: select_filter(selected_season, e.control.value or "Todos")
        episode_type.on_select = lambda e: select_filter(selected_episode_type, e.control.value or "Todos")
        availability.on_select = lambda e: select_filter(selected_availability, e.control.value or "Todos")
        metadata_filter.on_select = lambda e: select_filter(selected_metadata, e.control.value or "Todos")
        artwork_filter.on_select = lambda e: select_filter(selected_artwork, e.control.value or "Todos")

        def refresh_filter_options():
            options = library.search_options(catalog)
            tag.options = [ft.dropdown.Option("Todos", "Etiqueta"), ft.dropdown.Option("Sem etiqueta", "Sem etiqueta")] + [ft.dropdown.Option(v, v) for v in options["tags"]]
            season.options = [ft.dropdown.Option("Todos", "Temporada")] + [ft.dropdown.Option(str(v), f"Temporada {v}") for v in options["seasons"]]
            episode_type.options = [ft.dropdown.Option("Todos", "Tipo de episódio")] + [ft.dropdown.Option(v, v) for v in options["episode_types"]]
            if selected_tag[0] not in {"Todos", "Sem etiqueta", *options["tags"]}: selected_tag[0] = "Todos"
            if selected_season[0] not in {"Todos", *[str(v) for v in options["seasons"]]}: selected_season[0] = "Todos"
            if selected_episode_type[0] not in {"Todos", *options["episode_types"]}: selected_episode_type[0] = "Todos"
            tag.value = selected_tag[0]; season.value = selected_season[0]; episode_type.value = selected_episode_type[0]

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
                    catalog_by_id.clear()
                    catalog_by_id.update({anime.get("id"): anime for anime in catalog})
                    home_data = library.media_center_home(limit=12, catalog=catalog)
                    refresh_filter_options()
                    continuing = home_data.get("continue_watching", [])
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
            section("PRÓXIMO EPISÓDIO", "next_episode", home_data.get("next_episode", []), action=on_select_anime),
            section("RECENTEMENTE ADICIONADOS", "recently_added", home_data.get("recently_added", []), action=on_select_anime),
            section("RECENTEMENTE ASSISTIDOS", "recently_watched", home_data.get("recently_watched", []), episode=True),
            section("FAVORITOS", "favorites", home_data.get("favorites", []), action=on_select_anime),
            section("PINADOS", "pinned", home_data.get("pinned", []), action=on_select_anime),
            section("SÉRIES / ANIMES", "series", home_data.get("series", []), action=on_select_anime),
            section("FILMES", "movies", home_data.get("movies", []), action=on_select_anime),
            section("ESPECIAIS", "specials", home_data.get("specials", []), action=on_select_anime),
            section_title("Filtros", ft.Icons.TUNE), state_row, genres_row,
            ft.Row([library_label, sort], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Row([media_type, tag, season, episode_type], scroll=ft.ScrollMode.AUTO, spacing=8),
            ft.Row([availability, metadata_filter, artwork_filter], scroll=ft.ScrollMode.AUTO, spacing=8),
            feedback,
            grid,
            ft.Container(height=24),
        ], scroll=ft.ScrollMode.AUTO, expand=True, spacing=14)

        status.visible = True
        load_catalog()
        return ft.Container(
            content=layout,
            padding=ft.Padding(left=PAGE_PADDING, right=PAGE_PADDING, top=18, bottom=8),
            bgcolor=BACKGROUND,
            expand=True,
        )
