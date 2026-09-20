"""Small, platform-independent navigation and Android back policy."""
from __future__ import annotations

import time


class NavigationController:
    """Keeps the actual Rei-flix screen history and the double-back exit window."""

    ROOT = "home"

    def __init__(self, clock=time.monotonic, exit_window_seconds: float = 2.0):
        self._stack = [self.ROOT]
        self._clock = clock
        self._exit_window_seconds = exit_window_seconds
        self._exit_requested_at: float | None = None

    @property
    def current(self) -> str:
        return self._stack[-1]

    @property
    def stack(self) -> tuple[str, ...]:
        return tuple(self._stack)

    def push(self, screen: str) -> None:
        self._stack.append(screen)
        self._exit_requested_at = None

    def replace(self, screen: str) -> None:
        self._stack[-1] = screen
        self._exit_requested_at = None

    def reset_to_root(self) -> None:
        self._stack = [self.ROOT]
        self._exit_requested_at = None

    def back(self) -> str:
        """Return ``previous``, ``prompt_exit`` or ``exit`` for one back event."""
        if len(self._stack) > 1:
            self._stack.pop()
            self._exit_requested_at = None
            return "previous"
        now = self._clock()
        if self._exit_requested_at is not None and now - self._exit_requested_at <= self._exit_window_seconds:
            self._exit_requested_at = None
            return "exit"
        self._exit_requested_at = now
        return "prompt_exit"


class SafSelectionState:
    """Tracks only the period in which Android's tree picker has no result yet."""

    def __init__(self):
        self.pending = False

    def begin(self) -> bool:
        if self.pending:
            return False
        self.pending = True
        return True

    def finish(self) -> None:
        self.pending = False
