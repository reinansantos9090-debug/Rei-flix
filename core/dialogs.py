"""Flet 0.86-compatible modal dismissal helpers."""
from __future__ import annotations


def dismiss_dialog(page, dialog) -> None:
    """Close and detach an AlertDialog without calling its nonexistent ``close`` API."""
    dialog.open = False
    try:
        page.overlay.remove(dialog)
    except (AttributeError, ValueError):
        pass
    page.update()
