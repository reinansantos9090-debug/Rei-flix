import tempfile
import unittest

from core.google_account import GoogleAccountController
from core.library_store import LibraryStore


class GoogleAccountControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = LibraryStore(self.tmp.name)
        self.account = GoogleAccountController(self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def test_initial_state_is_disconnected_and_login_is_single_flight(self):
        self.assertEqual(self.account.state, "disconnected")
        self.assertTrue(self.account.begin())
        self.assertFalse(self.account.begin())
        self.account.awaiting_google()
        self.assertFalse(self.account.begin())

    def test_success_persists_only_profile_and_recovers_after_restart(self):
        self.account.begin()
        self.assertTrue(self.account.complete({"id": "google-subject", "name": "Rei", "email": "rei@example.com", "picture": "https://img"}))
        self.assertEqual(self.account.state, "connected")
        self.assertEqual(GoogleAccountController(LibraryStore(self.tmp.name)).account()["id"], "google-subject")

    def test_cancel_and_error_release_busy_state(self):
        self.account.begin(); self.account.awaiting_google(); self.account.cancel()
        self.assertEqual(self.account.state, "disconnected")
        self.assertTrue(self.account.begin())
        self.account.fail()
        self.assertEqual(self.account.state, "error")
        self.assertTrue(self.account.begin())

    def test_invalid_mailbox_payload_does_not_create_an_account(self):
        for payload in (None, {}, {"id": "subject"}, {"id": "subject", "email": "not-an-email"}):
            self.assertFalse(self.account.complete(payload))
            self.assertEqual(self.store.account(), {})

    def test_logout_removes_account_without_removing_library(self):
        anime = self.store.upsert_anime("naruto", {"title": "Naruto", "genres": "[]"})
        self.store.upsert_episode(anime, "/n.mkv", "Naruto - 001.mkv", 1, 1)
        self.account.complete({"id": "google-subject", "email": "rei@example.com"})
        self.account.logout()
        self.assertEqual(self.store.account(), {})
        self.assertEqual(self.store.library_summary()["animes"], 1)
