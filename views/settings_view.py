"""Settings UI for the local Rei-flix library.

The view receives service callbacks from ``main`` and keeps SQL/business rules
out of Flet controls.  It intentionally reads only compact store projections.
"""
from __future__ import annotations

import json

import flet as ft
from core.ui import ACCENT, BACKGROUND, PAGE_PADDING, RADIUS, SURFACE, TEXT, TEXT_MUTED, section_title


class SettingsView:
    @staticmethod
    def build(page, store, library, on_back, on_catalog_changed, on_add_folder,
              on_refresh_library, on_login, on_logout, account, account_state="disconnected"):
        status = ft.Text("", color="#9DA3B4", size=12)
        busy = {"folder": False, "scan": False, "login": False, "logout": False, "cache": False}

        def notice(message, error=False):
            status.value = message
            status.color = "#FFB4AB" if error else "#9DA3B4"
            page.update()

        def section(title, icon, content):
            return ft.Container(
                content=ft.Column([
                    section_title(title, icon),
                    content,
                ], spacing=10), padding=14, bgcolor=SURFACE, border_radius=RADIUS,
            )

        def confirm(title, body, action_label, action):
            dialog = ft.AlertDialog(
                modal=True, title=ft.Text(title), content=ft.Text(body),
                actions=[ft.TextButton("Cancelar", on_click=lambda _: page.close(dialog)),
                         ft.FilledButton(action_label, on_click=lambda _: (page.close(dialog), action()))],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            page.open(dialog)

        folders = store.folders()
        summary = store.library_summary()
        folder_lines = []
        for folder in folders:
            # SAF URI values are capability references, not meaningful names to expose.
            name = folder.get("name") or "Pasta configurada"
            description = "Pasta SAF autorizada" if folder.get("kind") == "saf" else "Pasta local configurada"
            if folder.get("authorization") != "granted":
                description = "Acesso precisa ser verificado"
            folder_lines.append(ft.Column([
                ft.Text(name, color=TEXT, size=13, weight=ft.FontWeight.BOLD, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(description, color=TEXT_MUTED, size=11),
            ], spacing=2))
        if not folder_lines:
            folder_lines = [ft.Text("Nenhuma pasta foi selecionada.", color="#AAA7B6", size=12)]

        add_folder_button = ft.OutlinedButton("Adicionar pasta", icon=ft.Icons.CREATE_NEW_FOLDER)
        async def add_folder(_):
            if busy["folder"] or busy["scan"]:
                return
            busy["folder"] = True
            add_folder_button.disabled = True
            try:
                await on_add_folder()
                notice("Abrindo seletor Android para autorizar a pasta…")
            except Exception:
                busy["folder"] = False
                add_folder_button.disabled = False
                notice("Não foi possível abrir o seletor de pasta.", error=True)
            page.update()
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
                page.update()
        scan_button.on_click = scan

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
        def clear_cache():
            if busy["cache"]:
                return
            busy["cache"] = True; cache_button.disabled = True; page.update()
            try:
                removed = library.clear_anilist_cache()
                notice(f"Cache AniList limpo ({removed} capa(s) removida(s)).")
            except Exception:
                notice("Não foi possível limpar o cache AniList.", error=True)
            finally:
                busy["cache"] = False; cache_button.disabled = False; page.update()
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
                # The Android/OAuth callback owns the final connected/error state.
                busy["login"] = False; account_button.disabled = False; page.update()
        account_button.on_click = login
        account_button.disabled = account_state == "connecting"
        logout_button = ft.OutlinedButton("Sair da conta", icon=ft.Icons.LOGOUT)
        def do_logout():
            if busy["logout"]:
                return
            busy["logout"] = True; logout_button.disabled = True; page.update()
            try:
                on_logout()
            except Exception:
                busy["logout"] = False; logout_button.disabled = False
                notice("Não foi possível sair da conta.", error=True)
        def ask_logout(_):
            confirm("Sair da conta Google?", "A sessão local será removida. Biblioteca, favoritos, progresso e histórico não serão alterados.", "Sair", do_logout)
        logout_button.on_click = ask_logout
        state_labels = {"connecting": "Conectando…", "connected": "Conectada", "error": "Erro ao conectar", "disconnecting": "Saindo…", "configuration_required": "Configuração necessária"}
        account_status = state_labels.get(account_state, "Conectada" if connected else "Não conectada")

        last = store.last_scan()
        diagnostic = "Ainda não houve varredura."
        if last:
            errors = json.loads(last["errors"] or "[]")
            diagnostic = f"Última varredura: {last['videos']} vídeos, {last['animes']} animes, {last['episodes']} episódios."
            if errors:
                diagnostic += " Há itens que precisam de atenção."

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
                ft.Row([add_folder_button, scan_button], wrap=True),
                ft.Text(diagnostic, color="#AAA7B6", size=11),
            ], spacing=8)),
            section("REPRODUÇÃO", ft.Icons.PLAY_CIRCLE_OUTLINE, ft.Column([
                resume_switch,
                ft.Text("O próximo episódio continua sendo uma ação explícita no player local.", color="#AAA7B6", size=11),
            ], spacing=4)),
            section("APARÊNCIA", ft.Icons.DARK_MODE_OUTLINED, ft.Text("Tema escuro Rei-flix ativo.", color="#C7C5D0", size=12)),
            section("DADOS", ft.Icons.STORAGE_OUTLINED, ft.Column([
                ft.Text(f"{summary['folders']} pasta(s) • {summary['history']} item(ns) no histórico", color="#C7C5D0", size=12),
                cache_button,
                ft.Text("Limpar cache não remove associações AniList confirmadas nem arquivos da biblioteca.", color="#AAA7B6", size=11),
            ], spacing=8)),
            section("SOBRE", ft.Icons.INFO_OUTLINE, ft.Column([
                ft.Text("Rei-flix Local 0.2.0", color="#F7F5FA", size=13, weight=ft.FontWeight.BOLD),
                ft.Text("Biblioteca local com SQLite, Android SAF e player nativo. Vídeos nunca são enviados.", color="#AAA7B6", size=11),
            ], spacing=4)),
            status,
        ], spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)
        return ft.Container(padding=PAGE_PADDING, bgcolor=BACKGROUND, content=content)
