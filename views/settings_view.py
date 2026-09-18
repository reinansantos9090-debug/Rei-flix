import flet as ft

class SettingsView:
    @staticmethod
    def build(page, store, library, on_back, on_catalog_changed, on_login, on_logout, account):
        folders=ft.Column(spacing=4); status=ft.Text('',color='#9DA3B4',size=12)
        picker=ft.FilePicker(); page.services.append(picker)
        def notice(message): status.value=message; page.update()
        def render_folders():
            folders.controls.clear()
            for path in store.folders(): folders.controls.append(ft.Row([ft.Text(path,expand=True,size=12,color='#C7C5D0'),ft.IconButton(icon=ft.Icons.DELETE_OUTLINE,icon_color=ft.Colors.RED_300,on_click=lambda _,p=path:(store.remove_folder(p),render_folders(),notice('Pasta removida.')))]))
            if not folders.controls: folders.controls.append(ft.Text('Nenhuma pasta adicionada.',color='#9DA3B4'))
        async def add_folder(_):
            try: path=await picker.get_directory_path(dialog_title='Selecione a pasta dos animes')
            except Exception as exc: notice(f'O seletor de pasta não está disponível: {exc}'); return
            if not path: notice('Seleção de pasta cancelada.'); return
            store.add_folder(path); render_folders(); notice('Pasta adicionada. Toque em Atualizar biblioteca.'); on_catalog_changed()
        def scan(_):
            notice('Escaneando biblioteca…')
            def work():
                library.scan(notice); on_catalog_changed()
            page.run_thread(work)
        matches=ft.Column(spacing=8)
        def render_matches():
            matches.controls.clear()
            for pending in store.pending_matches():
                candidates=pending['candidates']
                if not candidates:
                    continue
                selector=ft.Dropdown(
                    options=[ft.dropdown.Option(key=str(item['id']),text=f"{(item.get('title') or {}).get('english') or (item.get('title') or {}).get('romaji') or 'Sem título'} ({int(item.get('match_score',0)*100)}%)") for item in candidates],
                    value=str(candidates[0]['id']), expand=True, text_size=12)
                def confirm(_, p=pending, field=selector):
                    selected=field.value
                    if not selected:
                        notice('Escolha um resultado do AniList antes de confirmar.'); return
                    library.resolve_match(p['lookup_title'],int(selected))
                    render_matches(); notice('Associação salva. Atualize a biblioteca para baixar a capa correta.')
                matches.controls.append(ft.Column([ft.Text(f"Confirmar: {pending['display_title']}",weight=ft.FontWeight.BOLD,color='#C7C5D0'),ft.Row([selector,ft.FilledButton('Usar',on_click=confirm)])]))
            if not matches.controls:
                matches.controls.append(ft.Text('Nenhuma identificação precisa de revisão.',color='#9DA3B4',size=12))
        logged=account.get('email')
        account_block=ft.Column([ft.Text(account.get('name') or account.get('email') or 'Você não está conectado.',color='#C7C5D0'),ft.FilledButton('Sair',icon=ft.Icons.LOGOUT,on_click=lambda _:on_logout()) if logged else ft.FilledButton('Entrar com Google',icon=ft.Icons.LOGIN,on_click=lambda _:on_login())])
        render_folders()
        render_matches()
        return ft.Container(padding=ft.Padding.all(16),bgcolor='#16151F',content=ft.Column([ft.Row([ft.IconButton(icon=ft.Icons.ARROW_BACK,on_click=lambda _:on_back(),icon_color=ft.Colors.WHITE),ft.Text('Configurações',size=20,weight=ft.FontWeight.BOLD,color=ft.Colors.WHITE)]),ft.Text('BIBLIOTECA',size=12,weight=ft.FontWeight.BOLD,color='#9DA3B4'),folders,ft.Row([ft.OutlinedButton('Adicionar pasta',icon=ft.Icons.CREATE_NEW_FOLDER,on_click=add_folder),ft.FilledButton('Atualizar biblioteca',icon=ft.Icons.REFRESH,on_click=scan)]),status,ft.Divider(),ft.Text('ORGANIZADOR INTELIGENTE',size=12,weight=ft.FontWeight.BOLD,color='#9DA3B4'),ft.Text('Revise títulos com correspondência incerta antes de aplicar os metadados.',color='#C7C5D0',size=12),matches,ft.Divider(),ft.Text('CONTA',size=12,weight=ft.FontWeight.BOLD,color='#9DA3B4'),account_block,ft.Divider(),ft.Text('METADADOS',size=12,weight=ft.FontWeight.BOLD,color='#9DA3B4'),ft.Text('AniList fornece capas e informações; os episódios permanecem somente no aparelho.',color='#C7C5D0',size=12),ft.Divider(),ft.Text('SOBRE',size=12,weight=ft.FontWeight.BOLD,color='#9DA3B4'),ft.Text('ReiFlix Local • diagnóstico: banco SQLite e cache de capas no armazenamento privado do app.',color='#C7C5D0',size=12)],scroll=ft.ScrollMode.AUTO,expand=True))
