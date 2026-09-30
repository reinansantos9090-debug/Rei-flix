import os
import time
import asyncio
import logging
import json
import datetime
import uuid
import flet as ft
from flet.auth import OAuthProvider
from app_config import GOOGLE_CLIENT_ID as CONFIG_GOOGLE_CLIENT_ID, GOOGLE_REDIRECT_URL as CONFIG_GOOGLE_REDIRECT_URL, GOOGLE_WEB_CLIENT_ID as CONFIG_GOOGLE_WEB_CLIENT_ID
from core.android_bridge import AndroidBridge
from core.navigation import NavigationController, SafSelectionState
from core.scan_coordinator import ScanCoordinator, ScanOrigin, ScanState, ScanTarget
from core.storage_access import StorageAccessState, StorageCapabilities, ScanUiState, scan_ui_state_from_native, storage_access_state, storage_source_states
from core.diagnostics import DiagnosticTimeline
from core.performance import get_performance_monitor
from core.settings_focus import SettingsTaskRegistry
from core.build_identity import as_dict as build_identity
from core.diagnostic_service import DiagnosticsService
from core.backup import BackupError, BackupService
from core.library_store import LibraryStore
from core.library_service import LibraryService
from core.library_discovery import format_duration
from core.settings import SettingsStore
from core.ui import apply_page_theme
from core.recovery import RecoveryService
from views.recovery_view import RecoveryView
from core.google_account import normalize_google_profile
from views.home_view import HomeView
from views.details_view import DetailView
from views.organize_view import OrganizeView
from views.settings_view import SettingsView
from views.collector_view import CollectorView

logger = logging.getLogger("reiflix")

GOOGLE_CLIENT_ID = os.getenv('REIFLIX_GOOGLE_CLIENT_ID', CONFIG_GOOGLE_CLIENT_ID)
GOOGLE_REDIRECT_URL = os.getenv('REIFLIX_GOOGLE_REDIRECT_URL', CONFIG_GOOGLE_REDIRECT_URL)
GOOGLE_WEB_CLIENT_ID = os.getenv('REIFLIX_GOOGLE_WEB_CLIENT_ID', CONFIG_GOOGLE_WEB_CLIENT_ID)

async def main(page: ft.Page):
    performance = get_performance_monitor()
    startup_started = performance.now()
    performance.counter("startup.python_main")
    page.title='ReiAnix Local'; page.padding=0
    apply_page_theme(page, "dark")
    data_dir=os.getenv("FLET_APP_STORAGE_DATA") or os.path.join(os.path.dirname(__file__),'.reiflix-data')
    store_started = performance.now()
    store=LibraryStore(data_dir)
    performance.event("startup.library_store", duration_ms=(performance.now()-store_started)*1000.0,
                      metadata={"schema_version": getattr(store, "SCHEMA_VERSION", None)})
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
    settings_started = performance.now()
    settings=SettingsStore(store)
    performance.event("startup.settings_store", duration_ms=(performance.now()-settings_started)*1000.0)
    apply_page_theme(page, settings.get("appearance.theme"))
    recovered_scans=store.interrupted_scans()
    library=LibraryService(store, settings=settings)
    bridge_started = performance.now()
    bridge=AndroidBridge(data_dir, page)
    performance.event("startup.android_bridge", duration_ms=(performance.now()-bridge_started)*1000.0)
    current=[None]
    account_state=["connected" if store.account().get("email") else "disconnected"]
    diagnostics = DiagnosticTimeline()
    backup_service = BackupService(store, settings=settings, app_version="0.2.1")
    diagnostic_service = DiagnosticsService(store, timeline=diagnostics, app_version="0.2.1")
    diagnostics.record("APP_START", result="python_ui_initialized")
    logger.info("[BUILD] identity=%s", build_identity())
    diagnostics.record("BUILD_IDENTITY", result=json.dumps(build_identity(), sort_keys=True))
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
    player_transition_task = {"task": None}
    settings_tasks = SettingsTaskRegistry()

    def _handle_page_disconnect(_event=None):
        ui_alive[0] = False
        task = native_poll_task[0]
        if task is not None:
            try:
                task.cancel()
            except Exception as exc:
                logger.debug("[FLET] mailbox poll task cancellation failed: %s", exc)
        transition_task = player_transition_task.get("task")
        if transition_task is not None and not transition_task.done():
            try:
                transition_task.cancel()
            except Exception as exc:
                logger.debug("[FLET] player transition task cancellation failed: %s", exc)
        player_transition_task["task"] = None
        settings_tasks.invalidate()

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
    device_interaction_profile = {}
    navigation = NavigationController()
    performance.set_screen_provider(lambda: navigation.current)
    performance.install_page_hooks(page)
    details_instance_generation = [0]
    collector_instance_generation = [0]
    saf_selection = SafSelectionState()
    # One Python navigation stack, one persistent Flet host, and cached
    # top-level screens. Returning to a screen must not destroy its scroll,
    # search, filter or focus state.
    screen_cache = {}
    # Cache the Flet navigation shells separately from the content controls.
    # Replacing one screen's content therefore does not recreate its View/SafeArea
    # wrapper or unnecessarily churn page.views.
    view_shell_cache = {}
    render_state = {
        "dirty": True,
        "signature": None,
    }
    # Settings background tasks are generation-bound to the current Settings
    # control tree. Navigation/render replacement invalidates the previous tree.
    # Settings nested levels are part of NavigationController, so Android Back
    # never consults a second Settings-specific navigation authority.
    # Flet's page.views is the navigation surface consumed by the Android/system
    # Back dispatcher. The existing NavigationController remains the single
    # logical source of truth; page.views mirrors its stack without introducing
    # a second navigation model.
    # Runtime snapshots are deliberately not stored in SQLite: only Android is
    # proof of a current grant. ``dismissed`` prevents an automatic onboarding loop.
    processed_native_operations = set()
    native_operation_states = {}
    back_state = {
        "last_at": 0.0,
        "last_action": None,
        "flet_pop_count": 0,
        "navigation_count": 0,
    }
    BACK_DEBOUNCE_SECONDS = 0.30
    navigation_state_path = os.path.join(data_dir, "navigation_state.json")

    def load_navigation_state():
        """
        Restore durable UI preferences only.

        Runtime navigation is intentionally process-local. A fresh Python process
        always starts from NavigationController's Home root; persisted route/stack
        data from older versions is ignored rather than replayed.
        """
        try:
            with open(navigation_state_path, "r", encoding="utf-8") as handle:
                state = json.load(handle)
        except (OSError, ValueError, TypeError):
            return {}
        if not isinstance(state, dict):
            logger.warning("[NAV] persisted UI state is not an object; starting from Home")
            return {}

        restored = state.get("home_state")
        if isinstance(restored, dict):
            home_state.update(
                {str(key): value for key, value in restored.items() if not callable(value)}
            )
        for target, key in ((organize_state, "organize_state"), (settings_state, "settings_state")):
            restored_view = state.get(key)
            if isinstance(restored_view, dict):
                target.update(
                    {str(name): value for name, value in restored_view.items() if not callable(value)}
                )

        logger.info(
            "[NAV] startup route reset to Home; durable ui_state restored "
            "home_keys=%s organize_keys=%s settings_keys=%s",
            len(home_state),
            len(organize_state),
            len(settings_state),
        )
        return state

    if navigation.current != "home":
        navigation.reset_to_root()
        logger.warning("[NAV] startup invariant repaired: runtime route was not Home")

    navigation_persist = {"pending": False, "running": False, "closing": False}

    # Restore durable Home/Organize/Settings UI state only. Runtime route/stack
    # remains process-local and therefore starts at Home on every fresh process.
    load_navigation_state()

    def _navigation_state_payload():
        return {
            "version": 3,
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
        }

    def _write_navigation_state(state):
        temporary = navigation_state_path + ".tmp"
        try:
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump(state, handle, ensure_ascii=False, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
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
            while navigation_persist["pending"] and not navigation_persist["closing"] and ui_alive[0]:
                navigation_persist["pending"] = False
                await asyncio.to_thread(
                    _write_navigation_state,
                    _navigation_state_payload(),
                )
        finally:
            navigation_persist["running"] = False
            if navigation_persist["pending"] and not navigation_persist["closing"] and ui_alive[0]:
                page.run_task(_flush_navigation_state)

    def persist_navigation_state():
        if navigation_persist["closing"] or not ui_alive[0]:
            return
        navigation_persist["pending"] = True
        if not navigation_persist["running"]:
            page.run_task(_flush_navigation_state)

    def clear_persisted_navigation_state():
        # Kept as a lifecycle hook for the existing navigation contract. Runtime
        # navigation is no longer persisted, so closing the app must not erase
        # durable UI preferences such as filters and scroll positions.
        navigation_persist["closing"] = True
        navigation_persist["pending"] = False
        logger.info("[NAV] process exit: runtime route is not persisted")

    def _route_for_screen(screen):
        return {
            "home": "/",
            "organize": "/organize",
            "details": "/details",
            "collector": "/collector",
            "settings": "/settings",
        }.get(screen, "/" + str(screen))

    def _ui_render_signature():
        current_id = None
        if isinstance(current[0], dict):
            current_id = current[0].get("id")
        return (
            tuple(navigation.stack),
            tuple(navigation.settings_path),
            current_id,
        )

    def _mark_ui_dirty():
        render_state["dirty"] = True

    def _drop_screen_cache(route):
        screen_cache.pop(route, None)
        _mark_ui_dirty()

    def _clear_screen_cache():
        screen_cache.clear()
        _mark_ui_dirty()

    def _view_shell(route, view_route, control, *, key):
        cached = view_shell_cache.get(key)
        if cached is None:
            safe_area = ft.SafeArea(
                expand=True,
                content=control,
            )
            view = ft.View(
                route=view_route,
                bgcolor=page.bgcolor,
                controls=[safe_area],
                padding=0,
            )
            view_shell_cache[key] = (view, safe_area)
            return view

        view, safe_area = cached
        safe_area.content = control
        view.route = view_route
        view.bgcolor = page.bgcolor
        return view

    def _invalidate_cached_view(state, route):
        """Retire callbacks before dropping a cached Flet control tree."""
        invalidate_tasks = state.pop('_invalidate_view_tasks', None)
        if callable(invalidate_tasks):
            invalidate_tasks()
        state.pop('_update_thumbnail', None)
        screen_cache.pop(route, None)
        _mark_ui_dirty()

    def _invalidate_catalog_views():
        # Details mutations are durable Store changes. Invalidate only the
        # cached projections that can display those fields when we return.
        _invalidate_cached_view(home_state, "home")
        _invalidate_cached_view(organize_state, "organize")

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

    def _build_screen(route, *, force=False, settings_path_override=None):
        build_started = performance.now()
        cache_key = None if route == "collector" else (route if settings_path_override is None else None)
        if force and cache_key is not None:
            screen_cache.pop(cache_key, None)
        control = screen_cache.get(cache_key) if cache_key is not None else None
        if control is not None:
            performance.record_ui_build(route, (performance.now()-build_started)*1000.0,
                                        controls=performance.control_count(control), cached=True)
            return control
        if route == "home":
            control = HomeView.build(
                page, library, navigate_details, navigate_settings, play_episode,
                navigate_organize, view_state=home_state,
                on_request_thumbnail=request_missing_thumbnail,
                on_open_collector=navigate_collector,
                is_active=lambda: ui_alive[0] and navigation.current == "home",
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
                is_active=lambda: ui_alive[0] and navigation.current == "organize",
            )
        elif route == "details":
            details_instance_generation[0] += 1
            detail_instance_token = details_instance_generation[0]
            detail_anime_id = (current[0] or {}).get("id")
            control = DetailView.build(
                page, current[0], play_episode,
                lambda: navigate_back("visual:details"),
                _toggle_favorite_from_details, library.playback_target,
                _set_tags_from_details, _toggle_pin_from_details, _set_note_from_details,
                _set_episode_identification_from_details, refresh_current_details,
                refresh_current_metadata, library.resolve_artwork, library.resolve_artwork_batch,
                on_open_marathon=open_marathon,
                resolve_artwork_palette=library.resolve_artwork_palette,
                is_active=lambda token=detail_instance_token, anime_id=detail_anime_id: (
                    ui_alive[0]
                    and navigation.current == "details"
                    and details_instance_generation[0] == token
                    and (current[0] or {}).get("id") == anime_id
                ),
            )
        elif route == "collector":
            collector_instance_generation[0] += 1
            collector_instance_token = collector_instance_generation[0]
            control = CollectorView.build(
                page,
                library,
                lambda: navigate_back("visual:collector"),
                is_active=lambda token=collector_instance_token: (
                    ui_alive[0]
                    and navigation.current == "collector"
                    and collector_instance_generation[0] == token
                ),
            )
        elif route == "settings":
            fixed_settings_path = (
                tuple(settings_path_override)
                if settings_path_override is not None
                else None
            )
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
                settings_path_provider=(
                    (lambda path=fixed_settings_path: path)
                    if fixed_settings_path is not None
                    else (lambda: navigation.settings_path)
                ),
                settings_is_active=(
                    lambda path=fixed_settings_path: (
                        navigation.current == "settings"
                        and tuple(navigation.settings_path) == tuple(path or ())
                    )
                ),
                settings_generation_provider=lambda: settings_tasks.generation,
                register_settings_task=settings_tasks.register,
            )
        else:
            raise RuntimeError(f"Unknown navigation route: {route}")
        if cache_key is not None:
            screen_cache[cache_key] = control
        performance.record_ui_build(route, (performance.now()-build_started)*1000.0,
                                    controls=performance.control_count(control), cached=False)
        return control

    def _settings_view_paths():
        # page.views is only a projection of the existing NavigationController:
        # one top-level Settings view plus one View per existing settings_path level.
        paths = [()]
        current_path = tuple(navigation.settings_path)
        paths.extend(current_path[:index] for index in range(1, len(current_path) + 1))
        return paths

    def render_current(force=False, *, reason="unknown"):
        render_started = performance.now()
        reason_key = "".join(
            char if char.isalnum() else "_" for char in str(reason or "unknown")
        ).strip("_").lower() or "unknown"
        performance.counter("ui.render_current.requested")
        performance.counter(f"ui.render_current.request.{reason_key}")
        signature = _ui_render_signature()

        # Repeated render requests are common around navigation/back and external
        # callbacks. When neither navigation nor the mounted screen changed, do
        # not rebuild, invalidate Settings focus, churn page.views or call update.
        if (
            not force
            and not render_state["dirty"]
            and render_state["signature"] == signature
        ):
            performance.counter("ui.render_current.skipped_unchanged")
            performance.counter(f"ui.render_current.skip.{reason_key}")
            performance.event(
                "ui.render_current",
                status="skipped_unchanged",
                screen=navigation.current,
                metadata={
                    "reason": reason,
                    "settings_depth": len(navigation.settings_path),
                },
            )
            return

        if navigation.current == "settings":
            # Settings is intentionally not cached in screen_cache: every executed
            # Settings render creates a new control tree. Invalidate its tasks before
            # that replacement so callbacks capture the new generation.
            settings_tasks.invalidate()

        views = []
        for route in navigation.stack:
            if route != "settings":
                control = _build_screen(
                    route,
                    force=force and route == navigation.current,
                )
                views.append(
                    _view_shell(
                        route,
                        _route_for_screen(route),
                        control,
                        key=(route, None),
                    )
                )
                continue

            # Each nested Settings level gets its own Flet View, but all of them
            # are derived from the one NavigationController.settings_path.
            # This makes Android/Flet Back consume exactly one Settings level.
            for path in _settings_view_paths():
                control = _build_screen(
                    "settings",
                    force=force and path == navigation.settings_path,
                    settings_path_override=path,
                )
                route_suffix = "/".join(path)
                view_route = "/settings" + (f"/{route_suffix}" if route_suffix else "")
                views.append(
                    _view_shell(
                        "settings",
                        view_route,
                        control,
                        key=("settings", tuple(path)),
                    )
                )

        previous_view_ids = tuple(id(view) for view in page.views)
        next_view_ids = tuple(id(view) for view in views)
        page_views_replaced = previous_view_ids != next_view_ids
        if page_views_replaced:
            page.views.clear()
            page.views.extend(views)
            performance.counter("ui.render_current.page_views_replaced")
        else:
            performance.counter("ui.render_current.page_views_reused")

        render_state["signature"] = signature
        render_state["dirty"] = False
        performance.counter("ui.render_current")
        performance.counter("ui.render_current.executed")
        performance.counter(f"ui.render_current.execute.{reason_key}")
        performance.event(
            "ui.render_current",
            duration_ms=(performance.now()-render_started)*1000.0,
            screen=navigation.current,
            metadata={
                "force": force,
                "reason": reason,
                "settings_depth": len(navigation.settings_path),
                "view_count": len(views),
                "controls": sum(
                    performance.control_count(view) or 0 for view in views
                ),
                "page_views_replaced": page_views_replaced,
            },
        )
        safe_update()
        logger.info(
            "NAV_RENDER_CURRENT duration_ms=%s current=%s settings_depth=%s "
            "view_count=%s force=%s reason=%s page_views_replaced=%s",
            int((time.perf_counter() - render_started) * 1000),
            navigation.current,
            len(navigation.settings_path),
            len(views),
            force,
            reason,
            page_views_replaced,
        )

    def handle_flet_view_pop(_event):
        back_state["flet_pop_count"] += 1
        pop_id = back_state["flet_pop_count"]
        logger.info(
            "BACK_FLET_VIEW_POP_RECEIVED id=%s nav=%s settings_depth=%s views=%s",
            pop_id,
            navigation.current,
            len(navigation.settings_path),
            len(page.views),
        )
        navigate_back(f"flet_view_pop:{pop_id}")

    def navigate_home():
        previous = navigation.current
        with performance.interaction("return_home", source=previous, target="home"):
            navigation.reset_to_root()
            render_current(reason="return_home")
            persist_navigation_state()

    def navigate_organize():
        previous = navigation.current
        with performance.interaction("open_organize", source=previous, target="organize"):
            navigation.push("organize")
            render_current(reason="open_organize")
            persist_navigation_state()
    def navigate_collector():
        previous = navigation.current
        with performance.interaction("open_collector", source=previous, target="collector"):
            navigation.push("collector")
            render_current(reason="open_collector")
            persist_navigation_state()
    player_transition_inflight = {"value": False}
    player_launch_inflight = {"value": False}
    player_transition_generation = {"value": 0}
    player_active_request_id = {"value": None}
    player_active_session_id = {"value": None}
    player_active_episode_id = {"value": None}
    player_active_anime_id = {"value": None}
    player_active_uri = {"value": None}
    player_active_player_generation = {"value": 0}
    player_session_active = {"value": False}
    player_command_sequence = {"value": 0}
    player_command_seen = set()
    player_last_command = {"sequence": 0, "request_id": None, "direction": None, "created_at_ms": 0}
    pending_next_transition = {"value": None}
    pending_previous_transition = {"value": None}

    def cancel_player_transition(reason="unknown"):
        player_transition_generation["value"] += 1
        task = player_transition_task["task"]
        current_task = asyncio.current_task()
        if task is not None and task is not current_task and not task.done():
            task.cancel()
        player_transition_task["task"] = None
        player_transition_inflight["value"] = False
        next_context = pending_next_transition["value"]
        if isinstance(next_context, dict):
            performance.event(
                "NEXT_TRANSITION_INVALIDATED",
                screen=navigation.current,
                metadata={
                    "request_id": next_context.get("origin_request_id"),
                    "target_request_id": next_context.get("target_request_id"),
                    "age_ms": max(0, int(time.time() * 1000) - int(next_context.get("created_at_ms") or 0)),
                    "origin_generation": next_context.get("native_transition_generation"),
                    "current_generation": player_transition_generation["value"],
                    "player_session_id": next_context.get("player_session_id"),
                    "origin_monotonic_ns": next_context.get("command_monotonic_ns"),
                    "reason": reason,
                },
            )
            performance.event(
                "NEXT_REQUEST_CANCELLED",
                screen=navigation.current,
                metadata={
                    "request_id": next_context.get("origin_request_id"),
                    "reason": reason,
                    "player_session_id": next_context.get("player_session_id"),
                    "origin_monotonic_ns": next_context.get("command_monotonic_ns"),
                },
            )
            diagnostics.record(
                "NEXT_TRANSITION_CANCELLED",
                request_id=next_context.get("origin_request_id"),
                source="native_player",
                result=reason,
            )
            pending_next_transition["value"] = None

        previous_context = pending_previous_transition["value"]
        if isinstance(previous_context, dict):
            performance.event(
                "PREVIOUS_TRANSITION_INVALIDATED",
                screen=navigation.current,
                metadata={
                    "request_id": previous_context.get("origin_request_id"),
                    "target_request_id": previous_context.get("target_request_id"),
                    "age_ms": max(0, int(time.time() * 1000) - int(previous_context.get("created_at_ms") or 0)),
                    "origin_generation": previous_context.get("native_transition_generation"),
                    "current_generation": player_transition_generation["value"],
                    "player_session_id": previous_context.get("player_session_id"),
                    "origin_monotonic_ns": previous_context.get("command_monotonic_ns"),
                    "reason": reason,
                },
            )
            performance.event(
                "PREVIOUS_REQUEST_CANCELLED",
                screen=navigation.current,
                metadata={
                    "request_id": previous_context.get("origin_request_id"),
                    "reason": reason,
                    "player_session_id": previous_context.get("player_session_id"),
                    "origin_monotonic_ns": previous_context.get("command_monotonic_ns"),
                },
            )
            diagnostics.record(
                "PREVIOUS_TRANSITION_CANCELLED",
                request_id=previous_context.get("origin_request_id"),
                source="native_player",
                result=reason,
            )
            pending_previous_transition["value"] = None
        performance.event(
            "PLAYER_TRANSITION_INVALIDATED",
            screen=navigation.current,
            metadata={"request_id": player_active_request_id["value"],
                      "generation": player_transition_generation["value"],
                      "reason": reason},
        )
        diagnostics.record(
            "PLAYER_TRANSITION_CANCELLED",
            request_id=player_active_request_id["value"],
            source="native_player",
            result=reason,
        )
        logger.info(
            "[PLAYER] transition cancelled generation=%s reason=%s",
            player_transition_generation["value"],
            reason,
        )

    def invalidate_player_session(reason="unknown", expected_session_id=None, expected_request_id=None):
        current_session_id = player_active_session_id["value"]
        current_request_id = player_active_request_id["value"]
        if expected_session_id and current_session_id not in (None, expected_session_id):
            performance.event(
                "PLAYER_CALLBACK_STALE",
                screen=navigation.current,
                status="ignored",
                metadata={"request_id": expected_request_id or current_request_id, "player_session_id": expected_session_id, "current_player_session_id": current_session_id, "reason": "session_mismatch_on_invalidation"},
            )
            return False
        if expected_request_id and current_request_id not in (None, expected_request_id):
            performance.event(
                "PLAYER_CALLBACK_STALE",
                screen=navigation.current,
                status="ignored",
                metadata={"request_id": expected_request_id, "current_request_id": current_request_id, "reason": "request_mismatch_on_invalidation"},
            )
            return False
        if current_session_id:
            performance.event(
                "PLAYER_SESSION_INVALIDATED",
                screen=navigation.current,
                metadata={"request_id": current_request_id, "player_session_id": current_session_id, "player_generation": player_active_player_generation["value"], "reason": reason},
            )
        cancel_player_transition(reason)
        player_session_active["value"] = False
        player_active_session_id["value"] = None
        player_active_request_id["value"] = None
        player_active_episode_id["value"] = None
        player_active_anime_id["value"] = None
        player_active_uri["value"] = None
        player_active_player_generation["value"] = 0
        return True

    def player_callback_is_current(event_request_id, payload, *, require_active=True, episode_id=None):
        session_id = str(payload.get("playerSessionId") or payload.get("player_session_id") or "").strip()
        generation = int(payload.get("generation") or payload.get("playerGeneration") or 0)
        transition_gen = int(payload.get("transitionGeneration") or 0)
        if require_active and not player_session_active["value"]:
            return False, "stale_session"
        if session_id and player_active_session_id["value"] not in (None, session_id):
            return False, "stale_session"
        if event_request_id and player_active_request_id["value"] not in (None, event_request_id):
            return False, "stale_request"
        if generation > 0 and player_active_player_generation["value"] > 0 and generation != player_active_player_generation["value"]:
            return False, "stale_player_generation"
        if transition_gen > 0 and player_transition_generation["value"] > 0 and transition_gen < player_transition_generation["value"]:
            return False, "stale_transition_generation"
        if episode_id and player_active_episode_id["value"] not in (None, episode_id):
            return False, "stale_episode"
        return True, ""

    def player_transition_is_current(generation, request_id, player_session_id=None):
        session_matches = (
            player_session_id is None
            or (
                bool(player_active_session_id["value"])
                and str(player_active_session_id["value"]) == str(player_session_id)
            )
        )
        return (
            generation == player_transition_generation["value"]
            and player_active_request_id["value"] in (None, request_id)
            and player_session_active["value"]
            and session_matches
            and ui_alive[0]
        )

    async def start_native_player(
        path,
        title,
        position_ms=0,
        *,
        episode_id=None,
        anime_id=None,
        navigation_snapshot=None,
        origin_request_id=None,
        origin_created_at_ms=0,
        origin_transition_generation=0,
        origin_player_session_id=None,
        origin_monotonic_ns=0,
        transition_direction=None,
        transition_guard=None,
    ):
        direction_label = str(transition_direction or "").strip().upper()
        stale_event = {"NEXT": "NEXT_REQUEST_STALE", "PREVIOUS": "PREVIOUS_REQUEST_STALE"}.get(direction_label, "NEXT_REQUEST_STALE")
        stale_rejected_event = {"NEXT": "PLAYER_NEXT_STALE_REJECTED", "PREVIOUS": "PLAYER_PREVIOUS_STALE_REJECTED"}.get(direction_label, "PLAYER_NEXT_STALE_REJECTED")
        invalidated_event = {"NEXT": "NEXT_TRANSITION_INVALIDATED", "PREVIOUS": "PREVIOUS_TRANSITION_INVALIDATED"}.get(direction_label, "PLAYER_TRANSITION_INVALIDATED")

        def transition_is_valid():
            return transition_guard is None or bool(transition_guard())

        if not transition_is_valid():
            if origin_request_id:
                performance.event(
                    stale_event,
                    screen=navigation.current,
                    status="rejected",
                    metadata={
                        "request_id": origin_request_id,
                        "reason": "stale_before_native_handoff",
                        "player_session_id": origin_player_session_id,
                        "age_ms": max(0, int(time.time() * 1000) - int(origin_created_at_ms or 0)),
                    },
                )
                performance.event(
                    stale_rejected_event,
                    screen=navigation.current,
                    metadata={
                        "request_id": origin_request_id,
                        "age_ms": max(0, int(time.time() * 1000) - int(origin_created_at_ms or 0)),
                        "origin_generation": origin_transition_generation,
                        "current_generation": player_transition_generation["value"],
                        "reason": "stale_before_native_handoff",
                    },
                )
            raise asyncio.CancelledError()

        performance.event(
            "NATIVE_PLAY_REQUEST_CREATED",
            screen=navigation.current,
            metadata={
                "path": path,
                "position_ms": position_ms,
                "episode_id": episode_id,
                "anime_id": anime_id,
                "origin_request_id": origin_request_id,
                "origin_created_at_ms": origin_created_at_ms,
                "origin_transition_generation": origin_transition_generation,
                "origin_monotonic_ns": origin_monotonic_ns,
                "transition_direction": direction_label,
            },
        )

        if navigation_snapshot is None:
            play_started_at = time.perf_counter()
            navigation_snapshot = await asyncio.to_thread(library.player_navigation, path)
            neighbor_resolution_ms = int((time.perf_counter() - play_started_at) * 1000)
            performance.event(
                "player.neighbor_resolution",
                duration_ms=neighbor_resolution_ms,
                screen=navigation.current,
                metadata={
                    "path": path,
                    "can_next": bool(navigation_snapshot.get("can_next")),
                    "can_previous": bool(navigation_snapshot.get("can_previous")),
                    "source": "player_navigation",
                },
            )
            logger.info(
                "[PLAYER] PLAY_PREPARED path=%s neighbor_resolution_ms=%s source=player_navigation",
                path,
                neighbor_resolution_ms,
            )
        else:
            logger.info(
                "[PLAYER] PLAY_PREPARED path=%s source=navigation_snapshot can_next=%s can_previous=%s",
                path,
                bool(navigation_snapshot.get("can_next")),
                bool(navigation_snapshot.get("can_previous")),
            )

        performance.event(
            "PLAYER_NAVIGATION_REQUESTED",
            screen=navigation.current,
            metadata={"request_id": origin_request_id or player_active_request_id["value"],
                      "episode_id": episode_id, "anime_id": anime_id},
        )
        if not transition_is_valid():
            if origin_request_id:
                performance.event(
                    "NEXT_REQUEST_STALE",
                    screen=navigation.current,
                    status="rejected",
                    metadata={
                        "request_id": origin_request_id,
                        "reason": "stale_before_bridge_send",
                        "player_session_id": origin_player_session_id,
                    },
                )
                performance.event(
                    "PLAYER_NEXT_STALE_REJECTED",
                    screen=navigation.current,
                    metadata={
                        "request_id": origin_request_id,
                        "age_ms": max(0, int(time.time() * 1000) - int(origin_created_at_ms or 0)),
                        "origin_generation": origin_transition_generation,
                        "current_generation": player_transition_generation["value"],
                        "reason": "stale_before_bridge_send",
                    },
                )
            raise asyncio.CancelledError()

        request_id = await bridge.play(
            path,
            title,
            position_ms,
            episode_id=episode_id,
            anime_id=anime_id,
            can_next=bool(navigation_snapshot.get("can_next")),
            can_previous=bool(navigation_snapshot.get("can_previous")),
            autoplay=settings.get("player.autoplay_next"),
            origin_request_id=origin_request_id,
            origin_created_at_ms=origin_created_at_ms,
            origin_transition_generation=origin_transition_generation,
            origin_player_session_id=origin_player_session_id,
            origin_monotonic_ns=origin_monotonic_ns,
            transition_direction=direction_label or None,
            player_settings={
                "player.default_speed": settings.get("player.default_speed"),
                "player.aspect_ratio": settings.get("player.aspect_ratio"),
                "player.zoom_enabled": settings.get("player.zoom_enabled"),
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
        if not transition_is_valid():
            if origin_request_id:
                performance.event(
                    invalidated_event,
                    screen=navigation.current,
                    metadata={
                        "request_id": origin_request_id,
                        "target_request_id": request_id,
                        "reason": "session_invalidated_after_bridge",
                        "player_session_id": origin_player_session_id,
                    },
                )
            raise asyncio.CancelledError()

        performance.event(
            "NATIVE_HANDOFF_ACCEPTED",
            screen=navigation.current,
            metadata={
                "request_id": request_id,
                "episode_id": episode_id,
                "anime_id": anime_id,
                "origin_request_id": origin_request_id,
                "origin_created_at_ms": origin_created_at_ms,
                "origin_transition_generation": origin_transition_generation,
            },
        )
        logger.info(
            "[PLAYER] PLAY_COMMAND_CONFIRMED request_id=%s origin_request_id=%s",
            request_id,
            origin_request_id or "-",
        )
        return request_id

    def play_episode(path, title, on_next=None, progress_seconds=0, *, episode_id=None, anime_id=None):
        performance.event("player.click", screen=navigation.current,
                          metadata={"path": path, "progress_seconds": progress_seconds,
                                    "episode_id": episode_id, "anime_id": anime_id})
        if not settings.get("player.resume"):
            progress_seconds = 0
        if player_launch_inflight["value"]:
            logger.info("[PLAYER] duplicate launch ignored path=%s", path)
            diagnostics.record(
                "PLAYER_HANDOFF_DUPLICATE_IGNORED",
                source="android_bridge",
                result="launch_inflight",
            )
            return
        player_launch_inflight["value"] = True

        async def launch_native_player():
            try:
                request_id = await start_native_player(
                    path,
                    title,
                    max(0, int(progress_seconds * 1000)),
                    episode_id=episode_id,
                    anime_id=anime_id,
                )
                performance.event(
                    "player.launch_complete",
                    screen=navigation.current,
                    metadata={"request_id": request_id, "episode_id": episode_id, "anime_id": anime_id},
                )
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
            finally:
                player_launch_inflight["value"] = False

        # NativePlayerActivity is the only player. Do not push a synthetic Flet
        # route before launching it; the current Details/Home screen remains the
        # origin to which Android back returns.
        page.run_task(launch_native_player)
    def open_marathon(anime_id, current_path=None):
        async def load_and_show():
            try:
                report = await asyncio.to_thread(library.marathon, int(anime_id), current_path=current_path)
            except Exception:
                logger.exception("Marathon calculation failed", extra={"anime_id": anime_id})
                page.pop_dialog()
                page.snack_bar = ft.SnackBar(ft.Text("Não foi possível calcular a maratona agora."))
                page.snack_bar.open = True
                safe_update()
                return

            items = report.get("items") or []
            if not items:
                dialog.content = ft.Column([
                    ft.Text("Nenhum episódio restante foi encontrado."),
                    ft.Text("Episódios concluídos não entram no cálculo. Durações desconhecidas não são inventadas.", size=12),
                ], tight=True)
                dialog.actions = [ft.TextButton("Fechar", on_click=lambda _: page.pop_dialog())]
                page.update()
                return

            known_seconds = float(report.get("known_duration_seconds") or 0)
            unknown_count = int(report.get("unknown_duration_count") or 0)
            start = datetime.datetime.now()
            estimated_end = start + datetime.timedelta(seconds=known_seconds)
            lines = [
                ft.Text(f"{report.get('episode_count', 0)} episódios na sequência", weight=ft.FontWeight.BOLD),
                ft.Text(f"Tempo conhecido: {format_duration(known_seconds)}"),
                ft.Text(f"Início: {start.strftime('%H:%M')}"),
            ]
            if unknown_count:
                lines.append(ft.Text(f"{unknown_count} episódio(s) sem duração — término parcialmente desconhecido.", color=ft.Colors.ORANGE_300))
            else:
                lines.append(ft.Text(f"Término estimado: {estimated_end.strftime('%H:%M')}"))
                lines.append(ft.Text("Estimativa em velocidade normal; pausas e interrupções não estão incluídas.", size=11))
            episode_lines = []
            for index, item in enumerate(items[:48], 1):
                label = item.get("episode_title") or item.get("file_name") or f"Episódio {index}"
                remaining = item.get("remaining_seconds")
                remaining_label = format_duration(remaining) if remaining is not None else "duração desconhecida"
                prefix = "Agora • " if item.get("is_current") else ""
                episode_lines.append(ft.Text(f"{prefix}{label} — {remaining_label}", size=11))
            lines.append(ft.Column(episode_lines, spacing=4, scroll=ft.ScrollMode.AUTO, height=min(320, max(160, len(episode_lines) * 26))))
            dialog.content = ft.Column(lines, tight=True, spacing=8, width=min(520, max(280, float(page.width or 480) - 48)))
            dialog.actions = [ft.TextButton("Fechar", on_click=lambda _: page.pop_dialog())]
            page.update()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Maratona"),
            content=ft.Row([ft.ProgressRing(), ft.Text("Calculando…")], tight=True),
            actions=[ft.TextButton("Cancelar", on_click=lambda _: page.pop_dialog())],
        )
        page.show_dialog(dialog)
        page.run_task(load_and_show)
    def navigate_details(anime, on_back=None):
        previous = navigation.current
        anime_id = (anime or {}).get("id") if isinstance(anime, dict) else None
        current_id = (current[0] or {}).get("id") if isinstance(current[0], dict) else None
        if navigation.current == "details" and anime_id == current_id:
            performance.counter("navigation.duplicate_details_ignored")
            logger.info("[NAV] duplicate Details navigation ignored anime_id=%s", anime_id)
            return
        with performance.interaction("open_details", source=previous, target="details",
                                      metadata={"anime_id": anime_id}):
            current[0] = anime
            _drop_screen_cache("details")
            if navigation.current != "details":
                navigation.push("details")
            render_current(reason="open_details")
            persist_navigation_state()
    async def refresh_current_details():
        """Reload the durable record after an in-place Details edit."""
        refresh_started = performance.now()
        anime_id = current[0].get("id") if current[0] else None
        details_token = details_instance_generation[0]
        if navigation.current != "details" or anime_id is None:
            return
        catalog = await asyncio.to_thread(library.catalog)
        if (
            navigation.current != "details"
            or details_instance_generation[0] != details_token
            or (current[0] or {}).get("id") != anime_id
        ):
            logger.info("[DETAILS] stale refresh ignored anime_id=%s token=%s", anime_id, details_token)
            return
        current[0] = next((item for item in catalog if item["id"] == anime_id), current[0])
        render_current(force=True, reason="details_refresh")
        performance.event("details.refresh", duration_ms=(performance.now()-refresh_started)*1000.0,
                          screen="details", metadata={"anime_id": anime_id})
    async def refresh_current_metadata(e=None):
        """Refresh only editorial metadata; never rescans or mutates playback state."""
        metadata_started = performance.now()
        anime = current[0] or {}
        anime_id = anime.get("id")
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
            if navigation.current != "details" or (current[0] or {}).get("id") != anime_id:
                logger.info("[METADATA] stale refresh result ignored anime_id=%s", anime_id)
                return
            await refresh_current_details()
            performance.event("details.metadata_refresh", duration_ms=(performance.now()-metadata_started)*1000.0,
                              screen="details", status="ok", metadata={"anime_id": anime_id})
            page.snack_bar = ft.SnackBar(ft.Text("Metadata atualizada."))
            page.snack_bar.open = True
            safe_update()
        except Exception:
            logger.exception("[METADATA] refresh failed anime_id=%s", anime_id)
            page.snack_bar = ft.SnackBar(ft.Text("Não foi possível atualizar a metadata agora."))
            page.snack_bar.open = True
            safe_update()
    def on_catalog_changed(*, refresh_details=True):
        catalog_started = performance.now()
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
        if navigation.current == "details" and not refresh_details:
            return
        _drop_screen_cache(navigation.current)
        render_current(reason="catalog_changed")
        performance.event("ui.catalog_changed", duration_ms=(performance.now()-catalog_started)*1000.0,
                          screen=navigation.current, metadata={"refresh_details": refresh_details})

    def apply_settings_runtime(key, _value):
        setting_key = str(key)
        if setting_key == "appearance.theme":
            # Theme changes invalidate only Python/Flet control trees. Navigation,
            # query/filter state, scroll snapshots and all domain/storage/player
            # state remain owned by their existing controllers.
            apply_page_theme(page, settings.get("appearance.theme"))
            _invalidate_cached_view(home_state, "home")
            _invalidate_cached_view(organize_state, "organize")
            _clear_screen_cache()
            render_current(force=True, reason="theme_changed")
            return
        library.configure_settings(settings)
        if setting_key.startswith(("appearance.", "library.")):
            _invalidate_cached_view(home_state, "home")
            _invalidate_cached_view(organize_state, "organize")
            current_route = navigation.current
            if current_route in {"home", "organize"}:
                render_current(reason="runtime_setting_changed")

    def handle_platform_brightness_change(_event=None):
        if settings.get("appearance.theme") != "system":
            return
        apply_page_theme(page, "system")
        _invalidate_cached_view(home_state, "home")
        _invalidate_cached_view(organize_state, "organize")
        _clear_screen_cache()
        render_current(force=True, reason="platform_brightness")
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
        previous = navigation.current
        if navigation.current == "settings" and not navigation.settings_path:
            performance.counter("navigation.duplicate_settings_ignored")
            logger.info("[NAV] duplicate Settings navigation ignored")
            return
        with performance.interaction("open_settings", source=previous, target="settings"):
            if navigation.current != "settings":
                navigation.push("settings")
            _drop_screen_cache("settings")
            render_current(reason="open_settings")
            persist_navigation_state()
            if bridge.available:
                diagnostics.record("PERMISSION_CHECK", source="android")
                page.run_task(bridge.check_storage_access)
    def navigate_settings_category(label):
        previous = navigation.current
        with performance.interaction("settings_category", source=previous, target="settings",
                                      metadata={"category": label}):
            if navigation.current != "settings":
                navigation.push("settings")
            navigation.push_settings(label)
            _drop_screen_cache("settings")
            render_current(reason="open_settings_category")
            persist_navigation_state()

    def close_home_search():
        if not home_state.get("search_visible"):
            return False
        home_state["search_visible"] = False
        home_state["query"] = ""
        _invalidate_cached_view(home_state, "home")
        logger.info("[NAV] SEARCH_BACK consumed on Home")
        render_current(reason="home_search_closed")
        persist_navigation_state()
        return True

    def navigate_back(source="unknown"):
        # One user Back gesture/button owns one logical operation. This protects
        # against Android + Flutter delivering the same physical Back twice.
        back_policy_started = performance.now()
        now = time.monotonic()
        route_before = navigation.current
        if now - back_state["last_at"] < BACK_DEBOUNCE_SECONDS:
            logger.info(
                "[NAV] duplicate BACK suppressed source=%s route=%s delta_ms=%.0f",
                source, route_before, (now - back_state["last_at"]) * 1000,
            )
            performance.event("interaction.back", duration_ms=(performance.now()-back_policy_started)*1000.0,
                              status="duplicate_suppressed", screen=route_before,
                              metadata={"source": source, "from": route_before})
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
            performance.event("interaction.back", duration_ms=(performance.now()-back_policy_started)*1000.0,
                              status="dialog", screen=route_before,
                              metadata={"source": source, "from": route_before})
            safe_update()
            return

        # Search is a transient Home state, not a second route. Close it before
        # delegating Back to the top-level NavigationController.
        if route_before == "home" and close_home_search():
            performance.event("interaction.back", duration_ms=(performance.now()-back_policy_started)*1000.0,
                              status="search_closed", screen=route_before,
                              metadata={"source": source, "from": route_before})
            return

        action = navigation.back()
        performance.event("interaction.back", duration_ms=(performance.now()-back_policy_started)*1000.0,
                          screen=navigation.current,
                          metadata={"source": source, "from": route_before, "action": action, "to": navigation.current})
        logger.info(
            "NAV_BACK_POLICY duration_ms=%s source=%s from=%s action=%s",
            int((performance.now() - back_policy_started) * 1000),
            source,
            route_before,
            action,
        )
        back_state["navigation_count"] += 1
        navigation_event_id = back_state["navigation_count"]
        logger.info(
            "BACK_NAVIGATION_EXECUTED id=%s source=%s from=%s action=%s to=%s",
            navigation_event_id, source, route_before, action, navigation.current,
        )
        logger.info(
            "[NAV] NAVIGATE_BACK source=%s from=%s action=%s to=%s",
            source, route_before, action, navigation.current,
        )
        if action in {"previous", "settings_inner"}:
            # Settings content is rebuilt whenever its nested path changes, while
            # top-level screens remain cached for scroll/filter/search continuity.
            # A dialog-only Back was already returned above and therefore does not
            # invalidate the active Settings task generation.
            if route_before == "settings" and (
                action == "settings_inner" or navigation.current != "settings"
            ):
                settings_tasks.invalidate()
            if action == "settings_inner":
                _drop_screen_cache("settings")
            elif navigation.current == "settings":
                _drop_screen_cache("settings")
            # Details can mutate favorite/pin/progress state in LibraryStore while
            # Organize is cached for scroll/filter continuity. Refresh only when
            # returning to Organize so its collection reflects durable state
            # without triggering a scan or permission flow.
            if navigation.current == "organize":
                _drop_screen_cache("organize")
            render_current(reason="back")
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
            render_current(force=True, reason="settings_refresh")
    async def add_folder(_=None):
        # A scan already running must not block the user from choosing another
        # folder. ScanCoordinator already queues/coalesces the follow-up rescan.
        if scan_coordinator.exclusive or saf_selection.pending:
            return False
        if not saf_selection.begin():
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
    thumbnail_request_started_at = {}
    thumbnail_latest_key_by_uri = {}
    thumbnail_latest_at = {}
    thumbnail_completed_request_by_key = {}

    def _prune_thumbnail_requests():
        now = time.monotonic()
        for key, started_at in list(thumbnail_request_started_at.items()):
            if now - started_at > 60.0:
                thumbnail_request_started_at.pop(key, None)
                thumbnail_requests.discard(key)
                uri = key[0]
                if thumbnail_latest_key_by_uri.get(uri) == key:
                    thumbnail_latest_key_by_uri.pop(uri, None)
                    thumbnail_latest_at.pop(uri, None)
        if len(thumbnail_latest_at) > 1024:
            oldest = sorted(thumbnail_latest_at.items(), key=lambda item: item[1])[:256]
            for uri, _ in oldest:
                thumbnail_latest_at.pop(uri, None)
                thumbnail_latest_key_by_uri.pop(uri, None)
        if len(thumbnail_completed_request_by_key) > 1024:
            for key in list(thumbnail_completed_request_by_key)[:256]:
                thumbnail_completed_request_by_key.pop(key, None)

    def request_missing_thumbnail(item):
        thumbnail_started = performance.now()
        performance.counter("artwork.thumbnail.request")
        if not bridge.available or not isinstance(item, dict):
            performance.counter("artwork.thumbnail.rejected")
            return
        episode = item if item.get("path") else item.get("current_episode") or {}
        path_ref = str(episode.get("path") or "").strip()
        if not path_ref or episode.get("missing"):
            return
        _prune_thumbnail_requests()
        key = (path_ref, int(episode.get("file_size") or 0), int(episode.get("modified_at") or 0))
        if key in thumbnail_requests:
            return
        existing_latest = thumbnail_latest_key_by_uri.get(path_ref)
        if existing_latest is not None and existing_latest != key:
            # A newer media generation supersedes the previous request immediately.
            # The older native request may still finish later, but its callback will
            # be rejected by the latest-generation check. Do not block the newer
            # request merely because the older generation is still in flight.
            thumbnail_requests.discard(existing_latest)
            thumbnail_request_started_at.pop(existing_latest, None)
        thumbnail_latest_key_by_uri[path_ref] = key
        thumbnail_latest_at[path_ref] = time.monotonic()
        try:
            resolved = library.resolve_artwork("episode", episode.get("id"), "episode_thumbnail", allow_network=False)
        except Exception:
            resolved = None
        if resolved and resolved.get("local_path") and os.path.isfile(resolved.get("local_path")):
            thumbnail_requests.discard(key)
            thumbnail_request_started_at.pop(key, None)
            if thumbnail_latest_key_by_uri.get(path_ref) == key:
                thumbnail_latest_key_by_uri.pop(path_ref, None)
                thumbnail_latest_at.pop(path_ref, None)
            performance.counter("artwork.thumbnail.cache_hit")
            performance.event("artwork.thumbnail", duration_ms=(performance.now()-thumbnail_started)*1000.0,
                              status="cache_hit", screen=navigation.current, metadata={"path": path_ref})
            return
        performance.counter("artwork.thumbnail.cache_miss")
        if len(thumbnail_requests) >= 32:
            thumbnail_requests.discard(key)
            thumbnail_request_started_at.pop(key, None)
            if thumbnail_latest_key_by_uri.get(path_ref) == key:
                thumbnail_latest_key_by_uri.pop(path_ref, None)
                thumbnail_latest_at.pop(path_ref, None)
            performance.counter("artwork.thumbnail.rejected")
            return
        thumbnail_requests.add(key)
        thumbnail_request_started_at[key] = time.monotonic()
        performance.event("artwork.thumbnail", duration_ms=(performance.now()-thumbnail_started)*1000.0,
                          status="requested", screen=navigation.current, metadata={"path": path_ref, "media_identity": episode.get("media_identity")})
        async def run():
            try:
                await bridge.request_thumbnail(path_ref, key[1], key[2], str(episode.get('media_identity') or ''))
            except Exception as exc:
                thumbnail_requests.discard(key)
                thumbnail_request_started_at.pop(key, None)
                if thumbnail_latest_key_by_uri.get(path_ref) == key:
                    thumbnail_latest_key_by_uri.pop(path_ref, None)
                    thumbnail_latest_at.pop(path_ref, None)
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
                "O ReiAnix precisa de uma fonte de acesso aos seus vídeos locais. "
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

        poll_interval = 0.08
        while ui_alive[0]:
            try:
                mailbox_started = performance.now()
                mailbox_backlog_before = bridge.pending_count()
                events = bridge.drain()
                performance.gauge("android.mailbox.backlog", mailbox_backlog_before)
                performance.counter("android.mailbox.events_drained", len(events))
                failed_event_ids = set()
                seen_native_event_ids = set()
                for event in events:
                    try:
                        if not isinstance(event, dict):
                            continue
                        event["receivedAtMs"] = int(time.time() * 1000)
                        performance.record_native_event(event)
                        event_id = str(event.get('eventId') or '').strip()
                        if not event_id:
                            logger.error("[ANDROID] EVENT_REJECTED reason=missing_event_id type=%s", event.get('type'))
                            continue
                        if event_id in seen_native_event_ids:
                            performance.counter("android.events.duplicate")
                            logger.warning("[ANDROID] EVENT_DUPLICATE_IN_BATCH eventId=%s", event_id)
                            continue
                        seen_native_event_ids.add(event_id)
                        if store.has_native_event(event_id):
                            performance.counter("android.events.duplicate")
                            logger.info("[ANDROID] EVENT_DUPLICATE eventId=%s result=already_processed", event_id)
                            continue
                        event_type = event.get('type')
                        payload = event.get('payload')
                        if payload is None:
                            payload = {}
                        if not isinstance(payload, dict):
                            continue
                        # Resolve AndroidBridge command waiters only from the
                        # existing NativeMailbox event emitted by MainActivity.
                        # This makes launch acceptance distinct from real intent
                        # delivery; no secondary IPC channel is introduced.
                        bridge.observe_native_event(event)
                        event_request_id = event.get('requestId') or payload.get('requestId')
                        event_scan_id = payload.get('scanId') or event.get('scanId')
                        operation_state = str(
                            event.get('operationState')
                            or payload.get('operationState')
                            or ''
                        ).strip().upper()
                        if event_request_id and operation_state:
                            native_operation_states[str(event_request_id)] = operation_state
                            if len(native_operation_states) > 128:
                                native_operation_states.pop(next(iter(native_operation_states)))
                        if event_type == 'diagnostic':
                            diagnostic_event = str(payload.get('event') or 'NATIVE_DIAGNOSTIC').strip()
                            if diagnostic_event.startswith(('COMMAND_', 'OPERATION_')):
                                logger.info(
                                    "[ANDROID] %s requestId=%s action=%s state=%s result=%s",
                                    diagnostic_event,
                                    event_request_id or "-",
                                    payload.get('action') or "-",
                                    operation_state or "-",
                                    payload.get('result') or "-",
                                )
                            diagnostic_event = str(payload.get('event') or 'NATIVE_DIAGNOSTIC').strip()
                            if diagnostic_event == "PLAYER_HANDOFF_DISPATCHED" and event_request_id:
                                player_active_request_id["value"] = event_request_id
                                player_session_active["value"] = True
                            elif diagnostic_event == "PLAYER_ACTIVITY_RESULT":
                                controlled_result = bool(payload.get("controlled"))
                                if controlled_result and (
                                    player_active_request_id["value"] in (None, event_request_id)
                                ):
                                    cancel_player_transition("player_activity_result")
                                    player_active_request_id["value"] = None
                                    player_session_active["value"] = False
                            elif diagnostic_event == "PLAYER_LIFECYCLE":
                                lifecycle = str(payload.get("lifecycle") or "").strip()
                                lifecycle_session = str(payload.get("playerSessionId") or "").strip() or None
                                lifecycle_state = str(payload.get("sessionState") or "").strip().upper()
                                if lifecycle_session:
                                    if lifecycle in {"onCreate", "onNewIntent", "onStart", "onResume"}:
                                        player_active_session_id["value"] = lifecycle_session
                                        if event_request_id:
                                            player_active_request_id["value"] = event_request_id
                                        player_session_active["value"] = lifecycle_state not in {"EXITING", "DESTROYED"}
                                    elif lifecycle in {"onPause", "onStop", "onDestroy"} and (
                                        lifecycle_state in {"EXITING", "DESTROYED"} or lifecycle == "onDestroy"
                                    ) and player_active_session_id["value"] == lifecycle_session:
                                        cancel_player_transition(f"player_lifecycle_{lifecycle}")
                                        player_session_active["value"] = False
                                        player_active_session_id["value"] = None
                                        player_active_request_id["value"] = None
                                        player_active_episode_id["value"] = None
                                        player_active_anime_id["value"] = None
                                        player_active_uri["value"] = None
                            elif diagnostic_event == "FIRST_FRAME_RENDERED":
                                pending_candidates = (
                                    ("NEXT", pending_next_transition["value"]),
                                    ("PREVIOUS", pending_previous_transition["value"]),
                                )
                                context_direction = None
                                context = None
                                for candidate_direction, candidate_context in pending_candidates:
                                    if isinstance(candidate_context, dict) and event_request_id == str(candidate_context.get("target_request_id") or "").strip():
                                        context_direction = candidate_direction
                                        context = candidate_context
                                        break
                                diagnostic_session = str(payload.get("playerSessionId") or "").strip()
                                if isinstance(context, dict):
                                    target_request_id = str(context.get("target_request_id") or "").strip()
                                    origin_request_id = str(context.get("origin_request_id") or "").strip()
                                    if (
                                        event_request_id == target_request_id
                                        and diagnostic_session == str(context.get("player_session_id") or "")
                                        and player_session_active["value"]
                                        and player_active_session_id["value"] == diagnostic_session
                                        and bool(context.get("ready"))
                                    ):
                                        performance.event(
                                            "NEXT_TRANSITION_FIRST_FRAME" if context_direction == "NEXT" else "PREVIOUS_TRANSITION_FIRST_FRAME",
                                            screen=navigation.current,
                                            metadata={
                                                "request_id": origin_request_id,
                                                "target_request_id": target_request_id,
                                                "player_session_id": diagnostic_session,
                                                "episode_id": payload.get("episodeId") or context.get("target_episode_id"),
                                                "generation": payload.get("generation"),
                                            },
                                        )
                                        performance.event(
                                            "NEXT_TRANSITION_COMMITTED" if context_direction == "NEXT" else "PREVIOUS_TRANSITION_COMMITTED",
                                            screen=navigation.current,
                                            metadata={
                                                "request_id": origin_request_id,
                                                "target_request_id": target_request_id,
                                                "player_session_id": diagnostic_session,
                                                "episode_id": payload.get("episodeId") or context.get("target_episode_id"),
                                            },
                                        )
                                        performance.event(
                                            "PLAYER_TRANSITION_COMMITTED",
                                            screen=navigation.current,
                                            metadata={
                                                "request_id": target_request_id,
                                                "episode_id": payload.get("episodeId") or context.get("target_episode_id"),
                                                "generation": payload.get("generation"),
                                                "transition_generation": context.get("native_transition_generation"),
                                            },
                                        )
                                        pending_next_transition["value"] = None
                                    elif context is not None:
                                        performance.event(
                                            "NEXT_REQUEST_STALE" if context_direction == "NEXT" else "PREVIOUS_REQUEST_STALE" if is_next else "PREVIOUS_REQUEST_STALE",
                                            screen=navigation.current,
                                            status="rejected",
                                            metadata={
                                                "request_id": origin_request_id,
                                                "target_request_id": target_request_id,
                                                "reason": "first_frame_wrong_session_or_request",
                                                "player_session_id": diagnostic_session,
                                                "current_session_id": player_active_session_id["value"],
                                            },
                                        )
                                        performance.event(
                                            "PLAYER_NEXT_STALE_REJECTED" if context_direction == "NEXT" else "PLAYER_PREVIOUS_STALE_REJECTED" if is_next else "PLAYER_PREVIOUS_STALE_REJECTED",
                                            screen=navigation.current,
                                            metadata={
                                                "request_id": origin_request_id,
                                                "age_ms": max(0, int(time.time() * 1000) - int(context.get("created_at_ms") or 0)),
                                                "origin_generation": context.get("native_transition_generation"),
                                                "current_generation": player_transition_generation["value"],
                                                "reason": "first_frame_wrong_session_or_request",
                                            },
                                        )
                            diagnostics.record(
                                diagnostic_event,
                                request_id=event_request_id,
                                scan_id=event_scan_id,
                                source=payload.get('source'),
                                result=payload.get('result') or payload.get('access'),
                            )
                        else:
                            if event_type in {
                                "player_next_request",
                                "player_previous_request",
                                "player_opened",
                                "player_exited",
                                "player_error",
                            }:
                                created_ms = int(
                                    event.get("createdAt")
                                    or payload.get("createdAt")
                                    or time.time() * 1000
                                )
                                performance.event(
                                    "player.mailbox.consume",
                                    duration_ms=max(0, int(time.time() * 1000) - created_ms),
                                    screen=navigation.current,
                                    metadata={
                                        "event_type": event_type,
                                        "request_id": event_request_id,
                                    },
                                )
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
                            _prune_thumbnail_requests()
                            completed_request_id = thumbnail_completed_request_by_key.get(thumbnail_key)
                            if request_id and completed_request_id == request_id and thumbnail_key not in thumbnail_requests:
                                diagnostics.record(
                                    "THUMBNAIL_DUPLICATE",
                                    request_id=request_id,
                                    result="IGNORED",
                                )
                                continue
                            latest_key = thumbnail_latest_key_by_uri.get(uri)
                            if latest_key is not None and thumbnail_key != latest_key:
                                performance.counter("artwork.thumbnail.stale")
                                # Only the latest requested media version may publish.
                                # Older requests can finish later and must never
                                # overwrite the current thumbnail/artwork.
                                thumbnail_requests.discard(thumbnail_key)
                                thumbnail_request_started_at.pop(thumbnail_key, None)
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
                                thumbnail_requests.discard(thumbnail_key)
                                started_native = thumbnail_request_started_at.pop(thumbnail_key, None)
                                thumbnail_latest_at[uri] = time.monotonic()
                                if request_id:
                                    thumbnail_completed_request_by_key[thumbnail_key] = request_id
                                if registered:
                                    if started_native is not None:
                                        performance.event("artwork.thumbnail", duration_ms=(time.monotonic()-started_native)*1000.0,
                                                          status="ready", screen=navigation.current,
                                                          metadata={"path": uri, "media_identity": media_identity, "update": True})
                                    performance.counter("artwork.thumbnail.update")
                                    # A generated thumbnail changes one image, not the
                                    # catalog membership or ordering. Keep mounted Home
                                    # controls (and their scroll/focus state) intact.
                                    update_thumbnail = home_state.get('_update_thumbnail')
                                    if callable(update_thumbnail):
                                        update_thumbnail(uri, thumbnail_path)
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
                            latest_key = thumbnail_latest_key_by_uri.get(uri)
                            thumbnail_requests.discard(thumbnail_key)
                            thumbnail_request_started_at.pop(thumbnail_key, None)
                            if latest_key == thumbnail_key:
                                thumbnail_latest_key_by_uri.pop(uri, None)
                                thumbnail_latest_at.pop(uri, None)
                            diagnostics.record(
                                "THUMBNAIL_ERROR",
                                request_id=request_id,
                                result=payload.get('status') or "FAILED",
                                error=event.get('message') or payload.get('error'),
                            )
                        elif event_type in {'performance_metrics', 'performance_player'}:
                            performance.record_native_event(event)
                            continue
                        elif event_type == 'player_opened':
                            session_id = str(payload.get("playerSessionId") or "").strip()
                            if session_id:
                                if player_active_session_id["value"] not in (None, session_id):
                                    diagnostics.record(
                                        "PLAYER_OPENED_IGNORED",
                                        request_id=event_request_id,
                                        source="native_player",
                                        result="stale_player_session",
                                    )
                                    continue
                                player_active_session_id["value"] = session_id
                                player_session_active["value"] = True
                                player_active_episode_id["value"] = payload.get("episodeId")
                                player_active_anime_id["value"] = payload.get("animeId")
                                player_active_uri["value"] = payload.get("uri")

                            context = pending_next_transition["value"]
                            if isinstance(context, dict):
                                target_request_id = str(context.get("target_request_id") or "").strip()
                                if (
                                    event_request_id == target_request_id
                                    and session_id
                                    and session_id == str(context.get("player_session_id") or "")
                                    and str(payload.get("episodeId") or "") == str(context.get("target_episode_id") or "")
                                ):
                                    context["ready"] = True
                                    performance.event(
                                        "NEXT_TRANSITION_READY",
                                        screen=navigation.current,
                                        metadata={
                                            "request_id": context.get("origin_request_id"),
                                            "target_request_id": target_request_id,
                                            "player_session_id": session_id,
                                            "episode_id": payload.get("episodeId"),
                                            "transition_generation": context.get("native_transition_generation"),
                                        },
                                    )
                                    player_active_request_id["value"] = event_request_id
                                    diagnostics.record(
                                        "PLAYER_OPENED",
                                        request_id=event_request_id,
                                        source=payload.get("source") or "native_player",
                                        result=payload.get("state") or "READY",
                                    )
                                else:
                                    performance.event(
                                        "NEXT_REQUEST_STALE",
                                        screen=navigation.current,
                                        status="rejected",
                                        metadata={
                                            "request_id": context.get("origin_request_id"),
                                            "target_request_id": target_request_id,
                                            "reason": "player_opened_wrong_target",
                                        },
                                    )
                            else:
                                player_active_request_id["value"] = event_request_id
                                player_session_active["value"] = True
                                performance.event(
                                    "PLAYER_TRANSITION_COMMITTED",
                                    screen=navigation.current,
                                    metadata={
                                        "request_id": event_request_id,
                                        "episode_id": payload.get("episodeId"),
                                        "generation": payload.get("generation"),
                                        "transition_generation": payload.get("transitionGeneration"),
                                    },
                                )
                                diagnostics.record(
                                    "PLAYER_OPENED",
                                    request_id=event_request_id,
                                    source=payload.get("source") or "native_player",
                                    result=payload.get("state") or "READY",
                                )
                        elif event_type in {'player_progress', 'player_paused', 'player_completed'}:
                            path_ref = str(payload.get('uri') or '').strip()
                            if path_ref:
                                try:
                                    position_ms = max(0.0, float(payload.get('positionMs') or 0.0))
                                    duration_ms = max(0.0, float(payload.get('durationMs') or 0.0))
                                    progress_started = performance.now()
                                    updated = await asyncio.to_thread(
                                        store.save_progress,
                                        path_ref,
                                        position_ms / 1000.0,
                                        duration_ms / 1000.0,
                                        episode_id=payload.get("episodeId"),
                                        event_created_at=event.get('createdAt') or event.get('timestamp'),
                                    )
                                    performance.event("player.progress_persist", duration_ms=(performance.now()-progress_started)*1000.0,
                                                      screen=navigation.current,
                                                      metadata={"episode_id": payload.get("episodeId"), "media_identity": payload.get("mediaId"),
                                                                "position_ms": position_ms, "duration_ms": duration_ms, "event": event_type,
                                                                "updated": updated})
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
                            if path_ref or payload.get("episodeId"):
                                updated = await asyncio.to_thread(
                                    store.set_watched, path_ref, True, episode_id=payload.get("episodeId")
                                )
                            diagnostics.record(
                                "PLAYER_MARK_WATCHED",
                                request_id=event_request_id,
                                source="native_player",
                                result="updated" if updated else "ignored",
                            )
                        elif event_type == 'player_mark_unwatched':
                            path_ref = str(payload.get('uri') or '').strip()
                            updated = False
                            if path_ref or payload.get("episodeId"):
                                updated = await asyncio.to_thread(
                                    store.set_watched, path_ref, False, episode_id=payload.get("episodeId")
                                )
                            diagnostics.record(
                                "PLAYER_MARK_UNWATCHED",
                                request_id=event_request_id,
                                source="native_player",
                                result="updated" if updated else "ignored",
                            )
                        elif event_type == 'player_autoplay_changed':
                            enabled = bool(payload.get('enabled'))
                            settings.set("player.autoplay_next", enabled)
                            diagnostics.record(
                                "PLAYER_AUTOPLAY_CHANGED",
                                request_id=event_request_id,
                                source="native_player",
                                result="enabled" if enabled else "disabled",
                            )
                        elif event_type in {'player_next_request', 'player_previous_request'}:
                            transition_started = performance.now()
                            direction_name = "NEXT" if event_type == "player_next_request" else "PREVIOUS"
                            is_next = direction_name == "NEXT"
                            player_command_sequence["value"] += 1
                            command_sequence = int(payload.get("sequence") or player_command_sequence["value"])
                            button_created_at_ms = int(
                                payload.get("buttonPressedAtMs")
                                or payload.get("createdAt")
                                or event.get("createdAt")
                                or 0
                            )
                            source_player_session_id = str(payload.get("playerSessionId") or "").strip()
                            mailbox_created_at_ms = int(event.get("createdAt") or button_created_at_ms or int(time.time() * 1000))
                            mailbox_latency_ms = max(0, int(time.time() * 1000) - mailbox_created_at_ms)

                            performance.event(
                                "NEXT_BUTTON_PRESSED" if is_next else "PREVIOUS_BUTTON_PRESSED",
                                screen=navigation.current,
                                metadata={
                                    "request_id": event_request_id,
                                    "sequence": command_sequence,
                                    "episode_id": payload.get("episodeId"),
                                    "anime_id": payload.get("animeId"),
                                    "transition_generation": payload.get("transitionGeneration"),
                                    "player_session_id": source_player_session_id,
                                },
                            )
                            if not is_next:
                                performance.event(
                                    "PREVIOUS_REQUEST_RECEIVED",
                                    screen=navigation.current,
                                    metadata={
                                        "request_id": event_request_id,
                                        "sequence": command_sequence,
                                        "command_created_at_ms": button_created_at_ms,
                                        "command_monotonic_ns": payload.get("monotonicNs"),
                                        "transition_generation": payload.get("transitionGeneration"),
                                        "player_session_id": source_player_session_id,
                                    },
                                )
                            performance.event(
                                "PYTHON_MAILBOX_RECEIVED",
                                screen=navigation.current,
                                metadata={
                                    "request_id": event_request_id,
                                    "direction": direction_name,
                                    "sequence": command_sequence,
                                    "mailbox_age_ms": mailbox_latency_ms,
                                    "command_created_at_ms": button_created_at_ms,
                                    "command_generation": payload.get("transitionGeneration"),
                                    "current_generation": player_transition_generation["value"],
                                    "player_session_id": source_player_session_id,
                                },
                            )

                            duplicate_request = bool(event_request_id and event_request_id in player_command_seen)
                            if duplicate_request:
                                performance.event(
                                    "PLAYER_COMMAND_DUPLICATE",
                                    screen=navigation.current,
                                    status="duplicate",
                                    metadata={"request_id": event_request_id, "direction": direction_name, "sequence": command_sequence},
                                )
                                if is_next:
                                    performance.event(
                                        "NEXT_REQUEST_DUPLICATE" if is_next else "PREVIOUS_REQUEST_DUPLICATE",
                                        screen=navigation.current,
                                        status="rejected",
                                        metadata={
                                            "request_id": event_request_id,
                                            "age_ms": mailbox_latency_ms,
                                            "reason": "same_request_id",
                                            "player_session_id": source_player_session_id,
                                        },
                                    )
                                    continue
                            elif event_request_id:
                                player_command_seen.add(event_request_id)
                                if len(player_command_seen) > 128:
                                    player_command_seen.pop()

                            previous_sequence = int(player_last_command.get("sequence") or 0)
                            if command_sequence < previous_sequence:
                                performance.event(
                                    "PLAYER_COMMAND_OUT_OF_ORDER",
                                    screen=navigation.current,
                                    status="out_of_order",
                                    metadata={
                                        "request_id": event_request_id,
                                        "direction": direction_name,
                                        "sequence": command_sequence,
                                        "previous_sequence": previous_sequence,
                                        "previous_request_id": player_last_command.get("request_id"),
                                    },
                                )
                                performance.event(
                                    "NEXT_REQUEST_STALE" if is_next else "PREVIOUS_REQUEST_STALE",
                                        screen=navigation.current,
                                        status="rejected",
                                        metadata={
                                            "request_id": event_request_id,
                                            "age_ms": mailbox_latency_ms,
                                            "origin_generation": payload.get("transitionGeneration"),
                                            "current_generation": player_transition_generation["value"],
                                            "reason": "out_of_order",
                                        },
                                    )
                                performance.event(
                                    "PLAYER_NEXT_STALE_REJECTED" if is_next else "PLAYER_PREVIOUS_STALE_REJECTED",
                                    screen=navigation.current,
                                    metadata={
                                        "request_id": event_request_id,
                                        "age_ms": mailbox_latency_ms,
                                        "origin_generation": payload.get("transitionGeneration"),
                                        "current_generation": player_transition_generation["value"],
                                        "reason": "out_of_order",
                                    },
                                )
                                continue
                            player_last_command.update(
                                sequence=command_sequence,
                                request_id=event_request_id,
                                direction=direction_name,
                                created_at_ms=button_created_at_ms,
                            )

                            if is_next and not source_player_session_id:
                                performance.event(
                                    "NEXT_REQUEST_REJECTED",
                                    screen=navigation.current,
                                    status="rejected",
                                    metadata={
                                        "request_id": event_request_id,
                                        "reason": "missing_player_session_id",
                                        "age_ms": mailbox_latency_ms,
                                    },
                                )
                                continue

                            if is_next and player_active_session_id["value"] not in (None, source_player_session_id):
                                performance.event(
                                    "NEXT_REQUEST_STALE",
                                    screen=navigation.current,
                                    status="rejected",
                                    metadata={
                                        "request_id": event_request_id,
                                        "age_ms": mailbox_latency_ms,
                                        "origin_generation": payload.get("transitionGeneration"),
                                        "current_generation": player_transition_generation["value"],
                                        "origin_player_session_id": source_player_session_id,
                                        "current_player_session_id": player_active_session_id["value"],
                                        "reason": "player_session_mismatch",
                                    },
                                )
                                performance.event(
                                    "PLAYER_NEXT_STALE_REJECTED",
                                    screen=navigation.current,
                                    metadata={
                                        "request_id": event_request_id,
                                        "age_ms": mailbox_latency_ms,
                                        "origin_generation": payload.get("transitionGeneration"),
                                        "current_generation": player_transition_generation["value"],
                                        "reason": "player_session_mismatch",
                                    },
                                )
                                continue

                            if player_transition_inflight["value"]:
                                performance.event(
                                    "PLAYER_COMMAND_STALE",
                                    screen=navigation.current,
                                    status="rejected",
                                    metadata={
                                        "request_id": event_request_id,
                                        "direction": direction_name,
                                        "age_ms": mailbox_latency_ms,
                                        "current_request_id": player_active_request_id["value"],
                                        "current_generation": player_transition_generation["value"],
                                        "command_generation": payload.get("transitionGeneration"),
                                        "reason": "transition_in_progress",
                                    },
                                )
                                if is_next:
                                    performance.event(
                                        "NEXT_REQUEST_DUPLICATE" if pending_next_transition["value"] and
                                        event_request_id == pending_next_transition["value"].get("origin_request_id")
                                        else "NEXT_REQUEST_REJECTED",
                                        screen=navigation.current,
                                        status="rejected",
                                        metadata={
                                            "request_id": event_request_id,
                                            "age_ms": mailbox_latency_ms,
                                            "reason": "transition_in_progress",
                                        },
                                    )
                                continue

                            active_request = player_active_request_id["value"]
                            if active_request and event_request_id != active_request:
                                performance.event(
                                    "NEXT_REQUEST_STALE" if is_next else "PREVIOUS_REQUEST_STALE",
                                    screen=navigation.current,
                                    status="rejected",
                                    metadata={"request_id": event_request_id, "reason": "stale_player_request"},
                                )
                                performance.event(
                                    "PLAYER_NEXT_STALE_REJECTED" if is_next else "PLAYER_PREVIOUS_STALE_REJECTED",
                                    screen=navigation.current,
                                    metadata={"request_id": event_request_id, "reason": "stale_player_request"},
                                )
                                continue

                            performance.event(
                                "NEXT_REQUEST_ACCEPTED" if is_next else "PREVIOUS_REQUEST_ACCEPTED",
                                screen=navigation.current,
                                status="accepted",
                                metadata={"request_id": event_request_id, "age_ms": mailbox_latency_ms, "origin_generation": payload.get("transitionGeneration"), "player_session_id": source_player_session_id, "origin_monotonic_ns": payload.get("monotonicNs")},
                            )

                            player_transition_inflight["value"] = True
                            player_transition_generation["value"] += 1
                            transition_generation = player_transition_generation["value"]
                            if player_active_request_id["value"] is None:
                                player_active_request_id["value"] = event_request_id
                            player_session_active["value"] = True
                            if player_active_session_id["value"] is None:
                                player_active_session_id["value"] = source_player_session_id

                            transition_context = {
                                "origin_request_id": event_request_id,
                                "target_request_id": None,
                                "player_session_id": source_player_session_id,
                                "native_transition_generation": int(payload.get("transitionGeneration") or 0),
                                "python_transition_generation": transition_generation,
                                "created_at_ms": button_created_at_ms,
                                "command_monotonic_ns": int(payload.get("monotonicNs") or 0),
                                "source_episode_id": payload.get("episodeId"),
                                "source_anime_id": payload.get("animeId"),
                                "source_uri": str(payload.get("uri") or "").strip(),
                                "target_episode_id": None,
                                "target_anime_id": None,
                                "target_uri": None,
                                "ready": False,
                                "direction": direction_name,
                            }
                            if is_next:
                                pending_next_transition["value"] = transition_context
                            else:
                                pending_previous_transition["value"] = transition_context
                            performance.event(
                                "NEXT_TRANSITION_STARTED" if is_next else "PREVIOUS_TRANSITION_STARTED",
                                screen=navigation.current,
                                metadata={"request_id": event_request_id, "generation": transition_generation, "origin_generation": payload.get("transitionGeneration"), "player_session_id": source_player_session_id, "origin_monotonic_ns": payload.get("monotonicNs")},
                            )

                            async def run_player_transition(
                                direction_name=direction_name,
                                event_type=event_type,
                                event_request_id=event_request_id,
                                payload=dict(payload),
                                transition_generation=transition_generation,
                                transition_started=transition_started,
                                button_created_at_ms=button_created_at_ms,
                                source_player_session_id=source_player_session_id,
                                is_next=is_next,
                            ):
                                try:
                                    current_path = str(payload.get("uri") or "").strip()
                                    direction = 1 if event_type == "player_next_request" else -1
                                    current_is_valid = lambda: player_transition_is_current(
                                        transition_generation,
                                        event_request_id,
                                        source_player_session_id,
                                    )
                                    if not current_path:
                                        raise RuntimeError("missing_current_uri")
                                    if not current_is_valid():
                                        if is_next:
                                            performance.event(
                                                "NEXT_REQUEST_STALE",
                                                screen=navigation.current,
                                                status="rejected",
                                                metadata={
                                                    "request_id": event_request_id,
                                                    "reason": "stale_before_sqlite",
                                                    "origin_generation": payload.get("transitionGeneration"),
                                                    "current_generation": player_transition_generation["value"],
                                                },
                                            )
                                        return

                                    query_started = performance.now()
                                    performance.event(
                                        "PYTHON_PLAYER_NAVIGATION_STARTED",
                                        screen=navigation.current,
                                        metadata={
                                            "request_id": event_request_id,
                                            "direction": direction_name,
                                            "transition_generation": transition_generation,
                                            "player_session_id": source_player_session_id,
                                        },
                                    )
                                    performance.event(
                                        "SQLITE_NEIGHBOR_QUERY_STARTED",
                                        screen=navigation.current,
                                        metadata={
                                            "request_id": event_request_id,
                                            "direction": direction_name,
                                            "transition_generation": transition_generation,
                                        },
                                    )
                                    performance.event(
                                        "NEXT_SQLITE_QUERY_STARTED" if is_next else "PREVIOUS_SQLITE_QUERY_STARTED",
                                        screen=navigation.current,
                                        metadata={
                                            "request_id": event_request_id,
                                            "transition_generation": transition_generation,
                                            "player_session_id": source_player_session_id,
                                        },
                                    )
                                    navigation_snapshot = await asyncio.to_thread(
                                        library.player_navigation,
                                        current_path,
                                    )
                                    if not current_is_valid():
                                        performance.event(
                                            "NEXT_REQUEST_STALE" if is_next else "PREVIOUS_REQUEST_STALE",
                                            screen=navigation.current,
                                            status="rejected",
                                            metadata={
                                                "request_id": event_request_id,
                                                "age_ms": max(0, int(time.time() * 1000) - button_created_at_ms),
                                                "reason": "stale_after_sqlite",
                                                "origin_generation": payload.get("transitionGeneration"),
                                                "current_generation": player_transition_generation["value"],
                                            },
                                        )
                                        performance.event(
                                            "PLAYER_NEXT_STALE_REJECTED" if is_next else "PLAYER_PREVIOUS_STALE_REJECTED",
                                            screen=navigation.current,
                                            status="rejected",
                                            metadata={
                                                "request_id": event_request_id,
                                                "reason": "stale_after_sqlite",
                                            },
                                        )
                                        return

                                    current_row = navigation_snapshot.get("current") or {}
                                    current_row_id = str(current_row.get("id") or "")
                                    current_row_anime = str(current_row.get("anime_id") or "")
                                    current_row_path = str(current_row.get("path") or "").strip()
                                    if (
                                        (payload.get("episodeId") and current_row_id and str(payload.get("episodeId")) != current_row_id)
                                        or (payload.get("animeId") and current_row_anime and str(payload.get("animeId")) != current_row_anime)
                                        or (current_row_path and current_row_path != current_path)
                                    ):
                                        performance.event(
                                            "NEXT_REQUEST_STALE",
                                            screen=navigation.current,
                                            status="rejected",
                                            metadata={
                                                "request_id": event_request_id,
                                                "age_ms": max(0, int(time.time() * 1000) - button_created_at_ms),
                                                "reason": "sqlite_current_row_mismatch",
                                            },
                                        )
                                        performance.event(
                                            "PLAYER_NEXT_STALE_REJECTED",
                                            screen=navigation.current,
                                            metadata={
                                                "request_id": event_request_id,
                                                "age_ms": max(0, int(time.time() * 1000) - button_created_at_ms),
                                                "origin_generation": payload.get("transitionGeneration"),
                                                "current_generation": player_transition_generation["value"],
                                                "reason": "sqlite_current_row_mismatch",
                                            },
                                        )
                                        return

                                    target = navigation_snapshot.get("next") if direction > 0 else navigation_snapshot.get("previous")
                                    sqlite_ms = (performance.now() - query_started) * 1000.0
                                    performance.event(
                                        "SQLITE_NEIGHBOR_QUERY_FINISHED",
                                        duration_ms=sqlite_ms,
                                        screen=navigation.current,
                                        metadata={
                                            "request_id": event_request_id,
                                            "direction": direction_name,
                                            "transition_generation": transition_generation,
                                            "has_target": bool(target),
                                        },
                                    )
                                    performance.event(
                                        "NEXT_SQLITE_QUERY_FINISHED" if is_next else "PREVIOUS_SQLITE_QUERY_FINISHED",
                                        duration_ms=sqlite_ms,
                                        screen=navigation.current,
                                        metadata={
                                            "request_id": event_request_id,
                                            "direction": direction_name,
                                            "transition_generation": transition_generation,
                                            "player_session_id": source_player_session_id,
                                            "has_target": bool(target),
                                        },
                                    )
                                    performance.event(
                                        f"player.{direction_name.lower()}.query",
                                        duration_ms=sqlite_ms,
                                        screen=navigation.current,
                                        metadata={
                                            "request_id": event_request_id,
                                            "target": (target or {}).get("path") if isinstance(target, dict) else None,
                                            "source": "player_navigation",
                                        },
                                    )
                                    if not target:
                                        if is_next:
                                            performance.event(
                                                "NEXT_TRANSITION_FAILED",
                                                screen=navigation.current,
                                                status="failed",
                                                metadata={"request_id": event_request_id, "reason": "no_target"},
                                            )
                                            cancel_player_transition("next_no_target")
                                        else:
                                        else:
                                            performance.event(
                                                "PREVIOUS_TRANSITION_FAILED",
                                                screen=navigation.current,
                                                status="failed",
                                                metadata={"request_id": event_request_id, "reason": "no_target"},
                                            )
                                            cancel_player_transition("previous_no_target")
                                            logger.warning(
                                                "[PLAYER] adjacent episode not found direction=%s request_id=%s uri=%s",
                                                direction_name,
                                                event_request_id or "-",
                                                current_path,
                                            )
                                        page.snack_bar = ft.SnackBar(ft.Text(
                                            "Não existe outro episódio local disponível nesta direção."
                                        ))
                                        page.snack_bar.open = True
                                        safe_update()
                                        return

                                    target_path = str(target.get("path") or "").strip()
                                    target_title = (
                                        target.get("episode_title")
                                        or target.get("file_name")
                                        or target.get("title")
                                        or "Episódio local"
                                    )
                                    resume_enabled = settings.get("player.resume")
                                    target_position_ms = (
                                        max(0.0, float(target.get("progress") or 0.0)) * 1000.0
                                        if resume_enabled else 0.0
                                    )
                                    target_navigation = {
                                        "can_next": bool(navigation_snapshot.get(
                                            "next_can_next" if direction > 0 else "previous_can_next"
                                        )),
                                        "can_previous": bool(navigation_snapshot.get(
                                            "next_can_previous" if direction > 0 else "previous_can_previous"
                                        )),
                                    }
                                    if not current_is_valid():
                                        performance.event(
                                            "NEXT_REQUEST_STALE" if is_next else "PREVIOUS_REQUEST_STALE",
                                            screen=navigation.current,
                                            status="rejected",
                                            metadata={
                                                "request_id": event_request_id,
                                                "age_ms": max(0, int(time.time() * 1000) - button_created_at_ms),
                                                "reason": "stale_after_target_resolution",
                                                "origin_generation": payload.get("transitionGeneration"),
                                                "current_generation": player_transition_generation["value"],
                                            },
                                        )
                                        performance.event(
                                            "PLAYER_NEXT_STALE_REJECTED" if is_next else "PLAYER_PREVIOUS_STALE_REJECTED",
                                            screen=navigation.current,
                                            status="rejected",
                                            metadata={
                                                "request_id": event_request_id,
                                                "reason": "stale_after_target_resolution",
                                            },
                                        )
                                        return

                                    pending = pending_next_transition["value"] if is_next else pending_previous_transition["value"]
                                    if (
                                        not isinstance(pending, dict)
                                        or pending.get("origin_request_id") != event_request_id
                                        or str(pending.get("player_session_id") or "") != source_player_session_id
                                        or int(pending.get("python_transition_generation") or 0) != transition_generation
                                    ):
                                        performance.event(
                                            "NEXT_REQUEST_STALE" if is_next else "PREVIOUS_REQUEST_STALE",
                                            screen=navigation.current,
                                            status="rejected",
                                            metadata={
                                                "request_id": event_request_id,
                                                "reason": "pending_context_replaced",
                                                "origin_generation": payload.get("transitionGeneration"),
                                                "current_generation": player_transition_generation["value"],
                                            },
                                        )
                                        performance.event(
                                            "PLAYER_NEXT_STALE_REJECTED" if is_next else "PLAYER_PREVIOUS_STALE_REJECTED",
                                            screen=navigation.current,
                                            status="rejected",
                                            metadata={
                                                "request_id": event_request_id,
                                                "reason": "pending_context_replaced",
                                            },
                                        )
                                        return
                                    pending["target_episode_id"] = target.get("id")
                                    pending["target_anime_id"] = target.get("anime_id")
                                    pending["target_uri"] = target_path

                                    performance.event(
                                        "TARGET_EPISODE_RESOLVED",
                                        screen=navigation.current,
                                        metadata={
                                            "request_id": event_request_id,
                                            "direction": direction_name,
                                            "episode_id": target.get("id"),
                                            "anime_id": target.get("anime_id"),
                                            "transition_generation": transition_generation,
                                            "player_session_id": source_player_session_id,
                                        },
                                    )
                                    diagnostics.record(
                                        "PLAYER_NEXT" if is_next else "PLAYER_PREVIOUS",
                                        request_id=event_request_id,
                                        source="native_player",
                                        result=target_path,
                                    )
                                    handoff_started = performance.now()
                                    performance.event(
                                        "NATIVE_PLAY_REQUEST_CREATED",
                                        screen=navigation.current,
                                        metadata={
                                            "request_id": event_request_id,
                                            "direction": direction_name,
                                            "episode_id": target.get("id"),
                                            "anime_id": target.get("anime_id"),
                                            "origin_request_id": event_request_id,
                                            "origin_created_at_ms": button_created_at_ms,
                                            "origin_transition_generation": int(payload.get("transitionGeneration") or 0),
                                            "origin_player_session_id": source_player_session_id,
                                        },
                                    )
                                    target_request_id = await start_native_player(
                                        target_path,
                                        target_title,
                                        int(target_position_ms),
                                        episode_id=target.get("id"),
                                        anime_id=target.get("anime_id"),
                                        navigation_snapshot=target_navigation,
                                        origin_request_id=event_request_id,
                                        origin_created_at_ms=button_created_at_ms,
                                        origin_transition_generation=int(payload.get("transitionGeneration") or 0),
                                        origin_player_session_id=source_player_session_id,
                                        origin_monotonic_ns=int(payload.get("monotonicNs") or 0),
                                        transition_direction=direction_name,
                                        transition_guard=current_is_valid,
                                    )
                                    pending = pending_next_transition["value"] if is_next else pending_previous_transition["value"]
                                    if isinstance(pending, dict) and pending.get("origin_request_id") == event_request_id:
                                        pending["target_request_id"] = target_request_id
                                    performance.event(
                                        f"player.{direction_name.lower()}.handoff",
                                        duration_ms=(performance.now() - handoff_started) * 1000.0,
                                        screen=navigation.current,
                                        metadata={
                                            "request_id": event_request_id,
                                            "target": target_path,
                                            "mailbox_latency_ms": max(0, int(time.time() * 1000) - button_created_at_ms),
                                        },
                                    )
                                except asyncio.CancelledError:
                                    logger.info(
                                        "[PLAYER] adjacent episode transition cancelled request_id=%s generation=%s",
                                        event_request_id or "-",
                                        transition_generation,
                                    )
                                    raise
                                except Exception as exc:
                                    performance.event(
                                        "NEXT_TRANSITION_FAILED" if is_next else "PREVIOUS_TRANSITION_FAILED",
                                        screen=navigation.current,
                                        status="failed",
                                        metadata={
                                            "request_id": event_request_id,
                                            "reason": "exception",
                                            "error": str(exc),
                                            "player_session_id": source_player_session_id,
                                        },
                                    )
                                    if not current_is_valid():
                                        return
                                    logger.exception("[PLAYER] adjacent episode launch failed")
                                    page.snack_bar = ft.SnackBar(ft.Text(
                                        "Não foi possível abrir o próximo episódio local."
                                        if direction_name == "NEXT"
                                        else "Não foi possível abrir o episódio anterior local."
                                    ))
                                    page.snack_bar.open = True
                                    safe_update()
                                    diagnostics.record(
                                        "PLAYER_NEXT_FAILED" if is_next else "PLAYER_PREVIOUS_FAILED",
                                        request_id=event_request_id,
                                        source="native_player",
                                        result="transition_failed",
                                        error=str(exc),
                                    )
                                    cancel_player_transition("next_transition_failed" if is_next else "previous_transition_failed")
                                finally:
                                    current_task = player_transition_task["task"]
                                    if (
                                        current_task is asyncio.current_task()
                                        and transition_generation == player_transition_generation["value"]
                                    ):
                                        player_transition_task["task"] = None
                                        player_transition_inflight["value"] = False
                                        performance.event(
                                            f"player.{direction_name.lower()}.request_complete",
                                            duration_ms=(performance.now() - transition_started) * 1000.0,
                                            screen=navigation.current,
                                            metadata={
                                                "request_id": event_request_id,
                                                "button_to_handoff_or_fail_ms": (performance.now() - transition_started) * 1000.0,
                                                "button_created_at_ms": button_created_at_ms,
                                            },
                                        )

                            task = asyncio.create_task(
                                run_player_transition(),
                                name=f"reiflix-player-transition-{direction_name.lower()}-{transition_generation}",
                            )
                            player_transition_task["task"] = task
                        elif event_type == 'player_error':
                            for context_direction, pending in (
                                ("NEXT", pending_next_transition["value"]),
                                ("PREVIOUS", pending_previous_transition["value"]),
                            ):
                                if isinstance(pending, dict) and event_request_id in {
                                    pending.get("origin_request_id"),
                                    pending.get("target_request_id"),
                                }:
                                    performance.event(
                                        "NEXT_TRANSITION_FAILED" if context_direction == "NEXT" else "PREVIOUS_TRANSITION_FAILED",
                                        screen=navigation.current,
                                        status="failed",
                                        metadata={
                                            "request_id": pending.get("origin_request_id"),
                                            "target_request_id": pending.get("target_request_id"),
                                            "reason": payload.get("reason") or event.get("message") or "player_error",
                                            "player_session_id": pending.get("player_session_id"),
                                        },
                                    )
                            if event_request_id and (
                                event_request_id == player_active_request_id["value"]
                                or any(
                                    isinstance(pending, dict) and event_request_id == pending.get("target_request_id")
                                    for pending in (
                                        pending_next_transition["value"],
                                        pending_previous_transition["value"],
                                    )
                                )
                            ):
                                cancel_player_transition("player_error")
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
                            exit_session_id = str(payload.get("playerSessionId") or "").strip()
                            if (
                                (
                                    player_active_request_id["value"] in (None, event_request_id)
                                    or (
                                        exit_session_id
                                        and player_active_session_id["value"] == exit_session_id
                                    )
                                )
                            ):
                                cancel_player_transition("player_exited")
                                player_active_request_id["value"] = None
                                player_session_active["value"] = False
                                player_active_session_id["value"] = None
                                player_active_episode_id["value"] = None
                                player_active_anime_id["value"] = None
                                player_active_uri["value"] = None
                            else:
                                diagnostics.record(
                                    "PLAYER_EXIT_IGNORED",
                                    request_id=event_request_id,
                                    source="native_player",
                                    result="stale_player_session",
                                )
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
                                        episode_id=payload.get("episodeId"),
                                        event_created_at=event.get('createdAt') or event.get('timestamp'),
                                    )
                                except (TypeError, ValueError):
                                    exit_updated = False
                            performance.event("player.exited", screen=navigation.current,
                                              metadata={"request_id": event_request_id, "episode_id": payload.get("episodeId"),
                                                        "media_identity": payload.get("mediaId"), "position_ms": payload.get("positionMs"),
                                                        "duration_ms": payload.get("durationMs")})
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
                                error_message = event.get('message') or 'Não foi possível abrir o seletor de pastas do Android. Tente novamente.'
                                logger.error(
                                    "[SAF] native error request_id=%s stage=%s code=%s status=%s has_tree_uri=%s",
                                    event_request_id or "-",
                                    payload.get('stage') or "-",
                                    payload.get('code') or "-",
                                    payload.get('status') or "-",
                                    bool(tree_uri),
                                )
                                if tree_uri and tree_uri in pending_folder_removals:
                                    pending_folder_removals.discard(tree_uri)
                                    page.snack_bar=ft.SnackBar(ft.Text(event.get('message', 'Não foi possível liberar a pasta.'))); page.snack_bar.open=True; safe_update()
                                    refresh_settings_if_active()
                                    continue
                                page.snack_bar=ft.SnackBar(ft.Text(error_message)); page.snack_bar.open=True; safe_update()
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
                                    message = 'Este dispositivo não oferece suporte ao Gerenciador de Credenciais usado pelo ReiAnix.'
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
                                safe_update()

                        if operation_key:
                            processed_native_operations.add(operation_key)
                            if len(processed_native_operations) > 1024:
                                for _ in range(len(processed_native_operations) - 768):
                                    processed_native_operations.pop()
                        logger.info(
                            "[ANDROID] EVENT_PROCESSED eventId=%s requestId=%s type=%s state=%s",
                            event_id,
                            event_request_id or "-",
                            event_type or "-",
                            operation_state or "-",
                        )
                        if event_id:
                            claimed = store.claim_native_event(event_id)
                            if not claimed:
                                logger.info("[ANDROID] EVENT_DEDUPE_LEDGER_ALREADY_CLAIMED eventId=%s", event_id)
                    except Exception as exc:
                        if event_id:
                            failed_event_ids.add(str(event_id))
                        logger.exception(
                            "[ANDROID] EVENT_PROCESS_FAILED eventId=%s requestId=%s type=%s",
                            event_id or "-",
                            event_request_id if 'event_request_id' in locals() else "-",
                            event_type if 'event_type' in locals() else "-",
                        )
                # NativeMailbox retains the atomically claimed batch until this
                # point, after SQLite/UI handling has completed. A process restart
                # before acknowledgement replays the complete batch safely.
                bridge.requeue_event_ids(failed_event_ids)
                bridge.acknowledge()
                performance.event(
                    "android.mailbox.drain",
                    duration_ms=(performance.now() - mailbox_started) * 1000.0,
                    metadata={
                        "backlog_before": mailbox_backlog_before,
                        "events_drained": len(events),
                        "events_failed": len(failed_event_ids),
                        "backlog_after": bridge.pending_count(),
                    },
                )
                if events:
                    poll_interval = 0.08 if player_session_active["value"] else 0.2
                elif player_session_active["value"]:
                    poll_interval = min(0.25, max(0.08, poll_interval * 1.25))
                else:
                    poll_interval = min(1.0, max(0.2, poll_interval * 1.5))
            except Exception as exc:
                logger.exception("[ANDROID] NATIVE_MAILBOX_LOOP_FAILED")
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
    # Runtime navigation is deliberately process-local. The NavigationController
    # was initialized at Home and no persisted route is restored here.
    # MainActivity publishes the authoritative SAF grant inventory from
    # onResume. There is intentionally no Python -> reiflix://native startup
    # verification call.
    first_render_started = performance.now()
    render_current()
    performance.event("startup.first_render", duration_ms=(performance.now()-first_render_started)*1000.0,
                      screen=navigation.current)
    performance.event("startup.interactive", duration_ms=(performance.now()-startup_started)*1000.0,
                      screen=navigation.current)
    persist_navigation_state()

if __name__ == "__main__":
    ft.run(main)
