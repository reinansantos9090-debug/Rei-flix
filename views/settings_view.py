"""Settings UI for the local Rei-flix library.

The view receives service callbacks from ``main`` and keeps SQL/business rules
out of Flet controls.  It intentionally reads only compact store projections.
"""
from __future__ import annotations

import json
import logging

import flet as ft

logger = logging.getLogger("reiflix.settings")
from core.ui import ACCENT, BACKGROUND, PAGE_PADDING, RADIUS, SURFACE, TEXT, TEXT_MUTED, section_title


class SettingsView:
    @staticmethod
    def build(page, store, library, on_back, on_catalog_changed, on_add_folder, on_remove_folder,
              on_refresh_library, on_request_video_access, on_open_broad_storage, on_login, on_logout, account, account_state="disconnected",
              folder_selection_pending=lambda: False, on_resolve_match=lambda _lookup, _id: None,
              on_create_backup=None, on_restore_backup=None, storage_snapshot=None, scan_snapshot=None):
        status = ft.Text("", color="#9DA3B4", size=12)
        ui_alive = [True]
        def safe_update():
            if not ui_alive[0]:
                return
            try:
                page.update()
            except Exception as exc:
                logger.warning("[FLET] Settings update failed: %s", exc)
        try:
            page.on_disconnect = lambda _e: ui_alive.__setitem__(0, False)
        except Exception as exc:
            logger.warning("[FLET] Settings on_disconnect hook unavailable: %s", exc)
        busy = {"folder": False, "scan": False, "login": False, "logout": False, "cache": False, "permission": False, "backup": False, "restore": False}

        def notice(message, error=False):
            status.value = message
            status.color = "#FFB4AB" if error else "#9DA3B4"
            safe_update()

        def section(title, icon, content):
            return ft.Container(
                content=ft.Column([
                    section_title(title, icon),
                    content,
                ], spacing=10), padding=14, bgcolor=SURFACE, border_radius=RADIUS,
            )

        def confirm(title, body, action_label, action):
            async def run_action(_event):
                page.pop_dialog()
                result = action()
                if hasattr(result, "__await__"):
                    await result
            dialog = ft.AlertDialog(
                modal=True, title=ft.Text(title), content=ft.Text(body),
                actions=[ft.TextButton("Cancelar", on_click=lambda _: page.pop_dialog()),
                         ft.FilledButton(action_label, on_click=run_action)],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            page.show_dialog(dialog)
            safe_update()

        folders = store.folders()
        summary = store.library_summary()
        statistics = library.library_statistics()
        snapshot = storage_snapshot or {}
        scan = scan_snapshot or {}
        media_state = str(getattr(storage_snapshot, "media_read_state", snapshot.get("mediaReadState", "denied"))).casefold()
        broad_state = str(getattr(storage_snapshot, "broad_storage_state", snapshot.get("broadStorageState", "unavailable"))).casefold()
        saf_roots = tuple(getattr(storage_snapshot, "saf_roots", snapshot.get("safRoots", ())) or ())
        volumes = tuple(getattr(storage_snapshot, "removable_volumes", snapshot.get("removableVolumes", ())) or ())
        broad_granted = broad_state == "available"
        media_granted = media_state in {"partial", "full"}
        media_partial = media_state == "partial"
        media_full = media_state == "full"

        def show_video_permission_dialog(_=None):
            if busy["permission"]:
                return
            dialog = None
            async def allow(_event):
                busy["permission"] = True
                try:
                    page.pop_dialog()
                    await on_request_video_access()
                    notice("Solicitação de permissão para ler vídeos enviada ao Android…")
                except Exception:
                    notice("Não foi possível solicitar a permissão para ler vídeos.", error=True)
                finally:
                    busy["permission"] = False
                    safe_update()
            dialog = ft.AlertDialog(
                modal=True,
                icon=ft.Icon(ft.Icons.SETTINGS_OUTLINED, size=40),
                title=ft.Text("Permissão necessária"),
                content=ft.Text("Permissão para ler vídeos"),
                actions=[
                    ft.TextButton("CANCELAR", on_click=lambda _: page.pop_dialog()),
                    ft.FilledButton("PERMITIR", on_click=allow),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            page.show_dialog(dialog)
            safe_update()

        def show_broad_storage_dialog(_=None):
            if busy["permission"]:
                return
            dialog = None
            async def allow(_event):
                busy["permission"] = True
                try:
                    page.pop_dialog()
                    await on_open_broad_storage()
                    notice("Abrindo as configurações do Android para permitir o acesso ao armazenamento…")
                except Exception:
                    notice("Não foi possível abrir a configuração de armazenamento.", error=True)
                finally:
                    busy["permission"] = False
                    safe_update()
            dialog = ft.AlertDialog(
                modal=True,
                icon=ft.Icon(ft.Icons.FOLDER_OPEN_OUTLINED, size=40),
                title=ft.Text("Permissão necessária"),
                content=ft.Column([
                    ft.Text("Acesso amplo ao armazenamento compartilhado para procurar vídeos em várias pastas locais."),
                    ft.Text("Este acesso é opcional: o Rei-Flix também pode usar os vídeos do dispositivo e pastas específicas escolhidas por você.", color=TEXT_MUTED, size=11),
                ], spacing=6),
                actions=[
                    ft.TextButton("CANCELAR", on_click=lambda _: page.pop_dialog()),
                    ft.FilledButton("PERMITIR", on_click=allow),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            page.show_dialog(dialog)
            safe_update()

        pending_matches = store.pending_matches()
        folder_lines = []
        for folder in folders:
            name = folder.get("name") or "Pasta configurada"
            granted = folder.get("authorization") == "granted"
            authorization = str(folder.get("authorization") or "").casefold()
            if folder.get("kind") == "saf" and granted:
                description = "Pasta SAF autorizada"
            elif folder.get("kind") == "saf" and authorization == "unavailable":
                description = "Pasta SAF salva, mas o provedor está indisponível"
            elif folder.get("kind") != "saf" and granted:
                description = "Pasta local configurada"
            else:
                description = "Acesso precisa ser verificado"
            error = str(folder.get("last_error") or "").strip()

            def ask_remove(reference, display_name):
                async def remove():
                    result = on_remove_folder(reference)
                    if hasattr(result, "__await__"):
                        await result
                confirm(
                    "Remover pasta da biblioteca?",
                    f'"{display_name}" será removida das pastas configuradas. Os arquivos já indexados serão mantidos no histórico, mas ficarão indisponíveis até a pasta ser adicionada novamente.',
                    "Remover",
                    remove,
                )

            folder_info = ft.Column([
                ft.Text(name, color=TEXT, size=13, weight=ft.FontWeight.BOLD, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(description, color=TEXT_MUTED, size=11),
                ft.Text(error, color="#FFB4AB", size=10, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS, visible=bool(error)),
            ], spacing=2, expand=True)
            folder_lines.append(ft.Row([
                folder_info,
                ft.OutlinedButton(
                    "Remover",
                    icon=ft.Icons.DELETE_OUTLINE,
                    on_click=lambda _, ref=folder["path"], label=name: ask_remove(ref, label),
                ),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER))
        if not folder_lines:
            folder_lines = [ft.Text("Nenhuma pasta foi selecionada.", color="#AAA7B6", size=12)]

        add_folder_button = ft.OutlinedButton("Adicionar pasta", icon=ft.Icons.CREATE_NEW_FOLDER,
                                              disabled=bool(folder_selection_pending()))
        async def add_folder(_):
            if busy["folder"] or busy["scan"] or folder_selection_pending():
                return
            busy["folder"] = True
            add_folder_button.disabled = True
            try:
                await on_add_folder()
                notice("Abrindo seletor Android para autorizar a pasta…")
            except Exception:
                notice("Não foi possível abrir o seletor de pasta.", error=True)
            finally:
                busy["folder"] = False
                add_folder_button.disabled = bool(folder_selection_pending())
                safe_update()
        add_folder_button.on_click = add_folder

        scan_button = ft.FilledButton("Atualizar biblioteca", icon=ft.Icons.REFRESH)
        async def scan(_):
            if busy["scan"]:
                return
            busy["scan"] = True; scan_button.disabled = True; notice("Verificando biblioteca local…")
            waiting_native_result = False
            try:
                message, waiting_native_result = await on_refresh_library()
                notice(message)
                on_catalog_changed()
            except Exception:
                notice("Não foi possível atualizar a biblioteca.", error=True)
            finally:
                busy["scan"] = waiting_native_result
                scan_button.disabled = waiting_native_result
                safe_update()
        scan_button.on_click = scan

        video_permission_button = ft.FilledButton(
            "Solicitar leitura de vídeos" if not media_granted else ("Rever acesso parcial" if media_partial else "Permissão de vídeos concedida"),
            icon=ft.Icons.VIDEO_LIBRARY_OUTLINED,
            disabled=media_full,
            on_click=show_video_permission_dialog,
        )
        broad_storage_button = ft.OutlinedButton(
            "Permitir acesso ao armazenamento" if not broad_granted else "Acesso ao armazenamento concedido",
            icon=ft.Icons.FOLDER_OPEN_OUTLINED,
            disabled=broad_granted,
            on_click=show_broad_storage_dialog,
        )
        if media_granted:
            if media_partial:
                media_permission_text = "⚠ Permissão de vídeos: Acesso parcial (alguns vídeos selecionados pelo usuário)"
                media_permission_color = "#FFD54F"
            else:
                media_permission_text = "✓ Permissão para ler vídeos concedida"
                media_permission_color = "#9FE3B1"
        else:
            media_permission_text = "⚠ Permissão para ler vídeos ainda não concedida"
            media_permission_color = "#FFB4AB"

        media_label = {
            "full": "COMPLETO — acesso aos vídeos confirmado pelo Android",
            "partial": "PARCIAL — o Android liberou apenas itens selecionados",
            "denied": "NEGADO — o Android não liberou leitura de vídeos",
        }.get(media_state, "DESCONHECIDO")
        broad_label = "DISPONÍVEL — acesso amplo confirmado pelo Android" if broad_granted else "INDISPONÍVEL — acesso amplo não concedido"
        saf_label = f"PASTAS AUTORIZADAS — {len(saf_roots)}" if saf_roots else "SEM PASTA SAF AUTORIZADA"
        scan_state_label = str(scan.get("state") or "IDLE")
        scan_source = str(scan.get("source") or "—")
        scan_volume = str(scan.get("volume") or "—")
        scan_found = int(scan.get("found") or 0)
        scan_error = str(scan.get("error") or "")
        permission_lines = [
            ft.Text(f"MEDIASTORE: {media_label}", color="#9FE3B1" if media_granted else "#FFB4AB", size=11),
            ft.Text(f"SAF: {saf_label}", color="#9FE3B1" if saf_roots else "#AAA7B6", size=11),
            ft.Text(f"BROAD STORAGE: {broad_label}", color="#9FE3B1" if broad_granted else "#AAA7B6", size=11),
            ft.Row([video_permission_button, broad_storage_button], wrap=True, spacing=8, run_spacing=8),
            ft.Text(
                "Os estados acima vêm do snapshot atual do Android; as linhas do SQLite são apenas histórico/configuração.",
                color="#AAA7B6", size=10,
            ),
        ]
        diagnostics_content = ft.Column([
            ft.Text(f"SCAN: {scan_state_label}", color=TEXT, size=12, weight=ft.FontWeight.BOLD),
            ft.Text(f"Fonte: {scan_source} • Volume: {scan_volume}", color=TEXT_MUTED, size=11),
            ft.Text(f"Encontrados: {scan_found} • Diretórios: {int(scan.get('directories') or 0)} • Arquivos: {int(scan.get('files') or 0)}", color=TEXT_MUTED, size=11),
            ft.Text(f"Volumes removíveis: {len(volumes)}", color=TEXT_MUTED, size=11),
            ft.Text(f"Erro: {scan_error}" if scan_error else "Erro: nenhum", color="#FFB4AB" if scan_error else TEXT_MUTED, size=11),
            ft.Text(f"Timestamp: {scan.get('timestamp') or '—'}", color=TEXT_MUTED, size=10),
        ], spacing=4)

        resume_switch = ft.Switch(label="Continuar do progresso salvo", value=store.get_preference("resume_playback", "true") == "true")
        def save_resume(event):
            try:
                store.set_preference("resume_playback", "true" if event.control.value else "false")
                notice("Preferência de reprodução salva.")
            except Exception:
                event.control.value = not event.control.value
                notice("Não foi possível salvar a preferência.", error=True)
        resume_switch.on_change = save_resume

        cache_button = ft.OutlinedButton("Limpar cache AniList", icon=ft.Icons.DELETE_SWEEP_OUTLINED)

        backup_button = ft.OutlinedButton("Criar backup local", icon=ft.Icons.BACKUP_OUTLINED)
        restore_button = ft.OutlinedButton("Restaurar backup", icon=ft.Icons.RESTORE_OUTLINED)
        def create_backup():
            if busy["backup"] or not on_create_backup:
                return
            busy["backup"] = True
            backup_button.disabled = True
            safe_update()
            try:
                path = on_create_backup()
                notice(f"Backup criado: {str(path).rsplit('/', 1)[-1]}")
            except Exception:
                notice("Não foi possível criar o backup local.", error=True)
            finally:
                busy["backup"] = False
                backup_button.disabled = False
                safe_update()
        def ask_create_backup(_):
            confirm("Criar backup local?", "Será salva uma cópia offline da biblioteca SQLite e do cache de artwork gerenciado pelo Rei-Flix.", "Criar", create_backup)
        backup_button.on_click = ask_create_backup

        def restore_backup():
            if busy["restore"] or not on_restore_backup:
                return
            busy["restore"] = True
            restore_button.disabled = True
            safe_update()
            try:
                path = on_restore_backup()
                on_catalog_changed()
                notice(f"Backup restaurado: {str(path).rsplit('/', 1)[-1]}")
            except Exception:
                notice("Não foi possível restaurar o backup local.", error=True)
            finally:
                busy["restore"] = False
                restore_button.disabled = False
                safe_update()
        def ask_restore_backup(_):
            latest = store.latest_backup()
            if not latest:
                notice("Nenhum backup local encontrado.", error=True)
                return
            confirm("Restaurar backup local?", "A biblioteca atual será substituída pela cópia salva. O processo só substitui o banco depois da validação do backup.", "Restaurar", restore_backup)
        restore_button.on_click = ask_restore_backup
        def clear_cache():
            if busy["cache"]:
                return
            busy["cache"] = True; cache_button.disabled = True; safe_update()
            try:
                removed = library.clear_anilist_cache()
                notice(f"Cache AniList limpo ({removed} capa(s) removida(s)).")
            except Exception:
                notice("Não foi possível limpar o cache AniList.", error=True)
            finally:
                busy["cache"] = False; cache_button.disabled = False; safe_update()
        def ask_clear_cache(_):
            confirm("Limpar cache AniList?", "Metadados e capas temporárias serão atualizados na próxima varredura. Sua biblioteca, favoritos e progresso serão preservados.", "Limpar", clear_cache)
        cache_button.on_click = ask_clear_cache

        connected = bool(account.get("email"))
        account_text = account.get("name") or account.get("email") or "Você não está conectado."
        account_details = account.get("email", "")
        google_needs_configuration = account_state == "configuration_required"
        account_button = ft.FilledButton(
            "Configurar login Google" if google_needs_configuration else "Entrar com Google",
            icon=ft.Icons.SETTINGS if google_needs_configuration else ft.Icons.LOGIN,
        )
        async def login(_):
            if busy["login"]:
                return
            busy["login"] = True; account_button.disabled = True; notice("Conectando à conta Google…")
            try:
                await on_login()
            except Exception:
                notice("Não foi possível iniciar o login Google.", error=True)
            finally:
                busy["login"] = False; account_button.disabled = False; safe_update()
        account_button.on_click = login
        account_button.disabled = account_state in {"connecting", "awaiting_google"}
        logout_button = ft.OutlinedButton("Sair da conta", icon=ft.Icons.LOGOUT)
        def do_logout():
            if busy["logout"]:
                return
            busy["logout"] = True; logout_button.disabled = True; safe_update()
            try:
                on_logout()
            except Exception:
                busy["logout"] = False; logout_button.disabled = False
                notice("Não foi possível sair da conta.", error=True)
        def ask_logout(_):
            confirm("Sair da conta Google?", "A sessão local será removida. Biblioteca, favoritos, progresso e histórico não serão alterados.", "Sair", do_logout)
        logout_button.on_click = ask_logout
        state_labels = {"connecting": "Conectando…", "awaiting_google": "Aguardando Google…", "connected": "Conectada", "error": "Erro ao conectar", "disconnecting": "Saindo…", "configuration_required": "Configuração necessária"}
        account_status = state_labels.get(account_state, "Conectada" if connected else "Não conectada")

        pending_content = []
        if pending_matches:
            pending_content.append(ft.Text(
                f"{len(pending_matches)} título(s) precisam de confirmação antes de receber metadados AniList.",
                color=TEXT_MUTED, size=11,
            ))
            for pending in pending_matches:
                buttons = []
                for candidate in (pending.get("candidates") or [])[:5]:
                    title = candidate.get("title") or {}
                    label = title.get("english") or title.get("romaji") or title.get("native") or f"AniList #{candidate.get('id')}"
                    score = int(round(float(candidate.get("match_score") or 0) * 100))
                    buttons.append(ft.OutlinedButton(
                        f"{label} • {score}%",
                        on_click=lambda _, lookup=pending["lookup_title"], aid=candidate.get("id"): on_resolve_match(lookup, aid),
                    ))
                pending_content.append(ft.Container(
                    content=ft.Column([
                        ft.Text(pending["display_title"], color=TEXT, size=12, weight=ft.FontWeight.BOLD),
                        ft.Row(buttons, wrap=True, spacing=6, run_spacing=6),
                    ], spacing=5),
                    padding=10, bgcolor="#252836", border_radius=10,
                ))
        else:
            pending_content.append(ft.Text("Nenhum título aguarda confirmação AniList.", color=TEXT_MUTED, size=11))

        last = store.last_scan()
        diagnostic = "Ainda não houve varredura."
        if last:
            try:
                errors = json.loads(last["errors"] or "[]")
            except (TypeError, json.JSONDecodeError):
                errors = ["diagnóstico inválido"]
            diagnostic = f"Última varredura: {last['videos']} vídeos, {last['animes']} animes, {last['episodes']} episódios."
            if errors:
                diagnostic += " Há itens que precisam de atenção."
            if last.get("status"):
                diagnostic += f" Status: {last['status']}."

        stats_text = (
            f"{statistics['animes']} animes • {statistics['episodes_available']}/{statistics['episodes']} episódios disponíveis\n"
            f"{statistics['animes_completed']} concluídos • {statistics['animes_in_progress']} em andamento • {statistics['animes_not_started']} não iniciados\n"
            f"{statistics['episodes_watched']} episódios concluídos • {statistics['favorites']} favoritos • {statistics['pinned']} fixados\n"
            f"{statistics['tags']} etiquetas distintas • {statistics['notes']} notas pessoais\n"
            f"{statistics['without_metadata']} sem metadata • {statistics['without_cover']} sem capa"
        )

        account_content = ft.Row([
            ft.Image(src=account.get("picture"), width=42, height=42, border_radius=21) if account.get("picture") else ft.Icon(ft.Icons.ACCOUNT_CIRCLE_OUTLINED, size=42, color="#C7C5D0"),
            ft.Column([ft.Text(account_text, color="#F7F5FA", size=13, weight=ft.FontWeight.BOLD), ft.Text(f"{account_status}{' • ' + account_details if account_details else ''}", color="#AAA7B6", size=11)], spacing=2, expand=True),
            logout_button if connected else account_button,
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER)
        content = ft.Column([
            ft.Row([ft.IconButton(icon=ft.Icons.ARROW_BACK, icon_color=ft.Colors.WHITE, tooltip="Voltar", on_click=lambda _: on_back()), ft.Text("Configurações", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE)]),
            section("CONTA", ft.Icons.PERSON_OUTLINE, account_content),
            section("BIBLIOTECA", ft.Icons.VIDEO_LIBRARY_OUTLINED, ft.Column(folder_lines + [
                ft.Text(f"{summary['animes']} animes • {summary['episodes']} episódios locais", color="#C7C5D0", size=12),
                ft.Column(permission_lines, spacing=6),
                ft.Row([add_folder_button, scan_button], wrap=True),
                ft.Text(diagnostic, color="#AAA7B6", size=11),
            ], spacing=8)),
            section("DIAGNÓSTICOS DE ARMAZENAMENTO", ft.Icons.DIAGNOSTICS_OUTLINED, diagnostics_content),
            section("ESTATÍSTICAS OFFLINE", ft.Icons.INSIGHTS_OUTLINED, ft.Column([
                ft.Text(stats_text, color="#C7C5D0", size=12),
                ft.Text("“Registrado” representa a posição atual salva nos episódios disponíveis; não é tempo histórico assistido.", color=TEXT_MUTED, size=10),
                ft.Text(diagnostic, color="#AAA7B6", size=11),
            ], spacing=7)),
            section("REPRODUÇÃO", ft.Icons.PLAY_CIRCLE_OUTLINE, ft.Column([
                resume_switch,
                ft.Text("O próximo episódio continua sendo uma ação explícita no player local.", color="#AAA7B6", size=11),
            ], spacing=4)),
            section("APARÊNCIA", ft.Icons.DARK_MODE_OUTLINED, ft.Text("Tema escuro Rei-flix ativo.", color="#C7C5D0", size=12)),
            section("ANILIST", ft.Icons.MANAGE_SEARCH_OUTLINED, ft.Column(pending_content + [
                ft.Text("Associações confirmadas ficam salvas localmente e serão reutilizadas nas próximas varreduras.", color=TEXT_MUTED, size=11),
            ], spacing=8)),
            section("DADOS", ft.Icons.STORAGE_OUTLINED, ft.Column([
                ft.Text(f"{summary['folders']} pasta(s) • {summary['history']} item(ns) no histórico", color="#C7C5D0", size=12),
                ft.Row([backup_button, restore_button], wrap=True, spacing=8),
                cache_button,
                ft.Text("Backup local protege SQLite e artwork gerenciado; restaurar não depende de internet e não cria outro banco.", color="#AAA7B6", size=11),
                ft.Text("Limpar cache não remove associações AniList confirmadas nem arquivos da biblioteca.", color="#AAA7B6", size=11),
            ], spacing=8)),
            section("SOBRE", ft.Icons.INFO_OUTLINE, ft.Column([
                ft.Text("Rei-flix Local 0.2.0", color="#F7F5FA", size=13, weight=ft.FontWeight.BOLD),
                ft.Text("Biblioteca local com SQLite, Android SAF e player nativo. Vídeos nunca são enviados.", color="#AAA7B6", size=11),
            ], spacing=4)),
            status,
        ], spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)
        return ft.Container(padding=PAGE_PADDING, bgcolor=BACKGROUND, content=content)
