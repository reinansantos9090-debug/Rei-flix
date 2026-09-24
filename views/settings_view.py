"""Settings Center 2.0 for Rei-Flix.

The view is a thin UI layer. Persistent values live in the existing
LibraryStore preferences table through SettingsStore; storage, scanner,
metadata, artwork and player remain owned by their existing services.
"""
from __future__ import annotations

import inspect
import logging

import flet as ft

from core.storage_access import normalize_storage_snapshot
from core.settings import SettingsStore, SettingsValidationError
from core.ui import BACKGROUND, PAGE_PADDING, RADIUS, SURFACE, TEXT, TEXT_MUTED, section_title

logger = logging.getLogger("reiflix.settings")


class SettingsView:
    @staticmethod
    def build(
        page, store, library, on_back, on_catalog_changed, on_add_folder,
        on_remove_folder, on_refresh_library, on_request_video_access,
        on_open_broad_storage, on_login, on_logout, account,
        account_state="disconnected", folder_selection_pending=lambda: False,
        on_resolve_match=lambda _lookup, _id: None, storage_snapshot=None,
        scan_snapshot=None, settings: SettingsStore | None = None,
    ):
        settings = settings or SettingsStore(store)
        busy = {"scan": False, "folder": False, "permission": False, "cache": False}
        status = ft.Text("", size=12, color=TEXT_MUTED)
        search = ft.TextField(
            hint_text="Pesquisar configurações…",
            prefix_icon=ft.Icons.SEARCH,
            dense=True,
            border_radius=12,
        )
        sections_host = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)

        def safe_update():
            try:
                page.update()
            except Exception:
                logger.debug("settings update skipped")

        def notice(message: str, error: bool = False):
            status.value = message
            status.color = "#FFB4AB" if error else TEXT_MUTED
            safe_update()

        def confirm(title, body, action_label, action):
            if not settings.get("app.confirm_destructive"):
                result = action()
                if inspect.isawaitable(result):
                    page.run_task(lambda: result)
                return

            async def run(_):
                page.pop_dialog()
                try:
                    result = action()
                    if inspect.isawaitable(result):
                        await result
                except Exception:
                    logger.exception("settings action failed")
                    notice("Não foi possível concluir a operação.", True)
                finally:
                    safe_update()

            page.show_dialog(ft.AlertDialog(
                modal=True,
                title=ft.Text(title),
                content=ft.Text(body),
                actions=[
                    ft.TextButton("Cancelar", on_click=lambda _: page.pop_dialog()),
                    ft.FilledButton(action_label, on_click=run),
                ],
            ))
            safe_update()

        def save(key, value, control=None):
            try:
                normalized = settings.set(key, value)
                if control is not None:
                    control.value = normalized
                notice("Configuração salva.")
                return True
            except (SettingsValidationError, ValueError, TypeError):
                logger.exception("invalid setting %s", key)
                notice("Valor inválido para esta configuração.", True)
                return False
            except Exception:
                logger.exception("setting persistence failed: %s", key)
                notice("Não foi possível salvar a configuração.", True)
                return False

        def row(key, label, description, kind="bool", choices=None, labels=None):
            value = settings.get(key)
            if kind == "bool":
                control = ft.Switch(
                    value=bool(value),
                    on_change=lambda e, k=key: save(k, e.control.value, e.control),
                )
            else:
                display = labels.get(value, str(value)) if labels else str(value)
                async def choose(_):
                    opts = tuple(choices or ())
                    buttons = []
                    dialog = ft.AlertDialog(modal=True, title=ft.Text(label))
                    for option in opts:
                        text = labels.get(option, str(option)) if labels else str(option)
                        async def pick(_event, selected=option):
                            save(key, selected)
                            page.pop_dialog()
                            rebuild()
                        buttons.append(ft.TextButton(text, on_click=pick))
                    dialog.content = ft.Column(buttons, tight=True)
                    page.show_dialog(dialog)
                    safe_update()
                control = ft.TextButton(display, on_click=choose)
            return ft.Container(
                content=ft.Row([
                    ft.Column([
                        ft.Text(label, color=TEXT, size=13, weight=ft.FontWeight.BOLD),
                        ft.Text(description, color=TEXT_MUTED, size=10),
                    ], spacing=2, expand=True),
                    control,
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.padding.symmetric(vertical=7),
            )

        def action_row(label, description, button_text, callback):
            return ft.Container(
                content=ft.Row([
                    ft.Column([
                        ft.Text(label, color=TEXT, size=13, weight=ft.FontWeight.BOLD),
                        ft.Text(description, color=TEXT_MUTED, size=10),
                    ], spacing=2, expand=True),
                    ft.OutlinedButton(button_text, on_click=callback),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.padding.symmetric(vertical=7),
            )

        def section(title, icon, items, tags=()):
            container = ft.Container(
                content=ft.Column([section_title(title, icon), *items], spacing=4),
                padding=14, bgcolor=SURFACE, border_radius=RADIUS,
            )
            container.data = " ".join((title, *tags)).casefold()
            return container

        section_cache = []

        def rebuild(_=None):
            nonlocal section_cache
            section_cache = build_sections()
            filter_sections()

        def filter_sections(_=None):
            query = (search.value or "").strip().casefold()
            sections_host.controls = [
                item for item in section_cache
                if not query or query in getattr(item, "data", "")
            ]
            safe_update()

        search.on_change = filter_sections

        normalized = normalize_storage_snapshot(storage_snapshot)
        snap = normalized.as_mapping()
        media_state = str(snap.get("mediaReadState", "denied")).casefold()
        broad_state = str(snap.get("broadStorageState", "unavailable")).casefold()
        saf_roots = tuple(snap.get("safRoots", ()) or ())
        volumes = tuple(snap.get("removableVolumes", ()) or ())
        scan = scan_snapshot or {}
        folders = store.folders()
        summary = store.library_summary()

        def add_folder(_):
            if busy["folder"] or folder_selection_pending():
                return
            busy["folder"] = True
            async def run():
                try:
                    await on_add_folder()
                    notice("Abrindo seletor Android…")
                except Exception:
                    logger.exception("folder picker failed")
                    notice("Não foi possível abrir o seletor de pasta.", True)
                finally:
                    busy["folder"] = False
                    safe_update()
            page.run_task(run)

        def refresh(_):
            if busy["scan"]:
                return
            busy["scan"] = True
            async def run():
                try:
                    message, waiting = await on_refresh_library()
                    notice(message)
                    on_catalog_changed()
                except Exception:
                    logger.exception("library refresh failed")
                    notice("Não foi possível atualizar a biblioteca.", True)
                finally:
                    busy["scan"] = False
                    safe_update()
            page.run_task(run)

        def permission(_):
            if busy["permission"]:
                return
            busy["permission"] = True
            async def run():
                try:
                    await on_request_video_access()
                    notice("Solicitação de permissão enviada ao Android.")
                except Exception:
                    logger.exception("video permission request failed")
                    notice("Não foi possível solicitar a permissão.", True)
                finally:
                    busy["permission"] = False
                    safe_update()
            page.run_task(run)

        def broad(_):
            if busy["permission"]:
                return
            busy["permission"] = True
            async def run():
                try:
                    await on_open_broad_storage()
                    notice("Abrindo as configurações de armazenamento do Android.")
                except Exception:
                    logger.exception("broad storage request failed")
                    notice("Não foi possível abrir o armazenamento.", True)
                finally:
                    busy["permission"] = False
                    safe_update()
            page.run_task(run)

        def clear_cache_action():
            busy["cache"] = True
            try:
                removed = library.clear_anilist_cache()
                notice(f"Cache AniList limpo ({removed} capa(s) removida(s)).")
            except Exception:
                logger.exception("clear cache failed")
                notice("Não foi possível limpar o cache AniList.", True)
            finally:
                busy["cache"] = False

        def clear_cache(_):
            confirm(
                "Limpar cache AniList?",
                "A biblioteca, progresso, favoritos, notas, pins e arquivos não serão apagados.",
                "Limpar",
                clear_cache_action,
            )

        def reset_player(_):
            confirm(
                "Restaurar Player?",
                "Somente as preferências do Player serão restauradas. Biblioteca, progresso e arquivos permanecem intactos.",
                "Restaurar",
                lambda: (settings.reset_category("player"), notice("Configurações do Player restauradas."), rebuild()),
            )

        def reset_all(_):
            def do_reset_all():
                settings.reset_all()
                apply_theme_from_settings()
                notice("Configurações restauradas.")
                rebuild()
            confirm(
                "Restaurar todas as configurações?",
                "Somente preferências do Rei-Flix serão restauradas. Biblioteca, consumo, metadata manual, artwork, arquivos e permissões não serão apagados.",
                "Restaurar",
                do_reset_all,
            )


        def language_row(key, label, description):
            value = settings.get(key)
            field = ft.TextField(
                value=value,
                hint_text="Automático",
                width=150,
                dense=True,
                on_submit=lambda e, k=key: save(k, e.control.value, e.control),
            )
            return ft.Container(
                content=ft.Row([
                    ft.Column([
                        ft.Text(label, color=TEXT, size=13, weight=ft.FontWeight.BOLD),
                        ft.Text(description, color=TEXT_MUTED, size=10),
                    ], spacing=2, expand=True),
                    field,
                    ft.OutlinedButton("Salvar", on_click=lambda _, k=key, control=field: save(k, control.value, control)),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.padding.symmetric(vertical=7),
            )

        def apply_theme_from_settings():
            page.theme_mode = {
                "system": ft.ThemeMode.SYSTEM,
                "light": ft.ThemeMode.LIGHT,
                "dark": ft.ThemeMode.DARK,
            }[settings.get("appearance.theme")]

        async def export_settings(_):
            try:
                raw = settings.export_json().encode("utf-8")
                path = await ft.FilePicker().save_file(
                    dialog_title="Exportar configurações",
                    file_name="reiflix-settings.json",
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=["json"],
                    src_bytes=raw,
                )
                if path:
                    notice("Configurações exportadas com sucesso.")
                else:
                    notice("Exportação cancelada.")
            except Exception:
                logger.exception("settings export failed")
                notice("Não foi possível exportar as configurações.", True)

        async def import_settings(_):
            try:
                files = await ft.FilePicker().pick_files(
                    dialog_title="Importar configurações",
                    allow_multiple=False,
                    with_data=True,
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=["json"],
                )
                if not files:
                    notice("Importação cancelada.")
                    return
                selected = files[0]
                raw = selected.bytes or b""
                if not raw:
                    notice("O arquivo selecionado está vazio.", True)
                    return
                result = settings.import_json(raw.decode("utf-8"))
                apply_theme_from_settings()
                on_catalog_changed()
                unknown = len(result.get("unknown", []))
                message = f"{result['imported']} configurações importadas."
                if unknown:
                    message += f" {unknown} chave(s) desconhecida(s) foram ignoradas."
                notice(message)
                rebuild()
            except (UnicodeDecodeError, SettingsValidationError):
                logger.exception("invalid settings import")
                notice("Arquivo de configurações inválido ou incompatível.", True)
            except Exception:
                logger.exception("settings import failed")
                notice("Não foi possível importar as configurações.", True)

        def build_sections():
            items = []
            connected = bool(account.get("email"))
            account_text = account.get("name") or account.get("email") or "Não conectado"
            account_status = {
                "connecting": "Conectando…", "awaiting_google": "Aguardando Google…",
                "connected": "Conectada", "error": "Erro ao conectar",
                "configuration_required": "Configuração necessária",
            }.get(account_state, "Conectada" if connected else "Não conectada")
            account_control = (
                ft.FilledButton("Entrar com Google", on_click=lambda _: page.run_task(on_login))
                if not connected else
                ft.OutlinedButton("Sair", on_click=lambda _: on_logout())
            )
            items.append(section("Conta", ft.Icons.PERSON_OUTLINE, [
                ft.Row([
                    ft.Icon(ft.Icons.ACCOUNT_CIRCLE_OUTLINED, size=42),
                    ft.Column([
                        ft.Text(account_text, color=TEXT, weight=ft.FontWeight.BOLD),
                        ft.Text(account_status, color=TEXT_MUTED, size=11),
                    ], expand=True),
                    account_control,
                ]),
            ], ("google", "login", "conta")))

            items.append(section("Geral", ft.Icons.SETTINGS_OUTLINED, [
                row("app.confirm_destructive", "Confirmar ações destrutivas", "Pede confirmação antes de ações como limpar cache e restaurar configurações."),
            ], ("geral", "confirmação", "animações")))

            def theme_changed(e):
                if save("appearance.theme", e.control.value):
                    page.theme_mode = {
                        "system": ft.ThemeMode.SYSTEM,
                        "light": ft.ThemeMode.LIGHT,
                        "dark": ft.ThemeMode.DARK,
                    }[e.control.value]
                    safe_update()

            theme = ft.Dropdown(
                value=settings.get("appearance.theme"),
                options=[
                    ft.dropdown.Option("system", "Seguir sistema"),
                    ft.dropdown.Option("light", "Claro"),
                    ft.dropdown.Option("dark", "Escuro"),
                ],
                on_change=theme_changed, dense=True, width=180,
            )
            items.append(section("Aparência", ft.Icons.DARK_MODE_OUTLINED, [
                ft.Row([
                    ft.Column([
                        ft.Text("Tema", color=TEXT, weight=ft.FontWeight.BOLD),
                        ft.Text("Aplica imediatamente sem recriar banco, scanner ou navegação.", color=TEXT_MUTED, size=10),
                    ], expand=True),
                    theme,
                ]),
            ], ("aparência", "tema", "dark", "light", "system")))

            items.append(section("Biblioteca", ft.Icons.VIDEO_LIBRARY_OUTLINED, [
                row("library.continue_watching", "Continue Watching", "Controla a preferência global para a seção quando consumida pela Home."),
                row("library.continue_watching_limit", "Limite de Continue Watching", "Limite persistido para a seção.", "enum", (5, 10, 15, 20), {5:"5",10:"10",15:"15",20:"20"}),
            ], ("biblioteca", "home", "continue watching", "grid", "organize")))

            player = [
                row("player.autoplay_next", "Autoplay do próximo episódio", "Permite avanço automático no player local."),
                row("player.resume", "Continuar reprodução", "Usa a posição de progresso já salva; desligar não apaga o progresso."),
                row("player.default_speed", "Velocidade padrão", "Aplicada quando um episódio é aberto.", "enum", (0.5,0.75,1.0,1.25,1.5,2.0), {x:f"{x:.2f}x" for x in (0.5,0.75,1.0,1.25,1.5,2.0)}),
                row("player.aspect_ratio", "Aspect ratio", "Preencher preserva a proporção e corta somente o excedente.", "enum", ("auto","fit","fill","zoom","original"), {"auto":"Auto","fit":"Ajustar","fill":"Preencher","zoom":"Zoom","original":"Original"}),
                row("player.immersive", "Modo imersivo", "Controla as barras do sistema somente no player.", "enum", ("always","landscape","never"), {"always":"Sempre","landscape":"Somente landscape","never":"Nunca"}),
                row("player.rotation", "Rotação", "Orientação do player, sem forçar o aplicativo inteiro.", "enum", ("auto","portrait","landscape"), {"auto":"Automática","portrait":"Portrait","landscape":"Landscape"}),
                row("player.pip", "Picture-in-Picture", "Permite PiP quando suportado."),
                row("player.auto_hide_seconds", "Auto-hide dos controles", "0 significa nunca.", "enum", (5,10,15,30,0), {5:"5s",10:"10s",15:"15s",30:"30s",0:"Nunca"}),
                action_row("Restaurar Player", "Volta somente as preferências do Player aos defaults.", "Restaurar", reset_player),
            ]
            items.append(section("Player", ft.Icons.PLAY_CIRCLE_OUTLINE, player, ("player","autoplay","resume","velocidade","aspect","immersive","pip","rotation")))

            items.append(section("Gestos", ft.Icons.TOUCH_APP_OUTLINED, [
                row("gestures.volume", "Gestos de volume", "Swipe vertical no lado direito ajusta o volume quando ativado."),
                row("gestures.brightness", "Gestos de brilho", "Swipe vertical no lado esquerdo ajusta o brilho quando ativado."),
                row("gestures.double_tap", "Double tap para seek", "Controla o double tap existente; swipe horizontal continua desativado."),
                row("gestures.long_press", "Pressão longa", "Controla a ação de long press existente."),
            ], ("gestos","volume","brilho","double tap","long press","swipe")))

            items.append(section("Áudio e Legendas", ft.Icons.HEADPHONES_OUTLINED, [
                language_row(
                    "audio.preferred_language",
                    "Idioma de áudio",
                    "Use uma tag BCP-47 como pt-BR, en ou ja. Se não existir no arquivo, o Media3 usa fallback seguro.",
                ),
                language_row(
                    "audio.preferred_subtitle_language",
                    "Idioma da legenda",
                    "Use uma tag BCP-47. A seleção ocorre somente entre tracks existentes no arquivo.",
                ),
                row(
                    "audio.subtitles",
                    "Legendas",
                    "Automático respeita as preferências do arquivo; Sempre tenta selecionar uma legenda; Nunca desativa a track de texto.",
                    "enum",
                    ("auto", "always", "never"),
                    {"auto": "Automático", "always": "Sempre", "never": "Nunca"},
                ),
                ft.Text("Delay global de legenda: NÃO IMPLEMENTADO. Media3 1.5.1 não expõe uma preferência persistente de offset nessa camada; nenhuma configuração falsa é exibida.", color=TEXT_MUTED, size=10),
            ], ("áudio","legenda","subtitle","audio","pt-br","en","ja")))

            items.append(section("Metadata", ft.Icons.MANAGE_SEARCH_OUTLINED, [
                ft.Text("AniList continua opcional. Associações e decisões manuais permanecem no catálogo existente.", color=TEXT_MUTED, size=11),
                ft.Text("Alterar Settings não dispara sincronização em massa.", color=TEXT_MUTED, size=10),
            ], ("metadata","anilist","matching","offline")))

            items.append(section("Artwork", ft.Icons.IMAGE_OUTLINED, [
                ft.Text("O Artwork Engine existente continua sendo a única fonte do cache de artwork.", color=TEXT_MUTED, size=11),
                action_row("Limpar cache AniList", "Remove somente o cache temporário administrado pelo catálogo.", "Limpar", clear_cache),
            ], ("artwork","cache","thumbnail","offline")))

            folder_lines = []
            for folder in folders:
                name = folder.get("name") or folder.get("path") or "Pasta"
                path = str(folder.get("path") or "")
                async def remove_folder(_event, ref=path, display_name=name):
                    confirm(
                        "Remover pasta da biblioteca?",
                        f'"{display_name}" será removida somente da configuração da biblioteca. Nenhum arquivo físico será apagado.',
                        "Remover",
                        lambda: on_remove_folder(ref),
                    )
                folder_lines.append(
                    ft.Row([
                        ft.Text(f"• {name}", color=TEXT_MUTED, size=11, expand=True),
                        ft.TextButton("Remover", on_click=remove_folder),
                    ])
                )
            media_label = {"full":"Permitida","partial":"Parcial","denied":"Negada"}.get(media_state, "Desconhecida")
            broad_label = "Disponível" if broad_state == "available" else "Indisponível"
            items.append(section("Armazenamento", ft.Icons.STORAGE_OUTLINED, [
                ft.Text(f"Permissão de vídeos: {media_label}", color=TEXT, size=12),
                ft.Text(f"Acesso amplo: {broad_label} • SAF autorizadas: {len(saf_roots)} • volumes ativos: {len(volumes)}", color=TEXT_MUTED, size=11),
                ft.Column(folder_lines or [ft.Text("Nenhuma pasta indexada.", color=TEXT_MUTED, size=11)], spacing=2),
                ft.Row([
                    ft.OutlinedButton("Adicionar pasta", icon=ft.Icons.CREATE_NEW_FOLDER, on_click=add_folder),
                    ft.OutlinedButton("Atualizar biblioteca", icon=ft.Icons.REFRESH, on_click=refresh),
                ], wrap=True),
                ft.Row([
                    ft.OutlinedButton("Verificar permissão de vídeos", on_click=permission),
                    ft.OutlinedButton("Armazenamento amplo", on_click=broad),
                ], wrap=True),
            ], ("storage","armazenamento","permission","saf","mediastore","scan")))

            items.append(section("Dados e Cache", ft.Icons.CACHED_OUTLINED, [
                ft.Text(f"{summary['folders']} pasta(s) • {summary['animes']} anime(s) • {summary['episodes']} episódio(s)", color=TEXT, size=12),
                ft.Text("Limpar cache não remove catálogo, consumo, favoritos, tags, notas, pins, IDs AniList ou arquivos.", color=TEXT_MUTED, size=10),
                ft.Row([
                    ft.OutlinedButton("Exportar configurações", icon=ft.Icons.UPLOAD_FILE, on_click=lambda e: page.run_task(export_settings, e)),
                    ft.OutlinedButton("Importar configurações", icon=ft.Icons.DOWNLOAD, on_click=lambda e: page.run_task(import_settings, e)),
                ], wrap=True, spacing=8),
                action_row("Restaurar configurações", "Reseta somente Settings; não é backup/restore completo.", "Restaurar", reset_all),
            ], ("dados","cache","reset","exportar","importar","backup de configurações")))

            items.append(section("Privacidade", ft.Icons.PRIVACY_TIP_OUTLINED, [
                ft.Text("Biblioteca, histórico e caminhos locais permanecem locais.", color=TEXT, size=12),
                ft.Text("Não há analytics, tracking ou upload da biblioteca. Google Login não é requisito para reprodução local.", color=TEXT_MUTED, size=10),
            ], ("privacidade","local","offline","google")))

            database_ok, database_detail = store.database_check() if hasattr(store, "database_check") else (False, "não disponível")
            database_label = "OK" if database_ok else f"ERRO ({database_detail})"
            items.append(section("Diagnóstico", ft.Icons.BUG_REPORT_OUTLINED, [
                ft.Text(f"Database: {database_label} • Schema SQLite: {getattr(store, 'SCHEMA_VERSION', '—')}", color=TEXT if database_ok else "#FFB4AB", size=11),
                ft.Text(f"Scan: {scan.get('state') or 'IDLE'} • encontrados: {int(scan.get('found') or 0)} • arquivos: {int(scan.get('files') or 0)}", color=TEXT_MUTED, size=11),
                ft.Text(f"Volumes removíveis: {len(volumes)} • SAF: {len(saf_roots)}", color=TEXT_MUTED, size=11),
                ft.Text("Python/Flet: Flet 0.86.5 • Android target 36", color=TEXT_MUTED, size=11),
                ft.Text("Abrir Settings não inicia scan, AniList request, artwork download ou player.", color=TEXT_MUTED, size=10),
            ], ("diagnóstico","logs","database","index","player","android")))

            items.append(section("Sobre", ft.Icons.INFO_OUTLINE, [
                ft.Text("Rei-Flix Local", color=TEXT, size=14, weight=ft.FontWeight.BOLD),
                ft.Text("Versão real do projeto: 0.2.1 • Flet 0.86.5", color=TEXT_MUTED, size=11),
                ft.Text("Licença do projeto: não declarada no repositório atual.", color=TEXT_MUTED, size=11),
                ft.Text("Player nativo: Media3. Storage: MediaStore / SAF / scanner nativo.", color=TEXT_MUTED, size=11),
            ], ("sobre","versão","build","licença","media3")))
            return items

        rebuild()
        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.IconButton(icon=ft.Icons.ARROW_BACK, tooltip="Voltar", on_click=lambda _: on_back()),
                    ft.Text("Configurações", size=20, weight=ft.FontWeight.BOLD, color=TEXT),
                ]),
                search,
                sections_host,
                status,
            ], spacing=10, expand=True),
            padding=PAGE_PADDING,
            bgcolor=BACKGROUND,
            expand=True,
        )
