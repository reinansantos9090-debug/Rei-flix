"""State machine for Settings focus events.

This module deliberately contains no Flet dependencies so focus behavior can be
verified independently from the UI runtime.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FocusDecision:
    should_scroll: bool
    reason: str
    generation: int


class SettingsFocusState:
    """Classify Settings focus events and suppress non-user-driven duplicates."""

    def __init__(self) -> None:
        self._initial_focus_pending = True
        self._last_key: str | None = None
        self._generation = 0

    @property
    def generation(self) -> int:
        return self._generation

    def on_focus(self, key: str) -> FocusDecision:
        self._generation += 1
        normalized = str(key or "").strip()
        if not normalized:
            return FocusDecision(False, "invalid", self._generation)

        if self._initial_focus_pending:
            self._initial_focus_pending = False
            self._last_key = normalized
            return FocusDecision(False, "initial", self._generation)

        if normalized == self._last_key:
            return FocusDecision(False, "duplicate", self._generation)

        self._last_key = normalized
        return FocusDecision(True, "navigation", self._generation)

    def reset_for_rebuild(self) -> None:
        """Reset only the per-view focus state after a new control tree is built."""
        self._initial_focus_pending = True
        self._last_key = None
