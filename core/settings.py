"""Single-source settings facade for Rei-Flix.

Preferences are persisted by the existing LibraryStore.preferences table.  This
module adds schema/default/validation semantics without introducing another
database or settings backend.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class SettingDefinition:
    key: str
    kind: str
    default: Any
    choices: tuple[Any, ...] = ()

class SettingsDefaults:
    DEFINITIONS = (
        SettingDefinition("app.start_screen", "enum", "home", ("home", "organize")),
        SettingDefinition("app.confirm_destructive", "bool", True),
        SettingDefinition("app.animations", "bool", True),
        SettingDefinition("appearance.theme", "enum", "dark", ("system", "light", "dark")),
        SettingDefinition("appearance.card_size", "enum", "medium", ("small", "medium", "large")),
        SettingDefinition("appearance.show_thumbnails", "bool", True),
        SettingDefinition("appearance.show_badges", "bool", True),
        SettingDefinition("library.sort_default", "enum", "added_desc", ("added_desc", "title_asc", "title_desc", "recently_watched")),
        SettingDefinition("library.grid_density", "enum", "medium", ("small", "medium", "large")),
        SettingDefinition("library.continue_watching", "bool", True),
        SettingDefinition("library.continue_watching_limit", "int", 10),
        SettingDefinition("player.autoplay_next", "bool", True),
        SettingDefinition("player.resume", "bool", True),
        SettingDefinition("player.default_speed", "float", 1.0, (0.5, 0.75, 1.0, 1.25, 1.5, 2.0)),
        SettingDefinition("player.aspect_ratio", "enum", "fit", ("auto", "fit", "fill", "zoom", "original")),
        SettingDefinition("player.immersive", "enum", "always", ("always", "landscape", "never")),
        SettingDefinition("player.rotation", "enum", "auto", ("auto", "portrait", "landscape")),
        SettingDefinition("player.pip", "bool", True),
        SettingDefinition("player.auto_hide_seconds", "int", 5, (5, 10, 15, 30, 0)),
        SettingDefinition("gestures.volume", "bool", False),
        SettingDefinition("gestures.brightness", "bool", False),
        SettingDefinition("gestures.double_tap", "bool", False),
        SettingDefinition("gestures.long_press", "bool", False),
        SettingDefinition("audio.preferred_language", "string", ""),
        SettingDefinition("audio.preferred_subtitle_language", "string", ""),
        SettingDefinition("audio.subtitles", "enum", "auto", ("auto", "always", "never")),
        SettingDefinition("metadata.anilist_enabled", "bool", True),
        SettingDefinition("metadata.auto_match", "bool", True),
        SettingDefinition("metadata.keep_local", "bool", True),
        SettingDefinition("artwork.enabled", "bool", True),
        SettingDefinition("artwork.offline_cache", "bool", True),
        SettingDefinition("privacy.external_sync", "bool", False),
    )
    BY_KEY = {item.key: item for item in DEFINITIONS}

class SettingsValidationError(ValueError):
    pass

class SettingsStore:
    SCHEMA_VERSION = 1

    def __init__(self, store):
        self.store = store
        self._migrate_legacy_keys()

    def _migrate_legacy_keys(self):
        legacy = {
            "resume_playback": "player.resume",
            "autoplay_next": "player.autoplay_next",
            "gesture_volume": "gestures.volume",
            "gesture_brightness": "gestures.brightness",
            "gesture_double_tap": "gestures.double_tap",
            "gesture_long_press": "gestures.long_press",
        }
        for old, new in legacy.items():
            value = self.store.get_preference(old)
            if value is not None and self.store.get_preference(new) is None:
                definition = SettingsDefaults.BY_KEY[new]
                try:
                    self._write(new, self._coerce(definition, value))
                except SettingsValidationError:
                    continue

    @staticmethod
    def _coerce(definition: SettingDefinition, value: Any):
        if definition.kind == "bool":
            if isinstance(value, bool):
                return value
            if str(value).strip().casefold() in {"true", "1", "yes", "on"}:
                return True
            if str(value).strip().casefold() in {"false", "0", "no", "off"}:
                return False
            raise SettingsValidationError(f"valor booleano inválido para {definition.key}")
        if definition.kind == "int":
            if isinstance(value, bool):
                raise SettingsValidationError(f"inteiro inválido para {definition.key}")
            number = int(value)
            if number < 0:
                raise SettingsValidationError(f"inteiro negativo para {definition.key}")
            if definition.choices and number not in definition.choices:
                raise SettingsValidationError(f"valor não permitido para {definition.key}")
            return number
        if definition.kind == "float":
            number = float(value)
            if number <= 0:
                raise SettingsValidationError(f"número inválido para {definition.key}")
            if definition.choices and number not in definition.choices:
                raise SettingsValidationError(f"valor não permitido para {definition.key}")
            return number
        if definition.kind in {"enum", "string"}:
            text = str(value)
            if definition.kind == "enum" and text not in definition.choices:
                raise SettingsValidationError(f"opção não permitida para {definition.key}")
            return text
        raise SettingsValidationError(f"tipo desconhecido: {definition.kind}")

    @staticmethod
    def _encode(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    def _write(self, key, value):
        self.store.set_preference(key, self._encode(value))
        self.store.set_preference("settings.schema_version", str(self.SCHEMA_VERSION))

    def get(self, key):
        definition = SettingsDefaults.BY_KEY[key]
        raw = self.store.get_preference(key)
        if raw is None:
            return definition.default
        try:
            return self._coerce(definition, raw)
        except (ValueError, TypeError, SettingsValidationError):
            # A single corrupt key falls back without resetting unrelated settings.
            return definition.default

    def set(self, key, value):
        if key not in SettingsDefaults.BY_KEY:
            raise SettingsValidationError(f"chave desconhecida: {key}")
        definition = SettingsDefaults.BY_KEY[key]
        normalized = self._coerce(definition, value)
        self._write(key, normalized)
        return normalized

    def reset(self, key):
        if key not in SettingsDefaults.BY_KEY:
            raise SettingsValidationError(f"chave desconhecida: {key}")
        value = SettingsDefaults.BY_KEY[key].default
        self._write(key, value)
        return value

    def reset_category(self, prefix: str):
        changed = 0
        for key in SettingsDefaults.BY_KEY:
            if key.startswith(prefix + "."):
                self.reset(key)
                changed += 1
        return changed

    def reset_all(self):
        for key in SettingsDefaults.BY_KEY:
            self.reset(key)

    def snapshot(self):
        return {key: self.get(key) for key in SettingsDefaults.BY_KEY}
