import os
import asyncio
import logging
import flet as ft
from flet.auth import OAuthProvider
from app_config import GOOGLE_CLIENT_ID as CONFIG_GOOGLE_CLIENT_ID, GOOGLE_REDIRECT_URL as CONFIG_GOOGLE_REDIRECT_URL, GOOGLE_WEB_CLIENT_ID as CONFIG_GOOGLE_WEB_CLIENT_ID
from core.android_bridge import AndroidBridge
from core.navigation import NavigationController, SafSelectionState
from core.storage_access import StorageAccessState, StorageCapabilities, ScanUiState, scan_ui_state_from_native, storage_access_state, storage_source_states
from core.diagnostics import DiagnosticTimeline
from core.library_store import LibraryStore
from core.library_service import LibraryService
from core.google_account import normalize_google_profile
from views.home_view import HomeView
from views.details_view import DetailView
from views.organize_view import OrganizeView
from views.player_view import PlayerView
from views.settings_view import SettingsView

logger = logging.getLogger("reiflix")

GOOGLE_CLIENT_ID = os.getenv('REIFLIX_GOOGLE_CLIENT_ID', CONFIG_GOOGLE_CLIENT_ID)
GOOGLE_REDIRECT_URL = os.getenv('REIFLIX_GOOGLE_REDIRECT_URL', CONFIG_GOOGLE_REDIRECT_URL)
GOOGLE_WEB_CLIENT_ID = os.getenv('REIFLIX_GOOGLE_WEB_CLIENT_ID', CONFIG_GOOGLE_WEB_CLIENT_ID)

async def main(page: ft.Page):
    page.title='Rei-Flix Local'; page.theme_mode=ft.ThemeMode.DARK; page.bgcolor='#16151F'; page.padding=0
    try:
        page.on_disconnect = lambda _e: ui_alive.__setitem__(0, False)
    except Exception as exc:
        logger.warning("[FLET] on_disconnect hook unavailable: %s", exc)
    page.theme=ft.Theme(color_scheme_seed='#E50914',font_family='Roboto')
    data_dir=os.getenv("FLET_APP_STORAGE_DATA") or os.path.join(os.path.dirname(__file__),'.reiflix-data')
    store=LibraryStore(data_dir)
    recovered_scans=store.interrupted_scans()
    library=LibraryService(store); bridge=AndroidBridge(data_dir, page); current=[None]
    account_state=["connected" if store.account().get("email") else "disconnected"]
    diagnostics = DiagnosticTimeline()
    diagnostics.record("APP_START", result="python_ui_initialized")
    scan_in_progress=[False]
    pending_native_scans=[0]
    scan_state = [{
        "state": ScanUiState.IDLE.value,
        "source": None,
        "volume": None,
        "scanId": None,
        "found": 0,
        "files": 0,
        "directories": 0,
        "error": None,
        "timestamp": None,
    }]
    ui_alive = [True]
    def safe_update():
        if not ui_alive[0]:
            return
        try:
            page.update()
        except Exception as exc:
            logger.debug("[FLET] safe_update ignored stale lifecycle callback: %s", exc)
    def set_scan_state(state, *, source=None, volume=None, scan_id=None, found=None,
                       files=None, directories=None, error=None, timestamp=None):
        current = scan_state[0]
        scan_state[0] = {
            "state": str(state.value if isinstance(state, ScanUiState) else state),
            "source": source if source is not None else current.get("source"),
            "volume": volume if volume is not None else current.get("volume"),
            "scanId": scan_id if scan_id is not None else current.get("scanId"),
            "found": int(found if found is not None else current.get("found") or 0),
            "files": int(files if files is not None else current.get("files") or 0),
            "directories": int(directories if directories is not None else current.get("directories") or 0),
            "error": error,
            "timestamp": timestamp or current.get("timestamp"),
        }
    pending_folder_removals=set()
    # View-local query/filter state survives Details/Player round-trips while
    # the catalog itself is still read afresh from SQLite on each view entry.
    home_state = {}
    organize_state = {}
    navigation = NavigationController()
    saf_selection = SafSelectionState()
    # Runtime snapshots are deliberately not stored in SQLite: only Android is
    # proof of a current grant.  ``dismissed`` prevents an automatic onboarding loop.
    storage_onboarding = {"dismissed": False, "dialog_open": False, "waiting_for_result": False}
    storage_capabilities = [StorageCapabilities.unknown()]
    processed_native_operations = set()
    def show(control): page.clean(); page.add(control); safe_update()
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
                                    on_create_backup=create_backup, on_restore_backup=restore_backup,
                                    storage_snapshot=storage_capabilities[0], scan_snapshot=scan_state[0]))
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
            safe_update()
        except Exception:
            page.snack_bar = ft.SnackBar(ft.Text("Não foi possível atualizar a metadata agora."))
            page.snack_bar.open = True
            safe_update()
    def on_catalog_changed():
        diagnostics.record("UI_REFRESHED", result="catalog_changed", source=navigation.current)
        # Native scan completion must immediately re-read SQLite on the active
        # screen; the previous implementation intentionally did nothing here,
        # leaving a freshly indexed catalog invisible until manual navigation.
        render_current()
    async def remove_folder(reference):
        if scan_in_progress[0] or saf_selection.pending:
            page.snack_bar = ft.SnackBar(ft.Text("Aguarde a atualização ou a seleção de pasta terminar antes de remover uma pasta."))
            page.snack_bar.open = True
            safe_update()
            return
        folder = next((item for item in store.folders() if item.get("path") == reference), None)
        if folder and folder.get("kind") == "saf" and bridge.available:
            try:
                pending_folder_removals.add(reference)
                await bridge.release_tree(reference)
                page.snack_bar = ft.SnackBar(ft.Text("Liberando a permissão da pasta…"))
                page.snack_bar.open = True
                safe_update()
            except Exception as exc:
                pending_folder_removals.discard(reference)
                page.snack_bar = ft.SnackBar(ft.Text(f"Não foi possível liberar a pasta: {exc}"))
                page.snack_bar.open = True
                safe_update()
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
            safe_update()

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
            diagnostics.record("PERMISSION_CHECK", source="android")
            page.run_task(bridge.check_storage_access)
    def navigate_back():
        action = navigation.back()
        if action == "previous":
            render_current()
        elif action == "prompt_exit":
            page.snack_bar=ft.SnackBar(ft.Text("Pressione voltar novamente para sair")); page.snack_bar.open=True; safe_update()
        elif action == "exit":
            # Close only after the Android/Python shared two-back policy.
            page.window.close()
    def refresh_settings_if_active():
        if navigation.current == "settings":
            render_current()
    async def add_folder(_=None):
        if scan_in_progress[0] or not saf_selection.begin():
            return False
        try:
            await bridge.select_tree()
            return True
        except Exception as exc:
            saf_selection.finish()
            page.snack_bar=ft.SnackBar(ft.Text(str(exc))); page.snack_bar.open=True; safe_update()
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
        caps = storage_capabilities[0]
        return storage_access_state(
            caps.media_read_state,
            caps.broad_storage_state == "available",
            bool(caps.saf_roots),
            dismissed=storage_onboarding["dismissed"],
        )

    def apply_storage_capabilities(payload):
        raw = payload.get("capabilities") if isinstance(payload, dict) else None
        if isinstance(raw, dict):
            storage_capabilities[0] = StorageCapabilities.from_native(raw)
        elif isinstance(payload, dict) and ("mediaReadState" in payload or "broadStorageState" in payload):
            storage_capabilities[0] = StorageCapabilities.from_native(payload)

    def update_saf_capabilities(current_uris):
        current = storage_capabilities[0]
        roots = tuple(sorted({str(uri).strip() for uri in current_uris if str(uri).strip()}))
        scanners = set(current.scanner_capabilities)
        if roots:
            scanners.add("saf")
        else:
            scanners.discard("saf")
        storage_capabilities[0] = StorageCapabilities(
            media_read_state=current.media_read_state,
            broad_storage_state=current.broad_storage_state,
            saf_roots=roots,
            removable_volumes=current.removable_volumes,
            scanner_capabilities=frozenset(scanners),
            reconciliation_capabilities=current.reconciliation_capabilities,
            lifecycle_state=current.lifecycle_state,
            api=current.api,
        )

    def maybe_show_storage_onboarding():
        """Show at most one post-render explanation based on Android's snapshot."""
        if not bridge.available or storage_onboarding["dialog_open"] or storage_onboarding["waiting_for_result"]:
            return
        if not storage_capabilities[0].known:
            return
        state = storage_state()
        if state != StorageAccessState.NEEDS_MEDIA_PERMISSION:
            return
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Permissão necessária"),
            content=ft.Text(
                "O Rei-flix precisa de uma fonte de acesso aos seus vídeos locais. "
                "Você pode permitir o acesso aos vídeos do dispositivo ou escolher uma pasta específica."
            ),
        )

        async def allow_media(_event):
            storage_onboarding["dialog_open"] = False
            storage_onboarding["waiting_for_result"] = True
            page.pop_dialog()
            try:
                await request_video_access()
            except Exception:
                storage_onboarding["waiting_for_result"] = False
                page.snack_bar = ft.SnackBar(
                    ft.Text("Não foi possível abrir a solicitação de acesso.")
                )
                page.snack_bar.open = True
                safe_update()

        async def choose_folder(_event):
            storage_onboarding["dialog_open"] = False
            storage_onboarding["waiting_for_result"] = True
            page.pop_dialog()
            try:
                started = await add_folder()
                if not started:
                    storage_onboarding["waiting_for_result"] = False
                    page.snack_bar = ft.SnackBar(
                        ft.Text("A seleção de pasta já está em andamento ou a biblioteca está sendo atualizada.")
                    )
                    page.snack_bar.open = True
                    safe_update()
            except Exception:
                storage_onboarding["waiting_for_result"] = False
                page.snack_bar = ft.SnackBar(
                    ft.Text("Não foi possível abrir o seletor de pasta.")
                )
                page.snack_bar.open = True
                safe_update()

        def cancel(_event):
            logger.info("[STORAGE] request_id=- action=cancel python_callback=received dialog_open=false")
            storage_onboarding["dialog_open"] = False
            storage_onboarding["dismissed"] = True
            page.pop_dialog()
            safe_update()

        dialog.actions = [
            ft.TextButton("CANCELAR", on_click=cancel),
            ft.TextButton("ESCOLHER PASTA", on_click=choose_folder),
            ft.FilledButton("PERMITIR", on_click=allow_media),
        ]
        storage_onboarding["dialog_open"] = True
        logger.info("[STORAGE] request_id=- action=onboarding_show dialog_open=true")
        page.show_dialog(dialog)
        safe_update()

    async def refresh_library(_=None):
        if saf_selection.pending:
            return "Conclua ou cancele a seleção da pasta antes de atualizar a biblioteca.", False
        if scan_in_progress[0]:
            return "Uma atualização da biblioteca já está em andamento.", True
        scan_in_progress[0] = True
        set_scan_state(ScanUiState.CHECKING, source="orchestrator", error=None, timestamp=asyncio.get_running_loop().time())
        safe_update()
        try:
            folders = store.folders()
            caps = storage_capabilities[0]
            if bridge.available and not caps.known:
                set_scan_state(ScanUiState.CHECKING, source="permissions")
                await bridge.check_storage_access()
                return "Verificando as permissões do armazenamento…", True
            authorized_roots = set(caps.saf_roots)
            saf_folders = [
                folder for folder in folders
                if folder.get('kind') == 'saf' and folder.get('path') in authorized_roots
            ]
            mediastore_granted = caps.can_scan("mediastore")
            if bridge.available:
                # Android runtime capabilities are authoritative; SQLite rows are
                # durable configuration/catalog data and never grant scan access.
                pending_native_scans[0] = 0
                broad_granted = caps.can_scan("broad-storage")
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
                    set_scan_state(ScanUiState.SCANNING, source="multiple")
                    missing_sources = []
                    if not mediastore_granted:
                        missing_sources.append("vídeos do dispositivo")
                    if not broad_granted:
                        missing_sources.append("armazenamento amplo")
                    if missing_sources:
                        return "Atualização iniciada. Ainda sem acesso a " + ", ".join(missing_sources) + ".", True
                    return "Atualização iniciada. Verificando as fontes locais…", True
                scan_in_progress[0] = False
                set_scan_state(ScanUiState.COMPLETED, source="orchestrator", found=0)
                return "Nenhuma fonte local pôde iniciar uma varredura.", False
            result = await asyncio.to_thread(library.scan)
            return result.message(), False
        except Exception as exc:
            scan_in_progress[0] = False
            set_scan_state(ScanUiState.FAILED, source="orchestrator", error=str(exc))
            safe_update()
            raise
        finally:
            if not (bridge.available and pending_native_scans[0] > 0):
                scan_in_progress[0] = False
    async def login(_=None):
        if bridge.available:
            if not GOOGLE_WEB_CLIENT_ID:
                account_state[0] = 'configuration_required'; navigate_settings()
                page.snack_bar=ft.SnackBar(ft.Text('Login Google não configurado neste APK. Configure um Web Client ID público antes de tentar novamente.')); page.snack_bar.open=True; safe_update(); return
            account_state[0] = 'connecting'; navigate_settings()
            await bridge.sign_in(GOOGLE_WEB_CLIENT_ID); return
        account_state[0] = 'connecting'; navigate_settings()
        if not GOOGLE_CLIENT_ID or not GOOGLE_REDIRECT_URL:
            account_state[0] = 'error'; navigate_settings()
            page.snack_bar=ft.SnackBar(ft.Text('Configure REIFLIX_GOOGLE_CLIENT_ID e REIFLIX_GOOGLE_REDIRECT_URL para entrar com Google.'))
            page.snack_bar.open=True; safe_update(); return
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
            page.snack_bar=ft.SnackBar(ft.Text(f'Não foi possível entrar: {e.error_description or e.error}')); page.snack_bar.open=True; safe_update(); return
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

        async def ingest_native_batch(event_type, payload, event_request_id):
            source_map = {
                "saf_scan_batch": ("saf", "root"),
                "broad_storage_scan_batch": ("broad_storage", "volume"),
                "mediastore_scan_batch": ("mediastore", "volume"),
            }
            source_kind, default_scope_kind = source_map[event_type]
            documents = payload.get("documents") or []
            scope_kind = payload.get("scopeKind") or default_scope_kind
            scope_ref = payload.get("scopeRef") or payload.get("scope") or payload.get("volumeId") or event_type
            source_reference = (
                payload.get("treeUri")
                if source_kind == "saf"
                else payload.get("source")
                or ("broad-storage" if source_kind == "broad_storage" else "mediastore:external:video")
            )
            scope_scan_id = str(payload.get("scopeScanId") or payload.get("scanId") or "").strip()
            if scope_kind == "volume" and scope_ref and scope_scan_id and ":" not in scope_scan_id:
                scope_scan_id = f"{scope_scan_id}:{scope_ref}"
            result = await asyncio.to_thread(
                library.ingest_documents_batch,
                source_reference or source_kind,
                documents,
                source_kind=source_kind,
                scan_id=scope_scan_id or payload.get("scanId"),
                scope_kind=scope_kind,
                scope_ref=scope_ref,
                scan_generation=payload.get("scanGeneration"),
                generation_id=payload.get("generationId"),
                request_id=event_request_id,
                batch_id=payload.get("batchId"),
                batch_number=payload.get("batchNumber") or 0,
                batch_size=payload.get("batchSize"),
                folder_name=payload.get("name") or None,
            )
            diagnostics.record(
                "SCAN_BATCH",
                request_id=event_request_id,
                scan_id=scope_scan_id or payload.get("scanId"),
                source=source_kind,
                result="INGESTED" if not result.get("ignored") else "IGNORED",
                counts={
                    "batchId": payload.get("batchId"),
                    "batchNumber": payload.get("batchNumber") or 0,
                    "batchSize": payload.get("batchSize") or len(documents),
                    "processed": result.get("files", 0),
                    "discovered": len(documents),
                    "inserted": result.get("new", 0),
                    "updated": result.get("updated", 0),
                    "unchanged": result.get("unchanged", 0),
                    "duplicates": result.get("duplicates", 0),
                    "errors": len(result.get("errors") or []),
                    "elapsedMs": result.get("elapsed_ms", 0),
                },
            )
            return result

        poll_interval = 0.1
        while True:
            try:
                events = bridge.drain()
                failed_event_ids = set()
                for event in events:
                    try:
                        if not isinstance(event, dict):
                            continue
                        event_id = event.get('eventId')
                        if event_id and store.has_native_event(event_id):
                            continue
                        event_type = event.get('type')
                        payload = event.get('payload')
                        if payload is None:
                            payload = {}
                        if not isinstance(payload, dict):
                            continue
                        event_request_id = event.get('requestId') or payload.get('requestId')
                        event_scan_id = payload.get('scanId') or event.get('scanId')
                        if event_type == 'diagnostic':
                            diagnostics.record(
                                str(payload.get('event') or 'NATIVE_DIAGNOSTIC'),
                                request_id=event_request_id,
                                scan_id=event_scan_id,
                                source=payload.get('source'),
                                result=payload.get('result') or payload.get('access'),
                            )
                        else:
                            timeline_name = {
                                'storage_capabilities': 'ACTUAL_PERMISSION_STATE',
                                'mediastore_permission': 'PERMISSION_RESULT',
                                'broad_storage_permission': 'PERMISSION_RESULT',
                                'saf_permission': 'PERMISSION_RESULT',
                                'saf_scan_progress': 'SCAN_PROGRESS',
                                'broad_storage_scan_progress': 'SCAN_PROGRESS',
                                'mediastore_scan_progress': 'SCAN_PROGRESS',
                                'saf_scan_batch': 'SCAN_BATCH',
                                'broad_storage_scan_batch': 'SCAN_BATCH',
                                'mediastore_scan_batch': 'SCAN_BATCH',
                                'saf_scan': 'SCAN_COMPLETED',
                                'broad_storage_scan': 'SCAN_COMPLETED',
                                'mediastore_scan': 'SCAN_COMPLETED',
                                'saf_error': 'SCAN_FAILED',
                                'broad_storage_error': 'SCAN_FAILED',
                                'mediastore_error': 'SCAN_FAILED',
                                'volume_changed': 'VOLUME_CHANGED',
                            }.get(event_type)
                            if timeline_name:
                                diagnostics.record(timeline_name, request_id=event_request_id, scan_id=event_scan_id,
                                                   source=payload.get('source'),
                                                   result=payload.get('status'),
                                                   error=event.get('message'))
                        # Every native event updates one compact UI state projection.
                        # The projection is diagnostic only; Android remains authoritative.
                        if event_type in {'saf_scan_batch', 'broad_storage_scan_batch', 'mediastore_scan_batch'}:
                            try:
                                await ingest_native_batch(event_type, payload, event_request_id)
                                set_scan_state(
                                    ScanUiState.SCANNING,
                                    source=payload.get('source') or event_type.replace('_scan_batch',''),
                                    volume=payload.get('volumeId'),
                                    scan_id=payload.get('scanId'),
                                    found=payload.get('processed') or payload.get('batchSize') or 0,
                                    files=payload.get('processed') or payload.get('batchSize') or 0,
                                    timestamp=event.get('createdAt'),
                                )
                                safe_update()
                            except Exception as exc:
                                logger.exception("[STORAGE] batch ingest failed: %s", exc)
                                page.snack_bar=ft.SnackBar(ft.Text('Não foi possível processar um lote da biblioteca.')); page.snack_bar.open=True; safe_update()
                        if event_type in {'saf_scan_progress', 'broad_storage_scan_progress', 'mediastore_scan_progress'}:
                            phase = str(payload.get('phase') or 'scanning').upper()
                            native_state = ScanUiState.SCANNING if phase not in {'STARTED', 'CHECKING'} else ScanUiState.CHECKING
                            if phase == 'ALREADY_RUNNING':
                                native_state = ScanUiState.SCANNING
                            set_scan_state(
                                native_state,
                                source=payload.get('source') or event_type.replace('_scan_progress', ''),
                                volume=payload.get('volumeId') or payload.get('volume') or None,
                                scan_id=payload.get('scanId'),
                                found=payload.get('videos'),
                                files=payload.get('files'),
                                directories=payload.get('directories'),
                                timestamp=event.get('createdAt') or payload.get('timestamp'),
                            )
                            safe_update()
                        contract_event = str(event.get('eventType') or '').strip()
                        request_id = str(event.get('requestId') or payload.get('requestId') or '').strip()
                        operation_key = None
                        if event_type in {
                            'saf_scan', 'broad_storage_scan', 'mediastore_scan',
                            'saf_error', 'broad_storage_error', 'mediastore_error',
                        }:
                            discriminator = payload.get('scanId') or request_id
                            if discriminator:
                                operation_key = f"{event_type}:{discriminator}"
                                if operation_key in processed_native_operations:
                                    logger.info("[STORAGE] duplicate native operation ignored key=%s", operation_key)
                                    continue
                        if contract_event == 'permission_requested':
                            logger.info("[STORAGE] permission_requested type=%s requestId=%s", event_type, request_id or "-")
                        elif contract_event == 'permission_cancelled':
                            storage_onboarding["waiting_for_result"] = False
                        if event_type == 'storage_capabilities':
                            apply_storage_capabilities(payload)
                            refresh_settings_if_active()
                            maybe_show_storage_onboarding()
                        elif event_type == 'saf_scan_progress':
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
                            safe_update()
                        elif event_type == 'saf_scan':
                            try:
                                saf_selection.finish()
                                stats = payload.get('stats') or {}
                                tree_uri = payload.get('treeUri', '')
                                if not tree_uri:
                                    raise ValueError('Resultado SAF sem pasta de origem.')
                                diagnostics.record("PYTHON_INGEST_FINAL", request_id=request_id, scan_id=payload.get('scanId'), source="saf")
                                if payload.get('documents'):
                                    catalog=await asyncio.to_thread(library.ingest_documents, tree_uri, payload.get('documents', []), folder_name=payload.get('name'), scan_errors=stats.get('errors', []), scan_stats=stats, scan_id=payload.get('scanId'), scope_kind=payload.get('scopeKind') or 'root', scope_ref=payload.get('scopeRef') or None, scan_generation=payload.get('scanGeneration'))
                                else:
                                    final_result=await asyncio.to_thread(
                                        library.finish_ingest_documents,
                                        tree_uri,
                                        source_kind="saf",
                                        scan_id=payload.get('scanId'),
                                        scope_kind=payload.get('scopeKind') or 'root',
                                        scope_ref=payload.get('scopeRef') or tree_uri,
                                        scan_generation=payload.get('scanGeneration'),
                                        generation_id=payload.get('generationId'),
                                        status=payload.get('status') or stats.get('status') or 'completed',
                                        folder_name=payload.get('name'),
                                        scan_errors=stats.get('errors', []),
                                        scan_stats=stats,
                                    )
                                    catalog=final_result.catalog
                                videos = int(stats.get('videos') or 0)
                                status = str(payload.get('status') or stats.get('status') or '').upper()
                                partial = bool(payload.get('partial') or stats.get('errors') or status in {'PARTIAL', 'UNAVAILABLE'})
                                set_scan_state(
                                    scan_ui_state_from_native(
                                        status,
                                        errors=bool(stats.get('errors')),
                                        cancelled=status == 'CANCELLED',
                                        volume_available=status != 'UNAVAILABLE',
                                    ),
                                    source="saf",
                                    volume=payload.get('volumeId'),
                                    scan_id=payload.get('scanId'),
                                    found=videos,
                                    error=(stats.get('errors') or [None])[0] if stats.get('errors') else None,
                                    timestamp=event.get('createdAt'),
                                )
                                diagnostics.record("CATALOG_UPDATED", request_id=request_id, scan_id=payload.get('scanId'), source="saf", counts={"videos": videos, "catalog": len(catalog)}, result=status or "COMPLETED")
                                if status == 'CANCELLED':
                                    message = "Varredura da pasta cancelada. Os itens anteriores foram preservados."
                                elif status == 'UNAVAILABLE':
                                    message = "O provedor desta pasta está indisponível. Os itens anteriores foram preservados."
                                elif status == 'EMPTY_COMPLETE':
                                    message = "A pasta foi lida com sucesso e não contém vídeos compatíveis."
                                else:
                                    message = "Scan concluído parcialmente. Alguns diretórios não puderam ser acessados. " if partial else ""
                                    message += f"Encontramos {videos} vídeo(s) em {len(catalog)} anime(s)." if videos else "Não encontramos vídeos compatíveis nesta pasta."
                                page.snack_bar=ft.SnackBar(ft.Text(message)); page.snack_bar.open=True; safe_update()
                            except Exception:
                                page.snack_bar=ft.SnackBar(ft.Text('Não foi possível salvar a atualização da biblioteca.')); page.snack_bar.open=True; safe_update()
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
                            page.snack_bar = ft.SnackBar(ft.Text(text)); page.snack_bar.open = True; safe_update()
                        elif event_type == 'broad_storage_scan':
                            try:
                                stats = payload.get('stats') or {}
                                source = payload.get('source') or 'broad-storage'
                                scopes = payload.get('volumeScopes') or []
                                catalog = store.catalog()
                                if scopes:
                                    for scope in scopes:
                                        if not isinstance(scope, dict) or not scope.get('volumeId'):
                                            continue
                                        volume = str(scope.get('volumeId'))
                                        scan_id = str(scope.get('scanId') or ((payload.get('scanId') or 'broad-storage') + ':' + volume))
                                        scope_stats = dict(stats)
                                        scope_errors = scope.get('errors') or []
                                        if scope_errors:
                                            scope_stats['errors'] = scope_errors
                                        scope_status = str(scope.get('status') or '').casefold()
                                        if scope_status:
                                            scope_stats['status'] = scope_status
                                        if scope_status in {'cancelled', 'canceled'}:
                                            scope_stats['cancelled'] = True
                                        if not scope.get('complete'):
                                            scope_stats['partial'] = True
                                        diagnostics.record("PYTHON_INGEST", request_id=request_id, scan_id=scan_id, source=source)
                                        final_result = await asyncio.to_thread(
                                            library.finish_ingest_documents,
                                            source,
                                            source_kind='broad_storage',
                                            scan_id=scan_id,
                                            scope_kind='volume',
                                            scope_ref=volume,
                                            scan_generation=scope.get('scanGeneration'),
                                            generation_id=scope.get('generationId'),
                                            status=scope.get('status') or ('completed' if scope.get('complete') else 'partial'),
                                            folder_name=payload.get('name') or 'Armazenamento local',
                                            scan_errors=scope_errors, scan_stats=scope_stats,
                                        )
                                        catalog = final_result.catalog
                                else:
                                    diagnostics.record("PYTHON_INGEST", request_id=request_id, scan_id=payload.get('scanId'), source=source)
                                    catalog = await asyncio.to_thread(
                                        library.ingest_documents, source, payload.get('documents') or [],
                                        folder_name=payload.get('name') or 'Armazenamento local',
                                        scan_errors=stats.get('errors', []), scan_stats=stats, source_kind='broad_storage',
                                        scan_id=payload.get('scanId'), scope_kind='global', scope_ref=payload.get('scopeRef') or source,
                                        scan_generation=payload.get('scanGeneration'),
                                    )
                                videos = int(stats.get('videos') or 0)
                                partial = bool(payload.get('partial') or stats.get('errors'))
                                set_scan_state(
                                    scan_ui_state_from_native(
                                        str(stats.get('status') or payload.get('status') or ''),
                                        errors=partial,
                                        cancelled=bool(stats.get('cancelled')),
                                        volume_available=True,
                                    ),
                                    source="broad-storage",
                                    volume=payload.get('volumeId'),
                                    scan_id=payload.get('scanId'),
                                    found=videos,
                                    error=(stats.get('errors') or [None])[0] if stats.get('errors') else None,
                                    timestamp=event.get('createdAt'),
                                )
                                diagnostics.record("CATALOG_UPDATED", request_id=request_id, scan_id=payload.get('scanId'), source=source, counts={"videos": videos, "catalog": len(catalog)}, result=str(stats.get('status') or payload.get('status') or 'COMPLETED'))
                                message = ('Armazenamento local atualizado parcialmente. ' if partial else 'Armazenamento local atualizado. ')
                                message += f'{videos} vídeo(s) em {len(catalog)} anime(s).' if videos else 'Nenhum vídeo compatível encontrado.'
                                page.snack_bar = ft.SnackBar(ft.Text(message)); page.snack_bar.open = True; safe_update()
                            except Exception:
                                page.snack_bar = ft.SnackBar(ft.Text('Não foi possível salvar o índice do armazenamento local.')); page.snack_bar.open = True; safe_update()
                            finally:
                                finish_native_scan()
                                on_catalog_changed()
                                refresh_settings_if_active()
                        elif event_type == 'broad_storage_status':
                            granted = bool(payload.get('hasAccess'))
                            apply_storage_capabilities(payload)
                            if storage_onboarding["waiting_for_result"] and not granted:
                                storage_onboarding["dismissed"] = True
                            storage_onboarding["waiting_for_result"] = False
                            roots = payload.get('roots') or []
                            volumes = payload.get('volumes') or []
                            if granted:
                                store.add_folder('broad-storage', name='Armazenamento local', kind='broad_storage', authorization='granted', account_id=store.account().get('id'))
                                readable = sum(1 for root in roots if root.get('readable') and root.get('directory'))
                                store.update_folder_status('broad-storage', 'granted', f'Diagnóstico: {readable} raiz(es) legível(is), {len(volumes)} volume(s) detectado(s).')
                                store.restore_source('broad-storage')
                            else:
                                store.update_folder_status('broad-storage', 'revoked', 'Acesso amplo ao armazenamento não concedido.')
                                store.mark_source_unavailable('broad-storage', 'broad_access_revoked')
                            refresh_settings_if_active()
                            maybe_show_storage_onboarding()
                        elif event_type == 'broad_storage_permission':
                            granted = bool(payload.get('granted'))
                            was_waiting = storage_onboarding["waiting_for_result"]
                            apply_storage_capabilities(payload)
                            storage_onboarding["waiting_for_result"] = False
                            if granted:
                                storage_onboarding["dismissed"] = False
                                store.add_folder('broad-storage', name='Armazenamento local', kind='broad_storage', authorization='granted', account_id=store.account().get('id'))
                                store.restore_source('broad-storage')
                            else:
                                if was_waiting:
                                    # The native host emits a status event immediately before
                                    # opening Android Settings. Do not reopen the onboarding modal
                                    # over that external flow.
                                    storage_onboarding["dismissed"] = True
                                store.update_folder_status('broad-storage', 'revoked', 'Acesso amplo ao armazenamento ainda não foi concedido.')
                                store.mark_source_unavailable('broad-storage', 'broad_access_denied')
                                finish_native_scan()
                            refresh_settings_if_active()
                            maybe_show_storage_onboarding()
                        elif event_type == 'broad_storage_error':
                            storage_onboarding["waiting_for_result"] = False
                            message = event.get('message', 'Não foi possível acessar o armazenamento local.')
                            error_status = str(payload.get('status') or 'FAILED').upper()
                            if error_status in {'REVOKED', 'DENIED'}:
                                store.update_folder_status('broad-storage', 'revoked', message)
                                store.mark_source_unavailable('broad-storage', 'broad_access_revoked')
                            else:
                                store.update_folder_status('broad-storage', 'unavailable', message)
                                store.mark_source_unavailable('broad-storage', 'broad_scan_failed')
                            finish_native_scan(); page.snack_bar = ft.SnackBar(ft.Text(event.get('message', 'Não foi possível acessar o armazenamento local.'))); page.snack_bar.open = True; safe_update()
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
                            safe_update()
                        elif event_type == 'mediastore_scan':
                            try:
                                stats = payload.get('stats') or {}
                                source = payload.get('source') or 'mediastore:external:video'
                                scopes = payload.get('volumeScopes') or []
                                catalog = store.catalog()
                                if scopes:
                                    for scope in scopes:
                                        if not isinstance(scope, dict) or not scope.get('volumeId'):
                                            continue
                                        volume = str(scope.get('volumeId'))
                                        scan_id = str(scope.get('scanId') or ((payload.get('scanId') or 'mediastore') + ':' + volume))
                                        scope_stats = dict(stats)
                                        scope_errors = scope.get('errors') or []
                                        if scope_errors:
                                            scope_stats['errors'] = scope_errors
                                        if not scope.get('complete'):
                                            scope_stats['partial'] = True
                                        final_result = await asyncio.to_thread(
                                            library.finish_ingest_documents,
                                            source,
                                            source_kind='mediastore',
                                            scan_id=scan_id,
                                            scope_kind='volume',
                                            scope_ref=volume,
                                            scan_generation=scope.get('scanGeneration'),
                                            generation_id=scope.get('generationId'),
                                            status=scope.get('status') or ('completed' if scope.get('complete') else 'partial'),
                                            folder_name=payload.get('name') or 'Vídeos do dispositivo',
                                            scan_errors=scope_errors,
                                            scan_stats=scope_stats,
                                        )
                                        catalog = final_result.catalog
                                else:
                                    catalog = await asyncio.to_thread(
                                        library.ingest_documents, source, payload.get('documents') or [],
                                        folder_name=payload.get('name') or 'Vídeos do dispositivo',
                                        scan_errors=stats.get('errors', []), scan_stats=stats, source_kind='mediastore',
                                        scan_id=payload.get('scanId'), scope_kind='global', scope_ref=source,
                                        scan_generation=payload.get('scanGeneration'),
                                    )
                                videos = int(stats.get('videos') or 0)
                                set_scan_state(
                                    scan_ui_state_from_native(
                                        str(stats.get('status') or payload.get('status') or 'COMPLETED'),
                                        errors=bool(stats.get('errors')),
                                        cancelled=bool(stats.get('cancelled')),
                                        waiting_for_mediastore=str(stats.get('status') or payload.get('status') or '').upper() == ScanUiState.WAITING_FOR_MEDIASTORE.value,
                                    ),
                                    source="mediastore",
                                    volume=payload.get('volumeId'),
                                    scan_id=payload.get('scanId'),
                                    found=videos,
                                    error=(stats.get('errors') or [None])[0] if stats.get('errors') else None,
                                    timestamp=event.get('createdAt'),
                                )
                                diagnostics.record("CATALOG_UPDATED", request_id=request_id, scan_id=payload.get('scanId'), source=source, counts={"videos": videos, "catalog": len(catalog)}, result=str(stats.get('status') or payload.get('status') or 'COMPLETED'))
                                scan_status = str(stats.get('status') or payload.get('status') or 'COMPLETED').upper()
                                if scan_status == ScanUiState.WAITING_FOR_MEDIASTORE.value:
                                    message = 'Aguardando o Android concluir a indexação de mídia; a atualização continuará automaticamente.'
                                else:
                                    message = 'Vídeos do dispositivo atualizados. '
                                    message += f'{videos} vídeo(s) em {len(catalog)} anime(s).' if videos else 'Nenhum vídeo compatível encontrado.'
                                page.snack_bar = ft.SnackBar(ft.Text(message)); page.snack_bar.open = True; safe_update()
                            except Exception:
                                page.snack_bar=ft.SnackBar(ft.Text('Não foi possível salvar os vídeos do dispositivo.')); page.snack_bar.open=True; safe_update()
                            finally:
                                finish_native_scan()
                                on_catalog_changed()
                                refresh_settings_if_active()
                        elif event_type == 'mediastore_permission':
                            source = payload.get('source') or 'mediastore:external:video'
                            access = str(payload.get('access') or 'denied')
                            apply_storage_capabilities(payload)
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
                                store.restore_source(source)
                            else:
                                store.update_folder_status(source, 'revoked', 'A permissão para vídeos do dispositivo foi removida.')
                                store.mark_source_unavailable(source, 'media_permission_revoked')
                            refresh_settings_if_active()
                            maybe_show_storage_onboarding()
                        elif event_type == 'mediastore_error':
                            source = payload.get('source') or 'mediastore:external:video'
                            error_status = str(payload.get('status') or 'FAILED').upper()
                            message = event.get('message', 'Não foi possível acessar os vídeos do dispositivo.')
                            if error_status in {'REVOKED', 'DENIED'}:
                                store.update_folder_status(source, 'revoked', message)
                                store.mark_source_unavailable(source, 'media_permission_revoked')
                            else:
                                store.update_folder_status(source, 'unavailable', message)
                                store.mark_source_unavailable(source, 'mediastore_scan_failed')
                            finish_native_scan()
                            page.snack_bar = ft.SnackBar(ft.Text(event.get('message', 'Não foi possível acessar os vídeos do dispositivo.')))
                            page.snack_bar.open = True
                            safe_update()
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
                            page.snack_bar=ft.SnackBar(ft.Text(event.get('message', 'Não foi possível reproduzir este arquivo.'))); page.snack_bar.open=True; safe_update()
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
                                page.snack_bar=ft.SnackBar(ft.Text('A resposta da conta Google é inválida. Tente novamente.')); page.snack_bar.open=True; safe_update(); refresh_settings_if_active()
                            else:
                                store.save_account(profile); account_state[0] = 'connected'; page.snack_bar=ft.SnackBar(ft.Text('Conta Google conectada.')); page.snack_bar.open=True; safe_update(); refresh_settings_if_active()
                        elif event_type == 'volume_changed':
                            set_scan_state(
                                ScanUiState.SCANNING if any(
                                    isinstance(item, dict) and item.get('available') for item in (payload.get('added') or [])
                                ) else ScanUiState.VOLUME_UNAVAILABLE,
                                source="volume",
                                volume=(payload.get('changedVolumes') or [{}])[0].get('volumeId') if payload.get('changedVolumes') else None,
                                timestamp=event.get('createdAt') or payload.get('timestamp'),
                            )
                            volume_event = dict(payload)
                            volume_event["eventTimestamp"] = event.get('timestamp') or event.get('createdAt') or payload.get('timestamp')
                            volume_result = await asyncio.to_thread(library.ingest_native_volume_change, volume_event)
                            if volume_result.get("ignored"):
                                logger.info("[STORAGE] stale volume_changed event ignored timestamp=%s", volume_event.get("eventTimestamp"))
                                continue
                            on_catalog_changed()
                            volume_returned = False
                            for item in (payload.get('added') or []):
                                if isinstance(item, dict) and item.get('available', False):
                                    volume_returned = True
                            for change in (payload.get('changedVolumes') or []):
                                if not isinstance(change, dict):
                                    continue
                                after = change.get('after') or {}
                                before = change.get('before') or {}
                                if isinstance(after, dict) and after.get('available', False) and not before.get('available', False):
                                    volume_returned = True
                            if volume_returned:
                                # Event-driven rediscovery: a newly mounted/reconnected
                                # volume is scanned once instead of being polled.
                                asyncio.create_task(bridge.scan_all_storage())
                            logger.info(
                                "[STORAGE] action=volume_changed native_result=received "
                                "current=%s added=%s removed=%s changed=%s rediscovery=%s",
                                len(payload.get('current') or []),
                                len(payload.get('added') or []),
                                len(payload.get('removed') or []),
                                len(payload.get('changedVolumes') or []),
                                volume_returned,
                            )
                            refresh_settings_if_active()
                        elif event_type == 'saf_inventory':
                            trees = payload.get('trees') or []
                            inventory_complete = bool(payload.get('inventoryComplete'))
                            status_by_uri = {}
                            for item in trees:
                                if not isinstance(item, dict) or not item.get('treeUri'):
                                    continue
                                status_by_uri[str(item.get('treeUri'))] = item
                            available_uris = {
                                uri for uri, item in status_by_uri.items()
                                if str(item.get('status') or '').upper() in {'COMPLETED', 'EMPTY_COMPLETE'}
                            }
                            update_saf_capabilities(available_uris)
                            logger.info(
                                "[STORAGE] action=saf_inventory native_result=received "
                                "persisted=%s available=%s lifecycle=%s complete=%s",
                                len(status_by_uri),
                                len(available_uris),
                                payload.get('lifecycle', '-'),
                                inventory_complete,
                            )
                            for reference, item in status_by_uri.items():
                                status = str(item.get('status') or 'UNAVAILABLE').upper()
                                folder = next((f for f in store.folders() if f.get('path') == reference), None)
                                if folder is None and status in {'COMPLETED', 'EMPTY_COMPLETE'}:
                                    store.add_folder(
                                        reference,
                                        name=item.get('name') or reference.rsplit('/', 1)[-1],
                                        kind='saf',
                                        authorization='granted',
                                        account_id=store.account().get('id'),
                                        saf_authority=item.get('authority') or None,
                                        saf_document_id=item.get('documentId') or None,
                                        saf_volume_id=item.get('volumeId') or None,
                                        saf_identity=item.get('identity') or None,
                                    )
                                elif folder is not None:
                                    store.update_saf_identity(
                                        reference,
                                        item.get('authority') or '',
                                        item.get('documentId') or '',
                                        item.get('volumeId') or None,
                                        item.get('identity') or None,
                                    )
                                if status in {'COMPLETED', 'EMPTY_COMPLETE'}:
                                    store.update_folder_status(reference, 'granted')
                                    store.restore_source(reference)
                                elif status == 'REVOKED':
                                    store.update_folder_status(reference, 'revoked', item.get('error') or 'A autorização SAF desta pasta foi removida.')
                                    store.mark_source_unavailable(reference, 'saf_permission_revoked')
                                elif status in {'UNAVAILABLE', 'PARTIAL', 'FAILED'}:
                                    store.update_folder_status(reference, 'unavailable', item.get('error') or 'O provedor SAF está indisponível.')
                                    store.mark_source_unavailable(reference, 'saf_provider_unavailable')
                            if inventory_complete:
                                known_saf = {
                                    str(f.get('path') or '') for f in store.folders()
                                    if f.get('kind') == 'saf' and f.get('path')
                                }
                                for reference in known_saf - set(status_by_uri):
                                    store.update_folder_status(
                                        reference,
                                        'revoked',
                                        'A autorização SAF desta pasta não está mais presente no Android.',
                                    )
                                    store.mark_source_unavailable(reference, 'saf_permission_revoked')
                            refresh_settings_if_active()
                            maybe_show_storage_onboarding()
                        elif event_type == 'saf_cancelled':
                            saf_selection.finish()
                            storage_onboarding["waiting_for_result"] = False
                            set_scan_state(ScanUiState.CANCELLED, source="saf", error=None, timestamp=event.get('createdAt'))
                            page.snack_bar=ft.SnackBar(ft.Text('Seleção de pasta cancelada.')); page.snack_bar.open=True; safe_update()
                            refresh_settings_if_active()
                        elif event_type == 'saf_permission':
                            storage_onboarding["waiting_for_result"] = False
                            if payload.get('granted'):
                                apply_storage_capabilities(payload)
                            tree_uri = payload.get('treeUri')
                            if tree_uri:
                                if payload.get('granted'):
                                    if payload.get('selected'):
                                        store.add_folder(
                                            tree_uri,
                                            name=payload.get('name') or tree_uri.rsplit('/', 1)[-1],
                                            kind='saf',
                                            authorization='granted',
                                            account_id=store.account().get('id'),
                                            saf_authority=payload.get('authority') or None,
                                            saf_document_id=payload.get('documentId') or None,
                                            saf_volume_id=payload.get('volumeId') or None,
                                            saf_identity=payload.get('identity') or None,
                                        )
                                    else:
                                        store.update_folder_status(tree_uri, 'granted')
                                        store.update_saf_identity(
                                            tree_uri,
                                            payload.get('authority') or '',
                                            payload.get('documentId') or '',
                                            payload.get('volumeId') or None,
                                            payload.get('identity') or None,
                                        )
                                else:
                                    store.update_folder_status(tree_uri, 'revoked', 'A permissão desta pasta foi removida.')
                                    store.mark_source_unavailable(tree_uri, 'saf_permission_revoked')
                                refresh_settings_if_active()
                        elif event_type == 'saf_released':
                            tree_uri = payload.get('treeUri')
                            if tree_uri and tree_uri in pending_folder_removals:
                                pending_folder_removals.discard(tree_uri)
                                store.remove_folder(tree_uri)
                                on_catalog_changed()
                                refresh_settings_if_active()
                                page.snack_bar=ft.SnackBar(ft.Text('Pasta removida da biblioteca.')); page.snack_bar.open=True; safe_update()
                        elif event_type == 'google_cancelled':
                            account_state[0] = 'disconnected'
                            page.snack_bar=ft.SnackBar(ft.Text('Entrada com Google cancelada.')); page.snack_bar.open=True; safe_update(); refresh_settings_if_active()
                        elif event_type in {'saf_error','google_error'}:
                            if event_type == 'saf_error':
                                storage_onboarding["waiting_for_result"] = False
                                status = str(payload.get('status') or '').upper()
                                set_scan_state(
                                    scan_ui_state_from_native(
                                        status,
                                        errors=True,
                                        volume_available=status not in {'UNAVAILABLE', 'REVOKED'},
                                    ),
                                    source="saf",
                                    volume=payload.get('volumeId'),
                                    scan_id=payload.get('scanId'),
                                    error=event.get('message') or payload.get('error'),
                                    timestamp=event.get('createdAt'),
                                )
                                saf_selection.finish()
                                tree_uri = payload.get('treeUri')
                                if tree_uri and tree_uri in pending_folder_removals:
                                    pending_folder_removals.discard(tree_uri)
                                    page.snack_bar=ft.SnackBar(ft.Text(event.get('message', 'Não foi possível liberar a pasta.'))); page.snack_bar.open=True; safe_update()
                                    refresh_settings_if_active()
                                    continue
                                if tree_uri:
                                    status = str(payload.get('status') or '').upper()
                                    if status == 'REVOKED':
                                        store.update_folder_status(tree_uri, 'revoked', event.get('message', 'A autorização SAF foi removida.'))
                                        store.mark_source_unavailable(tree_uri, 'saf_permission_revoked')
                                    elif status in {'UNAVAILABLE', 'FAILED', 'PARTIAL'}:
                                        store.update_folder_status(tree_uri, 'unavailable', event.get('message', 'O provedor SAF está indisponível.'))
                                        store.mark_source_unavailable(tree_uri, 'saf_provider_unavailable')
                                    else:
                                        store.update_folder_status(tree_uri, 'unavailable', event.get('message', 'Não foi possível acessar a pasta.'))
                                        store.mark_source_unavailable(tree_uri, 'saf_scan_error')
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
                                page.snack_bar=ft.SnackBar(ft.Text(message)); page.snack_bar.open=True; safe_update()
                            if event_type == 'saf_error': refresh_settings_if_active()
                        elif event_type == 'android_back':
                            navigate_back()
                        if operation_key:
                            processed_native_operations.add(operation_key)
                        if event_id:
                            store.claim_native_event(event_id)
                    except Exception as exc:
                        if event_id:
                            failed_event_ids.add(str(event_id))
                        print(f"[ANDROID] Erro ao processar evento nativo: {exc}")
                # NativeMailbox retains the atomically claimed batch until this
                # point, after SQLite/UI handling has completed. A process restart
                # before acknowledgement replays the complete batch safely.
                bridge.requeue_event_ids(failed_event_ids)
                bridge.acknowledge()
                poll_interval = 0.1 if events else min(1.0, poll_interval * 1.5)
            except Exception as exc:
                print(f"[ANDROID] Erro no loop da ponte nativa: {exc}")
                poll_interval = min(1.0, poll_interval * 1.5)
            await asyncio.sleep(poll_interval)
    page.on_login=login_done
    page.run_task(poll_native_bridge)
    if recovered_scans:
        page.snack_bar = ft.SnackBar(ft.Text(
            f"{len(recovered_scans)} varredura(s) anterior(es) foram interrompidas e poderão ser refeitas."
        ))
        page.snack_bar.open = True
        safe_update()
    # MainActivity publishes the authoritative SAF grant inventory from
    # onResume. There is intentionally no Python -> reiflix://native startup
    # verification call.
    render_current()

if __name__ == "__main__":
    ft.run(main)
