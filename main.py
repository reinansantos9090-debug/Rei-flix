import os
import asyncio
import flet as ft
from flet.auth import OAuthProvider
from app_config import GOOGLE_CLIENT_ID as CONFIG_GOOGLE_CLIENT_ID, GOOGLE_REDIRECT_URL as CONFIG_GOOGLE_REDIRECT_URL, GOOGLE_WEB_CLIENT_ID as CONFIG_GOOGLE_WEB_CLIENT_ID
from core.android_bridge import AndroidBridge
from core.navigation import NavigationController, SafSelectionState
from core.library_store import LibraryStore
from core.library_service import LibraryService
from core.google_account import normalize_google_profile
from views.home_view import HomeView
from views.details_view import DetailView
from views.organize_view import OrganizeView
from views.player_view import PlayerView
from views.settings_view import SettingsView

GOOGLE_CLIENT_ID = os.getenv('REIFLIX_GOOGLE_CLIENT_ID', CONFIG_GOOGLE_CLIENT_ID)
GOOGLE_REDIRECT_URL = os.getenv('REIFLIX_GOOGLE_REDIRECT_URL', CONFIG_GOOGLE_REDIRECT_URL)
GOOGLE_WEB_CLIENT_ID = os.getenv('REIFLIX_GOOGLE_WEB_CLIENT_ID', CONFIG_GOOGLE_WEB_CLIENT_ID)

async def main(page: ft.Page):
    page.title='Rei-Flix Local'; page.theme_mode=ft.ThemeMode.DARK; page.bgcolor='#16151F'; page.padding=0
    page.theme=ft.Theme(color_scheme_seed='#E50914',font_family='Roboto')
    data_dir=os.getenv('FLET_APP_STORAGE_DATA') or os.path.join(os.path.dirname(__file__),'.reiflix-data')
    store=LibraryStore(data_dir); library=LibraryService(store); bridge=AndroidBridge(data_dir, page); current=[None]
    account_state=["connected" if store.account().get("email") else "disconnected"]
    scan_in_progress=[False]
    pending_native_scans=[0]
    # View-local query/filter state survives Details/Player round-trips while
    # the catalog itself is still read afresh from SQLite on each view entry.
    home_state = {}
    organize_state = {}
    navigation = NavigationController()
    saf_selection = SafSelectionState()
    def show(control): page.clean(); page.add(control); page.update()
    def render_current():
        if navigation.current == "home":
            show(HomeView.build(page, library, navigate_details, navigate_settings, play_episode, navigate_organize,
                                view_state=home_state))
        elif navigation.current == "organize":
            show(OrganizeView.build(page, library, navigate_details, navigate_back, navigate_settings,
                                    view_state=organize_state))
        elif navigation.current == "details":
            show(DetailView.build(page, current[0], play_episode, navigate_back,
                                  store.toggle_favorite, library.playback_target))
        elif navigation.current == "settings":
            show(SettingsView.build(page,store,library,navigate_back,on_catalog_changed,add_folder,refresh_library,login,logout,account(),account_state[0],
                                    folder_selection_pending=lambda: saf_selection.pending))
        elif navigation.current == "player":
            path, title, progress = player_context[0]
            show(PlayerView.build(page, path, title, navigate_back, None, start_native_player, progress))

    player_context=[("", "", 0)]
    def navigate_home():
        navigation.reset_to_root()
        render_current()
    def navigate_organize():
        navigation.push("organize")
        render_current()
    def start_native_player(path, title, position_ms=0):
        # Sequence decisions stay in LibraryStore; Android receives only the
        # selected local URI and booleans for the native controls.
        bridge.play(path, title, position_ms,
                    can_next=library.next_episode(path) is not None,
                    can_previous=library.previous_episode(path) is not None)

    def play_episode(path, title, on_next=None, progress_seconds=0):
        if store.get_preference("resume_playback", "true") != "true":
            progress_seconds = 0
        player_context[0] = (path, title, progress_seconds)
        navigation.push("player")
        render_current()
    def navigate_details(anime, on_back=None):
        # Refresh once from SQLite so Details always presents the durable
        # favorite/progress state without triggering a scan or network call.
        anime_id = anime.get('id') if anime else None
        current[0] = next((item for item in library.catalog() if item['id'] == anime_id), anime)
        navigation.push("details")
        render_current()
    def on_catalog_changed():
        # The active screen owns rendering; returning home always reads the SQLite catalog again.
        return None
    def account(): return store.account()
    def navigate_settings():
        navigation.push("settings")
        render_current()
    def navigate_back():
        action = navigation.back()
        if action == "previous":
            render_current()
        elif action == "prompt_exit":
            page.snack_bar=ft.SnackBar(ft.Text("Pressione voltar novamente para sair")); page.snack_bar.open=True; page.update()
        elif action == "exit":
            # Close only after the Android/Python shared two-back policy.
            page.window.close()
    def refresh_settings_if_active():
        if navigation.current == "settings":
            render_current()
    async def add_folder(_=None):
        if scan_in_progress[0] or not saf_selection.begin():
            return
        try:
            bridge.select_tree()
        except Exception as exc:
            saf_selection.finish()
            page.snack_bar=ft.SnackBar(ft.Text(str(exc))); page.snack_bar.open=True; page.update()
            raise
    async def refresh_library(_=None):
        if saf_selection.pending:
            return "Conclua ou cancele a seleção da pasta antes de atualizar a biblioteca.", False
        if scan_in_progress[0]:
            return "Uma atualização da biblioteca já está em andamento.", True
        scan_in_progress[0] = True
        try:
            saf_folders = [folder for folder in store.folders() if folder.get('kind') == 'saf']
            if saf_folders and bridge.available:
                # Native SAF scans finish through the mailbox; retain the lock
                # until their result/error event arrives.
                pending_native_scans[0] = len(saf_folders)
                for folder in saf_folders:
                    bridge.rescan_tree(folder['path'])
                return "Atualização iniciada. Verificando as pastas autorizadas…", True
            result = await asyncio.to_thread(library.scan)
            return result.message(), False
        except Exception:
            scan_in_progress[0] = False
            raise
        finally:
            if not (bridge.available and any(f.get('kind') == 'saf' for f in store.folders())):
                scan_in_progress[0] = False
    async def login(_=None):
        if bridge.available:
            if not GOOGLE_WEB_CLIENT_ID:
                account_state[0] = 'configuration_required'; navigate_settings()
                page.snack_bar=ft.SnackBar(ft.Text('Login Google não configurado neste APK. Configure um Web Client ID público antes de tentar novamente.')); page.snack_bar.open=True; page.update(); return
            account_state[0] = 'connecting'; navigate_settings()
            bridge.sign_in(GOOGLE_WEB_CLIENT_ID); return
        account_state[0] = 'connecting'; navigate_settings()
        if not GOOGLE_CLIENT_ID or not GOOGLE_REDIRECT_URL:
            account_state[0] = 'error'; navigate_settings()
            page.snack_bar=ft.SnackBar(ft.Text('Configure REIFLIX_GOOGLE_CLIENT_ID e REIFLIX_GOOGLE_REDIRECT_URL para entrar com Google.'))
            page.snack_bar.open=True; page.update(); return
        provider=OAuthProvider(client_id=GOOGLE_CLIENT_ID,client_secret='',authorization_endpoint='https://accounts.google.com/o/oauth2/v2/auth',token_endpoint='https://oauth2.googleapis.com/token',redirect_url=GOOGLE_REDIRECT_URL,scopes=['openid','email','profile'],user_endpoint='https://openidconnect.googleapis.com/v1/userinfo',user_id_fn=lambda u:u.get('sub'),authorization_params={'access_type':'offline','prompt':'select_account'})
        await page.login(provider,fetch_user=True)
    def logout(_=None):
        account_state[0] = 'disconnecting'; navigate_settings()
        try:
            store.clear_account(); page.logout()
            account_state[0] = 'disconnected'
        except Exception:
            account_state[0] = 'error'
            raise
        navigate_settings()
    async def login_done(e):
        if e.error:
            account_state[0] = 'error'
            page.snack_bar=ft.SnackBar(ft.Text(f'Não foi possível entrar: {e.error_description or e.error}')); page.snack_bar.open=True; page.update(); return
        user=page.auth.user
        if user:
            store.save_account({'id':str(user.id),'name':str(user.get('name','')),'email':str(user.get('email','')),'picture':str(user.get('picture',''))})
            account_state[0] = 'connected'
        navigate_settings()
    async def poll_native_bridge():
        def finish_native_scan():
            pending_native_scans[0] = max(0, pending_native_scans[0] - 1)
            if pending_native_scans[0] == 0:
                scan_in_progress[0] = False

        while True:
            events = bridge.drain()
            for event in events:
                event_type=event.get('type'); payload=event.get('payload') or {}
                if event_type == 'saf_scan':
                    try:
                        saf_selection.finish()
                        stats = payload.get('stats') or {}
                        tree_uri = payload.get('treeUri', '')
                        if not tree_uri:
                            raise ValueError('Resultado SAF sem pasta de origem.')
                        catalog=await asyncio.to_thread(library.ingest_documents, tree_uri, payload.get('documents', []), folder_name=payload.get('name'), scan_errors=stats.get('errors', []), scan_stats=stats)
                        videos = int(stats.get('videos') or 0)
                        partial = bool(payload.get('partial') or stats.get('errors'))
                        message = ("Scan concluído parcialmente. Alguns diretórios não puderam ser acessados. " if partial else "")
                        message += f"Encontramos {videos} vídeo(s) em {len(catalog)} anime(s)." if videos else "Não encontramos vídeos compatíveis nesta pasta."
                        page.snack_bar=ft.SnackBar(ft.Text(message)); page.snack_bar.open=True; page.update()
                    except Exception:
                        page.snack_bar=ft.SnackBar(ft.Text('Não foi possível salvar a atualização da biblioteca.')); page.snack_bar.open=True; page.update()
                    finally:
                        finish_native_scan()
                        refresh_settings_if_active()
                elif event_type in {'player_progress', 'player_paused', 'player_exited', 'player_completed'}:
                    uri = payload.get('uri', '')
                    if uri:
                        store.save_progress(uri, payload.get('positionMs', 0) / 1000,
                                            payload.get('durationMs', 0) / 1000)
                    if event_type == 'player_exited' and navigation.current == 'player':
                        navigate_back()
                elif event_type in {'player_next_request', 'player_previous_request'}:
                    uri = payload.get('uri', '')
                    target = library.next_episode(uri) if event_type == 'player_next_request' else library.previous_episode(uri)
                    if target:
                        start_native_player(target['path'], target['file_name'], 0)
                elif event_type == 'player_error':
                    page.snack_bar=ft.SnackBar(ft.Text(event.get('message', 'Não foi possível reproduzir este arquivo.'))); page.snack_bar.open=True; page.update()
                    # Invalid/unreadable URIs can fail before Media3 creates a
                    # player, so there may be no player_exited event to dismiss
                    # the Flet transition screen.
                    if navigation.current == 'player':
                        navigate_back()
                elif event_type == 'google_sign_in_started':
                    account_state[0] = 'awaiting_google'; refresh_settings_if_active()
                elif event_type == 'google_account':
                    profile = normalize_google_profile(payload)
                    if profile is None:
                        account_state[0] = 'error'
                        page.snack_bar=ft.SnackBar(ft.Text('A resposta da conta Google é inválida. Tente novamente.')); page.snack_bar.open=True; page.update(); refresh_settings_if_active()
                    else:
                        store.save_account(profile); account_state[0] = 'connected'; page.snack_bar=ft.SnackBar(ft.Text('Conta Google conectada.')); page.snack_bar.open=True; page.update(); refresh_settings_if_active()
                elif event_type == 'saf_cancelled':
                    saf_selection.finish()
                    page.snack_bar=ft.SnackBar(ft.Text('Seleção de pasta cancelada.')); page.snack_bar.open=True; page.update()
                    refresh_settings_if_active()
                elif event_type == 'saf_permission':
                    tree_uri = payload.get('treeUri')
                    if tree_uri:
                        if payload.get('granted'):
                            store.update_folder_status(tree_uri, 'granted')
                        else:
                            store.update_folder_status(tree_uri, 'revoked', 'A permissão desta pasta foi removida.')
                        refresh_settings_if_active()
                elif event_type == 'google_cancelled':
                    account_state[0] = 'disconnected'
                    page.snack_bar=ft.SnackBar(ft.Text('Entrada com Google cancelada.')); page.snack_bar.open=True; page.update(); refresh_settings_if_active()
                elif event_type in {'saf_error','google_error'}:
                    if event_type == 'saf_error':
                        saf_selection.finish()
                        tree_uri = payload.get('treeUri')
                        if tree_uri:
                            store.update_folder_status(tree_uri, 'revoked', event.get('message', 'Não foi possível acessar a pasta.'))
                        # A re-scan has no successful result event to clear
                        # its lock.  Without this, Settings can remain on its
                        # disabled loading button after one revoked grant.
                        if scan_in_progress[0]:
                            finish_native_scan()
                    if event_type == 'google_error': account_state[0] = 'error'
                    page.snack_bar=ft.SnackBar(ft.Text(event.get('message','Operação Android não concluída.'))); page.snack_bar.open=True; page.update()
                    if event_type == 'saf_error': refresh_settings_if_active()
                elif event_type == 'android_back':
                    navigate_back()
            # NativeMailbox retains the atomically claimed batch until this
            # point, after SQLite/UI handling has completed. A process restart
            # before acknowledgement replays the complete batch safely.
            bridge.acknowledge()
            await asyncio.sleep(0.2)
    page.on_login=login_done
    page.run_task(poll_native_bridge)
    if bridge.available:
        for folder in store.folders():
            if folder.get('kind') == 'saf':
                bridge.verify_tree(folder['path'])
    render_current()

if __name__ == "__main__":
    ft.run(main)
