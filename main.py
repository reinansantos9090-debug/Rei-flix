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
from views.player_view import PlayerView
from views.settings_view import SettingsView

GOOGLE_CLIENT_ID = os.getenv('REIFLIX_GOOGLE_CLIENT_ID', CONFIG_GOOGLE_CLIENT_ID)
GOOGLE_REDIRECT_URL = os.getenv('REIFLIX_GOOGLE_REDIRECT_URL', CONFIG_GOOGLE_REDIRECT_URL)
GOOGLE_WEB_CLIENT_ID = os.getenv('REIFLIX_GOOGLE_WEB_CLIENT_ID', CONFIG_GOOGLE_WEB_CLIENT_ID)

async def main(page: ft.Page):
    page.title='Rei-Flix Local'; page.theme_mode=ft.ThemeMode.DARK; page.bgcolor='#16151F'; page.padding=0
    page.theme=ft.Theme(color_scheme_seed='#E50914',font_family='Roboto')
    # Flet maps this to the host window; Android builds receive the immersive app window when supported.
    page.window.full_screen=True
    data_dir=os.getenv('FLET_APP_STORAGE_DATA') or os.path.join(os.path.dirname(__file__),'.reiflix-data')
    store=LibraryStore(data_dir); library=LibraryService(store); bridge=AndroidBridge(data_dir, page); current=[None]
    def show(control): page.clean(); page.add(control); page.update()
    def navigate_home(): show(HomeView.build(page,library,navigate_details,navigate_settings))
    def play_episode(path,title,on_next=None): show(PlayerView.build(page,path,title,lambda:navigate_details(current[0]),on_next,bridge.play))
    def navigate_details(anime):
        current[0]=anime; show(DetailView.build(page,anime,play_episode,navigate_home))
    def on_catalog_changed():
        # The active screen owns rendering; returning home always reads the SQLite catalog again.
        return None
    def account(): return store.account()
    def navigate_settings(): show(SettingsView.build(page,store,library,navigate_home,on_catalog_changed,add_folder,refresh_library,login,logout,account()))
    async def add_folder(_=None):
        try:
            bridge.select_tree()
        except RuntimeError as exc:
            page.snack_bar=ft.SnackBar(ft.Text(str(exc))); page.snack_bar.open=True; page.update()
    async def refresh_library(_=None):
        for folder in store.folders():
            if folder.get('kind') == 'saf':
                bridge.rescan_tree(folder['path'])
        library.scan()
    async def login(_=None):
        if bridge.available:
            if not GOOGLE_WEB_CLIENT_ID:
                page.snack_bar=ft.SnackBar(ft.Text('Configure REIFLIX_GOOGLE_WEB_CLIENT_ID para entrar com Google.')); page.snack_bar.open=True; page.update(); return
            bridge.sign_in(GOOGLE_WEB_CLIENT_ID); return
        if not GOOGLE_CLIENT_ID or not GOOGLE_REDIRECT_URL:
            page.snack_bar=ft.SnackBar(ft.Text('Configure REIFLIX_GOOGLE_CLIENT_ID e REIFLIX_GOOGLE_REDIRECT_URL para entrar com Google.'))
            page.snack_bar.open=True; page.update(); return
        provider=OAuthProvider(client_id=GOOGLE_CLIENT_ID,client_secret='',authorization_endpoint='https://accounts.google.com/o/oauth2/v2/auth',token_endpoint='https://oauth2.googleapis.com/token',redirect_url=GOOGLE_REDIRECT_URL,scopes=['openid','email','profile'],user_endpoint='https://openidconnect.googleapis.com/v1/userinfo',user_id_fn=lambda u:u.get('sub'),authorization_params={'access_type':'offline','prompt':'select_account'})
        await page.login(provider,fetch_user=True)
    def logout(_=None):
        store.clear_account(); page.logout(); navigate_settings()
    async def login_done(e):
        if e.error:
            page.snack_bar=ft.SnackBar(ft.Text(f'Não foi possível entrar: {e.error_description or e.error}')); page.snack_bar.open=True; page.update(); return
        user=page.auth.user
        if user: store.save_account({'id':str(user.id),'name':str(user.get('name','')),'email':str(user.get('email','')),'picture':str(user.get('picture',''))})
        navigate_settings()
    async def poll_native_bridge():
        while True:
            for event in bridge.drain():
                event_type=event.get('type'); payload=event.get('payload') or {}
                if event_type == 'saf_scan':
                    catalog=library.ingest_documents(payload.get('treeUri',''), payload.get('documents',[]))
                    page.snack_bar=ft.SnackBar(ft.Text(f"Biblioteca atualizada: {len(catalog)} animes.")); page.snack_bar.open=True; page.update()
                elif event_type == 'player_progress':
                    store.save_progress(payload.get('uri',''), payload.get('positionMs',0)/1000, payload.get('durationMs',0)/1000)
                elif event_type == 'google_account':
                    store.save_account(payload); page.snack_bar=ft.SnackBar(ft.Text('Conta Google conectada.')); page.snack_bar.open=True; page.update()
                elif event_type in {'saf_error','google_error'}:
                    page.snack_bar=ft.SnackBar(ft.Text(event.get('message','Operação Android não concluída.'))); page.snack_bar.open=True; page.update()
            await asyncio.sleep(1)
    page.on_login=login_done
    page.run_task(poll_native_bridge)
    navigate_home()

if __name__ == "__main__":
    ft.run(main)
