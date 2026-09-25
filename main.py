import os
import time
import asyncio
import logging
import json
import flet as ft
from flet.auth import OAuthProvider
from app_config import GOOGLE_CLIENT_ID as CONFIG_GOOGLE_CLIENT_ID, GOOGLE_REDIRECT_URL as CONFIG_GOOGLE_REDIRECT_URL, GOOGLE_WEB_CLIENT_ID as CONFIG_GOOGLE_WEB_CLIENT_ID
from core.android_bridge import AndroidBridge
from core.navigation import NavigationController, SafSelectionState
from core.scan_coordinator import ScanCoordinator, ScanOrigin, ScanState, ScanTarget
from core.storage_access import StorageAccessState, StorageCapabilities, ScanUiState, scan_ui_state_from_native, storage_access_state, storage_source_states
from core.diagnostics import DiagnosticTimeline
from core.diagnostic_service import DiagnosticsService
from core.backup import BackupError, BackupService
from core.library_store import LibraryStore
from core.library_service import LibraryService
from core.settings import SettingsStore
from core.ui import apply_page_theme
from core.recovery import RecoveryService
from views.recovery_view import RecoveryView
from core.google_account import normalize_google_profile
from views.home_view import HomeView
from views.details_view import DetailView
from views.organize_view import OrganizeView
from views.settings_view import SettingsView

logger = logging.getLogger("reiflix")

GOOGLE_CLIENT_ID = os.getenv('REIFLIX_GOOGLE_CLIENT_ID', CONFIG_GOOGLE_CLIENT_ID)
GOOGLE_REDIRECT_URL = os.getenv('REIFLIX_GOOGLE_REDIRECT_URL', CONFIG_GOOGLE_REDIRECT_URL)
GOOGLE_WEB_CLIENT_ID = os.getenv('REIFLIX_GOOGLE_WEB_CLIENT_ID', CONFIG_GOOGLE_WEB_CLIENT_ID)

async def main(page: ft.Page):
    page.title='Rei-Flix Local'; page.padding=0
    apply_page_theme(page, "dark")
    data_dir=os.getenv("FLET_APP_STORAGE_DATA") or os.path.join(os.path.dirname(__file__),'.reiflix-data')
    store=LibraryStore(data_dir)
    recovery_service = RecoveryService(store)
    recovery_status = recovery_service.diagnose()
    if store.recovery_error or recovery_status.get("required"):
        logger.error("[RECOVERY] database inconsistency detected: %s", store.recovery_error or recovery_status.get("error") or recovery_status.get("quick_check"))
        async def recovery_diagnostic():
            return await asyncio.to_thread(recovery_service.diagnostic_bytes)
        async def recovery_snapshot():
            return await asyncio.to_thread(recovery_service.create_safety_snapshot)
        async def recovery_restore(raw, *, preview_only=False):
            if preview_only:
                return await asyncio.to_thread(BackupService(store).inspect_bytes, raw)
            return await asyncio.to_thread(recovery_service.restore_backup, raw)
        page.views.clear()
        page.views.append(
            ft.View(
                route="/recovery",
                controls=[RecoveryView.build(
                    page,
                    recovery_status,
                    on_diagnostic=recovery_diagnostic,
                    on_snapshot=recovery_snapshot,
                    on_restore=recovery_restore,
                )],
                padding=0,
            )
        )
        page.update()
        return
    settings=SettingsStore(store)
    apply_page_theme(page, settings.get("appearance.theme"))
    recovered_scans=store.interrupted_scans()
    library=LibraryService(store, settings=settings); bridge=AndroidBridge(data_dir, page); current=[None]
    account_state=["connected" if store.account().get("email") else "disconnected"]
    diagnostics = DiagnosticTimeline()
    backup_service = BackupService(store, settings=settings, app_version="0.2.1")
    diagnostic_service = DiagnosticsService(store, timeline=diagnostics, app_version="0.2.1")
    diagnostics.record("APP_START", result="python_ui_initialized")
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
    native_poll_task = [None]

    def _handle_page_disconnect(_event=None):
        ui_alive[0] = False
        task = native_poll_task[0]
        if task is not None:
            try:
                task.cancel()
            except Exception as exc:
                logger.debug("[FLET] mailbox poll task cancellation failed: %s", exc)

    try:
        page.on_disconnect = _handle_page_disconnect
    except Exception as exc:
        logger.warning("[FLET] on_disconnect hook unavailable: %s", exc)

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
        incoming = str(state.value if isinstance(state, ScanUiState) else state)
        terminal_states = {
            ScanUiState.COMPLETED.value,
            ScanUiState.CANCELLED.value,
            ScanUiState.FAILED.value,
            ScanUiState.PARTIAL.value,
        }
        # Ignore a late progress callback from the same native operation after
        # a terminal result has already reached Python.
        if (
            str(current.get("state") or "") in terminal_states
            and incoming in {ScanUiState.SCANNING.value, ScanUiState.CHECKING.value}
            and scan_id is not None
            and str(scan_id) == str(current.get("scanId") or "")
        ):
            logger.warning(
                "[SCAN] stale progress ignored scan_id=%s state=%s current=%s",
                scan_id, incoming, current.get("state"),
            )
            return
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

    def _scan_coordinator_state_changed(snapshot):
        state = snapshot.state
        ui_state = {
            ScanState.QUEUED: ScanUiState.SCANNING,
            ScanState.RUNNING: ScanUiState.SCANNING,
            ScanState.CANCELLING: ScanUiState.SCANNING,
            ScanState.COMPLETED: ScanUiState.COMPLETED,
            ScanState.CANCELLED: ScanUiState.CANCELLED,
            ScanState.FAILED: ScanUiState.FAILED,
            ScanState.PARTIAL: ScanUiState.PARTIAL,
            ScanState.BLOCKED: ScanUiState.IDLE,
            ScanState.IDLE: ScanUiState.IDLE,
        }.get(state, ScanUiState.IDLE)
        set_scan_state(
            ui_state,
            source=snapshot.source,
            scan_id=snapshot.request_id,
            error=snapshot.last_result if state in {ScanState.FAILED, ScanState.PARTIAL} else None,
        )
        safe_update()

    # Resolve the callback and its runtime capability state before constructing
    # ScanCoordinator. Python binds function definitions as local names only when
    # execution reaches the definition; constructing the coordinator first caused
    # startup-time UnboundLocalError before the storage UI could render.
    storage_onboarding = {"dismissed": False, "dialog_open": False, "waiting_for_result": False}
    storage_capabilities = [StorageCapabilities.unknown()]

    def _authorized_scan_targets(source=None, scope_ref=None):
        normalized = ScanCoordinator.normalize_source(source)
        caps = storage_capabilities[0]
        targets = []
        if normalized in (None, "mediastore") and caps.can_scan("mediastore"):
            targets.append(ScanTarget("mediastore"))
        if normalized in (None, "broad_storage") and caps.can_scan("broad-storage"):
            targets.append(ScanTarget("broad_storage"))
        if normalized in (None, "saf"):
            allowed_roots = set(caps.saf_roots)
            folders = {
                str(folder.get("path") or "").strip()
                for folder in store.folders()
                if folder.get("kind") == "saf" and str(folder.get("path") or "").strip()
            }
            roots = sorted(allowed_roots | folders)
            for root in roots:
                if not scope_ref or root == scope_ref:
                    targets.append(ScanTarget("saf", root))
        return targets

    scan_coordinator = ScanCoordinator(
        bridge,
        store,
        _authorized_scan_targets,
        on_state=_scan_coordinator_state_changed,
    )
    pending_folder_removals=set()
    # View-local query/filter state survives Details/Player round-trips while
    # the catalog itself is still read afresh from SQLite on each view entry.
    home_state = {}
    organize_state = {}
    settings_state = {}
    navigation = NavigationController()
    saf_selection = SafSelectionState()
    # One Python navigation stack, one persistent Flet host, and cached
    # top-level screens. Returning to a screen must not destroy its scroll,
    # search, filter or focus state.
    screen_cache = {}
    # Settings nested levels are part of NavigationController, so Android Back
    # never consults a second Settings-specific navigation authority.
    # Flet's page.views is the navigation surface consumed by the Android/system
    # Back dispatcher. The existing NavigationController remains the single
    # logical source of truth; page.views mirrors its stack without introducing
    # a second navigation model.
    # Runtime snapshots are deliberately not stored in SQLite: only Android is
    # proof of a current grant. ``dismissed`` prevents an automatic onboarding loop.
    processed_native_operations = set()
    back_state = {"last_at": 0.0, "last_action": None}
    BACK_DEBOUNCE_SECONDS = 0.30
    navigation_state_path = os.path.join(data_dir, "navigation_state.json")
    navigation_state_exit_marker = navigation_state_path + ".closed"
    restored_detail_id = [None]

    def load_navigation_state():
        try:
            if os.path.exists(navigation_state_exit_marker):
                for path in (navigation_state_path, navigation_state_exit_marker):
                    try:
                        os.unlink(path)
                    except FileNotFoundError:
                        pass
                return {}
            with open(navigation_state_path, "r", encoding="utf-8") as handle:
                state = json.load(handle)
        except (OSError, ValueError, TypeError):
            return {}
        if not isinstance(state, dict):
            logger.warning("[NAV] persisted navigation state is not an object; starting from Home")
            return {}
        if not navigation.restore(state.get("navigation")):
            logger.warning("[NAV] invalid persisted navigation snapshot; starting from Home")
            return {}
        restored = state.get("home_state")
        if isinstance(restored, dict):
            home_state.update(
                {str(key): value for key, value in restored.items() if not callable(value)}
            )
        for target, key in ((organize_state, "organize_state"), (settings_state, "settings_state")):
            restored_view = state.get(key)
            if isinstance(restored_view, dict):
                target.update({str(name): value for name, value in restored_view.items() if not callable(value)})
        detail_id = state.get("details_media_id")
        restored_detail_id[0] = str(detail_id).strip() if detail_id not in (None, "") else None
        logger.info(
            "[NAV] restored stack=%s settings_depth=%s details_id=%s",
            navigation.stack,
            len(navigation.settings_path),
            restored_detail_id[0] or "-",
        )
        return state

    navigation_persist = {"pending": False, "running": False, "closing": False}

    def _navigation_state_payload():
        return {
            "version": 2,
            "navigation": navigation.snapshot(),
            "home_state": {
                str(key): value
                for key, value in home_state.items()
                if not callable(value)
            },
            "organize_state": {
                str(key): value
                for key, value in organize_state.items()
                if not callable(value)
            },
            "settings_state": {
                str(key): value
                for key, value in settings_state.items()
                if not callable(value)
            },
            "details_media_id": (
                str(current[0].get("id"))
                if navigation.current == "details" and current[0] and current[0].get("id") is not None
                else None
            ),
        }

    def _write_navigation_state(state):
        temporary = navigation_state_path + ".tmp"
        try:
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump(state, handle, ensure_ascii=False, separators=(",", ":"))
                handle.flush()
            os.replace(temporary, navigation_state_path)
        except (OSError, TypeError, ValueError):
            try:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            except OSError:
                pass
            logger.exception("[NAV] failed to persist navigation snapshot")

    async def _flush_navigation_state():
        navigation_persist["running"] = True
        try:
            while navigation_persist["pending"] and not navigation_persist["closing"]:
                navigation_persist["pending"] = False
                await asyncio.to_thread(
                    _write_navigation_state,
                    _navigation_state_payload(),
                )
        finally:
            navigation_persist["running"] = False
            if navigation_persist["pending"] and not navigation_persist["closing"]:
                page.run_task(_flush_navigation_state)

    def persist_navigation_state():
        if navigation_persist["closing"]:
            return
        navigation_persist["pending"] = True
        if not navigation_persist["running"]:
            page.run_task(_flush_navigation_state)

    def clear_persisted_navigation_state():
        navigation_persist["closing"] = True
        navigation_persist["pending"] = False
        temporary = navigation_state_exit_marker + ".tmp"
        try:
            with open(temporary, "w", encoding="utf-8") as handle:
                handle.write("closed")
            os.replace(temporary, navigation_state_exit_marker)
            try:
                os.unlink(navigation_state_path)
            except FileNotFoundError:
                pass
        except OSError:
            try:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            except OSError:
                pass
            logger.exception("[NAV] failed to clear persisted navigation snapshot")

    def restore_details_context():
        if navigation.current != "details":
            return
        detail_id = restored_detail_id[0]
        if not detail_id:
            navigation.replace("home")
            return
        try:
            projected = library.catalog_by_ids([int(detail_id)])
            current[0] = next(
                (item for item in projected if str(item.get("id")) == detail_id),
                None,
            )
        except (TypeError, ValueError):
            current[0] = None
        except Exception:
            logger.exception("[NAV] failed to rebuild persisted Details context")
            current[0] = None
        if current[0] is None:
            logger.warning(
                "[NAV] persisted Details target unavailable id=%s; falling back to Home",
                detail_id,
            )
            navigation.replace("home")
            restored_detail_id[0] = None
    # Restore only reconstructible UI state; durable library/player state remains in SQLite/Android.
    load_navigation_state()

    def _route_for_screen(screen):
        return {
            "home": "/",
            "organize": "/organize",
            "details": "/details",
            "settings": "/settings",
        }.get(screen, "/" + str(screen))

    def _invalidate_catalog_views():
        # Details mutations are durable Store changes. Invalidate only the
        # cached projections that can display those fields when we return.
        screen_cache.pop("home", None)
        screen_cache.pop("organize", None)

    def _toggle_favorite_from_details(anime_id):
        value = store.toggle_favorite(anime_id)
        _invalidate_catalog_views()
        return value

    def _toggle_pin_from_details(anime_id):
        value = library.toggle_pinned(anime_id)
        _invalidate_catalog_views()
        return value

    def _set_tags_from_details(anime_id, tags):
        value = library.set_user_tags(anime_id, tags)
        _invalidate_catalog_views()
        return value

    def _set_note_from_details(anime_id, note):
        value = library.set_personal_note(anime_id, note)
        _invalidate_catalog_views()
        return value

    def _set_episode_identification_from_details(path, **values):
        result = store.set_episode_identification(path, **values)
        _invalidate_catalog_views()
        return result

    def _build_screen(route, *, force=False):
        if force:
            screen_cache.pop(route, None)
        control = screen_cache.get(route)
        if control is not None:
            return control
        if route == "home":
            control = HomeView.build(
                page, library, navigate_details, navigate_settings, play_episode,
                navigate_organize, view_state=home_state,
                on_request_thumbnail=request_missing_thumbnail,
            )
        elif route == "organize":
            control = OrganizeView.build(
                page, library, navigate_details,
                lambda: navigate_back("visual:organize"), navigate_settings,
                on_request_storage_access=open_broad_storage_access,
                on_scan_storage=refresh_library,
                on_request_video_access=request_video_access,
                on_add_folder=add_folder,
                view_state=organize_state,
            )
        elif route == "details":
            control = DetailView.build(
                page, current[0], play_episode,
                lambda: navigate_back("visual:details"),
                _toggle_favorite_from_details, library.playback_target,
                _set_tags_from_details, _toggle_pin_from_details, _set_note_from_details,
                _set_episode_identification_from_details, refresh_current_details,
                refresh_current_metadata, library.resolve_artwork, library.resolve_artwork_batch,
            )
        elif route == "settings":
            control = SettingsView.build(
                page, store, library,
                lambda: navigate_back("visual:settings"),
                on_catalog_changed, add_folder, remove_folder, refresh_library,
                request_video_access, open_broad_storage_access, login, logout,
                account(), account_state[0],
                folder_selection_pending=lambda: saf_selection.pending,
                on_resolve_match=resolve_match,
                storage_snapshot=storage_capabilities[0], scan_snapshot=scan_state[0],
                settings=settings,
                view_state=settings_state,
                on_check_video_access=check_video_access,
                on_create_backup=create_backup,
                on_inspect_backup=inspect_backup,
                on_restore_backup=restore_backup,
                on_export_diagnostics=export_diagnostics,
                on_integrity_check=integrity_check,
                on_reconcile_after_restore=request_restore_reconciliation,
                on_settings_changed=apply_settings_runtime,
                on_open_settings_category=navigate_settings_category,
                settings_path_provider=lambda: navigation.settings_path,
            )
        else:
            raise RuntimeError(f"Unknown navigation route: {route}")
        screen_cache[route] = control
        return control

    def render_current(force=False):
        # page.views mirrors NavigationController exactly. The native player is
        # intentionally absent: it is a separate Activity, so Back there never
        # mutates the Flet navigation stack.
        views = []
        for index, route in enumerate(navigation.stack):
            control = _build_screen(route, force=force and route == navigation.current)
            views.append(
                ft.View(
                    route=_route_for_screen(route),
                    controls=[control],
                    padding=0,
                )
            )
        page.views.clear()
        page.views.extend(views)
        safe_update()

    def handle_flet_view_pop(_event):
        navigate_back("flet_view_pop")

    def navigate_home():
        navigation.reset_to_root()
        render_current()
        persist_navigation_state()

    def navigate_organize():
        navigation.push("organize")
        render_current()
        persist_navigation_state()
    async def start_native_player(path, title, position_ms=0):
        # Sequence decisions stay in LibraryStore; Android receives only the
        # selected local URI and the already-derived autoplay preference.
        await bridge.play(
            path,
            title,
            position_ms,
            can_next=library.next_episode(path) is not None,
            can_previous=library.previous_episode(path) is not None,
            autoplay=settings.get("player.autoplay_next"),
            player_settings={
                "player.default_speed": settings.get("player.default_speed"),
                "player.aspect_ratio": settings.get("player.aspect_ratio"),
                "player.immersive": settings.get("player.immersive"),
                "player.rotation": settings.get("player.rotation"),
                "player.pip": settings.get("player.pip"),
                "player.auto_hide_seconds": settings.get("player.auto_hide_seconds"),
                "player.double_tap_seek_seconds": settings.get("player.double_tap_seek_seconds"),
                "player.long_press_speed": settings.get("player.long_press_speed"),
                "player.max_video_resolution": settings.get("player.max_video_resolution"),
                "player.max_video_frame_rate": settings.get("player.max_video_frame_rate"),
                "player.max_audio_channels": settings.get("player.max_audio_channels"),
                "gestures.volume": settings.get("gestures.volume"),
                "gestures.brightness": settings.get("gestures.brightness"),
                "gestures.double_tap": settings.get("gestures.double_tap"),
                "gestures.long_press": settings.get("gestures.long_press"),
                "audio.preferred_language": settings.get("audio.preferred_language"),
                "audio.preferred_subtitle_language": settings.get("audio.preferred_subtitle_language"),
                "audio.subtitles": settings.get("audio.subtitles"),
                "audio.subtitle_scale": settings.get("audio.subtitle_scale"),
                "audio.subtitle_bottom_padding": settings.get("audio.subtitle_bottom_padding"),
                "audio.subtitle_embedded_style": settings.get("audio.subtitle_embedded_style"),
            },
        )

    def play_episode(path, title, on_next=None, progress_seconds=0):
        if not settings.get("player.resume"):
            progress_seconds = 0

        async def launch_native_player():
            try:
                await start_native_player(path, title, max(0, int(progress_seconds * 1000)))
            except Exception as exc:
                logger.exception("[PLAYER] native handoff failed path=%s", path)
                page.snack_bar = ft.SnackBar(
                    ft.Text("Não foi possível enviar este episódio ao player Android.")
                )
                page.snack_bar.open = True
                diagnostics.record(
                    "PLAYER_HANDOFF_PYTHON_FAILED",
                    source="android_bridge",
                    error=str(exc),
                )
                safe_update()

        # NativePlayerActivity is the only player. Do not push a synthetic Flet
        # route before launching it; the current Details/Home screen remains the
        # origin to which Android back returns.
        page.run_task(launch_native_player)
    def navigate_details(anime, on_back=None):
        current[0] = anime
        # Details is keyed by the selected anime, so never reuse the previous
        # anime's cached control tree.
        screen_cache.pop("details", None)
        navigation.push("details")
        render_current()
        persist_navigation_state()
    async def refresh_current_details():
        """Reload the durable record after an in-place Details edit."""
        anime_id = current[0].get("id") if current[0] else None
        catalog = await asyncio.to_thread(library.catalog)
        current[0] = next((item for item in catalog if item["id"] == anime_id), current[0])
        render_current(force=True)
    async def refresh_current_metadata(e=None):
        """Refresh only editorial metadata; never rescans or mutates playback state."""
        anime = current[0] or {}
        lookup = (anime.get("meta") or {}).get("lookup_title")
        title = anime.get("main_title") or (anime.get("meta") or {}).get("title") or "Anime local"
        if not lookup:
            return
        if not settings.get("metadata.anilist_enabled"):
            page.snack_bar = ft.SnackBar(ft.Text("AniList está desativado nas configurações."))
            page.snack_bar.open = True
            safe_update()
            return
        try:
            await asyncio.to_thread(library.refresh_metadata, lookup, title, force=True)
            await refresh_current_details()
            page.snack_bar = ft.SnackBar(ft.Text("Metadata atualizada."))
            page.snack_bar.open = True
            safe_update()
        except Exception:
            page.snack_bar = ft.SnackBar(ft.Text("Não foi possível atualizar a metadata agora."))
            page.snack_bar.open = True
            safe_update()
    def on_catalog_changed():
        diagnostics.record("UI_REFRESHED", result="catalog_changed", source=navigation.current)
        # Home/Organize keep their cached control tree across Details/Player.
        # Refresh their current dataset in place instead of rebuilding the whole
        # screen and losing its viewport/window state.
        if navigation.current == "home":
            refresh = home_state.get("_refresh_from_catalog")
            if callable(refresh):
                refresh()
                return
        if navigation.current == "organize":
            refresh = organize_state.get("_refresh_from_catalog")
            if callable(refresh):
                refresh()
                return
        screen_cache.pop(navigation.current, None)
        render_current()

    def apply_settings_runtime(key, _value):
        setting_key = str(key)
        if setting_key == "appearance.theme":
            # Theme changes invalidate only Python/Flet control trees. Navigation,
            # query/filter state, scroll snapshots and all domain/storage/player
            # state remain owned by their existing controllers.
            apply_page_theme(page, settings.get("appearance.theme"))
            screen_cache.clear()
            render_current(force=True)
            return
        library.configure_settings(settings)
        if setting_key.startswith(("appearance.", "library.")):
            screen_cache.pop("home", None)
            screen_cache.pop("organize", None)
            current_route = navigation.current
            if current_route in {"home", "organize"}:
                render_current()

    def handle_platform_brightness_change(_event=None):
        if settings.get("appearance.theme") != "system":
            return
        apply_page_theme(page, "system")
        screen_cache.clear()
        render_current(force=True)
    async def remove_folder(reference):
        if scan_coordinator.active or saf_selection.pending:
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

    async def create_backup():
        started = time.monotonic()
        raw = await asyncio.to_thread(backup_service.create_backup_bytes)
        diagnostics.record(
            "BACKUP_CREATED",
            result="success",
            backup_duration_ms=int((time.monotonic() - started) * 1000),
        )
        return raw

    async def inspect_backup(raw):
        return await asyncio.to_thread(backup_service.inspect_bytes, raw)

    async def restore_backup(raw):
        reserved = await scan_coordinator.begin_exclusive("restore")
        if not reserved:
            raise BackupError(
                "SCAN_IN_PROGRESS",
                "Finalize a atualização da biblioteca antes de restaurar um backup.",
            )

        try:
            def run_restore():
                with library._metadata_lock:
                    library.artwork.invalidate_generation("restore_started")
                    try:
                        result = backup_service.restore_bytes(raw)
                    except Exception:
                        library.artwork.invalidate_generation("restore_failed")
                        raise
                    library.artwork.invalidate_generation("restore_completed")
                    return result

            started = time.monotonic()
            result = await asyncio.to_thread(run_restore)
            diagnostics.record(
                "RESTORE_COMPLETED",
                result="success",
                restore_duration_ms=int((time.monotonic() - started) * 1000),
                counts=(result.get("preview") or {}).get("counts") or {},
            )
        finally:
            await scan_coordinator.end_exclusive()

        on_catalog_changed()
        refresh_settings_if_active()
        return result

    async def request_restore_reconciliation():
        if scan_coordinator.active:
            return {"accepted": False, "message": "scan_already_running"}
        return await scan_coordinator.request_restore_reconciliation(
            reason="user_requested_post_restore",
        )

    async def export_diagnostics():
        raw = await asyncio.to_thread(
            diagnostic_service.diagnostic_bytes,
            storage_snapshot=storage_capabilities[0],
            scan_snapshot=scan_state[0],
            text=False,
        )
        return raw

    async def integrity_check():
        return await asyncio.to_thread(
            diagnostic_service.report,
            storage_snapshot=storage_capabilities[0],
            scan_snapshot=scan_state[0],
        )

    def account(): return store.account()
    def navigate_settings():
        if navigation.current == "settings":
            navigation.replace("settings")
        else:
            navigation.push("settings")
        screen_cache.pop("settings", None)
        render_current()
        persist_navigation_state()
        if bridge.available:
            diagnostics.record("PERMISSION_CHECK", source="android")
            page.run_task(bridge.check_storage_access)
    def navigate_settings_category(label):
        if navigation.current != "settings":
            navigation.push("settings")
        navigation.push_settings(label)
        screen_cache.pop("settings", None)
        render_current()
        persist_navigation_state()

    def close_home_search():
        if not home_state.get("search_visible"):
            return False
        home_state["search_visible"] = False
        home_state["query"] = ""
        screen_cache.pop("home", None)
        logger.info("[NAV] SEARCH_BACK consumed on Home")
        render_current()
        persist_navigation_state()
        return True

    def navigate_back(source="unknown"):
        # One user Back gesture/button owns one logical operation. This protects
        # against Android + Flutter delivering the same physical Back twice.
        now = time.monotonic()
        route_before = navigation.current
        if now - back_state["last_at"] < BACK_DEBOUNCE_SECONDS:
            logger.info(
                "[NAV] duplicate BACK suppressed source=%s route=%s delta_ms=%.0f",
                source, route_before, (now - back_state["last_at"]) * 1000,
            )
            return
        back_state.update(last_at=now, last_action=source)
        logger.info("[NAV] BACK received source=%s route=%s", source, route_before)

        try:
            dialog = page.pop_dialog()
        except Exception as exc:
            logger.exception(
                "[NAV] DIALOG_BACK lookup failed",
                extra={"screen": route_before, "requestId": "-", "event": source},
            )
            dialog = None
        if dialog is not None:
            logger.info("[NAV] DIALOG_BACK source=%s route=%s", source, route_before)
            safe_update()
            return

        # Search is a transient Home state, not a second route. Close it before
        # delegating Back to the top-level NavigationController.
        if route_before == "home" and close_home_search():
            return

        action = navigation.back()
        logger.info(
            "[NAV] NAVIGATE_BACK source=%s from=%s action=%s to=%s",
            source, route_before, action, navigation.current,
        )
        if action in {"previous", "settings_inner"}:
            # Settings content is rebuilt whenever its nested path changes, while
            # top-level screens remain cached for scroll/filter/search continuity.
            if action == "settings_inner":
                screen_cache.pop("settings", None)
            elif navigation.current == "settings":
                screen_cache.pop("settings", None)
            # Details can mutate favorite/pin/progress state in LibraryStore while
            # Organize is cached for scroll/filter continuity. Refresh only when
            # returning to Organize so its collection reflects durable state
            # without triggering a scan or permission flow.
            if navigation.current == "organize":
                screen_cache.pop("organize", None)
            render_current()
            persist_navigation_state()
        elif action == "prompt_exit":
            persist_navigation_state()
            page.snack_bar=ft.SnackBar(ft.Text("Pressione voltar novamente para sair"))
            page.snack_bar.open=True
            safe_update()
        elif action == "exit":
            logger.info("[NAV] NAVIGATE_BACK exit source=%s", source)
            clear_persisted_navigation_state()
            page.window.close()
    page.on_view_pop = handle_flet_view_pop
    try:
        page.on_platform_brightness_change = handle_platform_brightness_change
    except Exception as exc:
        logger.warning("[FLET] platform brightness callback unavailable: %s", exc)
    def refresh_settings_if_active():
        if navigation.current == "settings":
            render_current(force=True)
    async def add_folder(_=None):
        if scan_coordinator.active or not saf_selection.begin():
            return False
        try:
            await bridge.select_tree()
            return True
        except Exception as exc:
            saf_selection.finish()
            page.snack_bar=ft.SnackBar(ft.Text(str(exc))); page.snack_bar.open=True; safe_update()
            raise
    async def check_video_access(_=None):
        if not bridge.available:
            return
        logger.info("[STORAGE] action=check_storage_access python_callback=dispatch")
        await bridge.check_storage_access()

    async def request_video_access(_=None):
        if not bridge.available:
            return
        logger.info("[STORAGE] action=request_media_access python_callback=dispatch")
        await bridge.request_media_access()

    async def open_broad_storage_access(_=None):
        if not bridge.available:
            return
        logger.info("[STORAGE] action=broad_storage python_callback=dispatch")
        await bridge.open_broad_storage_settings()

    thumbnail_requests = set()

    def request_missing_thumbnail(item):
        if not bridge.available or not isinstance(item, dict):
            return
        episode = item if item.get("path") else item.get("current_episode") or {}
        path_ref = str(episode.get("path") or "").strip()
        if not path_ref or episode.get("missing"):
            return
        key = (path_ref, int(episode.get("file_size") or 0), int(episode.get("modified_at") or 0))
        if key in thumbnail_requests:
            return
        try:
            resolved = library.resolve_artwork("episode", episode.get("id"), "episode_thumbnail", allow_network=False)
        except Exception:
            resolved = None
        if resolved and resolved.get("local_path") and os.path.isfile(resolved.get("local_path")):
            return
        if len(thumbnail_requests) >= 32:
            return
        thumbnail_requests.add(key)
        async def run():
            try:
                await bridge.request_thumbnail(path_ref, key[1], key[2], str(episode.get('media_identity') or ''))
            except Exception as exc:
                thumbnail_requests.discard(key)
                logger.debug("[ARTWORK] native thumbnail request failed: %s", exc)
        page.run_task(run)

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
        caps = storage_capabilities[0]
        if bridge.available and not caps.known:
            set_scan_state(ScanUiState.CHECKING, source="permissions")
            safe_update()
            await bridge.check_storage_access()
            return "Verificando as permissões do armazenamento…", True
        transition = await scan_coordinator.request(
            ScanOrigin.USER_REFRESH,
            source=None,
            full=False,
            reason="explicit_user_refresh",
        )
        if transition.kind == "ignored":
            return "Nenhuma fonte local autorizada para atualizar a biblioteca.", False
        if transition.kind == "blocked":
            return "Nenhuma fonte local autorizada para atualizar a biblioteca.", False
        if transition.kind == "deduped":
            return "Uma atualização da biblioteca já está em andamento.", True
        if transition.kind == "queued":
            return "Atualização enfileirada; a varredura atual será concluída primeiro.", True
        return "Atualização iniciada. Verificando as fontes locais…", True
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

        poll_interval = 0.2
        while ui_alive[0]:
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
                                'player_opened': 'PLAYER_OPENED',
                                'player_error': 'PLAYER_ERROR',
                                'player_exited': 'PLAYER_EXITED',
                                'player_progress': 'PLAYER_PROGRESS',
                                'player_paused': 'PLAYER_PAUSED',
                                'player_completed': 'PLAYER_COMPLETED',
                                'player_mark_watched': 'PLAYER_MARK_WATCHED',
                                'player_autoplay_changed': 'PLAYER_AUTOPLAY_CHANGED',
                                'player_next_request': 'PLAYER_NEXT',
                                'player_previous_request': 'PLAYER_PREVIOUS',
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
                        if event_type == 'scan_request':
                            origin_raw = str(payload.get('origin') or 'MEDIASTORE_CHANGE').strip().upper()
                            source_raw = str(payload.get('source') or '').strip() or None
                            scope_ref = str(payload.get('scopeRef') or '').strip() or None
                            full = bool(payload.get('full'))
                            reason = str(payload.get('reason') or '').strip()
                            try:
                                transition = await scan_coordinator.request(
                                    origin_raw,
                                    source=source_raw,
                                    scope_ref=scope_ref,
                                    full=full,
                                    reason=reason,
                                    request_id=request_id or None,
                                )
                                diagnostics.record(
                                    "SCAN_COORDINATOR",
                                    request_id=request_id,
                                    source=source_raw,
                                    result=transition.kind,
                                )
                            except Exception as exc:
                                logger.exception("[SCAN] coordinator request failed: %s", exc)
                                set_scan_state(ScanUiState.FAILED, source=source_raw, error=str(exc))
                                safe_update()
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
                        elif event_type == 'broad_storage_scan_progress':
                            files = int(payload.get('files') or 0)
                            videos = int(payload.get('videos') or 0)
                            directories = int(payload.get('directories') or 0)
                            phase = payload.get('phase') or 'scanning'
                            if phase == 'already_running':
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
                            page.snack_bar = ft.SnackBar(ft.Text(event.get('message', 'Não foi possível acessar o armazenamento local.'))); page.snack_bar.open = True; safe_update()
                            refresh_settings_if_active()
                        elif event_type == 'mediastore_scan_progress':
                            files = int(payload.get('files') or 0)
                            videos = int(payload.get('videos') or 0)
                            phase = payload.get('phase') or 'scanning'
                            if phase == 'already_running':

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

                            page.snack_bar = ft.SnackBar(ft.Text(event.get('message', 'Não foi possível acessar os vídeos do dispositivo.')))
                            page.snack_bar.open = True
                            safe_update()
                            refresh_settings_if_active()
                        elif event_type == 'thumbnail_ready':
                            uri = str(payload.get('uri') or '').strip()
                            thumbnail_path = str(payload.get('thumbnailPath') or '').strip()
                            size = int(payload.get('size') or 0)
                            modified_at = int(payload.get('modifiedAt') or 0)
                            media_identity = str(payload.get('mediaIdentity') or '').strip()
                            thumbnail_key = (uri, size, modified_at)
                            pending_same_uri = any(key[0] == uri for key in thumbnail_requests)
                            if pending_same_uri and thumbnail_key not in thumbnail_requests:
                                # A newer request for the same URI is already pending.
                                # Do not let a late result for the old media version
                                # overwrite the current card/artwork.
                                diagnostics.record(
                                    "THUMBNAIL_STALE",
                                    request_id=request_id,
                                    result="IGNORED",
                                )
                                continue
                            metadata = {
                                "durationMs": float(payload.get('durationMs') or 0),
                                "width": int(payload.get('width') or 0),
                                "height": int(payload.get('height') or 0),
                                "rotation": int(payload.get('rotation') or 0),
                                "title": str(payload.get('title') or ''),
                                "mimeType": str(payload.get('mimeType') or ''),
                            }
                            if uri and thumbnail_path:
                                registered = await asyncio.to_thread(
                                    library.register_generated_thumbnail,
                                    uri,
                                    thumbnail_path,
                                    size=size,
                                    modified_at=modified_at,
                                    media_identity=media_identity,
                                    metadata=metadata,
                                )
                                if registered:
                                    thumbnail_requests.discard(thumbnail_key)
                                    if navigation.current in {'home', 'details', 'organize'}:
                                        on_catalog_changed()
                            diagnostics.record(
                                "THUMBNAIL_READY",
                                request_id=request_id,
                                source=payload.get('source') or "media_metadata_retriever",
                                result="REGISTERED" if thumbnail_path else "EMPTY",
                            )
                        elif event_type == 'thumbnail_error':
                            uri = str(payload.get('uri') or '').strip()
                            thumbnail_key = (
                                uri,
                                int(payload.get('size') or 0),
                                int(payload.get('modifiedAt') or 0),
                            )
                            pending_same_uri = any(key[0] == uri for key in thumbnail_requests)
                            if not pending_same_uri or thumbnail_key in thumbnail_requests:
                                thumbnail_requests.discard(thumbnail_key)
                            diagnostics.record(
                                "THUMBNAIL_ERROR",
                                request_id=request_id,
                                result=payload.get('status') or "FAILED",
                                error=event.get('message') or payload.get('error'),
                            )
                        elif event_type == 'player_opened':
                            diagnostics.record(
                                "PLAYER_OPENED",
                                request_id=event_request_id,
                                source=payload.get('source') or "native_player",
                                result=payload.get('state') or "READY",
                            )
                        elif event_type in {'player_progress', 'player_paused', 'player_completed'}:
                            path_ref = str(payload.get('uri') or '').strip()
                            if path_ref:
                                try:
                                    position_ms = max(0.0, float(payload.get('positionMs') or 0.0))
                                    duration_ms = max(0.0, float(payload.get('durationMs') or 0.0))
                                    updated = await asyncio.to_thread(
                                        store.save_progress,
                                        path_ref,
                                        position_ms / 1000.0,
                                        duration_ms / 1000.0,
                                        event_created_at=event.get('createdAt') or event.get('timestamp'),
                                    )
                                except (TypeError, ValueError):
                                    updated = False
                                # Playback progress is persisted while the native Activity is
                                # on top. Refresh only after it exits to avoid rebuilding Flet UI
                                # every 15 seconds and losing scroll position.
                                diagnostics.record(
                                    str(event_type).upper(),
                                    request_id=event_request_id,
                                    source="native_player",
                                    result="updated" if updated else "ignored",
                                )
                        elif event_type == 'player_mark_watched':
                            path_ref = str(payload.get('uri') or '').strip()
                            updated = False
                            if path_ref:
                                updated = await asyncio.to_thread(store.set_watched, path_ref, True)
                                if updated and navigation.current != 'player':
                                    render_current()
                            diagnostics.record(
                                "PLAYER_MARK_WATCHED",
                                request_id=event_request_id,
                                source="native_player",
                                result="updated" if updated else "ignored",
                            )
                        elif event_type == 'player_mark_unwatched':
                            path_ref = str(payload.get('uri') or '').strip()
                            updated = False
                            if path_ref:
                                updated = await asyncio.to_thread(store.set_watched, path_ref, False)
                                if updated and navigation.current != 'player':
                                    render_current()
                            diagnostics.record(
                                "PLAYER_MARK_UNWATCHED",
                                request_id=event_request_id,
                                source="native_player",
                                result="updated" if updated else "ignored",
                            )
                        elif event_type == 'player_autoplay_changed':
                            enabled = bool(payload.get('enabled'))
                            store.set_preference('autoplay_next', 'true' if enabled else 'false')
                            diagnostics.record(
                                "PLAYER_AUTOPLAY_CHANGED",
                                request_id=event_request_id,
                                source="native_player",
                                result="enabled" if enabled else "disabled",
                            )
                        elif event_type in {'player_next_request', 'player_previous_request'}:
                            current_path = str(payload.get('uri') or '').strip()
                            direction = 1 if event_type == 'player_next_request' else -1
                            target = library.next_episode(current_path) if direction > 0 else library.previous_episode(current_path)
                            if not target:
                                page.snack_bar = ft.SnackBar(ft.Text(
                                    "Não existe outro episódio local disponível nesta direção."
                                ))
                                page.snack_bar.open = True
                                safe_update()
                                continue
                            target_path = str(target.get('path') or '').strip()
                            target_title = (
                                target.get('episode_title')
                                or target.get('file_name')
                                or target.get('title')
                                or "Episódio local"
                            )
                            resume_enabled = store.get_preference('resume_playback', 'true') == 'true'
                            target_position_ms = (
                                max(0.0, float(target.get('progress') or 0.0)) * 1000.0
                                if resume_enabled else 0.0
                            )
                            diagnostics.record(
                                "PLAYER_NEXT" if direction > 0 else "PLAYER_PREVIOUS",
                                request_id=event_request_id,
                                source="native_player",
                                result=target_path,
                            )
                            try:
                                await start_native_player(
                                    target_path,
                                    target_title,
                                    int(target_position_ms),
                                )
                            except Exception:
                                logger.exception("[PLAYER] adjacent episode launch failed")
                                page.snack_bar = ft.SnackBar(ft.Text(
                                    "Não foi possível abrir o próximo episódio local."
                                    if direction > 0
                                    else "Não foi possível abrir o episódio anterior local."
                                ))
                                page.snack_bar.open = True
                                safe_update()
                        elif event_type == 'player_error':
                            message = event.get('message', 'Não foi possível reproduzir este arquivo localmente.')
                            diagnostics.record(
                                "PLAYER_ERROR",
                                request_id=event_request_id,
                                source="native_player",
                                result=payload.get('reason') or message,
                                error=message,
                            )
                            logger.error(
                                "[PLAYER] native_error request_id=%s uri=%s payload=%s",
                                event_request_id or "-",
                                payload.get('uri') or "",
                                payload,
                            )
                            page.snack_bar = ft.SnackBar(ft.Text(message))
                            page.snack_bar.open = True
                            safe_update()
                        elif event_type == 'player_exited':
                            exit_uri = str(payload.get('uri') or '').strip()
                            exit_updated = False
                            if exit_uri and payload.get('positionMs') is not None:
                                try:
                                    position_seconds = max(0.0, float(payload.get('positionMs') or 0.0)) / 1000.0
                                    duration_seconds = max(0.0, float(payload.get('durationMs') or 0.0)) / 1000.0
                                    exit_updated = await asyncio.to_thread(
                                        store.save_progress,
                                        exit_uri,
                                        position_seconds,
                                        duration_seconds,
                                        event_created_at=event.get('createdAt') or event.get('timestamp'),
                                    )
                                except (TypeError, ValueError):
                                    exit_updated = False
                            diagnostics.record(
                                "PLAYER_EXITED",
                                request_id=event_request_id,
                                source="native_player",
                                result=(payload.get('reason') or "exit") + (":progress_saved" if exit_updated else ":progress_not_updated"),
                            )
                            # The native player sits over the current Flet screen;
                            # there is no synthetic player route to pop.
                            on_catalog_changed()
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
                                transition = await scan_coordinator.request(
                                    ScanOrigin.VOLUME_MOUNT,
                                    source="broad_storage",
                                    full=False,
                                    reason="volume_returned",
                                )
                                diagnostics.record("SCAN_COORDINATOR", source="broad_storage", result=transition.kind)
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
                        if event_type in {'saf_scan', 'broad_storage_scan', 'mediastore_scan',
                            'saf_error', 'broad_storage_error', 'mediastore_error'}:
                            transition = await scan_coordinator.handle_native_event(
                                event_type,
                                request_id,
                                payload,
                            )
                            if transition.refresh_required and transition.logical_finished:
                                on_catalog_changed()
                                refresh_settings_if_active()
                                safe_update()

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
                poll_interval = 0.2 if events else min(1.0, poll_interval * 1.5)
            except Exception as exc:
                print(f"[ANDROID] Erro no loop da ponte nativa: {exc}")
                poll_interval = min(1.0, poll_interval * 1.5)
            await asyncio.sleep(poll_interval)
    page.on_login=login_done
    native_poll_task[0] = page.run_task(poll_native_bridge)
    if recovered_scans:
        page.snack_bar = ft.SnackBar(ft.Text(
            f"{len(recovered_scans)} varredura(s) anterior(es) foram interrompidas e poderão ser refeitas."
        ))
        page.snack_bar.open = True
        safe_update()
    # Rebuild only the durable Details target when lifecycle restoration says
    # the last Flet screen was Details. The player remains a separate Android
    # Activity and is never serialized into Python navigation state.
    restore_details_context()

    # MainActivity publishes the authoritative SAF grant inventory from
    # onResume. There is intentionally no Python -> reiflix://native startup
    # verification call.
    render_current()
    persist_navigation_state()

if __name__ == "__main__":
    ft.run(main)
