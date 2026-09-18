import os
import asyncio
import flet as ft
from flet.auth import OAuthProvider
from app_config import GOOGLE_CLIENT_ID as CONFIG_GOOGLE_CLIENT_ID, GOOGLE_REDIRECT_URL as CONFIG_GOOGLE_REDIRECT_URL, GOOGLE_WEB_CLIENT_ID as CONFIG_GOOGLE_WEB_CLIENT_ID
from core.android_bridge import AndroidBridge
from core.library_store import LibraryStore
from core.library_service import LibraryService
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
    store=LibraryStore(data_dir); library=LibraryService(store); bridge=AndroidBridge(data_dir, page); current=[None]; details_back=[None]
    account_state=["connected" if store.account().get("email") else "disconnected"]
    scan_in_progress=[False]
    active_view=["home"]
    def show(control): page.clean(); page.add(control); page.update()
    def navigate_home():
        active_view[0] = "home"
        show(HomeView.build(page, library, navigate_details, navigate_settings, play_episode, navigate_organize))
    def navigate_organize():
        active_view[0] = "organize"
        show(OrganizeView.build(page, library, lambda anime: navigate_details(anime, navigate_organize), navigate_home, navigate_settings))
    def start_native_player(path, title, position_ms=0):
        # Sequence decisions stay in LibraryStore; Android receives only the
        # selected local URI and booleans for the native controls.
        bridge.play(path, title, position_ms,
                    can_next=library.next_episode(path) is not None,
                    can_previous=library.previous_episode(path) is not None)

    def play_episode(path, title, on_next=None, progress_seconds=0):
        if store.get_preference("resume_playback", "true") != "true":
            progress_seconds = 0
        active_view[0] = "player"
        show(PlayerView.build(page, path, title, lambda: navigate_details(current[0], details_back[0]),
                              on_next, start_native_player, progress_seconds))
    def navigate_details(anime, on_back=None):
        # Refresh once from SQLite so Details always presents the durable
        # favorite/progress state without triggering a scan or network call.
        anime_id = anime.get('id') if anime else None
        details_back[0] = on_back or navigate_home
        current[0] = next((item for item in library.catalog() if item['id'] == anime_id), anime)
        active_view[0] = "details"
        show(DetailView.build(page, current[0], play_episode, details_back[0],
                              store.toggle_favorite, library.playback_target))
    def on_catalog_changed():
        # The active screen owns rendering; returning home always reads the SQLite catalog again.
        return None
    def account(): return store.account()
    def navigate_settings():
        active_view[0] = "settings"
        show(SettingsView.build(page,store,library,navigate_home,on_catalog_changed,add_folder,refresh_library,login,logout,account(),account_state[0]))
    def refresh_settings_if_active():
        if active_view[0] == "settings":
            navigate_settings()
    async def add_folder(_=None):
        try:
            bridge.select_tree()
        except RuntimeError as exc:
            page.snack_bar=ft.SnackBar(ft.Text(str(exc))); page.snack_bar.open=True; page.update()
    async def refresh_library(_=None):
        if scan_in_progress[0]:
            return "Uma atualização da biblioteca já está em andamento.", True
        scan_in_progress[0] = True
        try:
            saf_folders = [folder for folder in store.folders() if folder.get('kind') == 'saf']
            for folder in saf_folders:
                if bridge.available:
                    bridge.rescan_tree(folder['path'])
            result = await asyncio.to_thread(library.scan)
            if saf_folders and bridge.available:
                # Native SAF scans finish through the mailbox; retain the lock
                # until their result/error event arrives.
                return "Atualização iniciada. Verificando as pastas autorizadas…", True
            return result.message(), False
        except Exception:
            scan_in_progress[0] = False
            raise
        finally:
            if not (bridge.available and any(f.get('kind') == 'saf' for f in store.folders())):
                scan_in_progress[0] = False
    async def login(_=None):
        account_state[0] = 'connecting'; navigate_settings()
        if bridge.available:
            if not GOOGLE_WEB_CLIENT_ID:
                account_state[0] = 'error'; navigate_settings()
                page.snack_bar=ft.SnackBar(ft.Text('Configure REIFLIX_GOOGLE_WEB_CLIENT_ID para entrar com Google.')); page.snack_bar.open=True; page.update(); return
            bridge.sign_in(GOOGLE_WEB_CLIENT_ID); return
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
        while True:
            for event in bridge.drain():
                event_type=event.get('type'); payload=event.get('payload') or {}
                if event_type == 'saf_scan':
                    try:
                        stats = payload.get('stats') or {}
                        tree_uri = payload.get('treeUri', '')
                        if not tree_uri:
                            raise ValueError('Resultado SAF sem pasta de origem.')
                        catalog=library.ingest_documents(tree_uri, payload.get('documents', []), folder_name=payload.get('name'), scan_errors=stats.get('errors', []))
                        page.snack_bar=ft.SnackBar(ft.Text(f"Biblioteca atualizada: {len(catalog)} animes.")); page.snack_bar.open=True; page.update()
                    except Exception:
                        page.snack_bar=ft.SnackBar(ft.Text('Não foi possível salvar a atualização da biblioteca.')); page.snack_bar.open=True; page.update()
                    finally:
                        scan_in_progress[0] = False
                        refresh_settings_if_active()
                elif event_type in {'player_progress', 'player_paused', 'player_exited', 'player_completed'}:
                    uri = payload.get('uri', '')
                    if uri:
                        store.save_progress(uri, payload.get('positionMs', 0) / 1000,
                                            payload.get('durationMs', 0) / 1000)
                elif event_type in {'player_next_request', 'player_previous_request'}:
                    uri = payload.get('uri', '')
                    target = library.next_episode(uri) if event_type == 'player_next_request' else library.previous_episode(uri)
                    if target:
                        start_native_player(target['path'], target['file_name'], 0)
                elif event_type == 'player_error':
                    page.snack_bar=ft.SnackBar(ft.Text(event.get('message', 'Não foi possível reproduzir este arquivo.'))); page.snack_bar.open=True; page.update()
                elif event_type == 'google_account':
                    store.save_account(payload); account_state[0] = 'connected'; page.snack_bar=ft.SnackBar(ft.Text('Conta Google conectada.')); page.snack_bar.open=True; page.update(); refresh_settings_if_active()
                elif event_type == 'saf_cancelled':
                    scan_in_progress[0] = False
                    page.snack_bar=ft.SnackBar(ft.Text('Seleção de pasta cancelada.')); page.snack_bar.open=True; page.update()
                elif event_type == 'google_cancelled':
                    account_state[0] = 'disconnected'
                    page.snack_bar=ft.SnackBar(ft.Text('Entrada com Google cancelada.')); page.snack_bar.open=True; page.update(); refresh_settings_if_active()
                elif event_type in {'saf_error','google_error'}:
                    if event_type == 'saf_error':
                        scan_in_progress[0] = False
                        tree_uri = payload.get('treeUri')
                        if tree_uri:
                            store.update_folder_status(tree_uri, 'revoked', event.get('message', 'Não foi possível acessar a pasta.'))
                    if event_type == 'google_error': account_state[0] = 'error'
                    page.snack_bar=ft.SnackBar(ft.Text(event.get('message','Operação Android não concluída.'))); page.snack_bar.open=True; page.update()
            await asyncio.sleep(1)
    page.on_login=login_done
    page.run_task(poll_native_bridge)
    navigate_home()

if __name__ == "__main__":
    ft.run(main)
