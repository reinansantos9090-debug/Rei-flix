import json
import flet as ft

class SettingsView:
    @staticmethod
    def build(page, store, library, on_back, on_catalog_changed, on_add_folder, on_refresh_library, on_login, on_logout, account):
        folders=ft.Column(spacing=4); status=ft.Text('',color='#9DA3B4',size=12); diagnostic=ft.Column(spacing=3)
        def notice(message): status.value=message; page.update()
        def render_folders():
            folders.controls.clear()
            for folder in store.folders():
                label = f"{folder['name']}\n{folder['path']}"
                state = folder.get('authorization') or 'unknown'
                error = folder.get('last_error')
                remove = ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE, icon_color=ft.Colors.RED_300, tooltip='Remover pasta',
                    on_click=lambda _, p=folder['path']: (store.remove_folder(p), render_folders(), render_diagnostic(), notice('Pasta removida.')),
                )
                info = ft.Column([
                    ft.Text(label, expand=True, size=11, color='#C7C5D0'),
                    ft.Text(f"Acesso: {state}" + (f" — {error}" if error else ''), size=10, color='#FFB4AB' if error else '#9DA3B4'),
                ], expand=True)
                folders.controls.append(ft.Container(bgcolor='#252836', border_radius=8, padding=8, content=ft.Row([info, remove])))
            if not folders.controls:
                folders.controls.append(ft.Text('Nenhuma pasta adicionada.',color='#9DA3B4'))
        def render_diagnostic():
            diagnostic.controls.clear(); last=store.last_scan()
            if not last: diagnostic.controls.append(ft.Text('Ainda não houve varredura.',color='#9DA3B4',size=12)); return
            errors=json.loads(last['errors'] or '[]')
            diagnostic.controls.extend([ft.Text(f"Arquivos: {last['files']} • Vídeos: {last['videos']} • Animes: {last['animes']} • Episódios: {last['episodes']}",color='#C7C5D0',size=12),ft.Text('Erros: ' + ('; '.join(errors) if errors else 'nenhum'),color='#FFB4AB' if errors else '#9DA3B4',size=11)])
        async def add_folder(_):
            await on_add_folder()
            notice('Abrindo seletor Android para autorizar a pasta…')
        async def scan(_):
            notice('Atualizando pastas autorizadas…')
            await on_refresh_library()
            render_diagnostic(); on_catalog_changed()
        matches=ft.Column(spacing=8)
        def render_matches():
            matches.controls.clear()
            for pending in store.pending_matches():
                candidates=pending['candidates']
                if not candidates: continue
                selector=ft.Dropdown(options=[ft.dropdown.Option(key=str(item['id']),text=f"{(item.get('title') or {}).get('english') or (item.get('title') or {}).get('romaji') or 'Sem título'} ({int(item.get('match_score',0)*100)}%)") for item in candidates],value=str(candidates[0]['id']),expand=True,text_size=12)
                def confirm(_, p=pending, field=selector):
                    if not field.value: notice('Escolha um resultado do AniList antes de confirmar.'); return
                    library.resolve_match(p['lookup_title'],int(field.value)); render_matches(); notice('Associação salva. Atualize a biblioteca para aplicar a capa.')
                matches.controls.append(ft.Column([ft.Text(f"Confirmar: {pending['display_title']}",weight=ft.FontWeight.BOLD,color='#C7C5D0'),ft.Row([selector,ft.FilledButton('Usar',on_click=confirm)])]))
            if not matches.controls: matches.controls.append(ft.Text('Nenhuma identificação precisa de revisão.',color='#9DA3B4',size=12))
        logged=account.get('email')
        account_block=ft.Column([ft.Image(src=account.get('picture'),width=48,height=48,border_radius=24) if account.get('picture') else ft.Container(),ft.Text(account.get('name') or account.get('email') or 'Você não está conectado.',color='#C7C5D0'),ft.Text(account.get('email',''),color='#9DA3B4',size=12),ft.FilledButton('Sair',icon=ft.Icons.LOGOUT,on_click=lambda _:on_logout()) if logged else ft.FilledButton('Entrar com Google',icon=ft.Icons.LOGIN,on_click=lambda _:on_login())])
        render_folders(); render_matches(); render_diagnostic()
        return ft.Container(padding=ft.Padding.all(16),bgcolor='#16151F',content=ft.Column([ft.Row([ft.IconButton(icon=ft.Icons.ARROW_BACK,on_click=lambda _:on_back(),icon_color=ft.Colors.WHITE),ft.Text('Configurações',size=20,weight=ft.FontWeight.BOLD,color=ft.Colors.WHITE)]),ft.Text('BIBLIOTECA LOCAL',size=12,weight=ft.FontWeight.BOLD,color='#9DA3B4'),folders,ft.Row([ft.OutlinedButton('Adicionar pasta',icon=ft.Icons.CREATE_NEW_FOLDER,on_click=add_folder),ft.FilledButton('Atualizar biblioteca',icon=ft.Icons.REFRESH,on_click=scan)]),status,ft.Divider(),ft.Text('DIAGNÓSTICO DA BIBLIOTECA',size=12,weight=ft.FontWeight.BOLD,color='#9DA3B4'),diagnostic,ft.Divider(),ft.Text('CORRESPONDÊNCIAS ANILIST',size=12,weight=ft.FontWeight.BOLD,color='#9DA3B4'),matches,ft.Divider(),ft.Text('CONTA GOOGLE',size=12,weight=ft.FontWeight.BOLD,color='#9DA3B4'),account_block,ft.Divider(),ft.Text('PRIVACIDADE',size=12,weight=ft.FontWeight.BOLD,color='#9DA3B4'),ft.Text('Somente a pasta escolhida é lida. AniList fornece metadados; vídeos nunca são enviados.',color='#C7C5D0',size=12)],scroll=ft.ScrollMode.AUTO,expand=True))
