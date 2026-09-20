import os
import asyncio
import flet as ft
from flet.auth import OAuthProvider
from app_config import GOOGLE_CLIENT_ID as CONFIG_GOOGLE_CLIENT_ID, GOOGLE_REDIRECT_URL as CONFIG_GOOGLE_REDIRECT_URL, GOOGLE_WEB_CLIENT_ID as CONFIG_GOOGLE_WEB_CLIENT_ID
from core.android_bridge import AndroidBridge
from core.navigation import NavigationController, SafSelectionState
from core.storage_access import StorageAccessState, storage_access_state
from core.dialogs import dismiss_dialog
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
    store=LibraryStore(data_dir)
    recovered_scans=store.interrupted_scans()
    library=LibraryService(store); bridge=AndroidBridge(data_dir, page); current=[None]
    account_state=["connected" if store.account().get("email") else "disconnected"]
    scan_in_progress=[False]
    pending_native_scans=[0]
    pending_folder_removals=set()
    # View-local query/filter state survives Details/Player round-trips while
    # the catalog itself is still read afresh from SQLite on each view entry.
    home_state = {}
    organize_state = {}
    navigation = NavigationController()
    saf_selection = SafSelectionState()
    # Runtime snapshots are deliberately not stored in SQLite: only Android is
    # proof of a current grant.  ``dismissed`` prevents an automatic prompt loop.
    storage_onboarding = {"media": None, "broad": None, "dismissed": False,
                          "dialog_open": False, "waiting_for_result": False}
    def show(control): page.clean(); page.add(control); page.update()
    def render_current():
        if navigation.current == "home":
            show(HomeView.build(page, library, navigate_details, navigate_settings, play_episode, navigate_organize,
                                view_state=home_state))
        elif navigation.current == "organize":
            show(OrganizeView.build(page, library, navigate_details, navigate_back, navigate_settings,
                                    on_request_storage_access=open_broad_storage_access,
                                    on_scan_storage=refresh_library,
                                    on_request_video_access=request_video_access,
                                    on_add_folder=add_folder,
                                    view_state=organize_state))
        elif navigation.current == "details":
            show(DetailView.build(page, current[0], play_episode, navigate_back,
                                  store.toggle_favorite, library.playback_target, library.set_user_tags,
                                  library.toggle_pinned, library.set_personal_note, store.set_episode_identification,
                                  refresh_current_details, refresh_current_metadata, library.resolve_artwork))
        elif navigation.current == "settings":
            show(SettingsView.build(page,store,library,navigate_back,on_catalog_changed,add_folder,remove_folder,refresh_library,request_video_access,open_broad_storage_access,login,logout,account(),account_state[0],
                                    folder_selection_pending=lambda: saf_selection.pending, on_resolve_match=resolve_match,
                                    on_create_backup=create_backup, on_restore_backup=restore_backup))
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
    async def start_native_player(path, title, position_ms=0):
        # Sequence decisions stay in LibraryStore; Android receives only the
        # selected local URI and the already-derived autoplay preference.
        await bridge.play(
            path,
            title,
            position_ms,
            can_next=library.next_episode(path) is not None,
            can_previous=library.previous_episode(path) is not None,
            autoplay=store.get_preference("autoplay_next", "true") == "true",
        )

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
    def refresh_current_details():
        """Reload the durable record after an in-place Details edit.

        A manual season correction can move an episode between groups, so a
        local widget patch is insufficient; rebuild from SQLite without
        pushing another navigation entry.
        """
        anime_id = current[0].get("id") if current[0] else None
        current[0] = next((item for item in library.catalog() if item["id"] == anime_id), current[0])
        render_current()
    async def refresh_current_metadata(e=None):
        """Refresh only editorial metadata; never rescans or mutates playback state."""
        anime = current[0] or {}
        lookup = (anime.get("meta") or {}).get("lookup_title")
        title = anime.get("main_title") or (anime.get("meta") or {}).get("title") or "Anime local"
        if not lookup:
            return
        try:
            await asyncio.to_thread(library.refresh_metadata, lookup, title, force=True)
            refresh_current_details()
            page.snack_bar = ft.SnackBar(ft.Text("Metadata atualizada."))
            page.snack_bar.open = True
            page.update()
        except Exception:
            page.snack_bar = ft.SnackBar(ft.Text("Não foi possível atualizar a metadata agora."))
            page.snack_bar.open = True
            page.update()
    def on_catalog_changed():
        # Native scan completion must immediately re-read SQLite on the active
        # screen; the previous implementation intentionally did nothing here,
        # leaving a freshly indexed catalog invisible until manual navigation.
        render_current()
    async def remove_folder(reference):
        if scan_in_progress[0] or saf_selection.pending:
            page.snack_bar = ft.SnackBar(ft.Text("Aguarde a atualização ou a seleção de pasta terminar antes de remover uma pasta."))
            page.snack_bar.open = True
            page.update()
            return
        folder = next((item for item in store.folders() if item.get("path") == reference), None)
        if folder and folder.get("kind") == "saf" and bridge.available:
            try:
                pending_folder_removals.add(reference)
                await bridge.release_tree(reference)
                page.snack_bar = ft.SnackBar(ft.Text("Liberando a permissão da pasta…"))
                page.snack_bar.open = True
                page.update()
            except Exception as exc:
                pending_folder_removals.discard(reference)
                page.snack_bar = ft.SnackBar(ft.Text(f"Não foi possível liberar a pasta: {exc}"))
                page.snack_bar.open = True
                page.update()
            return
        store.remove_folder(reference)
        on_catalog_changed()
        refresh_settings_if_active()
    async def resolve_match(lookup_title, anilist_id):
        try:
            await asyncio.to_thread(library.resolve_match, lookup_title, anilist_id)
            page.snack_bar = ft.SnackBar(ft.Text("Associação AniList salva. Atualize a biblioteca para aplicar os metadados ao catálogo."))
            page.snack_bar.open = True
            refresh_settings_if_active()
        except Exception as exc:
            page.snack_bar = ft.SnackBar(ft.Text(str(exc)))
            page.snack_bar.open = True
            page.update()

    def create_backup():
        return library.create_backup()

    def restore_backup():
        path = library.restore_backup()
        on_catalog_changed()
        refresh_settings_if_active()
        return path

    def account(): return store.account()
    def navigate_settings():
        navigation.push("settings")
        render_current()
        if bridge.available:
            page.run_task(bridge.check_storage_access)
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
            await bridge.select_tree()
        except Exception as exc:
            saf_selection.finish()
            page.snack_bar=ft.SnackBar(ft.Text(str(exc))); page.snack_bar.open=True; page.update()
            raise
    async def request_video_access(_=None):
        if not bridge.available:
            return
        logger.info("[STORAGE] action=media_permission python_callback=dispatch")
        await bridge.request_media_access()

    async def open_broad_storage_access(_=None):
        if not bridge.available:
            return
        logger.info("[STORAGE] action=broad_storage python_callback=dispatch")
        await bridge.open_broad_storage_settings()

    def storage_state():
        return storage_access_state(storage_onboarding["media"], bool(storage_onboarding["broad"]),
                                    dismissed=storage_onboarding["dismissed"])

    def maybe_show_storage_onboarding():
        """Show at most one post-render explanation based on Android's snapshot."""
        if not bridge.available or storage_onboarding["dialog_open"] or storage_onboarding["waiting_for_result"]:
            return
        if storage_onboarding["media"] is None or storage_onboarding["broad"] is None:
            return
        state = storage_state()
        if state not in {StorageAccessState.NEEDS_MEDIA_PERMISSION, StorageAccessState.NEEDS_BROAD_STORAGE}:
            return
        is_media = state == StorageAccessState.NEEDS_MEDIA_PERMISSION
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Permissão necessária" if is_media else "Acesso ao armazenamento"),
            content=ft.Text(
                "O Rei-flix precisa acessar seus vídeos locais para encontrar os episódios salvos no aparelho."
                if is_media else
                "Para encontrar vídeos em diferentes pastas do armazenamento compartilhado, o Rei-flix precisa de acesso amplo ao armazenamento."
            ),
        )
        async def allow(_event):
            storage_onboarding["dialog_open"] = False
            storage_onboarding["waiting_for_result"] = True
            page.pop_dialog()
            try:
                if is_media:
                    await request_video_access()
                else:
                    await open_broad_storage_access()
            except Exception:
                storage_onboarding["waiting_for_result"] = False
                page.snack_bar = ft.SnackBar(ft.Text("Não foi possível abrir a solicitação de acesso.")); page.snack_bar.open = True; page.update()
        def cancel(_event):
            logger.info("[STORAGE] request_id=- action=cancel python_callback=received dialog_open=false")
            storage_onboarding["dialog_open"] = False
            storage_onboarding["dismissed"] = True
            page.pop_dialog()
            page.update()
        dialog.actions = [ft.TextButton("CANCELAR", on_click=cancel),
                          ft.FilledButton("PERMITIR" if is_media else "CONTINUAR", on_click=allow)]
        storage_onboarding["dialog_open"] = True
        logger.info("[STORAGE] request_id=- action=onboarding_show dialog_open=true")
        page.show_dialog(dialog)
        page.update()

    async def refresh_library(_=None):
        if saf_selection.pending:
            return "Conclua ou cancele a seleção da pasta antes de atualizar a biblioteca.", False
        if scan_in_progress[0]:
            return "Uma atualização da biblioteca já está em andamento.", True
        scan_in_progress[0] = True
        try:
            folders = store.folders()
            saf_folders = [folder for folder in folders
                       if folder.get('kind') == 'saf' and folder.get('authorization') == 'granted']
            mediastore_granted = any(
                folder.get('kind') == 'mediastore' and folder.get('authorization') == 'granted'
                for folder in folders
            )
            if bridge.available:
                # Native sources remain independent for persistence/missing-state,
                # while Python owns one user-visible refresh lifecycle.
                pending_native_scans[0] = 0
                broad_granted = any(
                    folder.get('kind') == 'broad_storage' and folder.get('authorization') == 'granted'
                    for folder in folders
                )
                if broad_granted:
                    pending_native_scans[0] += 1
                    try:
                        await bridge.scan_all_storage()
                    except Exception:
                        pending_native_scans[0] = max(0, pending_native_scans[0] - 1)
                for folder in saf_folders:
                    pending_native_scans[0] += 1
                    try:
                        await bridge.rescan_tree(folder['path'])
                    except Exception:
                        pending_native_scans[0] = max(0, pending_native_scans[0] - 1)
                        store.update_folder_status(folder['path'], "granted", "Não foi possível iniciar a varredura SAF.")
                if mediastore_granted:
                    pending_native_scans[0] += 1
                    try:
                        await bridge.scan_media_store()
                    except Exception:
                        pending_native_scans[0] = max(0, pending_native_scans[0] - 1)
                        store.update_folder_status(
                            "mediastore:external:video",
                            "unknown",
                            "Não foi possível iniciar a varredura MediaStore.",
                        )
                if pending_native_scans[0] > 0:
                    missing_sources = []
                    if not mediastore_granted:
                        missing_sources.append("vídeos do dispositivo")
                    if not broad_granted:
                        missing_sources.append("armazenamento amplo")
                    if missing_sources:
                        return "Atualização iniciada. Ainda sem acesso a " + ", ".join(missing_sources) + ".", True
                    return "Atualização iniciada. Verificando as fontes locais…", True
                scan_in_progress[0] = False
                return "Nenhuma fonte local pôde iniciar uma varredura.", False
            result = await asyncio.to_thread(library.scan)
            return result.message(), False
        except Exception:
            scan_in_progress[0] = False
            raise
        finally:
            if not (bridge.available and pending_native_scans[0] > 0):
                scan_in_progress[0] = False
    async def login(_=None):
        if bridge.available:
            if not GOOGLE_WEB_CLIENT_ID:
                account_state[0] = 'configuration_required'; navigate_settings()
                page.snack_bar=ft.SnackBar(ft.Text('Login Google não configurado neste APK. Configure um Web Client ID público antes de tentar novamente.')); page.snack_bar.open=True; page.update(); return
            account_state[0] = 'connecting'; navigate_settings()
            await bridge.sign_in(GOOGLE_WEB_CLIENT_ID); return
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
            try:
                events = bridge.drain()
                for event in events:
                    try:
                        if not isinstance(event, dict):
                            continue
                        event_id = event.get('eventId')
                        if event_id and not store.claim_native_event(event_id):
                            # NativeMailbox is at-least-once; duplicate delivery must be
                            # harmless even when the event file is replayed.
                            continue
                        event_type = event.get('type')
                        payload = event.get('payload')
                        if payload is None:
                            payload = {}
                        if not isinstance(payload, dict):
                            continue
                        if event_type == 'saf_scan_progress':
                            # Native scanner reports coarse progress so large SAF trees do not
                            # look frozen while the Android ContentResolver is traversing them.
                            files = int(payload.get('files') or 0)
                            videos = int(payload.get('videos') or 0)
                            directories = int(payload.get('directories') or 0)
                            phase = payload.get('phase') or 'scanning'
                            if phase == 'already_running':
                                finish_native_scan()
                                text = 'A varredura desta pasta já está em andamento.'
                            elif phase == 'started':
                                text = 'Preparando varredura da pasta…'
                            else:
                                text = f'Verificando pasta… {directories} diretórios, {files} arquivos, {videos} vídeos.'
                            page.snack_bar = ft.SnackBar(ft.Text(text))
                            page.snack_bar.open = True
                            page.update()
                        elif event_type == 'saf_scan':
                            try:
                                saf_selection.finish()
                                stats = payload.get('stats') or {}
                                tree_uri = payload.get('treeUri', '')
                                if not tree_uri:
                                    raise ValueError('Resultado SAF sem pasta de origem.')
                                catalog=await asyncio.to_thread(library.ingest_documents, tree_uri, payload.get('documents', []), folder_name=payload.get('name'), scan_errors=stats.get('errors', []), scan_stats=stats, scan_id=payload.get('scanId'), scope_kind=payload.get('scopeKind') or 'root', scope_ref=payload.get('scopeRef') or None)
                                videos = int(stats.get('videos') or 0)
                                partial = bool(payload.get('partial') or stats.get('errors'))
                                message = ("Scan concluído parcialmente. Alguns diretórios não puderam ser acessados. " if partial else "")
                                message += f"Encontramos {videos} vídeo(s) em {len(catalog)} anime(s)." if videos else "Não encontramos vídeos compatíveis nesta pasta."
                                page.snack_bar=ft.SnackBar(ft.Text(message)); page.snack_bar.open=True; page.update()
                            except Exception:
                                page.snack_bar=ft.SnackBar(ft.Text('Não foi possível salvar a atualização da biblioteca.')); page.snack_bar.open=True; page.update()
                            finally:
                                finish_native_scan()
                                on_catalog_changed()
                                refresh_settings_if_active()
                        elif event_type == 'broad_storage_scan_progress':
                            files = int(payload.get('files') or 0)
                            videos = int(payload.get('videos') or 0)
                            directories = int(payload.get('directories') or 0)
                            phase = payload.get('phase') or 'scanning'
                            if phase == 'already_running':
                                finish_native_scan()
                                text = 'A varredura do armazenamento local já está em andamento.'
                            else:
                                text = 'Preparando armazenamento local…' if phase == 'started' else f'Verificando armazenamento… {directories} diretórios, {files} arquivos, {videos} vídeos.'
                            page.snack_bar = ft.SnackBar(ft.Text(text)); page.snack_bar.open = True; page.update()
                        elif event_type == 'broad_storage_scan':
                            try:
                                stats = payload.get('stats') or {}
                                source = payload.get('source') or 'broad-storage'
                                catalog = await asyncio.to_thread(library.ingest_documents, source, payload.get('documents') or [], folder_name=payload.get('name') or 'Armazenamento local', scan_errors=stats.get('errors', []), scan_stats=stats, source_kind='broad_storage', scan_id=payload.get('scanId'), scope_kind=payload.get('scopeKind') or 'global', scope_ref=payload.get('scopeRef') or source)
                                store.add_folder(source, name=payload.get('name') or 'Armazenamento local', kind='broad_storage', authorization='granted', account_id=store.account().get('id'))
                                videos = int(stats.get('videos') or 0)
                                partial = bool(payload.get('partial') or stats.get('errors'))
                                message = ('Armazenamento local atualizado parcialmente. ' if partial else 'Armazenamento local atualizado. ')
                                message += f'{videos} vídeo(s) em {len(catalog)} anime(s).' if videos else 'Nenhum vídeo compatível encontrado.'
                                page.snack_bar = ft.SnackBar(ft.Text(message)); page.snack_bar.open = True; page.update()
                            except Exception:
                                page.snack_bar = ft.SnackBar(ft.Text('Não foi possível salvar o índice do armazenamento local.')); page.snack_bar.open = True; page.update()
                            finally:
                                finish_native_scan()
                                on_catalog_changed()
                                refresh_settings_if_active()
                        elif event_type == 'broad_storage_status':
                            granted = bool(payload.get('hasAccess'))
                            storage_onboarding["broad"] = granted
                            if storage_onboarding["waiting_for_result"] and not granted:
                                storage_onboarding["dismissed"] = True
                            storage_onboarding["waiting_for_result"] = False
                            roots = payload.get('roots') or []
                            volumes = payload.get('volumes') or []
                            if granted:
                                store.add_folder('broad-storage', name='Armazenamento local', kind='broad_storage', authorization='granted', account_id=store.account().get('id'))
                                readable = sum(1 for root in roots if root.get('readable') and root.get('directory'))
                                store.update_folder_status('broad-storage', 'granted', f'Diagnóstico: {readable} raiz(es) legível(is), {len(volumes)} volume(s) detectado(s).')
                            else:
                                store.update_folder_status('broad-storage', 'revoked', 'Acesso amplo ao armazenamento não concedido.')
                            refresh_settings_if_active()
                            maybe_show_storage_onboarding()
                        elif event_type == 'broad_storage_permission':
                            granted = bool(payload.get('granted'))
                            was_waiting = storage_onboarding["waiting_for_result"]
                            storage_onboarding["broad"] = granted
                            storage_onboarding["waiting_for_result"] = False
                            if granted:
                                storage_onboarding["dismissed"] = False
                                store.add_folder('broad-storage', name='Armazenamento local', kind='broad_storage', authorization='granted', account_id=store.account().get('id'))
                            else:
                                if was_waiting:
                                    # The native host emits a status event immediately before
                                    # opening Android Settings. Do not reopen the onboarding modal
                                    # over that external flow.
                                    storage_onboarding["dismissed"] = True
                                store.update_folder_status('broad-storage', 'revoked', 'Acesso amplo ao armazenamento ainda não foi concedido.')
                                finish_native_scan()
                            refresh_settings_if_active()
                            maybe_show_storage_onboarding()
                        elif event_type == 'broad_storage_error':
                            storage_onboarding["waiting_for_result"] = False
                            store.update_folder_status('broad-storage', 'revoked', event.get('message', 'Não foi possível acessar o armazenamento local.'))
                            finish_native_scan(); page.snack_bar = ft.SnackBar(ft.Text(event.get('message', 'Não foi possível acessar o armazenamento local.'))); page.snack_bar.open = True; page.update()
                            refresh_settings_if_active()
                        elif event_type == 'mediastore_scan_progress':
                            files = int(payload.get('files') or 0)
                            videos = int(payload.get('videos') or 0)
                            phase = payload.get('phase') or 'scanning'
                            if phase == 'already_running':
                                finish_native_scan()
                                text = 'A varredura dos vídeos do dispositivo já está em andamento.'
                            else:
                                text = 'Preparando vídeos do dispositivo…' if phase == 'started' else f'Verificando vídeos do dispositivo… {files} itens, {videos} vídeos.'
                            page.snack_bar = ft.SnackBar(ft.Text(text))
                            page.snack_bar.open = True
                            page.update()
                        elif event_type == 'mediastore_scan':
                            try:
                                stats = payload.get('stats') or {}
                                source = payload.get('source') or 'mediastore:external:video'
                                documents = payload.get('documents') or []
                                catalog = await asyncio.to_thread(
                                    library.ingest_documents,
                                    source,
                                    documents,
                                    folder_name=payload.get('name') or 'Vídeos do dispositivo',
                                    scan_errors=stats.get('errors', []),
                                    scan_stats=stats,
                                    source_kind='mediastore',
                                )
                                videos = int(stats.get('videos') or 0)
                                partial = bool(payload.get('partial') or stats.get('errors'))
                                message = ('Atualização do dispositivo concluída parcialmente. ' if partial else 'Vídeos do dispositivo atualizados. ')
                                message += f'{videos} vídeo(s) em {len(catalog)} anime(s).' if videos else 'Nenhum vídeo compatível encontrado.'
                                page.snack_bar = ft.SnackBar(ft.Text(message))
                                page.snack_bar.open = True
                                page.update()
                            except Exception:
                                page.snack_bar = ft.SnackBar(ft.Text('Não foi possível salvar os vídeos do dispositivo.'))
                                page.snack_bar.open = True
                                page.update()
                            finally:
                                finish_native_scan()
                                on_catalog_changed()
                                refresh_settings_if_active()
                        elif event_type == 'mediastore_permission':
                            source = payload.get('source') or 'mediastore:external:video'
                            access = str(payload.get('access') or 'denied')
                            storage_onboarding["media"] = access
                            if storage_onboarding["waiting_for_result"]:
                                storage_onboarding["waiting_for_result"] = False
                                if access == 'denied':
                                    storage_onboarding["dismissed"] = True
                            if payload.get('granted'):
                                label = 'acesso total' if access == 'full' else 'acesso parcial'
                                store.add_folder(
                                    source,
                                    name='Vídeos do dispositivo',
                                    kind='mediastore',
                                    authorization='granted',
                                    account_id=store.account().get('id'),
                                )
                                store.update_folder_status(source, 'granted', f'Permissão de vídeos: {label}.')
                            else:
                                store.update_folder_status(source, 'revoked', 'A permissão para vídeos do dispositivo foi removida.')
                            refresh_settings_if_active()
                            maybe_show_storage_onboarding()
                        elif event_type == 'mediastore_error':
                            source = payload.get('source') or 'mediastore:external:video'
                            store.update_folder_status(source, 'revoked', event.get('message', 'Não foi possível acessar os vídeos do dispositivo.'))
                            finish_native_scan()
                            page.snack_bar = ft.SnackBar(ft.Text(event.get('message', 'Não foi possível acessar os vídeos do dispositivo.')))
                            page.snack_bar.open = True
                            page.update()
                            refresh_settings_if_active()
                        elif event_type in {'player_progress', 'player_paused', 'player_exited', 'player_completed'}:
                            uri = payload.get('uri', '')
                            if isinstance(payload, dict) and isinstance(uri, str) and uri:
                                store.save_progress(
                                    uri,
                                    payload.get('positionMs', 0) / 1000,
                                    payload.get('durationMs', 0) / 1000,
                                    event_created_at=event.get('createdAt'),
                                )
                                # The durable store is the single source of truth;
                                # refresh active projections after meaningful playback
                                # events without rescanning or rebuilding the database.
                                if navigation.current != 'player':
                                    render_current()
                            if event_type == 'player_exited' and navigation.current == 'player':
                                navigate_back()
                        elif event_type == 'player_autoplay_changed':
                            enabled = bool((payload or {}).get('enabled'))
                            store.set_preference('autoplay_next', 'true' if enabled else 'false')
                        elif event_type in {'player_next_request', 'player_previous_request'}:
                            uri = payload.get('uri', '')
                            target = library.next_episode(uri) if event_type == 'player_next_request' else library.previous_episode(uri)
                            if target:
                                episode_label = f"T{target.get('season', '—')} E{target.get('number') if target.get('number') is not None else '—'}"
                                player_title = f"{target.get('anime_title') or target.get('file_name')} • {episode_label}"
                                await start_native_player(target['path'], player_title, 0)
                        elif event_type in {'player_mark_watched', 'player_mark_unwatched'}:
                            uri = payload.get('uri', '')
                            if uri:
                                store.set_watched(uri, event_type == 'player_mark_watched')
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
                        elif event_type == 'saf_inventory':
                            trees = payload.get('trees') or []
                            current_uris = {
                                str(item.get('treeUri'))
                                for item in trees
                                if isinstance(item, dict) and item.get('treeUri')
                            }
                            logger.info(
                                "[STORAGE] action=saf_inventory native_result=received "
                                "count=%s lifecycle=%s",
                                len(current_uris),
                                payload.get('lifecycle', '-'),
                            )
                            for folder in store.folders():
                                if folder.get('kind') != 'saf':
                                    continue
                                reference = str(folder.get('path') or '')
                                if not reference:
                                    continue
                                if reference in current_uris:
                                    if folder.get('authorization') != 'granted':
                                        store.update_folder_status(reference, 'granted')
                                else:
                                    store.update_folder_status(
                                        reference,
                                        'revoked',
                                        'A autorização SAF desta pasta não está mais presente no Android.',
                                    )
                            refresh_settings_if_active()
                        elif event_type == 'saf_cancelled':
                            saf_selection.finish()
                            page.snack_bar=ft.SnackBar(ft.Text('Seleção de pasta cancelada.')); page.snack_bar.open=True; page.update()
                            refresh_settings_if_active()
                        elif event_type == 'saf_permission':
                            tree_uri = payload.get('treeUri')
                            if tree_uri:
                                if payload.get('granted'):
                                    # A freshly selected tree must be registered before
                                    # scanning so a provider failure does not make the
                                    # user's persisted permission disappear from Settings.
                                    if payload.get('selected'):
                                        store.add_folder(
                                            tree_uri,
                                            name=payload.get('name') or tree_uri.rsplit('/', 1)[-1],
                                            kind='saf',
                                            authorization='granted',
                                            account_id=store.account().get('id'),
                                        )
                                    else:
                                        store.update_folder_status(tree_uri, 'granted')
                                else:
                                    store.update_folder_status(tree_uri, 'revoked', 'A permissão desta pasta foi removida.')
                                refresh_settings_if_active()
                        elif event_type == 'saf_released':
                            tree_uri = payload.get('treeUri')
                            if tree_uri and tree_uri in pending_folder_removals:
                                pending_folder_removals.discard(tree_uri)
                                store.remove_folder(tree_uri)
                                on_catalog_changed()
                                refresh_settings_if_active()
                                page.snack_bar=ft.SnackBar(ft.Text('Pasta removida da biblioteca.')); page.snack_bar.open=True; page.update()
                        elif event_type == 'google_cancelled':
                            account_state[0] = 'disconnected'
                            page.snack_bar=ft.SnackBar(ft.Text('Entrada com Google cancelada.')); page.snack_bar.open=True; page.update(); refresh_settings_if_active()
                        elif event_type in {'saf_error','google_error'}:
                            if event_type == 'saf_error':
                                saf_selection.finish()
                                tree_uri = payload.get('treeUri')
                                if tree_uri and tree_uri in pending_folder_removals:
                                    pending_folder_removals.discard(tree_uri)
                                    page.snack_bar=ft.SnackBar(ft.Text(event.get('message', 'Não foi possível liberar a pasta.'))); page.snack_bar.open=True; page.update()
                                    refresh_settings_if_active()
                                    continue
                                if tree_uri:
                                    store.update_folder_status(tree_uri, 'revoked', event.get('message', 'Não foi possível acessar a pasta.'))
                                # A re-scan has no successful result event to clear
                                # its lock.  Without this, Settings can remain on its
                                # disabled loading button after one revoked grant.
                                if scan_in_progress[0]:
                                    finish_native_scan()
                            if event_type == 'google_error':
                                code = str(event.get('code') or 'credential_error')
                                account_state[0] = 'configuration_required' if code == 'configuration_required' else 'error'
                                if code == 'no_credential':
                                    message = 'Nenhuma conta/credencial Google disponível. Verifique se uma conta Google está configurada no dispositivo.'
                                elif code == 'unsupported':
                                    message = 'Este dispositivo não oferece suporte ao Gerenciador de Credenciais usado pelo Rei-Flix.'
                                elif code == 'provider_configuration':
                                    message = 'O provedor Google do Gerenciador de Credenciais não está configurado corretamente.'
                                elif code == 'invalid_credential':
                                    message = 'O Google retornou uma credencial que não pôde ser validada com segurança.'
                                elif code == 'configuration_required':
                                    message = 'O login Google precisa de um Web Client ID válido neste APK.'
                                else:
                                    message = event.get('message', 'O login Google não pôde ser concluído.')
                                page.snack_bar=ft.SnackBar(ft.Text(message)); page.snack_bar.open=True; page.update()
                            if event_type == 'saf_error': refresh_settings_if_active()
                        elif event_type == 'android_back':
                            navigate_back()
                    except Exception as exc:
                        print(f"[ANDROID] Erro ao processar evento nativo: {exc}")
                # NativeMailbox retains the atomically claimed batch until this
                # point, after SQLite/UI handling has completed. A process restart
                # before acknowledgement replays the complete batch safely.
                bridge.acknowledge()
            except Exception as exc:
                print(f"[ANDROID] Erro no loop da ponte nativa: {exc}")
            await asyncio.sleep(0.2)
    page.on_login=login_done
    page.run_task(poll_native_bridge)
    if recovered_scans:
        page.snack_bar = ft.SnackBar(ft.Text(
            f"{len(recovered_scans)} varredura(s) anterior(es) foram interrompidas e poderão ser refeitas."
        ))
        page.snack_bar.open = True
        page.update()
    if bridge.available:
        # MainActivity publishes the authoritative SAF grant inventory from
        # onResume. Never self-launch reiflix://native during app startup just
        # to verify persisted trees; this can re-enter the singleTask Activity
        # while Flet is still mounting.
        pass
    render_current()

if __name__ == "__main__":
    ft.run(main)
