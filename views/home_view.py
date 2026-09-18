import flet as ft


class HomeView:
    @staticmethod
    def build(page: ft.Page, library, on_select_anime, on_open_settings):
        grid = ft.GridView(expand=True, runs_count=3, max_extent=150, child_aspect_ratio=.62, spacing=14, run_spacing=18)
        status = ft.Text("Carregando biblioteca…", color="#9DA3B4", size=12)
        all_animes, active_genre, only_favs = [], ["Todos"], [False]
        genres_row = ft.Row(scroll=ft.ScrollMode.AUTO, spacing=8)

        def render_grid(filter_text=""):
            grid.controls.clear(); q=filter_text.strip().casefold()
            for anime in all_animes:
                title=anime['main_title']
                if q and q not in title.casefold(): continue
                if active_genre[0] != "Todos" and active_genre[0] not in anime['genres']: continue
                if only_favs[0]: continue # favorito ainda não possui persistência; o filtro não oculta a biblioteca
                meta=anime['meta']; cover=meta.get('cover_cache') or meta.get('cover_url')
                art=ft.Image(src=cover,fit=ft.ImageFit.COVER,border_radius=12) if cover else ft.Container(bgcolor="#252836",border_radius=12,alignment=ft.alignment.center,content=ft.Icon(ft.Icons.MOVIE_OUTLINED,color="#9DA3B4",size=32))
                grid.controls.append(ft.GestureDetector(on_tap=lambda _,a=anime:on_select_anime(a),content=ft.Column([ft.Stack([ft.Container(content=art,height=205,border_radius=12),ft.Container(content=ft.Icon(ft.Icons.PLAY_CIRCLE_FILL,color="#FFFFFF",size=34),right=8,bottom=8)]),ft.Text(title,size=12,weight=ft.FontWeight.BOLD,max_lines=1,overflow=ft.TextOverflow.ELLIPSIS,color="#F5F5F7"),ft.Text(" • ".join(anime['genres'][:2]) or "Local",size=10,color="#9DA3B4",max_lines=1)],spacing=5)))
            if not grid.controls:
                grid.controls.append(ft.Text("Nenhum anime ainda. Adicione uma pasta nas configurações.",color="#9DA3B4"))
            page.update()
        search = ft.TextField(hint_text="Pesquisar na biblioteca",prefix_icon=ft.Icons.SEARCH,border_radius=14,bgcolor="#252836",color=ft.Colors.WHITE,content_padding=10,text_size=13,on_change=lambda e:render_grid(e.control.value))
        def render_genres():
            genres_row.controls.clear()
            for genre in ["Todos"]+sorted({g for a in all_animes for g in a['genres']}):
                genres_row.controls.append(ft.OutlinedButton(genre,on_click=lambda _,g=genre:select_genre(g),style=ft.ButtonStyle(color="#FFFFFF",bgcolor="#E50914" if genre==active_genre[0] else "#252836",shape=ft.RoundedRectangleBorder(radius=18),padding=ft.Padding(left=16,right=16,top=0,bottom=0))))
        def select_genre(genre): active_genre[0]=genre; render_genres(); render_grid(search.value or "")
        def refresh():
            status.value="Escaneando biblioteca…"; page.update()
            def work():
                nonlocal all_animes
                scan_result=library.scan(lambda value:setattr(status,'value',value)); all_animes=scan_result.catalog
                render_genres(); render_grid(search.value or "")
            page.run_thread(work)
        def toggle(_): only_favs[0]=not only_favs[0]; render_grid(search.value or "")
        layout=ft.Column([ft.Row([ft.Row([ft.Icon(ft.Icons.PLAY_CIRCLE_FILLED,color="#E50914",size=30),ft.Text("ReiFlix",size=22,weight=ft.FontWeight.BOLD,color="#F5F5F7")]),ft.Row([ft.IconButton(icon=ft.Icons.STAR,icon_color=ft.Colors.WHITE,tooltip="Favoritos",on_click=toggle),ft.IconButton(icon=ft.Icons.REFRESH,icon_color="#FFFFFF",tooltip="Atualizar biblioteca",on_click=lambda _:refresh()),ft.IconButton(icon=ft.Icons.SETTINGS,icon_color="#FFFFFF",tooltip="Configurações",on_click=lambda _:on_open_settings())])],alignment=ft.MainAxisAlignment.SPACE_BETWEEN),ft.Text("Sua biblioteca local, do seu jeito",size=13,color="#9DA3B4"),search,genres_row,status,ft.Text("ORGANIZAR • GÊNERO",size=12,weight=ft.FontWeight.BOLD,color="#9DA3B4"),ft.Text("Selecione um gênero acima para filtrar títulos locais. Ano, status e progresso aparecem nos detalhes.",size=11,color="#9DA3B4"),ft.Text("TODOS OS TÍTULOS",size=12,weight=ft.FontWeight.BOLD,color="#9DA3B4"),grid],expand=True)
        refresh()
        return ft.Container(content=layout,padding=ft.Padding(left=16,right=16,top=18,bottom=12),bgcolor="#16151F")
