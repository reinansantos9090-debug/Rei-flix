"""Local, token-free state machine for the optional Google identity."""
from __future__ import annotations


class GoogleAccountController:
    """Persist only the profile projection delivered by Android Credential Manager."""

    BUSY = {"initiating", "awaiting_google"}

    def __init__(self, store):
        self.store = store
        self.state = "connected" if self.account().get("email") else "disconnected"

    def account(self) -> dict:
        return self.store.account()

    def begin(self) -> bool:
        if self.state in self.BUSY:
            return False
        self.state = "initiating"
        return True

    def awaiting_google(self) -> None:
        self.state = "awaiting_google"

    def configuration_required(self) -> None:
        self.state = "configuration_required"

    def cancel(self) -> None:
        self.state = "connected" if self.account().get("email") else "disconnected"

    def fail(self) -> None:
        self.state = "error"

    def complete(self, payload: object) -> bool:
        if not isinstance(payload, dict):
            self.fail()
            return False
        profile = {key: str(payload.get(key) or "").strip() for key in ("id", "name", "email", "picture")}
        # Both claims are required to ensure an arbitrary mailbox entry cannot
        # create an apparently authenticated local account.
        if not profile["id"] or not profile["email"] or "@" not in profile["email"]:
            self.fail()
            return False
        self.store.save_account(profile)
        self.state = "connected"
        return True

    def logout(self) -> None:
        self.store.clear_account()
        self.state = "disconnected"
