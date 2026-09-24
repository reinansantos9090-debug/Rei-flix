import os
import sqlite3
import tempfile
import unittest

from core.library_store import LibraryStore
from core.recovery import RecoveryError, RecoveryService


class RecoveryModeTests(unittest.TestCase):
    def test_healthy_database_does_not_require_recovery(self):
        with tempfile.TemporaryDirectory() as root:
            store = LibraryStore(root)
            status = RecoveryService(store).diagnose()
            self.assertFalse(status["required"])
            self.assertEqual("ok", status["quick_check"].casefold())
            self.assertTrue(status["foreign_key_ok"])

    def test_inconsistent_database_enters_recovery_without_deleting_it(self):
        with tempfile.TemporaryDirectory() as root:
            store = LibraryStore(root)
            with sqlite3.connect(store.db_path) as con:
                con.execute("CREATE TABLE recovery_probe(id INTEGER)")
                con.execute("INSERT INTO recovery_probe VALUES (1)")
                con.commit()
            # A deliberately malformed SQLite header makes the health check fail.
            with open(store.db_path, "r+b") as handle:
                handle.seek(0)
                handle.write(b"not-a-sqlite-database")
            status = RecoveryService(store).diagnose()
            self.assertTrue(status["required"])
            self.assertTrue(os.path.isfile(store.db_path))

    def test_recovery_restore_is_explicit_and_preserves_account_when_readable(self):
        with tempfile.TemporaryDirectory() as source_root, tempfile.TemporaryDirectory() as target_root:
            source = LibraryStore(source_root)
            source.save_account({"email": "local@example.invalid", "name": "Local"})
            backup = source.create_backup()
            target = LibraryStore(target_root)
            target.save_account({"email": "keep@example.invalid", "name": "Keep"})
            service = RecoveryService(target)
            result = service.restore_backup(open(backup, "rb").read())
            self.assertTrue(result["restart_required"])
            restored = LibraryStore(target_root)
            self.assertEqual("keep@example.invalid", restored.account().get("email"))

    def test_recovery_refuses_restore_if_authentication_cannot_be_read(self):
        with tempfile.TemporaryDirectory() as root:
            store = LibraryStore(root)
            with open(store.db_path, "r+b") as handle:
                handle.seek(0)
                handle.write(b"not-a-sqlite-database")
            with self.assertRaises(RecoveryError) as ctx:
                RecoveryService(store).restore_backup(b"invalid")
            self.assertEqual("RECOVERY_BACKUP_INVALID", ctx.exception.code)
